"""Error Handler Module

This module provides error handling utilities for the gatherers.
"""

import logging
import time

logger = logging.getLogger(__name__)

class ErrorHandler:
    """Handles errors and retries for API requests."""

    def __init__(self, max_retries=3, backoff_factor=2):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def handle_error(self, func, *args, **kwargs):
        """Executes a function with error handling and retries.

        Args:
            func (callable): The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful, None otherwise.
        """
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error occurred: {e}")
                retries += 1
                sleep_time = self.backoff_factor ** retries
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
        logger.error("Max retries reached. Operation failed.")
        return None

    def log_error(self, error):
        """Logs an error message.

        Args:
            error (Exception): The error to log.
        """
        logger.error(f"An error occurred: {error}")
