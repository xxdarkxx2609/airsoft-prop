"""Mock wires implementation for desktop testing.

Simulates GPIO wires with software-togglable states. Wire names and
their initial (intact) states are loaded from ``gpio.wires`` in
hardware.yaml, matching the GpioWires implementation exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.hal.base import WiresBase
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.utils.config import Config

logger = get_logger(__name__)

_DEFAULT_WIRE_NAMES: tuple[str, ...] = ("Green", "Blue", "White", "Yellow", "Red")


class MockWires(WiresBase):
    """Software-simulated wires for desktop testing.

    Wire names are loaded from hardware config. All wires start intact
    (True). States can be changed via ``cut_wire()``, ``reset_wire()``,
    and ``toggle_wire()`` for integration testing.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize all wires as intact.

        Args:
            config: Application configuration. If None, uses default names.
        """
        if config is not None:
            pins_cfg = config.get("gpio", "wires", default={})
            names = list(pins_cfg.keys()) if pins_cfg else list(_DEFAULT_WIRE_NAMES)
        else:
            names = list(_DEFAULT_WIRE_NAMES)
        self._wire_names: tuple[str, ...] = tuple(names)
        self._states: dict[str, bool] = {name: True for name in self._wire_names}

    def init(self) -> None:
        """Initialize the mock wire detection system."""
        logger.info(
            "MockWires initialized: %s",
            {k: "intact" for k in self._states},
        )

    def get_wire_states(self) -> dict[str, bool]:
        """Return the current state of all wires.

        Returns:
            Dict mapping color name to boolean (True = intact, False = cut).
        """
        return dict(self._states)

    def all_wires_intact(self) -> bool:
        """Check whether all wires are currently intact.

        Returns:
            True if every wire is intact.
        """
        return all(self._states.values())

    def shutdown(self) -> None:
        """Clean up mock wires (reset to intact)."""
        self._states = {name: True for name in self._wire_names}
        logger.info("MockWires shut down (all wires reset to intact)")

    # ------------------------------------------------------------------
    # Mock-specific control methods
    # ------------------------------------------------------------------

    def cut_wire(self, name: str) -> None:
        """Simulate cutting (pulling) a wire.

        Args:
            name: Wire color name.

        Raises:
            ValueError: If the wire name is invalid.
        """
        self._validate_name(name)
        if self._states[name]:
            self._states[name] = False
            logger.info("MockWires: wire '%s' CUT", name)
        else:
            logger.warning("MockWires: wire '%s' already cut", name)

    def reset_wire(self, name: str) -> None:
        """Reset a wire back to the intact state.

        Args:
            name: Wire color name.

        Raises:
            ValueError: If the wire name is invalid.
        """
        self._validate_name(name)
        if not self._states[name]:
            self._states[name] = True
            logger.info("MockWires: wire '%s' RESET to intact", name)
        else:
            logger.warning("MockWires: wire '%s' already intact", name)

    def toggle_wire(self, name: str) -> None:
        """Toggle a wire between intact and cut.

        Args:
            name: Wire color name.

        Raises:
            ValueError: If the wire name is invalid.
        """
        self._validate_name(name)
        self._states[name] = not self._states[name]
        state_label = "intact" if self._states[name] else "cut"
        logger.info("MockWires: wire '%s' toggled -> %s", name, state_label)

    def reset_all(self) -> None:
        """Reset all wires to the intact state."""
        self._states = {name: True for name in self._wire_names}
        logger.info("MockWires: all wires reset to intact")

    def _validate_name(self, name: str) -> None:
        """Validate that a wire name is known.

        Args:
            name: Wire name to validate.

        Raises:
            ValueError: If the name is not in the known wires.
        """
        if name not in self._states:
            raise ValueError(
                f"Unknown wire name '{name}'. "
                f"Valid names: {', '.join(self._wire_names)}"
            )
