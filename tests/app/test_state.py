"""Tests for App state introspection: ``is_game_in_progress``, snapshot, events."""

from src.modes.base_mode import GameContext
from src.ui.base_screen import BaseScreen


class _NoOpScreen(BaseScreen):
    """Minimal screen with no rendering or input handling."""

    def render(self, display) -> None:
        pass

    def handle_input(self, key: str) -> None:
        pass


class TestIsGameInProgress:
    """``is_game_in_progress`` returns True only for ``armed`` and ``planting``."""

    def test_returns_false_when_no_screen_active(self, mock_app) -> None:
        assert mock_app.is_game_in_progress() is False

    def test_returns_true_for_armed_screen(self, mock_app) -> None:
        mock_app.screen_manager.register("armed", _NoOpScreen(mock_app))
        mock_app.screen_manager.switch_to("armed")
        assert mock_app.is_game_in_progress() is True

    def test_returns_true_for_planting_screen(self, mock_app) -> None:
        mock_app.screen_manager.register("planting", _NoOpScreen(mock_app))
        mock_app.screen_manager.switch_to("planting")
        assert mock_app.is_game_in_progress() is True

    def test_returns_false_for_menu(self, mock_app) -> None:
        mock_app.screen_manager.register("menu", _NoOpScreen(mock_app))
        mock_app.screen_manager.switch_to("menu")
        assert mock_app.is_game_in_progress() is False


class TestGameStateSnapshot:
    """``_update_game_snapshot`` reflects current state; getter is thread-safe."""

    def test_snapshot_contains_state_and_device_name(self, mock_app) -> None:
        mock_app.screen_manager.register("menu", _NoOpScreen(mock_app))
        mock_app.screen_manager.switch_to("menu")
        mock_app._update_game_snapshot()
        snap = mock_app.get_game_state_snapshot()
        assert snap["state"] == "menu"
        assert snap["device_name"] == "Prop"

    def test_armed_snapshot_includes_remaining_seconds(self, mock_app) -> None:
        mock_app.screen_manager.register("armed", _NoOpScreen(mock_app))
        mock_app.screen_manager.switch_to("armed")
        mock_app.game_context = GameContext(timer_seconds=300, remaining_seconds=180)
        # selected_mode is None — armed_info uses empty mode_name string.
        mock_app._update_game_snapshot()
        snap = mock_app.get_game_state_snapshot()
        assert snap["armed"] is not None
        assert snap["armed"]["remaining_seconds"] == 180
        assert snap["armed"]["total_seconds"] == 300


class TestRecentEventsRing:
    """Recent events are bounded to 20 entries, newest first."""

    def test_append_recent_event_inserts_at_front(self, mock_app) -> None:
        mock_app._append_recent_event("boot", "first")
        mock_app._append_recent_event("armed", "second")
        snap = mock_app.get_game_state_snapshot()
        events = snap["recent_events"]
        assert events[0]["message"] == "second"
        assert events[1]["message"] == "first"

    def test_ring_buffer_caps_at_twenty(self, mock_app) -> None:
        for i in range(25):
            mock_app._append_recent_event("test", f"event-{i}")
        events = mock_app.get_game_state_snapshot()["recent_events"]
        assert len(events) == 20
        # Newest five are 24..20 — the first five (0..4) were dropped.
        assert events[0]["message"] == "event-24"
