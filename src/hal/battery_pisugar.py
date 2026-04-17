"""PiSugar 3 battery HAL implementation.

Communicates with the pisugar-power-manager daemon via TCP socket
on localhost:8423.  The daemon must be installed and running::

    curl http://cdn.pisugar.com/release/pisugar-power-manager.sh | sudo bash

Protocol: send ``"get <key>\\n"``, receive ``"<key>: <value>\\n"``.
"""

import socket
import time
from typing import Any, Dict, Optional

from src.hal.base import BatteryBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default battery capacity for PiSugar 3 (mAh).
_DEFAULT_CAPACITY_MAH = 1200
# Average system draw estimate used when live current is unavailable (mA).
_DEFAULT_AVG_DRAW_MA = 280
# Typical USB-C charging current at 5V (mA) — used for charge time estimation.
_DEFAULT_CHARGE_CURRENT_MA = 500
# How long to keep cached values (seconds).
_CACHE_TTL = 5.0
# Seconds between reconnect attempts after the daemon becomes unreachable.
_RETRY_INTERVAL = 30.0


class PiSugarBattery(BatteryBase):
    """Read battery data from a PiSugar 3 via *pisugar-power-manager*."""

    def __init__(self, config: "src.utils.config.Config") -> None:
        self._host: str = "127.0.0.1"
        self._port: int = 8423
        self._timeout: float = 2.0
        self._capacity_mah: int = _DEFAULT_CAPACITY_MAH

        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._available: bool = True
        self._retry_after: float = 0.0
        self._warned: bool = False

    # ------------------------------------------------------------------
    # BatteryBase interface
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Probe the daemon on first startup."""
        model = self._query("get model")
        if model is not None:
            logger.info("PiSugar detected: %s", self._parse_str(model))
            self._available = True
        else:
            logger.warning(
                "pisugar-power-manager not reachable on %s:%s "
                "-- battery monitoring unavailable until daemon starts",
                self._host,
                self._port,
            )
            self._available = False
            self._retry_after = time.monotonic() + _RETRY_INTERVAL

    def get_battery_level(self) -> Optional[int]:
        value = self._parse_float(self._cached("get battery"))
        return int(round(value)) if value is not None else None

    def get_voltage(self) -> Optional[float]:
        value = self._parse_float(self._cached("get battery_v"))
        return round(value, 2) if value is not None else None

    def is_charging(self) -> Optional[bool]:
        return self._parse_bool(self._cached("get battery_charging"))

    def get_current(self) -> Optional[float]:
        value = self._parse_float(self._cached("get battery_i"))
        return round(value, 1) if value is not None else None

    def is_power_plugged(self) -> Optional[bool]:
        return self._parse_bool(self._cached("get battery_power_plugged"))

    def get_runtime_minutes(self) -> Optional[int]:
        level = self.get_battery_level()
        if level is None:
            return None

        # Prefer live current reading when available.
        current = self.get_current()
        if current is not None and current > 0:
            remaining_mah = self._capacity_mah * (level / 100.0)
            return max(0, int(remaining_mah / current * 60))

        # Fallback: estimate from percentage and average draw.
        remaining_mah = self._capacity_mah * (level / 100.0)
        return max(0, int(remaining_mah / _DEFAULT_AVG_DRAW_MA * 60))

    def get_charge_minutes(self) -> Optional[int]:
        """Estimate minutes until battery is fully charged."""
        level = self.get_battery_level()
        if level is None or level >= 100:
            return None
        remaining_pct = 100 - level
        remaining_mah = self._capacity_mah * (remaining_pct / 100.0)
        return max(0, int(remaining_mah / _DEFAULT_CHARGE_CURRENT_MA * 60))

    def shutdown(self) -> None:
        logger.info("PiSugarBattery shut down")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_cache(self) -> None:
        """Fetch all values in a single burst and cache them."""
        commands = [
            "get battery",
            "get battery_v",
            "get battery_i",
            "get battery_charging",
            "get battery_power_plugged",
        ]
        for cmd in commands:
            resp = self._query(cmd)
            if resp is not None:
                self._cache[cmd] = resp
            # On connection failure _query sets _available=False and we
            # stop wasting time on subsequent commands.
            if not self._available:
                break
        self._cache_time = time.monotonic()

    def _cached(self, command: str) -> Optional[str]:
        """Return a cached response, refreshing if stale."""
        now = time.monotonic()

        # If daemon was unreachable, periodically retry.
        if not self._available:
            if now < self._retry_after:
                return self._cache.get(command)
            # Try to reconnect.
            probe = self._query("get battery")
            if probe is not None:
                logger.info("pisugar-power-manager reconnected")
                self._available = True
                self._warned = False
                self._cache["get battery"] = probe
            else:
                self._retry_after = now + _RETRY_INTERVAL
                return None

        if now - self._cache_time > _CACHE_TTL:
            self._refresh_cache()

        return self._cache.get(command)

    def _query(self, command: str) -> Optional[str]:
        """Send a single command and return the raw response line."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self._timeout)
                sock.connect((self._host, self._port))
                sock.sendall((command + "\n").encode("utf-8"))
                data = sock.recv(1024).decode("utf-8").strip()
                return data if data else None
        except (ConnectionRefusedError, socket.timeout, OSError) as exc:
            if not self._warned:
                logger.warning("pisugar-power-manager query failed: %s", exc)
                self._warned = True
            self._available = False
            self._retry_after = time.monotonic() + _RETRY_INTERVAL
            return None

    # ------------------------------------------------------------------
    # Response parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_float(response: Optional[str]) -> Optional[float]:
        if response is None:
            return None
        try:
            _, value = response.split(":", 1)
            return float(value.strip())
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_bool(response: Optional[str]) -> Optional[bool]:
        if response is None:
            return None
        try:
            _, value = response.split(":", 1)
            return value.strip().lower() == "true"
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_str(response: Optional[str]) -> Optional[str]:
        if response is None:
            return None
        try:
            _, value = response.split(":", 1)
            return value.strip()
        except (ValueError, IndexError):
            return None
