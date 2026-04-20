"""Git-based update system for Airsoft Prop.

Checks for updates via git fetch and applies them with git pull.
"""

import subprocess
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import get_logger
from src.utils.version import _strip_v_prefix

logger = get_logger(__name__)


@dataclass
class UpdateInfo:
    """Information about available updates."""
    current_version: str
    remote_version: Optional[str]
    update_available: bool
    commits_behind: int
    error: Optional[str] = None


def _short_version(version: str) -> str:
    """Strip the git hash suffix (e.g. 1.0.0-37-g66cf51b -> 1.0.0-37)."""
    parts = version.rsplit("-g", 1)
    return parts[0] if len(parts) == 2 and parts[1].isalnum() else version


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    """Run a git command and return (returncode, stdout).

    Args:
        args: Git command arguments.
        cwd: Working directory.

    Returns:
        Tuple of (return_code, stdout_text).
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("Git command timed out: git %s", " ".join(args))
        return -1, ""
    except FileNotFoundError:
        logger.error("Git not found in PATH")
        return -1, ""


def check_internet() -> bool:
    """Check if we can reach the git remote.

    Returns:
        True if the remote is reachable.
    """
    code, _ = _run_git(["ls-remote", "--exit-code", "--quiet", "origin", "HEAD"])
    return code == 0


def check_for_updates(project_root: str) -> UpdateInfo:
    """Check if updates are available from the git remote.

    Args:
        project_root: Path to the project root directory.

    Returns:
        UpdateInfo with current and remote version details.
    """
    # Get current version from git tags
    code, current_desc = _run_git(
        ["describe", "--tags", "--always"], cwd=project_root
    )
    if code != 0:
        return UpdateInfo(
            current_version="unknown",
            remote_version=None,
            update_available=False,
            commits_behind=0,
            error="Not a git repository",
        )
    current_version = _strip_v_prefix(current_desc)

    # Check connectivity before touching the object store
    if not check_internet():
        return UpdateInfo(
            current_version=current_version,
            remote_version=None,
            update_available=False,
            commits_behind=0,
            error="Cannot reach remote",
        )

    # Fetch from remote (including tags)
    code, _ = _run_git(["fetch", "--tags", "origin"], cwd=project_root)
    if code != 0:
        return UpdateInfo(
            current_version=current_version,
            remote_version=None,
            update_available=False,
            commits_behind=0,
            error="Cannot reach remote",
        )

    # Get remote version from git tags
    code, remote_desc = _run_git(
        ["describe", "--tags", "--always", "origin/main"], cwd=project_root
    )
    if code != 0:
        # Try master branch as fallback
        code, remote_desc = _run_git(
            ["describe", "--tags", "--always", "origin/master"], cwd=project_root
        )
        if code != 0:
            return UpdateInfo(
                current_version=current_version,
                remote_version=None,
                update_available=False,
                commits_behind=0,
                error="Cannot determine remote branch",
            )
    remote_version = _strip_v_prefix(remote_desc)

    # Count commits behind
    code, count_str = _run_git(
        ["rev-list", "--count", f"HEAD..origin/main"], cwd=project_root
    )
    if code != 0:
        code, count_str = _run_git(
            ["rev-list", "--count", f"HEAD..origin/master"], cwd=project_root
        )

    commits_behind = int(count_str) if code == 0 and count_str.isdigit() else 0

    return UpdateInfo(
        current_version=current_version,
        remote_version=remote_version,
        update_available=current_version != remote_version and commits_behind > 0,
        commits_behind=commits_behind,
    )


def apply_update(project_root: str) -> tuple[bool, str]:
    """Apply pending updates via git pull and pip install.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Tuple of (success, message).
    """
    logger.info("Applying update...")

    # Fetch tags explicitly so git describe resolves the new version correctly.
    _run_git(["fetch", "--tags", "origin"], cwd=project_root)

    # Git pull
    code, output = _run_git(["pull", "origin", "main"], cwd=project_root)
    if code != 0:
        code, output = _run_git(["pull", "origin", "master"], cwd=project_root)
        if code != 0:
            logger.error("Git pull failed: %s", output)
            return False, f"Git pull failed: {output}"

    # Update pip dependencies
    try:
        result = subprocess.run(
            ["pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_root,
        )
        if result.returncode != 0:
            logger.warning("pip install had issues: %s", result.stderr)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Could not update pip packages: %s", e)

    # Refresh VERSION file so the app reads the correct version on next boot.
    code, new_desc = _run_git(["describe", "--tags", "--always"], cwd=project_root)
    if code == 0 and new_desc:
        try:
            from pathlib import Path
            (Path(project_root) / "VERSION").write_text(
                _strip_v_prefix(new_desc) + "\n", encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Could not update VERSION file: %s", e)

    logger.info("Update applied successfully")
    return True, "Update applied successfully. Restart required."
