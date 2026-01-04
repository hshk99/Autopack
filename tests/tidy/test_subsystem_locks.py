"""
Tests for BUILD-165: Per-subsystem locks with canonical ordering.

Tests verify:
- Canonical acquisition order is enforced
- Release order is reverse (LIFO)
- Lock contention handling
- Umbrella lock compatibility
- Disabled mode works correctly
"""

from __future__ import annotations

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add scripts/tidy to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tidy"))

from locks import MultiLock, LOCK_ORDER, lock_path
from lease import Lease


@pytest.fixture
def temp_repo():
    """Create a temporary repository structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        locks_dir = repo_root / ".autonomous_runs" / ".locks"
        locks_dir.mkdir(parents=True, exist_ok=True)
        yield repo_root


def test_lock_path_generation(temp_repo):
    """Test that lock paths are generated correctly."""
    expected = temp_repo / ".autonomous_runs" / ".locks" / "queue.lock"
    actual = lock_path(temp_repo, "queue")
    assert actual == expected


def test_canonical_order_enforcement(temp_repo):
    """Test that locks are acquired in canonical order regardless of request order."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    # Request locks out of order
    requested = ["docs", "queue", "archive"]
    multi_lock.acquire(requested)

    try:
        # Verify locks were acquired in canonical order: queue, archive, docs
        assert len(multi_lock.leases) == 3
        acquired_names = [
            lease.lock_path.stem.replace('.lock', '')
            for lease in multi_lock.leases
        ]

        # Should match canonical order from LOCK_ORDER
        expected_order = ["queue", "archive", "docs"]
        assert acquired_names == expected_order

    finally:
        multi_lock.release()


def test_reverse_release_order(temp_repo):
    """Test that locks are released in reverse order (LIFO)."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    multi_lock.acquire(["queue", "archive", "docs"])

    # Patch release method to track order
    release_order = []

    original_release = Lease.release

    def tracked_release(self):
        release_order.append(self.lock_path.stem.replace('.lock', ''))
        original_release(self)

    with patch.object(Lease, 'release', tracked_release):
        multi_lock.release()

    # Should release in reverse: docs, archive, queue
    expected_reverse = ["docs", "archive", "queue"]
    assert release_order == expected_reverse


def test_lock_contention_timeout(temp_repo):
    """Test that MultiLock times out correctly when locks are held."""
    # Acquire a lock manually to block MultiLock
    queue_lock_path = lock_path(temp_repo, "queue")
    blocking_lease = Lease(
        lock_path=queue_lock_path,
        owner="blocker",
        ttl_seconds=60
    )
    blocking_lease.acquire(timeout_seconds=5)

    try:
        multi_lock = MultiLock(
            repo_root=temp_repo,
            owner="test",
            ttl_seconds=60,
            timeout_seconds=1  # Short timeout
        )

        # Should timeout when trying to acquire queue lock
        with pytest.raises(TimeoutError) as exc_info:
            multi_lock.acquire(["queue", "archive"])

        assert "queue" in str(exc_info.value)

    finally:
        blocking_lease.release()


def test_disabled_mode(temp_repo):
    """Test that MultiLock is a no-op when disabled."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5,
        enabled=False
    )

    # All operations should be no-ops
    multi_lock.acquire(["queue", "archive", "docs"])
    assert len(multi_lock.leases) == 0
    assert not multi_lock.is_acquired()

    multi_lock.renew()  # Should not raise
    multi_lock.release()  # Should not raise


def test_renew_all_locks(temp_repo):
    """Test that renew extends TTL for all held locks."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    multi_lock.acquire(["queue", "archive"])

    try:
        # Renew should succeed for all locks
        multi_lock.renew()

        # Verify all locks are still held
        assert len(multi_lock.leases) == 2
        for lease in multi_lock.leases:
            assert lease.is_acquired()

    finally:
        multi_lock.release()


def test_partial_acquisition_cleanup(temp_repo):
    """Test that partially acquired locks are cleaned up on failure."""
    # Manually create a blocking lock for "archive"
    archive_lock_path = lock_path(temp_repo, "archive")
    blocking_lease = Lease(
        lock_path=archive_lock_path,
        owner="blocker",
        ttl_seconds=60
    )
    blocking_lease.acquire(timeout_seconds=5)

    try:
        multi_lock = MultiLock(
            repo_root=temp_repo,
            owner="test",
            ttl_seconds=60,
            timeout_seconds=1
        )

        # Try to acquire queue and archive (queue should succeed, archive should fail)
        with pytest.raises(TimeoutError):
            multi_lock.acquire(["queue", "archive"])

        # Verify that queue lock was released during cleanup
        assert len(multi_lock.leases) == 0
        assert not multi_lock.is_acquired()

        # Verify queue lock is actually free (can be acquired)
        queue_lease = Lease(
            lock_path=lock_path(temp_repo, "queue"),
            owner="test_after_cleanup",
            ttl_seconds=60
        )
        queue_lease.acquire(timeout_seconds=2)  # Should succeed
        queue_lease.release()

    finally:
        blocking_lease.release()


def test_held_locks_reporting(temp_repo):
    """Test that held_locks() returns correct lock names."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    # Initially no locks
    assert multi_lock.held_locks() == []

    multi_lock.acquire(["queue", "docs"])

    try:
        # Should report held locks in acquisition order
        held = multi_lock.held_locks()
        assert set(held) == {"queue", "docs"}

    finally:
        multi_lock.release()

    # After release, no locks
    assert multi_lock.held_locks() == []


def test_double_acquire_raises(temp_repo):
    """Test that acquiring locks twice raises an error."""
    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    multi_lock.acquire(["queue"])

    try:
        with pytest.raises(RuntimeError) as exc_info:
            multi_lock.acquire(["archive"])

        assert "already holds" in str(exc_info.value).lower()

    finally:
        multi_lock.release()


def test_unknown_lock_names_warning(temp_repo, caplog):
    """Test that unknown lock names generate a warning."""
    import logging
    caplog.set_level(logging.WARNING)

    multi_lock = MultiLock(
        repo_root=temp_repo,
        owner="test",
        ttl_seconds=60,
        timeout_seconds=5
    )

    # Request a lock with unknown name
    multi_lock.acquire(["queue", "unknown_subsystem"])

    try:
        # Should have logged a warning
        assert any("unknown" in record.message.lower() for record in caplog.records)

    finally:
        multi_lock.release()


def test_integration_with_umbrella_lock(temp_repo):
    """Test that subsystem locks work alongside umbrella tidy.lock."""
    # Acquire umbrella lock
    umbrella = Lease(
        lock_path=temp_repo / ".autonomous_runs" / ".locks" / "tidy.lock",
        owner="tidy_up",
        ttl_seconds=1800
    )
    umbrella.acquire(timeout_seconds=5)

    try:
        # Acquire subsystem locks (should not conflict)
        multi_lock = MultiLock(
            repo_root=temp_repo,
            owner="tidy_up:phase1",
            ttl_seconds=60,
            timeout_seconds=5
        )

        multi_lock.acquire(["queue", "archive"])

        try:
            # Both should be held successfully
            assert umbrella.is_acquired()
            assert multi_lock.is_acquired()
            assert len(multi_lock.held_locks()) == 2

        finally:
            multi_lock.release()

    finally:
        umbrella.release()


def test_canonical_order_constant():
    """Test that LOCK_ORDER is defined correctly."""
    assert LOCK_ORDER == ["queue", "runs", "archive", "docs"]
    assert len(LOCK_ORDER) == len(set(LOCK_ORDER))  # No duplicates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
