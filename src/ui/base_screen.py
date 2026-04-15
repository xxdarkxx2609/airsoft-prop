"""Abstract base class for all UI screens.

Every screen in the application (boot, menu, setup, armed, result, status,
update) inherits from BaseScreen and implements render() and handle_input().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase

if TYPE_CHECKING:
    from src.app import App

# Mapping from numpad digit keys to navigation directions.
# The Delock USB numpad always sends digit keycodes (KEY_KP0-KEY_KP9)
# regardless of NumLock state.  Navigation screens apply this mapping
# so that 8=up, 2=down, 4=left, 6=right — matching the physical
# arrow labels printed on the numpad keys.
DIGIT_TO_NAV: dict[str, str] = {
    "8": "up",
    "2": "down",
    "4": "left",
    "6": "right",
}


def translate_digit_to_nav(key: str) -> str:
    """Translate a numpad digit to its navigation equivalent.

    Returns the navigation direction for keys in ``DIGIT_TO_NAV``
    (8→up, 2→down, 4→left, 6→right).  All other keys pass through
    unchanged.

    Args:
        key: The input key string.

    Returns:
        The navigation string if mapped, or the original key.
    """
    return DIGIT_TO_NAV.get(key, key)


class BaseScreen(ABC):
    """Abstract base for all UI screens.

    Provides the interface that ScreenManager uses to drive screen
    lifecycle and rendering on the 20x4 LCD display.
    """

    def __init__(self, app: App) -> None:
        """Store reference to the App instance for accessing HAL, config, etc.

        Args:
            app: The main application instance.
        """
        self.app = app

    @abstractmethod
    def render(self, display: DisplayBase) -> None:
        """Draw the screen content on the display.

        Called by ScreenManager whenever the display needs to be refreshed.

        Args:
            display: The display HAL instance to render on.
        """

    @abstractmethod
    def handle_input(self, key: str) -> None:
        """Process a key press.

        Args:
            key: One of '0'-'9', 'enter', 'backspace', 'up', 'down',
                 'left', 'right', 'plus', 'minus', 'dot', 'numlock',
                 'slash', 'asterisk'.
        """

    def on_enter(self) -> None:
        """Called when this screen becomes active.

        Override to perform setup when switching to this screen
        (e.g. reset state, start timers).
        """

    def on_exit(self) -> None:
        """Called when leaving this screen.

        Override to perform cleanup when switching away from this screen
        (e.g. stop timers, release resources).
        """
