"""Helper utilities for the 20x4 HD44780 LCD display.

Provides custom character definitions, text formatting helpers,
and display utility functions used across all screens.
"""

from src.hal.base import DisplayBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Custom character slot assignments (0-7)
# ---------------------------------------------------------------------------
CHAR_WIFI_ON: int = 0
"""WiFi connected icon."""

CHAR_WIFI_OFF: int = 1
"""WiFi disconnected icon."""

CHAR_BATTERY_FULL: int = 2
"""Battery full icon."""

CHAR_BATTERY_LOW: int = 3
"""Battery low icon."""

CHAR_CURSOR: int = 4
"""Menu cursor (triangle pointing right)."""

CHAR_SCROLL_UP: int = 5
"""Scroll-up indicator (▲) for the menu."""

CHAR_SCROLL_DOWN: int = 6
"""Scroll-down indicator (▼) for the menu."""

CHAR_LOCK: int = 7
"""Lock icon for tournament mode."""

# ---------------------------------------------------------------------------
# Custom character pixel patterns (5x8 bitmaps, 8 rows each)
# ---------------------------------------------------------------------------
CUSTOM_CHARS: dict[int, list[int]] = {
    CHAR_WIFI_ON: [
        0b00000,
        0b01110,
        0b10001,
        0b00100,
        0b01010,
        0b00000,
        0b00100,
        0b00000,
    ],
    CHAR_WIFI_OFF: [
        0b00000,
        0b01110,
        0b10001,
        0b00100,
        0b01010,
        0b10001,
        0b00100,
        0b00000,
    ],
    CHAR_BATTERY_FULL: [
        0b01110,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
    ],
    CHAR_BATTERY_LOW: [
        0b01110,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b11111,
        0b11111,
    ],
    CHAR_CURSOR: [
        0b00000,
        0b01000,
        0b01100,
        0b01110,
        0b01100,
        0b01000,
        0b00000,
        0b00000,
    ],
    CHAR_SCROLL_UP: [
        0b00000,
        0b00100,
        0b01110,
        0b11111,
        0b00000,
        0b00000,
        0b00000,
        0b00000,
    ],
    CHAR_SCROLL_DOWN: [
        0b00000,
        0b00000,
        0b00000,
        0b00000,
        0b11111,
        0b01110,
        0b00100,
        0b00000,
    ],
    CHAR_LOCK: [
        0b01110,
        0b10001,
        0b10001,
        0b11111,
        0b11011,
        0b11011,
        0b11111,
        0b00000,
    ],
}


def register_custom_chars(display: DisplayBase) -> None:
    """Register all custom characters on the display.

    Should be called once during display initialization (e.g. in the
    boot sequence) before any screen tries to use the custom chars.

    Args:
        display: The display HAL instance.
    """
    for slot, pattern in CUSTOM_CHARS.items():
        display.create_custom_char(slot, pattern)
    logger.debug("Registered %d custom characters", len(CUSTOM_CHARS))


def center_text(text: str, width: int = 20) -> str:
    """Center text within the given width.

    If the text is longer than width it is truncated.

    Args:
        text: The text to center.
        width: Target width in characters (default 20).

    Returns:
        Centered string of exactly *width* characters.
    """
    return text[:width].center(width)


def pad_text(text: str, width: int = 20) -> str:
    """Pad or truncate text to exactly *width* characters.

    Text is left-aligned. Longer text is truncated; shorter text is
    padded with spaces on the right.

    Args:
        text: The text to pad.
        width: Target width in characters (default 20).

    Returns:
        Left-aligned string of exactly *width* characters.
    """
    return text[:width].ljust(width)


def format_timer(seconds: int) -> str:
    """Format seconds as a MM:SS string.

    Handles values from 0 up to 99:59 (5999 seconds).

    Args:
        seconds: Non-negative number of seconds.

    Returns:
        Formatted string like '05:30' or '00:07'.
    """
    seconds = max(0, seconds)
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def blink_text(text: str, visible: bool) -> str:
    """Return text or blank spaces based on the blink state.

    Used to create a blinking effect by alternating between
    the real text and a blank placeholder of the same length.

    Args:
        text: The text to display when visible.
        visible: True to show text, False to show spaces.

    Returns:
        The original text or spaces of the same length.
    """
    if visible:
        return text
    return " " * len(text)


def progress_bar(current: int, total: int, width: int = 16) -> str:
    """Render a progress bar within brackets.

    Output looks like ``[=====>          ]`` where the inner area is
    *width - 2* characters wide (accounting for the ``[`` and ``]``
    brackets).

    Args:
        current: Current progress value.
        total: Maximum progress value.
        width: Total width including brackets (default 16, min 4).

    Returns:
        Progress bar string of exactly *width* characters.
    """
    width = max(4, width)
    inner_width = width - 2  # subtract brackets

    if total <= 0:
        filled = 0
    else:
        ratio = max(0.0, min(1.0, current / total))
        filled = int(ratio * inner_width)

    # Build the inner bar: filled '=' with a '>' head, rest spaces
    if filled == 0:
        bar = " " * inner_width
    elif filled >= inner_width:
        bar = "=" * inner_width
    else:
        bar = "=" * (filled - 1) + ">" + " " * (inner_width - filled)

    return f"[{bar}]"
