"""Tests for src.ui.lcd_helpers — text formatting + timer."""

from src.ui.lcd_helpers import (
    blink_text,
    center_text,
    format_timer,
    pad_text,
    progress_bar,
)


class TestFormatTimer:
    """``format_timer`` formats seconds as MM:SS, clamping negatives to 0."""

    def test_two_minute_five_seconds(self) -> None:
        assert format_timer(125) == "02:05"

    def test_zero_seconds(self) -> None:
        assert format_timer(0) == "00:00"

    def test_max_timer(self) -> None:
        # 5999 seconds = 99 minutes 59 seconds — fits in the LCD's MM:SS.
        assert format_timer(5999) == "99:59"

    def test_negative_clamps_to_zero(self) -> None:
        assert format_timer(-5) == "00:00"


class TestCenterText:
    """``center_text`` pads to the given width, truncating overflow."""

    def test_pads_short_text(self) -> None:
        out = center_text("hi", 20)
        assert len(out) == 20
        assert out.strip() == "hi"
        # Padding is roughly balanced.
        assert out == "         hi         "

    def test_truncates_long_text(self) -> None:
        out = center_text("a" * 30, 20)
        assert len(out) == 20
        assert out == "a" * 20


class TestPadText:
    """``pad_text`` left-aligns and pads to width, never truncates short input."""

    def test_short_text_padded_with_spaces(self) -> None:
        out = pad_text("hi", 20)
        assert out == "hi" + " " * 18
        assert len(out) == 20

    def test_long_text_truncated(self) -> None:
        out = pad_text("x" * 30, 20)
        assert out == "x" * 20


class TestBlinkText:
    """``blink_text`` swaps text with spaces of equal length."""

    def test_visible_returns_original(self) -> None:
        assert blink_text("hello", visible=True) == "hello"

    def test_hidden_returns_spaces(self) -> None:
        assert blink_text("hello", visible=False) == "     "


class TestProgressBar:
    """``progress_bar`` renders a bracketed bar of exactly ``width`` chars."""

    def test_empty_bar(self) -> None:
        bar = progress_bar(0, 100, width=10)
        assert len(bar) == 10
        assert bar == "[        ]"

    def test_full_bar(self) -> None:
        bar = progress_bar(100, 100, width=10)
        assert bar == "[========]"
        assert len(bar) == 10

    def test_zero_total_does_not_divide_by_zero(self) -> None:
        bar = progress_bar(5, 0, width=10)
        assert len(bar) == 10
