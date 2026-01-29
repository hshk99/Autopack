"""
Unit tests for run_checkpoint module.

Tests git command invocation with mocked subprocess.run.
No real git operations are performed.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from autopack.executor.run_checkpoint import (
    create_checkpoint,
    create_deletion_savepoint,
    create_execute_fix_checkpoint,
    create_run_checkpoint,
    list_checkpoints,
    rollback_to_checkpoint,
    rollback_to_run_checkpoint,
    write_audit_log,
)


class TestCreateCheckpoint:
    """Tests for create_checkpoint (tag-based checkpoints)."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_creates_git_tag_with_correct_format(self, mock_datetime, mock_run):
        """Test that checkpoint creates git tag with deterministic format."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # Act
        result = create_checkpoint(run_id="test-run", phase_id="phase-1", message="test checkpoint")

        # Assert
        expected_tag = "autopack-test-run-phase-1-20260112-143000"
        assert result == expected_tag
        mock_run.assert_called_once_with(
            ["git", "tag", expected_tag],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_checkpoint_creation_failure_returns_empty_string(self, mock_datetime, mock_run):
        """Test that failed checkpoint returns empty string."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="tag already exists")

        # Act
        result = create_checkpoint(run_id="test-run", phase_id="phase-1", message="test")

        # Assert
        assert result == ""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_checkpoint_timeout_returns_empty_string(self, mock_datetime, mock_run):
        """Test that timeout returns empty string."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git tag", timeout=10)

        # Act
        result = create_checkpoint(run_id="test-run", phase_id="phase-1", message="test")

        # Assert
        assert result == ""


class TestRollbackToCheckpoint:
    """Tests for rollback_to_checkpoint."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_invokes_git_reset_hard(self, mock_run):
        """Test that rollback invokes git reset --hard <checkpoint_id>."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        workspace = Path("/fake/workspace")

        # Act
        result = rollback_to_checkpoint(
            checkpoint_id="abc123def",
            workspace=workspace,
        )

        # Assert
        assert result is True
        mock_run.assert_called_once_with(
            ["git", "reset", "--hard", "abc123def"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=30,
        )

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_no_checkpoint_id_fails_fast(self, mock_run):
        """Test that empty checkpoint_id fails without invoking git."""
        # Arrange
        workspace = Path("/fake/workspace")

        # Act
        result = rollback_to_checkpoint(checkpoint_id="", workspace=workspace)

        # Assert
        assert result is False
        mock_run.assert_not_called()

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_rollback_failure_returns_false(self, mock_run):
        """Test that failed git reset returns False."""
        # Arrange
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: ambiguous argument")
        workspace = Path("/fake/workspace")

        # Act
        result = rollback_to_checkpoint(checkpoint_id="invalid", workspace=workspace)

        # Assert
        assert result is False

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_rollback_timeout_returns_false(self, mock_run):
        """Test that timeout during rollback returns False."""
        # Arrange
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git reset", timeout=30)
        workspace = Path("/fake/workspace")

        # Act
        result = rollback_to_checkpoint(checkpoint_id="abc123", workspace=workspace)

        # Assert
        assert result is False


class TestWriteAuditLog:
    """Tests for write_audit_log."""

    @patch("autopack.file_layout.RunFileLayout")
    @patch("builtins.open", create=True)
    def test_writes_to_expected_location(self, mock_open, mock_layout_cls):
        """Test that audit log writes to correct file."""
        # Arrange
        mock_layout = Mock()
        mock_layout.base_dir = Path("/fake/runs/test-run")
        mock_layout_cls.return_value = mock_layout

        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        # Act
        result = write_audit_log(
            run_id="test-run",
            phase_id="phase-1",
            action="checkpoint_created",
            details={"checkpoint_id": "tag-abc", "project_id": "proj-1"},
        )

        # Assert
        assert result is True
        expected_path = Path("/fake/runs/test-run/checkpoint_audit.log")
        mock_open.assert_called_once_with(expected_path, "a", encoding="utf-8")
        # Verify log entry contains key information
        written_content = mock_file.write.call_args[0][0]
        assert "test-run" in written_content
        assert "phase-1" in written_content
        assert "checkpoint_created" in written_content
        assert "tag-abc" in written_content

    @patch("autopack.file_layout.RunFileLayout")
    def test_audit_log_failure_returns_false(self, mock_layout_cls):
        """Test that audit log write failure returns False."""
        # Arrange
        mock_layout_cls.side_effect = Exception("Failed to create layout")

        # Act
        result = write_audit_log(
            run_id="test-run",
            phase_id="phase-1",
            action="checkpoint_created",
            details={},
        )

        # Assert
        assert result is False


class TestListCheckpoints:
    """Tests for list_checkpoints."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_filters_tags_by_run_id_prefix(self, mock_run):
        """Test that list_checkpoints filters tags by run_id prefix."""
        # Arrange
        mock_run.return_value = Mock(
            returncode=0,
            stdout="autopack-run1-phase1-20260112\nautopack-run1-phase2-20260112\n",
            stderr="",
        )
        workspace = Path("/fake/workspace")

        # Act
        result = list_checkpoints(run_id="run1", workspace=workspace)

        # Assert
        assert len(result) == 2
        assert "autopack-run1-phase1-20260112" in result
        assert "autopack-run1-phase2-20260112" in result
        mock_run.assert_called_once_with(
            ["git", "tag", "-l", "autopack-run1-*"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_empty_result_returns_empty_list(self, mock_run):
        """Test that no matching tags returns empty list."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        workspace = Path("/fake/workspace")

        # Act
        result = list_checkpoints(run_id="nonexistent", workspace=workspace)

        # Assert
        assert result == []

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_list_failure_returns_empty_list(self, mock_run):
        """Test that git tag -l failure returns empty list."""
        # Arrange
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: not a git repo")
        workspace = Path("/fake/workspace")

        # Act
        result = list_checkpoints(run_id="run1", workspace=workspace)

        # Assert
        assert result == []


class TestCreateRunCheckpoint:
    """Tests for create_run_checkpoint."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_captures_branch_and_commit(self, mock_run):
        """Test that run checkpoint captures current branch and commit."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="main\n", stderr=""),  # git rev-parse --abbrev-ref HEAD
            Mock(returncode=0, stdout="abc123def456\n", stderr=""),  # git rev-parse HEAD
        ]

        # Act
        success, branch, commit, error = create_run_checkpoint(workspace)

        # Assert
        assert success is True
        assert branch == "main"
        assert commit == "abc123def456"
        assert error is None
        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        mock_run.assert_any_call(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_branch_failure_returns_error(self, mock_run):
        """Test that failure to get branch returns error."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: not a git repo")

        # Act
        success, branch, commit, error = create_run_checkpoint(workspace)

        # Assert
        assert success is False
        assert branch is None
        assert commit is None
        assert error is not None
        assert "git_branch_failed" in error

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_commit_failure_returns_error(self, mock_run):
        """Test that failure to get commit returns error."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="main\n", stderr=""),  # Branch succeeds
            Mock(returncode=1, stdout="", stderr="fatal: bad revision"),  # Commit fails
        ]

        # Act
        success, branch, commit, error = create_run_checkpoint(workspace)

        # Assert
        assert success is False
        assert branch is None
        assert commit is None
        assert error is not None
        assert "git_commit_failed" in error


class TestRollbackToRunCheckpoint:
    """Tests for rollback_to_run_checkpoint."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_executes_reset_clean_and_checkout(self, mock_run):
        """Test that rollback executes git reset, clean, and checkout."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git reset --hard
            Mock(returncode=0, stdout="", stderr=""),  # git clean -fd
            Mock(returncode=0, stdout="", stderr=""),  # git checkout main
        ]

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="main",
            checkpoint_commit="abc123def",
            reason="test rollback",
        )

        # Assert
        assert success is True
        assert error is None
        assert mock_run.call_count == 3
        mock_run.assert_any_call(
            ["git", "reset", "--hard", "abc123def"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        mock_run.assert_any_call(
            ["git", "clean", "-fd"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        mock_run.assert_any_call(
            ["git", "checkout", "main"],
            cwd=workspace.resolve(),
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_no_checkpoint_commit_fails_fast(self, mock_run):
        """Test that missing checkpoint_commit fails without destructive commands."""
        # Arrange
        workspace = Path("/fake/workspace")

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="main",
            checkpoint_commit="",  # Empty checkpoint
            reason="test",
        )

        # Assert
        assert success is False
        assert error == "no_checkpoint_commit"
        mock_run.assert_not_called()  # No git commands should be invoked

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_reset_failure_returns_error(self, mock_run):
        """Test that git reset failure returns error."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: bad revision")

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="main",
            checkpoint_commit="invalid",
            reason="test",
        )

        # Assert
        assert success is False
        assert "git_reset_failed" in error

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_clean_failure_is_non_fatal(self, mock_run):
        """Test that git clean failure is non-fatal if reset succeeded."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # Reset succeeds
            Mock(returncode=1, stdout="", stderr="failed to clean"),  # Clean fails
            Mock(returncode=0, stdout="", stderr=""),  # Checkout succeeds
        ]

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="main",
            checkpoint_commit="abc123",
            reason="test",
        )

        # Assert
        assert success is True  # Overall success despite clean failure
        assert error is None

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_checkout_failure_is_non_fatal(self, mock_run):
        """Test that git checkout failure is non-fatal if reset succeeded."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # Reset succeeds
            Mock(returncode=0, stdout="", stderr=""),  # Clean succeeds
            Mock(returncode=1, stdout="", stderr="branch not found"),  # Checkout fails
        ]

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="nonexistent",
            checkpoint_commit="abc123",
            reason="test",
        )

        # Assert
        assert success is True  # Overall success despite checkout failure
        assert error is None

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_skips_checkout_for_detached_head(self, mock_run):
        """Test that checkout is skipped for detached HEAD state."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # Reset succeeds
            Mock(returncode=0, stdout="", stderr=""),  # Clean succeeds
        ]

        # Act
        success, error = rollback_to_run_checkpoint(
            workspace=workspace,
            checkpoint_branch="HEAD",  # Detached HEAD
            checkpoint_commit="abc123",
            reason="test",
        )

        # Assert
        assert success is True
        assert error is None
        assert mock_run.call_count == 2  # No checkout call


class TestCreateDeletionSavepoint:
    """Tests for create_deletion_savepoint."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_creates_commit_and_tag_for_uncommitted_changes(self, mock_datetime, mock_run):
        """Test that savepoint creates commit and tag when there are uncommitted changes."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=1, stdout="", stderr=""),  # git diff --quiet (changes exist)
            Mock(returncode=0, stdout="", stderr=""),  # git add -A
            Mock(returncode=0, stdout="", stderr=""),  # git commit
            Mock(returncode=0, stdout="", stderr=""),  # git tag
        ]

        # Act
        result = create_deletion_savepoint(
            workspace=workspace,
            phase_id="phase-1",
            run_id="run-123",
            net_deletion=500,
        )

        # Assert
        expected_tag = "save-before-deletion-phase-1-20260112-143000"
        assert result == expected_tag
        assert mock_run.call_count == 4
        # Verify commit message contains key info
        commit_call = mock_run.call_args_list[2]
        commit_args = commit_call[0][0]
        assert "git" in commit_args
        assert "commit" in commit_args
        assert any("phase-1" in arg and "500" in arg for arg in commit_args)

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_creates_tag_without_commit_for_clean_state(self, mock_datetime, mock_run):
        """Test that savepoint only creates tag when there are no uncommitted changes."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git diff --quiet (no changes)
            Mock(returncode=0, stdout="", stderr=""),  # git tag
        ]

        # Act
        result = create_deletion_savepoint(
            workspace=workspace,
            phase_id="phase-2",
            run_id="run-456",
            net_deletion=100,
        )

        # Assert
        expected_tag = "save-before-deletion-phase-2-20260112-143000"
        assert result == expected_tag
        assert mock_run.call_count == 2  # Only diff and tag, no add/commit

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    @patch("autopack.executor.run_checkpoint.datetime")
    def test_savepoint_failure_returns_none(self, mock_datetime, mock_run):
        """Test that savepoint failure returns None."""
        # Arrange
        mock_datetime.now.return_value.strftime.return_value = "20260112-143000"
        workspace = Path("/fake/workspace")
        mock_run.side_effect = Exception("git command failed")

        # Act
        result = create_deletion_savepoint(
            workspace=workspace,
            phase_id="phase-1",
            run_id="run-123",
            net_deletion=500,
        )

        # Assert
        assert result is None


