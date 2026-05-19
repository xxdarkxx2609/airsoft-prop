"""Tests for /api/config and /api/config/reset — Gotchas #4 (layer 2) + #5."""


def _drain_event_types(app) -> list[str]:
    """Drain the event queue and return the ``type`` of each event."""
    types: list[str] = []
    while not app._event_queue.empty():
        ev = app._event_queue.get_nowait()
        types.append(ev.get("type"))
    return types


class TestConfigGet:
    """``GET /api/config`` returns the current merged configuration."""

    def test_returns_defaults_when_no_user_overrides(self, web_client) -> None:
        response = web_client.get("/api/config")
        assert response.status_code == 200
        data = response.get_json()
        assert data["game"]["device_name"] == "Prop"
        assert data["audio"]["volume"] == 0.5


class TestDeviceNameValidation:
    """Gotcha #4 layer 2: the web API enforces the 7-char limit on save."""

    def test_too_long_device_name_returns_400(self, web_client) -> None:
        response = web_client.post(
            "/api/config",
            json={"game.device_name": "TooLongName"},
        )
        assert response.status_code == 400
        assert "7 characters" in response.get_json()["message"]

    def test_seven_char_device_name_accepted(self, web_client) -> None:
        response = web_client.post(
            "/api/config",
            json={"game.device_name": "Lucky77"},
        )
        assert response.status_code == 200


class TestConfigSaveEvents:
    """Saving runtime-tunable values fires events on the main-loop queue."""

    def test_audio_volume_save_posts_event(self, web_client, mock_app) -> None:
        # Drain any pre-test events.
        _drain_event_types(mock_app)
        response = web_client.post("/api/config", json={"audio.volume": 0.42})
        assert response.status_code == 200
        types = _drain_event_types(mock_app)
        assert "audio_volume_changed" in types

    def test_display_backlight_save_posts_event(
        self, web_client, mock_app
    ) -> None:
        _drain_event_types(mock_app)
        response = web_client.post(
            "/api/config", json={"display.backlight": False}
        )
        assert response.status_code == 200
        types = _drain_event_types(mock_app)
        assert "display_backlight_changed" in types


class TestConfigReset:
    """Gotcha #5: ``/api/config/reset`` deletes only ``user.yaml``."""

    def test_reset_deletes_user_yaml_but_preserves_usb_keys(
        self, web_client, mock_app, tmp_project_root
    ) -> None:
        # Seed both user overrides and a usb_keys registry entry.
        mock_app.config.save_user_config({"audio.volume": 0.7})
        mock_app.config.save_usb_keys(
            {"defuse_keys": [{"id": "abc", "label": "Test"}], "tournament_keys": []}
        )
        user_path = tmp_project_root / "custom" / "user.yaml"
        usb_path = tmp_project_root / "custom" / "usb_keys.yaml"
        assert user_path.exists()
        assert usb_path.exists()

        response = web_client.post("/api/config/reset")
        assert response.status_code == 200

        assert not user_path.exists(), "user.yaml must be removed on reset"
        assert usb_path.exists(), (
            "usb_keys.yaml must survive reset (Gotcha #5) — "
            "otherwise registered USB keys are lost on a settings reset"
        )
