"""Tests for src.ui.screen_manager — registry + lifecycle + transitions."""

import pytest

from src.ui.base_screen import BaseScreen
from src.ui.screen_manager import ScreenManager


class _LifecycleScreen(BaseScreen):
    """Tracks every on_enter / on_exit / render / handle_input call."""

    def __init__(self) -> None:
        # Intentionally skip BaseScreen.__init__ — we don't need an App.
        self.entered = 0
        self.exited = 0
        self.rendered = 0
        self.last_key: str | None = None

    def on_enter(self) -> None:
        self.entered += 1

    def on_exit(self) -> None:
        self.exited += 1

    def render(self, display) -> None:
        self.rendered += 1

    def handle_input(self, key: str) -> None:
        self.last_key = key


class TestSwitchToLifecycle:
    """``switch_to`` calls on_exit on old, on_enter on new, exactly once."""

    def test_lifecycle_callbacks_invoked_on_transition(self) -> None:
        mgr = ScreenManager()
        a = _LifecycleScreen()
        b = _LifecycleScreen()
        mgr.register("a", a)
        mgr.register("b", b)

        mgr.switch_to("a")
        assert a.entered == 1
        assert a.exited == 0

        mgr.switch_to("b")
        assert a.exited == 1
        assert b.entered == 1

    def test_active_name_updated_synchronously(self) -> None:
        mgr = ScreenManager()
        mgr.register("a", _LifecycleScreen())
        mgr.register("b", _LifecycleScreen())
        mgr.switch_to("a")
        assert mgr.active_name == "a"
        mgr.switch_to("b")
        assert mgr.active_name == "b"


class TestSwitchToUnknown:
    """Switching to an unregistered name raises KeyError (fail-fast).

    Plan said "logs ERROR, does not crash" — the actual code raises
    :class:`KeyError`. Fail-fast is the right choice here: a typo
    in a screen name is a code bug, not a runtime condition.
    """

    def test_unknown_screen_raises_key_error(self) -> None:
        mgr = ScreenManager()
        with pytest.raises(KeyError, match="not registered"):
            mgr.switch_to("nope")


class TestRegisterDuplicate:
    """Registering the same name twice raises ValueError."""

    def test_duplicate_registration_raises(self) -> None:
        mgr = ScreenManager()
        mgr.register("a", _LifecycleScreen())
        with pytest.raises(ValueError, match="already registered"):
            mgr.register("a", _LifecycleScreen())


class TestNoActiveScreen:
    """``render`` / ``handle_input`` are no-ops when no screen is active."""

    def test_render_without_active_does_nothing(self) -> None:
        mgr = ScreenManager()
        mgr.render(display=None)  # must not raise

    def test_handle_input_without_active_does_nothing(self) -> None:
        mgr = ScreenManager()
        mgr.handle_input("enter")  # must not raise
