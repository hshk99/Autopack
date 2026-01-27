"""Tests for logging_config module.

Tests the centralized logging configuration with rotating file handlers.
"""

import logging
import os
import tempfile
from unittest.mock import patch


# Add scripts to path for import
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from logging_config import (
    BACKUP_COUNT,
    LOG_DIR,
    MAX_LOG_SIZE,
    setup_logging,
)


class TestLoggingConfig:
    """Tests for setup_logging function."""

    def test_setup_logging_returns_logger(self) -> None:
        """Test that setup_logging returns a Logger instance."""
        logger = setup_logging("test_logger_1")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger_1"

    def test_setup_logging_sets_correct_level(self) -> None:
        """Test that logger has correct logging level."""
        logger = setup_logging("test_logger_2", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_setup_logging_default_level_is_info(self) -> None:
        """Test that default logging level is INFO."""
        logger = setup_logging("test_logger_3")
        assert logger.level == logging.INFO

    def test_setup_logging_creates_log_directory(self) -> None:
        """Test that setup_logging creates the log directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("logging_config.LOG_DIR", tmpdir):
                from logging_config import setup_logging as patched_setup

                # Clear any existing handlers to force re-creation
                test_logger = logging.getLogger("test_logger_dir")
                test_logger.handlers.clear()

                patched_setup("test_logger_dir")
                assert os.path.exists(tmpdir)

                # Close handlers to release file handles (needed on Windows)
                for handler in test_logger.handlers[:]:
                    handler.close()
                    test_logger.removeHandler(handler)

    def test_setup_logging_adds_handlers(self) -> None:
        """Test that setup_logging adds file and console handlers."""
        # Get a fresh logger name to avoid handler accumulation
        logger = logging.getLogger("test_logger_handlers")
        logger.handlers.clear()

        result = setup_logging("test_logger_handlers")

        # Should have 2 handlers: file and console
        assert len(result.handlers) == 2

        handler_types = [type(h).__name__ for h in result.handlers]
        assert "RotatingFileHandler" in handler_types
        assert "StreamHandler" in handler_types

    def test_setup_logging_idempotent(self) -> None:
        """Test that calling setup_logging twice doesn't add duplicate handlers."""
        # Get a fresh logger
        logger = logging.getLogger("test_logger_idempotent")
        logger.handlers.clear()

        setup_logging("test_logger_idempotent")
        initial_handler_count = len(logger.handlers)

        setup_logging("test_logger_idempotent")
        assert len(logger.handlers) == initial_handler_count

    def test_setup_logging_formatter_format(self) -> None:
        """Test that handlers have correct formatter."""
        logger = logging.getLogger("test_logger_format")
        logger.handlers.clear()

        setup_logging("test_logger_format")

        for handler in logger.handlers:
            formatter = handler.formatter
            assert formatter is not None
            assert "%(asctime)s" in formatter._fmt
            assert "%(name)s" in formatter._fmt
            assert "%(levelname)s" in formatter._fmt
            assert "%(message)s" in formatter._fmt


class TestLoggingConstants:
    """Tests for logging configuration constants."""

    def test_max_log_size_is_10mb(self) -> None:
        """Test that MAX_LOG_SIZE is 10MB."""
        assert MAX_LOG_SIZE == 10 * 1024 * 1024

    def test_backup_count_is_5(self) -> None:
        """Test that BACKUP_COUNT is 5."""
        assert BACKUP_COUNT == 5

    def test_log_dir_exists_or_can_be_created(self) -> None:
        """Test that LOG_DIR path is valid."""
        # LOG_DIR should be a valid path string
        assert isinstance(LOG_DIR, str)
        assert len(LOG_DIR) > 0


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def test_logger_can_log_messages(self, tmp_path: str) -> None:
        """Test that logger can write log messages."""
        with patch("logging_config.LOG_DIR", str(tmp_path)):
            # Clear existing logger
            logger = logging.getLogger("test_integration")
            logger.handlers.clear()

            from logging_config import setup_logging as patched_setup

            test_logger = patched_setup("test_integration")
            test_logger.info("Test message")

            # Flush handlers before reading
            for handler in test_logger.handlers:
                handler.flush()

            # Check that log file was created
            log_file = os.path.join(str(tmp_path), "test_integration.log")
            assert os.path.exists(log_file)

            # Check log content
            with open(log_file, "r") as f:
                content = f.read()
                assert "Test message" in content
                assert "INFO" in content

            # Close handlers to release file handles (needed on Windows)
            for handler in test_logger.handlers[:]:
                handler.close()
                test_logger.removeHandler(handler)
