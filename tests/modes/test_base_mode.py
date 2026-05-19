"""Tests for src.modes.base_mode — dataclasses + enums consumed by all modes."""

from src.modes.base_mode import (
    GameContext,
    PlantingConfig,
    PlantingType,
    SetupOption,
    SetupOptionType,
)


class TestSetupOption:
    """The four ``SetupOptionType``s round-trip through ``SetupOption``."""

    def test_range_option_uses_default_as_value(self) -> None:
        opt = SetupOption(
            key="timer",
            label="Timer",
            option_type=SetupOptionType.RANGE,
            default=300,
            min_val=30,
            max_val=5999,
        )
        assert opt.value == 300
        assert opt.min_val == 30
        assert opt.max_val == 5999

    def test_code_input_option(self) -> None:
        opt = SetupOption(
            key="code",
            label="Code",
            option_type=SetupOptionType.CODE_INPUT,
            default="",
            min_val=1,
            max_val=10,
        )
        assert opt.value == ""

    def test_select_option_with_choices(self) -> None:
        opt = SetupOption(
            key="wire",
            label="Wire",
            option_type=SetupOptionType.SELECT,
            default="Green",
            choices=["Green", "Blue", "Red"],
        )
        assert opt.choices == ["Green", "Blue", "Red"]
        assert opt.value == "Green"


class TestGameContext:
    """``GameContext`` defaults: collections are empty per-instance."""

    def test_defaults_are_empty_dicts(self) -> None:
        ctx = GameContext(timer_seconds=300, remaining_seconds=300)
        assert ctx.setup_values == {}
        assert ctx.wire_roles == {}
        assert ctx.custom_data == {}

    def test_default_factories_are_not_shared_between_instances(self) -> None:
        """Mutating one context's dicts must not leak into another."""
        ctx_a = GameContext(timer_seconds=300, remaining_seconds=300)
        ctx_a.custom_data["x"] = 1
        ctx_b = GameContext(timer_seconds=600, remaining_seconds=600)
        assert ctx_b.custom_data == {}


class TestPlantingConfig:
    """``PlantingConfig`` defaults match the INSTANT case."""

    def test_default_is_instant_with_zero_duration(self) -> None:
        cfg = PlantingConfig()
        assert cfg.planting_type is PlantingType.INSTANT
        assert cfg.duration == 0
        assert cfg.code_length == 0

    def test_code_entry_config(self) -> None:
        cfg = PlantingConfig(
            planting_type=PlantingType.CODE_ENTRY, code_length=10
        )
        assert cfg.planting_type is PlantingType.CODE_ENTRY
        assert cfg.code_length == 10

    def test_timed_config(self) -> None:
        cfg = PlantingConfig(planting_type=PlantingType.TIMED, duration=10)
        assert cfg.planting_type is PlantingType.TIMED
        assert cfg.duration == 10
