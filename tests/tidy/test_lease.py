"""
Tests for tidy system lease (cross-process locking).

Validates:
- Basic acquire/release
- Stale lock detection and breaking
- Timeout behavior
- Heartbeat renewal
- Ownership verification
- Concurrent access simulation
"""

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
import pytest

# Add scripts/tidy to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tidy"))

from lease import Lease


class TestLeaseBasics:
    """Test basic lease acquisition and release."""

    def test_acquire_and_release(self):
        """Test that lease can be acquired and released cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            assert lease.is_acquired()
            assert lock_path.exists()

            # Verify lock file contents
            lock_data = json.loads(lock_path.read_text())
            assert lock_data["owner"] == "test"
            assert "token" in lock_data
            assert "expires_at" in lock_data

            lease.release()
            assert not lease.is_acquired()
            assert not lock_path.exists()

    def test_acquire_timeout(self):
        """Test that acquisition times out when lock is held."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            # First lease acquires successfully
            lease1 = Lease(lock_path=lock_path, owner="lease1", ttl_seconds=60)
            lease1.acquire(timeout_seconds=5)

            # Second lease times out
            lease2 = Lease(lock_path=lock_path, owner="lease2", ttl_seconds=60)
            with pytest.raises(TimeoutError, match="Could not acquire lease"):
                lease2.acquire(timeout_seconds=2)

            # Release first lease
            lease1.release()

            # Now second lease can acquire
            lease2.acquire(timeout_seconds=5)
            assert lease2.is_acquired()
            lease2.release()

    def test_cannot_acquire_twice(self):
        """Test that same instance cannot acquire twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            with pytest.raises(RuntimeError, match="Lease already acquired"):
                lease.acquire(timeout_seconds=5)

            lease.release()

    def test_release_is_idempotent(self):
        """Test that release can be called multiple times safely."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)
            lease.release()

            # Second release should not raise
            lease.release()


