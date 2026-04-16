"""Main menu screen for selecting a game mode.

Displays a scrollable list of discovered game modes and provides
shortcuts to the status and update screens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen, translate_digit_to_nav
from src.ui.lcd_helpers import (
    CHAR_BATTERY_FULL,
    CHAR_BATTERY_LOW,
    CHAR_CURSOR,
    CHAR_SCROLL_DOWN,
    CHAR_SCROLL_UP,
    CHAR_WIFI_ON,
    pad_text,
)
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Maximum number of mode entries visible at once (lines 0-2).
_VISIBLE_ROWS: int = 3

# Label for the exit entry appended after all game modes.
_EXIT_LABEL: str = "EXIT"


class MenuScreen(BaseScreen):
    """Scrollable game-mode selection menu.

    Lines 0-2 show up to three game modes with a cursor indicating the
    currently highlighted entry.  Line 3 is a fixed status bar displaying
    shortcut hints and an optional WiFi icon.

    Navigation (numpad digits are translated to directions):
        8 / up   — move cursor up
        2 / down — move cursor down
        enter    — select the highlighted mode
        *        — open the status screen
        /        — open the update screen
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._cursor_index: int = 0
        self._scroll_offset: int = 0
        self._confirm_exit: bool = False

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Reset cursor position when entering the menu."""
        self._cursor_index = 0
        self._scroll_offset = 0
        self._confirm_exit = False
        logger.info("Menu screen entered with %d modes", len(self.app.modes))

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Draw the mode list and the fixed status bar.

        If ``_confirm_exit`` is True, renders a confirmation prompt instead.

        Args:
            display: The display HAL instance to render on.
        """
        if self._confirm_exit:
            display.write_line(0, pad_text("!! Stop service? !!"))
            display.write_line(1, pad_text("Press ENTER to"))
            display.write_line(2, pad_text("confirm"))
            display.write_line(3, pad_text("or any key to abort"))
            return

        modes = self.app.modes
        # Total items = game modes + EXIT entry.
        total_items = len(modes) + 1

        # Ensure scroll window contains the cursor.
        self._adjust_scroll(total_items)

        # Scroll indicator flags: show ▲ on row 0 when entries exist above,
        # show ▼ on row 2 when entries exist below the visible window.
        has_above = self._scroll_offset > 0
        has_below = (self._scroll_offset + _VISIBLE_ROWS) < total_items

        # Lines 0-2: mode entries and EXIT
        for row in range(_VISIBLE_ROWS):
            item_idx = self._scroll_offset + row
            if item_idx < len(modes):
                mode = modes[item_idx]
                cursor = chr(CHAR_CURSOR) if item_idx == self._cursor_index else " "
                label = f"{cursor} {mode.name}"
            elif item_idx == len(modes):
                cursor = chr(CHAR_CURSOR) if item_idx == self._cursor_index else " "
                label = f"{cursor} {_EXIT_LABEL}"
            else:
                label = ""

            # Append scroll indicator on the first/last visible row if needed.
            # Reserve 1 character on the right so the indicator never overwrites text.
            if row == 0 and has_above:
                display.write_line(row, pad_text(label, width=19) + chr(CHAR_SCROLL_UP))
            elif row == _VISIBLE_ROWS - 1 and has_below:
                display.write_line(row, pad_text(label, width=19) + chr(CHAR_SCROLL_DOWN))
            else:
                display.write_line(row, pad_text(label))

        # Line 3: fixed status bar with optional battery icon
        wifi_icon = chr(CHAR_WIFI_ON)
        battery_level = self.app.battery.get_battery_level()
        if battery_level is not None:
            bat_icon = chr(CHAR_BATTERY_FULL if battery_level > 20 else CHAR_BATTERY_LOW)
            status_bar = f"* Status  / Upd {bat_icon}{wifi_icon}"
        else:
            status_bar = f"* Status  / Upd  {wifi_icon}"
        display.write_line(3, pad_text(status_bar))

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Process navigation and selection keys.

        Numpad digits are translated to directions (8→up, 2→down)
        so that the physical arrow labels on the numpad work for
        menu navigation.

        Args:
            key: The pressed key string.
        """
        if self._confirm_exit:
            if key == "enter":
                self._do_exit()
            else:
                logger.debug("Exit cancelled by user")
                self._confirm_exit = False
            return

        key = translate_digit_to_nav(key)

        if key == "up":
            self._move_cursor(-1)
        elif key == "down":
            self._move_cursor(1)
        elif key == "enter":
            modes = self.app.modes
            if self._cursor_index == len(modes):
                logger.info("Exit selected — showing confirmation")
                self._confirm_exit = True
            else:
                self._select_mode(self._cursor_index)
        elif key == "asterisk":
            logger.debug("Shortcut: opening status screen")
            self.app.screen_manager.switch_to("status")
        elif key == "slash":
            logger.debug("Shortcut: opening update screen")
            self.app.screen_manager.switch_to("update")

    # -- helpers --------------------------------------------------------------

    def _move_cursor(self, delta: int) -> None:
        """Move the cursor by *delta* positions, clamped to valid range.

        Args:
            delta: Number of positions to move (negative = up).
        """
        # Total items includes game modes plus the EXIT entry.
        total = len(self.app.modes) + 1
        if total == 0:
            return
        self._cursor_index = max(0, min(total - 1, self._cursor_index + delta))
        self._adjust_scroll(total)

    def _adjust_scroll(self, total_items: Optional[int] = None) -> None:
        """Ensure the scroll window keeps the cursor visible.

        Args:
            total_items: Total number of items including EXIT. Computed if not provided.
        """
        if total_items is None:
            total_items = len(self.app.modes) + 1
        if self._cursor_index < self._scroll_offset:
            self._scroll_offset = self._cursor_index
        elif self._cursor_index >= self._scroll_offset + _VISIBLE_ROWS:
            self._scroll_offset = self._cursor_index - _VISIBLE_ROWS + 1

    def _do_exit(self) -> None:
        """Display a restart hint and shut down the application.

        Writes the hint directly to the display before calling shutdown so
        the message remains visible after the main loop exits.
        """
        service_name = self.app.config.get("system", "service_name", default="airsoft-prop")
        logger.info("User requested service exit via menu")
        self.app.display.write_lines([
            "Service stopped.",
            "To restart:",
            "systemctl start",
            service_name,
        ])
        self.app.shutdown()

    def _select_mode(self, index: int) -> None:
        """Select a game mode by index and switch to the setup screen.

        Args:
            index: Index into ``app.modes``.
        """
        modes = self.app.modes
        if not modes or index < 0 or index >= len(modes):
            logger.warning("Invalid mode index: %d", index)
            return

        selected = modes[index]
        self.app.selected_mode = selected  # type: ignore[attr-defined]
        logger.info("Selected mode: %s", selected.name)
        self.app.screen_manager.switch_to("setup")
