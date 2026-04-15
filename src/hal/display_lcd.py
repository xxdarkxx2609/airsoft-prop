"""HD44780 20x4 LCD display via I2C (PCF8574 backpack).

Drives an AZDelivery-style 20x4 character LCD connected through a
PCF8574 I2C expander using the RPLCD library.  Configuration (I2C
address, port, dimensions) is read from ``config/hardware.yaml``
under the ``lcd`` section.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from RPLCD.i2c import CharLCD

from src.hal.base import DisplayBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)


class LcdDisplay(DisplayBase):
    """Real HD44780 20x4 LCD display over I2C.

    All I2C operations are individually wrapped in ``try/except`` so
    that a single failed write does not crash the application.  If
    ``init()`` fails to create the LCD instance, all subsequent
    methods become safe no-ops.
    """

    def __init__(self, config: Config) -> None:
        """Prepare configuration without touching I2C yet.

        Args:
            config: Application configuration (reads ``lcd.*``).
        """
        self._config = config
        self._lcd: Optional[CharLCD] = None
        self._backlight: bool = True
        # Dirty-line tracking: buffer holds last-written content per row,
        # dirty flags indicate which rows need an I2C write on flush().
        self._buffer: list[str] = [""] * self.ROWS
        self._dirty: list[bool] = [False] * self.ROWS

    def init(self) -> None:
        """Create the RPLCD CharLCD instance and clear the display."""
        address = int(self._config.get("lcd", "i2c_address", default=0x27))
        port = int(self._config.get("lcd", "i2c_port", default=1))
        cols = int(self._config.get("lcd", "cols", default=20))
        rows = int(self._config.get("lcd", "rows", default=4))

        try:
            self._lcd = CharLCD(
                i2c_expander="PCF8574",
                address=address,
                port=port,
                cols=cols,
                rows=rows,
            )
            self.clear()
            logger.info(
                "LcdDisplay initialized (%dx%d) at I2C 0x%02X on bus %d",
                cols, rows, address, port,
            )
        except (OSError, IOError) as exc:
            logger.warning("LcdDisplay init failed (I2C 0x%02X): %s", address, exc)
            self._lcd = None

    def clear(self) -> None:
        """Clear the entire LCD and reset the line buffer."""
        blank = " " * self.COLS
        self._buffer = [blank] * self.ROWS
        self._dirty = [False] * self.ROWS
        if self._lcd is None:
            return
        try:
            self._lcd.clear()
        except (OSError, IOError) as exc:
            logger.warning("LcdDisplay.clear failed: %s", exc)

    def write_line(self, row: int, text: str) -> None:
        """Buffer text for a full row, padded/truncated to 20 characters.

        The actual I2C write is deferred to :meth:`flush` and only
        happens when the content has changed since the last flush.

        Args:
            row: Row index (0-3).
            text: Text to display on the row.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("LcdDisplay.write_line: row %d out of range", row)
            return

        padded = text.ljust(self.COLS)[:self.COLS]
        if padded != self._buffer[row]:
            self._buffer[row] = padded
            self._dirty[row] = True

    def write_at(self, row: int, col: int, text: str) -> None:
        """Buffer text at a specific row/column position.

        Merges the text into the row buffer and marks the row dirty.
        The actual I2C write is deferred to :meth:`flush`.

        Args:
            row: Row index (0-3).
            col: Column index (0-19).
            text: Text to write starting at the given position.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("LcdDisplay.write_at: row %d out of range", row)
            return
        if not 0 <= col < self.COLS:
            logger.warning("LcdDisplay.write_at: col %d out of range", col)
            return

        truncated = text[:self.COLS - col]
        # Merge into the existing row buffer.
        buf = self._buffer[row]
        if not buf:
            buf = " " * self.COLS
        new_buf = buf[:col] + truncated + buf[col + len(truncated):]
        if new_buf != self._buffer[row]:
            self._buffer[row] = new_buf
            self._dirty[row] = True

    def set_backlight(self, on: bool) -> None:
        """Turn the backlight on or off.

        Args:
            on: True to enable, False to disable.
        """
        self._backlight = on
        if self._lcd is None:
            return
        try:
            self._lcd.backlight_enabled = on
        except (OSError, IOError) as exc:
            logger.warning("LcdDisplay.set_backlight failed: %s", exc)

    def create_custom_char(self, slot: int, pattern: list[int]) -> None:
        """Define a custom character in the given CGRAM slot (0-7).

        Args:
            slot: Character slot index (0-7).
            pattern: List of 8 ints defining the 5x8 pixel pattern.
        """
        if self._lcd is None:
            return
        if not 0 <= slot <= 7:
            logger.warning("LcdDisplay.create_custom_char: slot %d out of range", slot)
            return
        try:
            self._lcd.create_char(slot, tuple(pattern))
        except (OSError, IOError) as exc:
            logger.warning("LcdDisplay.create_custom_char failed (slot %d): %s", slot, exc)

    def flush(self) -> None:
        """Write only the dirty (changed) rows to the LCD via I2C.

        This avoids redundant I2C traffic for rows whose content has
        not changed since the last flush, significantly reducing CPU
        load and improving responsiveness on the Pi Zero.
        """
        if self._lcd is None:
            return
        for row in range(self.ROWS):
            if not self._dirty[row]:
                continue
            try:
                self._lcd.cursor_pos = (row, 0)
                self._lcd.write_string(self._buffer[row])
            except (OSError, IOError) as exc:
                logger.warning("LcdDisplay.flush failed (row %d): %s", row, exc)
            self._dirty[row] = False

    def shutdown(self) -> None:
        """Clear the display, turn off backlight, and close I2C."""
        if self._lcd is not None:
            try:
                self._lcd.clear()
                self._lcd.backlight_enabled = False
                self._lcd.close(clear=True)
            except (OSError, IOError) as exc:
                logger.warning("LcdDisplay.shutdown failed: %s", exc)
            self._lcd = None
        logger.info("LcdDisplay shut down")
