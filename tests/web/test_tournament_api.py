"""Tests for /api/tournament — HTTP 409 game-in-progress guard + events."""

from src.ui.base_screen import BaseScreen


class _ArmedScreen(BaseScreen):
    """Stand-in armed screen so ``is_game_in_progress()`` returns True."""

    def render(self, display) -> None: pass
    def handle_input(self, key: str) -> None: pass


def _drain_event_types(app) -> list[str]:
    types: list[str] = []
    while not app._event_queue.empty():
        ev = app._event_queue.get_nowait()
        types.append(ev.get("type"))
    return types


class TestTournamentGet:
    """``GET /api/tournament`` returns current settings + game_in_progress."""

    def test_returns_disabled_by_default(self, web_client) -> None:
        response = web_client.get("/api/tournament")
        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is False
        assert data["game_in_progress"] is False
        # ``available_modes`` is populated from mock_app.modes (discovered).
        assert any(
            m["module"] == "random_code" for m in data["available_modes"]
        )


class TestGameInProgressGuard:
    """Saving tournament settings is blocked with HTTP 409 while playing."""

    def test_save_blocked_with_409_when_armed(
        self, web_client, mock_app
    ) -> None:
        mock_app.screen_manager.register("armed", _ArmedScreen(mock_app))
        mock_app.screen_manager.switch_to("armed")
        assert mock_app.is_game_in_progress() is True

        response = web_client.post(
            "/api/tournament",
            json={"enabled": True, "mode": "random_code", "pin": "1234"},
        )
        assert response.status_code == 409


class TestPinValidation:
    """PIN must be exactly 4 digits — anything else is 400."""

    def test_three_digit_pin_returns_400(self, web_client) -> None:
        response = web_client.post(
            "/api/tournament",
            json={"enabled": False, "mode": "random_code", "pin": "123"},
        )
        assert response.status_code == 400

    def test_non_digit_pin_returns_400(self, web_client) -> None:
        response = web_client.post(
            "/api/tournament",
            json={"enabled": False, "mode": "random_code", "pin": "abcd"},
        )
        assert response.status_code == 400


class TestActivateEvent:
    """Transitioning ``enabled`` False→True posts ``tournament_activate``."""

    def test_enable_posts_activate_event(self, web_client, mock_app) -> None:
        _drain_event_types(mock_app)
        response = web_client.post(
            "/api/tournament",
            json={"enabled": True, "mode": "random_code", "pin": "1234"},
        )
        assert response.status_code == 200
        types = _drain_event_types(mock_app)
        assert "tournament_activate" in types
        # Settings persisted.
        assert mock_app.config.is_tournament_enabled() is True
        assert mock_app.config.get_tournament_pin() == "1234"
