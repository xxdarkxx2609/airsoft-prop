"""Tests for src.hal.display_mock — buffer behaviour of the 20x4 mock LCD."""

from src.hal.display_mock import MockDisplay


class TestWriteLine:
    """``write_line`` pads/truncates each line to the LCD's 20-column width."""

    def test_short_text_is_padded_to_20_chars(self) -> None:
        display = MockDisplay()
        display.write_line(0, "hi")
        assert "".join(display._buffer[0]) == "hi" + " " * 18

    def test_long_text_is_truncated_to_20_chars(self) -> None:
        display = MockDisplay()
        display.write_line(1, "x" * 30)
        assert "".join(display._buffer[1]) == "x" * 20


class TestWriteAt:
    """``write_at`` clips at the row boundary — never spills into the next row."""

    def test_write_at_does_not_overflow_into_next_row(self) -> None:
        display = MockDisplay()
        display.write_line(0, "")  # ensure rows initialised
        display.write_line(1, "")
        # Start near the end of row 0 with text that would overflow.
        display.write_at(0, 18, "ABCDE")
        assert "".join(display._buffer[0])[-2:] == "AB"
        # Row 1 must remain untouched (still all spaces).
        assert "".join(display._buffer[1]) == " " * 20


class TestCustomChar:
    """LCD has 8 CGRAM slots — slots 0-7 valid, slot 8+ rejected."""

    def test_create_custom_char_accepts_valid_slots(self) -> None:
        display = MockDisplay()
        for slot in range(8):
            display.create_custom_char(slot, [0] * 8)
        assert set(display._custom_chars.keys()) == set(range(8))

    def test_create_custom_char_rejects_out_of_range_slot(
        self, caplog
    ) -> None:
        display = MockDisplay()
        with caplog.at_level("WARNING"):
            display.create_custom_char(8, [0] * 8)
        assert 8 not in display._custom_chars
        assert any("out of range" in r.message for r in caplog.records)
