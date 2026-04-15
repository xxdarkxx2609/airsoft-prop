"""No-battery HAL implementation.

Used when no UPS HAT (PiSugar, UPS-Lite, etc.) is present.
All battery queries return None, which UI code must handle gracefully.
"""

from typing import Optional

from src.hal.base import BatteryBase
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NoBattery(BatteryBase):
    """Stub battery implementation for systems without a UPS HAT.

    Every query method returns None, signalling to the UI layer that
    no battery information is available and battery indicators should
    not be rendered.
    """

    def init(self) -> None:
        """Initialize the no-battery stub."""
        logger.info("No UPS HAT configured -- battery monitoring disabled")

    def get_battery_level(self) -> Optional[int]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def get_voltage(self) -> Optional[float]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def is_charging(self) -> Optional[bool]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def get_current(self) -> Optional[float]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def is_power_plugged(self) -> Optional[bool]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def get_runtime_minutes(self) -> Optional[int]:
        """Return None (no UPS HAT present).

        Returns:
            Always None.
        """
        return None

    def shutdown(self) -> None:
        """No resources to clean up."""
        logger.info("NoBattery shut down (no-op)")
