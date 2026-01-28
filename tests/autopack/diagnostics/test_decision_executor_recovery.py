"""Tests for Decision Executor Patch Conflict Recovery.

Tests the enhanced patch conflict recovery functionality that includes:
- 3-way merge fallback when direct patch application fails
- Conflict line extraction for retry context
- Retry context with merge attempt information
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.diagnostics.decision_executor import DecisionExecutor
from autopack.diagnostics.diagnostics_models import (
    Decision,
    DecisionType,
    ExecutionResult,
    PhaseSpec,
)


class TestExtractConflictLines:
    """Tests for _extract_conflict_lines helper method."""

    def test_extract_line_numbers_from_error_message(self, tmp_path):
        """Test extracting line numbers from git apply error messages."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        error_message = (
            "error: patch failed: src/file.py:42\nerror: src/file.py: patch does not apply"
        )
        patch_content = ""

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert 42 in conflict_lines

    def test_extract_line_numbers_from_multiple_errors(self, tmp_path):
        """Test extracting multiple line numbers from error messages."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        error_message = (
            "error: patch failed: src/file.py:10\n"
            "error: patch failed: src/file.py:25\n"
            "error: patch failed: src/other.py:100"
        )
        patch_content = ""

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert 10 in conflict_lines
        assert 25 in conflict_lines
        assert 100 in conflict_lines

    def test_extract_line_numbers_from_patch_hunks(self, tmp_path):
        """Test extracting line numbers from patch hunk headers."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        patch_content = """--- a/src/file.py
+++ b/src/file.py
@@ -10,5 +10,6 @@ def existing_function():
     pass
+    # new line
@@ -50,3 +51,4 @@ def another_function():
     return True
+    # another new line
"""
        error_message = ""

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert 10 in conflict_lines
        assert 51 in conflict_lines

    def test_extract_no_duplicates(self, tmp_path):
        """Test that duplicate line numbers are not included."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        error_message = "error: patch failed: src/file.py:42\nerror: also at src/file.py:42"
        patch_content = "@@ -42,1 +42,2 @@ def func():"

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert conflict_lines.count(42) == 1

    def test_extract_returns_sorted_lines(self, tmp_path):
        """Test that conflict lines are returned sorted."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        error_message = (
            "error: patch failed: src/file.py:100\n"
            "error: patch failed: src/file.py:25\n"
            "error: patch failed: src/file.py:50"
        )
        patch_content = ""

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert conflict_lines == sorted(conflict_lines)
        assert conflict_lines == [25, 50, 100]

    def test_extract_empty_on_no_conflicts(self, tmp_path):
        """Test that empty list is returned when no conflicts found."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        error_message = "Some general error without line numbers"
        patch_content = "Some patch content without hunks"

        conflict_lines = executor._extract_conflict_lines(patch_content, error_message)

        assert conflict_lines == []


class TestAttemptThreeWayMerge:
    """Tests for _attempt_three_way_merge helper method."""

    def test_three_way_merge_success(self, tmp_path):
        """Test successful 3-way merge by mocking subprocess."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        # Create the necessary directory structure
        (tmp_path / ".autonomous_runs" / "test-run").mkdir(parents=True, exist_ok=True)

        patch_content = "some patch content"

        # Mock subprocess.run to simulate successful 3-way merge
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = executor._attempt_three_way_merge(patch_content)

        assert result["success"] is True
        assert result["merge_used"] is True

    def test_three_way_merge_failure(self, tmp_path):
        """Test 3-way merge failure with invalid patch."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        # Create an invalid patch
        patch_content = "not a valid patch"

        result = executor._attempt_three_way_merge(patch_content)

        assert result["success"] is False
        assert result["merge_used"] is True
        assert "error" in result

    def test_three_way_merge_cleans_up_temp_file(self, tmp_path):
        """Test that temp patch file is cleaned up after merge attempt."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        patch_content = "some patch content"
        executor._attempt_three_way_merge(patch_content)

        # Check that temp file was cleaned up
        temp_patch = tmp_path / ".autonomous_runs" / "test-run" / "temp_3way.patch"
        assert not temp_patch.exists()


class TestExecutionResultFields:
    """Tests for new ExecutionResult fields."""

    def test_execution_result_has_conflict_lines(self):
        """Test that ExecutionResult has conflict_lines field."""
        result = ExecutionResult(
            success=False,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=False,
            deliverables_validated=False,
            tests_passed=False,
            rollback_performed=False,
            error_message="Test error",
            conflict_lines=[10, 20, 30],
        )

        assert result.conflict_lines == [10, 20, 30]

    def test_execution_result_has_retry_context(self):
        """Test that ExecutionResult has retry_context field."""
        result = ExecutionResult(
            success=False,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=False,
            deliverables_validated=False,
            tests_passed=False,
            rollback_performed=False,
            error_message="Test error",
            retry_context={
                "original_error": "patch failed",
                "merge_attempted": True,
            },
        )

        assert result.retry_context["original_error"] == "patch failed"
        assert result.retry_context["merge_attempted"] is True

    def test_execution_result_defaults_to_none(self):
        """Test that new fields default to None."""
        result = ExecutionResult(
            success=True,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=True,
            deliverables_validated=True,
            tests_passed=True,
            rollback_performed=False,
        )

        assert result.conflict_lines is None
        assert result.retry_context is None


class TestPatchRecoveryIntegration:
    """Integration tests for patch conflict recovery flow."""

    def test_recovery_flow_on_patch_failure(self, tmp_path):
        """Test that recovery flow is triggered on patch failure."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and commit a file
        test_file = tmp_path / "test.py"
        test_file.write_text("original content\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create decision with invalid patch
        decision = Decision(
            type=DecisionType.CLEAR_FIX,
            fix_strategy="Test fix",
            rationale="Test rationale",
            alternatives_considered=["Alt 1"],
            risk_level="LOW",
            deliverables_met=["test.py"],
            files_modified=["test.py"],
            net_deletion=0,
            patch="invalid patch that will fail",
            confidence=0.9,
        )

        phase_spec = PhaseSpec(
            phase_id="test-phase",
            deliverables=["test.py"],
            acceptance_criteria=[],
            allowed_paths=["test.py"],
            protected_paths=[],
        )

        result = executor.execute_decision(decision, phase_spec)

        # Should have failed with conflict info
        assert result.success is False
        assert result.retry_context is not None
        assert result.retry_context["merge_attempted"] is True

    def test_successful_recovery_with_valid_patch(self, tmp_path):
        """Test successful patch application after initial setup."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create and commit a file
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create decision with valid patch
        patch_content = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line1
+new_line
 line2
 line3
"""
        decision = Decision(
            type=DecisionType.CLEAR_FIX,
            fix_strategy="Add new line",
            rationale="Test rationale",
            alternatives_considered=["Alt 1"],
            risk_level="LOW",
            deliverables_met=["test.py"],
            files_modified=["test.py"],
            net_deletion=-1,
            patch=patch_content,
            confidence=0.9,
        )

        phase_spec = PhaseSpec(
            phase_id="test-phase",
            deliverables=["test.py"],
            acceptance_criteria=[],
            allowed_paths=["test.py"],
            protected_paths=[],
        )

        # Mock deliverables validation to always pass
        with patch.object(executor, "_validate_deliverables", return_value=True):
            result = executor.execute_decision(decision, phase_spec)

        # Should succeed
        assert result.patch_applied is True
