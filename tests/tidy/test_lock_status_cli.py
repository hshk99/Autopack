"""
Tests for BUILD-161: Lock Status UX and Safe Stale Lock Breaking.

Tests cover:
- Lock status reading and parsing
- PID running detection
- Safe lock breaking policy
- CLI integration (--lock-status, --break-stale-lock)
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# Ensure tidy scripts are importable
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "tidy"))

from lease import (
    LockStatus,
    pid_running,
    read_lock_status,
    break_stale_lock,
    lock_path_for_name,
    print_lock_status
)


class TestPIDRunning:
    """Test PID running detection (platform-independent)."""

    def test_current_process_running(self):
        """Test that current process PID is detected as running."""
        pid = os.getpid()
        assert pid_running(pid) is True

    def test_invalid_pid_not_running(self):
        """Test that clearly invalid PID returns False."""
        # PID 999999 is very unlikely to exist
        assert pid_running(999999) is False

    def test_pid_1_handling(self):
        """Test PID 1 handling (init/system process)."""
        # On Unix, PID 1 is init (always running)
        # On Windows, PID 1 may not exist
        # Result can be True, False, or None (permission)
        result = pid_running(1)
        assert result in [True, False, None]


class TestReadLockStatus:
    """Test lock status reading and parsing."""

    def test_lock_not_exists(self, tmp_path):
        """Test status when lock file doesn't exist."""
        lock_path = tmp_path / "nonexistent.lock"
        status = read_lock_status(lock_path)

        assert status.path == lock_path
        assert status.exists is False
        assert status.owner is None

    def test_valid_lock_parsing(self, tmp_path):
        """Test parsing valid lock file with all fields."""
        lock_path = tmp_path / "test.lock"
        now = datetime.utcnow()
        expires = now + timedelta(seconds=1800)

        lock_data = {
            "owner": "test_owner",
            "pid": 12345,
            "token": "test-token-uuid",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path, grace_seconds=120)

        assert status.exists is True
        assert status.owner == "test_owner"
        assert status.pid == 12345
        assert status.token == "test-token-uuid"
        assert status.created_at == now.isoformat() + "Z"
        assert status.expires_at == expires.isoformat() + "Z"
        assert status.expired is False  # Not expired yet
        assert status.malformed is False

    def test_expired_lock_detection(self, tmp_path):
        """Test detection of expired lock (past grace period)."""
        lock_path = tmp_path / "expired.lock"
        now = datetime.utcnow()
        # Expired 10 minutes ago
        expires = now - timedelta(seconds=600)

        lock_data = {
            "owner": "old_owner",
            "pid": 99999,
            "token": "old-token",
            "created_at": (now - timedelta(seconds=1800)).isoformat() + "Z",
            "last_renewed_at": (now - timedelta(seconds=600)).isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path, grace_seconds=120)

        assert status.expired is True  # Expired + grace period passed

    def test_lock_within_grace_period(self, tmp_path):
        """Test lock that is expired but within grace period."""
        lock_path = tmp_path / "grace.lock"
        now = datetime.utcnow()
        # Expired 1 minute ago (within 2 min grace period)
        expires = now - timedelta(seconds=60)

        lock_data = {
            "owner": "recent_owner",
            "pid": 12345,
            "token": "recent-token",
            "created_at": (now - timedelta(seconds=1800)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path, grace_seconds=120)

        assert status.expired is False  # Still within grace period

    def test_malformed_json(self, tmp_path):
        """Test handling of malformed JSON lock file."""
        lock_path = tmp_path / "malformed.lock"
        lock_path.write_text("{invalid json", encoding="utf-8")

        status = read_lock_status(lock_path)

        assert status.exists is True
        assert status.malformed is True
        assert "Invalid JSON" in status.error

    def test_missing_fields(self, tmp_path):
        """Test lock file with missing required fields."""
        lock_path = tmp_path / "partial.lock"
        lock_data = {"owner": "partial_owner"}  # Missing pid, expires_at, etc.

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path)

        assert status.exists is True
        assert status.owner == "partial_owner"
        assert status.pid is None
        assert status.expires_at is None
        assert status.expired is None  # Cannot determine


