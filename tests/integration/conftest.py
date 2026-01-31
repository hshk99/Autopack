"""Integration test fixtures and configuration.

This module provides synchronization utilities to prevent flaky tests:
- Async: asyncio.wait_for, asyncio.Event for proper async coordination
- Threading: threading.Barrier, threading.Event for thread synchronization
- Timeouts: All integration tests have configurable timeouts

Replaces arbitrary sleep() calls with proper synchronization primitives.
"""

import asyncio
import threading
import time
from contextlib import contextmanager
from typing import Callable, Optional, TypeVar
from unittest.mock import patch

import pytest

T = TypeVar("T")

# =============================================================================
# Default timeout configuration for integration tests
# =============================================================================
DEFAULT_ASYNC_TIMEOUT = 10.0  # seconds
DEFAULT_THREAD_TIMEOUT = 10.0  # seconds


# =============================================================================
# Async synchronization utilities
# =============================================================================


class AsyncSyncPoint:
    """Synchronization point for coordinating async operations.

    Use instead of asyncio.sleep() for waiting on conditions.
    Provides proper timeout handling and clear error messages.

    Example:
        sync = AsyncSyncPoint()

        async def task1():
            # Do work...
            await sync.signal("task1_done")

        async def task2():
            await sync.wait_for("task1_done")
            # Continue after task1 is done
    """

    def __init__(self):
        self._events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def signal(self, name: str) -> None:
        """Signal that a named checkpoint has been reached."""
        async with self._lock:
            if name not in self._events:
                self._events[name] = asyncio.Event()
            self._events[name].set()

    async def wait_for(self, name: str, timeout: float = DEFAULT_ASYNC_TIMEOUT) -> None:
        """Wait for a named checkpoint to be signaled.

        Args:
            name: The checkpoint name to wait for
            timeout: Maximum time to wait in seconds

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        async with self._lock:
            if name not in self._events:
                self._events[name] = asyncio.Event()
            event = self._events[name]

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(
                f"Timed out waiting for sync point '{name}' after {timeout}s"
            )

    def reset(self, name: Optional[str] = None) -> None:
        """Reset sync points. If name is None, reset all."""
        if name:
            if name in self._events:
                self._events[name].clear()
        else:
            for event in self._events.values():
                event.clear()


async def async_wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = DEFAULT_ASYNC_TIMEOUT,
    poll_interval: float = 0.01,
    description: str = "condition",
) -> None:
    """Wait for a condition to become true with proper timeout.

    Use instead of polling with asyncio.sleep() loops.

    Args:
        condition: Callable that returns True when ready
        timeout: Maximum time to wait
        poll_interval: How often to check the condition
        description: Description for timeout error message

    Raises:
        asyncio.TimeoutError: If condition not met within timeout
    """
    deadline = time.perf_counter() + timeout
    while not condition():
        if time.perf_counter() >= deadline:
            raise asyncio.TimeoutError(f"Timed out waiting for {description} after {timeout}s")
        await asyncio.sleep(poll_interval)


# =============================================================================
# Threading synchronization utilities
# =============================================================================


class ThreadSyncPoint:
    """Synchronization point for coordinating threaded operations.

    Use instead of time.sleep() for waiting on conditions in threads.

    Example:
        sync = ThreadSyncPoint()

        def thread1():
            # Do work...
            sync.signal("thread1_done")

        def thread2():
            sync.wait_for("thread1_done")
            # Continue after thread1 is done
    """

    def __init__(self):
        self._events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def signal(self, name: str) -> None:
        """Signal that a named checkpoint has been reached."""
        with self._lock:
            if name not in self._events:
                self._events[name] = threading.Event()
            self._events[name].set()

    def wait_for(self, name: str, timeout: float = DEFAULT_THREAD_TIMEOUT) -> bool:
        """Wait for a named checkpoint to be signaled.

        Args:
            name: The checkpoint name to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            True if checkpoint was signaled, False if timeout occurred

        Raises:
            TimeoutError: If timeout is exceeded
        """
        with self._lock:
            if name not in self._events:
                self._events[name] = threading.Event()
            event = self._events[name]

        if not event.wait(timeout=timeout):
            raise TimeoutError(f"Timed out waiting for sync point '{name}' after {timeout}s")
        return True

    def reset(self, name: Optional[str] = None) -> None:
        """Reset sync points. If name is None, reset all."""
        with self._lock:
            if name:
                if name in self._events:
                    self._events[name].clear()
            else:
                for event in self._events.values():
                    event.clear()


def thread_wait_for_condition(
    condition: Callable[[], bool],
    timeout: float = DEFAULT_THREAD_TIMEOUT,
    poll_interval: float = 0.01,
    description: str = "condition",
) -> None:
    """Wait for a condition to become true with proper timeout.

    Use instead of polling with time.sleep() loops.

    Args:
        condition: Callable that returns True when ready
        timeout: Maximum time to wait
        poll_interval: How often to check the condition
        description: Description for timeout error message

    Raises:
        TimeoutError: If condition not met within timeout
    """
    import time

    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description} after {timeout}s")
        time.sleep(poll_interval)


@contextmanager
def thread_barrier(num_threads: int, timeout: float = DEFAULT_THREAD_TIMEOUT):
    """Context manager for thread synchronization barriers.

    Use to ensure all threads reach a certain point before proceeding.

    Example:
        with thread_barrier(3) as barrier:
            def worker():
                # Do setup...
                barrier.wait()  # All threads sync here
                # Continue together...

            threads = [Thread(target=worker) for _ in range(3)]
    """
    barrier = threading.Barrier(num_threads, timeout=timeout)
    try:
        yield barrier
    finally:
        barrier.abort()  # Clean up if test fails


# =============================================================================
# Pytest fixtures for synchronization
# =============================================================================


@pytest.fixture
def async_sync_point():
    """Fixture providing an async synchronization point.

    Example:
        async def test_async_coordination(async_sync_point):
            async def producer():
                # produce data...
                await async_sync_point.signal("data_ready")

            async def consumer():
                await async_sync_point.wait_for("data_ready")
                # consume data...
    """
    return AsyncSyncPoint()


@pytest.fixture
def thread_sync_point():
    """Fixture providing a thread synchronization point.

    Example:
        def test_thread_coordination(thread_sync_point):
            def producer():
                # produce data...
                thread_sync_point.signal("data_ready")

            def consumer():
                thread_sync_point.wait_for("data_ready")
                # consume data...
    """
    return ThreadSyncPoint()


@pytest.fixture
def async_timeout():
    """Fixture providing a configured timeout for async operations.

    Example:
        async def test_with_timeout(async_timeout):
            await asyncio.wait_for(some_operation(), timeout=async_timeout)
    """
    return DEFAULT_ASYNC_TIMEOUT


@pytest.fixture
def thread_timeout():
    """Fixture providing a configured timeout for thread operations.

    Example:
        def test_with_timeout(thread_timeout):
            event.wait(timeout=thread_timeout)
    """
    return DEFAULT_THREAD_TIMEOUT


# =============================================================================
# Database session fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def mock_session_local(db_engine):
    """Mock SessionLocal to use the test database engine.

    This ensures PhaseStateManager and other components use the test database
    instead of creating their own connection to the global database.
    """
    from sqlalchemy.orm import sessionmaker

    from autopack import database

    # Create a sessionmaker bound to the test engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    # Patch the SessionLocal in the database module
    with patch.object(database, "SessionLocal", TestingSessionLocal):
        yield
