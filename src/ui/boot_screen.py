"""Boot splash screen shown at application startup.

Displays the project name and version for a configurable duration,
then automatically transitions to the main menu screen.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text
from src.utils.logger import get_logger
from src.utils.version import format_version_short

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# How long the splash screen stays visible (seconds).
_BOOT_DURATION: float = 2.5


class BootScreen(BaseScreen):
    """Splash screen displayed during application boot.

    Shows the project name and version for approximately 2.5 seconds,
    then transitions to the main menu.  Any key press during boot
    immediately skips to the menu.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._start_time: float = 0.0
        self._transitioned: bool = False

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Record the time the boot screen was entered."""
        self._start_time = time.time()
        self._transitioned = False
        logger.info("Boot screen entered")

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Draw the splash screen and auto-transition when time has elapsed.

        Layout (20x4):
            Line 0: '  AIRSOFT  PROP  '  (centered)
            Line 1: '   PROP v1.0.0   '  (centered, with version)
            Line 2: (blank)
            Line 3: '   Booting...    '  (centered)

        Args:
            display: The display HAL instance to render on.
        """
        version: str = self.app.config.get("version", default="unknown")

        display.write_line(0, center_text("AIRSOFT  PROP"))
        display.write_line(1, center_text(f"PROP v{format_version_short(version)}"))
        display.write_line(2, center_text(""))
        display.write_line(3, center_text("Booting..."))

        # Check whether the boot duration has elapsed.
        elapsed = time.time() - self._start_time
        if elapsed >= _BOOT_DURATION and not self._transitioned:
            self._transition_to_menu()

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Skip the boot splash on any key press.

        Args:
            key: The pressed key string (ignored — any key skips).
        """
        if not self._transitioned:
            logger.debug("Boot splash skipped by key press: %s", key)
            self._transition_to_menu()

    # -- helpers --------------------------------------------------------------

    def _transition_to_menu(self) -> None:
        """Switch to the main menu or tournament screen exactly once."""
        self._transitioned = True
        if self.app.config.is_tournament_enabled():
            logger.info("Boot complete, switching to tournament screen")
            self.app.screen_manager.switch_to("tournament")
        else:
            logger.info("Boot complete, switching to menu")
            self.app.screen_manager.switch_to("menu")
