"""Mock LED implementation for desktop testing.

Logs blink_once() and set_enabled() calls without touching any GPIO hardware.
"""

from src.hal.base import LedBase
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MockLed(LedBase):
    """Software-only LED that logs all operations."""

    def __init__(self) -> None:
        self._enabled: bool = False

    def init(self) -> None:
        """Initialize the mock LED (no-op)."""
        logger.info("MockLed initialized (no hardware)")

    def blink_once(self) -> None:
        """Log a blink event."""
        logger.debug("MockLed BLINK")

    def set_enabled(self, on: bool) -> None:
        """Log an enable/disable event."""
        self._enabled = on
        logger.debug("MockLed set_enabled: %s", on)

    def shutdown(self) -> None:
        """Shut down the mock LED (no-op)."""
        self._enabled = False
        logger.info("MockLed shut down")
