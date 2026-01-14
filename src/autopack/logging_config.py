"""
Centralized Logging Configuration with Structured Logging Support

Provides a centralized logging configuration to prevent root clutter.
Supports both traditional text logging and structured JSON logging with correlation IDs.

Default log directory: archive/diagnostics/logs/ (for main project)
                        .autonomous_runs/<project>/archive/diagnostics/logs/ (for sub-projects)

Usage:
    from autopack.logging_config import configure_logging, setup_structured_logging, correlation_id_var

    # Traditional logging
    configure_logging(run_id="build-147", project_id="autopack")

    # Structured logging (for API servers)
    setup_structured_logging()

    # Use correlation IDs in middleware
    from autopack.logging_config import correlation_id_var
    correlation_id_var.set("request-123")

Environment Variables:
    AUTOPACK_LOG_DIR - Override default log directory
    AUTOPACK_LOG_LEVEL - Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional

# Context var for correlation ID (used in structured logging)
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON formatter with correlation ID for structured logging.

    Formats log records as JSON with correlation ID support for distributed tracing.
    Each log entry includes timestamp, level, logger name, message, correlation ID,
    and any extra fields added to the log record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: The log record to format

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (custom log attributes)
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
            "message",
        }

        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_data[key] = value

        return json.dumps(log_data)


def setup_structured_logging(log_level: str = "INFO") -> None:
    """Configure structured JSON logging for the application.

    This function configures the root logger to use JSON-formatted output
    with correlation ID support. Useful for API servers and services
    that need structured logging for observability.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Example:
        from autopack.logging_config import setup_structured_logging, correlation_id_var
        import uuid

        setup_structured_logging()

        # In request handler:
        correlation_id_var.set(str(uuid.uuid4()))
        logger.info("Processing request")  # Will include correlation_id in JSON output
    """
    # Get or create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create and configure stream handler with structured formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    handler.setLevel(getattr(logging, log_level.upper()))

    root_logger.addHandler(handler)


def get_default_log_dir(workspace: Optional[Path] = None, project_id: Optional[str] = None) -> Path:
    """
    Get the default log directory for the project.

    Args:
        workspace: Repository root (defaults to current working directory)
        project_id: Project identifier (e.g., "autopack", "file-organizer-app-v1")

    Returns:
        Default log directory path
    """
    if workspace is None:
        workspace = Path.cwd()

    # Check for environment variable override
    if "AUTOPACK_LOG_DIR" in os.environ:
        return Path(os.environ["AUTOPACK_LOG_DIR"])

    # Default log directory based on project
    if project_id == "autopack" or project_id is None:
        # Main project: archive/diagnostics/logs/
        return workspace / "archive" / "diagnostics" / "logs"
    else:
        # Sub-project: .autonomous_runs/{project}/archive/diagnostics/logs/
        return workspace / ".autonomous_runs" / project_id / "archive" / "diagnostics" / "logs"


def configure_logging(
    run_id: Optional[str] = None,
    project_id: Optional[str] = None,
    workspace: Optional[Path] = None,
    log_dir: Optional[Path] = None,
    log_level: Optional[str] = None,
    log_to_console: bool = True,
    log_to_file: bool = True,
    log_filename: Optional[str] = None,
) -> logging.Logger:
    """
    Configure centralized logging for Autopack.

    Args:
        run_id: Run identifier (used in log filename if not specified)
        project_id: Project identifier (e.g., "autopack", "file-organizer-app-v1")
        workspace: Repository root (defaults to current working directory)
        log_dir: Log directory (overrides default)
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_console: Whether to log to console
        log_to_file: Whether to log to file
        log_filename: Custom log filename (overrides run_id-based naming)

    Returns:
        Configured logger instance
    """
    # Get or create logger
    logger = logging.getLogger("autopack")

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Set log level
    if log_level is None:
        log_level = os.environ.get("AUTOPACK_LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Create formatter (Windows-safe, no emoji)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        # Determine log directory
        if log_dir is None:
            log_dir = get_default_log_dir(workspace, project_id)

        # Create log directory if it doesn't exist
        log_dir.mkdir(parents=True, exist_ok=True)

        # Determine log filename
        if log_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if run_id:
                log_filename = f"{run_id}_{timestamp}.log"
            else:
                log_filename = f"autopack_{timestamp}.log"

        log_path = log_dir / log_filename

        # Create file handler with UTF-8 encoding (Windows-safe)
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"Logging to: {log_path}")

    return logger


def get_safe_log_path(
    filename: str,
    workspace: Optional[Path] = None,
    project_id: Optional[str] = None,
) -> Path:
    """
    Get a safe log path to prevent root clutter.

    Use this helper for scripts that write logs directly.

    Args:
        filename: Log filename (e.g., "batch_drain.log")
        workspace: Repository root (defaults to current working directory)
        project_id: Project identifier

    Returns:
        Safe log path in archive/diagnostics/logs/

    Example:
        log_path = get_safe_log_path("batch_drain.log")
        with open(log_path, "w") as f:
            f.write("log content...")
    """
    log_dir = get_default_log_dir(workspace, project_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / filename


# Convenience function for quick setup
def setup_logging(run_id: Optional[str] = None, project_id: Optional[str] = None) -> logging.Logger:
    """
    Quick setup for centralized logging with sensible defaults.

    Args:
        run_id: Run identifier
        project_id: Project identifier

    Returns:
        Configured logger

    Example:
        from autopack.logging_config import setup_logging

        logger = setup_logging(run_id="build-147")
        logger.info("Starting execution...")
    """
    return configure_logging(run_id=run_id, project_id=project_id)
