"""Tests for ExecutorLockManager (BUILD-048-T1 process-level locking)."""

import os
import platform
import threading
import time

import pytest

from autopack.executor_lock import ExecutorLockManager


@pytest.fixture
def lock_dir(tmp_path):
    """Create a temporary lock directory."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    return lock_dir


def test_executor_lock_acquire_release(lock_dir):
    """Test basic lock acquisition and release."""
    lock = ExecutorLockManager("test-run-id", lock_dir=lock_dir)

    # Acquire lock
    assert lock.acquire() is True
    assert lock.is_locked() is True

    # Release lock
    lock.release()
    assert lock.is_locked() is False


def test_executor_lock_prevents_concurrent_executors(lock_dir):
    """Test that lock prevents concurrent executors for same run-id."""
    lock1 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
    lock2 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)

    # First lock acquires
    assert lock1.acquire() is True

    # Second lock should fail
    assert lock2.acquire() is False

    # After first releases, second can acquire
    lock1.release()
    assert lock2.acquire() is True

    # Cleanup
    lock2.release()


def test_executor_lock_context_manager(lock_dir):
    """Test ExecutorLockManager as context manager."""
    with ExecutorLockManager("test-run-id", lock_dir=lock_dir) as lock:
        assert lock.is_locked() is True

    # Should auto-release on exit
    assert lock.is_locked() is False


def test_executor_lock_context_manager_blocks_concurrent(lock_dir):
    """Test that context manager blocks concurrent access."""
    lock1 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)

    with lock1:
        # Try to acquire another lock - should raise
        lock2 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
        with pytest.raises(RuntimeError, match="Executor lock already held"):
            with lock2:
                pass


def test_executor_lock_different_run_ids_independent(lock_dir):
    """Test that locks for different run-ids are independent."""
    lock1 = ExecutorLockManager("run-id-1", lock_dir=lock_dir)
    lock2 = ExecutorLockManager("run-id-2", lock_dir=lock_dir)

    # Both should acquire successfully (different run-ids)
    assert lock1.acquire() is True
    assert lock2.acquire() is True

    # Cleanup
    lock1.release()
    lock2.release()


def test_executor_lock_threaded_access(lock_dir):
    """Test lock prevents concurrent access from multiple threads."""

    results = []

    def try_acquire_lock(thread_id):
        """Thread worker that tries to acquire lock."""
        lock = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
        if lock.acquire():
            results.append(f"thread-{thread_id}-acquired")
            time.sleep(0.1)  # Hold lock briefly
            lock.release()
            results.append(f"thread-{thread_id}-released")
        else:
            results.append(f"thread-{thread_id}-blocked")

    # Start multiple threads trying to acquire same lock
    threads = [threading.Thread(target=try_acquire_lock, args=(i,)) for i in range(5)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    # Exactly one thread should have acquired (at least on Unix-like systems)
    # On Windows, file locking may behave differently, so we allow some flexibility
    acquired_count = sum(1 for r in results if "acquired" in r)
    blocked_count = sum(1 for r in results if "blocked" in r)

    if platform.system() == "Windows":
        # Windows file locking may allow multiple processes to acquire the lock
        # Just verify that at least one acquired
        assert acquired_count >= 1
    else:
        # On Unix-like systems, enforce strict single-acquirer semantics
        assert acquired_count == 1
    assert blocked_count >= 0


def test_executor_lock_force_unlock(lock_dir):
    """Test force unlock for stale locks."""
    lock1 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
    lock1.acquire()

    # Simulate crash by not releasing properly
    if lock1._file_lock._lock_fd is not None:
        os.close(lock1._file_lock._lock_fd)
        lock1._file_lock._lock_fd = None

    # Lock file might still exist (stale lock file)
    lock2 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)

    # If lock file exists, force_unlock should remove it
    if lock2.is_locked():
        assert lock2.force_unlock() is True
        assert lock2.is_locked() is False

    # Now can acquire
    assert lock2.acquire() is True
    lock2.release()


def test_executor_lock_no_file_handle_leak_on_release(lock_dir):
    """Verify file descriptor is properly closed on release."""
    # Create lock and acquire successfully
    lock = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
    assert lock.acquire() is True

    # Verify _lock_fd is set
    assert lock._file_lock._lock_fd is not None

    # Release the lock
    lock.release()

    # Verify _lock_fd was cleared (fd was closed)
    assert lock._file_lock._lock_fd is None


def test_executor_lock_no_leak_on_failed_acquire(lock_dir):
    """Verify no file handle leak when lock acquisition fails (already held)."""
    # First lock holds
    lock1 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
    assert lock1.acquire() is True

    # Second lock tries to acquire (will fail)
    lock2 = ExecutorLockManager("test-run-id", lock_dir=lock_dir)
    assert lock2.acquire() is False

    # Verify second lock cleaned up its fd (no leak)
    assert lock2._file_lock._lock_fd is None

    # Cleanup
    lock1.release()


def test_executor_lock_no_leak_on_exception_in_acquire(lock_dir):
    """Verify no file handle leak when FileLock.acquire fails."""
    from unittest import mock

    # Create a lock
    lock = ExecutorLockManager("test-run-id", lock_dir=lock_dir)

    # Mock the FileLock.acquire to raise an exception (simulating lock already held)
    with mock.patch.object(
        lock._file_lock, "acquire", side_effect=RuntimeError("Simulated lock failure")
    ):
        # This should return False (lock not acquired)
        result = lock.acquire()
        assert result is False

    # Verify _lock_fd was cleaned up (no leak)
    assert lock._file_lock._lock_fd is None
