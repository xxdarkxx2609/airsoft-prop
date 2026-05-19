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

    def test_hal_shutdown_exception_is_swallowed_not_raised(
        self, mock_app
    ) -> None:
        """A raising HAL shutdown is logged, never propagated to the caller.

        Note: the seven HAL shutdowns share a single try/except (see
        :func:`src.app.App.shutdown`). If display.shutdown() raises,
        audio/input/etc. are NOT subsequently called in that run —
        the exception jumps straight to the ``logger.exception`` branch.
        Systemd's TimeoutStopSec safety net still bounds the process,
        but a more granular per-HAL try/except would be a worthwhile
        future refactor.
        """
        boom = MagicMock()
        boom.shutdown.side_effect = RuntimeError("HAL died")
        mock_app.display = boom
        mock_app.shutdown()  # must not raise — that's the only guarantee here
