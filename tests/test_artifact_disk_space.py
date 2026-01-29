"""Tests for IMP-SAFETY-007: Disk space check before artifact writes.

Tests the disk space checking functionality to prevent disk exhaustion crashes.
"""

from unittest.mock import MagicMock, patch

import pytest

from autopack.autonomy.action_executor import SafeActionExecutor
from autopack.disk_space import (check_disk_space, ensure_disk_space,
                                 get_available_disk_space)
from autopack.exceptions import DiskSpaceError


class TestCheckDiskSpace:
    """Tests for check_disk_space function."""

    def test_check_disk_space_sufficient_space(self, tmp_path):
        """Test that check returns True when sufficient space is available."""
        # tmp_path should have plenty of space on any normal system
        result = check_disk_space(tmp_path, required_bytes=1000, min_free_bytes=1000)
        assert result is True

    def test_check_disk_space_insufficient_space(self, tmp_path):
        """Test that check returns False when insufficient space is available."""
        # Request an impossibly large amount of space
        result = check_disk_space(
            tmp_path,
            required_bytes=0,
            min_free_bytes=10**18,  # 1 exabyte
        )
        assert result is False

    def test_check_disk_space_with_file_path(self, tmp_path):
        """Test that check works with file paths (uses parent directory)."""
        file_path = tmp_path / "subdir" / "test.txt"
        result = check_disk_space(file_path, required_bytes=1000, min_free_bytes=1000)
        assert result is True

    def test_check_disk_space_nonexistent_path_walks_up(self, tmp_path):
        """Test that check walks up to find existing directory."""
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / "file.txt"
        result = check_disk_space(deep_path, required_bytes=1000, min_free_bytes=1000)
        assert result is True

    @patch("autopack.disk_space.shutil.disk_usage")
    def test_check_disk_space_os_error_returns_true(self, mock_disk_usage, tmp_path):
        """Test that OSError during check returns True (fail open)."""
        mock_disk_usage.side_effect = OSError("Disk error")
        result = check_disk_space(tmp_path, required_bytes=1000, min_free_bytes=1000)
        # Should return True (proceed with caution) when check fails
        assert result is True


class TestEnsureDiskSpace:
    """Tests for ensure_disk_space function."""

    def test_ensure_disk_space_sufficient_space(self, tmp_path):
        """Test that ensure does not raise when sufficient space is available."""
        # Should not raise
        ensure_disk_space(tmp_path, required_bytes=1000, min_free_bytes=1000)

    def test_ensure_disk_space_insufficient_space_raises(self, tmp_path):
        """Test that ensure raises DiskSpaceError when insufficient space."""
        with pytest.raises(DiskSpaceError) as exc_info:
            ensure_disk_space(
                tmp_path,
                required_bytes=0,
                min_free_bytes=10**18,  # 1 exabyte
            )

        error = exc_info.value
        assert "Insufficient disk space" in str(error)
        assert error.required_bytes > 0
        assert error.available_bytes >= 0

    def test_ensure_disk_space_includes_path_in_error(self, tmp_path):
        """Test that DiskSpaceError includes the path."""
        target_path = tmp_path / "test_file.txt"
        with pytest.raises(DiskSpaceError) as exc_info:
            ensure_disk_space(
                target_path,
                required_bytes=0,
                min_free_bytes=10**18,
            )

        assert exc_info.value.path is not None


class TestGetAvailableDiskSpace:
    """Tests for get_available_disk_space function."""

    def test_get_available_disk_space_existing_path(self, tmp_path):
        """Test getting available space for existing path."""
        space = get_available_disk_space(tmp_path)
        assert space > 0

    def test_get_available_disk_space_nonexistent_path(self, tmp_path):
        """Test getting available space for path that doesn't exist (walks up)."""
        nonexistent = tmp_path / "does" / "not" / "exist"
        space = get_available_disk_space(nonexistent)
        # Should still return valid space by walking up to tmp_path
        assert space > 0

    @patch("autopack.disk_space.shutil.disk_usage")
    def test_get_available_disk_space_os_error(self, mock_disk_usage, tmp_path):
        """Test that OSError returns -1."""
        mock_disk_usage.side_effect = OSError("Disk error")
        space = get_available_disk_space(tmp_path)
        assert space == -1


class TestSafeActionExecutorDiskSpace:
    """Tests for disk space check integration in SafeActionExecutor."""

    def test_write_artifact_checks_disk_space(self, tmp_path):
        """Test that write_artifact checks disk space before writing."""
        executor = SafeActionExecutor(workspace_root=tmp_path)

        # Write should succeed when sufficient space
        result = executor.write_artifact(
            ".autonomous_runs/test.txt",
            "test content",
        )
        assert result.success is True
        assert result.executed is True

    @patch("autopack.autonomy.action_executor.check_disk_space")
    def test_write_artifact_fails_on_insufficient_space(self, mock_check, tmp_path):
        """Test that write_artifact fails when disk space check fails."""
        mock_check.return_value = False

        executor = SafeActionExecutor(workspace_root=tmp_path)
        result = executor.write_artifact(
            ".autonomous_runs/test.txt",
            "test content",
        )

        assert result.success is False
        assert result.executed is False
        assert result.error == "DiskSpaceError"
        assert "Insufficient disk space" in result.reason

    def test_write_artifact_dry_run_skips_disk_check(self, tmp_path):
        """Test that dry run mode doesn't check disk space."""
        executor = SafeActionExecutor(workspace_root=tmp_path, dry_run=True)

        result = executor.write_artifact(
            ".autonomous_runs/test.txt",
            "test content",
        )

        # Dry run should succeed without actually writing
        assert result.success is True
        assert result.executed is False
        assert "Dry run" in result.reason


class TestDiskSpaceErrorException:
    """Tests for DiskSpaceError exception."""

    def test_disk_space_error_attributes(self):
        """Test that DiskSpaceError has all expected attributes."""
        error = DiskSpaceError(
            "Insufficient disk space",
            required_bytes=1000000,
            available_bytes=500000,
            path="/some/path/file.txt",
        )

        assert str(error) == "Insufficient disk space"
        assert error.required_bytes == 1000000
        assert error.available_bytes == 500000
        assert error.path == "/some/path/file.txt"

    def test_disk_space_error_default_values(self):
        """Test DiskSpaceError default values."""
        error = DiskSpaceError("Disk full")

        assert error.required_bytes == 0
        assert error.available_bytes == 0
        assert error.path is None


class TestConfigIntegration:
    """Tests for config integration."""

    def test_min_disk_space_bytes_config_exists(self):
        """Test that min_disk_space_bytes config setting exists."""
        from autopack.config import settings

        # Should have a default value
        assert hasattr(settings, "min_disk_space_bytes")
        assert settings.min_disk_space_bytes > 0

    def test_min_disk_space_bytes_default_100mb(self):
        """Test that default is 100MB."""
        from autopack.config import settings

        # Default should be 100MB (100,000,000 bytes)
        assert settings.min_disk_space_bytes == 100_000_000

    def test_check_disk_space_uses_config_default(self, tmp_path):
        """Test that check_disk_space uses config default when min_free_bytes not specified."""
        from autopack.config import settings

        with patch("autopack.disk_space.shutil.disk_usage") as mock_usage:
            # Set up mock to return less than config minimum
            mock_usage.return_value = MagicMock(free=settings.min_disk_space_bytes - 1000)

            result = check_disk_space(tmp_path, required_bytes=0)
            # Should fail because free space is less than config minimum
            assert result is False
