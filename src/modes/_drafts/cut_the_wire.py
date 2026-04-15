"""Cut the Wire game mode.

Three coloured wires (Red, Blue, Green) are physically connected via GPIO.
Each wire is randomly assigned one of three roles:
  - **Defuse**: cutting this wire defuses the device.
  - **Explode**: cutting this wire detonates the device immediately.
  - **Halve**: cutting this wire halves the remaining time.

The player must decide which wire to cut based on intel or luck.
"""

import random

from src.modes.base_mode import (
    BaseMode,
    GameContext,
    ModeResult,
    SetupOption,
    SetupOptionType,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Physical wire names matching the HAL get_wire_states() keys
WIRE_NAMES: list[str] = ["defuse", "explode", "halve"]

# Display labels for the three wires (Red, Blue, Green)
WIRE_LABELS: list[str] = ["R", "B", "G"]

# Roles that are randomly shuffled and assigned to wires
WIRE_ROLES: list[str] = ["defuse", "explode", "halve"]


def _format_timer(seconds: int) -> str:
    """Format seconds as MM:SS string.

    Args:
        seconds: Time in seconds (0-5999).

    Returns:
        Formatted timer string, e.g. '05:00'.
    """
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _center(text: str, width: int = 20) -> str:
    """Center text within the given width.

    Args:
        text: Text to center.
        width: Total width (default 20 for LCD).

    Returns:
        Centered string padded to width.
    """
    return text.center(width)


def _build_wire_status(wire_states: dict[str, bool]) -> str:
    """Build the wire status display string.

    Each wire is shown as ``[x]`` (intact) or ``[ ]`` (cut).
    The order follows WIRE_NAMES: defuse, explode, halve.

    Args:
        wire_states: Dict mapping wire names to boolean states
                     (True=intact, False=cut).

    Returns:
        Formatted status string, e.g. '[x] [ ] [x]'.
    """
    parts: list[str] = []
    for wire_name in WIRE_NAMES:
        intact = wire_states.get(wire_name, False)
        parts.append("[x]" if intact else "[ ]")
    return " ".join(parts)


class CutTheWireMode(BaseMode):
    """Cut the Wire mode: pull the correct physical cable to defuse.

    Setup options:
        - Timer: duration in seconds (30-5999).

    The mode requires access to the WiresBase HAL for reading GPIO states.
    A reference must be passed via ``context.custom_data['wires']`` before
    ``on_armed`` is called.
    """

    name: str = "Cut the Wire"
    description: str = "Pull the right wire to defuse"
    menu_key: str = "3"

    def get_setup_options(self) -> list[SetupOption]:
        """Return the timer setup option.

        Returns:
            List containing the timer option.
        """
        return [
            SetupOption(
                key="timer",
                label="Timer",
                option_type=SetupOptionType.RANGE,
                default=300,
                min_val=30,
                max_val=5999,
                step=30,
                large_step=300,
            ),
        ]

    def on_armed(self, context: GameContext) -> None:
        """Randomly assign roles to wires and record initial states.

        The three roles (defuse, explode, halve) are shuffled and mapped
        to the three physical wires. Initial wire states are read from
        the HAL and stored so that changes can be detected on each tick.

        Requires ``context.custom_data['wires']`` to be set to a
        WiresBase instance before this method is called.

        Args:
            context: The game context for this round.
        """
        # Shuffle roles and assign to wire names
        roles = list(WIRE_ROLES)
        random.shuffle(roles)
        for wire_name, role in zip(WIRE_NAMES, roles):
            context.wire_roles[wire_name] = role
        logger.info(
            "Wire roles assigned: %s",
            {name: role for name, role in zip(WIRE_NAMES, roles)},
        )

        # Read initial wire states from HAL
        wires = context.custom_data.get("wires")
        if wires is not None:
            initial_states = wires.get_wire_states()
        else:
            # Fallback: assume all intact if no HAL available
            logger.warning("No wires HAL provided - assuming all wires intact")
            initial_states = {name: True for name in WIRE_NAMES}

        context.custom_data["previous_states"] = dict(initial_states)
        context.custom_data["halve_triggered"] = False

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """No key input is used in this mode.

        Wire cutting is detected via GPIO polling in on_tick.

        Args:
            key: The pressed key string (ignored).
            context: The current game context.

        Returns:
            Always CONTINUE.
        """
        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        """Poll wire states and react to newly cut wires.

        Compares current GPIO states with the previously recorded states.
        If a wire transitions from intact (True) to cut (False), its
        assigned role determines the outcome:
          - defuse: returns DEFUSED
          - explode: returns DETONATED
          - halve: halves remaining time (once only)

        Args:
            remaining_seconds: Seconds left on the timer.
            context: The current game context.

        Returns:
            ModeResult based on wire actions or CONTINUE if nothing changed.
        """
        wires = context.custom_data.get("wires")
        if wires is None:
            return ModeResult.CONTINUE

        current_states: dict[str, bool] = wires.get_wire_states()
        previous_states: dict[str, bool] = context.custom_data["previous_states"]

        for wire_name in WIRE_NAMES:
            was_intact = previous_states.get(wire_name, True)
            is_intact = current_states.get(wire_name, True)

            # Detect transition from intact to cut
            if was_intact and not is_intact:
                role: str = context.wire_roles.get(wire_name, "")
                logger.info(
                    "Wire '%s' cut - role: %s", wire_name, role
                )

                if role == "defuse":
                    context.custom_data["previous_states"] = dict(current_states)
                    return ModeResult.DEFUSED

                if role == "explode":
                    context.custom_data["previous_states"] = dict(current_states)
                    return ModeResult.DETONATED

                if role == "halve":
                    if not context.custom_data.get("halve_triggered", False):
                        context.remaining_seconds = remaining_seconds // 2
                        context.custom_data["halve_triggered"] = True
                        logger.info(
                            "Time halved: %d -> %d seconds",
                            remaining_seconds,
                            context.remaining_seconds,
                        )

        # Update stored states for next tick
        context.custom_data["previous_states"] = dict(current_states)
        return ModeResult.CONTINUE

    def _get_wire_states_for_display(self, context: GameContext) -> dict[str, bool]:
        """Get current wire states, preferring live HAL data.

        Args:
            context: The current game context.

        Returns:
            Dict mapping wire names to boolean states.
        """
        wires = context.custom_data.get("wires")
        if wires is not None:
            return wires.get_wire_states()
        # Fall back to last known states
        return context.custom_data.get(
            "previous_states",
            {name: True for name in WIRE_NAMES},
        )

    def render(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render the armed screen with wire statuses.

        Layout:
            Line 1: ** {device_name} ARMED **
            Line 2: Timer MM:SS (centered)
            Line 3: 'Wires:  R  B  G'
            Line 4: '[x] [x] [x]' (intact/cut indicators)

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        wire_states = self._get_wire_states_for_display(context)
        status_str = _build_wire_status(wire_states)
        dn = context.custom_data.get("device_name", "Prop").upper()

        display.write_line(0, _center(f"** {dn} ARMED **"))
        display.write_line(1, _center(_format_timer(remaining_seconds)))
        display.write_line(2, _center("Wires:  R  B  G"))
        display.write_line(3, _center(status_str))

    def render_last_10s(self, display: object, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Line 1 is handled by the armed screen (!! MM:SS !! ARMED !!).
        Line 2: 'CUT A WIRE!!'
        Line 3: 'Wires:  R  B  G'
        Line 4: wire status indicators

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        wire_states = self._get_wire_states_for_display(context)
        status_str = _build_wire_status(wire_states)

        display.write_line(1, _center("CUT A WIRE!!"))
        display.write_line(2, _center("Wires:  R  B  G"))
        display.write_line(3, _center(status_str))
