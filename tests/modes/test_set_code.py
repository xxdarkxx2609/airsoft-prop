"""Tests for src.modes.set_code — pre-configured secret code."""

from src.modes.base_mode import GameContext, ModeResult, PlantingType
from src.modes.set_code import SetCodeMode


def _armed_context(secret: str = "4321") -> tuple[SetCodeMode, GameContext]:
    mode = SetCodeMode()
    ctx = GameContext(timer_seconds=300, remaining_seconds=300)
    ctx.setup_values["code"] = secret
    mode.on_armed(ctx)
    return mode, ctx


class TestPlantingConfig:
    """SetCode requires a 10-digit random activation code to plant."""

    def test_planting_is_code_entry_with_ten_digits(self) -> None:
        cfg = SetCodeMode().get_planting_config()
        assert cfg.planting_type is PlantingType.CODE_ENTRY
        assert cfg.code_length == 10


class TestOnArmed:
    """``on_armed`` stores the GM-configured secret in ``custom_data``."""

    def test_secret_is_stored_from_setup_values(self) -> None:
        _, ctx = _armed_context("9876")
        assert ctx.custom_data["code"] == "9876"
        assert ctx.custom_data["input"] == ""


class TestOnInput:
    """Defuse behaviour mirrors random_code (full match defuses)."""

    def test_correct_secret_returns_defused(self) -> None:
        mode, ctx = _armed_context("4321")
        result: ModeResult = ModeResult.CONTINUE
        for digit in "4321":
            result = mode.on_input(digit, ctx)
        assert result is ModeResult.DEFUSED

    def test_wrong_full_attempt_clears_input(self) -> None:
        mode, ctx = _armed_context("4321")
        for digit in "9999":
            mode.on_input(digit, ctx)
        assert ctx.custom_data["input"] == ""
