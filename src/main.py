"""Entry point for the Airsoft Prop application.

Usage:
    python -m src.main             # Run with real hardware (on Raspberry Pi)
    python -m src.main --mock      # Run with mock HAL (desktop testing)
    python -m src.main --debug     # Enable debug logging
    python -m src.main --no-log-file  # Disable file logging (stderr only)
"""

import argparse
import sys

from src.utils.config import load_yaml, _load_custom_yaml
from src.utils.logger import setup_logging, get_logger


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

    # Configure logging (always to file unless --no-log-file).
    setup_logging(
        level=log_level,
        log_file=log_file,
        log_dir=log_dir,
        max_files=max_files,
    )

    logger = get_logger(__name__)
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
