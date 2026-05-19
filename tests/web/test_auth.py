"""Tests for the auth layer: password gate + unauthenticated branding logo."""

from werkzeug.security import generate_password_hash


def _set_password(config, password: str) -> None:
    config.save_web_config({"password_hash": generate_password_hash(password)})


class TestOpenMode:
    """No password set → ``require_auth_api`` is a no-op (open mode)."""

    def test_api_accessible_without_password(self, web_client) -> None:
        # No password configured by default — open mode.
        response = web_client.get("/api/config")
        assert response.status_code == 200


class TestPasswordGate:
    """Once a password is set, unauthenticated requests get 401 / redirect."""

    def test_api_returns_401_without_session(
        self, web_client, mock_app
    ) -> None:
        _set_password(mock_app.config, "letmein")
        response = web_client.get("/api/config")
        assert response.status_code == 401

    def test_login_then_api_works(self, web_client, mock_app) -> None:
        _set_password(mock_app.config, "letmein")
        # Wrong password — still unauthenticated.
        web_client.post("/login", data={"password": "wrong"})
        assert web_client.get("/api/config").status_code == 401
        # Correct password — session established.
        web_client.post("/login", data={"password": "letmein"})
        assert web_client.get("/api/config").status_code == 200


class TestUnauthenticatedRoutes:
    """``/api/branding/logo`` is intentionally open — login page needs it."""

    def test_branding_logo_not_gated_by_auth(
        self, web_client, mock_app
    ) -> None:
        _set_password(mock_app.config, "letmein")
        response = web_client.get("/api/branding/logo")
        # No logo configured → 404 (NOT 401 — the route is unauthenticated).
        assert response.status_code == 404
