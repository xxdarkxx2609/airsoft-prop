"""Tests for src.modes.usb_key_cracker — insert/remove/crack sequence."""

from src.hal.usb_detector_mock import MockUsbDetector
from src.modes.base_mode import GameContext, ModeResult, PlantingType
from src.modes.usb_key_cracker import UsbKeyCrackerMode


def _armed_context(digits: int = 4) -> tuple[
    UsbKeyCrackerMode, GameContext, MockUsbDetector
]:
    mode = UsbKeyCrackerMode()
    ctx = GameContext(timer_seconds=300, remaining_seconds=300)
    ctx.setup_values["digits"] = digits
    # Make every tick crack the next digit — bypass the real timer.
    ctx.custom_data["crack_interval"] = 0.0
    usb = MockUsbDetector()
    usb.init()
    ctx.custom_data["usb_detector"] = usb
    mode.on_armed(ctx)
    return mode, ctx, usb


class TestPlantingConfig:
    """USB Key Cracker requires holding Enter for 10s to plant."""

    def test_planting_is_timed_with_ten_seconds(self) -> None:
        cfg = UsbKeyCrackerMode().get_planting_config()
        assert cfg.planting_type is PlantingType.TIMED
        assert cfg.duration == 10


class TestSetupOptions:
    """Timer 30-5999, digits 4-20."""

    def test_digit_option_ranges(self) -> None:
        opts = UsbKeyCrackerMode().get_setup_options()
        digits = next(o for o in opts if o.key == "digits")
        assert digits.min_val == 4
        assert digits.max_val == 20


class TestCrackingFlow:
    """The full insert → crack → defuse sequence."""

    def test_inserting_usb_starts_cracking(self) -> None:
        mode, ctx, usb = _armed_context(digits=4)
        assert ctx.custom_data["cracking_active"] is False
        usb.key_inserted = True
        mode.on_tick(300, ctx)
        assert ctx.custom_data["cracking_active"] is True

    def test_removing_usb_mid_crack_aborts_and_resets_progress(self) -> None:
        mode, ctx, usb = _armed_context(digits=4)
        usb.key_inserted = True
        # Two ticks → 2 digits cracked (crack_interval=0).
        mode.on_tick(300, ctx)  # starts cracking, no digit yet
        mode.on_tick(300, ctx)  # cracks first digit
        mode.on_tick(300, ctx)  # cracks second digit
        assert len(ctx.custom_data["cracked_indices"]) >= 1

        usb.key_inserted = False
        mode.on_tick(300, ctx)
        assert ctx.custom_data["cracking_active"] is False
        assert ctx.custom_data["cracked_indices"] == []

    def test_all_digits_cracked_returns_defused(self) -> None:
        mode, ctx, usb = _armed_context(digits=4)
        usb.key_inserted = True
        # First tick starts cracking; next N ticks crack each digit.
        result: ModeResult = ModeResult.CONTINUE
        for _ in range(10):  # generous budget
            result = mode.on_tick(300, ctx)
            if result is ModeResult.DEFUSED:
                break
        assert result is ModeResult.DEFUSED
        assert len(ctx.custom_data["cracked_indices"]) == 4
