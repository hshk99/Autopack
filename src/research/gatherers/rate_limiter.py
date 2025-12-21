"""Rate Limiter Module

This module provides rate limiting functionality for API requests.
"""

import time
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Limits the rate of API requests."""

    def __init__(self, max_requests_per_hour=5000):
        self.max_requests_per_hour = max_requests_per_hour
        self.requests_made = 0
        self.start_time = time.time()

    def wait_for_rate_limit(self):
        """Waits if the rate limit is exceeded."""
        elapsed_time = time.time() - self.start_time
        if self.requests_made >= self.max_requests_per_hour:
            wait_time = 3600 - elapsed_time
            if wait_time > 0:
                logger.info(f"Rate limit exceeded. Waiting for {wait_time} seconds.")
                time.sleep(wait_time)
            self.reset_rate_limit()

    def reset_rate_limit(self):
        """Resets the rate limit counter."""
        self.requests_made = 0
        self.start_time = time.time()

    def increment_request_count(self):
        """Increments the request count."""
        self.requests_made += 1

    def log_rate_limit_status(self):
        """Logs the current rate limit status."""
        elapsed_time = time.time() - self.start_time
        logger.info(f"Requests made: {self.requests_made}/{self.max_requests_per_hour} in {elapsed_time} seconds.")

    def can_make_request(self):
        """Checks if a request can be made without exceeding the rate limit.

        Returns:
            bool: True if a request can be made, False otherwise.
        """
        return self.requests_made < self.max_requests_per_hour
