"""Tests for src.utils.logger — get_logger, level changes, rotation, hygiene."""

import ast
import logging
import time
from pathlib import Path

from src.utils.logger import (
    _cleanup_old_logs,
    _rotate_log_file,
    get_logger,
    set_log_level,
)


class TestGetLogger:
    """``get_logger`` is a thin wrapper around ``logging.getLogger``."""

    def test_returns_named_logger(self) -> None:
        log = get_logger("test.module.name")
        assert isinstance(log, logging.Logger)
        assert log.name == "test.module.name"


class TestSetLogLevel:
    """Runtime level change is what the ``logging_level_changed`` event uses."""

    def test_runtime_level_change_is_honored(self) -> None:
        original = logging.getLogger().level
        try:
            set_log_level("DEBUG")
            assert logging.getLogger().level == logging.DEBUG
            set_log_level("WARNING")
            assert logging.getLogger().level == logging.WARNING
        finally:
            logging.getLogger().setLevel(original)


class TestLogRotation:
    """``_rotate_log_file`` + ``_cleanup_old_logs`` keep at most N archives."""

    def test_oldest_archives_deleted_beyond_max_files(
        self, tmp_path: Path
    ) -> None:
        # Create 5 archive files with increasing mtimes.
        archives = []
        for i in range(5):
            f = tmp_path / f"prop.2026-01-0{i + 1}_00-00-00.log"
            f.write_text(f"archive {i}", encoding="utf-8")
            # Stagger mtimes so cleanup has a clear order.
            mtime = time.time() - (5 - i) * 100
            import os
            os.utime(f, (mtime, mtime))
            archives.append(f)

        _cleanup_old_logs(tmp_path, "prop", ".log", max_files=2)

        remaining = sorted(tmp_path.glob("prop.*.log"))
        assert len(remaining) == 2
        # The two newest survive.
        assert archives[3] in remaining
        assert archives[4] in remaining


class TestNoPrintInSrc:
    """Static guard: no ``print()`` calls anywhere under src/.

    AGENTS.md and CLAUDE.md both forbid ``print()`` — use ``get_logger``.
    This test parses every .py file in src/ via ast and fails if any
    bare ``print(...)`` call is found.
    """

    def test_src_has_no_print_calls(self) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent
        src_dir = project_root / "src"
        offenders: list[str] = []
        for py_file in src_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                ):
                    rel = py_file.relative_to(project_root)
                    offenders.append(f"{rel}:{node.lineno}")
        assert not offenders, (
            f"print() calls found in src/ — use get_logger() instead: {offenders}"
        )
