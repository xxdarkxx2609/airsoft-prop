"""Cut the Wire game mode.

Five coloured wires (Green, Blue, White, Yellow, Red) are physically
connected via GPIO. Roles are randomly assigned each round unless the
game master pre-configured specific colours in the web interface:

  - **Defuse**: pulling this wire defuses the device.
  - **Detonate**: pulling this wire detonates the device immediately.
  - **Penalty** (×3): pulling these wires subtracts an escalating amount
    of time. First penalty = base_seconds, each subsequent cut multiplies
    by penalty_multiplier.

The LCD optionally shows a GM-configured hint on the bottom line.
"""

import random
from typing import Any

from src.modes.base_mode import (
    BaseMode,
    GameContext,
    ModeResult,
    PlantingConfig,
    PlantingType,
    SetupOption,
    SetupOptionType,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Wire colours in display order — must match hardware.yaml gpio.wires order
WIRE_COLORS: tuple[str, ...] = ("Green", "Blue", "White", "Yellow", "Red")

# Single-character initials for LCD display
_COLOR_INITIAL: dict[str, str] = {
    "Green": "G",
    "Blue": "B",
    "White": "W",
    "Yellow": "Y",
    "Red": "R",
}

_DEFAULT_PENALTY_BASE: float = 60.0
_DEFAULT_PENALTY_MULTIPLIER: float = 2.0
_DEFAULT_PLANTING_DURATION: int = 10  # seconds to hold Enter


def _format_timer(seconds: int) -> str:
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def _center(text: str, width: int = 20) -> str:
    return text.center(width)


def _build_wire_row(wire_states: dict[str, bool]) -> str:
    """Build LCD wire status string.

    Each intact wire shows its colour initial, each cut wire shows a
    space.  Format: ``[G][B][ ][ ][R]`` — 19 chars for 5 wires.

    Args:
        wire_states: Mapping of colour name to intact state.

    Returns:
        19-character wire status string.
    """
    parts: list[str] = []
    for color in WIRE_COLORS:
        if color not in wire_states:
            continue
        initial = _COLOR_INITIAL.get(color, color[0]) if wire_states[color] else " "
        parts.append(f"[{initial}]")
    return "".join(parts)


class CutTheWireMode(BaseMode):
    """Cut the Wire: pull the right wire before time runs out.

    Setup options:
        - timer: game duration in seconds (30–5999).

    Config (web interface, default.yaml → modes.cut_the_wire):
        - penalty_base_seconds: time lost on first wrong cut
        - penalty_multiplier: multiplier for each subsequent wrong cut
        - hint: optional GM message shown on LCD line 3 (max 20 chars)
        - defuse_wire: colour pre-assigned as defuse (empty = random)
        - detonate_wire: colour pre-assigned as detonate (empty = random)
    """

    name: str = "Cut the Wire"
    description: str = "Pull the right wire to defuse"
    menu_key: str = "4"

    def get_planting_config(self) -> PlantingConfig:
        """Require holding Enter for the configured duration to plant."""
        return PlantingConfig(
            planting_type=PlantingType.TIMED,
            duration=_DEFAULT_PLANTING_DURATION,
        )

    def get_setup_options(self) -> list[SetupOption]:
        """Return setup options for the LCD setup screen."""
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
        """Assign wire roles and record initial states.

        Reads GM-configured wire assignments from custom_data (injected by
        setup_screen / tournament_screen from the config). Falls back to
        random assignment if values are absent or invalid.

        Args:
            context: The game context for this round.
        """
        wires = context.custom_data.get("wires")
        if wires is not None:
            wire_names = list(wires.get_wire_states().keys())
            initial_states = wires.get_wire_states()
        else:
            logger.warning("CutTheWire: no wires HAL — using defaults")
            wire_names = list(WIRE_COLORS)
            initial_states = {name: True for name in wire_names}

        # Resolve GM-configured role assignments
        gm_defuse: str = context.custom_data.get("cut_wire_defuse", "")
        gm_detonate: str = context.custom_data.get("cut_wire_detonate", "")

        if (
            gm_defuse in wire_names
            and gm_detonate in wire_names
            and gm_defuse != gm_detonate
        ):
            defuse_wire = gm_defuse
            detonate_wire = gm_detonate
        else:
            if gm_defuse or gm_detonate:
                logger.warning(
                    "CutTheWire: invalid GM wire config (defuse=%r, detonate=%r) — randomising",
                    gm_defuse,
                    gm_detonate,
                )
            pool = list(wire_names)
            random.shuffle(pool)
            defuse_wire = pool[0]
            detonate_wire = pool[1]

        roles: dict[str, str] = {}
        for name in wire_names:
            if name == defuse_wire:
                roles[name] = "defuse"
            elif name == detonate_wire:
                roles[name] = "detonate"
            else:
                roles[name] = "penalty"

        context.wire_roles.update(roles)
        context.custom_data["previous_states"] = dict(initial_states)
        context.custom_data["penalty_count"] = 0
        context.custom_data["wire_names"] = wire_names

        logger.info("CutTheWire roles: %s", roles)

    def on_input(self, key: str, context: GameContext) -> ModeResult:
        """No key input used — wire cutting is detected in on_tick."""
        return ModeResult.CONTINUE

    def on_tick(self, remaining_seconds: int, context: GameContext) -> ModeResult:
        """Poll wire states and react to newly cut wires.

        Args:
            remaining_seconds: Seconds left on the timer.
            context: The current game context.

        Returns:
            DEFUSED, DETONATED, or CONTINUE.
        """
        wires = context.custom_data.get("wires")
        if wires is None:
            return ModeResult.CONTINUE

        current_states: dict[str, bool] = wires.get_wire_states()
        previous_states: dict[str, bool] = context.custom_data["previous_states"]

        for name in context.custom_data.get("wire_names", []):
            was_intact = previous_states.get(name, True)
            is_intact = current_states.get(name, True)

            if was_intact and not is_intact:
                role: str = context.wire_roles.get(name, "")
                logger.info("CutTheWire: wire '%s' cut — role: %s", name, role)

                if role == "defuse":
                    context.custom_data["previous_states"] = dict(current_states)
                    return ModeResult.DEFUSED

                if role == "detonate":
                    context.custom_data["previous_states"] = dict(current_states)
                    return ModeResult.DETONATED

                if role == "penalty":
                    penalty_count: int = context.custom_data.get("penalty_count", 0)
                    base: float = context.custom_data.get(
                        "cut_wire_penalty_base", _DEFAULT_PENALTY_BASE
                    )
                    multiplier: float = context.custom_data.get(
                        "cut_wire_penalty_multiplier", _DEFAULT_PENALTY_MULTIPLIER
                    )
                    penalty = int(base * (multiplier ** penalty_count))
                    new_remaining = max(0, remaining_seconds - penalty)
                    logger.info(
                        "CutTheWire: penalty wire — -%ds (count=%d), %d->%d",
                        penalty,
                        penalty_count,
                        remaining_seconds,
                        new_remaining,
                    )
                    context.remaining_seconds = new_remaining
                    context.custom_data["penalty_count"] = penalty_count + 1
                    if new_remaining == 0:
                        context.custom_data["previous_states"] = dict(current_states)
                        return ModeResult.DETONATED

        context.custom_data["previous_states"] = dict(current_states)
        return ModeResult.CONTINUE

    def _get_wire_states_for_display(self, context: GameContext) -> dict[str, bool]:
        wires = context.custom_data.get("wires")
        if wires is not None:
            return wires.get_wire_states()
        return context.custom_data.get(
            "previous_states",
            {name: True for name in WIRE_COLORS},
        )

    def render(self, display: Any, remaining_seconds: int, context: GameContext) -> None:
        """Render the armed screen.

        Layout::

            ** {device_name} ARMED **
                  05:00
            [G][B][W][Y][R]
            <hint or blank>

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        dn = context.custom_data.get("device_name", "Prop").upper()
        wire_states = self._get_wire_states_for_display(context)
        hint: str = context.custom_data.get("cut_wire_hint", "")

        display.write_line(0, _center(f"** {dn} ARMED **"))
        display.write_line(1, _center(_format_timer(remaining_seconds)))
        display.write_line(2, _center(_build_wire_row(wire_states)))
        display.write_line(3, _center(hint))

    def render_last_10s(self, display: Any, remaining_seconds: int, context: GameContext) -> None:
        """Render during the last 10 seconds.

        Line 0 is handled by the armed screen (``!! MM:SS !! ARMED !!``).

        Args:
            display: A DisplayBase instance.
            remaining_seconds: Seconds left on the timer.
            context: The current game context.
        """
        wire_states = self._get_wire_states_for_display(context)
        hint: str = context.custom_data.get("cut_wire_hint", "")

        display.write_line(1, _center("CUT A WIRE!!"))
        display.write_line(2, _center(_build_wire_row(wire_states)))
        display.write_line(3, _center(hint))
