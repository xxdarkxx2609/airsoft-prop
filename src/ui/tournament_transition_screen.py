"""Tournament transition screen — timed message during mode switch.

Shows 'Switching to Tournament Mode' or 'Leaving Tournament Mode' for
3 seconds, then auto-transitions to the target screen.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

_TRANSITION_DURATION: float = 3.0


class TournamentTransitionScreen(BaseScreen):
    """Timed screen shown when entering or leaving tournament mode."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._start_time: float = 0.0
        self._transitioned: bool = False

    def on_enter(self) -> None:
        """Record the transition start time."""
        self._start_time = time.time()
        self._transitioned = False
        direction = self.app.tournament_transition_target
        logger.info("Tournament transition screen entered (direction=%s)", direction)

    def render(self, display: DisplayBase) -> None:
        """Render the transition message and auto-switch after 3 seconds."""
        direction = self.app.tournament_transition_target

        if direction == "enter":
            line1 = "Switching to"
        else:
            line1 = "Leaving"

        display.write_line(0, center_text(""))
        display.write_line(1, center_text(line1))
        display.write_line(2, center_text("Tournament Mode"))
        display.write_line(3, center_text(""))

        elapsed = time.time() - self._start_time
        if elapsed >= _TRANSITION_DURATION and not self._transitioned:
            self._transitioned = True
            if direction == "enter":
                self.app.screen_manager.switch_to("tournament")
            else:
                self.app.screen_manager.switch_to("menu")

    def handle_input(self, key: str) -> None:
        """Ignore all input during the transition."""
