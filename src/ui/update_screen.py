"""Update screen for checking and installing OTA updates.

Accessible from the main menu via the '9' shortcut.  Runs the update
check in a background thread so the UI is never blocked.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text, pad_text, progress_bar
from src.utils.logger import get_logger
from src.utils.updater import UpdateInfo, _short_version, apply_update, check_for_updates

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)



class _State(Enum):
    """Internal states of the update screen."""

    CHECKING = auto()
    NO_INTERNET = auto()
    UP_TO_DATE = auto()
    UPDATE_AVAILABLE = auto()
    UPDATING = auto()
    UPDATE_DONE = auto()
    UPDATE_FAILED = auto()
    RESTARTING = auto()


class UpdateScreen(BaseScreen):
    """Screen for checking and applying git-based OTA updates.

    State flow::

        CHECKING ──► UP_TO_DATE
                 ├──► UPDATE_AVAILABLE ──► UPDATING ──► UPDATE_DONE ──► RESTARTING
                 │                                  └──► UPDATE_FAILED
                 └──► NO_INTERNET

    The initial check and the actual update both run in background
    threads to avoid blocking the render/input loop.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._state: _State = _State.CHECKING
        self._update_info: Optional[UpdateInfo] = None
        self._error_msg: str = ""
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Start the update check in a background thread."""
        self._state = _State.CHECKING
        self._update_info = None
        self._error_msg = ""
        logger.info("Update screen entered, starting check")
        self._run_in_background(self._do_check)

    def on_exit(self) -> None:
        """Clean up (the background thread is daemonic, so it will not
        block application shutdown)."""
        self._thread = None

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Render the screen according to the current state.

        Args:
            display: The display HAL instance to render on.
        """
        renderer = {
            _State.CHECKING: self._render_checking,
            _State.NO_INTERNET: self._render_no_internet,
            _State.UP_TO_DATE: self._render_up_to_date,
            _State.UPDATE_AVAILABLE: self._render_update_available,
            _State.UPDATING: self._render_updating,
            _State.UPDATE_DONE: self._render_update_done,
            _State.UPDATE_FAILED: self._render_update_failed,
            _State.RESTARTING: self._render_restarting,
        }.get(self._state, self._render_checking)
        renderer(display)

    def _render_checking(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text(""))
        display.write_line(2, center_text("Checking updates..."))
        display.write_line(3, pad_text(progress_bar(0, 1, width=20)))

    def _render_no_internet(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text("No internet"))
        display.write_line(2, center_text("connection"))
        display.write_line(3, pad_text("<- Back"))

    def _render_up_to_date(self, display: DisplayBase) -> None:
        info = self._update_info
        version = _short_version(info.current_version) if info else "?"
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text("Up to date!"))
        display.write_line(2, pad_text(f"Version: {version}"))
        display.write_line(3, pad_text("<- Back"))

    def _render_update_available(self, display: DisplayBase) -> None:
        info = self._update_info
        if info:
            current = _short_version(info.current_version)
            remote = _short_version(info.remote_version) if info.remote_version else "?"
            behind = info.commits_behind
        else:
            current = remote = "?"
            behind = 0

        display.write_line(0, center_text("Update available!"))
        display.write_line(1, pad_text(f"{current} -> {remote}"))
        display.write_line(2, pad_text(f"{behind} commit(s) behind"))
        display.write_line(3, pad_text("Ent Install <- Back"))

    def _render_updating(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text(""))
        display.write_line(2, center_text("Installing update.."))
        display.write_line(3, pad_text(progress_bar(1, 2, width=20)))

    def _render_update_done(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text("Update complete!"))
        display.write_line(2, center_text("Restart required"))
        display.write_line(3, pad_text("Ent Restart <- Back"))

    def _render_restarting(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text(""))
        display.write_line(2, center_text("Restarting..."))
        display.write_line(3, center_text(""))

    def _render_update_failed(self, display: DisplayBase) -> None:
        display.write_line(0, center_text("=== Update ==="))
        display.write_line(1, center_text("Update failed!"))
        # Truncate error to fit one LCD line.
        display.write_line(2, pad_text(self._error_msg[:20]))
        display.write_line(3, pad_text("<- Back"))

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Handle user input based on current state.

        Args:
            key: The pressed key string.
        """
        if key == "backspace":
            # Allow going back from any non-busy state.
            if self._state not in (
                _State.CHECKING, _State.UPDATING, _State.RESTARTING,
            ):
                logger.debug("Returning to menu from update screen")
                self.app.screen_manager.switch_to("menu")
            return

        if key == "enter" and self._state == _State.UPDATE_AVAILABLE:
            logger.info("User initiated update installation")
            self._state = _State.UPDATING
            self._run_in_background(self._do_apply)

        elif key == "enter" and self._state == _State.UPDATE_DONE:
            logger.info("User initiated service restart after update")
            self._state = _State.RESTARTING
            self._run_in_background(self._do_restart)

    # -- background work ------------------------------------------------------

    def _run_in_background(self, target: object) -> None:
        """Launch *target* in a daemon thread.

        Args:
            target: Callable to execute.
        """
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def _do_check(self) -> None:
        """Run the update check (called in a background thread)."""
        try:
            project_root = str(self.app.config.project_root)
            info = check_for_updates(project_root)
            self._update_info = info

            if info.error:
                logger.warning("Update check error: %s", info.error)
                self._error_msg = info.error
                self._state = _State.NO_INTERNET
            elif info.update_available:
                logger.info(
                    "Update available: %s -> %s (%d commits behind)",
                    info.current_version,
                    info.remote_version,
                    info.commits_behind,
                )
                self._state = _State.UPDATE_AVAILABLE
            else:
                logger.info("System is up to date (%s)", info.current_version)
                self._state = _State.UP_TO_DATE
        except Exception as exc:  # noqa: BLE001
            logger.error("Update check failed: %s", exc)
            self._error_msg = str(exc)[:20]
            self._state = _State.NO_INTERNET

    def _do_apply(self) -> None:
        """Apply the update (called in a background thread)."""
        try:
            project_root = str(self.app.config.project_root)
            success, message = apply_update(project_root)
            if success:
                logger.info("Update applied: %s", message)
                self._state = _State.UPDATE_DONE
            else:
                logger.error("Update failed: %s", message)
                self._error_msg = message[:20]
                self._state = _State.UPDATE_FAILED
        except Exception as exc:  # noqa: BLE001
            logger.error("Update apply failed: %s", exc)
            self._error_msg = str(exc)[:20]
            self._state = _State.UPDATE_FAILED

    def _do_restart(self) -> None:
        """Restart the service (called in a background thread).

        On the Pi this issues ``systemctl restart`` via sudo.
        In mock mode the application simply exits.
        """
        try:
            if self.app._mock:
                logger.info("Mock mode: exiting application for restart")
                self.app.shutdown()
                sys.exit(0)
            else:
                logger.info("Restarting service via systemctl")
                subprocess.Popen(
                    ["sudo", "systemctl", "restart", "airsoft-prop"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Service restart failed: %s", exc)
            self._error_msg = str(exc)[:20]
            self._state = _State.UPDATE_FAILED
