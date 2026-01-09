"""Retry utility functions for handling retries with exponential backoff.

This module provides retry logic utilities including:
- retry_on_exception: Decorator to retry a function on exception
- exponential_backoff: Calculate exponential backoff delay
- RetryConfig: Configuration class for retry behavior
"""

import time
import functools
from typing import Callable, Type, Tuple, Optional, Any
import random


class RetryConfig:
    """Configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        max_delay: Maximum delay in seconds between retries (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2)
        jitter: Whether to add random jitter to delays (default: True)
        exceptions: Tuple of exception types to catch (default: (Exception,))
    """
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """Initialize retry configuration.
        
        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds between retries
            exponential_base: Base for exponential calculation
            jitter: Whether to add random jitter to delays
            exceptions: Tuple of exception types to catch
            
        Raises:
            ValueError: If max_attempts < 1, base_delay < 0, max_delay < 0,
                       exponential_base <= 1, or exceptions is empty
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if base_delay < 0:
            raise ValueError("base_delay must be non-negative")
        if max_delay < 0:
            raise ValueError("max_delay must be non-negative")
        if exponential_base <= 1:
            raise ValueError("exponential_base must be greater than 1")
        if not exceptions:
            raise ValueError("exceptions tuple cannot be empty")
        
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.exceptions = exceptions


def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff delay.
    
    Calculates the delay for a retry attempt using exponential backoff.
    The delay is calculated as: base_delay * (exponential_base ** attempt)
    and capped at max_delay. Optional jitter adds randomness to prevent
    thundering herd problems.
    
    Args:
        attempt: The attempt number (0-indexed)
        base_delay: Base delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        jitter: Whether to add random jitter (default: True)
        
    Returns:
        The calculated delay in seconds
        
    Raises:
        ValueError: If attempt < 0, base_delay < 0, max_delay < 0,
                   or exponential_base <= 1
        
    Examples:
        >>> delay = exponential_backoff(0, base_delay=1.0)
        >>> 0.5 <= delay <= 1.5  # With jitter
        True
        >>> delay = exponential_backoff(1, base_delay=1.0, exponential_base=2.0, jitter=False)
        >>> delay
        2.0
        >>> delay = exponential_backoff(5, base_delay=1.0, max_delay=10.0, jitter=False)
        >>> delay
        10.0
        >>> delay = exponential_backoff(2, base_delay=0.5, exponential_base=3.0, jitter=False)
        >>> delay
        4.5
    """
    if attempt < 0:
        raise ValueError("attempt must be non-negative")
    if base_delay < 0:
        raise ValueError("base_delay must be non-negative")
    if max_delay < 0:
        raise ValueError("max_delay must be non-negative")
    if exponential_base <= 1:
        raise ValueError("exponential_base must be greater than 1")
    
    # Calculate exponential delay
    delay = base_delay * (exponential_base ** attempt)
    
    # Cap at max_delay
    delay = min(delay, max_delay)
    
    # Add jitter if requested (±50% randomness)
    if jitter:
        jitter_range = delay * 0.5
        delay = delay + random.uniform(-jitter_range, jitter_range)
        # Ensure delay is non-negative after jitter
        delay = max(0, delay)
    
    return delay


def retry_on_exception(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None,
) -> Callable:
    """Decorator to retry a function on exception with exponential backoff.
    
    Retries the decorated function if it raises one of the specified exceptions.
    Uses exponential backoff to calculate delays between retries.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        max_delay: Maximum delay in seconds between retries (default: 60.0)
        exponential_base: Base for exponential calculation (default: 2.0)
        jitter: Whether to add random jitter to delays (default: True)
        exceptions: Tuple of exception types to catch (default: (Exception,))
        on_retry: Optional callback function called before each retry.
                 Receives (exception, attempt_number, delay) as arguments.
        
    Returns:
        A decorator function
        
    Raises:
        ValueError: If max_attempts < 1 or other invalid parameters
        
    Examples:
        >>> @retry_on_exception(max_attempts=3, base_delay=0.1)
        ... def flaky_function():
        ...     import random
        ...     if random.random() < 0.5:
        ...         raise ValueError("Random failure")
        ...     return "success"
        
        >>> @retry_on_exception(max_attempts=2, exceptions=(IOError,))
        ... def read_file(path):
        ...     with open(path, 'r') as f:
        ...         return f.read()
        
        >>> def log_retry(exc, attempt, delay):
        ...     print(f"Retry {attempt} after {delay}s due to {exc}")
        >>> @retry_on_exception(max_attempts=3, on_retry=log_retry)
        ... def api_call():
        ...     pass
    """
    # Validate parameters
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if base_delay < 0:
        raise ValueError("base_delay must be non-negative")
    if max_delay < 0:
        raise ValueError("max_delay must be non-negative")
    if exponential_base <= 1:
        raise ValueError("exponential_base must be greater than 1")
    if not exceptions:
        raise ValueError("exceptions tuple cannot be empty")
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # If this was the last attempt, re-raise
                    if attempt == max_attempts - 1:
                        raise
                    
                    # Calculate delay for next retry
                    delay = exponential_backoff(
                        attempt=attempt,
                        base_delay=base_delay,
                        max_delay=max_delay,
                        exponential_base=exponential_base,
                        jitter=jitter,
                    )
                    
                    # Call retry callback if provided
                    if on_retry is not None:
                        try:
                            on_retry(e, attempt + 1, delay)
                        except Exception:
                            # Ignore exceptions in callback
                            pass
                    
                    # Wait before retrying
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception is not None:
                raise last_exception
        
        return wrapper
    
    return decorator


def retry_with_config(config: RetryConfig, on_retry: Optional[Callable[[Exception, int, float], None]] = None) -> Callable:
    """Decorator to retry a function using a RetryConfig object.
    
    Convenience wrapper around retry_on_exception that accepts a RetryConfig object.
    
    Args:
        config: RetryConfig object with retry settings
        on_retry: Optional callback function called before each retry
        
    Returns:
        A decorator function
        
    Examples:
        >>> config = RetryConfig(max_attempts=5, base_delay=0.5)
        >>> @retry_with_config(config)
        ... def my_function():
        ...     pass
    """
    return retry_on_exception(
        max_attempts=config.max_attempts,
        base_delay=config.base_delay,
        max_delay=config.max_delay,
        exponential_base=config.exponential_base,
        jitter=config.jitter,
        exceptions=config.exceptions,
        on_retry=on_retry,
    )