class TestBreakStaleLock:
    """Test safe lock breaking policy."""

    def test_lock_does_not_exist(self, tmp_path):
        """Test attempting to break non-existent lock."""
        lock_path = tmp_path / "nonexistent.lock"
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)

        assert did_break is False
        assert "does not exist" in msg

    def test_lock_not_expired_cannot_break(self, tmp_path):
        """Test that active (non-expired) locks cannot be broken."""
        lock_path = tmp_path / "active.lock"
        now = datetime.utcnow()
        expires = now + timedelta(seconds=1800)  # Expires in 30 min

        lock_data = {
            "owner": "active_owner",
            "pid": os.getpid(),
            "token": "active-token",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)

        assert did_break is False
        assert "not expired" in msg
        assert lock_path.exists()  # Lock still exists

    def test_expired_lock_pid_not_running_breaks(self, tmp_path):
        """Test that expired lock with non-running PID can be broken."""
        lock_path = tmp_path / "stale.lock"
        now = datetime.utcnow()
        expires = now - timedelta(seconds=600)  # Expired 10 min ago

        lock_data = {
            "owner": "dead_owner",
            "pid": 999999,  # Very unlikely to be running
            "token": "dead-token",
            "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)

        assert did_break is True
        assert "Broke stale lock" in msg
        assert not lock_path.exists()  # Lock file deleted

    def test_expired_lock_pid_running_cannot_break(self, tmp_path):
        """Test that expired lock with running PID cannot be broken."""
        lock_path = tmp_path / "running.lock"
        now = datetime.utcnow()
        expires = now - timedelta(seconds=600)  # Expired but process still running

        lock_data = {
            "owner": "running_owner",
            "pid": os.getpid(),  # Current process (definitely running)
            "token": "running-token",
            "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)

        assert did_break is False
        assert "Process is still running" in msg
        assert lock_path.exists()  # Lock still exists

    def test_malformed_lock_requires_force(self, tmp_path):
        """Test that malformed locks require --force to break."""
        lock_path = tmp_path / "malformed.lock"
        lock_path.write_text("{invalid json", encoding="utf-8")

        # Without force
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)
        assert did_break is False
        assert "malformed" in msg.lower()
        assert "force" in msg.lower()
        assert lock_path.exists()

        # With force
        did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=True)
        assert did_break is True
        assert "Broke malformed lock" in msg
        assert not lock_path.exists()

    def test_expired_lock_pid_unknown_requires_force(self, tmp_path):
        """Test that expired lock with unknown PID status requires --force."""
        lock_path = tmp_path / "unknown_pid.lock"
        now = datetime.utcnow()
        expires = now - timedelta(seconds=600)

        # Use PID 1 which may have permission issues on some systems
        lock_data = {
            "owner": "unknown_owner",
            "pid": 1,  # PID 1 might return None (permission denied)
            "token": "unknown-token",
            "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

        # Check if PID 1 returns unknown status
        if pid_running(1) is None:
            # Without force
            did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=False)
            assert did_break is False
            assert "Cannot verify" in msg or "force" in msg.lower()
            assert lock_path.exists()

            # With force
            did_break, msg = break_stale_lock(lock_path, grace_seconds=120, force=True)
            assert did_break is True
            assert not lock_path.exists()


class TestLockPathForName:
    """Test lock path resolution."""

    def test_default_tidy_lock(self, tmp_path):
        """Test default tidy lock path."""
        lock_path = lock_path_for_name(tmp_path, "tidy")
        expected = tmp_path / ".autonomous_runs" / ".locks" / "tidy.lock"
        assert lock_path == expected

    def test_custom_lock_name(self, tmp_path):
        """Test custom lock name."""
        lock_path = lock_path_for_name(tmp_path, "archive")
        expected = tmp_path / ".autonomous_runs" / ".locks" / "archive.lock"
        assert lock_path == expected


class TestCLIIntegration:
    """Test CLI integration (smoke tests using subprocess)."""

    def test_lock_status_no_lock(self, tmp_path):
        """Test --lock-status when no lock exists."""
        import subprocess

        # Use tmp_path as repo root
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                "--lock-status",
                "--lock-name", "test_no_lock"
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "LOCK STATUS" in result.stdout
        assert "Exists:           False" in result.stdout

    def test_lock_status_with_active_lock(self, tmp_path):
        """Test --lock-status with active lock file."""
        # Create a fake active lock
        lock_path = REPO_ROOT / ".autonomous_runs" / ".locks" / "test_active.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        expires = now + timedelta(seconds=1800)

        lock_data = {
            "owner": "test_cli",
            "pid": os.getpid(),
            "token": "test-cli-token",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        try:
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")

            import subprocess
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                    "--lock-status",
                    "--lock-name", "test_active"
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
            assert "LOCK STATUS" in result.stdout
            assert "Exists:           True" in result.stdout
            assert "Owner:            test_cli" in result.stdout
            assert "Lock is active and valid" in result.stdout

        finally:
            lock_path.unlink(missing_ok=True)

    def test_break_stale_lock_cli(self, tmp_path):
        """Test --break-stale-lock CLI command."""
        # Create a stale lock
        lock_path = REPO_ROOT / ".autonomous_runs" / ".locks" / "test_stale.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        expires = now - timedelta(seconds=600)  # Expired 10 min ago

        lock_data = {
            "owner": "stale_cli",
            "pid": 999999,  # Non-existent PID
            "token": "stale-cli-token",
            "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z"
        }

        try:
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")

            import subprocess
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                    "--break-stale-lock",
                    "--lock-name", "test_stale"
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
            assert "Broke stale lock" in result.stdout
            assert not lock_path.exists()  # Lock should be deleted

        finally:
            lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
