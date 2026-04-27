"""Logging configuration for Airsoft Prop.

Provides centralized logging with per-session log files, automatic rotation
on startup, and retention-based cleanup. Captures uncaught exceptions
(main thread + child threads), Python warnings, and stray stderr output.

All modules should use:
    from src.utils.logger import get_logger
    logger = get_logger(__name__)
"""

import atexit
import datetime
import logging
import sys
import threading
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_initialized = False

# Keep a reference to the real stderr before any redirect.
_original_stderr = sys.stderr


# ------------------------------------------------------------------
# Log rotation helpers
# ------------------------------------------------------------------

def _rotate_log_file(log_path: Path, max_files: int) -> None:
    """Rotate an existing log file to a timestamped archive.

    If *log_path* exists it is renamed to
    ``<stem>.<mtime_timestamp><suffix>`` (e.g. ``prop.2026-04-06_14-30-22.log``).
    Afterwards the oldest archives beyond *max_files* are deleted.

    Args:
        log_path: Path to the current log file.
        max_files: Maximum number of archived log files to keep.
    """
    if not log_path.exists():
        return

    # Use the file's modification time so the archive reflects when the
    # session actually ran, not when the next session starts.
    mtime = log_path.stat().st_mtime
    ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d_%H-%M-%S")
    archive_name = f"{log_path.stem}.{ts}{log_path.suffix}"
    archive_path = log_path.parent / archive_name

    # Avoid overwriting if two sessions start in the same second.
    counter = 1
    while archive_path.exists():
        archive_name = f"{log_path.stem}.{ts}_{counter}{log_path.suffix}"
        archive_path = log_path.parent / archive_name
        counter += 1

    log_path.rename(archive_path)
    _cleanup_old_logs(log_path.parent, log_path.stem, log_path.suffix, max_files)


def _cleanup_old_logs(
    log_dir: Path, stem: str, suffix: str, max_files: int,
) -> None:
    """Delete the oldest archived log files beyond *max_files*.

    Archives are identified by the pattern ``<stem>.*<suffix>`` and sorted
    by modification time (oldest first).
    """
    archives = sorted(
        log_dir.glob(f"{stem}.*{suffix}"),
        key=lambda p: p.stat().st_mtime,
    )
    while len(archives) > max_files:
        oldest = archives.pop(0)
        try:
            oldest.unlink()
        except OSError:
            pass  # Best-effort cleanup


# ------------------------------------------------------------------
# Flushing file handler
# ------------------------------------------------------------------

class _FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes the stream after every record.

    The default FileHandler buffers writes. If systemd SIGKILLs the
    process (e.g. after TimeoutStopSec on a hang) the last log lines
    never reach disk, leaving prop.log silent for the most interesting
    moment. Flushing per record is cheap at this app's log volume and
    guarantees the final entry is on disk before any kill.
    """

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        try:
            self.flush()
        except Exception:  # noqa: BLE001 — never let logging break the app
            pass


# ------------------------------------------------------------------
# Stderr / stdout capture
# ------------------------------------------------------------------

class _LoggerWriter:
    """File-like wrapper that forwards ``write()`` calls to a logger.

    Used to redirect ``sys.stderr`` so that any stray output from
    third-party libraries is captured in the log file.
    """

    def __init__(self, logger_inst: logging.Logger, level: int = logging.WARNING) -> None:
        self._logger = logger_inst
        self._level = level

    def write(self, message: str) -> int:
        if message and message.strip():
            self._logger.log(self._level, message.rstrip())
        return len(message) if message else 0

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        # Some libraries (e.g. subprocess) need a real fd — fall back to
        # the original stderr fd.
        return _original_stderr.fileno()

    def isatty(self) -> bool:
        return False


# ------------------------------------------------------------------
# Exception hooks
# ------------------------------------------------------------------

def _uncaught_exception_handler(
    exc_type: type,
    exc_value: BaseException,
    exc_tb: object,
) -> None:
    """``sys.excepthook`` replacement that logs uncaught exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.getLogger("UNCAUGHT").critical(
        "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb),
    )


def _thread_exception_handler(args: threading.ExceptHookArgs) -> None:
    """``threading.excepthook`` replacement for uncaught thread exceptions."""
    if issubclass(args.exc_type, SystemExit):
        return
    thread_name = args.thread.name if args.thread else "unknown"
    logging.getLogger("UNCAUGHT").critical(
        "Uncaught exception in thread '%s'",
        thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    log_dir: str | None = None,
    max_files: int = 10,
    console: bool | None = None,
) -> None:
    """Configure the root logger for the application.

    Args:
        level: Log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        log_file: Log file name (e.g. ``'prop.log'``). When ``None`` no
            file handler is created.
        log_dir: Directory for log files. Relative paths are resolved
            against the project root. Defaults to ``'logs'``.
        max_files: How many archived log files to keep. The current
            session file does not count towards this limit.
        console: If ``True`` always add a stderr handler. Defaults to
            ``True`` when *log_file* is ``None``, ``False`` otherwise
            (to keep the mock display clean).
    """
    global _initialized
    if _initialized:
        return

    # Resolve log directory relative to project root.
    from src.utils.paths import get_project_root
    project_root = get_project_root()
    if log_dir is None:
        log_dir_path = project_root / "logs"
    else:
        log_dir_path = Path(log_dir)
        if not log_dir_path.is_absolute():
            log_dir_path = project_root / log_dir_path

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    # Determine whether to log to console.
    if console is None:
        console = log_file is None

    # Console handler (stderr) — skip when logging to file so the
    # mock display can use the terminal without interference.
    if console:
        stderr_handler = logging.StreamHandler(_original_stderr)
        stderr_handler.setFormatter(formatter)
        root.addHandler(stderr_handler)

    # File handler with rotation.
    if log_file:
        log_dir_path.mkdir(parents=True, exist_ok=True)
        full_path = log_dir_path / log_file

        # Rotate previous session's log to a timestamped archive.
        _rotate_log_file(full_path, max_files)

        file_handler = _FlushingFileHandler(str(full_path), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        # Redirect stderr so stray output from libraries is captured.
        sys.stderr = _LoggerWriter(  # type: ignore[assignment]
            logging.getLogger("stderr"), logging.WARNING,
        )

    # Capture Python warnings through the logging system.
    logging.captureWarnings(True)

    # Install exception hooks.
    sys.excepthook = _uncaught_exception_handler
    threading.excepthook = _thread_exception_handler

    # Belt and suspenders: ensure every handler is flushed and closed on
    # interpreter shutdown. logging.shutdown is idempotent.
    atexit.register(logging.shutdown)

    _initialized = True


def set_log_level(level: str) -> None:
    """Change the root logger level at runtime.

    Args:
        level: Log level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
    """
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric)
    logging.getLogger(__name__).info("Log level changed to %s", level.upper())


def get_logger(name: str) -> logging.Logger:
    """Get a named logger.

    Args:
        name: Logger name (typically ``__name__``).

    Returns:
        Configured ``Logger`` instance.
    """
    return logging.getLogger(name)
