"""Modal info screen — displays a message until the user dismisses it.

Reads ``self.app.pending_info_message`` and ``self.app.pending_info_return``
which the caller sets before ``screen_manager.switch_to("info")``. Pressing
Enter or Backspace returns to the named screen.
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

_TITLE: str = "CANNOT START"
_FOOTER: str = "Press ENTER"


class InfoScreen(BaseScreen):
    """Blocking message screen with a keypress-to-dismiss footer.

    Used to surface mode preconditions (e.g. wires not connected) that
    prevent a game from starting. The message and the return target are
    handed in via ``app.pending_info_message`` / ``app.pending_info_return``
    so the caller doesn't need parameter passing through ``switch_to``.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._message: str = ""
        self._return_screen: str = "menu"

    def on_enter(self) -> None:
        """Snapshot the pending message and clear the app-level fields."""
        self.app.input.flush()
        self._message = getattr(self.app, "pending_info_message", "") or ""
        self._return_screen = (
            getattr(self.app, "pending_info_return", "") or "menu"
        )
        self.app.pending_info_message = ""
        self.app.pending_info_return = ""
        logger.info(
            "InfoScreen entered (return='%s'): %s",
            self._return_screen,
            self._message.replace("\n", " | "),
        )

    def render(self, display: DisplayBase) -> None:
        """Draw the title, up to two body lines, and the dismiss footer."""
        body_lines = self._message.split("\n") if self._message else []

        display.write_line(0, center_text(_TITLE))
        display.write_line(1, center_text(body_lines[0][:20] if body_lines else ""))
        display.write_line(2, center_text(body_lines[1][:20] if len(body_lines) > 1 else ""))
        display.write_line(3, center_text(_FOOTER))

    def handle_input(self, key: str) -> None:
        """Dismiss on Enter or Backspace; ignore everything else."""
        if key in ("enter", "backspace"):
            logger.debug("InfoScreen dismissed via '%s'", key)
            self.app.screen_manager.switch_to(self._return_screen)
