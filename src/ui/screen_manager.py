"""Screen manager for handling screen transitions and input routing.

Maintains a registry of named screens and manages the active screen,
including lifecycle callbacks (on_enter / on_exit) during transitions.
"""

from __future__ import annotations

from typing import Optional

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ScreenManager:
    """Manages registered screens and transitions between them.

    Screens are registered by name. At any point exactly one screen is
    active and receives render() and handle_input() calls.
    """

    def __init__(self) -> None:
        """Initialize the screen manager with an empty registry."""
        self._screens: dict[str, BaseScreen] = {}
        self._active: Optional[BaseScreen] = None
        self._active_name: str = ""

    def register(self, name: str, screen: BaseScreen) -> None:
        """Register a screen with a unique name.

        Args:
            name: Unique identifier for the screen (e.g. 'menu', 'armed').
            screen: The BaseScreen instance to register.

        Raises:
            ValueError: If a screen with the given name is already registered.
        """
        if name in self._screens:
            raise ValueError(f"Screen '{name}' is already registered")
        self._screens[name] = screen
        logger.debug("Registered screen: %s", name)

    def switch_to(self, name: str) -> None:
        """Switch to a named screen.

        Calls on_exit() on the current screen (if any) and on_enter()
        on the new screen.

        Args:
            name: Name of the screen to switch to.

        Raises:
            KeyError: If no screen with the given name is registered.
        """
        if name not in self._screens:
            raise KeyError(f"Screen '{name}' is not registered")

        if self._active is not None:
            logger.debug("Exiting screen: %s", self._active_name)
            self._active.on_exit()

        self._active_name = name
        self._active = self._screens[name]
        logger.info("Switching to screen: %s", name)
        self._active.on_enter()

    def render(self, display: DisplayBase) -> None:
        """Render the active screen on the display.

        Does nothing if no screen is active.

        Args:
            display: The display HAL instance to render on.
        """
        if self._active is not None:
            self._active.render(display)

    def handle_input(self, key: str) -> None:
        """Forward a key press to the active screen.

        Does nothing if no screen is active.

        Args:
            key: The key string to forward.
        """
        if self._active is not None:
            self._active.handle_input(key)

    def get_screen(self, name: str) -> Optional[BaseScreen]:
        """Return a registered screen by name, or None if not found."""
        return self._screens.get(name)

    @property
    def active_name(self) -> str:
        """Name of the currently active screen.

        Returns:
            The name string, or empty string if no screen is active.
        """
        return self._active_name
