"""Tests for src.modes.set_code_plus — digit-by-digit on a hidden secret."""

from src.modes.base_mode import GameContext, ModeResult
from src.modes.set_code_plus import SetCodePlusMode


def _armed_context(
    secret: str = "1234", remaining: int = 100, penalty: int = 10
) -> tuple[SetCodePlusMode, GameContext]:
    mode = SetCodePlusMode()
    ctx = GameContext(timer_seconds=300, remaining_seconds=remaining)
    ctx.setup_values["code"] = secret
    mode.on_armed(ctx)
    ctx.custom_data["penalty_seconds"] = penalty
    return mode, ctx


class TestMenuKey:
    """SetCodePlus has its own menu_key separate from SetCode."""

    def test_menu_key_is_five(self) -> None:
        assert SetCodePlusMode.menu_key == "5"


class TestCorrectInput:
    """Walking through the full correct secret defuses."""

    def test_full_correct_secret_defuses(self) -> None:
        mode, ctx = _armed_context(secret="7777")
        result: ModeResult = ModeResult.CONTINUE
        for digit in "7777":
            result = mode.on_input(digit, ctx)
        assert result is ModeResult.DEFUSED


class TestWrongDigit:
    """Wrong digit applies penalty without revealing the code."""

    def test_wrong_digit_applies_penalty(self) -> None:
        mode, ctx = _armed_context(secret="1234", remaining=100, penalty=15)
        mode.on_input("9", ctx)
        assert ctx.remaining_seconds == 85
        assert ctx.custom_data["input"] == ""
