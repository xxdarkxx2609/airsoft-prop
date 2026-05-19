"""Screen shown when no USB numpad is attached after boot.

The device is unusable without input, so we surface a clear "Connect USB
numpad" message instead of dropping the user on a frozen main menu. The
screen polls ``app.input.is_connected()`` each render and transitions to
the menu (or tournament screen) automatically once a numpad appears —
no service restart needed; the input HAL's reader thread grabs the
device mid-flight via its hot-plug path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)


class NoNumpadScreen(BaseScreen):
    """Waiting screen displayed while no input device is detected.

    Renders a static 20x4 message and polls ``app.input.is_connected()``
    every frame. Transitions to the tournament or menu screen as soon as
    the numpad reader thread reports a successful attach.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._transitioned: bool = False

    def on_enter(self) -> None:
        """Reset the transition guard so the screen can re-trigger."""
        self._transitioned = False
        logger.warning("NoNumpadScreen entered -- waiting for USB numpad")

    def render(self, display: DisplayBase) -> None:
        """Draw the waiting message, or transition once a numpad appears."""
        if not self._transitioned and self.app.input.is_connected():
            self._transition_to_menu()
            return

        display.write_line(0, center_text("NO NUMPAD"))
        display.write_line(1, center_text("Connect USB numpad"))
        display.write_line(2, center_text(""))
        display.write_line(3, center_text("Waiting..."))

    def handle_input(self, key: str) -> None:
        """No-op: the screen exists precisely because no input is expected."""

    def _transition_to_menu(self) -> None:
        """Switch to the tournament or main menu screen exactly once."""
        self._transitioned = True
        if self.app.config.is_tournament_enabled():
            logger.info("Numpad detected, switching to tournament screen")
            self.app.screen_manager.switch_to("tournament")
        else:
            logger.info("Numpad detected, switching to menu")
            self.app.screen_manager.switch_to("menu")
