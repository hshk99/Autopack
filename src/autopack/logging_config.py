"""
Centralized Logging Configuration

Provides a centralized logging configuration to prevent root clutter.
Default log directory: archive/diagnostics/logs/ (for main project)
                        .autonomous_runs/<project>/archive/diagnostics/logs/ (for sub-projects)

Usage:
    from autopack.logging_config import configure_logging

    # In main project
    configure_logging(run_id="build-147", project_id="autopack")

    # In sub-project
    configure_logging(run_id="phase-1", project_id="file-organizer-app-v1")

Environment Variables:
    AUTOPACK_LOG_DIR - Override default log directory
    AUTOPACK_LOG_LEVEL - Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_default_log_dir(
    workspace: Optional[Path] = None,
    project_id: Optional[str] = None
) -> Path:
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
