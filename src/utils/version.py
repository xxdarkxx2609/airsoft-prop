"""Git-tag-based version resolution for Airsoft Prop.

Derives the application version from ``git describe --tags`` at runtime.
For frozen PyInstaller builds, reads a VERSION file placed alongside the
executable during the CI build.
"""

import re
import subprocess
import sys
from pathlib import Path

from src.utils.logger import get_logger
from src.utils.paths import get_project_root

logger = get_logger(__name__)

# Cached version — resolved once, reused for the lifetime of the process.
_cached_version: str | None = None

# Pattern: "1.0.0-3-gabcdef" → groups (tag, commits_ahead, hash)
_DESCRIBE_RE = re.compile(r"^(.+)-(\d+)-g[0-9a-f]+$")


def get_version() -> str:
    """Return the application version string (single source of truth).

    Resolution order:
        1. Frozen build → read ``VERSION`` file next to the executable.
        2. Git repository → ``git describe --tags --always``.
        3. Fallback → ``"unknown"``.

    The leading ``v`` prefix (from tags like ``v1.0.0``) is stripped.
    The result is cached after the first call.

    Returns:
        Version string, e.g. ``"1.0.0"`` or ``"1.0.0-3-gabcdef"``.
    """
    global _cached_version  # noqa: PLW0603
    if _cached_version is not None:
        return _cached_version

    version = _resolve_version()
    _cached_version = version
    logger.info("Resolved application version: %s", version)
    return version


def format_version_short(version: str, max_length: int = 10) -> str:
    """Format a version string for the 20-character LCD display.

    Conversions:
        ``"1.0.0"``              → ``"1.0.0"``  (clean tag, unchanged)
        ``"1.0.0-3-gabcdef"``    → ``"1.0.0+3"`` (shortened)
        ``"abcdef1"``            → ``"abcdef1"``  (hash-only fallback)

    Args:
        version: Full version string from :func:`get_version`.
        max_length: Maximum allowed length (truncated if exceeded).

    Returns:
        A short version string suitable for LCD display.
    """
    match = _DESCRIBE_RE.match(version)
    if match:
        tag, commits_ahead = match.group(1), match.group(2)
        short = f"{tag}+{commits_ahead}"
    else:
        short = version

    if len(short) > max_length:
        short = short[:max_length]
    return short


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_version() -> str:
    """Determine the version from the best available source."""
    # 1. Frozen build: read VERSION file next to the .exe
    if getattr(sys, "frozen", False):
        return _read_version_file()

    # 2. Git repository
    return _git_describe()


def _read_version_file() -> str:
    """Read the VERSION file written during the CI build."""
    version_path = get_project_root() / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
        if version:
            return _strip_v_prefix(version)
    except (OSError, ValueError):
        logger.warning("VERSION file not readable: %s", version_path)
    return "unknown"


def _git_describe() -> str:
    """Run ``git describe --tags --always`` and return the result."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(get_project_root()),
        )
        if result.returncode == 0 and result.stdout.strip():
            return _strip_v_prefix(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("git describe failed — cannot determine version")
    return "unknown"


def _strip_v_prefix(version: str) -> str:
    """Remove a leading 'v' or 'V' from a version string."""
    if version.startswith(("v", "V")):
        return version[1:]
    return version
