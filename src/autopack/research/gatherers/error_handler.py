"""Error handler with retry budget enforcement for research phase (IMP-RELIABILITY-003).

This module provides error handling for research gatherers with:
- Retry budget enforcement (max 3 retries per agent)
- Exponential backoff with 60 second ceiling
- Fallback to cached results when retries exhausted
- Comprehensive logging of retry exhaustion events
"""

import logging
import time
from typing import Any, Callable, Optional, TypeVar

import requests

from autopack.research.gatherers.rate_limiter import RetryBudget

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryBudgetExhaustedError(Exception):
    """Raised when retry budget is exhausted and no cached fallback is available."""

    def __init__(
        self,
        message: str = "Retry budget exhausted",
        total_retries: int = 0,
        budget_limit: int = 3,
        last_error: Optional[Exception] = None,
    ):
        self.total_retries = total_retries
        self.budget_limit = budget_limit
        self.last_error = last_error
        super().__init__(
            f"{message}: {total_retries}/{budget_limit} retries exhausted. "
            f"Last error: {last_error}"
        )


class ErrorHandler:
    """Handles errors for gatherers with retry logic, budget enforcement, and caching.

    Features (IMP-RELIABILITY-003):
    - Max 3 retries per agent (configurable)
    - Exponential backoff ceiling (60s max)
    - Fallback to cached results when retries exhausted
    - Logging of exhausted retries for monitoring
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        base_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        cache_fallback_enabled: bool = True,
    ):
        """Initialize error handler with retry budget.

        Args:
            max_retries: Maximum number of retries allowed (default: 3 per IMP-RELIABILITY-003)
            backoff_factor: Multiplier for exponential backoff (alias for backoff_multiplier)
            base_backoff_seconds: Base backoff time in seconds
            max_backoff_seconds: Maximum backoff time (60s ceiling per IMP-RELIABILITY-003)
            cache_fallback_enabled: Whether to use cached results as fallback
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.cache_fallback_enabled = cache_fallback_enabled

        # Create retry budget for tracking
        self._retry_budget = RetryBudget(
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
            backoff_multiplier=backoff_factor,
        )

        # Cache for fallback results
        self._cache: dict[str, Any] = {}

    def execute_with_retry(
        self,
        func: Callable[..., T],
        *args: Any,
        cache_key: Optional[str] = None,
        **kwargs: Any,
    ) -> T:
        """Execute a function with retry logic and optional cache fallback.

        Args:
            func: The function to execute.
            *args: Positional arguments for the function.
            cache_key: Optional key for caching results (enables cache fallback)
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful.

        Raises:
            Exception: Re-raises the last exception if all retries fail and no cache fallback
        """
        retries = 0
        last_error: Optional[Exception] = None
        func_name = getattr(func, "__name__", str(func))

        while retries < self.max_retries:
            try:
                result = func(*args, **kwargs)

                # Cache successful result if cache_key provided
                if cache_key is not None:
                    self._cache[cache_key] = result
                    logger.debug(f"Cached result for key: {cache_key}")

                # Log successful recovery if this was a retry
                if retries > 0:
                    logger.info(
                        f"[RETRY_SUCCESS] Function {func_name} succeeded after "
                        f"{retries} retries"
                    )

                return result

            except Exception as e:
                last_error = e

                # Check if error is retryable
                if not self.is_retryable_error(e):
                    logger.debug(f"Non-retryable error for {func_name}: {e}")
                    raise

                retries += 1

                # Calculate backoff time with ceiling
                backoff_time = min(
                    self.base_backoff_seconds * (self.backoff_factor ** (retries - 1)),
                    self.max_backoff_seconds,
                )

                logger.warning(
                    f"[RETRY_ATTEMPT] Function {func_name} failed (attempt {retries}/{self.max_retries}). "
                    f"Error: {e}. Backing off for {backoff_time:.2f}s"
                )

                # Wait with backoff before next retry
                time.sleep(backoff_time)

        # Retries exhausted - log exhaustion event (IMP-RELIABILITY-003 requirement)
        self._log_retry_exhaustion(func_name, last_error, retries)

        # Try cache fallback if enabled and available
        if self.cache_fallback_enabled and cache_key is not None:
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                logger.warning(
                    f"[RETRY_FALLBACK] Using cached result for {func_name} "
                    f"(cache_key: {cache_key}) after {retries} failed retries"
                )
                return cached_result

        # No cache available - re-raise the last error
        logger.error(
            f"[RETRY_EXHAUSTED] Max retries ({self.max_retries}) reached for {func_name}. "
            f"No cached fallback available. Re-raising last error."
        )
        if last_error:
            raise last_error
        raise RuntimeError(f"All retries exhausted for {func_name}")

    def handle_error(
        self,
        func_or_error: Any,
        *args: Any,
        cache_key: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Any]:
        """Handle errors with retry logic or log an error directly.

        This method provides two modes of operation for backward compatibility:
        1. If first argument is an Exception, it logs the error (legacy mode)
        2. If first argument is callable, it executes with retries and returns None on failure

        Args:
            func_or_error: Either a callable to execute or an Exception to log
            *args: Arguments - either context string (for Exception) or function args
            cache_key: Optional key for caching results (only for callable mode)
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function if successful, None if failed (callable mode)
            None (Exception logging mode)
        """
        # Legacy mode: handle_error(exception, context)
        if isinstance(func_or_error, Exception):
            error = func_or_error
            context = args[0] if args else "unknown context"
            self._log_error(error, context)
            return None

        # New mode: handle_error(func, *args, **kwargs)
        func = func_or_error
        func_name = getattr(func, "__name__", str(func))

        try:
            return self.execute_with_retry(func, *args, cache_key=cache_key, **kwargs)
        except Exception as e:
            logger.error(f"[HANDLE_ERROR] Function {func_name} failed after all retries: {e}")
            return None

    def _log_error(self, error: Exception, context: str) -> None:
        """Log an error with context.

        Args:
            error: The exception to log
            context: Context information about where the error occurred
        """
        error_type = type(error).__name__

        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", "unknown") if response else "unknown"
            logger.warning(f"[HTTP_ERROR] {context}: HTTP {status_code} - {error}")
        elif isinstance(error, requests.exceptions.ConnectionError):
            logger.warning(f"[CONNECTION_ERROR] {context}: {error}")
        elif isinstance(error, requests.exceptions.Timeout):
            logger.warning(f"[TIMEOUT_ERROR] {context}: {error}")
        else:
            logger.warning(f"[{error_type.upper()}] {context}: {error}")

    def is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable.

        Args:
            error: The exception to check

        Returns:
            True if the error should trigger a retry, False otherwise
        """
        # Connection and timeout errors are always retryable
        if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True

        # HTTP errors: only retry on 429 (rate limit) and 5xx (server errors)
        if isinstance(error, requests.exceptions.HTTPError):
            response = getattr(error, "response", None)
            if response is not None:
                status_code = getattr(response, "status_code", 0)
                # Retry on 429 (rate limit) and 5xx (server errors)
                return status_code == 429 or status_code >= 500
            return False

        # Other request exceptions may be retryable
        if isinstance(error, requests.exceptions.RequestException):
            return True

        # All other errors are not retryable
        return False

    def _log_retry_exhaustion(
        self,
        func_name: str,
        last_error: Optional[Exception],
        total_retries: int,
    ) -> None:
        """Log detailed information when retry budget is exhausted.

        This is a key monitoring point for IMP-RELIABILITY-003 to track
        when research agents are hitting retry limits.

        Args:
            func_name: Name of the function that failed
            last_error: The last exception that occurred
            total_retries: Total number of retries attempted
        """
        error_type = type(last_error).__name__ if last_error else "Unknown"
        logger.error(
            f"[RETRY_BUDGET_EXHAUSTED] Research agent retry budget exhausted:\n"
            f"  Function: {func_name}\n"
            f"  Total retries: {total_retries}/{self.max_retries}\n"
            f"  Last error: {error_type}: {last_error}\n"
            f"  Backoff ceiling: {self.max_backoff_seconds}s\n"
            f"  Action: Falling back to cache or re-raising error"
        )

    def set_cached_result(self, cache_key: str, result: Any) -> None:
        """Manually set a cached result for fallback.

        Args:
            cache_key: Key for the cached result
            result: Result to cache
        """
        self._cache[cache_key] = result
        logger.debug(f"Manually cached result for key: {cache_key}")

    def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Get a cached result if available.

        Args:
            cache_key: Key for the cached result

        Returns:
            Cached result if available, None otherwise
        """
        return self._cache.get(cache_key)

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()
        logger.debug("Error handler cache cleared")

    def get_retry_stats(self) -> dict[str, Any]:
        """Get retry budget statistics.

        Returns:
            Dictionary with retry configuration and cache stats
        """
        return {
            "max_retries": self.max_retries,
            "base_backoff_seconds": self.base_backoff_seconds,
            "max_backoff_seconds": self.max_backoff_seconds,
            "backoff_factor": self.backoff_factor,
            "cache_fallback_enabled": self.cache_fallback_enabled,
            "cached_items": len(self._cache),
        }


# Default error handler instance for backward compatibility
error_handler = ErrorHandler()
