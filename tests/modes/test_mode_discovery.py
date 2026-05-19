"""Tests for src.modes.__init__ — discover_modes + Gotcha #3 guards.

Gotcha #3: adding a new mode requires updates in TWO places —
``src/modes/__init__.py::_KNOWN_MODES`` (used as fallback in frozen
PyInstaller builds) AND ``build/airsoft_prop.spec::hiddenimports``
(so PyInstaller bundles the module). Forgetting either makes the
frozen build silently lose modes.
"""

import ast
from pathlib import Path

import pytest

from src.modes import _KNOWN_MODES, discover_modes
from src.modes.base_mode import BaseMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _spec_hiddenimports() -> list[str]:
    """Parse hiddenimports list from build/airsoft_prop.spec via AST.

    The .spec file is a PyInstaller-style Python module — top-level
    ``a = Analysis(..., hiddenimports=[...], ...)``. We walk the AST
    instead of executing the file so we don't need PyInstaller installed.
    """
    spec_path = _project_root() / "build" / "airsoft_prop.spec"
    tree = ast.parse(spec_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id != "Analysis":
                continue
            for kw in node.keywords:
                if kw.arg == "hiddenimports" and isinstance(kw.value, ast.List):
                    return [
                        elt.value
                        for elt in kw.value.elts
                        if isinstance(elt, ast.Constant)
                        and isinstance(elt.value, str)
                    ]
    pytest.fail("hiddenimports not found in build/airsoft_prop.spec")


def _actual_mode_files() -> list[str]:
    """Return the stem of every importable module file in src/modes/."""
    modes_dir = _project_root() / "src" / "modes"
    return sorted(
        f.stem
        for f in modes_dir.glob("*.py")
        if not f.name.startswith("_") and f.name != "base_mode.py"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiscoverModes:
    """Source-mode discovery finds every mode file."""

    def test_discover_finds_all_known_modes(self) -> None:
        modes = discover_modes()
        module_stems = {m.__module__.rsplit(".", 1)[-1] for m in modes}
        # Every name in _KNOWN_MODES has at least one BaseMode subclass.
        for name in _KNOWN_MODES:
            assert name in module_stems, (
                f"discover_modes() did not return any class from "
                f"src.modes.{name}"
            )

    def test_every_returned_class_subclasses_base_mode(self) -> None:
        for cls in discover_modes():
            assert issubclass(cls, BaseMode)
            assert cls is not BaseMode


class TestKnownModesMatchesFiles:
    """``_KNOWN_MODES`` is the frozen-build fallback — it must list every mode file."""

    def test_known_modes_matches_actual_mode_files(self) -> None:
        actual = set(_actual_mode_files())
        known = set(_KNOWN_MODES)
        missing = actual - known
        extra = known - actual
        assert not missing, (
            f"Mode files exist but are missing from _KNOWN_MODES: {missing}. "
            f"Update src/modes/__init__.py::_KNOWN_MODES."
        )
        assert not extra, (
            f"_KNOWN_MODES lists modules that don't exist as files: {extra}."
        )


class TestSpecHiddenImportsMatchesKnownModes:
    """Gotcha #3 layer 2: every mode in _KNOWN_MODES is in hiddenimports."""

    def test_every_known_mode_is_in_pyinstaller_spec(self) -> None:
        hidden = set(_spec_hiddenimports())
        missing = [
            name
            for name in _KNOWN_MODES
            if f"src.modes.{name}" not in hidden
        ]
        assert not missing, (
            f"Modes missing from build/airsoft_prop.spec hiddenimports: "
            f"{missing}. Frozen builds will silently lose these modes."
        )


class TestCustomModeDiscovery:
    """A user-supplied .py file in custom/modes/ is picked up at runtime."""

    def test_custom_mode_is_discovered(
        self, tmp_path, monkeypatch
    ) -> None:
        custom_modes = tmp_path / "custom" / "modes"
        custom_modes.mkdir(parents=True)
        (custom_modes / "my_mode.py").write_text(
            "from src.modes.base_mode import BaseMode\n"
            "\n"
            "class MyCustomMode(BaseMode):\n"
            "    name = 'My Mode'\n"
            "    description = 'desc'\n"
            "    menu_key = '9'\n"
            "    def get_setup_options(self): return []\n"
            "    def on_armed(self, context): pass\n"
            "    def on_input(self, key, context): return None\n"
            "    def on_tick(self, remaining_seconds, context): return None\n"
            "    def render(self, display, remaining_seconds, context): pass\n"
            "    def render_last_10s(self, display, remaining_seconds, context): pass\n",
            encoding="utf-8",
        )

        # discover_modes() reads custom/modes/ via get_project_root().
        # The function is imported into src.modes namespace via
        # ``from src.utils.paths import get_project_root`` — so we
        # rebind the local name there.
        import src.modes as modes_pkg
        monkeypatch.setattr(modes_pkg, "get_project_root", lambda: tmp_path)

        all_modes = discover_modes()
        names = {m.__name__ for m in all_modes}
        assert "MyCustomMode" in names
