"""Contract tests for run checkpoint module.

These tests verify the run_checkpoint module behavior contract for PR-EXE-4.
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import subprocess

from autopack.executor.run_checkpoint import (
    RunCheckpoint,
    CheckpointResult,
    RollbackResult,
    create_run_checkpoint,
    rollback_to_checkpoint,
    log_run_rollback_action,
    perform_full_rollback,
)


class TestRunCheckpoint:
    """Contract tests for RunCheckpoint dataclass."""

    def test_short_commit_returns_first_8_chars(self):
        """Contract: short_commit returns first 8 characters of commit SHA."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abcdef1234567890",
            created_at=datetime.utcnow(),
        )

        assert checkpoint.short_commit() == "abcdef12"

    def test_short_commit_handles_short_sha(self):
        """Contract: short_commit handles commit shorter than 8 chars."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc",
            created_at=datetime.utcnow(),
        )

        assert checkpoint.short_commit() == "abc"

    def test_short_commit_handles_empty_sha(self):
        """Contract: short_commit returns 'unknown' for empty commit."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="",
            created_at=datetime.utcnow(),
        )

        assert checkpoint.short_commit() == "unknown"


class TestCheckpointResult:
    """Contract tests for CheckpointResult dataclass."""

    def test_success_result_has_checkpoint(self):
        """Contract: Successful result contains checkpoint data."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )
        result = CheckpointResult(success=True, checkpoint=checkpoint)

        assert result.success is True
        assert result.checkpoint is not None
        assert result.error is None

    def test_failure_result_has_error(self):
        """Contract: Failed result contains error message."""
        result = CheckpointResult(success=False, error="git_timeout")

        assert result.success is False
        assert result.checkpoint is None
        assert result.error == "git_timeout"


class TestRollbackResult:
    """Contract tests for RollbackResult dataclass."""

    def test_success_result_defaults(self):
        """Contract: Successful result has correct defaults."""
        result = RollbackResult(success=True)

        assert result.success is True
        assert result.error is None
        assert result.clean_failed is False
        assert result.branch_failed is False

    def test_partial_success_with_warnings(self):
        """Contract: Partial success can report non-fatal failures."""
        result = RollbackResult(
            success=True,
            clean_failed=True,
            branch_failed=True,
        )

        assert result.success is True
        assert result.clean_failed is True
        assert result.branch_failed is True


class TestCreateRunCheckpoint:
    """Contract tests for create_run_checkpoint function."""

    def test_creates_checkpoint_on_success(self, tmp_path):
        """Contract: Returns checkpoint with branch and commit on success."""
        with patch("subprocess.run") as mock_run:
            # Mock branch query
            branch_result = Mock()
            branch_result.returncode = 0
            branch_result.stdout = "main\n"
            branch_result.stderr = ""

            # Mock commit query
            commit_result = Mock()
            commit_result.returncode = 0
            commit_result.stdout = "abcdef1234567890\n"
            commit_result.stderr = ""

            mock_run.side_effect = [branch_result, commit_result]

            result = create_run_checkpoint(tmp_path)

            assert result.success is True
            assert result.checkpoint is not None
            assert result.checkpoint.branch == "main"
            assert result.checkpoint.commit == "abcdef1234567890"

    def test_returns_error_on_branch_failure(self, tmp_path):
        """Contract: Returns error when branch query fails."""
        with patch("subprocess.run") as mock_run:
            branch_result = Mock()
            branch_result.returncode = 1
            branch_result.stdout = ""
            branch_result.stderr = "fatal: not a git repository"

            mock_run.return_value = branch_result

            result = create_run_checkpoint(tmp_path)

            assert result.success is False
            assert "git_branch_failed" in result.error
            assert result.checkpoint is None

    def test_returns_error_on_commit_failure(self, tmp_path):
        """Contract: Returns error when commit query fails."""
        with patch("subprocess.run") as mock_run:
            # Mock branch query (success)
            branch_result = Mock()
            branch_result.returncode = 0
            branch_result.stdout = "main\n"
            branch_result.stderr = ""

            # Mock commit query (failure)
            commit_result = Mock()
            commit_result.returncode = 1
            commit_result.stdout = ""
            commit_result.stderr = "fatal: ambiguous argument"

            mock_run.side_effect = [branch_result, commit_result]

            result = create_run_checkpoint(tmp_path)

            assert result.success is False
            assert "git_commit_failed" in result.error

    def test_returns_error_on_timeout(self, tmp_path):
        """Contract: Returns error on subprocess timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            result = create_run_checkpoint(tmp_path)

            assert result.success is False
            assert result.error == "git_timeout"

    def test_returns_error_on_exception(self, tmp_path):
        """Contract: Returns error on unexpected exception."""
        with patch("subprocess.run", side_effect=OSError("Permission denied")):
            result = create_run_checkpoint(tmp_path)

            assert result.success is False
            assert "exception:" in result.error


