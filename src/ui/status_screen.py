"""Multi-page status screen showing network, system, and battery info.

Accessible from the main menu via the '8' shortcut.  The user pages
through three screens with Enter and returns to the menu with Backspace.
"""

from __future__ import annotations

import os
import platform
import time
from typing import TYPE_CHECKING

from src.hal.base import DisplayBase
from src.ui.base_screen import BaseScreen
from src.ui.lcd_helpers import center_text, pad_text
from src.utils.logger import get_logger
from src.utils.version import format_version_short

if TYPE_CHECKING:
    from src.app import App

logger = get_logger(__name__)

# Total number of status pages.
_TOTAL_PAGES: int = 3

# Footer shown on every page.
_FOOTER: str = "Ent->Next  <-Back"


class StatusScreen(BaseScreen):
    """Three-page information screen (Network / System / Battery).

    Pages:
        0 — Network: WLAN name and IP address (or AP-mode fallback).
        1 — System:  Version, CPU temperature, uptime.
        2 — Battery: Level and voltage (or "No UPS HAT" placeholder).

    Navigation:
        enter     — advance to the next page (wraps around).
        backspace — return to the main menu.
    """

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self._page: int = 0

    # -- lifecycle ------------------------------------------------------------

    def on_enter(self) -> None:
        """Reset to the first page when the screen becomes active."""
        self._page = 0
        logger.info("Status screen entered")

    # -- rendering ------------------------------------------------------------

    def render(self, display: DisplayBase) -> None:
        """Render the current status page.

        Args:
            display: The display HAL instance to render on.
        """
        if self._page == 0:
            self._render_network(display)
        elif self._page == 1:
            self._render_system(display)
        else:
            self._render_battery(display)

    # -- page renderers -------------------------------------------------------

    def _render_network(self, display: DisplayBase) -> None:
        """Page 0: network information.

        Shows AP credentials when the captive portal is active,
        otherwise the current WLAN name and IP address.
        """
        portal = self.app.captive_portal
        if portal and portal.is_active():
            info = portal.get_ap_info()
            display.write_line(0, center_text("=== Network ==="))
            display.write_line(1, pad_text(f"AP: {info['ssid']}"))
            display.write_line(2, pad_text(f"Pass: {info['password']}"))
            display.write_line(3, pad_text("-> Connect phone"))
            return

        ssid = self._get_ssid()
        ip_addr = self._get_ip_address()

        display.write_line(0, center_text("=== Network ==="))
        display.write_line(1, pad_text(f"WLAN: {ssid}"))
        display.write_line(2, pad_text(f"IP: {ip_addr}"))
        display.write_line(3, pad_text(_FOOTER))

    def _render_system(self, display: DisplayBase) -> None:
        """Page 1: system information."""
        version: str = self.app.config.get("version", default="unknown")
        uptime_str = self._get_uptime()

        display.write_line(0, center_text("=== System ==="))
        display.write_line(1, pad_text(f"Version: {format_version_short(version)}"))
        display.write_line(2, pad_text(f"Uptime: {uptime_str}"))
        display.write_line(3, pad_text(_FOOTER))

    def _render_battery(self, display: DisplayBase) -> None:
        """Page 2: battery information."""
        level = self.app.battery.get_battery_level()
        voltage = self.app.battery.get_voltage()

        display.write_line(0, center_text("=== Battery ==="))

        if level is not None:
            # Line 1: percentage + mini bar
            bar = self._battery_bar(level, width=8)
            display.write_line(1, pad_text(f"Level: {level:3d}% {bar}"))

            # Line 2: voltage + runtime or charging status
            charging = self.app.battery.is_charging()
            runtime = self.app.battery.get_runtime_minutes()
            parts: list[str] = []
            if voltage is not None:
                parts.append(f"{voltage:.2f}V")
            if charging:
                parts.append("Charging")
            elif runtime is not None:
                hours, mins = divmod(runtime, 60)
                parts.append(f"~{hours}h {mins:02d}m left")
            display.write_line(2, pad_text("  ".join(parts)))
        else:
            display.write_line(1, pad_text("No UPS HAT"))
            display.write_line(2, pad_text(""))

        display.write_line(3, pad_text(_FOOTER))

    @staticmethod
    def _battery_bar(percent: int, width: int = 8) -> str:
        """Build a text progress bar like ``[####  ]``.

        Args:
            percent: Battery percentage (0-100).
            width: Inner width (characters between brackets).

        Returns:
            Formatted bar string.
        """
        filled = round(percent / 100 * width)
        return "[" + "#" * filled + " " * (width - filled) + "]"

    # -- input ----------------------------------------------------------------

    def handle_input(self, key: str) -> None:
        """Handle page navigation.

        Args:
            key: The pressed key string.
        """
        if key == "enter":
            self._page = (self._page + 1) % _TOTAL_PAGES
            logger.debug("Status page: %d", self._page)
        elif key == "backspace":
            logger.debug("Returning to menu from status screen")
            self.app.screen_manager.switch_to("menu")

    # -- platform helpers (best-effort, never raise) --------------------------

    @staticmethod
    def _get_ssid() -> str:
        """Attempt to determine the connected WiFi SSID.

        Returns:
            SSID string or a fallback message.
        """
        try:
            if platform.system() == "Linux":
                import subprocess
                result = subprocess.run(
                    ["iwgetid", "-r"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                ssid = result.stdout.strip()
                return ssid if ssid else "Not connected"
        except Exception:  # noqa: BLE001
            pass
        return "N/A"

    @staticmethod
    def _get_ip_address() -> str:
        """Attempt to determine the device's IP address.

        Uses a non-connecting UDP socket trick that works on all
        platforms without requiring third-party packages.

        Returns:
            IP address string or a fallback message.
        """
        import socket

        try:
            # This does not actually send traffic — it just lets the OS
            # choose the interface that would route to 8.8.8.8.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(1)
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:  # noqa: BLE001
            return "No connection"

    @staticmethod
    def _get_uptime() -> str:
        """Return a human-readable system uptime string.

        Returns:
            Uptime like '2h 15m' or 'N/A' on unsupported platforms.
        """
        try:
            if platform.system() == "Linux" and os.path.exists("/proc/uptime"):
                with open("/proc/uptime", "r", encoding="utf-8") as f:
                    seconds = float(f.readline().split()[0])
                hours = int(seconds) // 3600
                minutes = (int(seconds) % 3600) // 60
                return f"{hours}h {minutes:02d}m"
        except Exception:  # noqa: BLE001
            pass

        # Fallback: use process uptime as a rough approximation.
        try:
            process_uptime = time.time() - _PROCESS_START
            hours = int(process_uptime) // 3600
            minutes = (int(process_uptime) % 3600) // 60
            return f"~{hours}h {minutes:02d}m"
        except Exception:  # noqa: BLE001
            return "N/A"


# Snapshot of process start time for fallback uptime calculation.
_PROCESS_START: float = time.time()
