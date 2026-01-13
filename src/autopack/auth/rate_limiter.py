"""Rate limiting for authentication endpoints.

Prevents brute force attacks by limiting login attempts per IP address.
"""

from functools import wraps
from time import time
from typing import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    """In-memory rate limiter based on client IP and time windows."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        """Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            window_seconds: Time window in seconds for rate limiting
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}

    def check_rate_limit(self, client_ip: str) -> bool:
        """Check if the client IP is within rate limit.

        Args:
            client_ip: Client IP address

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        now = time()
        if client_ip not in self.requests:
            self.requests[client_ip] = []

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
