"""Error Handler Module

This module provides error handling utilities for the gatherers.
"""

import logging
import time
from typing import Callable, Any, Optional, Type, Tuple
import requests

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handles errors and retries for API requests with exponential backoff."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        """Initialize error handler.
        
        Args:
            max_retries: Maximum number of retry attempts
            backoff_factor: Multiplier for exponential backoff delay
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        logger.info(f"ErrorHandler initialized with max_retries={max_retries}, backoff_factor={backoff_factor}")

    def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Execute a function with retry logic and exponential backoff.
        
        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result of the function call
            
        Raises:
            Exception: If all retry attempts fail, raises the last exception
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"Success on attempt {attempt + 1}")
                return result
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries:
                    delay = self.backoff_factor ** attempt
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}): {str(e)}. "
                        f"Retrying in {delay:.2f} seconds..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error: {str(e)}")
                raise
        
        # If we get here, all retries failed
        raise last_exception

    def is_retryable_error(self, exception: Exception) -> bool:
        """Determine if an error is retryable.
        
        Args:
            exception: The exception to check
            
        Returns:
            True if the error should be retried, False otherwise
        """
        # Network errors are retryable
        if isinstance(exception, (requests.exceptions.ConnectionError,
                                 requests.exceptions.Timeout,
                                 requests.exceptions.HTTPError)):
            # Check for specific HTTP status codes
            if hasattr(exception, 'response') and exception.response is not None:
                status_code = exception.response.status_code
                # Retry on server errors (5xx) and rate limiting (429)
                if status_code >= 500 or status_code == 429:
                    return True
                # Don't retry on client errors (4xx) except 429
                if 400 <= status_code < 500:
                    return False
            return True
        
        return False

    def handle_error(
        self,
        exception: Exception,
        context: Optional[str] = None
    ) -> None:
        """Log and handle an error appropriately.
        
        Args:
            exception: The exception to handle
            context: Optional context string describing where the error occurred
        """
        context_str = f" in {context}" if context else ""
        
        if isinstance(exception, requests.exceptions.HTTPError):
            status_code = exception.response.status_code if exception.response else "unknown"
            logger.error(f"HTTP error{context_str}: {status_code} - {str(exception)}")
        elif isinstance(exception, requests.exceptions.ConnectionError):
            logger.error(f"Connection error{context_str}: {str(exception)}")
        elif isinstance(exception, requests.exceptions.Timeout):
            logger.error(f"Timeout error{context_str}: {str(exception)}")
        else:
            logger.error(f"Unexpected error{context_str}: {type(exception).__name__} - {str(exception)}")
