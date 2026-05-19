"""Tests for App.shutdown — graceful HAL teardown order + idempotency."""

from unittest.mock import MagicMock


class TestShutdown:
    """``shutdown()`` flips ``_running`` and tears down every HAL component."""

    def test_shutdown_sets_running_to_false(self, mock_app) -> None:
        mock_app._running = True
        mock_app.shutdown()
        assert mock_app._running is False

    def test_shutdown_calls_every_hal_shutdown_method(self, mock_app) -> None:
        """Each of the seven HAL slots must receive a shutdown() call."""
        for attr in ("display", "audio", "input", "wires", "usb_detector", "battery", "led"):
            setattr(mock_app, attr, MagicMock())
        mock_app.shutdown()
        for attr in ("display", "audio", "input", "wires", "usb_detector", "battery", "led"):
            getattr(mock_app, attr).shutdown.assert_called_once()

    def test_shutdown_safe_with_no_web_or_portal(self, mock_app) -> None:
        """``self._web_server is None`` and ``captive_portal is None`` must not raise."""
        assert mock_app._web_server is None
        assert mock_app.captive_portal is None
        mock_app.shutdown()  # must not raise

    def test_hal_shutdown_isolates_per_component_failures(
        self, mock_app
    ) -> None:
        """One bad driver must not prevent the others from releasing resources.

        Each HAL component has its own try/except in
        :func:`src.app.App.shutdown` — a raising display.shutdown() is
        logged but does not skip audio/input/wires/usb_detector/battery/led.
        """
        boom = MagicMock()
        boom.shutdown.side_effect = RuntimeError("HAL died")
        mock_app.display = boom
        survivors = {
            attr: MagicMock()
            for attr in ("audio", "input", "wires", "usb_detector", "battery", "led")
        }
        for attr, m in survivors.items():
            setattr(mock_app, attr, m)

        mock_app.shutdown()  # must not raise

        boom.shutdown.assert_called_once()
        for attr, m in survivors.items():
            m.shutdown.assert_called_once()
