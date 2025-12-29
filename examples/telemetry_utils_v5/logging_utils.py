"""Logging utility functions for application logging.

This module provides common logging utilities including:
- setup_logger: Configure and return a logger with specified settings
- log_to_file: Configure file-based logging for a logger
- get_logger: Get or create a logger instance by name
"""

import logging
from pathlib import Path
from typing import Optional, Union


def setup_logger(
    name: str,
    level: Union[int, str] = logging.INFO,
    format_string: Optional[str] = None,
    datefmt: Optional[str] = None,
) -> logging.Logger:
    """Configure and return a logger with specified settings.
    
    Creates or retrieves a logger with the given name and configures it
    with the specified log level and format. If no format is provided,
    uses a default format with timestamp, level, and message.
    
    Args:
        name: Name of the logger to create/configure
        level: Logging level (e.g., logging.DEBUG, logging.INFO, or string like 'DEBUG')
        format_string: Optional custom format string for log messages
        datefmt: Optional date format string (default: '%Y-%m-%d %H:%M:%S')
        
    Returns:
        Configured Logger instance
        
    Examples:
        >>> logger = setup_logger('my_app')
        >>> logger.info('Application started')
        >>> logger = setup_logger('debug_logger', level=logging.DEBUG)
        >>> logger = setup_logger('custom', format_string='%(levelname)s: %(message)s')
        >>> logger = setup_logger('app', level='WARNING')
    """
    # Get or create logger
    logger = logging.getLogger(name)
    
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # Set format
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    if datefmt is None:
        datefmt = '%Y-%m-%d %H:%M:%S'
    
    formatter = logging.Formatter(format_string, datefmt=datefmt)
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
    
    return logger


def log_to_file(
    logger: logging.Logger,
    filepath: Union[str, Path],
    level: Optional[Union[int, str]] = None,
    format_string: Optional[str] = None,
    datefmt: Optional[str] = None,
    mode: str = 'a',
    encoding: str = 'utf-8',
    create_dirs: bool = True,
) -> None:
    """Configure file-based logging for a logger.
    
    Adds a file handler to an existing logger to write log messages to a file.
    Can optionally create parent directories if they don't exist.
    
    Args:
        logger: Logger instance to configure
        filepath: Path to the log file (string or Path object)
        level: Optional logging level for file handler (uses logger's level if None)
        format_string: Optional custom format string for log messages
        datefmt: Optional date format string (default: '%Y-%m-%d %H:%M:%S')
        mode: File open mode - 'a' for append, 'w' for overwrite (default: 'a')
        encoding: Character encoding for the log file (default: 'utf-8')
        create_dirs: If True, create parent directories if they don't exist
        
    Raises:
        IOError: If there is an error creating directories or opening the file
        PermissionError: If the file cannot be written due to permissions
        
    Examples:
        >>> logger = setup_logger('my_app')
        >>> log_to_file(logger, 'logs/app.log')
        >>> log_to_file(logger, 'debug.log', level=logging.DEBUG)
        >>> log_to_file(logger, '/var/log/app.log', mode='w', create_dirs=True)
        >>> log_to_file(logger, 'app.log', format_string='%(levelname)s: %(message)s')
    """
    file_path = Path(filepath)
    
    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {filepath}: {e}")
    
    # Determine log level for file handler
    if level is None:
        level = logger.level
    elif isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    
    # Create file handler
    try:
        file_handler = logging.FileHandler(file_path, mode=mode, encoding=encoding)
        file_handler.setLevel(level)
        
        # Set format
        if format_string is None:
            format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        if datefmt is None:
            datefmt = '%Y-%m-%d %H:%M:%S'
        
        formatter = logging.Formatter(format_string, datefmt=datefmt)
        file_handler.setFormatter(formatter)
        
        # Add handler to logger
        logger.addHandler(file_handler)
        
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {filepath}")
    except Exception as e:
        raise IOError(f"Error configuring file logging for {filepath}: {e}")


def get_logger(
    name: str,
    level: Union[int, str] = logging.INFO,
    setup_if_new: bool = True,
) -> logging.Logger:
    """Get or create a logger instance by name.
    
    Retrieves an existing logger by name, or creates and configures a new one
    if it doesn't exist. If the logger already exists and has handlers, it is
    returned as-is. If it's new or has no handlers and setup_if_new is True,
    it will be configured with default settings.
    
    Args:
        name: Name of the logger to get or create
        level: Logging level to use if creating a new logger (default: logging.INFO)
        setup_if_new: If True, configure new loggers with default settings
        
    Returns:
        Logger instance
        
    Examples:
        >>> logger = get_logger('my_app')
        >>> logger.info('Hello, World!')
        >>> logger2 = get_logger('my_app')  # Returns the same logger
        >>> debug_logger = get_logger('debug', level=logging.DEBUG)
        >>> raw_logger = get_logger('raw', setup_if_new=False)  # No default config
    """
    logger = logging.getLogger(name)
    
    # If logger has no handlers and setup_if_new is True, configure it
    if setup_if_new and not logger.handlers:
        # Convert string level to int if needed
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        
        logger.setLevel(level)
        
        # Create console handler with default format
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        logger.propagate = False
    
    return logger
