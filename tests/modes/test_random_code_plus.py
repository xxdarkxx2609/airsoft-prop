"""Tests for src.modes.random_code_plus — digit-by-digit verification + penalty."""

from src.modes.base_mode import GameContext, ModeResult
from src.modes.random_code_plus import RandomCodePlusMode


def _armed_context(
    code: str = "1234", remaining: int = 100, penalty: int = 10
) -> tuple[RandomCodePlusMode, GameContext]:
    mode = RandomCodePlusMode()
    ctx = GameContext(timer_seconds=300, remaining_seconds=remaining)
    ctx.setup_values["digits"] = len(code)
    mode.on_armed(ctx)
    # Override the randomly generated code with a known value.
    ctx.custom_data["code"] = code
    ctx.custom_data["input"] = ""
    ctx.custom_data["penalty_seconds"] = penalty
    return mode, ctx


class TestMenuKey:
    """Plus modes have their own menu_keys distinct from the base modes."""

    def test_menu_key_is_four(self) -> None:
        assert RandomCodePlusMode.menu_key == "4"


class TestCorrectInput:
    """Each correct digit is appended; a full match defuses."""

    def test_all_correct_digits_returns_defused(self) -> None:
        mode, ctx = _armed_context(code="1234")
        result: ModeResult = ModeResult.CONTINUE
        for digit in "1234":
            result = mode.on_input(digit, ctx)
        assert result is ModeResult.DEFUSED
        assert ctx.custom_data["input"] == "1234"


class TestWrongDigitPenalty:
    """A wrong digit subtracts ``penalty_seconds`` from remaining_seconds."""

    def test_wrong_first_digit_applies_penalty(self) -> None:
        mode, ctx = _armed_context(code="1234", remaining=100, penalty=10)
        mode.on_input("9", ctx)  # wrong at position 0
        assert ctx.remaining_seconds == 90
        # Wrong digit is rejected — input stays empty.
        assert ctx.custom_data["input"] == ""

    def test_wrong_digit_when_timer_runs_out_returns_detonated(self) -> None:
        mode, ctx = _armed_context(code="1234", remaining=5, penalty=10)
        result = mode.on_input("9", ctx)
        assert result is ModeResult.DETONATED
        assert ctx.remaining_seconds == 0


class TestBackspaceIgnored:
    """Plus mode has no backspace — confirmed digits stay locked in."""

    def test_backspace_does_not_pop_input(self) -> None:
        mode, ctx = _armed_context(code="1234")
        mode.on_input("1", ctx)
        mode.on_input("2", ctx)
        assert ctx.custom_data["input"] == "12"
        mode.on_input("backspace", ctx)
        assert ctx.custom_data["input"] == "12"
