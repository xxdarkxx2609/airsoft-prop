"""GPIO wire detection for Raspberry Pi.

Reads physical wires connected to GPIO pins via gpiozero.
Each wire has an external 10k pull-down resistor:
  - Wire inserted (connecting 3.3V to GPIO) = HIGH = intact
  - Wire pulled / cut = LOW (pull-down wins) = cut

Pin assignments are read from ``config/hardware.yaml`` under
``gpio.wires`` as a mapping of color name to BCM pin number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gpiozero import InputDevice as GpioInputDevice

from src.hal.base import WiresBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)


class GpioWires(WiresBase):
    """Read physical wire states via GPIO pins on Raspberry Pi.

    Uses ``gpiozero.InputDevice`` with ``pull_up=False`` because the
    hardware has external 10k pull-down resistors. Wire names and pin
    assignments are loaded from ``gpio.wires`` in hardware.yaml.
    """

    def __init__(self, config: Config) -> None:
        """Prepare pin configuration without touching GPIO yet.

        Args:
            config: Application configuration (reads ``gpio.wires``).
        """
        self._config = config
        self._devices: dict[str, GpioInputDevice] = {}
        pins_cfg = config.get("gpio", "wires", default={})
        self._pins: dict[str, int] = {
            name: int(pin) for name, pin in pins_cfg.items()
        }
        # Per-wire failure counter. Used to log only the first failure
        # of a burst (avoids log spam if a flaky joint produces hundreds
        # of bad reads per second). Resets on a successful read.
        self._read_failures: dict[str, int] = {}

    def init(self) -> None:
        """Initialize GPIO InputDevice for each wire."""
        for name, pin in self._pins.items():
            try:
                device = GpioInputDevice(pin, pull_up=False)
                self._devices[name] = device
                logger.debug("Wire '%s' on GPIO%d", name, pin)
            except Exception as exc:
                logger.warning(
                    "Failed to init wire '%s' on GPIO%d: %s", name, pin, exc,
                )
        logger.info(
            "GpioWires initialized: %s",
            {name: f"GPIO{self._pins[name]}" for name in self._devices},
        )

    def get_wire_states(self) -> dict[str, bool]:
        """Read the current state of all wires.

        On a hardware read error (e.g. flaky soldered joint, RPi.GPIO
        raising ``RuntimeError``), the wire is reported as cut (False)
        to preserve existing game-logic behavior, but the exception is
        logged once per failure burst so that diagnostics are visible
        in ``prop.log``. The counter resets the next time the wire
        reads cleanly.

        Returns:
            Dict mapping color name to boolean (True = intact, False = cut).
        """
        states: dict[str, bool] = {}
        for name in self._pins:
            device = self._devices.get(name)
            if device is None:
                states[name] = False
                continue
            try:
                states[name] = bool(device.value)
                if self._read_failures.get(name):
                    logger.info(
                        "Wire '%s' recovered after %d failed reads",
                        name,
                        self._read_failures[name],
                    )
                    self._read_failures[name] = 0
            except Exception as exc:
                count = self._read_failures.get(name, 0) + 1
                self._read_failures[name] = count
                if count == 1:
                    logger.warning(
                        "Wire '%s' GPIO read failed: %s: %s",
                        name,
                        type(exc).__name__,
                        exc,
                    )
                states[name] = False
        return states

    def all_wires_intact(self) -> bool:
        """Check whether all wires are currently intact.

        Returns:
            True if every wire reads HIGH.
        """
        return all(self.get_wire_states().values())

    def shutdown(self) -> None:
        """Close all GPIO devices."""
        for device in self._devices.values():
            try:
                device.close()
            except Exception:
                pass
        self._devices.clear()
        logger.info("GpioWires shut down")
