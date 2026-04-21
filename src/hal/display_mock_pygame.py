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

When a ``MockWires`` instance is attached via ``set_wires()``, a wire
control panel is rendered to the right of the LCD. Clicking a wire button
toggles its cut/intact state.
"""

import queue
import sys
from typing import TYPE_CHECKING, Callable, Optional

from src.hal.base import DisplayBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.hal.wires_mock import MockWires

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
# Wire panel constants
# ---------------------------------------------------------------------------

PANEL_W: int = 140                   # Width of the wire control panel
PANEL_GAP: int = 12                  # Gap between LCD area and panel

# Wire colours rendered on the buttons (R, G, B)
_WIRE_BUTTON_COLORS: dict[str, tuple[int, int, int]] = {
    "Green":  (0, 180, 60),
    "Blue":   (30, 100, 220),
    "White":  (200, 200, 200),
    "Yellow": (210, 180, 0),
    "Red":    (200, 40, 40),
}
_WIRE_BTN_H: int = 34                # Button height in screen pixels
_WIRE_BTN_GAP: int = 8              # Vertical gap between buttons

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
        self._panel_font: Optional[object] = None  # pygame.font.Font for wire panel
        self._keymap: dict[int, str] = {}
        self._display_rect: Optional[tuple[int, int, int, int]] = None
        self._initialized: bool = False

        # Hold-repeat state: emit synthetic enter repeats while Enter is held.
        self._enter_held: bool = False
        self._enter_repeat_due: float = 0.0

        # Wire control panel — populated via set_wires()
        self._wires: Optional["MockWires"] = None
        self._wire_btn_rects: list[tuple[str, tuple[int, int, int, int]]] = []
        self._prev_wire_snapshot: str = ""

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

            # Disable pygame's built-in key repeat; we handle Enter repeat manually
            # so it doesn't flood the queue and cause duplicate inputs on other keys.
            pygame.key.set_repeat(0, 0)

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

    def set_wires(self, wires: "MockWires") -> None:
        """Attach a MockWires instance to enable the wire control panel.

        Must be called before ``init()`` so the window is sized correctly.

        Args:
            wires: The MockWires instance to control.
        """
        self._wires = wires

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
        wire_snapshot = self._wire_snapshot()
        if snapshot == self._prev_snapshot and wire_snapshot == self._prev_wire_snapshot:
            return
        self._prev_snapshot = snapshot
        self._prev_wire_snapshot = wire_snapshot
        self._render()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_window(self) -> None:
        """Create the pygame window sized to fit the LCD and optional wire panel."""
        lcd_w = self.COLS * CELL_W - CELL_GAP
        lcd_h = self.ROWS * CELL_H - CELL_GAP

        if self._wires is not None:
            n = len(self._wires.get_wire_states())
            panel_h = 26 + n * (_WIRE_BTN_H + _WIRE_BTN_GAP) - _WIRE_BTN_GAP + 20
            content_h = max(lcd_h, panel_h)
            win_w = lcd_w + PANEL_GAP + PANEL_W + 2 * PADDING
        else:
            content_h = lcd_h
            win_w = lcd_w + 2 * PADDING

        win_h = content_h + 2 * PADDING
        # Vertically centre the LCD within the (potentially taller) window
        lcd_top = PADDING + (content_h - lcd_h) // 2
        self._display_rect = (PADDING, lcd_top, lcd_w, lcd_h)
        self._screen = pygame.display.set_mode((win_w, win_h))
        pygame.display.set_caption("Airsoft Prop — LCD Mock")
        self._render()

    def _snapshot(self) -> str:
        """Return a hashable snapshot of the current buffer + backlight state."""
        state = "1" if self._backlight else "0"
        return state + "".join("".join(row) for row in self._buffer)

    def _wire_snapshot(self) -> str:
        """Return a hashable snapshot of wire states (empty if no wires attached)."""
        if self._wires is None:
            return ""
        return "".join(
            "1" if intact else "0"
            for intact in self._wires.get_wire_states().values()
        )

    def _render(self) -> None:
        """Redraw the entire window (LCD + optional wire panel)."""
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

        if self._wires is not None:
            panel_x = px + lcd_w + PANEL_GAP
            win_h = screen.get_height()
            self._render_wire_panel(screen, panel_x, PADDING, win_h - 2 * PADDING)

        pygame.display.flip()

    def _render_wire_panel(
        self,
        screen: "pygame.Surface",
        x: int,
        y: int,
        panel_h: int,
    ) -> None:
        """Draw the wire control panel.

        Renders one clickable button per wire. Intact wires show their
        colour; cut wires are shown dark with a strikethrough label.

        Args:
            screen: Target pygame surface.
            x: Left edge of the panel in screen pixels.
            y: Top edge of the panel in screen pixels.
            panel_h: Available height (matches LCD height).
        """
        if self._wires is None:
            return

        font = self._get_panel_font()
        wire_states = self._wires.get_wire_states()
        wire_names = list(wire_states.keys())

        # Panel title
        title_surf = font.render("WIRES", True, (160, 160, 180))
        screen.blit(title_surf, (x + (PANEL_W - title_surf.get_width()) // 2, y))
        title_h = title_surf.get_height() + 6

        self._wire_btn_rects = []
        btn_y = y + title_h
        for name in wire_names:
            intact = wire_states[name]
            base_color = _WIRE_BUTTON_COLORS.get(name, (120, 120, 120))
            if intact:
                btn_color = base_color
                label_color = (10, 10, 10)
                label = name
            else:
                # Dimmed when cut
                btn_color = tuple(max(0, c // 4) for c in base_color)  # type: ignore[assignment]
                label_color = (120, 120, 120)
                label = f"{name} [CUT]"

            rect = (x, btn_y, PANEL_W, _WIRE_BTN_H)
            pygame.draw.rect(screen, btn_color, rect, border_radius=5)
            if not intact:
                # Draw a thin line through the button to emphasise cut state
                mid_y = btn_y + _WIRE_BTN_H // 2
                pygame.draw.line(screen, (180, 60, 60), (x + 4, mid_y), (x + PANEL_W - 4, mid_y), 2)

            lbl_surf = font.render(label, True, label_color)
            lx = x + (PANEL_W - lbl_surf.get_width()) // 2
            ly = btn_y + (_WIRE_BTN_H - lbl_surf.get_height()) // 2
            screen.blit(lbl_surf, (lx, ly))

            self._wire_btn_rects.append((name, rect))
            btn_y += _WIRE_BTN_H + _WIRE_BTN_GAP

        # Footer hint
        hint_surf = font.render("click to toggle", True, (80, 80, 100))
        screen.blit(hint_surf, (x + (PANEL_W - hint_surf.get_width()) // 2, y + panel_h - hint_surf.get_height()))

    def _get_panel_font(self) -> "pygame.font.Font":
        """Return a small font for the wire panel labels."""
        if self._panel_font is not None:
            return self._panel_font  # type: ignore[return-value]
        for name in ("Segoe UI", "Arial", "Helvetica", "DejaVu Sans", ""):
            try:
                f = pygame.font.SysFont(name, 13) if name else pygame.font.Font(None, 15)
                self._panel_font = f
                return f
            except Exception:
                continue
        self._panel_font = pygame.font.Font(None, 15)
        return self._panel_font  # type: ignore[return-value]

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

    # Interval for synthetic Enter repeats while the key is held.
    # Must be shorter than HOLD_TIMEOUT (0.6 s) so the planting screen
    # never times out, but long enough that normal typing never double-fires.
    _ENTER_REPEAT_INTERVAL: float = 0.4

    def _poll_events(self) -> None:
        """Process pygame events: quit signals, key presses, and wire clicks."""
        if not _HAS_PYGAME:
            return
        import time as _time
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
                if key == "enter":
                    self._enter_held = True
                    self._enter_repeat_due = _time.monotonic() + self._ENTER_REPEAT_INTERVAL
            elif event.type == pygame.KEYUP:
                key = self._keymap.get(event.key)
                if key == "enter":
                    self._enter_held = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_wire_click(event.pos)

        # Emit synthetic Enter repeats while the key is physically held.
        if self._enter_held:
            now = _time.monotonic()
            if now >= self._enter_repeat_due:
                self._key_queue.put("enter")
                logger.debug("PygameDisplay key repeat: enter")
                self._enter_repeat_due = now + self._ENTER_REPEAT_INTERVAL

    def _handle_wire_click(self, pos: tuple[int, int]) -> None:
        """Toggle a wire when its button is clicked.

        Args:
            pos: Mouse position (x, y) in screen pixels.
        """
        if self._wires is None:
            return
        mx, my = pos
        for name, (bx, by, bw, bh) in self._wire_btn_rects:
            if bx <= mx < bx + bw and by <= my < by + bh:
                self._wires.toggle_wire(name)
                logger.debug("PygameDisplay: wire '%s' toggled via click", name)
                # Force immediate redraw
                self._prev_wire_snapshot = ""
                break
