"""Planting screen -- intermediate phase between setup and armed.

Depending on the mode's PlantingConfig, the player must either:
  - Enter a code to plant the device (CODE_ENTRY), or
  - Hold the Enter key for a set duration (TIMED).

INSTANT planting skips this screen entirely.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.modes.base_mode import (
    HOLD_TIMEOUT,
    GameContext,
    PlantingConfig,
    PlantingType,
)
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text, progress_bar
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)


class PlantingScreen(BaseScreen):
    """Screen that handles the planting phase before the device is armed.

    Supports two planting mechanics:
      - CODE_ENTRY: display a code the player must type correctly.
      - TIMED: the player must hold Enter for a configurable duration.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._config: PlantingConfig = PlantingConfig()
        self._code: str = ""
        self._input: str = ""

        # TIMED state
        self._hold_start: float = 0.0
        self._hold_active: bool = False
        self._last_enter_time: float = 0.0
        self._elapsed_held: float = 0.0

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Prepare the planting screen based on the active mode's config."""
        mode = self.app.selected_mode
        context = self.app.game_context
        if mode is None or context is None:
            logger.error("Planting screen entered without mode or context")
            self.app.screen_manager.switch_to("setup")
            return

        self._config = mode.get_planting_config()

        if self._config.planting_type == PlantingType.INSTANT:
            # Skip planting entirely
            self._arm_device()
            return

        if self._config.planting_type == PlantingType.CODE_ENTRY:
            self._setup_code_entry(context)
        elif self._config.planting_type == PlantingType.TIMED:
            self._setup_timed()

        logger.info(
            "Planting phase started: type=%s",
            self._config.planting_type.value,
        )

    def on_exit(self) -> None:
        """Clean up planting state."""
        self._hold_active = False
        self._input = ""

    # -- setup helpers --------------------------------------------------------

    def _setup_code_entry(self, context: GameContext) -> None:
        """Initialise CODE_ENTRY planting state.

        For modes that provide code_length > 0, a separate random
        activation code is generated.  For code_length == 0, the mode's
        game code (already stored in custom_data by on_armed) is reused.
        """
        code_length = self._config.code_length

        if code_length > 0:
            # Generate a separate random activation code
            self._code = "".join(
                str(random.randint(0, 9)) for _ in range(code_length)
            )
        else:
            # Reuse the mode's game code (generated during on_armed)
            self._code = context.custom_data.get("code", "")
            if not self._code:
                logger.warning("No code found in context for planting")
                self._arm_device()
                return

        self._input = ""
        logger.debug(
            "Planting code ready: length=%d", len(self._code)
        )

    def _setup_timed(self) -> None:
        """Initialise TIMED planting state."""
        self._hold_active = False
        self._hold_start = 0.0
        self._last_enter_time = 0.0
        self._elapsed_held = 0.0

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Render the planting screen.

        Args:
            display: The display HAL instance.
        """
        if self._config.planting_type == PlantingType.CODE_ENTRY:
            self._render_code_entry(display)
        elif self._config.planting_type == PlantingType.TIMED:
            self._render_timed(display)

    def _render_code_entry(self, display: DisplayBase) -> None:
        """Render the code-entry planting screen.

        Layout:
            Line 0: PLANTING {device_name}...
            Line 1: Enter code to arm:
            Line 2: The activation code
            Line 3: Player input with underscores
        """
        code = self._code
        entered = self._input
        remaining_slots = len(code) - len(entered)
        input_display = entered + "_" * remaining_slots

        dn = self.app.config.get("game", "device_name", default="Prop").upper()
        display.write_line(0, center_text(f"PLANTING {dn}..."))
        display.write_line(1, center_text("Enter code to arm:"))
        display.write_line(2, center_text(code))
        display.write_line(3, center_text(input_display))

    def _render_timed(self, display: DisplayBase) -> None:
        """Render the timed (hold Enter) planting screen.

        Layout:
            Line 0: PLANTING {device_name}...
            Line 1: (empty)
            Line 2: Progress bar
            Line 3: Hold ENTER  Xs
        """
        duration = self._config.duration
        now = time.time()

        if self._hold_active:
            # Check for key release
            if now - self._last_enter_time > HOLD_TIMEOUT:
                self._cancel_planting()
                return

            # Accumulate elapsed time
            self._elapsed_held = now - self._hold_start
            remaining = max(0, duration - self._elapsed_held)

            if self._elapsed_held >= duration:
                logger.info("Timed planting completed after %ds", duration)
                self._arm_device()
                return
        else:
            remaining = float(duration)
            self._elapsed_held = 0.0

        bar = progress_bar(
            int(self._elapsed_held), duration, width=20
        )
        remaining_int = int(remaining) + (1 if remaining % 1 > 0 else 0)

        dn = self.app.config.get("game", "device_name", default="Prop").upper()
        display.write_line(0, center_text(f"PLANTING {dn}..."))
        display.write_line(1, center_text(""))
        display.write_line(2, bar)

        if self._hold_active:
            display.write_line(3, center_text(f"Hold ENTER   {remaining_int}s"))
        else:
            display.write_line(3, center_text("Hold ENTER to plant"))

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Process key input during planting.

        Args:
            key: The pressed key string.
        """
        if self._config.planting_type == PlantingType.CODE_ENTRY:
            self._handle_code_input(key)
        elif self._config.planting_type == PlantingType.TIMED:
            self._handle_timed_input(key)

    def _handle_code_input(self, key: str) -> None:
        """Handle input for CODE_ENTRY planting.

        Digit keys append to input. Backspace deletes last digit or
        cancels if input is empty.  When all digits are entered,
        auto-checks against the planting code.
        """
        if key == "backspace":
            if self._input:
                self._input = self._input[:-1]
            else:
                self._cancel_planting()
            return

        if key in "0123456789" and len(self._input) < len(self._code):
            self._input += key

            # Auto-check when all digits are entered
            if len(self._input) == len(self._code):
                if self._input == self._code:
                    logger.info("Planting code entered correctly")
                    self._arm_device()
                else:
                    logger.debug("Wrong planting code, clearing input")
                    self._input = ""

    def _handle_timed_input(self, key: str) -> None:
        """Handle input for TIMED planting.

        Enter key starts/sustains the hold timer.  Any other key or
        absence of Enter events (detected in render) cancels planting.
        """
        if key == "enter":
            now = time.time()
            self._last_enter_time = now

            if not self._hold_active:
                self._hold_active = True
                self._hold_start = now
                self._elapsed_held = 0.0
                logger.debug("Timed planting hold started")
        elif key == "backspace":
            self._cancel_planting()
        else:
            # Any non-Enter key cancels the hold
            if self._hold_active:
                self._cancel_planting()

    # -- transitions ----------------------------------------------------------

    def _arm_device(self) -> None:
        """Transition to the armed screen."""
        logger.info("Planting complete, transitioning to armed")
        self.app.screen_manager.switch_to("armed")

    def _cancel_planting(self) -> None:
        """Cancel planting and return to setup or tournament screen."""
        self._hold_active = False
        self._elapsed_held = 0.0
        self._input = ""
        if self.app.config.is_tournament_enabled():
            logger.debug("Planting cancelled, returning to tournament")
            self.app.screen_manager.switch_to("tournament")
        else:
            logger.debug("Planting cancelled, returning to setup")
            self.app.screen_manager.switch_to("setup")
