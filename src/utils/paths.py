"""Frozen-aware path resolution for PyInstaller compatibility.

Provides a single source of truth for the project root directory,
whether running from source or from a PyInstaller bundle.
"""

import sys
from pathlib import Path


def get_project_root() -> Path:
    """Return the project root directory.

    When running from source: three levels up from this file
    (src/utils/paths.py -> src/utils -> src -> project_root).

    When frozen with PyInstaller --onedir: the directory containing
    the executable. Config and assets sit alongside the .exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent
