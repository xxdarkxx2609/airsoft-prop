"""Pygame-based mock display for desktop testing.

Renders the 20x4 LCD as a graphical pygame window that closely resembles
the appearance of a real HD44780 character LCD: dark green background,
bright green pixel-style characters, and proper rendering of custom
characters (WiFi icon, cursor, scroll indicators, lock).

Each LCD character cell is rendered as a 5x8 pixel grid scaled up by
CELL_SCALE. Custom characters registered via ``create_custom_char()``
are rendered as pixel bitmaps; standard ASCII characters use a monospace
font rendered into an off-screen surface and sampled to the pixel grid.

Keyboard events from the pygame window are collected during ``flush()``
and placed into an external ``queue.Queue`` shared with ``MockInput``.
Closing the window signals shutdown via a provided callback.
"""

import queue
import sys
from typing import Callable, Optional

from src.hal.base import DisplayBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Pixel grid per character cell on the real HD44780 (5 columns, 8 rows).
CHAR_PIXEL_COLS: int = 5
CHAR_PIXEL_ROWS: int = 8

# Scale factor: each LCD pixel becomes a CELL_SCALE × CELL_SCALE square.
CELL_SCALE: int = 3

# Gap (in screen pixels) between adjacent character cells.
CELL_GAP: int = 1

# Width / height of one character cell in screen pixels.
CELL_W: int = CHAR_PIXEL_COLS * CELL_SCALE + CELL_GAP
CELL_H: int = CHAR_PIXEL_ROWS * CELL_SCALE + CELL_GAP

# Padding around the LCD area inside the window (in screen pixels).
PADDING: int = 24

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

COLOR_BG_WINDOW = (15, 15, 25)       # Window background (dark blue-black)
COLOR_BG_DISPLAY = (0, 17, 0)        # LCD panel background (very dark green)
COLOR_BG_DISPLAY_DIM = (0, 5, 0)     # LCD panel when backlight is off
COLOR_PIXEL_ON = (51, 255, 51)       # Lit LCD pixel
COLOR_PIXEL_OFF = (0, 34, 0)         # Unlit LCD pixel (visible dot matrix)
COLOR_PIXEL_ON_DIM = (10, 35, 10)    # Lit pixel when backlight is off
COLOR_PIXEL_OFF_DIM = (0, 8, 0)      # Unlit pixel when backlight is off
COLOR_BEZEL = (30, 30, 45)           # LCD bezel / frame border

# ---------------------------------------------------------------------------
# Key mapping: pygame key codes → app key strings
# ---------------------------------------------------------------------------

try:
    import pygame  # type: ignore[import-untyped]
    _K = pygame.locals if hasattr(pygame, "locals") else pygame
    _KEYMAP: dict[int, str] = {}  # filled in _build_keymap() after pygame.init()
    _HAS_PYGAME = True
except ImportError:
    _HAS_PYGAME = False
    pygame = None  # type: ignore[assignment]


def _build_keymap() -> dict[int, str]:
    """Build the pygame-keycode → app-key-string mapping after pygame.init()."""
    if not _HAS_PYGAME or pygame is None:
        return {}
    return {
        pygame.K_RETURN: "enter",
        pygame.K_KP_ENTER: "enter",
        pygame.K_BACKSPACE: "backspace",
        pygame.K_DELETE: "backspace",
        pygame.K_UP: "up",
        pygame.K_DOWN: "down",
        pygame.K_LEFT: "left",
        pygame.K_RIGHT: "right",
        pygame.K_KP8: "up",
        pygame.K_KP2: "down",
        pygame.K_KP4: "left",
        pygame.K_KP6: "right",
        pygame.K_PLUS: "plus",
        pygame.K_KP_PLUS: "plus",
        pygame.K_MINUS: "minus",
        pygame.K_KP_MINUS: "minus",
        pygame.K_PERIOD: "dot",
        pygame.K_KP_PERIOD: "dot",
        pygame.K_ASTERISK: "asterisk",
        pygame.K_KP_MULTIPLY: "asterisk",
        pygame.K_SLASH: "slash",
        pygame.K_KP_DIVIDE: "slash",
        pygame.K_0: "0",  pygame.K_KP0: "0",
        pygame.K_1: "1",  pygame.K_KP1: "1",
        pygame.K_2: "2",  pygame.K_KP2: "2",
        pygame.K_3: "3",  pygame.K_KP3: "3",
        pygame.K_4: "4",  pygame.K_KP4: "4",
        pygame.K_5: "5",  pygame.K_KP5: "5",
        pygame.K_6: "6",  pygame.K_KP6: "6",
        pygame.K_7: "7",  pygame.K_KP7: "7",
        pygame.K_8: "8",  pygame.K_KP8: "8",
        pygame.K_9: "9",  pygame.K_KP9: "9",
    }


