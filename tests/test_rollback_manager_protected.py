"""Tests for rollback manager protected file blocking (IMP-SAFETY-006)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.rollback_manager import RollbackManager


class TestRollbackManagerProtectedFiles:
    """Tests for protected file blocking in rollback operations."""

    @pytest.fixture
    def temp_workspace(self, tmp_path: Path) -> Path:
        """Create a temporary workspace for testing."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture
    def rollback_manager(self, temp_workspace: Path) -> RollbackManager:
        """Create a rollback manager instance."""
        return RollbackManager(
            workspace=temp_workspace,
            run_id="test-run-1",
            phase_id="test-phase-1",
        )

    def test_create_savepoint_success(self, rollback_manager: RollbackManager):
        """Test successful savepoint creation."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, error = rollback_manager.create_savepoint()

            assert success is True
            assert error is None
            assert rollback_manager.savepoint_tag is not None
            assert mock_run.called

    def test_rollback_blocks_when_protected_files_detected(self, rollback_manager: RollbackManager):
        """Test that rollback is blocked when protected files would be affected."""
        rollback_manager.savepoint_tag = "save-before-test-run-1-test-phase-1-20240101-120000"

        with patch.object(rollback_manager, "_check_protected_untracked_files") as mock_check:
            # Simulate protected files detected
            mock_check.return_value = (
                True,
                [".env", "autopack.db"],
            )

            success, error = rollback_manager.rollback_to_savepoint(
                reason="Test rollback", safe_clean=True
            )

            # Should fail with protected files error
            assert success is False
            assert error == "Protected files would be deleted"
            mock_check.assert_called_once()

    def test_rollback_proceeds_when_no_protected_files(self, rollback_manager: RollbackManager):
        """Test that rollback proceeds when no protected files detected."""
        rollback_manager.savepoint_tag = "save-before-test-run-1-test-phase-1-20240101-120000"

        with (
            patch.object(rollback_manager, "_check_protected_untracked_files") as mock_check,
            patch("subprocess.run") as mock_run,
        ):
            # Simulate no protected files
            mock_check.return_value = (False, [])

            # Mock git reset and clean success
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, error = rollback_manager.rollback_to_savepoint(
                reason="Test rollback", safe_clean=True
            )

            # Should succeed
            assert success is True
            assert error is None
            mock_check.assert_called_once()

    def test_rollback_proceeds_with_safe_clean_false(self, rollback_manager: RollbackManager):
        """Test that rollback proceeds with safe_clean=False even with protected files."""
        rollback_manager.savepoint_tag = "save-before-test-run-1-test-phase-1-20240101-120000"

        with (
            patch.object(rollback_manager, "_check_protected_untracked_files") as mock_check,
            patch("subprocess.run") as mock_run,
        ):
            # Mock git reset and clean success
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            success, error = rollback_manager.rollback_to_savepoint(
                reason="Test rollback", safe_clean=False
            )

            # Should succeed (bypass protected check)
            assert success is True
            assert error is None
            # Protected check should not be called when safe_clean=False
            mock_check.assert_not_called()

    def test_check_protected_files_detects_env_file(
        self, rollback_manager: RollbackManager, temp_workspace: Path
    ):
        """Test that .env file is detected as protected."""
        with patch("subprocess.run") as mock_run:
            # Simulate git clean dry run with .env file
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Would remove .env\nWould remove temp.txt\n",
                stderr="",
            )

            has_protected, protected_files = rollback_manager._check_protected_untracked_files()

            assert has_protected is True
            assert ".env" in protected_files
            assert "temp.txt" not in protected_files

    def test_check_protected_files_detects_db_file(self, rollback_manager: RollbackManager):
        """Test that .db files are detected as protected."""
        with patch("subprocess.run") as mock_run:
            # Simulate git clean dry run with .db file
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Would remove autopack.db\nWould remove test.db\nWould remove temp.txt\n",
                stderr="",
            )

            has_protected, protected_files = rollback_manager._check_protected_untracked_files()

            assert has_protected is True
            assert "autopack.db" in protected_files
            assert "test.db" in protected_files
            assert "temp.txt" not in protected_files

    def test_check_protected_files_detects_autonomous_runs_dir(
        self, rollback_manager: RollbackManager
    ):
        """Test that .autonomous_runs/ directory is detected as protected."""
        with patch("subprocess.run") as mock_run:
            # Simulate git clean dry run with .autonomous_runs directory
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Would remove .autonomous_runs/run123/artifacts.txt\n",
                stderr="",
            )

            has_protected, protected_files = rollback_manager._check_protected_untracked_files()

            assert has_protected is True
            assert ".autonomous_runs/run123/artifacts.txt" in protected_files

    def test_check_protected_files_no_match(self, rollback_manager: RollbackManager):
        """Test that non-protected files are not detected as protected."""
        with patch("subprocess.run") as mock_run:
            # Simulate git clean dry run with only unprotected files
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Would remove temp.txt\nWould remove logs.txt\nWould remove cache/\n",
                stderr="",
            )

            has_protected, protected_files = rollback_manager._check_protected_untracked_files()

            assert has_protected is False
            assert len(protected_files) == 0

    def test_no_savepoint_tag_error(self, rollback_manager: RollbackManager):
        """Test that rollback fails gracefully when no savepoint tag is set."""
        rollback_manager.savepoint_tag = None

        success, error = rollback_manager.rollback_to_savepoint(reason="Test")

        assert success is False
        assert error == "no_savepoint_tag_set"
