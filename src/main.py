"""Entry point for the Airsoft Prop application.

Usage:
    python -m src.main             # Run with real hardware (on Raspberry Pi)
    python -m src.main --mock      # Run with mock HAL (desktop testing)
    python -m src.main --debug     # Enable debug logging
    python -m src.main --no-log-file  # Disable file logging (stderr only)
"""

import argparse
import atexit
import faulthandler
import sys
from pathlib import Path
from typing import TextIO

from src.utils.config import load_yaml, _load_custom_yaml
from src.utils.logger import setup_logging, get_logger
from src.utils.paths import get_project_root

# Watchdog interval for faulthandler.dump_traceback_later. If the main loop
# hangs in a C call (e.g. RPi.GPIO read or LCD I2C write), a traceback of all
# threads is dumped every N seconds to the crash log so we can see WHERE it
# is stuck. Cheap (one wakeup + one write) and signal-safe.
_FAULT_WATCHDOG_SECONDS: int = 10


def _enable_faulthandler(log_dir: Path) -> TextIO | None:
    """Arm faulthandler so fatal native signals dump a Python traceback.

    Captures SIGSEGV / SIGBUS / SIGFPE / SIGABRT / SIGILL via signal-safe
    raw writes into ``logs/prop.crash.log``. Without this, a kernel-level
    fault in a C extension (gpiozero, RPi.GPIO, RPLCD) kills the process
    before Python's ``sys.excepthook`` can run, leaving prop.log silent.

    Also schedules a repeating watchdog dump so a hung main loop produces
    a traceback every ``_FAULT_WATCHDOG_SECONDS`` while it is stuck.

    Args:
        log_dir: Directory where ``prop.crash.log`` will be created.

    Returns:
        The open crash-log file object (kept alive for the process
        lifetime), or ``None`` if the file could not be opened.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        crash_path = log_dir / "prop.crash.log"
        crash_fd = open(crash_path, "a", buffering=1, encoding="utf-8")
    except OSError:
        # Fall back to stderr — better than nothing.
        faulthandler.enable(file=sys.stderr, all_threads=True)
        return None

    # Header so multiple sessions are distinguishable in the same file.
    import datetime
    crash_fd.write(
        f"\n=== faulthandler armed at "
        f"{datetime.datetime.now().isoformat(timespec='seconds')} ===\n",
    )
    crash_fd.flush()

    faulthandler.enable(file=crash_fd, all_threads=True)
    faulthandler.dump_traceback_later(
        _FAULT_WATCHDOG_SECONDS, repeat=True, file=crash_fd,
    )

    # Make sure the watchdog timer is cancelled on a clean exit so pytest
    # and dev runs don't leave a daemon timer behind.
    atexit.register(faulthandler.cancel_dump_traceback_later)
    return crash_fd


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Airsoft Prop — Raspberry Pi game device",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock HAL implementations for desktop testing",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Override log file name (default: from config or 'prop.log')",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Disable file logging, output to stderr only",
    )
    return parser.parse_args()


def main() -> None:
    """Application entry point."""
    args = parse_args()

    # Load logging config from YAML before full App/Config initialization.
    # Merge custom/user.yaml overrides so that user-configured log levels
    # take effect immediately at startup.
    defaults = load_yaml("default.yaml")
    user_overrides = _load_custom_yaml("user.yaml")
    log_cfg = {**defaults.get("logging", {}), **user_overrides.get("logging", {})}

    # CLI flags override YAML values.
    log_level = "DEBUG" if args.debug else log_cfg.get("level", "INFO")
    log_dir = log_cfg.get("log_dir", "logs")
    max_files = log_cfg.get("max_files", 10)

    if args.no_log_file:
        log_file = None
    else:
        log_file = args.log_file or log_cfg.get("log_file", "prop.log")

    # Resolve absolute log directory once so faulthandler and setup_logging
    # write to the same place.
    log_dir_path = Path(log_dir)
    if not log_dir_path.is_absolute():
        log_dir_path = get_project_root() / log_dir_path

    # Arm faulthandler BEFORE setup_logging so any crash during HAL init
    # (which happens later in App.init) is also captured.
    crash_fd = _enable_faulthandler(log_dir_path)

    # Configure logging (always to file unless --no-log-file).
    setup_logging(
        level=log_level,
        log_file=log_file,
        log_dir=log_dir,
        max_files=max_files,
    )

    logger = get_logger(__name__)
    if crash_fd is not None:
        logger.info(
            "faulthandler armed (crash log: %s, watchdog: %ds)",
            crash_fd.name,
            _FAULT_WATCHDOG_SECONDS,
        )
    else:
        logger.warning("faulthandler enabled on stderr only (no crash log)")
    logger.info("Starting Airsoft Prop (mock=%s, debug=%s)", args.mock, args.debug)

    # Create and run the app.
    from src.app import App

    app = App(mock=args.mock)
    try:
        app.init()
        app.run()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