class PygameDisplay(DisplayBase):
    """Pygame-based mock of the 20x4 HD44780 LCD display.

    Opens a dedicated window that renders the display buffer as a pixel-art
    LCD. Custom characters are shown as their actual 5x8 bitmaps. Standard
    ASCII characters are rendered via a small bitmap font approximation.

    Args:
        key_queue: Shared queue for keyboard events. Keys pressed in the
            pygame window are placed here so ``MockInput`` can consume them.
        on_quit: Callback invoked when the user closes the pygame window.
            Typically calls ``app.shutdown()``.
    """

    def __init__(
        self,
        key_queue: Optional["queue.Queue[str]"] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Initialize the display state (window not yet created)."""
        self._buffer: list[list[str]] = [
            [" "] * self.COLS for _ in range(self.ROWS)
        ]
        self._prev_snapshot: str = ""
        self._backlight: bool = True
        self._custom_chars: dict[int, list[int]] = {}

        self._key_queue: "queue.Queue[str]" = key_queue or queue.Queue()
        self._on_quit: Optional[Callable[[], None]] = on_quit

        self._screen: Optional[object] = None  # pygame.Surface
        self._font: Optional[object] = None    # pygame.font.Font (lazy)
        self._keymap: dict[int, str] = {}
        self._display_rect: Optional[tuple[int, int, int, int]] = None
        self._initialized: bool = False

    # ------------------------------------------------------------------
    # DisplayBase interface
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Initialize pygame and open the LCD window."""
        if not _HAS_PYGAME:
            logger.error(
                "pygame-ce not available — PygameDisplay cannot initialize. "
                "Install pygame-ce or use MockDisplay instead."
            )
            return

        try:
            # pygame.mixer may already be initialized by MockAudio — that's fine.
            if not pygame.get_init():
                pygame.init()
            else:
                # Only init the display subsystem if pygame is already running.
                pygame.display.init()
                pygame.font.init()

            self._keymap = _build_keymap()
            self._create_window()
            self._initialized = True
            logger.info("PygameDisplay initialized (%dx%d)", self.COLS, self.ROWS)
        except Exception:
            logger.error("PygameDisplay init failed", exc_info=True)

    def clear(self) -> None:
        """Clear the display buffer."""
        self._buffer = [[" "] * self.COLS for _ in range(self.ROWS)]

    def write_line(self, row: int, text: str) -> None:
        """Write text to a full row.

        Args:
            row: Row index (0-3).
            text: Text to display on the row.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("PygameDisplay.write_line: row %d out of range", row)
            return
        padded = text.ljust(self.COLS)[:self.COLS]
        self._buffer[row] = list(padded)

    def write_at(self, row: int, col: int, text: str) -> None:
        """Write text at a specific position.

        Args:
            row: Row index (0-3).
            col: Column index (0-19).
            text: Text starting at the given position.
        """
        if not 0 <= row < self.ROWS:
            logger.warning("PygameDisplay.write_at: row %d out of range", row)
            return
        if not 0 <= col < self.COLS:
            logger.warning("PygameDisplay.write_at: col %d out of range", col)
            return
        for i, ch in enumerate(text):
            if col + i >= self.COLS:
                break
            self._buffer[row][col + i] = ch

    def set_backlight(self, on: bool) -> None:
        """Toggle the backlight state.

        Args:
            on: True to enable, False to disable.
        """
        self._backlight = on
        self._prev_snapshot = ""  # force full redraw with new colours
        logger.debug("PygameDisplay backlight: %s", "ON" if on else "OFF")

    def create_custom_char(self, slot: int, pattern: list[int]) -> None:
        """Store a custom character pixel pattern.

        Args:
            slot: Character slot index (0-7).
            pattern: List of 8 ints defining the 5x8 pixel pattern.
        """
        if not 0 <= slot <= 7:
            logger.warning(
                "PygameDisplay.create_custom_char: slot %d out of range", slot
            )
            return
        self._custom_chars[slot] = pattern

    def write_screen(self, lines: list[str]) -> None:
        """Write up to 4 lines and flush once.

        Args:
            lines: List of strings (max 4).
        """
        self.clear()
        for i, line in enumerate(lines[: self.ROWS]):
            padded = line.ljust(self.COLS)[: self.COLS]
            self._buffer[i] = list(padded)
        self.flush()

    def shutdown(self, clear_display: bool = True) -> None:
        """Close the pygame window and clean up.

        Args:
            clear_display: If True (default), clear display and quit pygame.
                If False, preserve display content (pygame still quits).
        """
        if self._initialized and _HAS_PYGAME:
            try:
                pygame.display.quit()
            except Exception:
                pass
        logger.info("PygameDisplay shut down")

    def flush(self) -> None:
        """Poll pygame events and redraw the display if the buffer changed."""
        if not self._initialized or not _HAS_PYGAME:
            return

        self._poll_events()

        snapshot = self._snapshot()
        if snapshot == self._prev_snapshot:
            return
        self._prev_snapshot = snapshot
        self._render()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_window(self) -> None:
        """Create the pygame window sized to fit the LCD."""
        lcd_w = self.COLS * CELL_W - CELL_GAP
        lcd_h = self.ROWS * CELL_H - CELL_GAP
        win_w = lcd_w + 2 * PADDING
        win_h = lcd_h + 2 * PADDING

        self._display_rect = (PADDING, PADDING, lcd_w, lcd_h)
        self._screen = pygame.display.set_mode((win_w, win_h))
        pygame.display.set_caption("Airsoft Prop — LCD Mock")
        # Render an initial blank frame.
        self._render()

    def _snapshot(self) -> str:
        """Return a hashable snapshot of the current buffer + backlight state."""
        state = "1" if self._backlight else "0"
        return state + "".join("".join(row) for row in self._buffer)

    def _render(self) -> None:
        """Redraw the entire LCD surface."""
        if self._screen is None or self._display_rect is None:
            return

        screen: pygame.Surface = self._screen  # type: ignore[assignment]
        px, py, lcd_w, lcd_h = self._display_rect

        bg_display = COLOR_BG_DISPLAY if self._backlight else COLOR_BG_DISPLAY_DIM

        # Window background + bezel frame
        screen.fill(COLOR_BG_WINDOW)
        bezel_rect = (px - 6, py - 6, lcd_w + 12, lcd_h + 12)
        pygame.draw.rect(screen, COLOR_BEZEL, bezel_rect, border_radius=4)
        pygame.draw.rect(screen, bg_display, (px, py, lcd_w, lcd_h))

        # Draw each character cell
        for row in range(self.ROWS):
            for col in range(self.COLS):
                ch = self._buffer[row][col]
                cell_x = px + col * CELL_W
                cell_y = py + row * CELL_H
                self._draw_char(screen, ch, cell_x, cell_y)

        pygame.display.flip()

    def _get_font(self) -> "pygame.font.Font":
        """Return the cached monospace font used for ASCII character rendering.

        Iterates through candidate sizes to find the largest that fits
        within the cell height (``CHAR_PIXEL_ROWS * CELL_SCALE``).
        """
        if self._font is not None:
            return self._font  # type: ignore[return-value]

        cell_h = CHAR_PIXEL_ROWS * CELL_SCALE
        font_names = ("Courier New", "Courier", "Lucida Console", "Consolas")

        # Binary-search for the largest size where the rendered 'M' fits.
        best_font = None
        lo, hi = 6, cell_h
        while lo <= hi:
            mid = (lo + hi) // 2
            f = None
            for name in font_names:
                try:
                    f = pygame.font.SysFont(name, mid, bold=False)
                    break
                except Exception:
                    continue
            if f is None:
                f = pygame.font.Font(None, mid)
            _, gh = f.render("M", True, (255, 255, 255)).get_size()
            if gh <= cell_h:
                best_font = f
                lo = mid + 1
            else:
                hi = mid - 1

        self._font = best_font or pygame.font.Font(None, cell_h - 4)
        return self._font  # type: ignore[return-value]

    def _draw_char(
        self, screen: "pygame.Surface", ch: str, x: int, y: int
    ) -> None:
        """Draw a single character cell at pixel position (x, y).

        Custom characters (``ord(ch) < 8``) are drawn as 5x8 pixel bitmaps
        to accurately reproduce the HD44780 icon appearance.
        All other printable ASCII characters are rendered directly with a
        monospace font — no downsampling, fully readable.

        Args:
            screen: Target pygame surface.
            ch: The character to render.
            x: Top-left x position in screen pixels.
            y: Top-left y position in screen pixels.
        """
        code = ord(ch)
        pixel_on = COLOR_PIXEL_ON if self._backlight else COLOR_PIXEL_ON_DIM
        pixel_off = COLOR_PIXEL_OFF if self._backlight else COLOR_PIXEL_OFF_DIM

        if code < 8:
            # Custom character: render as 5×8 pixel bitmap.
            pattern = self._custom_chars.get(code)
            if pattern is None:
                self._draw_blank_cell(screen, x, y, pixel_off)
                return
            self._draw_bitmap(screen, pattern, x, y, pixel_on, pixel_off)
        elif ch == " ":
            self._draw_blank_cell(screen, x, y, pixel_off)
        else:
            # ASCII character: render with font, centered in the cell.
            self._draw_ascii_char(screen, ch, x, y, pixel_on, pixel_off)

    def _draw_blank_cell(
        self,
        screen: "pygame.Surface",
        x: int,
        y: int,
        pixel_off: tuple[int, int, int],
    ) -> None:
        """Draw an empty cell showing only the dot-matrix background grid."""
        for pr in range(CHAR_PIXEL_ROWS):
            for pc in range(CHAR_PIXEL_COLS):
                rx = x + pc * CELL_SCALE
                ry = y + pr * CELL_SCALE
                pygame.draw.rect(screen, pixel_off, (rx, ry, CELL_SCALE - 1, CELL_SCALE - 1))

    def _draw_bitmap(
        self,
        screen: "pygame.Surface",
        pattern: list[int],
        x: int,
        y: int,
        pixel_on: tuple[int, int, int],
        pixel_off: tuple[int, int, int],
    ) -> None:
        """Draw a 5x8 bitmap pattern as scaled pixels.

        Args:
            screen: Target surface.
            pattern: List of 8 ints; bit 4 = leftmost pixel, bit 0 = rightmost.
            x: Top-left x in screen pixels.
            y: Top-left y in screen pixels.
            pixel_on: Colour for set pixels.
            pixel_off: Colour for unset pixels.
        """
        for pr in range(CHAR_PIXEL_ROWS):
            row_bits = pattern[pr] if pr < len(pattern) else 0
            for pc in range(CHAR_PIXEL_COLS):
                bit = (row_bits >> (CHAR_PIXEL_COLS - 1 - pc)) & 1
                color = pixel_on if bit else pixel_off
                rx = x + pc * CELL_SCALE
                ry = y + pr * CELL_SCALE
                pygame.draw.rect(screen, color, (rx, ry, CELL_SCALE - 1, CELL_SCALE - 1))

    def _draw_ascii_char(
        self,
        screen: "pygame.Surface",
        ch: str,
        x: int,
        y: int,
        pixel_on: tuple[int, int, int],
        pixel_off: tuple[int, int, int],
    ) -> None:
        """Render an ASCII character directly using the monospace font.

        The glyph is drawn in ``pixel_on`` colour and centered within
        the character cell. The cell background shows the dot-matrix grid
        using ``pixel_off``.

        Args:
            screen: Target surface.
            ch: Character to render.
            x: Top-left x of cell in screen pixels.
            y: Top-left y of cell in screen pixels.
            pixel_on: Foreground colour.
            pixel_off: Background / dot-matrix colour.
        """
        cell_w = CHAR_PIXEL_COLS * CELL_SCALE
        cell_h = CHAR_PIXEL_ROWS * CELL_SCALE

        # Draw dot-matrix background for this cell.
        for pr in range(CHAR_PIXEL_ROWS):
            for pc in range(CHAR_PIXEL_COLS):
                rx = x + pc * CELL_SCALE
                ry = y + pr * CELL_SCALE
                pygame.draw.rect(screen, pixel_off, (rx, ry, CELL_SCALE - 1, CELL_SCALE - 1))

        font = self._get_font()
        glyph: pygame.Surface = font.render(ch, True, pixel_on)
        gw, gh = glyph.get_size()

        # Centre the glyph within the cell.
        off_x = max(0, (cell_w - gw) // 2)
        off_y = max(0, (cell_h - gh) // 2)
        screen.blit(glyph, (x + off_x, y + off_y))

    def _poll_events(self) -> None:
        """Process pygame events: quit signals and key presses."""
        if not _HAS_PYGAME:
            return
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                logger.info("PygameDisplay: window closed — requesting shutdown")
                if self._on_quit is not None:
                    try:
                        self._on_quit()
                    except Exception:
                        logger.warning("PygameDisplay on_quit callback raised", exc_info=True)
            elif event.type == pygame.KEYDOWN:
                key = self._keymap.get(event.key)
                if key is not None:
                    self._key_queue.put(key)
                    logger.debug("PygameDisplay key: %s", key)
