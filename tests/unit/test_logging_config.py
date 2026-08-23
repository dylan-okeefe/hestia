"""Tests for logging configuration."""

import logging

from hestia.logging_config import setup_logging


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_verbose_sets_debug(self):
        """Verbose=True sets root logger to DEBUG."""
        initial_level = logging.getLogger().level
        setup_logging(verbose=True)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        root_logger.setLevel(initial_level)

    def test_setup_logging_non_verbose_sets_info(self):
        """Verbose=False sets root logger to INFO."""
        initial_level = logging.getLogger().level
        setup_logging(verbose=False)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        root_logger.setLevel(initial_level)

    def test_setup_logging_installs_stream_handler(self):
        """Setup installs a StreamHandler on the root logger."""
        root_logger = logging.getLogger()
        initial_handlers = list(root_logger.handlers)
        setup_logging(verbose=True)
        # setup_logging clears existing handlers and installs exactly one StreamHandler
        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)
        # Restore original handlers so pytest log capture keeps working
        root_logger.handlers.clear()
        for h in initial_handlers:
            root_logger.addHandler(h)

    def test_setup_logging_idempotent(self):
        """Calling setup multiple times doesn't leave duplicate handlers."""
        root_logger = logging.getLogger()
        initial_handlers = list(root_logger.handlers)
        setup_logging(verbose=True)
        after_first = len(root_logger.handlers)
        setup_logging(verbose=True)
        assert len(root_logger.handlers) == after_first == 1
        # Restore original handlers
        root_logger.handlers.clear()
        for h in initial_handlers:
            root_logger.addHandler(h)
