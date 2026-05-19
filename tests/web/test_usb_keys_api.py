"""Tests for /api/usb-keys/* — generate, validate, revoke."""

import hashlib


class TestGenerate:
    """``POST /api/usb-keys/generate`` issues a token and stores its hash."""

    def test_generate_defuse_key_returns_token_and_persists_hash(
        self, web_client, mock_app
    ) -> None:
        response = web_client.post(
            "/api/usb-keys/generate",
            json={
                "key_type": "defuse",
                "mount_point": "/mock",
                "label": "Test Key",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        token = data["token"]
        assert token  # raw token returned exactly once
        # The stored record hashes the token with SHA-256.
        expected_hash = hashlib.sha256(token.encode()).hexdigest()
        keys = mock_app.config.load_usb_keys()
        defuse = keys["defuse_keys"]
        assert any(k["token_hash"] == expected_hash for k in defuse)

    def test_generated_key_validates_via_mock_detector(
        self, web_client, mock_app
    ) -> None:
        """After generation, the allowlist is hot-reloaded into the detector."""
        response = web_client.post(
            "/api/usb-keys/generate",
            json={"key_type": "defuse", "mount_point": "/mock"},
        )
        token = response.get_json()["token"]
        # Simulate the USB stick carrying the issued token.
        mock_app.usb_detector._defuse_token = token
        mock_app.usb_detector.key_inserted = True
        assert mock_app.usb_detector.is_key_present() is True


class TestKeyTypeSeparation:
    """Defuse and tournament keys live in independent lists."""

    def test_tournament_key_not_stored_in_defuse_list(
        self, web_client, mock_app
    ) -> None:
        web_client.post(
            "/api/usb-keys/generate",
            json={"key_type": "tournament", "mount_point": "/mock"},
        )
        keys = mock_app.config.load_usb_keys()
        assert keys["defuse_keys"] == []
        assert len(keys["tournament_keys"]) == 1


class TestRevoke:
    """``DELETE /api/usb-keys/<type>/<id>`` removes the registered entry."""

    def test_revoke_removes_key_from_registry(
        self, web_client, mock_app
    ) -> None:
        gen = web_client.post(
            "/api/usb-keys/generate",
            json={"key_type": "defuse", "mount_point": "/mock"},
        )
        key_id = gen.get_json()["record"]["id"]
        response = web_client.delete(f"/api/usb-keys/defuse/{key_id}")
        assert response.status_code == 200
        assert mock_app.config.load_usb_keys()["defuse_keys"] == []

    def test_revoke_unknown_id_returns_404(self, web_client) -> None:
        response = web_client.delete("/api/usb-keys/defuse/doesnotexist")
        assert response.status_code == 404
