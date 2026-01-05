"""
Tests for BUILD-161: Lock Status UX and Safe Stale Lock Breaking.
BUILD-162: ASCII-safe lock output and comprehensive lock listing.

Tests cover:
- Lock status reading and parsing
- PID running detection
- Safe lock breaking policy
- CLI integration (--lock-status, --break-stale-lock)
- ASCII-safe output (--ascii, --unicode)
- All lock listing (--all)
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# Ensure tidy scripts are importable
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "tidy"))

from lease import (
    pid_running,
    read_lock_status,
    break_stale_lock,
    lock_path_for_name,
    print_lock_status,
    should_use_ascii,
    print_all_lock_status,
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
            "expires_at": expires.isoformat() + "Z",
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
                "--lock-name",
                "test_no_lock",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
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
            "expires_at": expires.isoformat() + "Z",
        }

        try:
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                    "--lock-status",
                    "--lock-name",
                    "test_active",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
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
            "expires_at": expires.isoformat() + "Z",
        }

        try:
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")

            import subprocess

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                    "--break-stale-lock",
                    "--lock-name",
                    "test_stale",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "Broke stale lock" in result.stdout
            assert not lock_path.exists()  # Lock should be deleted

        finally:
            lock_path.unlink(missing_ok=True)


class TestASCIIMode:
    """Test BUILD-162: ASCII-safe output mode."""

    def test_should_use_ascii_force_ascii(self):
        """Test that force_ascii=True always returns ASCII mode."""
        assert should_use_ascii(force_ascii=True, force_unicode=False) is True
        assert should_use_ascii(force_ascii=True, force_unicode=True) is True  # ASCII wins

    def test_should_use_ascii_force_unicode(self):
        """Test that force_unicode=True returns Unicode mode when not forced ASCII."""
        assert should_use_ascii(force_ascii=False, force_unicode=True) is False

    def test_should_use_ascii_auto_detect(self):
        """Test auto-detection based on sys.stdout.encoding."""
        # Auto-detect should return bool based on current environment
        result = should_use_ascii(force_ascii=False, force_unicode=False)
        assert isinstance(result, bool)

        # With UTF-8 encoding, should prefer Unicode
        if sys.stdout.encoding and "utf" in sys.stdout.encoding.lower():
            assert result is False
        # Otherwise, should use ASCII for safety
        else:
            assert result is True

    def test_print_lock_status_ascii_mode(self, tmp_path, capsys):
        """Test that ASCII mode produces no Unicode emojis."""
        lock_path = tmp_path / "test.lock"
        now = datetime.utcnow()
        expires = now + timedelta(seconds=1800)

        lock_data = {
            "owner": "test_owner",
            "pid": os.getpid(),
            "token": "test-token",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z",
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path)

        # Print in ASCII mode
        print_lock_status(status, ascii_mode=True)
        captured = capsys.readouterr()

        # Should contain ASCII markers, no Unicode emojis
        assert "[LOCK]" in captured.out
        assert "🔒" not in captured.out
        assert "✅" not in captured.out
        assert "❌" not in captured.out
        assert "⚠️" not in captured.out

    def test_print_lock_status_unicode_mode(self, tmp_path, capsys):
        """Test that Unicode mode produces emojis."""
        lock_path = tmp_path / "test.lock"
        now = datetime.utcnow()
        expires = now + timedelta(seconds=1800)

        lock_data = {
            "owner": "test_owner",
            "pid": os.getpid(),
            "token": "test-token",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z",
        }

        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path)

        # Print in Unicode mode
        print_lock_status(status, ascii_mode=False)
        captured = capsys.readouterr()

        # Should contain Unicode emoji
        assert "🔒" in captured.out
        assert "[LOCK]" not in captured.out

    def test_stale_lock_ascii_indicators(self, tmp_path, capsys):
        """Test all status indicators in ASCII mode."""
        now = datetime.utcnow()

        # Test 1: Stale lock (OK to break)
        lock_path = tmp_path / "stale.lock"
        expires = now - timedelta(seconds=600)
        lock_data = {
            "owner": "stale_owner",
            "pid": 999999,  # Not running
            "token": "stale-token",
            "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
            "last_renewed_at": expires.isoformat() + "Z",
            "expires_at": expires.isoformat() + "Z",
        }
        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")
        status = read_lock_status(lock_path, grace_seconds=120)

        print_lock_status(status, ascii_mode=True)
        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "✅" not in captured.out


class TestAllLockStatus:
    """Test BUILD-162: --all lock listing."""

    def test_print_all_lock_status_no_locks_dir(self, tmp_path, capsys):
        """Test --all when locks directory doesn't exist."""
        print_all_lock_status(tmp_path, grace_seconds=120, ascii_mode=True)
        captured = capsys.readouterr()

        assert "ALL LOCK STATUS" in captured.out
        assert "does not exist" in captured.out

    def test_print_all_lock_status_empty_dir(self, tmp_path, capsys):
        """Test --all when locks directory is empty."""
        locks_dir = tmp_path / ".autonomous_runs" / ".locks"
        locks_dir.mkdir(parents=True, exist_ok=True)

        print_all_lock_status(tmp_path, grace_seconds=120, ascii_mode=True)
        captured = capsys.readouterr()

        assert "ALL LOCK STATUS" in captured.out
        assert "No lock files found" in captured.out

    def test_print_all_lock_status_multiple_locks(self, tmp_path, capsys):
        """Test --all with multiple lock files."""
        locks_dir = tmp_path / ".autonomous_runs" / ".locks"
        locks_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()

        # Create active lock
        active_lock = locks_dir / "tidy.lock"
        active_lock.write_text(
            json.dumps(
                {
                    "owner": "tidy",
                    "pid": os.getpid(),
                    "token": "tidy-token",
                    "created_at": now.isoformat() + "Z",
                    "last_renewed_at": now.isoformat() + "Z",
                    "expires_at": (now + timedelta(seconds=1800)).isoformat() + "Z",
                }
            ),
            encoding="utf-8",
        )

        # Create stale lock
        stale_lock = locks_dir / "archive.lock"
        stale_lock.write_text(
            json.dumps(
                {
                    "owner": "archive",
                    "pid": 999999,
                    "token": "archive-token",
                    "created_at": (now - timedelta(seconds=2400)).isoformat() + "Z",
                    "last_renewed_at": (now - timedelta(seconds=600)).isoformat() + "Z",
                    "expires_at": (now - timedelta(seconds=600)).isoformat() + "Z",
                }
            ),
            encoding="utf-8",
        )

        # Create malformed lock
        malformed_lock = locks_dir / "malformed.lock"
        malformed_lock.write_text("{invalid json", encoding="utf-8")

        print_all_lock_status(tmp_path, grace_seconds=120, ascii_mode=True)
        captured = capsys.readouterr()

        assert "ALL LOCK STATUS" in captured.out
        assert "Lock files found: 3" in captured.out

        # Check all locks are listed
        assert "Lock: tidy.lock" in captured.out
        assert "Lock: archive.lock" in captured.out
        assert "Lock: malformed.lock" in captured.out

        # Check status indicators (ASCII mode)
        assert "[LOCK]" in captured.out  # Active lock
        assert "[OK]" in captured.out  # Stale lock
        assert "[ERROR]" in captured.out  # Malformed lock

    def test_print_all_lock_status_unicode_mode(self, tmp_path, capsys):
        """Test --all with Unicode mode."""
        locks_dir = tmp_path / ".autonomous_runs" / ".locks"
        locks_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()

        active_lock = locks_dir / "test.lock"
        active_lock.write_text(
            json.dumps(
                {
                    "owner": "test",
                    "pid": os.getpid(),
                    "token": "test-token",
                    "created_at": now.isoformat() + "Z",
                    "last_renewed_at": now.isoformat() + "Z",
                    "expires_at": (now + timedelta(seconds=1800)).isoformat() + "Z",
                }
            ),
            encoding="utf-8",
        )

        print_all_lock_status(tmp_path, grace_seconds=120, ascii_mode=False)
        captured = capsys.readouterr()

        # Should use Unicode emoji
        assert "🔒" in captured.out
        assert "[LOCK]" not in captured.out


