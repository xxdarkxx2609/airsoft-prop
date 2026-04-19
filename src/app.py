"""Application core — state machine, HAL initialization, and main loop.

The App class ties together all components: HAL, config, screens, and
game modes. It runs the main event loop that polls for input, ticks
screens, and renders the display.
"""

from __future__ import annotations

import queue
import signal
import sys
import time
from typing import Any, Optional

from src.hal.base import (
    AudioBase,
    BatteryBase,
    DisplayBase,
    InputBase,
    LedBase,
    UsbDetectorBase,
    WiresBase,
)
from src.modes.base_mode import BaseMode, GameContext, ModeResult
from src.ui.lcd_helpers import register_custom_chars
from src.ui.screen_manager import ScreenManager
from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Target frame time for the main loop (~30 fps).
_LOOP_INTERVAL: float = 1.0 / 15.0


class App:
    """Main application class — owns HAL, screens, and the event loop.

    Attributes:
        config: Application configuration.
        display: Display HAL instance.
        audio: Audio HAL instance.
        input: Input HAL instance.
        wires: Wires HAL instance.
        battery: Battery HAL instance.
        screen_manager: Manages screen transitions.
        modes: Discovered game mode instances.
        selected_mode: Currently selected game mode (set by menu).
        game_context: Runtime context for the current game (set by setup).
        game_result: Result of the last game (set by armed screen).
    """

    def __init__(self, mock: bool = False) -> None:
        """Initialize the application.

        Args:
            mock: If True, force all HAL modules to their mock variants
                  regardless of hardware.yaml settings.
        """
        self.config = Config()
        self._mock = mock

        # HAL instances (initialized in _init_hal)
        self.display: DisplayBase = None  # type: ignore[assignment]
        self.audio: AudioBase = None  # type: ignore[assignment]
        self.input: InputBase = None  # type: ignore[assignment]
        self.wires: WiresBase = None  # type: ignore[assignment]
        self.battery: BatteryBase = None  # type: ignore[assignment]
        self.usb_detector: UsbDetectorBase = None  # type: ignore[assignment]
        self.led: LedBase = None  # type: ignore[assignment]

        # UI
        self.screen_manager = ScreenManager()

        # Game state
        self.modes: list[BaseMode] = []
        self.selected_mode: Optional[BaseMode] = None
        self.game_context: Optional[GameContext] = None
        self.game_result: Optional[ModeResult] = None

        # Tournament transition target ("enter" or "leave")
        self.tournament_transition_target: str = ""

        # Cross-thread event queue (WebUI → main loop)
        self._event_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        # Captive portal / AP management (initialized in _init_network)
        self.captive_portal: object | None = None

        # Web server (lazy import — avoids Flask dependency when disabled)
        self._web_server: object | None = None

        self._running = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Initialize all subsystems: HAL, modes, screens."""
        logger.info("Initializing application (mock=%s)", self._mock)
        self._init_hal()
        self._init_modes()
        self._init_screens()
        register_custom_chars(self.display)
        self._init_network()
        self._init_web_server()
        self._log_startup_info()
        logger.info("Application initialized successfully")

    def _init_hal(self) -> None:
        """Create and initialize HAL instances based on config or mock flag."""
        if self._mock:
            self._init_mock_hal()
        else:
            self._init_real_hal()

        self.display.init()
        self.audio.init()
        self.input.init()
        self.wires.init()
        self.battery.init()
        self.usb_detector.init()
        self.led.init()

        # Apply config
        volume = self.config.get("audio", "volume", default=0.8)
        self.audio.set_volume(volume)
        backlight = self.config.get("display", "backlight", default=True)
        self.display.set_backlight(backlight)

    def _init_mock_hal(self) -> None:
        """Initialize mock HAL for desktop testing.

        Uses ``PygameDisplay`` for a graphical LCD window when pygame-ce is
        available. Falls back to the terminal-based ``MockDisplay`` otherwise.
        The pygame display and ``MockInput`` share a key queue so that keys
        pressed in the graphical window reach the application.
        """
        import queue as _queue

        from src.hal.audio_mock import MockAudio
        from src.hal.battery_none import NoBattery
        from src.hal.input_mock import MockInput
        from src.hal.usb_detector_mock import MockUsbDetector
        from src.hal.wires_mock import MockWires
        from src.hal.led_mock import MockLed

        try:
            import pygame  # noqa: F401  (availability check only)
            from src.hal.display_mock_pygame import PygameDisplay

            shared_key_queue: _queue.Queue[str] = _queue.Queue()
            self.display = PygameDisplay(
                key_queue=shared_key_queue,
                on_quit=self.shutdown,
            )
            self.input = MockInput(external_key_queue=shared_key_queue)
            logger.info("Mock HAL: using PygameDisplay")
        except ImportError:
            from src.hal.display_mock import MockDisplay
            self.display = MockDisplay()
            self.input = MockInput()
            logger.info("Mock HAL: pygame not available, using MockDisplay (terminal)")

        self.audio = MockAudio()
        self.wires = MockWires()
        self.battery = NoBattery()
        self.usb_detector = MockUsbDetector()
        self.led = MockLed()
        logger.info("Mock HAL initialized")

    @staticmethod
    def _load_custom_hal(hal_spec: str) -> Any:
        """Load a HAL class from custom/hal/ given a 'custom:module.Class' spec.

        Args:
            hal_spec: String like 'custom:my_display.MyDisplay'.

        Returns:
            Instantiated HAL object.
        """
        import importlib.util as ilu
        from src.utils.paths import get_project_root

        _, module_class = hal_spec.split(":", 1)
        module_name, class_name = module_class.rsplit(".", 1)
        custom_hal_dir = get_project_root() / "custom" / "hal"
        spec = ilu.spec_from_file_location(
            f"custom.hal.{module_name}",
            custom_hal_dir / f"{module_name}.py",
        )
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load custom HAL: {hal_spec}")
        module = ilu.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, class_name)
        return cls()

    def _init_real_hal(self) -> None:
        """Initialize real HAL based on hardware.yaml config.

        Falls back to mock for components where the real driver fails
        to import (e.g. running on a desktop without RPi libraries).
        Supports ``custom:module.Class`` syntax for user-provided HAL
        implementations in ``custom/hal/``.
        """
        # Helper to check custom: prefix for any HAL component.
        def _try_custom(component_name: str) -> Any | None:
            hal_type = self.config.get_hal_type(component_name)
            if hal_type.startswith("custom:"):
                try:
                    return self._load_custom_hal(hal_type)
                except Exception:
                    logger.error("Failed to load custom HAL '%s'", hal_type, exc_info=True)
                    return None
            return None

        # Display
        display_type = self.config.get_hal_type("display")
        custom = _try_custom("display")
        if custom is not None:
            self.display = custom
        elif display_type == "lcd":
            try:
                from src.hal.display_lcd import LcdDisplay
                self.display = LcdDisplay(self.config)
            except ImportError:
                logger.warning("LCD driver not available, falling back to mock")
                from src.hal.display_mock import MockDisplay
                self.display = MockDisplay()
        else:
            from src.hal.display_mock import MockDisplay
            self.display = MockDisplay()

        # Audio
        audio_type = self.config.get_hal_type("audio")
        custom = _try_custom("audio")
        if custom is not None:
            self.audio = custom
        elif audio_type == "pygame":
            try:
                from src.hal.audio import PygameAudio
                self.audio = PygameAudio(self.config)
            except ImportError:
                logger.warning("Pygame not available, falling back to mock audio")
                from src.hal.audio_mock import MockAudio
                self.audio = MockAudio()
        else:
            from src.hal.audio_mock import MockAudio
            self.audio = MockAudio()

        # Input
        input_type = self.config.get_hal_type("input")
        custom = _try_custom("input")
        if custom is not None:
            self.input = custom
        elif input_type == "numpad":
            try:
                from src.hal.input_numpad import NumpadInput
                self.input = NumpadInput(self.config)
            except ImportError:
                logger.warning("Numpad driver not available, falling back to mock")
                from src.hal.input_mock import MockInput
                self.input = MockInput()
        else:
            from src.hal.input_mock import MockInput
            self.input = MockInput()

        # Wires
        wires_type = self.config.get_hal_type("wires")
        custom = _try_custom("wires")
        if custom is not None:
            self.wires = custom
        elif wires_type == "gpio":
            try:
                from src.hal.wires import GpioWires
                self.wires = GpioWires(self.config)
            except ImportError:
                logger.warning("GPIO not available, falling back to mock wires")
                from src.hal.wires_mock import MockWires
                self.wires = MockWires()
        else:
            from src.hal.wires_mock import MockWires
            self.wires = MockWires()

        # USB detector
        usb_type = self.config.get_hal_type("usb_detector")
        if usb_type == "usb_detector":
            try:
                from src.hal.usb_detector import UsbDetector
                self.usb_detector = UsbDetector(config=self.config)
            except ImportError:
                logger.warning("USB detector not available, falling back to mock")
                from src.hal.usb_detector_mock import MockUsbDetector
                self.usb_detector = MockUsbDetector()
        else:
            from src.hal.usb_detector_mock import MockUsbDetector
            self.usb_detector = MockUsbDetector()

        # LED
        led_type = self.config.get_hal_type("led")
        if led_type == "gpio":
            try:
                from src.hal.led import GpioLed
                self.led = GpioLed(self.config)
            except ImportError:
                logger.warning("GPIO not available, falling back to mock LED")
                from src.hal.led_mock import MockLed
                self.led = MockLed()
        else:
            from src.hal.led_mock import MockLed
            self.led = MockLed()

        # Battery
        if self._mock:
            from src.hal.battery_mock import MockBattery
            self.battery = MockBattery()
        else:
            battery_type = self.config.get_hal_type("battery")
            if battery_type == "pisugar":
                try:
                    from src.hal.battery_pisugar import PiSugarBattery
                    self.battery = PiSugarBattery(self.config)
                except ImportError:
                    logger.warning("PiSugar not available, falling back to none")
                    from src.hal.battery_none import NoBattery
                    self.battery = NoBattery()
            else:
                from src.hal.battery_none import NoBattery
                self.battery = NoBattery()

    def _init_modes(self) -> None:
        """Discover and instantiate game modes."""
        from src.modes import discover_modes

        mode_classes = discover_modes()
        self.modes = [cls() for cls in mode_classes]
        logger.info(
            "Discovered %d game modes: %s",
            len(self.modes),
            ", ".join(m.name for m in self.modes),
        )

    def _init_screens(self) -> None:
        """Create and register all screens."""
        from src.ui.armed_screen import ArmedScreen
        from src.ui.boot_screen import BootScreen
        from src.ui.menu_screen import MenuScreen
        from src.ui.planting_screen import PlantingScreen
        from src.ui.result_screen import ResultScreen
        from src.ui.setup_screen import SetupScreen
        from src.ui.status_screen import StatusScreen
        from src.ui.tournament_screen import TournamentScreen
        from src.ui.tournament_transition_screen import TournamentTransitionScreen
        from src.ui.update_screen import UpdateScreen

        self.screen_manager.register("boot", BootScreen(self))
        self.screen_manager.register("menu", MenuScreen(self))
        self.screen_manager.register("setup", SetupScreen(self))
        self.screen_manager.register("planting", PlantingScreen(self))
        self.screen_manager.register("armed", ArmedScreen(self))
        self.screen_manager.register("result", ResultScreen(self))
        self.screen_manager.register("status", StatusScreen(self))
        self.screen_manager.register("update", UpdateScreen(self))
        self.screen_manager.register("tournament", TournamentScreen(self))
        self.screen_manager.register("tournament_transition", TournamentTransitionScreen(self))

    def _init_network(self) -> None:
        """Initialize captive portal / AP fallback.

        Checks WiFi connectivity and starts the access point if no
        network is available.  A background monitor re-enables the AP
        if WiFi drops at runtime.
        """
        try:
            from src.web.captive_portal import create_captive_portal

            self.captive_portal = create_captive_portal(
                self.config, mock=self._mock,
            )
            if not self.captive_portal.is_wifi_connected():
                logger.info("No WiFi connection — starting AP mode")
                self.captive_portal.start_ap()
            self.captive_portal.start_monitor()
        except ImportError as e:
            logger.warning("Captive portal module not available — %s", e)

    def _init_web_server(self) -> None:
        """Start the web server in a background thread."""
        if self.config.get("web", "enabled", default=True):
            try:
                from src.web.server import WebServer
                self._web_server = WebServer(
                    config=self.config,
                    mock=self._mock,
                    battery=self.battery,
                    app=self,
                    captive_portal=self.captive_portal,
                )
                self._web_server.start()
            except ImportError as e:
                logger.warning("Flask not available — web server disabled: %s", e)

    # ------------------------------------------------------------------
    # Cross-thread events
    # ------------------------------------------------------------------

    def post_event(self, event: dict[str, Any]) -> None:
        """Post an event from any thread (e.g. Flask) for the main loop.

        Args:
            event: Event dict with at least a ``"type"`` key.
        """
        self._event_queue.put(event)
        logger.debug("Event posted: %s", event.get("type"))

    def _process_events(self) -> None:
        """Drain the event queue and handle known event types.

        Called once per frame at the start of the main loop iteration.
        """
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break

            event_type = event.get("type")

            if event_type == "tournament_activate":
                logger.info("Tournament mode activated via event")
                self.tournament_transition_target = "enter"
                self.screen_manager.switch_to("tournament_transition")

            elif event_type == "tournament_deactivate":
                logger.info("Tournament mode deactivated via event")
                self.config.save_user_config({"tournament.enabled": False})
                self.tournament_transition_target = "leave"
                self.screen_manager.switch_to("tournament_transition")

            elif event_type == "tournament_refresh":
                # Re-enter tournament screen to pick up new mode/settings
                if self.screen_manager.active_name == "tournament":
                    logger.info("Refreshing tournament screen (settings changed)")
                    self.screen_manager.switch_to("tournament")

            elif event_type == "audio_volume_changed":
                volume = float(event.get("value", 0.8))
                logger.info("Audio volume changed via web: %.2f", volume)
                self.audio.set_volume(volume)

            elif event_type == "display_backlight_changed":
                on = bool(event.get("value", True))
                logger.info("Display backlight changed via web: %s",
                            "ON" if on else "OFF")
                self.display.set_backlight(on)

            elif event_type == "logging_level_changed":
                level = str(event.get("value", "INFO"))
                logger.info("Log level changed via web: %s", level)
                from src.utils.logger import set_log_level
                set_log_level(level)

            else:
                logger.warning("Unknown event type: %s", event_type)

    def is_game_in_progress(self) -> bool:
        """Check if a game is currently running (armed or planting).

        Returns:
            True if the active screen is armed or planting.
        """
        active = self.screen_manager.active_name
        return active in ("armed", "planting")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the main event loop.

        Starts at the boot screen and loops until stopped. Individual
        frame errors are logged but do not crash the application. After
        ``_MAX_CONSECUTIVE_ERRORS`` failures in a row the app shuts down
        gracefully.

        Signal Handling:
        - SIGTERM (systemd stop): triggers graceful shutdown
        - SIGINT (Ctrl+C): triggers graceful shutdown
        """
        self._running = True
        self.screen_manager.switch_to("boot")
        logger.info("Main loop started")

        # Register signal handlers for graceful shutdown
        def _signal_handler(signum: int, frame: Any) -> None:
            """Handle SIGTERM/SIGINT by setting _running to False."""
            sig_name = signal.Signals(signum).name
            logger.info(f"Received {sig_name}, initiating graceful shutdown")
            self._running = False

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        logger.debug("Signal handlers registered (SIGTERM, SIGINT)")

        _consecutive_errors = 0
        _MAX_CONSECUTIVE_ERRORS = 10

        try:
            while self._running:
                loop_start = time.time()

                try:
                    # Process cross-thread events (e.g. from WebUI)
                    self._process_events()

                    # Poll input
                    key = self.input.get_key()
                    if key is not None:
                        self.screen_manager.handle_input(key)

                    # Render
                    self.screen_manager.render(self.display)
                    self.display.flush()

                    _consecutive_errors = 0
                except Exception:
                    _consecutive_errors += 1
                    logger.exception(
                        "Error in main loop (consecutive: %d/%d)",
                        _consecutive_errors,
                        _MAX_CONSECUTIVE_ERRORS,
                    )
                    if _consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                        logger.critical(
                            "Too many consecutive errors, shutting down",
                        )
                        break

                # Frame rate limiting (outside try so loop never spins
                # at full speed on repeated errors).
                elapsed = time.time() - loop_start
                sleep_time = _LOOP_INTERVAL - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Interrupted by user (KeyboardInterrupt)")
        finally:
            self.shutdown()

    def _log_startup_info(self) -> None:
        """Log system information for remote debugging."""
        import platform

        logger.info(
            "Python %s on %s (%s)",
            sys.version, platform.system(), platform.machine(),
        )
        logger.info(
            "HAL: display=%s, audio=%s, input=%s, wires=%s, usb=%s, battery=%s, led=%s",
            type(self.display).__name__,
            type(self.audio).__name__,
            type(self.input).__name__,
            type(self.wires).__name__,
            type(self.usb_detector).__name__,
            type(self.battery).__name__,
            type(self.led).__name__,
        )
        logger.info("Modes: %s", ", ".join(m.name for m in self.modes))
        logger.info(
            "Config: version=%s, timer=%s, volume=%s",
            self.config.get("version", default="?"),
            self.config.get("game", "default_timer", default="?"),
            self.config.get("audio", "volume", default="?"),
        )

    def shutdown(self, clear_display: bool = True) -> None:
        """Shut down all subsystems gracefully.

        Logs each shutdown step so that slow shutdowns can be debugged.
        Timing: typically < 5s for clean shutdown, 15s timeout before systemd
        force-kills.

        Args:
            clear_display: If True (default), clear the display during shutdown.
                If False, preserve display content (used for EXIT screen messages).
        """
        self._running = False
        logger.info("Shutting down application...")
        _shutdown_start = time.time()

        # Shutdown order: web first (stop accepting connections),
        # then peripherals, then HAL
        try:
            if self.captive_portal:
                logger.debug("Stopping captive portal...")
                _cp_start = time.time()
                self.captive_portal.shutdown()
                _cp_elapsed = time.time() - _cp_start
                logger.debug(f"Captive portal shut down in {_cp_elapsed:.2f}s")
        except Exception:
            logger.exception("Error shutting down captive portal")

        try:
            if self._web_server:
                logger.debug("Stopping web server...")
                _ws_start = time.time()
                self._web_server.stop()
                _ws_elapsed = time.time() - _ws_start
                logger.debug(f"Web server shut down in {_ws_elapsed:.2f}s")
        except Exception:
            logger.exception("Error shutting down web server")

        # HAL shutdown
        try:
            logger.debug("Stopping HAL components...")
            self.display.shutdown(clear_display=clear_display)
            self.audio.shutdown()
            self.input.shutdown()
            self.wires.shutdown()
            self.usb_detector.shutdown()
            self.battery.shutdown()
            self.led.shutdown()
        except Exception:
            logger.exception("Error shutting down HAL")

        _shutdown_elapsed = time.time() - _shutdown_start
        logger.info(f"Application shut down complete ({_shutdown_elapsed:.2f}s)")
