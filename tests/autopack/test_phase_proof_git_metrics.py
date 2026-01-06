"""Tests for phase proof git-based metrics (BUILD-180 Phase 0/3).

Validates that phase proofs include real metrics when git is available,
with explicit metrics_placeholder flag.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from autopack.proof_metrics import (
    count_changed_files,
    list_changed_files,
    get_proof_metrics,
    ProofMetrics,
)
from autopack.phase_proof_writer import write_minimal_phase_proof


class TestCountChangedFiles:
    """Test counting changed files via git."""

    def test_counts_modified_files(self):
        """Should count modified files from git diff."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="file1.py\nfile2.py\nfile3.py\n",
                stderr=""
            )

            count = count_changed_files(Path("."))

            assert count == 3

    def test_empty_diff_returns_zero(self):
        """Empty git diff should return zero."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )

            count = count_changed_files(Path("."))

            assert count == 0

    def test_git_failure_returns_none(self):
        """Git failure should return None (not zero)."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("git not found")

            count = count_changed_files(Path("."))

            assert count is None


class TestListChangedFiles:
    """Test listing changed files."""

    def test_lists_files_up_to_limit(self):
        """Should list files up to specified limit."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="file1.py\nfile2.py\nfile3.py\nfile4.py\nfile5.py\n",
                stderr=""
            )

            files = list_changed_files(Path("."), limit=3)

            assert len(files) == 3
            assert files == ["file1.py", "file2.py", "file3.py"]

    def test_returns_all_if_under_limit(self):
        """Should return all files if under limit."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="file1.py\nfile2.py\n",
                stderr=""
            )

            files = list_changed_files(Path("."), limit=10)

            assert len(files) == 2

    def test_git_failure_returns_empty_list(self):
        """Git failure should return empty list."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("git not found")

            files = list_changed_files(Path("."))

            assert files == []


class TestGetProofMetrics:
    """Test getting full proof metrics."""

    def test_returns_real_metrics_when_git_available(self):
        """Should return real metrics with placeholder=False when git works."""
        with patch("autopack.proof_metrics.count_changed_files") as mock_count, \
             patch("autopack.proof_metrics.list_changed_files") as mock_list:

            mock_count.return_value = 5
            mock_list.return_value = ["a.py", "b.py"]

            metrics = get_proof_metrics(Path("."))

            assert metrics.files_modified == 5
            assert metrics.changed_file_sample == ["a.py", "b.py"]
            assert metrics.metrics_placeholder is False

    def test_returns_placeholder_when_git_unavailable(self):
        """Should return placeholder metrics when git unavailable."""
        with patch("autopack.proof_metrics.count_changed_files") as mock_count:
            mock_count.return_value = None

            metrics = get_proof_metrics(Path("."))

            assert metrics.files_modified == 0
            assert metrics.metrics_placeholder is True


class TestPhaseProofWriterIntegration:
    """Test phase proof writer integration with metrics."""

    def test_proof_includes_real_file_count(self):
        """Phase proof should include real file count when available."""
        with patch("autopack.phase_proof_writer.get_proof_metrics") as mock_metrics, \
             patch("autopack.phase_proof_writer.PhaseProofStorage") as mock_storage:

            mock_metrics.return_value = ProofMetrics(
                files_modified=3,
                changed_file_sample=["x.py"],
                metrics_placeholder=False
            )

            write_minimal_phase_proof(
                run_id="test-run",
                project_id="test-project",
                phase_id="phase-1",
                success=True,
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

            # Verify the proof was saved with real metrics
            save_call = mock_storage.save_proof.call_args
            proof = save_call[0][0]
            assert proof.changes.files_modified == 3
            assert proof.metrics_placeholder is False

    def test_proof_indicates_placeholder_when_git_unavailable(self):
        """Phase proof should indicate placeholder when git unavailable."""
        with patch("autopack.phase_proof_writer.get_proof_metrics") as mock_metrics, \
             patch("autopack.phase_proof_writer.PhaseProofStorage") as mock_storage:

            mock_metrics.return_value = ProofMetrics(
                files_modified=0,
                changed_file_sample=[],
                metrics_placeholder=True
            )

            write_minimal_phase_proof(
                run_id="test-run",
                project_id="test-project",
                phase_id="phase-1",
                success=True,
                created_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )

            save_call = mock_storage.save_proof.call_args
            proof = save_call[0][0]
            assert proof.metrics_placeholder is True


class TestProofMetricsDataclass:
    """Test ProofMetrics dataclass."""

    def test_dataclass_fields(self):
        """ProofMetrics should have expected fields."""
        metrics = ProofMetrics(
            files_modified=5,
            changed_file_sample=["a.py", "b.py"],
            metrics_placeholder=False,
            tests_passed=10,
            tests_failed=2,
        )

        assert metrics.files_modified == 5
        assert metrics.changed_file_sample == ["a.py", "b.py"]
        assert metrics.metrics_placeholder is False
        assert metrics.tests_passed == 10
        assert metrics.tests_failed == 2

    def test_default_values(self):
        """ProofMetrics should have sensible defaults."""
        metrics = ProofMetrics(
            files_modified=0,
            changed_file_sample=[],
            metrics_placeholder=True,
        )

        assert metrics.tests_passed == 0
        assert metrics.tests_failed == 0
