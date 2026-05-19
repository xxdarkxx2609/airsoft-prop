"""Tests for build/airsoft_prop.spec — guardrails for the frozen build.

The PyInstaller spec is plain Python, but it's executed by PyInstaller —
not by pytest. We parse it via :mod:`ast` instead so the tests run
without PyInstaller installed.

The ``hiddenimports`` ↔ ``_KNOWN_MODES`` parity check lives in
:mod:`tests.modes.test_mode_discovery` (Gotcha #3 layer 2). This file
adds two complementary guards: excluded Pi-only packages and required
``datas`` entries for the bundled Flask templates/static.
"""

import ast
from pathlib import Path


def _analysis_kwargs() -> dict[str, ast.expr]:
    """Return the ``Analysis(...)`` call's keyword args from the spec."""
    spec_path = (
        Path(__file__).resolve().parent.parent.parent
        / "build"
        / "airsoft_prop.spec"
    )
    tree = ast.parse(spec_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ):
            return {kw.arg: kw.value for kw in node.keywords if kw.arg}
    raise AssertionError("No Analysis(...) call found in airsoft_prop.spec")


def _string_list(value: ast.expr) -> list[str]:
    """Extract the string constants from an ``ast.List`` literal."""
    if not isinstance(value, ast.List):
        return []
    return [
        elt.value
        for elt in value.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
    ]


class TestExcludesPiOnlyPackages:
    """The Windows .exe must NOT bundle the Pi-only hardware libraries.

    These packages are not pip-installable on Windows / macOS and would
    explode at import time inside the frozen binary. They're listed in
    ``excludes`` so PyInstaller leaves them out of the bundle and the
    mock HAL is used at runtime instead.
    """

    REQUIRED_EXCLUDES = {"RPi", "RPi.GPIO", "RPLCD", "smbus2", "gpiozero"}

    def test_all_required_excludes_present(self) -> None:
        excludes = set(_string_list(_analysis_kwargs()["excludes"]))
        missing = self.REQUIRED_EXCLUDES - excludes
        assert not missing, (
            f"Pi-only packages missing from spec ``excludes``: {missing}. "
            f"Without these, the Windows build will try to import them "
            f"and crash on first HAL access."
        )


class TestDatasIncludesWebAssets:
    """Flask templates + static dirs must be bundled into the .exe.

    PyInstaller does not pick these up automatically — they live outside
    the import graph. Forgetting them breaks every web route at runtime
    inside the frozen binary.
    """

    def test_templates_and_static_in_datas(self) -> None:
        datas = _analysis_kwargs()["datas"]
        assert isinstance(datas, ast.List)
        dest_dirs: list[str] = []
        for entry in datas.elts:
            if isinstance(entry, ast.Tuple) and len(entry.elts) == 2:
                dest = entry.elts[1]
                if isinstance(dest, ast.Constant) and isinstance(dest.value, str):
                    dest_dirs.append(dest.value)
        assert any("templates" in d for d in dest_dirs), (
            "Flask templates not bundled — every web route renders blank"
        )
        assert any("static" in d for d in dest_dirs), (
            "Flask static dir not bundled — CSS / JS won't load"
        )
