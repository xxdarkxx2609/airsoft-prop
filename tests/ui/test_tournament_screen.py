"""Tests for the tournament screen — PIN entry trigger + USB key exit.

The two organiser-exit mechanisms documented in CLAUDE.md:
1. **PIN entry**: five rapid backspaces within 3 s opens a PIN prompt;
   the correct PIN exits tournament mode.
2. **USB-stick exit**: a USB stick carrying ``TOURNAMENT.KEY`` triggers
   an automatic exit when detected during ``render()``.
"""

from src.modes import discover_modes
from src.ui.base_screen import BaseScreen
from src.ui.tournament_screen import TournamentScreen


class _NoOpScreen(BaseScreen):
    def render(self, display) -> None: pass
    def handle_input(self, key: str) -> None: pass


def _setup_screen(mock_app):
    """Populate modes + register transition + instantiate + on_enter."""
    mock_app.modes = [cls() for cls in discover_modes()]
    mock_app.screen_manager.register(
        "tournament_transition", _NoOpScreen(mock_app)
    )
    screen = TournamentScreen(mock_app)
    screen.on_enter()
    return screen


class TestRapidBackspaceTriggersPin:
    """Five backspaces within 3 s opens the PIN prompt."""

    def test_five_fast_backspaces_open_pin_mode(
        self, mock_app, monkeypatch
    ) -> None:
        screen = _setup_screen(mock_app)
        # Freeze time so all five presses share the same timestamp.
        monkeypatch.setattr("src.ui.tournament_screen.time.time", lambda: 100.0)
        for _ in range(5):
            screen.handle_input("backspace")
        assert screen._pin_mode is True

    def test_four_backspaces_do_not_open_pin_mode(
        self, mock_app, monkeypatch
    ) -> None:
        screen = _setup_screen(mock_app)
        monkeypatch.setattr("src.ui.tournament_screen.time.time", lambda: 100.0)
        for _ in range(4):
            screen.handle_input("backspace")
        assert screen._pin_mode is False

    def test_five_backspaces_spread_over_four_seconds_do_not_trigger(
        self, mock_app, monkeypatch
    ) -> None:
        screen = _setup_screen(mock_app)
        # Each press advances time by 1s; the 3-second window means
        # by the time the 5th arrives, the first two are out of scope.
        clock = {"t": 100.0}

        def _now() -> float:
            return clock["t"]

        monkeypatch.setattr("src.ui.tournament_screen.time.time", _now)
        for _ in range(5):
            screen.handle_input("backspace")
            clock["t"] += 1.0
        assert screen._pin_mode is False


class TestPinCheck:
    """Correct PIN exits tournament; wrong PIN drops back to lobby."""

    def test_correct_pin_exits_to_transition_and_disables_tournament(
        self, mock_app, monkeypatch
    ) -> None:
        # Configure a known PIN + start tournament enabled.
        mock_app.config.save_user_config(
            {"tournament.enabled": True, "tournament.pin": "1234"}
        )
        screen = _setup_screen(mock_app)
        monkeypatch.setattr("src.ui.tournament_screen.time.time", lambda: 100.0)

        for _ in range(5):
            screen.handle_input("backspace")
        assert screen._pin_mode is True

        for digit in "1234":
            screen.handle_input(digit)

        assert mock_app.screen_manager.active_name == "tournament_transition"
        assert mock_app.tournament_transition_target == "leave"
        assert mock_app.config.is_tournament_enabled() is False

    def test_wrong_pin_clears_input_and_stays_in_tournament(
        self, mock_app, monkeypatch
    ) -> None:
        mock_app.config.save_user_config(
            {"tournament.enabled": True, "tournament.pin": "1234"}
        )
        screen = _setup_screen(mock_app)
        monkeypatch.setattr("src.ui.tournament_screen.time.time", lambda: 100.0)
        for _ in range(5):
            screen.handle_input("backspace")
        for digit in "9999":
            screen.handle_input(digit)

        assert screen._pin_mode is False
        assert screen._pin_input == ""
        # Tournament still enabled in config.
        assert mock_app.config.is_tournament_enabled() is True
        # Did NOT switch to transition.
        assert mock_app.screen_manager.active_name != "tournament_transition"


class TestUsbKeyExit:
    """Detecting ``TOURNAMENT.KEY`` during ``render()`` triggers the exit."""

    def test_tournament_key_present_switches_to_transition(
        self, mock_app
    ) -> None:
        mock_app.config.save_user_config({"tournament.enabled": True})
        screen = _setup_screen(mock_app)
        # Simulate the organiser inserting the TOURNAMENT.KEY USB stick.
        mock_app.usb_detector.tournament_key_inserted = True

        screen.render(mock_app.display)

        assert mock_app.screen_manager.active_name == "tournament_transition"
        assert mock_app.tournament_transition_target == "leave"
        assert mock_app.config.is_tournament_enabled() is False
