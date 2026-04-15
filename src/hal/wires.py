"""GPIO wire detection for Raspberry Pi.

Reads three physical wires connected to GPIO pins via gpiozero.
Each wire has an external 10k pull-down resistor:
  - Wire inserted (connecting 3.3V to GPIO) = HIGH = intact
  - Wire pulled / cut = LOW (pull-down wins) = cut

Pin assignments are read from ``config/hardware.yaml`` under
``gpio.wires``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gpiozero import InputDevice as GpioInputDevice

from src.hal.base import WiresBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

# Wire names matching the rest of the application and the mock.
WIRE_NAMES: tuple[str, ...] = ("defuse", "explode", "halve")


class GpioWires(WiresBase):
    """Read physical wire states via GPIO pins on Raspberry Pi.

    Uses ``gpiozero.InputDevice`` with ``pull_up=False`` because the
    hardware has external 10k pull-down resistors.
    """

    def __init__(self, config: Config) -> None:
        """Prepare pin configuration without touching GPIO yet.

        Args:
            config: Application configuration (reads ``gpio.wires.*``).
        """
        self._config = config
        self._devices: dict[str, GpioInputDevice] = {}
        self._pins: dict[str, int] = {
            "defuse": int(self._config.get("gpio", "wires", "wire_defuse", default=17)),
            "explode": int(self._config.get("gpio", "wires", "wire_explode", default=27)),
            "halve": int(self._config.get("gpio", "wires", "wire_halve", default=22)),
        }

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
        """Read the current state of all three wires.

        Returns:
            Dict with keys 'defuse', 'explode', 'halve' and boolean
            values (True = intact / HIGH, False = cut / LOW).
        """
        states: dict[str, bool] = {}
        for name in WIRE_NAMES:
            device = self._devices.get(name)
            if device is not None:
                try:
                    # value == 1 -> wire intact (HIGH), value == 0 -> wire cut (LOW)
                    states[name] = bool(device.value)
                except Exception:
                    states[name] = False
            else:
                states[name] = False
        return states

    def all_wires_intact(self) -> bool:
        """Check whether all three wires are currently intact.

        Returns:
            True if every wire reads HIGH.
        """
        return all(self.get_wire_states().values())

    def shutdown(self) -> None:
        """Close all GPIO devices."""
        for name, device in self._devices.items():
            try:
                device.close()
            except Exception:
                pass
        self._devices.clear()
        logger.info("GpioWires shut down")
