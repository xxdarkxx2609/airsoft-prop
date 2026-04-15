"""Base class and supporting types for all game modes.

Every game mode inherits from BaseMode and is auto-discovered
by the modes package __init__.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SetupOptionType(Enum):
    """Type of setup option for UI rendering."""

    RANGE = "range"      # Numeric value with min/max (e.g. timer, digits)
    CODE_INPUT = "code"  # Direct digit input (e.g. set code)


@dataclass
class SetupOption:
    """A configurable option shown in the setup screen before a game starts.

    Attributes:
        key: Internal key name used to store the value.
        label: Display label (max ~12 chars for LCD).
        option_type: How this option is rendered/edited in the UI.
        default: Default value.
        value: Current value (set during setup).
        min_val: Minimum value for RANGE type.
        max_val: Maximum value for RANGE type.
        step: Small step for left/right navigation.
        large_step: Large step for +/- keys.
    """

    key: str
    label: str
    option_type: SetupOptionType
    default: Any
    value: Any = None
    min_val: int = 0
    max_val: int = 9999
    step: int = 1
    large_step: int = 10

    def __post_init__(self) -> None:
        """Set value to default if not explicitly provided."""
        if self.value is None:
            self.value = self.default


@dataclass
class GameContext:
    """Runtime context passed to mode during gameplay.

    Attributes:
        timer_seconds: Total timer duration in seconds.
        remaining_seconds: Current remaining seconds.
        setup_values: Values from setup screen keyed by option key.
        wire_roles: Wire name to role mapping for cut-the-wire mode.
        custom_data: Arbitrary mode-specific runtime data.
    """

    timer_seconds: int
    remaining_seconds: int
    setup_values: dict[str, Any] = field(default_factory=dict)
    wire_roles: dict[str, str] = field(default_factory=dict)
    custom_data: dict[str, Any] = field(default_factory=dict)


class ModeResult(Enum):
    """Result of a mode tick or input handler."""

    CONTINUE = "continue"    # Game continues normally
    DEFUSED = "defused"      # Device was successfully defused
    DETONATED = "detonated"  # Device detonated


class PlantingType(Enum):
    """How the device must be planted before arming."""

    INSTANT = "instant"        # Immediate arming (legacy behaviour)
    CODE_ENTRY = "code_entry"  # Player must enter a code to plant
    TIMED = "timed"            # Player must hold Enter for a duration


@dataclass
class PlantingConfig:
    """Configuration for the planting phase of a mode.

    Attributes:
        planting_type: The planting mechanic to use.
        duration: Seconds the player must hold Enter (TIMED only).
        code_length: Digit count for the planting code (CODE_ENTRY only).
                     0 means derive from the mode's setup options.
    """

    planting_type: PlantingType = PlantingType.INSTANT
    duration: int = 0
    code_length: int = 0


# Tolerance for key-hold detection: if no Enter event arrives within
# this many seconds, the key is considered released.  Must exceed the
# OS key-repeat initial delay (~500 ms on most systems).
HOLD_TIMEOUT: float = 0.6


class BaseMode(ABC):
    """Abstract base class for all game modes.

    Each game mode is a plugin that inherits from this class.
    Modes are auto-discovered from the src/modes/ package.

    Subclasses must define the class attributes ``name``, ``description``,
    and ``menu_key`` and implement all abstract methods.
    """

    # Subclasses must define these class attributes
    name: str = ""
    description: str = ""
    menu_key: str = ""  # Key to select in menu ("1", "2", "3", ...)

    def get_planting_config(self) -> PlantingConfig:
        """Return the planting configuration for this mode.

        Override in subclasses to require code entry or timed planting.
        The default is instant arming (no planting phase).

        Returns:
            PlantingConfig describing the planting mechanic.
        """
        return PlantingConfig()

    @abstractmethod
    def get_setup_options(self) -> list[SetupOption]:
        """Return the list of configurable options for this mode.

        Returns:
            List of SetupOption instances that the setup screen will present.
        """

    @abstractmethod
    def on_armed(self, context: GameContext) -> None:
        """Called once when the device is armed and the game starts.

        Use this to initialise mode-specific state such as generating
        codes, assigning wire roles, etc.

        Args:
            context: The game context for this round.
        """

    @abstractmethod
    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """Handle a key press during gameplay.

        Args:
            key: The pressed key string (e.g. '0'-'9', 'backspace', 'enter').
            context: The current game context.

        Returns:
            ModeResult indicating if the game continues, device defused, or detonated.
        """

    @abstractmethod
    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        """Called every second while the device is armed.

        Can be used for wire checking or other periodic logic.

        Args:
            remaining_seconds: Seconds left on the timer.
            context: The current game context.

        Returns:
            ModeResult indicating the current game state.
        """

    @abstractmethod
    def render(self, display: Any, remaining_seconds: int, context: GameContext) -> None:
        """Render the mode-specific content on the display.

        Lines 1-2 are typically timer info. Lines 3-4 are mode content.

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """

    @abstractmethod
    def render_last_10s(self, display: Any, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Timer is shown on line 1 as ``!! MM:SS !! ARMED !!``.
        Lines 2-4 are mode-specific.

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
