"""Mock display implementation for desktop testing.

Renders the 20x4 LCD content as a bordered ASCII frame in the terminal.
Uses ANSI escape codes to overwrite the display in-place rather than
scrolling. Only redraws when the buffer has actually changed.
"""

import os
import sys

from src.hal.base import DisplayBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Number of terminal lines the display frame occupies (border + 4 rows + border).
_FRAME_HEIGHT = 6


class MockDisplay(DisplayBase):
    """Terminal-based mock of the 20x4 HD44780 LCD display.

    Maintains an internal 20x4 character buffer. Renders using ANSI
    escape codes so the display updates in-place instead of scrolling.
    Only redraws when the buffer content has changed.
    """

    def __init__(self) -> None:
        """Initialize the internal display buffer."""
        self._buffer: list[list[str]] = [
            [" "] * self.COLS for _ in range(self.ROWS)
        ]
        self._prev_snapshot: str = ""
        self._backlight: bool = True
        self._custom_chars: dict[int, list[int]] = {}
        self._first_render: bool = True

    def init(self) -> None:
        """Initialize the mock display."""
        logger.info("MockDisplay initialized (%dx%d)", self.COLS, self.ROWS)
        self._first_render = True
        self.clear()

    def clear(self) -> None:
        """Clear the display buffer."""
        self._buffer = [
            [" "] * self.COLS for _ in range(self.ROWS)
        ]

    def write_line(self, row: int, text: str) -> None:
        """Write text to a full row, padded/truncated to 20 characters.

        Does NOT immediately render — the display is rendered once per
        frame by the ``flush()`` method (called from ``write_screen()``
        or explicitly).

        Args:
            row: Row index (0-3).
            text: Text to display on the row.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("MockDisplay.write_line: row %d out of range", row)
            return

        padded = text.ljust(self.COLS)[:self.COLS]
        self._buffer[row] = list(padded)

    def write_at(self, row: int, col: int, text: str) -> None:
        """Write text at a specific row/column position.

        Args:
            row: Row index (0-3).
            col: Column index (0-19).
            text: Text to write starting at the given position.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("MockDisplay.write_at: row %d out of range", row)
            return
        if not 0 <= col < self.COLS:
            logger.warning("MockDisplay.write_at: col %d out of range", col)
            return

        for i, char in enumerate(text):
            target_col = col + i
            if target_col >= self.COLS:
                break
            self._buffer[row][target_col] = char

    def set_backlight(self, on: bool) -> None:
        """Toggle the simulated backlight state.

        Args:
            on: True to enable, False to disable.
        """
        self._backlight = on
        logger.debug("MockDisplay backlight: %s", "ON" if on else "OFF")

    def create_custom_char(self, slot: int, pattern: list[int]) -> None:
        """Store a custom character pattern.

        Args:
            slot: Character slot index (0-7).
            pattern: List of 8 ints defining the 5x8 pixel pattern.
        """
        if not 0 <= slot <= 7:
            logger.warning(
                "MockDisplay.create_custom_char: slot %d out of range", slot
            )
            return
        self._custom_chars[slot] = pattern

    def shutdown(self, clear_display: bool = True) -> None:
        """Clean up the mock display.

        Args:
            clear_display: If True (default), clear display and turn off backlight.
                If False, preserve display content.
        """
        if clear_display:
            self.clear()
            self.flush()
            self.set_backlight(False)
            # Move cursor below the display frame so the shell prompt is clean.
            sys.stdout.write("\n")
            sys.stdout.flush()
        logger.info("MockDisplay shut down")

    def write_screen(self, lines: list[str]) -> None:
        """Write up to 4 lines and flush once.

        Overrides the base implementation to avoid per-line rendering.

        Args:
            lines: List of strings (max 4).
        """
        self.clear()
        for i, line in enumerate(lines[:self.ROWS]):
            padded = line.ljust(self.COLS)[:self.COLS]
            self._buffer[i] = list(padded)
        self.flush()

    def flush(self) -> None:
        """Render the current buffer to the terminal if it has changed.

        Uses ANSI escape codes to move the cursor up and overwrite the
        previous frame in-place, giving the appearance of a real
        updating display.
        """
        snapshot = self._build_frame()
        if snapshot == self._prev_snapshot:
            return  # Nothing changed — skip redraw
        self._prev_snapshot = snapshot

        if not self._first_render:
            # Move cursor up to overwrite previous frame
            sys.stdout.write(f"\033[{_FRAME_HEIGHT}A")
        else:
            self._first_render = False

        sys.stdout.write(snapshot)
        sys.stdout.flush()

    def _build_frame(self) -> str:
        """Build the ASCII frame string from the current buffer.

        Returns:
            Multi-line string representing the bordered display.
        """
        border = "+" + "-" * self.COLS + "+"
        lines = [border]
        for row in self._buffer:
            lines.append("|" + "".join(row) + "|")
        lines.append(border)
        # Use \r\n to ensure correct behavior on Windows terminals
        return "\r\n".join(lines) + "\r\n"
