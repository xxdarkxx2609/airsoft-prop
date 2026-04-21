"""Game mode auto-discovery.

Scans this package for all classes inheriting from BaseMode
and registers them automatically.  Also discovers custom modes
from the ``custom/modes/`` directory.
"""

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import Type

from src.modes.base_mode import BaseMode
from src.utils.paths import get_project_root

# Known mode modules — used as fallback in frozen (PyInstaller) builds
# where pkgutil.iter_modules cannot scan the filesystem.
# Update this list when adding new game modes.
_KNOWN_MODES = ["random_code", "set_code", "random_code_plus", "set_code_plus", "usb_key_cracker", "cut_the_wire"]


def _extract_modes(module: object) -> list[Type[BaseMode]]:
    """Extract all BaseMode subclasses defined in a module."""
    found: list[Type[BaseMode]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, BaseMode)
            and obj is not BaseMode
            and obj.__module__ == module.__name__
        ):
            found.append(obj)
    return found


def discover_modes() -> list[Type[BaseMode]]:
    """Discover all game mode classes in the modes package.

    Scans all .py files in the modes directory, imports them,
    and returns classes that inherit from BaseMode. In frozen
    (PyInstaller) builds where filesystem scanning is unavailable,
    falls back to the explicit ``_KNOWN_MODES`` list.

    Returns:
        List of BaseMode subclasses, sorted by menu_key.
    """
    modes: list[Type[BaseMode]] = []
    package_dir = Path(__file__).parent

    discovered = list(pkgutil.iter_modules([str(package_dir)]))

    if discovered:
        # Normal source run — dynamic discovery
        for module_info in discovered:
            if module_info.name.startswith("_") or module_info.name == "base_mode":
                continue
            module = importlib.import_module(f"src.modes.{module_info.name}")
            modes.extend(_extract_modes(module))
    elif getattr(sys, "frozen", False):
        # Frozen build — use explicit list
        for name in _KNOWN_MODES:
            module = importlib.import_module(f"src.modes.{name}")
            modes.extend(_extract_modes(module))

    # Discover custom modes from custom/modes/ directory.
    custom_modes_dir = get_project_root() / "custom" / "modes"
    if custom_modes_dir.is_dir():
        for py_file in sorted(custom_modes_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            mod_name = f"custom.modes.{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(mod_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = module
                    spec.loader.exec_module(module)
                    modes.extend(_extract_modes(module))
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to load custom mode from %s", py_file, exc_info=True
                )

    modes.sort(key=lambda m: m.menu_key)
    return modes