class TestStaleLeaseDetection:
    """Test stale lock detection and automatic breaking."""

    def test_stale_lock_is_broken(self):
        """Test that expired locks are automatically broken."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            # Create an expired lock manually
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            expired_data = {
                "owner": "stale_process",
                "token": "abc123",
                "pid": 99999,
                "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                "expires_at": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
                "last_renewed_at": (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z",
            }
            lock_path.write_text(json.dumps(expired_data, indent=2))

            # New lease should break the stale lock and acquire
            lease = Lease(
                lock_path=lock_path, owner="new_process", ttl_seconds=60, grace_period_seconds=10
            )
            lease.acquire(timeout_seconds=5)

            assert lease.is_acquired()

            # Verify lock was replaced
            lock_data = json.loads(lock_path.read_text())
            assert lock_data["owner"] == "new_process"
            assert lock_data["token"] != "abc123"

            lease.release()

    def test_valid_lock_is_not_broken(self):
        """Test that non-expired locks are respected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            # Create a valid lock
            lease1 = Lease(lock_path=lock_path, owner="owner1", ttl_seconds=300)
            lease1.acquire(timeout_seconds=5)

            # Second lease should timeout (not break valid lock)
            lease2 = Lease(lock_path=lock_path, owner="owner2", ttl_seconds=300)
            with pytest.raises(TimeoutError):
                lease2.acquire(timeout_seconds=2)

            lease1.release()

    def test_malformed_lock_is_broken(self):
        """Test that unreadable/corrupt locks are broken."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            # Create a malformed lock file
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text("not valid json {{{")

            # Should break malformed lock and acquire
            lease = Lease(lock_path=lock_path, owner="new_process", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            assert lease.is_acquired()
            lease.release()


class TestLeaseRenewal:
    """Test heartbeat renewal functionality."""

    def test_renew_extends_ttl(self):
        """Test that renewal extends the expiry time."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            # Get initial expiry
            lock_data_before = json.loads(lock_path.read_text())
            expires_before = datetime.fromisoformat(lock_data_before["expires_at"].rstrip("Z"))

            # Wait a bit and renew
            time.sleep(0.5)
            renewed = lease.renew()
            assert renewed

            # Check that expiry was extended
            lock_data_after = json.loads(lock_path.read_text())
            expires_after = datetime.fromisoformat(lock_data_after["expires_at"].rstrip("Z"))

            assert expires_after > expires_before
            assert lock_data_after["last_renewed_at"] > lock_data_before["last_renewed_at"]

            lease.release()

    def test_renew_without_acquire_fails(self):
        """Test that renewal fails if lease was not acquired."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)

            with pytest.raises(RuntimeError, match="Cannot renew lease that was not acquired"):
                lease.renew()

    def test_renew_detects_ownership_change(self):
        """Test that renewal fails if ownership changed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            # Simulate another process stealing the lock
            stolen_data = json.loads(lock_path.read_text())
            stolen_data["token"] = "stolen_token"
            stolen_data["owner"] = "hacker"
            lock_path.write_text(json.dumps(stolen_data, indent=2))

            # Renewal should fail
            renewed = lease.renew()
            assert not renewed
            assert not lease.is_acquired()  # Marked as lost

    def test_renew_fails_if_lock_deleted(self):
        """Test that renewal fails gracefully if lock file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            # Delete lock file externally
            lock_path.unlink()

            # Renewal should fail
            renewed = lease.renew()
            assert not renewed


class TestConcurrentAccess:
    """Test concurrent access scenarios (simulated within single process)."""

    def test_serial_acquisition(self):
        """Test that multiple processes can acquire serially."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            for i in range(3):
                lease = Lease(lock_path=lock_path, owner=f"process_{i}", ttl_seconds=60)
                lease.acquire(timeout_seconds=5)
                assert lease.is_acquired()

                lock_data = json.loads(lock_path.read_text())
                assert lock_data["owner"] == f"process_{i}"

                lease.release()

    def test_polling_acquires_after_release(self):
        """Test that polling successfully acquires after lease is released."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease1 = Lease(lock_path=lock_path, owner="lease1", ttl_seconds=60, poll_seconds=0.1)
            lease1.acquire(timeout_seconds=5)

            # Start "concurrent" acquisition in background (simulated with timing)
            lease2 = Lease(lock_path=lock_path, owner="lease2", ttl_seconds=60, poll_seconds=0.1)

            # Release lease1 after small delay
            time.sleep(0.3)
            lease1.release()

            # lease2 should acquire quickly (within poll interval)
            lease2.acquire(timeout_seconds=5)
            assert lease2.is_acquired()

            lease2.release()


class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_short_ttl_with_grace_period(self):
        """Test that grace period prevents premature lock breaking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            # Create a lock that expired 1 second ago but within grace period
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            recent_expired = {
                "owner": "recent_process",
                "token": "xyz789",
                "pid": 88888,
                "created_at": (datetime.utcnow() - timedelta(seconds=10)).isoformat() + "Z",
                "expires_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat()
                + "Z",  # Expired 1s ago
                "last_renewed_at": (datetime.utcnow() - timedelta(seconds=1)).isoformat() + "Z",
            }
            lock_path.write_text(json.dumps(recent_expired, indent=2))

            # With large grace period, lock should NOT be broken
            lease = Lease(
                lock_path=lock_path, owner="new_process", ttl_seconds=60, grace_period_seconds=120
            )

            with pytest.raises(TimeoutError):
                lease.acquire(timeout_seconds=2)

    def test_zero_ttl(self):
        """Test that zero TTL lease works (immediate expiry after acquisition)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / ".locks" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=0, grace_period_seconds=0)
            lease.acquire(timeout_seconds=5)

            # Lock should be immediately stale (but still held by this instance)
            assert lease.is_acquired()

            # Another process can break it immediately
            lease2 = Lease(
                lock_path=lock_path, owner="breaker", ttl_seconds=60, grace_period_seconds=0
            )
            lease2.acquire(timeout_seconds=5)  # Should succeed by breaking stale lock

            assert lease2.is_acquired()
            lease2.release()

    def test_lock_directory_created_automatically(self):
        """Test that lock directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "nested" / "locks" / "dir" / "test.lock"

            lease = Lease(lock_path=lock_path, owner="test", ttl_seconds=60)
            lease.acquire(timeout_seconds=5)

            assert lock_path.exists()
            assert lock_path.parent.exists()

            lease.release()