class TestBUILD162CLIIntegration:
    """Test BUILD-162 CLI integration."""

    def test_lock_status_ascii_flag(self):
        """Test --lock-status --ascii produces ASCII-only output."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                "--lock-status",
                "--lock-name",
                "test_ascii",
                "--ascii",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert result.returncode == 0
        assert "LOCK STATUS" in result.stdout
        # No Unicode emojis in output
        assert "🔒" not in result.stdout
        assert "✅" not in result.stdout
        assert "❌" not in result.stdout
        assert "⚠️" not in result.stdout

    def test_lock_status_all_flag(self):
        """Test --lock-status --all lists all locks."""
        import subprocess

        # Create a test lock
        lock_path = REPO_ROOT / ".autonomous_runs" / ".locks" / "test_all_1.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        lock_data = {
            "owner": "test_all",
            "pid": os.getpid(),
            "token": "test-token",
            "created_at": now.isoformat() + "Z",
            "last_renewed_at": now.isoformat() + "Z",
            "expires_at": (now + timedelta(seconds=1800)).isoformat() + "Z",
        }

        try:
            lock_path.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                    "--lock-status",
                    "--all",
                    "--ascii",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            assert result.returncode == 0
            assert "ALL LOCK STATUS" in result.stdout
            # Should list the test lock we created
            assert "Lock: test_all_1.lock" in result.stdout or "Lock files found:" in result.stdout

        finally:
            lock_path.unlink(missing_ok=True)

    def test_lock_status_all_ascii_combined(self):
        """Test --lock-status --all --ascii combination."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "tidy" / "tidy_up.py"),
                "--lock-status",
                "--all",
                "--ascii",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        assert result.returncode == 0
        assert "ALL LOCK STATUS" in result.stdout
        # No Unicode emojis in output
        assert "🔒" not in result.stdout
        assert "✅" not in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
