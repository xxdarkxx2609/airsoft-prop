"""Tournament screen — locked-down lobby for tournament mode.

Displays the configured game mode and a single 'Start Game' action.
Players cannot access settings, status, or update screens.
Supports PIN-based and USB-based exit mechanisms for the organizer.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from src.hal.base import DisplayBase
from src.modes.base_mode import BaseMode, GameContext, PlantingType, SetupOptionType
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Number of rapid backspace presses to trigger PIN entry.
_PIN_TRIGGER_COUNT: int = 5
# Time window for the rapid presses (seconds).
_PIN_TRIGGER_WINDOW: float = 3.0
# PIN input timeout (seconds).
_PIN_INPUT_TIMEOUT: float = 10.0


class TournamentScreen(BaseScreen):
    """Locked-down tournament lobby screen.

    Layout (normal state):
        Line 0: ##Tournament-Mode##
        Line 1: Game: <mode name>
        Line 2: > Start Game
        Line 3: ##Tournament-Mode##

    Layout (PIN entry state):
        Line 0: ##Tournament-Mode##
        Line 1: Enter PIN:
        Line 2: > ____
        Line 3: ##Tournament-Mode##
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._mode: Optional[BaseMode] = None
        self._mode_error: bool = False

        # PIN entry state
        self._pin_mode: bool = False
        self._pin_input: str = ""
        self._pin_last_input_time: float = 0.0

        # Backspace rapid press tracking
        self._backspace_times: list[float] = []

    def on_enter(self) -> None:
        """Look up the configured tournament mode."""
        self._pin_mode = False
        self._pin_input = ""
        self._backspace_times = []
        self._mode_error = False

        mode_module = self.app.config.get_tournament_mode()
        self._mode = self._find_mode_by_module(mode_module)

        if self._mode is None:
            self._mode_error = True
            logger.error("Tournament mode '%s' not found", mode_module)
        else:
            logger.info("Tournament screen entered: mode='%s'", self._mode.name)

    def _find_mode_by_module(self, module_name: str) -> Optional[BaseMode]:
        """Find a mode instance by its Python module name.

        Args:
            module_name: Module name like 'random_code'.

        Returns:
            The matching BaseMode instance, or None.
        """
        for mode in self.app.modes:
            if type(mode).__module__.endswith(f".{module_name}"):
                return mode
        return None

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Render the tournament screen."""
        # Check for USB tournament key each frame
        if self.app.usb_detector.is_tournament_key_present():
            logger.info("TOURNAMENT.KEY detected, exiting tournament mode")
            self._exit_tournament()
            return

        # Check PIN input timeout
        if self._pin_mode and self._pin_input:
            if time.time() - self._pin_last_input_time > _PIN_INPUT_TIMEOUT:
                logger.debug("PIN input timed out")
                self._pin_mode = False
                self._pin_input = ""

        header = "##Tournament-Mode##"
        display.write_line(0, center_text(header))

        if self._pin_mode:
            self._render_pin_entry(display)
        elif self._mode_error:
            self._render_error(display)
        else:
            self._render_lobby(display)

        display.write_line(3, center_text(header))

    def _render_lobby(self, display: DisplayBase) -> None:
        """Render the normal tournament lobby."""
        mode_name = self._mode.name if self._mode else "?"
        display.write_line(1, f" Game: {mode_name}"[:20].ljust(20))
        display.write_line(2, " > Start Game".ljust(20))

    def _render_pin_entry(self, display: DisplayBase) -> None:
        """Render the PIN entry sub-state."""
        entered = self._pin_input
        remaining = 4 - len(entered)
        pin_display = "*" * len(entered) + "_" * remaining
        display.write_line(1, center_text("Enter PIN:"))
        display.write_line(2, center_text(f"> {pin_display}"))

    def _render_error(self, display: DisplayBase) -> None:
        """Render mode-not-found error."""
        mode_module = self.app.config.get_tournament_mode()
        display.write_line(1, center_text("Mode not found!"))
        display.write_line(2, center_text(mode_module[:20]))

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Process input on the tournament screen."""
        if self._pin_mode:
            self._handle_pin_input(key)
            return

        if key == "enter" and not self._mode_error:
            self._start_game()
        elif key == "backspace":
            self._track_backspace()

    def _track_backspace(self) -> None:
        """Track rapid backspace presses to trigger PIN entry."""
        now = time.time()
        self._backspace_times.append(now)

        # Keep only presses within the time window
        cutoff = now - _PIN_TRIGGER_WINDOW
        self._backspace_times = [
            t for t in self._backspace_times if t > cutoff
        ]

        if len(self._backspace_times) >= _PIN_TRIGGER_COUNT:
            logger.info("PIN entry triggered (5x backspace)")
            self._pin_mode = True
            self._pin_input = ""
            self._pin_last_input_time = now
            self._backspace_times = []

    def _handle_pin_input(self, key: str) -> None:
        """Handle input during PIN entry."""
        if key == "backspace":
            if self._pin_input:
                self._pin_input = self._pin_input[:-1]
                self._pin_last_input_time = time.time()
            else:
                # Empty input + backspace = cancel PIN entry
                self._pin_mode = False
        elif key in "0123456789" and len(self._pin_input) < 4:
            self._pin_input += key
            self._pin_last_input_time = time.time()

            if len(self._pin_input) == 4:
                self._check_pin()

    def _check_pin(self) -> None:
        """Validate the entered PIN."""
        correct_pin = self.app.config.get_tournament_pin()
        if self._pin_input == correct_pin:
            logger.info("Correct PIN entered, exiting tournament mode")
            self._exit_tournament()
        else:
            logger.warning("Wrong PIN entered")
            self._pin_input = ""
            self._pin_mode = False

    # -- game start -----------------------------------------------------------

    def _start_game(self) -> None:
        """Build GameContext from tournament settings and start the game."""
        mode = self._mode
        if mode is None:
            return

        settings = self.app.config.get_tournament_settings()
        options = mode.get_setup_options()

        # Apply tournament settings to options
        for option in options:
            if option.key in settings:
                option.value = settings[option.key]

        # Apply config defaults for options not in tournament settings
        self._apply_config_defaults(options, mode)

        # Build setup_values and determine timer
        setup_values: dict[str, object] = {}
        timer_seconds: int = 60

        for option in options:
            setup_values[option.key] = option.value
            if option.key == "timer":
                timer_seconds = int(option.value)

        # Validate CODE_INPUT options have at least 1 digit
        for option in options:
            if option.option_type == SetupOptionType.CODE_INPUT:
                code = str(option.value) if option.value else ""
                if not code:
                    logger.warning("Tournament: no code set for '%s'", option.key)
                    return

        context = GameContext(
            timer_seconds=timer_seconds,
            remaining_seconds=timer_seconds,
            setup_values=setup_values,
        )

        # Provide HAL access and config
        context.custom_data["device_name"] = self.app.config.get(
            "game", "device_name", default="Prop"
        )
        context.custom_data["wires"] = self.app.wires
        context.custom_data["usb_detector"] = self.app.usb_detector
        context.custom_data["penalty_seconds"] = self.app.config.get(
            "game", "penalty_seconds", default=10,
        )
        context.custom_data["crack_interval"] = self.app.config.get(
            "modes", "usb_key_cracker", "crack_interval", default=2.5,
        )

        self.app.selected_mode = mode
        self.app.game_context = context
        mode.on_armed(context)

        logger.info(
            "Tournament game started: mode='%s', timer=%ds",
            mode.name,
            timer_seconds,
        )

        # Route through planting or directly to armed
        planting_config = mode.get_planting_config()
        if planting_config.planting_type == PlantingType.INSTANT:
            self.app.screen_manager.switch_to("armed")
        else:
            self.app.screen_manager.switch_to("planting")

    def _apply_config_defaults(
        self, options: list, mode: BaseMode
    ) -> None:
        """Apply config defaults to options not overridden by tournament settings."""
        config = self.app.config
        config_map: dict[str, tuple] = {
            "timer": ("game", "default_timer"),
        }
        if mode.name in ("Random Code", "Random Code+"):
            config_map["digits"] = ("modes", "random_code", "default_digits")
        elif mode.name == "USB Key Cracker":
            config_map["digits"] = ("modes", "usb_key_cracker", "default_digits")

        tournament_settings = self.app.config.get_tournament_settings()

        for option in options:
            # Only apply config defaults if not overridden by tournament settings
            if option.key not in tournament_settings and option.key in config_map:
                keys = config_map[option.key]
                cfg_val = config.get(*keys)
                if cfg_val is not None:
                    option.default = cfg_val
                    option.value = cfg_val

    # -- exit -----------------------------------------------------------------

    def _exit_tournament(self) -> None:
        """Disable tournament mode and transition out."""
        self.app.config.save_user_config({"tournament.enabled": False})
        self.app.tournament_transition_target = "leave"
        self.app.screen_manager.switch_to("tournament_transition")
