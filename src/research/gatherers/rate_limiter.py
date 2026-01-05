"""Rate Limiter Module

This module provides rate limiting functionality for API requests.
"""

import time
import logging
from threading import Lock
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimiter:
    """Limits the rate of API requests to prevent exceeding API quotas."""

    def __init__(self, max_requests_per_hour: int = 5000):
        """Initialize rate limiter.

        Args:
            max_requests_per_hour: Maximum number of requests allowed per hour
        """
        self.max_requests_per_hour = max_requests_per_hour
        self.request_times = deque()
        self.lock = Lock()
        logger.info(f"RateLimiter initialized with {max_requests_per_hour} requests/hour")

    def acquire(self) -> None:
        """Acquire permission to make a request, blocking if necessary.

        This method will block until a request slot is available within the rate limit.
        """
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(hours=1)

            # Remove requests older than 1 hour
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()

            # If at limit, wait until oldest request expires
            if len(self.request_times) >= self.max_requests_per_hour:
                oldest = self.request_times[0]
                sleep_time = (oldest + timedelta(hours=1) - now).total_seconds() + 0.1
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                    # Recursively try again after sleeping
                    return self.acquire()

            # Record this request
            self.request_times.append(now)
            logger.debug(
                f"Request acquired, {len(self.request_times)}/{self.max_requests_per_hour} used"
            )

    def get_remaining_requests(self) -> int:
        """Get the number of remaining requests in the current window.

        Returns:
            Number of requests remaining before hitting the rate limit
        """
        with self.lock:
            now = datetime.now()
            cutoff = now - timedelta(hours=1)

            # Remove requests older than 1 hour
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()

            return self.max_requests_per_hour - len(self.request_times)

    def reset(self) -> None:
        """Reset the rate limiter, clearing all recorded requests."""
        with self.lock:
            self.request_times.clear()
            logger.info("RateLimiter reset")
