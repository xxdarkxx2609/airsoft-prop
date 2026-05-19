"""Tests for the cross-thread event queue (WebUI → main loop).

Covered events: tournament_activate, tournament_deactivate,
audio_volume_changed, display_backlight_changed, logging_level_changed,
and the unknown-event-type warning path.
"""

import logging

from src.ui.base_screen import BaseScreen


class _FakeScreen(BaseScreen):
    """Minimal screen — tracks lifecycle calls without rendering anything."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.entered = False
        self.exited = False

    def on_enter(self) -> None:
        self.entered = True

    def on_exit(self) -> None:
        self.exited = True

    def render(self, display) -> None:
        pass

    def handle_input(self, key: str) -> None:
        pass


def _register_dummy_screens(app) -> None:
    """Register the screens the event handlers may switch into."""
    for name in ("tournament", "tournament_transition"):
        app.screen_manager.register(name, _FakeScreen(app))


class TestPostEvent:
    """``post_event`` enqueues; ``_process_events`` consumes."""

    def test_post_then_process_drains_queue(self, mock_app) -> None:
        _register_dummy_screens(mock_app)
        mock_app.post_event({"type": "audio_volume_changed", "value": 0.3})
        assert not mock_app._event_queue.empty()
        mock_app._process_events()
        assert mock_app._event_queue.empty()


class TestTournamentEvents:
    """``tournament_activate`` / ``tournament_deactivate`` drive transitions."""

    def test_activate_switches_to_transition_with_enter_target(
        self, mock_app
    ) -> None:
        _register_dummy_screens(mock_app)
        mock_app.post_event({"type": "tournament_activate"})
        mock_app._process_events()
        assert mock_app.tournament_transition_target == "enter"
        assert mock_app.screen_manager.active_name == "tournament_transition"

    def test_deactivate_saves_config_and_switches(self, mock_app) -> None:
        _register_dummy_screens(mock_app)
        # Seed tournament.enabled=True so the save creates a diff.
        mock_app.config.save_user_config({"tournament.enabled": True})
        assert mock_app.config.is_tournament_enabled() is True

        mock_app.post_event({"type": "tournament_deactivate"})
        mock_app._process_events()
        assert mock_app.tournament_transition_target == "leave"
        assert mock_app.config.is_tournament_enabled() is False


class TestHardwareEvents:
    """``audio_volume_changed`` and ``display_backlight_changed`` reach the HAL."""

    def test_audio_volume_changed_calls_set_volume(self, mock_app) -> None:
        mock_app.post_event({"type": "audio_volume_changed", "value": 0.42})
        mock_app._process_events()
        assert mock_app.audio._volume == 0.42

    def test_display_backlight_changed_toggles_backlight(self, mock_app) -> None:
        mock_app.display._backlight = True
        mock_app.post_event({"type": "display_backlight_changed", "value": False})
        mock_app._process_events()
        assert mock_app.display._backlight is False


class TestLoggingLevelEvent:
    """``logging_level_changed`` updates the root logger level."""

    def test_log_level_event_updates_root_logger(self, mock_app) -> None:
        original = logging.getLogger().level
        try:
            mock_app.post_event(
                {"type": "logging_level_changed", "value": "DEBUG"}
            )
            mock_app._process_events()
            assert logging.getLogger().level == logging.DEBUG
        finally:
            logging.getLogger().setLevel(original)


class TestUnknownEvent:
    """An unknown event type logs a warning, never raises."""

    def test_unknown_event_type_logs_warning(self, mock_app, caplog) -> None:
        with caplog.at_level("WARNING"):
            mock_app.post_event({"type": "this-does-not-exist"})
            mock_app._process_events()
        assert any(
            "Unknown event type" in r.message for r in caplog.records
        )