class TestCreateExecuteFixCheckpoint:
    """Tests for create_execute_fix_checkpoint."""

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_creates_commit_with_correct_message(self, mock_run):
        """Test that execute_fix checkpoint creates commit with correct message."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git add -A
            Mock(returncode=0, stdout="", stderr=""),  # git commit
        ]

        # Act
        result = create_execute_fix_checkpoint(workspace=workspace, phase_id="phase-1")

        # Assert
        assert result is True
        assert mock_run.call_count == 2
        # Verify commit message
        commit_call = mock_run.call_args_list[1]
        commit_args = commit_call[0][0]
        assert "git" in commit_args
        assert "commit" in commit_args
        assert any("Pre-execute_fix" in arg and "phase-1" in arg for arg in commit_args)

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_handles_nothing_to_commit(self, mock_run):
        """Test that 'nothing to commit' is handled gracefully."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git add -A
            Mock(returncode=1, stdout="nothing to commit, working tree clean", stderr=""),
        ]

        # Act
        result = create_execute_fix_checkpoint(workspace=workspace, phase_id="phase-1")

        # Assert
        assert result is True  # Success even though nothing to commit

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_add_failure_returns_false(self, mock_run):
        """Test that git add failure returns False."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="fatal: not a git repo")

        # Act
        result = create_execute_fix_checkpoint(workspace=workspace, phase_id="phase-1")

        # Assert
        assert result is False

    @patch("autopack.executor.run_checkpoint.subprocess.run")
    def test_commit_failure_returns_false(self, mock_run):
        """Test that git commit failure returns False."""
        # Arrange
        workspace = Path("/fake/workspace")
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # git add succeeds
            Mock(returncode=1, stdout="", stderr="fatal: unable to commit"),  # commit fails
        ]

        # Act
        result = create_execute_fix_checkpoint(workspace=workspace, phase_id="phase-1")

        # Assert
        assert result is False
