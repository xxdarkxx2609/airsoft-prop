"""Result screen -- shows the game outcome (defused or detonated).

Displays a summary after the device has been defused or detonated,
plays the appropriate audio, and waits for the user to return to the
main menu.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.modes.base_mode import ModeResult
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text, format_timer
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Delay before showing "Ent -> Menu" on detonation screen.
_DETONATION_SHOW_MENU_DELAY: float = 3.0


class ResultScreen(BaseScreen):
    """Displays the game result and waits for the user to return to menu."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._enter_time: float = 0.0
        self._siren_played: bool = False

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Play the appropriate result sound."""
        self._enter_time = time.time()
        self._siren_played = False
        result = self.app.game_result

        if result == ModeResult.DEFUSED:
            self.app.audio.play("defused")
            logger.info("Result: DEFUSED")
        elif result == ModeResult.DETONATED:
            self.app.audio.play("explosion")
            logger.info("Result: DETONATED")

    def on_exit(self) -> None:
        """Stop all audio when leaving the result screen."""
        self.app.audio.stop()

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Render the result screen.

        Args:
            display: The display HAL instance.
        """
        result = self.app.game_result
        if result == ModeResult.DEFUSED:
            self._render_defused(display)
        else:
            self._render_detonated(display)

    def _render_defused(self, display: DisplayBase) -> None:
        """Render the defused result.

        Args:
            display: The display HAL instance.
        """
        context = self.app.game_context
        remaining = context.remaining_seconds if context else 0

        display.write_line(0, center_text(""))
        dn = self.app.config.get("game", "device_name", default="Prop").upper()
        display.write_line(1, center_text(f"{dn} DEFUSED!"))
        display.write_line(2, center_text(f"Time left: {format_timer(remaining)}"))
        display.write_line(3, center_text("Ent -> Menu"))

    def _render_detonated(self, display: DisplayBase) -> None:
        """Render the detonated result.

        Shows an explosion frame, then after a delay shows the menu hint.
        Also plays the siren sound after the explosion sound finishes.

        Args:
            display: The display HAL instance.
        """
        elapsed = time.time() - self._enter_time
        frame = "*" * 20

        # Start siren loop after explosion sound (~2s), plays until
        # the user presses Enter and on_exit() calls stop().
        if not self._siren_played and elapsed >= 2.0:
            self.app.audio.play_loop("siren")
            self._siren_played = True

        display.write_line(0, frame)
        dn = self.app.config.get("game", "device_name", default="Prop").upper()
        display.write_line(1, center_text(f"{dn} EXPLODED!"))
        display.write_line(2, center_text("GAME OVER!"))

        if elapsed >= _DETONATION_SHOW_MENU_DELAY:
            display.write_line(3, center_text("Ent -> Menu"))
        else:
            display.write_line(3, frame)

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Handle input on the result screen.

        Args:
            key: The key string from the input HAL.
        """
        if key == "enter":
            if self.app.config.is_tournament_enabled():
                self.app.screen_manager.switch_to("tournament")
            else:
                self.app.screen_manager.switch_to("menu")
