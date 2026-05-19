"""Tests for src.ui.base_screen — DIGIT_TO_NAV mapping."""

from src.ui.base_screen import DIGIT_TO_NAV, translate_digit_to_nav


class TestDigitToNav:
    """Numpad arrow-layout: 8/2/4/6 → up/down/left/right."""

    def test_mapping_constants(self) -> None:
        assert DIGIT_TO_NAV == {
            "8": "up",
            "2": "down",
            "4": "left",
            "6": "right",
        }

    def test_translate_arrow_digits(self) -> None:
        assert translate_digit_to_nav("8") == "up"
        assert translate_digit_to_nav("2") == "down"
        assert translate_digit_to_nav("4") == "left"
        assert translate_digit_to_nav("6") == "right"

    def test_other_keys_pass_through(self) -> None:
        for key in ("0", "1", "3", "5", "7", "9", "enter", "backspace"):
            assert translate_digit_to_nav(key) == key
