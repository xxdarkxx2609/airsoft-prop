"""Tests for src.hal.wires_mock — state transitions and validation."""

import pytest

from src.hal.wires_mock import MockWires


class TestCutAndReset:
    """``cut_wire`` flips state; ``reset_wire`` restores it."""

    def test_cut_wire_changes_state_and_intact_flag(self) -> None:
        wires = MockWires()
        wires.init()
        assert wires.all_wires_intact() is True
        wires.cut_wire("Green")
        assert wires.get_wire_states()["Green"] is False
        assert wires.all_wires_intact() is False

    def test_reset_wire_restores_intact_state(self) -> None:
        wires = MockWires()
        wires.init()
        wires.cut_wire("Blue")
        wires.reset_wire("Blue")
        assert wires.get_wire_states()["Blue"] is True
        assert wires.all_wires_intact() is True


class TestInvalidWireName:
    """Unknown wire names raise ValueError — this is a fail-fast contract.

    Mock-only methods (cut_wire/reset_wire/toggle_wire) raise so the
    caller — typically the cut_the_wire mode — fails loudly during
    setup rather than silently no-op'ing on a misconfigured wire role.
    """

    def test_cut_unknown_wire_raises_value_error(self) -> None:
        wires = MockWires()
        wires.init()
        with pytest.raises(ValueError, match="Unknown wire"):
            wires.cut_wire("NotARealColor")