class TestRollbackToCheckpoint:
    """Contract tests for rollback_to_checkpoint function."""

    def test_returns_error_for_empty_commit(self, tmp_path):
        """Contract: Returns error when checkpoint has no commit."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="",
            created_at=datetime.utcnow(),
        )

        result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

        assert result.success is False
        assert result.error == "no_checkpoint_commit"

    def test_rolls_back_successfully(self, tmp_path):
        """Contract: Successfully rolls back on all git operations succeeding."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # All operations succeed
            success_result = Mock()
            success_result.returncode = 0
            success_result.stdout = ""
            success_result.stderr = ""
            mock_run.return_value = success_result

            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is True
            assert result.error is None
            assert result.clean_failed is False
            assert result.branch_failed is False

    def test_returns_error_on_reset_failure(self, tmp_path):
        """Contract: Returns error when git reset fails."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            reset_result = Mock()
            reset_result.returncode = 1
            reset_result.stdout = ""
            reset_result.stderr = "error: could not reset"
            mock_run.return_value = reset_result

            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is False
            assert "git_reset_failed" in result.error

    def test_reports_clean_failure_as_warning(self, tmp_path):
        """Contract: Reports clean failure as non-fatal warning."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # Reset succeeds
            reset_result = Mock()
            reset_result.returncode = 0
            reset_result.stdout = ""
            reset_result.stderr = ""

            # Clean fails
            clean_result = Mock()
            clean_result.returncode = 1
            clean_result.stdout = ""
            clean_result.stderr = "warning: could not clean"

            # Checkout succeeds
            checkout_result = Mock()
            checkout_result.returncode = 0
            checkout_result.stdout = ""
            checkout_result.stderr = ""

            mock_run.side_effect = [reset_result, clean_result, checkout_result]

            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is True
            assert result.clean_failed is True

    def test_reports_branch_failure_as_warning(self, tmp_path):
        """Contract: Reports branch checkout failure as non-fatal warning."""
        checkpoint = RunCheckpoint(
            branch="feature-branch",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # Reset succeeds
            reset_result = Mock()
            reset_result.returncode = 0
            reset_result.stdout = ""
            reset_result.stderr = ""

            # Clean succeeds
            clean_result = Mock()
            clean_result.returncode = 0
            clean_result.stdout = ""
            clean_result.stderr = ""

            # Checkout fails
            checkout_result = Mock()
            checkout_result.returncode = 1
            checkout_result.stdout = ""
            checkout_result.stderr = "error: branch not found"

            mock_run.side_effect = [reset_result, clean_result, checkout_result]

            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is True
            assert result.branch_failed is True

    def test_skips_checkout_for_head_branch(self, tmp_path):
        """Contract: Skips branch checkout when branch is HEAD."""
        checkpoint = RunCheckpoint(
            branch="HEAD",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # Reset succeeds
            reset_result = Mock()
            reset_result.returncode = 0
            reset_result.stdout = ""
            reset_result.stderr = ""

            # Clean succeeds
            clean_result = Mock()
            clean_result.returncode = 0
            clean_result.stdout = ""
            clean_result.stderr = ""

            mock_run.side_effect = [reset_result, clean_result]

            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is True
            # Only 2 calls (reset, clean), no checkout
            assert mock_run.call_count == 2

    def test_returns_error_on_timeout(self, tmp_path):
        """Contract: Returns error on subprocess timeout."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            result = rollback_to_checkpoint(tmp_path, checkpoint, "test reason")

            assert result.success is False
            assert result.error == "git_timeout"


class TestLogRunRollbackAction:
    """Contract tests for log_run_rollback_action function."""

    def test_logs_rollback_to_file(self, tmp_path):
        """Contract: Logs rollback action to audit file."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123def456",
            created_at=datetime.utcnow(),
        )

        # Mock RunFileLayout at the import location
        with patch("autopack.file_layout.RunFileLayout") as mock_layout_class:
            mock_layout = Mock()
            mock_layout.base_dir = tmp_path
            mock_layout.ensure_directories = Mock()
            mock_layout_class.return_value = mock_layout

            result = log_run_rollback_action(
                run_id="run-123",
                checkpoint=checkpoint,
                reason="Test rollback",
                project_id="project-1",
            )

            assert result is True

            # Check log file was created
            log_file = tmp_path / "run_rollback.log"
            assert log_file.exists()

            content = log_file.read_text()
            assert "run-123" in content
            assert "abc123de" in content  # short commit
            assert "Test rollback" in content

    def test_returns_false_on_exception(self, tmp_path):
        """Contract: Returns False when logging fails."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch(
            "autopack.file_layout.RunFileLayout",
            side_effect=Exception("Layout error"),
        ):
            result = log_run_rollback_action(
                run_id="run-123",
                checkpoint=checkpoint,
                reason="Test",
            )

            assert result is False


class TestPerformFullRollback:
    """Contract tests for perform_full_rollback function."""

    def test_performs_rollback_and_logs(self, tmp_path):
        """Contract: Performs rollback and logs action on success."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # All git operations succeed
            success_result = Mock()
            success_result.returncode = 0
            success_result.stdout = ""
            success_result.stderr = ""
            mock_run.return_value = success_result

            with patch("autopack.executor.run_checkpoint.log_run_rollback_action") as mock_log:
                mock_log.return_value = True

                result = perform_full_rollback(
                    workspace=tmp_path,
                    checkpoint=checkpoint,
                    reason="Test reason",
                    run_id="run-123",
                    project_id="project-1",
                )

                assert result.success is True
                mock_log.assert_called_once_with(
                    "run-123", checkpoint, "Test reason", "project-1"
                )

    def test_skips_logging_on_rollback_failure(self, tmp_path):
        """Contract: Skips logging when rollback fails."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # Reset fails
            reset_result = Mock()
            reset_result.returncode = 1
            reset_result.stdout = ""
            reset_result.stderr = "error"
            mock_run.return_value = reset_result

            with patch("autopack.executor.run_checkpoint.log_run_rollback_action") as mock_log:
                result = perform_full_rollback(
                    workspace=tmp_path,
                    checkpoint=checkpoint,
                    reason="Test reason",
                    run_id="run-123",
                )

                assert result.success is False
                mock_log.assert_not_called()

    def test_succeeds_even_if_logging_fails(self, tmp_path):
        """Contract: Rollback succeeds even if logging fails."""
        checkpoint = RunCheckpoint(
            branch="main",
            commit="abc123",
            created_at=datetime.utcnow(),
        )

        with patch("subprocess.run") as mock_run:
            # All git operations succeed
            success_result = Mock()
            success_result.returncode = 0
            success_result.stdout = ""
            success_result.stderr = ""
            mock_run.return_value = success_result

            with patch("autopack.executor.run_checkpoint.log_run_rollback_action") as mock_log:
                mock_log.return_value = False  # Logging fails

                result = perform_full_rollback(
                    workspace=tmp_path,
                    checkpoint=checkpoint,
                    reason="Test reason",
                    run_id="run-123",
                )

                # Rollback still succeeds
                assert result.success is True
