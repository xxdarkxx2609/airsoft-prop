"""Tests for the main loop's error tolerance — Gotcha #6.

The loop survives individual frame errors but bails out after 10
consecutive failures. Verifying this requires actually running
``App.run()`` because the ``_consecutive_errors`` counter is a local
variable inside the loop, not an attribute on App.

We run the loop in a background thread with:
- ``signal.signal`` patched (the real call raises from non-main threads),
- ``time.sleep`` patched (so the test doesn't burn frame-time budget),
- ``shutdown`` patched (so HAL teardown noise stays out of the test).
"""

import threading
import time

import pytest

from src.ui.base_screen import BaseScreen


class _AlwaysRaisingScreen(BaseScreen):
    """Render path raises every frame — the 10-error path."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.render_calls = 0

    def render(self, display) -> None:
        self.render_calls += 1
        raise RuntimeError(f"intentional failure #{self.render_calls}")

    def handle_input(self, key: str) -> None:
        pass


class _RaiseOnceScreen(BaseScreen):
    """Render fails on the first call, succeeds thereafter."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.render_calls = 0

    def render(self, display) -> None:
        self.render_calls += 1
        if self.render_calls == 1:
            raise RuntimeError("first-frame blip")

    def handle_input(self, key: str) -> None:
        pass


def _neuter_runtime_hooks(monkeypatch) -> None:
    """Make ``run()`` safe to call from a background thread.

    - signal.signal must be a no-op (non-main-thread call raises ValueError)
    - _LOOP_INTERVAL set to 0 so each frame's sleep_time is negative
      and the ``if sleep_time > 0`` guard skips ``time.sleep`` entirely.
      We deliberately do NOT patch ``time.sleep`` globally — the test's
      own polling loop relies on it.
    """
    monkeypatch.setattr("src.app.signal.signal", lambda *a, **kw: None)
    monkeypatch.setattr("src.app._LOOP_INTERVAL", 0.0)


def _run_in_thread(app, timeout: float) -> threading.Thread:
    """Run ``app.run()`` in a daemon thread and join with the given timeout."""
    thread = threading.Thread(target=app.run, daemon=True, name="AppMainLoop")
    thread.start()
    thread.join(timeout=timeout)
    return thread


class TestTenConsecutiveErrorsTerminateLoop:
    """Gotcha #6: ten consecutive frame errors trigger a graceful exit."""

    def test_loop_terminates_after_ten_errors(
        self, mock_app, monkeypatch, caplog
    ) -> None:
        _neuter_runtime_hooks(monkeypatch)
        # Suppress per-frame teardown — shutdown() is exercised in test_shutdown.
        monkeypatch.setattr(mock_app, "shutdown", lambda *a, **kw: None)

        screen = _AlwaysRaisingScreen(mock_app)
        mock_app.screen_manager.register("boot", screen)

        with caplog.at_level("CRITICAL"):
            thread = _run_in_thread(mock_app, timeout=5.0)

        assert not thread.is_alive(), (
            "Main loop did not terminate after consecutive errors"
        )
        assert screen.render_calls >= 10, (
            f"Expected at least 10 render attempts before shutdown, "
            f"got {screen.render_calls}"
        )
        assert any(
            "Too many consecutive errors" in r.message
            for r in caplog.records
        ), "Expected the 'Too many consecutive errors' critical log"


class TestOneErrorDoesNotKillLoop:
    """A single frame error must not terminate the loop."""

    def test_loop_survives_a_single_error(
        self, mock_app, monkeypatch
    ) -> None:
        _neuter_runtime_hooks(monkeypatch)
        monkeypatch.setattr(mock_app, "shutdown", lambda *a, **kw: None)

        screen = _RaiseOnceScreen(mock_app)
        mock_app.screen_manager.register("boot", screen)

        thread = threading.Thread(target=mock_app.run, daemon=True)
        thread.start()
        # Let it tick a few times.
        for _ in range(20):
            if screen.render_calls >= 5:
                break
            time.sleep(0.01)

        mock_app._running = False
        thread.join(timeout=2.0)

        assert not thread.is_alive(), "Loop did not stop when _running cleared"
        assert screen.render_calls >= 2, (
            f"Loop terminated after first error — expected to survive. "
            f"Render calls: {screen.render_calls}"
        )
