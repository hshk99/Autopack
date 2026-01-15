"""Rate limiting for authentication endpoints.

Prevents brute force attacks by limiting login attempts per IP address.

IMP-SEC-002: Added memory bounds with LRU cleanup to prevent DoS via memory exhaustion.
"""

import logging
from functools import wraps
from time import time
from typing import Callable

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


class RateLimiter:
    """In-memory rate limiter based on client IP and time windows.

    IMP-SEC-002: Includes memory bounds with LRU cleanup to prevent DoS.
    """

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: int = 60,
        max_tracked_ips: int = 10_000,
    ):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            window_seconds: Time window in seconds for rate limiting
            max_tracked_ips: Maximum number of IPs to track (IMP-SEC-002 memory cap)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_ips = max_tracked_ips
        self.requests: dict[str, list[float]] = {}
        self.last_access: dict[str, float] = {}  # Track last access for LRU cleanup

    def check_rate_limit(self, client_ip: str) -> bool:
        """Check if the client IP is within rate limit (with memory cap).

        Args:
            client_ip: Client IP address

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time()

        # IMP-SEC-002: Enforce memory cap before adding new IP
        if client_ip not in self.requests and len(self.requests) >= self.max_tracked_ips:
            self._cleanup_lru_entries()

        if client_ip not in self.requests:
            self.requests[client_ip] = []

        # Update last access time (for LRU tracking)
        self.last_access[client_ip] = now

        # Remove old requests outside window
        self.requests[client_ip] = [
            req_time
            for req_time in self.requests[client_ip]
            if now - req_time < self.window_seconds
        ]

        if len(self.requests[client_ip]) >= self.max_requests:
            return False

        self.requests[client_ip].append(now)
        return True

    def _cleanup_lru_entries(self, cleanup_percent: float = 0.20):
        """Remove least recently used entries when memory cap reached.

        IMP-SEC-002: Prevents unbounded memory growth from many unique IPs.

        Args:
            cleanup_percent: Percentage of entries to remove (default: 20%)
        """
        if not self.requests:
            return

        # Sort IPs by last access time (oldest first)
        sorted_ips = sorted(self.last_access.items(), key=lambda x: x[1])

        # Calculate how many entries to remove (20% of cap)
        entries_to_remove = max(1, int(self.max_tracked_ips * cleanup_percent))

        # Remove oldest entries
        removed_count = 0
        for ip, _ in sorted_ips[:entries_to_remove]:
            self.requests.pop(ip, None)
            self.last_access.pop(ip, None)
            removed_count += 1

        logger.info(
            f"Rate limiter LRU cleanup: removed {removed_count} oldest IPs "
            f"(cap: {self.max_tracked_ips}, remaining: {len(self.requests)})"
        )

    def get_tracked_ip_count(self) -> int:
        """Return the number of currently tracked IPs.

        Returns:
            Number of IPs in the rate limiter cache
        """
        return len(self.requests)


# Global rate limiter instance for login endpoints
# 5 requests per 60 seconds (1 minute)
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


def rate_limit(limiter: RateLimiter) -> Callable:
    """Decorator to apply rate limiting to FastAPI endpoints.

    Args:
        limiter: RateLimiter instance to use

    Returns:
        Decorator function that enforces rate limiting
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from kwargs (FastAPI dependency injection)
            request: Request | None = kwargs.get("request")
            if not request:
                # If no request object, allow the request (for testing)
                return await func(*args, **kwargs)

            client_ip = request.client.host if request.client else "unknown"

            if not limiter.check_rate_limit(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Please try again later.",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
