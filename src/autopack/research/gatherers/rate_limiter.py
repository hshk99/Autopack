"""Rate limiter with retry budget enforcement for research phase error recovery.

This module provides:
- Token bucket rate limiting to prevent excessive API requests
- Retry budget tracking to prevent infinite loops on 429 errors
- Exponential backoff for rate limit errors
- Thread-safe operations
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class RetryBudgetExhausted(Exception):
    """Raised when retry budget is exhausted and no more retries are allowed."""

    def __init__(
        self,
        message: str = "Retry budget exhausted",
        total_retries: int = 0,
        budget_limit: int = 0,
    ):
        self.total_retries = total_retries
        self.budget_limit = budget_limit
        super().__init__(f"{message}: {total_retries}/{budget_limit} retries used")


@dataclass
class RetryBudget:
    """Tracks retry attempts with a configurable budget.

    Provides a mechanism to limit retry attempts across operations,
    preventing infinite loops when APIs return 429 errors.

    Default Configuration (IMP-RELIABILITY-003):
    - Max 3 retries per agent to prevent infinite loops
    - 60 second backoff ceiling with exponential backoff
    - Logging of exhausted retries for monitoring
    """

    max_retries: int = 3
    """Maximum number of retries allowed within the budget period (default: 3 per agent)."""

    budget_window_seconds: float = 3600.0
    """Time window for the retry budget (default: 1 hour)."""

    base_backoff_seconds: float = 1.0
    """Base backoff time for exponential backoff."""

    max_backoff_seconds: float = 60.0
    """Maximum backoff time."""

    backoff_multiplier: float = 2.0
    """Multiplier for exponential backoff."""

    retry_attempts: list[datetime] = field(default_factory=list)
    """Timestamps of retry attempts within the budget window."""

    _lock: Lock = field(default_factory=Lock)
    """Lock for thread-safe operations."""

    def _cleanup_expired_retries(self) -> None:
        """Remove retry attempts outside the budget window."""
        cutoff = datetime.now() - timedelta(seconds=self.budget_window_seconds)
        self.retry_attempts = [t for t in self.retry_attempts if t > cutoff]

    def get_remaining_retries(self) -> int:
        """Get number of retries remaining in the budget.

        Returns:
            Number of retries still available
        """
        with self._lock:
            self._cleanup_expired_retries()
            return max(0, self.max_retries - len(self.retry_attempts))

    def is_budget_exhausted(self) -> bool:
        """Check if retry budget is exhausted.

        Returns:
            True if no more retries are allowed
        """
        return self.get_remaining_retries() == 0

    def record_retry(self) -> None:
        """Record a retry attempt.

        Raises:
            RetryBudgetExhausted: If budget is exhausted
        """
        with self._lock:
            self._cleanup_expired_retries()
            if len(self.retry_attempts) >= self.max_retries:
                raise RetryBudgetExhausted(
                    total_retries=len(self.retry_attempts),
                    budget_limit=self.max_retries,
                )
            self.retry_attempts.append(datetime.now())
            logger.debug(f"Retry recorded: {len(self.retry_attempts)}/{self.max_retries}")

    def get_backoff_time(self, consecutive_failures: int = 1) -> float:
        """Calculate exponential backoff time.

        Args:
            consecutive_failures: Number of consecutive failures

        Returns:
            Backoff time in seconds
        """
        backoff = self.base_backoff_seconds * (
            self.backoff_multiplier ** (consecutive_failures - 1)
        )
        return min(backoff, self.max_backoff_seconds)

    def wait_with_backoff(self, consecutive_failures: int = 1) -> None:
        """Wait using exponential backoff.

        Args:
            consecutive_failures: Number of consecutive failures
        """
        backoff_time = self.get_backoff_time(consecutive_failures)
        logger.info(f"Backing off for {backoff_time:.2f}s after {consecutive_failures} failures")
        time.sleep(backoff_time)

    def reset(self) -> None:
        """Reset the retry budget."""
        with self._lock:
            self.retry_attempts.clear()
            logger.debug("Retry budget reset")

    def get_retry_stats(self) -> dict:
        """Get retry statistics.

        Returns:
            Dictionary with retry statistics
        """
        with self._lock:
            self._cleanup_expired_retries()
            return {
                "total_retries_used": len(self.retry_attempts),
                "max_retries": self.max_retries,
                "remaining_retries": self.max_retries - len(self.retry_attempts),
                "budget_window_seconds": self.budget_window_seconds,
                "is_exhausted": len(self.retry_attempts) >= self.max_retries,
            }


class RateLimiter:
    """Rate limiter with retry budget enforcement using sliding window algorithm.

    Combines token bucket rate limiting with retry budget tracking to:
    - Limit requests per time window
    - Track and limit retry attempts on 429 errors
    - Provide exponential backoff for rate limit errors
    - Prevent infinite retry loops
    """

    def __init__(
        self,
        max_requests_per_hour: int = 100,
        max_retries: int = 3,
        retry_budget_window_seconds: float = 3600.0,
    ):
        """Initialize rate limiter with retry budget.

        Args:
            max_requests_per_hour: Maximum requests allowed per hour
            max_retries: Maximum retry attempts in budget window (default: 3 per IMP-RELIABILITY-003)
            retry_budget_window_seconds: Time window for retry budget
        """
        self.max_requests_per_hour = max_requests_per_hour
        self.request_times: list[datetime] = []
        self._lock = Lock()
        self._consecutive_failures = 0

        # Retry budget for preventing infinite loops on 429 errors
        self.retry_budget = RetryBudget(
            max_retries=max_retries,
            budget_window_seconds=retry_budget_window_seconds,
        )

    def _cleanup_old_requests(self) -> None:
        """Remove requests outside the 1-hour window."""
        cutoff = datetime.now() - timedelta(hours=1)
        self.request_times = [t for t in self.request_times if t > cutoff]

    def get_remaining_requests(self) -> int:
        """Get number of requests remaining in the current hour.

        Returns:
            Number of requests remaining
        """
        with self._lock:
            self._cleanup_old_requests()
            return max(0, self.max_requests_per_hour - len(self.request_times))

    def acquire(self, block: bool = True) -> bool:
        """Acquire a request slot.

        Args:
            block: If True, blocks until a slot is available.
                   If False, returns immediately.

        Returns:
            True if slot acquired, False if no slots available and non-blocking

        Raises:
            RetryBudgetExhausted: If retry budget is exhausted during blocking
        """
        with self._lock:
            self._cleanup_old_requests()

            if len(self.request_times) >= self.max_requests_per_hour:
                if not block:
                    return False

                # Calculate wait time until oldest request expires
                oldest = self.request_times[0]
                wait_time = (oldest + timedelta(hours=1) - datetime.now()).total_seconds()

                if wait_time > 0:
                    # Release lock while waiting
                    self._lock.release()
                    try:
                        logger.info(f"Rate limit reached, waiting {wait_time:.2f}s")
                        time.sleep(wait_time)
                    finally:
                        self._lock.acquire()

                    self._cleanup_old_requests()

            self.request_times.append(datetime.now())
            return True

    def wait(self) -> None:
        """Wait until a request can be made (compatibility method).

        This method provides backwards compatibility with the original
        token bucket implementation.
        """
        self.acquire(block=True)

    def reset(self) -> None:
        """Reset the rate limiter state."""
        with self._lock:
            self.request_times.clear()
            self._consecutive_failures = 0
        self.retry_budget.reset()
        logger.debug("Rate limiter reset")

    def record_rate_limit_error(self) -> float:
        """Record a rate limit (429) error and get backoff time.

        Call this method when a 429 error is received from an API.

        Returns:
            Recommended backoff time in seconds

        Raises:
            RetryBudgetExhausted: If retry budget is exhausted
        """
        self._consecutive_failures += 1
        self.retry_budget.record_retry()
        return self.retry_budget.get_backoff_time(self._consecutive_failures)

    def record_success(self) -> None:
        """Record a successful request (resets consecutive failure count)."""
        self._consecutive_failures = 0

    def handle_rate_limit_error(self, wait: bool = True) -> None:
        """Handle a rate limit error with backoff.

        Args:
            wait: If True, waits the backoff time

        Raises:
            RetryBudgetExhausted: If retry budget is exhausted
        """
        backoff_time = self.record_rate_limit_error()
        if wait:
            logger.warning(
                f"Rate limit error (429), backing off for {backoff_time:.2f}s "
                f"(retries: {self.retry_budget.get_retry_stats()['total_retries_used']}/"
                f"{self.retry_budget.max_retries})"
            )
            time.sleep(backoff_time)

    def is_retry_budget_exhausted(self) -> bool:
        """Check if retry budget is exhausted.

        Returns:
            True if no more retries are allowed
        """
        return self.retry_budget.is_budget_exhausted()

    def get_stats(self) -> dict:
        """Get rate limiter statistics.

        Returns:
            Dictionary with rate limiter and retry budget statistics
        """
        with self._lock:
            self._cleanup_old_requests()
            return {
                "requests_made": len(self.request_times),
                "max_requests_per_hour": self.max_requests_per_hour,
                "remaining_requests": self.max_requests_per_hour - len(self.request_times),
                "consecutive_failures": self._consecutive_failures,
                "retry_budget": self.retry_budget.get_retry_stats(),
            }


# Default rate limiter instance for backward compatibility
rate_limiter = RateLimiter()


def limited_function():
    """Example rate-limited function."""
    rate_limiter.wait()
    print("Function executed")


# Only run example when executed directly
if __name__ == "__main__":
    limited_function()
