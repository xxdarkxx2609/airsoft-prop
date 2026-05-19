"""Tests for /api/service/restart — mock-mode behaviour.

The real restart path uses ``sudo systemctl`` and PID comparison, which
only makes sense on the Pi. In mock mode the endpoint short-circuits
to a simulated success with ``restart_verified=True``.
"""


class TestServiceRestartMockMode:
    """In mock mode the endpoint returns a simulated success."""

    def test_returns_simulated_success(self, web_client) -> None:
        response = web_client.post("/api/service/restart")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["restart_verified"] is True
