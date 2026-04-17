"""Mock battery HAL implementation for desktop testing.

Simulates a slowly discharging battery so the UI can be tested
without a real PiSugar HAT.
"""

import random
import time
from typing import Optional

from src.hal.base import BatteryBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Simulated starting values.
_START_LEVEL = 85
# Simulated discharge rate: percent per real second.
_DISCHARGE_PER_SEC = 0.05
# Simulated system draw (mA) with slight jitter.
_AVG_DRAW_MA = 280.0
_DRAW_JITTER = 30.0
# Battery capacity for runtime calc.
_CAPACITY_MAH = 1200


class MockBattery(BatteryBase):
    """Simulate a discharging battery for desktop / mock testing."""

    def __init__(self) -> None:
        self._start_time: float = 0.0
        self._start_level: float = _START_LEVEL

    def init(self) -> None:
        self._start_time = time.monotonic()
        logger.info(
            "MockBattery initialised at %d%% (discharges over time)",
            self._start_level,
        )

    # ------------------------------------------------------------------
    # BatteryBase interface
    # ------------------------------------------------------------------

    def get_battery_level(self) -> Optional[int]:
        return max(0, int(self._simulated_level()))

    def get_voltage(self) -> Optional[float]:
        level = self._simulated_level()
        # Simple linear mapping: 0% → 3.0V, 100% → 4.2V.
        voltage = 3.0 + (level / 100.0) * 1.2
        return round(voltage, 2)

    def is_charging(self) -> Optional[bool]:
        return False

    def get_current(self) -> Optional[float]:
        jitter = random.uniform(-_DRAW_JITTER, _DRAW_JITTER)
        return round(_AVG_DRAW_MA + jitter, 1)

    def is_power_plugged(self) -> Optional[bool]:
        return False

    def get_runtime_minutes(self) -> Optional[int]:
        level = self._simulated_level()
        if level <= 0:
            return 0
        remaining_mah = _CAPACITY_MAH * (level / 100.0)
        return max(0, int(remaining_mah / _AVG_DRAW_MA * 60))

    def get_charge_minutes(self) -> Optional[int]:
        """Estimate minutes until fully charged (mock: fixed value)."""
        level = self._simulated_level()
        if level >= 100:
            return None
        remaining_pct = 100 - level
        remaining_mah = _CAPACITY_MAH * (remaining_pct / 100.0)
        return max(0, int(remaining_mah / 500 * 60))

    def shutdown(self) -> None:
        logger.info("MockBattery shut down")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _simulated_level(self) -> float:
        elapsed = time.monotonic() - self._start_time
        level = self._start_level - elapsed * _DISCHARGE_PER_SEC
        return max(0.0, level)
