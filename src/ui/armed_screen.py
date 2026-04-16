"""Armed screen -- the main gameplay screen with countdown timer.

Manages the countdown, beep intervals, blinking effects, and
delegates rendering and input handling to the active game mode.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.modes.base_mode import ModeResult
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import blink_text, center_text, format_timer
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Beep interval thresholds (seconds remaining -> interval in seconds).
# The beep sound is ~400ms (100ms USB padding + 300ms tone), so
# intervals must stay at or above 500ms to avoid overlap.
_BEEP_INTERVAL_NORMAL: float = 5.0
_BEEP_INTERVAL_30S: float = 2.0
_BEEP_INTERVAL_10S: float = 0.8
_BEEP_INTERVAL_5S: float = 0.5

# Blink toggle interval for visual effects (seconds).
_BLINK_INTERVAL: float = 0.5


class ArmedScreen(BaseScreen):
    """Main gameplay screen that runs while the device is armed.

    Handles the one-second countdown tick, delegates rendering to the
    active game mode, plays beep sounds at configurable intervals, and
    transitions to the result screen when the game ends (defused or
    detonated).
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.last_tick_time: float = 0.0
        self.last_beep_time: float = 0.0
        self.blink_state: bool = True
        self.blink_time: float = 0.0

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Start the armed phase: play the planted sound and init timers."""
        now = time.monotonic()
        self.last_tick_time = now
        self.last_beep_time = now
        self.blink_state = True
        self.blink_time = now

        self.app.audio.play("planted")
        logger.info(
            "Device armed! Timer: %ds",
            self.app.game_context.remaining_seconds
            if self.app.game_context
            else 0,
        )

    def on_exit(self) -> None:
        """Stop all audio when leaving the armed screen."""
        self.app.audio.stop()
        logger.debug("Armed screen exited, audio stopped")

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Update timing logic and render the armed screen.

        This method drives the countdown, beep scheduling, and blink
        toggling, then delegates actual display rendering to the active
        game mode.

        Args:
            display: The display HAL instance to render on.
        """
        context = self.app.game_context
        mode = self.app.selected_mode
        if context is None or mode is None:
            logger.error("Armed screen rendered without context or mode")
            return

        now = time.monotonic()

        # --- 1-second countdown tick ---
        elapsed_since_tick = now - self.last_tick_time
        if elapsed_since_tick >= 1.0:
            ticks = int(elapsed_since_tick)
            self.last_tick_time += ticks

            for _ in range(ticks):
                context.remaining_seconds -= 1

                if context.remaining_seconds <= 0:
                    context.remaining_seconds = 0
                    self._end_game(ModeResult.DETONATED)
                    return

                result = mode.on_tick(context.remaining_seconds, context)
                if result in (ModeResult.DEFUSED, ModeResult.DETONATED):
                    self._end_game(result)
                    return

        remaining = context.remaining_seconds

        # --- Beep logic ---
        beep_interval = self._get_beep_interval(remaining)
        if now - self.last_beep_time >= beep_interval:
            self.app.audio.play("beep")
            self.app.led.blink_once()
            self.last_beep_time = now

        # --- Blink logic ---
        if now - self.blink_time >= _BLINK_INTERVAL:
            self.blink_state = not self.blink_state
            self.blink_time = now

        # --- Rendering ---
        if remaining > 10:
            mode.render(display, remaining, context)
        else:
            # Last 10 seconds: blinking timer header on line 0
            header = f"!! {format_timer(remaining)} !! ARMED !!"
            display.write_line(
                0, center_text(blink_text(header, self.blink_state))
            )
            mode.render_last_10s(display, remaining, context)

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Forward input to the active game mode and check the result.

        Args:
            key: The key string from the input HAL.
        """
        context = self.app.game_context
        mode = self.app.selected_mode
        if context is None or mode is None:
            return

        result = mode.on_input(key, context)

        # Check if the mode signalled a penalty (used by Plus modes)
        if context.custom_data.pop("penalty_triggered", False):
            self.app.audio.play("wrong")

        if result in (ModeResult.DEFUSED, ModeResult.DETONATED):
            self._end_game(result)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _get_beep_interval(remaining: int) -> float:
        """Determine the beep interval based on remaining seconds.

        Args:
            remaining: Seconds left on the timer.

        Returns:
            Interval in seconds between beep sounds.
        """
        if remaining <= 5:
            return _BEEP_INTERVAL_5S
        if remaining <= 10:
            return _BEEP_INTERVAL_10S
        if remaining <= 30:
            return _BEEP_INTERVAL_30S
        return _BEEP_INTERVAL_NORMAL

    def _end_game(self, result: ModeResult) -> None:
        """Store the game result and transition to the result screen.

        Args:
            result: DEFUSED or DETONATED.
        """
        self.app.game_result = result
        logger.info("Game ended: %s", result.value)
        self.app.screen_manager.switch_to("result")
