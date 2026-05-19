"""Tests for src.modes.cut_the_wire — role assignment, defuse, penalty, tamper."""

from src.hal.wires_mock import MockWires
from src.modes.base_mode import GameContext, ModeResult
from src.modes.cut_the_wire import CutTheWireMode


def _armed_context(
    defuse: str = "Green",
    detonate: str = "Red",
    penalty_base: float = 60.0,
    penalty_mult: float = 2.0,
) -> tuple[CutTheWireMode, GameContext, MockWires]:
    """Build a mode with deterministic wire roles via GM config."""
    mode = CutTheWireMode()
    wires = MockWires()
    wires.init()
    ctx = GameContext(timer_seconds=300, remaining_seconds=300)
    ctx.custom_data["wires"] = wires
    ctx.custom_data["cut_wire_defuse"] = defuse
    ctx.custom_data["cut_wire_detonate"] = detonate
    ctx.custom_data["cut_wire_penalty_base"] = penalty_base
    ctx.custom_data["cut_wire_penalty_multiplier"] = penalty_mult
    mode.on_armed(ctx)
    return mode, ctx, wires


class TestValidateCanStart:
    """``validate_can_start`` blocks if any configured wire is disconnected."""

    def test_returns_none_when_all_wires_intact(self) -> None:
        mode = CutTheWireMode()
        wires = MockWires()
        wires.init()
        ctx = GameContext(timer_seconds=300, remaining_seconds=300)
        ctx.custom_data["wires"] = wires
        assert mode.validate_can_start(ctx) is None

    def test_returns_error_when_a_wire_is_cut(self) -> None:
        mode = CutTheWireMode()
        wires = MockWires()
        wires.init()
        wires.cut_wire("Green")
        ctx = GameContext(timer_seconds=300, remaining_seconds=300)
        ctx.custom_data["wires"] = wires
        result = mode.validate_can_start(ctx)
        assert result is not None
        assert "Disconnected wires" in result


class TestOnTickResults:
    """Cutting each role triggers the right ModeResult."""

    def test_cutting_defuse_wire_returns_defused(self) -> None:
        mode, ctx, wires = _armed_context(defuse="Green", detonate="Red")
        wires.cut_wire("Green")
        assert mode.on_tick(300, ctx) is ModeResult.DEFUSED

    def test_cutting_detonate_wire_returns_detonated(self) -> None:
        mode, ctx, wires = _armed_context(defuse="Green", detonate="Red")
        wires.cut_wire("Red")
        assert mode.on_tick(300, ctx) is ModeResult.DETONATED

    def test_cutting_two_wires_in_one_tick_returns_detonated(self) -> None:
        """The tamper guard: ripping multiple wires at once detonates."""
        mode, ctx, wires = _armed_context(defuse="Green", detonate="Red")
        wires.cut_wire("Green")
        wires.cut_wire("Blue")  # also cut in the same tick
        assert mode.on_tick(300, ctx) is ModeResult.DETONATED


class TestPenaltyEscalation:
    """Each successive penalty cut multiplies the base by the multiplier."""

    def test_first_penalty_uses_base_seconds(self) -> None:
        mode, ctx, wires = _armed_context(
            defuse="Green", detonate="Red", penalty_base=30, penalty_mult=2
        )
        # Cut a penalty wire (any wire that isn't Green or Red).
        wires.cut_wire("Blue")
        result = mode.on_tick(300, ctx)
        assert result is ModeResult.CONTINUE
        assert ctx.remaining_seconds == 270
        assert ctx.custom_data["penalty_count"] == 1

    def test_second_penalty_doubles_with_multiplier_two(self) -> None:
        mode, ctx, wires = _armed_context(
            defuse="Green", detonate="Red", penalty_base=30, penalty_mult=2
        )
        wires.cut_wire("Blue")
        mode.on_tick(300, ctx)  # -30 → 270
        wires.cut_wire("White")
        mode.on_tick(ctx.remaining_seconds, ctx)  # -60 → 210
        assert ctx.remaining_seconds == 210
        assert ctx.custom_data["penalty_count"] == 2
