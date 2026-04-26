"""Tests for logging configuration."""

import logging

from hestia.logging_config import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_verbose_sets_debug(self):
        """Verbose=True sets root logger to DEBUG."""
        setup_logging(verbose=True)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_setup_logging_non_verbose_sets_info(self):
        """Verbose=False sets root logger to INFO."""
        setup_logging(verbose=False)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO

    def test_setup_logging_creates_handler(self):
        """Setup creates at least one handler."""
        setup_logging(verbose=True)
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) >= 1

    def test_setup_logging_idempotent(self):
        """Calling setup multiple times doesn't duplicate handlers."""
        setup_logging(verbose=True)
        initial_handler_count = len(logging.getLogger().handlers)
        setup_logging(verbose=True)
        assert len(logging.getLogger().handlers) == initial_handler_count
