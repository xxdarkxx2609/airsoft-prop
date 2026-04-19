"""GPIO LED output for Raspberry Pi.

Drives a single indicator LED on a configurable GPIO pin using gpiozero.
The LED is wired through a current-limiting resistor to the GPIO output.

Pin assignment is read from ``config/hardware.yaml`` under ``gpio.led.pin``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.hal.base import LedBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# Flash duration in seconds.
_BLINK_ON_TIME: float = 0.20   # 200 ms on
_BLINK_OFF_TIME: float = 0.05  # 50 ms off (tail — keeps total cycle short)


class GpioLed(LedBase):
    """Single-pin LED driven via gpiozero on Raspberry Pi."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._pin: int = int(self._config.get("gpio", "led", "pin", default=24))
        self._led = None

    def init(self) -> None:
        """Open the GPIO output pin."""
        try:
            from gpiozero import LED as GpioLED  # type: ignore[import]
            self._led = GpioLED(self._pin)
            logger.info("GpioLed initialized on GPIO%d", self._pin)
        except Exception as exc:
            logger.warning("GpioLed: failed to init GPIO%d: %s", self._pin, exc)

    def blink_once(self) -> None:
        """Flash the LED once non-blocking via gpiozero background thread."""
        if self._led is None:
            return
        try:
            # n=1 fires exactly one on/off cycle; background=True is the default.
            self._led.blink(on_time=_BLINK_ON_TIME, off_time=_BLINK_OFF_TIME, n=1)
        except Exception as exc:
            logger.warning("GpioLed blink_once failed: %s", exc)

    def set_enabled(self, on: bool) -> None:
        """Hold the LED on or off continuously."""
        if self._led is None:
            return
        try:
            if on:
                self._led.on()
            else:
                self._led.off()
        except Exception as exc:
            logger.warning("GpioLed set_enabled failed: %s", exc)

    def shutdown(self) -> None:
        """Turn off and release the GPIO pin."""
        if self._led is not None:
            try:
                self._led.off()
                self._led.close()
            except Exception:
                pass
            self._led = None
        logger.info("GpioLed shut down")
