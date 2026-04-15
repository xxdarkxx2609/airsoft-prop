"""Mock wires implementation for desktop testing.

Simulates three GPIO wires (defuse, explode, halve) with software-togglable
states. All wires start as intact (True). States can be changed via the
``cut_wire()`` and ``reset_wire()`` methods.
"""

from src.hal.base import WiresBase
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Valid wire names matching the GPIO wire configuration
WIRE_NAMES: tuple[str, ...] = ("defuse", "explode", "halve")


class MockWires(WiresBase):
    """Software-simulated wires for desktop testing.

    Three wires (defuse, explode, halve) are maintained in an internal
    dictionary.  True means the wire is intact (inserted), False means
    the wire has been cut (pulled).

    State can be changed programmatically via ``cut_wire()``,
    ``reset_wire()``, and ``toggle_wire()`` for integration testing or
    manual desktop use.
    """

    def __init__(self) -> None:
        """Initialize all wires as intact."""
        self._states: dict[str, bool] = {
            "defuse": True,
            "explode": True,
            "halve": True,
        }

    def init(self) -> None:
        """Initialize the mock wire detection system."""
        logger.info(
            "MockWires initialized: %s",
            {k: "intact" for k in self._states},
        )

    def get_wire_states(self) -> dict[str, bool]:
        """Return the current state of all three wires.

        Returns:
            Dict with keys 'defuse', 'explode', 'halve' and boolean
            values (True = intact, False = cut).
        """
        return dict(self._states)

    def all_wires_intact(self) -> bool:
        """Check whether all three wires are currently intact.

        Returns:
            True if every wire is intact.
        """
        return all(self._states.values())

    def shutdown(self) -> None:
        """Clean up mock wires (reset to intact)."""
        self._states = {name: True for name in WIRE_NAMES}
        logger.info("MockWires shut down (all wires reset to intact)")

    # ------------------------------------------------------------------
    # Mock-specific control methods
    # ------------------------------------------------------------------

    def cut_wire(self, name: str) -> None:
        """Simulate cutting (pulling) a wire.

        Args:
            name: Wire name ('defuse', 'explode', or 'halve').

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
            name: Wire name ('defuse', 'explode', or 'halve').

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
            name: Wire name ('defuse', 'explode', or 'halve').

        Raises:
            ValueError: If the wire name is invalid.
        """
        self._validate_name(name)
        self._states[name] = not self._states[name]
        state_label = "intact" if self._states[name] else "cut"
        logger.info("MockWires: wire '%s' toggled -> %s", name, state_label)

    def reset_all(self) -> None:
        """Reset all wires to the intact state."""
        self._states = {name: True for name in WIRE_NAMES}
        logger.info("MockWires: all wires reset to intact")

    @staticmethod
    def _validate_name(name: str) -> None:
        """Validate that a wire name is one of the known wires.

        Args:
            name: Wire name to validate.

        Raises:
            ValueError: If the name is not in WIRE_NAMES.
        """
        if name not in WIRE_NAMES:
            raise ValueError(
                f"Unknown wire name '{name}'. "
                f"Valid names: {', '.join(WIRE_NAMES)}"
            )
