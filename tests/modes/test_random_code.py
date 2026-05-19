"""Tests for src.modes.random_code — random code generation + matching.

Note: timer expiry → DETONATED is NOT handled in this mode's ``on_tick``
(which always returns CONTINUE). The armed screen drives that transition.
Tested in Phase E.
"""

from src.modes.base_mode import (
    GameContext,
    ModeResult,
    PlantingType,
    SetupOptionType,
)
from src.modes.random_code import RandomCodeMode


def _armed_context(mode: RandomCodeMode, digits: int = 6) -> GameContext:
    """Build an armed GameContext for the given mode + digit count."""
    ctx = GameContext(timer_seconds=300, remaining_seconds=300)
    ctx.setup_values["digits"] = digits
    mode.on_armed(ctx)
    return ctx


class TestSetup:
    """Setup options and planting configuration."""

    def test_setup_options_are_timer_and_digits(self) -> None:
        opts = RandomCodeMode().get_setup_options()
        keys = [o.key for o in opts]
        assert keys == ["timer", "digits"]
        timer = next(o for o in opts if o.key == "timer")
        digits = next(o for o in opts if o.key == "digits")
        assert timer.option_type is SetupOptionType.RANGE
        assert timer.min_val == 30 and timer.max_val == 5999
        assert digits.min_val == 4 and digits.max_val == 20

    def test_planting_config_is_code_entry(self) -> None:
        cfg = RandomCodeMode().get_planting_config()
        assert cfg.planting_type is PlantingType.CODE_ENTRY


class TestOnArmed:
    """``on_armed`` populates ``custom_data['code']`` with the right length."""

    def test_generated_code_length_matches_digits_setting(self) -> None:
        mode = RandomCodeMode()
        for digits in (4, 6, 10, 20):
            ctx = _armed_context(mode, digits=digits)
            code = ctx.custom_data["code"]
            assert len(code) == digits
            assert code.isdigit()


class TestOnInput:
    """Defuse logic: correct full input wins, wrong input clears."""

    def test_correct_full_code_returns_defused(self) -> None:
        mode = RandomCodeMode()
        ctx = _armed_context(mode, digits=4)
        code = ctx.custom_data["code"]

        result: ModeResult = ModeResult.CONTINUE
        for digit in code:
            result = mode.on_input(digit, ctx)
        assert result is ModeResult.DEFUSED

    def test_wrong_code_clears_input_and_continues(self) -> None:
        mode = RandomCodeMode()
        ctx = _armed_context(mode, digits=4)
        # Replace the generated code so we know what's wrong.
        ctx.custom_data["code"] = "1234"

        # Type four wrong digits → input fills, gets checked, clears.
        for digit in "9999":
            result = mode.on_input(digit, ctx)
        assert result is ModeResult.CONTINUE
        assert ctx.custom_data["input"] == ""

    def test_backspace_removes_last_digit(self) -> None:
        mode = RandomCodeMode()
        ctx = _armed_context(mode, digits=6)
        mode.on_input("1", ctx)
        mode.on_input("2", ctx)
        mode.on_input("backspace", ctx)
        assert ctx.custom_data["input"] == "1"
