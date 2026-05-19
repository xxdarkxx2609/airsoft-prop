"""Tests for the captive portal — Gotcha #8 and AP-mode redirects."""

import subprocess
from unittest.mock import MagicMock


class TestWifiConnectionCachePriming:
    """Gotcha #8: ``_wifi_connected`` is primed in ``__init__`` via nmcli.

    Without the cache primer, ``is_wifi_connected()`` returns the
    uninitialised value (False) at boot, which makes :mod:`src.app`
    falsely start AP mode. This test asserts the priming subprocess
    call happens during construction.
    """

    def test_init_calls_nmcli_to_prime_cache(
        self, mock_config, monkeypatch
    ) -> None:
        from src.web import captive_portal as cp_module
        from src.web.captive_portal import CaptivePortal

        calls: list[list[str]] = []

        def _fake_run(cmd, **kwargs):
            calls.append(cmd)
            result = MagicMock()
            result.stdout = "GENERAL.STATE:100 (connected)\n"
            result.returncode = 0
            return result

        monkeypatch.setattr(cp_module.subprocess, "run", _fake_run)

        portal = CaptivePortal(mock_config)

        nmcli_calls = [c for c in calls if c and c[0] == "nmcli"]
        assert nmcli_calls, (
            "CaptivePortal.__init__ did not call nmcli to prime the cache. "
            "Without this priming, is_wifi_connected() returns False at boot "
            "and the app falsely starts AP mode (Gotcha #8)."
        )
        assert portal._wifi_connected is True

    def test_is_wifi_connected_uses_cache_no_subprocess(
        self, mock_config, monkeypatch
    ) -> None:
        from src.web import captive_portal as cp_module
        from src.web.captive_portal import CaptivePortal

        call_count = {"n": 0}

        def _fake_run(cmd, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            result.stdout = "GENERAL.STATE:100 (connected)\n"
            result.returncode = 0
            return result

        monkeypatch.setattr(cp_module.subprocess, "run", _fake_run)
        portal = CaptivePortal(mock_config)
        # One subprocess call during __init__.
        baseline = call_count["n"]
        # 100 reads — none should trigger another subprocess.
        for _ in range(100):
            portal.is_wifi_connected()
        assert call_count["n"] == baseline, (
            "is_wifi_connected() spawned a subprocess — must return cached value"
        )


class TestCaptiveRedirects:
    """``/generate_204`` redirects to ``/wifi`` when the AP is active."""

    def test_generate_204_returns_no_redirect_with_no_portal(
        self, web_client
    ) -> None:
        # Default web_client fixture has no captive_portal — open mode.
        response = web_client.get("/generate_204", follow_redirects=False)
        assert response.status_code == 204

    def test_generate_204_redirects_to_wifi_when_ap_active(
        self, tmp_project_root, mock_app
    ) -> None:
        from src.modes import discover_modes
        from src.web.captive_portal import MockCaptivePortal
        from src.web.server import create_app

        portal = MockCaptivePortal()
        portal.start_ap()  # is_active() now True
        mock_app.modes = [cls() for cls in discover_modes()]

        flask_app = create_app(
            config=mock_app.config,
            mock=True,
            battery=mock_app.battery,
            prop_app=mock_app,
            captive_portal=portal,
        )
        with flask_app.test_client() as client:
            response = client.get("/generate_204", follow_redirects=False)
        assert response.status_code in (301, 302, 308)
        assert "/wifi" in response.headers["Location"]
