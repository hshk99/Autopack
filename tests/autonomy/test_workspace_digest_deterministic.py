"""Tests for deterministic workspace digest (BUILD-180 Phase 0/2).

Validates that workspace digest is deterministic even when git is unavailable.
Must use sentinel value, never timestamps.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

from autopack.gaps.scanner import _compute_workspace_digest, scan_workspace


class TestWorkspaceDigestDeterminism:
    """Test workspace digest determinism."""

    def test_same_git_state_same_digest(self):
        """Same git state should produce same digest."""
        with patch("subprocess.run") as mock_run:
            # Simulate consistent git state
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="abc123\n", stderr=""),  # git rev-parse HEAD
                MagicMock(returncode=0, stdout="M file.py\n", stderr=""),  # git status
            ]

            digest1 = _compute_workspace_digest(Path("."))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="abc123\n", stderr=""),
                MagicMock(returncode=0, stdout="M file.py\n", stderr=""),
            ]

            digest2 = _compute_workspace_digest(Path("."))

        assert digest1 == digest2

    def test_different_git_state_different_digest(self):
        """Different git state should produce different digest."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="abc123\n", stderr=""),
                MagicMock(returncode=0, stdout="M file.py\n", stderr=""),
            ]

            digest1 = _compute_workspace_digest(Path("."))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="def456\n", stderr=""),  # Different HEAD
                MagicMock(returncode=0, stdout="M file.py\n", stderr=""),
            ]

            digest2 = _compute_workspace_digest(Path("."))

        assert digest1 != digest2


class TestWorkspaceDigestGitUnavailable:
    """Test workspace digest when git is unavailable."""

    def test_git_failure_returns_deterministic_sentinel(self):
        """Git failure should return deterministic sentinel, not timestamp."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("git not found")

            digest1 = _compute_workspace_digest(Path("."))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("git not found")

            digest2 = _compute_workspace_digest(Path("."))

        # Both calls should return the same sentinel-based digest
        assert digest1 == digest2
        assert len(digest1) == 16  # Expected digest length

    def test_git_failure_uses_sentinel_not_timestamp(self):
        """Git failure should use sentinel value, not timestamp."""
        import time

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("git not found")

            digest1 = _compute_workspace_digest(Path("."))
            time.sleep(0.1)  # Small delay
            digest2 = _compute_workspace_digest(Path("."))

        # If timestamps were used, these would differ
        assert digest1 == digest2

    def test_git_timeout_returns_deterministic_sentinel(self):
        """Git timeout should return deterministic sentinel."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 5)

            digest1 = _compute_workspace_digest(Path("."))
            digest2 = _compute_workspace_digest(Path("."))

        assert digest1 == digest2

    def test_sentinel_digest_is_valid_hex(self):
        """Sentinel digest should be valid hex string."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.SubprocessError("git not found")

            digest = _compute_workspace_digest(Path("."))

        # Should be valid hex
        int(digest, 16)  # Raises if not valid hex
        assert len(digest) == 16


class TestWorkspaceDigestEdgeCases:
    """Test edge cases for workspace digest."""

    def test_empty_git_status_handled(self):
        """Empty git status (clean repo) should be handled."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="abc123\n", stderr=""),
                MagicMock(returncode=0, stdout="", stderr=""),  # Clean repo
            ]

            digest = _compute_workspace_digest(Path("."))

        assert digest is not None
        assert len(digest) == 16

    def test_git_head_failure_status_success(self):
        """If git HEAD fails but status succeeds, use sentinel."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="not a git repo"),  # HEAD fails
                MagicMock(returncode=0, stdout="", stderr=""),  # status succeeds
            ]

            digest1 = _compute_workspace_digest(Path("."))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="not a git repo"),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]

            digest2 = _compute_workspace_digest(Path("."))

        # Should be deterministic even on partial failure
        assert digest1 == digest2

    def test_scanner_uses_deterministic_digest(self):
        """GapScanner should use the deterministic digest function."""
        with patch("autopack.gaps.scanner._compute_workspace_digest") as mock_digest:
            mock_digest.return_value = "abc123def456"

            report = scan_workspace(Path("."), "test-project", "test-run")

            mock_digest.assert_called_once()
            assert report.workspace_state_digest == "abc123def456"
