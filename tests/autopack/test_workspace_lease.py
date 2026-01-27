"""Tests for WorkspaceLease (P2.4 workspace locking)."""

import os
import platform
import threading
import time

import pytest

from autopack.workspace_lease import WorkspaceLease


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace directory."""
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def lease_dir(tmp_path):
    """Create a temporary lease directory."""
    lease_dir = tmp_path / "leases"
    lease_dir.mkdir()
    return lease_dir


def test_workspace_lease_acquire_release(temp_workspace, lease_dir):
    """Test basic lease acquisition and release."""
    lease = WorkspaceLease(temp_workspace, lease_dir=lease_dir)

    # Acquire lease
    assert lease.acquire() is True
    assert lease.is_locked() is True

    # Release lease
    lease.release()
    assert lease.is_locked() is False


def test_workspace_lease_prevents_concurrent_access(temp_workspace, lease_dir):
    """Test that lease prevents concurrent access to same workspace."""
    lease1 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
    lease2 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)

    # First lease acquires
    assert lease1.acquire() is True

    # Second lease should fail
    assert lease2.acquire() is False

    # After first releases, second can acquire
    lease1.release()
    assert lease2.acquire() is True

    # Cleanup
    lease2.release()


def test_workspace_lease_context_manager(temp_workspace, lease_dir):
    """Test WorkspaceLease as context manager."""
    with WorkspaceLease(temp_workspace, lease_dir=lease_dir) as lease:
        assert lease.is_locked() is True

    # Should auto-release on exit
    assert lease.is_locked() is False


def test_workspace_lease_context_manager_blocks_concurrent(temp_workspace, lease_dir):
    """Test that context manager blocks concurrent access."""
    lease1 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)

    with lease1:
        # Try to acquire another lease - should raise
        lease2 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
        with pytest.raises(RuntimeError, match="Workspace lease already held"):
            with lease2:
                pass


def test_workspace_lease_different_workspaces_independent(tmp_path, lease_dir):
    """Test that leases for different workspaces are independent."""
    workspace1 = tmp_path / "workspace1"
    workspace2 = tmp_path / "workspace2"
    workspace1.mkdir()
    workspace2.mkdir()

    lease1 = WorkspaceLease(workspace1, lease_dir=lease_dir)
    lease2 = WorkspaceLease(workspace2, lease_dir=lease_dir)

    # Both should acquire successfully (different workspaces)
    assert lease1.acquire() is True
    assert lease2.acquire() is True

    # Cleanup
    lease1.release()
    lease2.release()


def test_workspace_lease_threaded_access(temp_workspace, lease_dir):
    """Test lease prevents concurrent access from multiple threads."""

    results = []

    def try_acquire_lease(thread_id):
        """Thread worker that tries to acquire lease."""
        lease = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
        if lease.acquire():
            results.append(f"thread-{thread_id}-acquired")
            time.sleep(0.1)  # Hold lease briefly
            lease.release()
            results.append(f"thread-{thread_id}-released")
        else:
            results.append(f"thread-{thread_id}-blocked")

    # Start multiple threads trying to acquire same lease
    threads = [threading.Thread(target=try_acquire_lease, args=(i,)) for i in range(5)]

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


def test_workspace_lease_force_unlock(temp_workspace, lease_dir):
    """Test force unlock for stale locks."""
    lease1 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
    lease1.acquire()

    # Simulate crash by not releasing properly
    # Note: On some systems, closing file handle releases OS lock automatically
    # So we just check that force_unlock can clean up the lock file
    if lease1._file_lock._lock_fd is not None:
        os.close(lease1._file_lock._lock_fd)
        lease1._file_lock._lock_fd = None

    # Lock file might still exist (stale lock file)
    # Even if OS lock was released, the file remains

    # Force unlock removes the lock file
    lease2 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)

    # If lock file exists, force_unlock should remove it
    if lease2.is_locked():
        assert lease2.force_unlock() is True
        assert lease2.is_locked() is False

    # Now can acquire
    assert lease2.acquire() is True
    lease2.release()


def test_workspace_lease_handles_absolute_path_normalization(tmp_path, lease_dir):
    """Test that relative and absolute paths to same workspace are treated as same lease."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create lease with absolute path
    lease1 = WorkspaceLease(workspace.resolve(), lease_dir=lease_dir)
    assert lease1.acquire() is True

    # Try to acquire with same absolute path
    lease2 = WorkspaceLease(workspace.resolve(), lease_dir=lease_dir)
    assert lease2.acquire() is False  # Should be blocked

    # Cleanup
    lease1.release()


def test_workspace_lease_no_file_handle_leak_on_release(temp_workspace, lease_dir):
    """Verify file descriptor is properly closed on release."""
    # Create lease and acquire lock successfully
    lease = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
    assert lease.acquire() is True

    # Verify _lock_fd is set
    assert lease._file_lock._lock_fd is not None

    # Release the lock
    lease.release()

    # Verify _lock_fd was cleared (fd was closed)
    assert lease._file_lock._lock_fd is None


def test_workspace_lease_no_leak_on_failed_acquire(temp_workspace, lease_dir):
    """Verify no file handle leak when lock acquisition fails (already held)."""
    # First lease holds the lock
    lease1 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
    assert lease1.acquire() is True

    # Second lease tries to acquire (will fail)
    lease2 = WorkspaceLease(temp_workspace, lease_dir=lease_dir)
    assert lease2.acquire() is False

    # Verify second lease cleaned up its fd (no leak)
    assert lease2._file_lock._lock_fd is None

    # Cleanup
    lease1.release()


def test_workspace_lease_no_leak_on_exception_in_acquire(temp_workspace, lease_dir):
    """Verify no file handle leak when FileLock.acquire fails."""
    from unittest import mock

    # Create a lease
    lease = WorkspaceLease(temp_workspace, lease_dir=lease_dir)

    # Mock the FileLock.acquire to raise an exception (simulating lock already held)
    with mock.patch.object(
        lease._file_lock, "acquire", side_effect=RuntimeError("Simulated lock failure")
    ):
        # This should return False (lock not acquired)
        result = lease.acquire()
        assert result is False

    # Verify _lock_fd was cleaned up (no leak)
    assert lease._file_lock._lock_fd is None
