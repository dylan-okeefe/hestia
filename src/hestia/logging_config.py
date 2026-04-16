"""Centralized logging configuration for Hestia."""

import logging
import sys


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger with consistent formatting.

    Args:
        verbose: If True, set level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates if called multiple times
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
