"""Tests for executor instance locking (BUILD-048-T1)."""

import os
import pytest
import tempfile
from pathlib import Path
import time
import subprocess
import sys

from autopack.executor_lock import ExecutorLockManager


class TestExecutorLockManager:
    """Tests for ExecutorLockManager file-based locking."""

    @pytest.fixture
    def temp_lock_dir(self):
        """Create temporary directory for lock files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_acquire_lock_success(self, temp_lock_dir):
        """Test successfully acquiring a lock."""
        lock = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock.acquire() is True
        assert lock.is_locked() is True
        lock.release()

    def test_acquire_lock_twice_fails(self, temp_lock_dir):
        """Test that acquiring same lock twice fails."""
        lock1 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        lock2 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)

        assert lock1.acquire() is True

        # Second lock should fail
        assert lock2.acquire() is False

        lock1.release()

    def test_release_allows_reacquire(self, temp_lock_dir):
        """Test that releasing a lock allows it to be acquired again."""
        lock1 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        lock2 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)

        # First lock acquires
        assert lock1.acquire() is True

        # Second lock fails
        assert lock2.acquire() is False

        # First lock releases
        lock1.release()

        # Second lock can now acquire
        assert lock2.acquire() is True

        lock2.release()

    def test_context_manager_success(self, temp_lock_dir):
        """Test using lock as context manager."""
        with ExecutorLockManager("test-run", lock_dir=temp_lock_dir) as lock:
            assert lock.is_locked() is True

        # Lock should be released after context
        lock2 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock2.acquire() is True
        lock2.release()

    def test_context_manager_fails_on_duplicate(self, temp_lock_dir):
        """Test context manager raises on duplicate lock."""
        lock1 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock1.acquire() is True

        # Second context manager should raise
        with pytest.raises(RuntimeError, match="Executor lock already held"):
            with ExecutorLockManager("test-run", lock_dir=temp_lock_dir):
                pass

        lock1.release()

    def test_different_run_ids_independent(self, temp_lock_dir):
        """Test that different run-ids have independent locks."""
        lock1 = ExecutorLockManager("run-1", lock_dir=temp_lock_dir)
        lock2 = ExecutorLockManager("run-2", lock_dir=temp_lock_dir)

        assert lock1.acquire() is True
        assert lock2.acquire() is True

        lock1.release()
        lock2.release()

    @pytest.mark.skipif(os.name == 'nt', reason="Windows file locking prevents reading locked files")
    def test_force_unlock(self, temp_lock_dir):
        """Test force unlocking a stale lock."""
        lock1 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock1.acquire() is True

        # Simulate crash - don't release, just create new lock
        lock2 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)

        # Lock2 can't acquire
        assert lock2.acquire() is False

        # Force unlock
        assert lock2.force_unlock() is True

        # Now lock2 can acquire
        assert lock2.acquire() is True

        lock2.release()

    @pytest.mark.skipif(os.name == 'nt', reason="Windows file locking prevents reading locked files")
    def test_lock_file_contains_executor_info(self, temp_lock_dir):
        """Test that lock file contains executor information."""
        lock = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock.acquire() is True

        # Read lock file
        lock_file = temp_lock_dir / "test-run.lock"
        content = lock_file.read_text()

        # Should contain executor info
        assert str(lock.pid) in content
        assert lock.hostname in content

        lock.release()

    def test_lock_file_cleaned_up_on_release(self, temp_lock_dir):
        """Test that lock file is removed on release."""
        lock = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        lock_file = temp_lock_dir / "test-run.lock"

        assert lock.acquire() is True
        assert lock_file.exists()

        lock.release()
        assert not lock_file.exists()

    def test_is_locked_before_acquire(self, temp_lock_dir):
        """Test is_locked returns False before acquisition."""
        lock = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock.is_locked() is False

    @pytest.mark.skipif(os.name == 'nt', reason="Unix-specific test")
    def test_lock_survives_process_fork(self, temp_lock_dir):
        """Test that lock is held across process fork (Unix only)."""
        lock = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
        assert lock.acquire() is True

        # Fork a child process
        pid = os.fork()
        if pid == 0:  # Child process
            # Child should not be able to acquire same lock
            lock2 = ExecutorLockManager("test-run", lock_dir=temp_lock_dir)
            can_acquire = lock2.acquire()
            sys.exit(0 if not can_acquire else 1)
        else:  # Parent process
            _, status = os.waitpid(pid, 0)
            exit_code = os.WEXITSTATUS(status)
            assert exit_code == 0  # Child correctly failed to acquire

        lock.release()


class TestExecutorLockIntegration:
    """Integration tests for executor lock with real executor process."""

    @pytest.fixture
    def temp_lock_dir(self):
        """Create temporary directory for lock files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_duplicate_executor_prevented(self, temp_lock_dir):
        """Test that duplicate executor process is prevented."""
        # This test would launch actual executor processes
        # Skipped in unit tests, should be run in integration tests
        pytest.skip("Integration test - run manually")

        # Example implementation:
        # proc1 = subprocess.Popen([
        #     sys.executable, "-m", "autopack.autonomous_executor",
        #     "--run-id", "test-run"
        # ])
        # time.sleep(2)  # Let first executor start
        #
        # proc2 = subprocess.Popen([
        #     sys.executable, "-m", "autopack.autonomous_executor",
        #     "--run-id", "test-run"
        # ])
        # proc2.wait()
        #
        # # Second executor should exit with code 1
        # assert proc2.returncode == 1
        #
        # proc1.terminate()
        # proc1.wait()
