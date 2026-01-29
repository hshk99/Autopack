"""Tests for Decision Executor Post-Fix Validation.

Tests the post-execution validation functionality that includes:
- Re-running diagnostic probes after fix application
- Checking if original error is resolved
- Rolling back on validation failure
- Setting needs_retry flag when validation fails
"""

import subprocess
from unittest.mock import MagicMock, patch

from autopack.diagnostics.command_runner import CommandResult
from autopack.diagnostics.decision_executor import DecisionExecutor
from autopack.diagnostics.diagnostics_models import (
    Decision,
    DecisionType,
    ExecutionResult,
    PhaseSpec,
    ValidationResult,
)
from autopack.diagnostics.probes import Probe, ProbeCommand, ProbeRunResult


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_resolved(self):
        """Test ValidationResult when fix is resolved."""
        result = ValidationResult(
            resolved=True,
            reason="Original error no longer detected",
        )

        assert result.resolved is True
        assert result.original_error_still_present is False

    def test_validation_result_not_resolved(self):
        """Test ValidationResult when fix is not resolved."""
        result = ValidationResult(
            resolved=False,
            reason="Original error still detected after fix",
            original_error_still_present=True,
        )

        assert result.resolved is False
        assert result.original_error_still_present is True

    def test_validation_result_with_probe_results(self):
        """Test ValidationResult with probe results."""
        probe = Probe(
            name="test_probe",
            description="Test probe",
            commands=[ProbeCommand("echo test", label="test")],
        )
        probe_result = ProbeRunResult(
            probe=probe,
            command_results=[],
            resolved=True,
        )
        result = ValidationResult(
            resolved=True,
            reason="Test",
            probe_results=[probe_result],
        )

        assert len(result.probe_results) == 1


class TestInferFailureClass:
    """Tests for _infer_failure_class helper method."""

    def test_infer_patch_error(self, tmp_path):
        """Test inferring patch_apply_error failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert (
            executor._infer_failure_class("patch failed to apply", decision) == "patch_apply_error"
        )
        assert executor._infer_failure_class("hunk #1 failed", decision) == "patch_apply_error"
        assert (
            executor._infer_failure_class("merge conflict detected", decision)
            == "patch_apply_error"
        )

    def test_infer_test_failure(self, tmp_path):
        """Test inferring ci_fail failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert executor._infer_failure_class("test_function failed", decision) == "ci_fail"
        assert executor._infer_failure_class("AssertionError: expected True", decision) == "ci_fail"
        assert executor._infer_failure_class("pytest exited with code 1", decision) == "ci_fail"

    def test_infer_dependency_error(self, tmp_path):
        """Test inferring deps_missing failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert (
            executor._infer_failure_class("ImportError: No module named", decision)
            == "deps_missing"
        )
        assert executor._infer_failure_class("ModuleNotFoundError", decision) == "deps_missing"
        assert (
            executor._infer_failure_class("Missing dependency: requests", decision)
            == "deps_missing"
        )

    def test_infer_file_not_found(self, tmp_path):
        """Test inferring missing_path failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert executor._infer_failure_class("FileNotFoundError", decision) == "missing_path"
        assert (
            executor._infer_failure_class("No such file or directory", decision) == "missing_path"
        )

    def test_infer_timeout(self, tmp_path):
        """Test inferring timeout failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert executor._infer_failure_class("Operation timed out", decision) == "timeout"
        assert executor._infer_failure_class("Request timeout after 30s", decision) == "timeout"

    def test_infer_permission_error(self, tmp_path):
        """Test inferring permission_denied failure class."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert executor._infer_failure_class("Permission denied", decision) == "permission_denied"
        assert (
            executor._infer_failure_class("Access denied to file", decision) == "permission_denied"
        )

    def test_infer_baseline_for_unknown(self, tmp_path):
        """Test that unknown errors default to baseline."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)

        assert executor._infer_failure_class("Some unknown error", decision) == "baseline"


class TestValidateFix:
    """Tests for _validate_fix method."""

    def test_validate_fix_no_original_error(self, tmp_path):
        """Test validation is skipped when no original error specified."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)
        phase_spec = MagicMock(spec=PhaseSpec)

        result = executor._validate_fix(None, decision, phase_spec)

        assert result.resolved is True
        assert "No original error" in result.reason

    def test_validate_fix_empty_original_error(self, tmp_path):
        """Test validation is skipped when original error is empty."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)
        phase_spec = MagicMock(spec=PhaseSpec)

        result = executor._validate_fix("", decision, phase_spec)

        assert result.resolved is True

    def test_validate_fix_error_resolved(self, tmp_path):
        """Test validation passes when error is resolved."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)
        decision.files_modified = ["test.py"]
        phase_spec = MagicMock(spec=PhaseSpec)
        phase_spec.phase_id = "test-phase"

        # Mock the command runner to return output without the original error
        mock_result = CommandResult(
            command="git status --short",
            redacted_command="git status --short",
            exit_code=0,
            stdout="M test.py",
            stderr="",
            duration_sec=0.1,
            timed_out=False,
            skipped=False,
            label="git_status",
        )

        with patch("autopack.diagnostics.decision_executor.GovernedCommandRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            result = executor._validate_fix(
                "ImportError: No module named foo",
                decision,
                phase_spec,
            )

        assert result.resolved is True
        assert not result.original_error_still_present

    def test_validate_fix_error_still_present(self, tmp_path):
        """Test validation fails when error is still present."""
        executor = DecisionExecutor(
            run_id="test-run",
            workspace=tmp_path,
        )
        decision = MagicMock(spec=Decision)
        decision.files_modified = ["test.py"]
        phase_spec = MagicMock(spec=PhaseSpec)
        phase_spec.phase_id = "test-phase"

        # Mock the command runner to return output containing the original error
        mock_result = CommandResult(
            command="git status --short",
            redacted_command="git status --short",
            exit_code=1,
            stdout="",
            stderr="ImportError: No module named foo",
            duration_sec=0.1,
            timed_out=False,
            skipped=False,
            label="git_status",
        )

        with patch("autopack.diagnostics.decision_executor.GovernedCommandRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.run.return_value = mock_result
            MockRunner.return_value = mock_runner_instance

            result = executor._validate_fix(
                "ImportError: No module named foo",
                decision,
                phase_spec,
            )

        assert result.resolved is False
        assert result.original_error_still_present is True
        assert "still detected" in result.reason


class TestExecutionResultValidationFields:
    """Tests for new validation fields in ExecutionResult."""

    def test_execution_result_has_fix_validated(self):
        """Test that ExecutionResult has fix_validated field."""
        result = ExecutionResult(
            success=True,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=True,
            deliverables_validated=True,
            tests_passed=True,
            rollback_performed=False,
            fix_validated=True,
        )

        assert result.fix_validated is True

    def test_execution_result_has_needs_retry(self):
        """Test that ExecutionResult has needs_retry field."""
        result = ExecutionResult(
            success=False,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=True,
            deliverables_validated=True,
            tests_passed=True,
            rollback_performed=True,
            error_message="Validation failed",
            needs_retry=True,
        )

        assert result.needs_retry is True

    def test_execution_result_has_validation_result(self):
        """Test that ExecutionResult has validation_result field."""
        validation_result = ValidationResult(
            resolved=False,
            reason="Original error still detected",
            original_error_still_present=True,
        )
        result = ExecutionResult(
            success=False,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=True,
            deliverables_validated=True,
            tests_passed=True,
            rollback_performed=True,
            validation_result=validation_result,
        )

        assert result.validation_result is not None
        assert result.validation_result.resolved is False

    def test_execution_result_validation_defaults(self):
        """Test that validation fields have correct defaults."""
        result = ExecutionResult(
            success=True,
            decision_id="test-id",
            save_point="test-save-point",
            patch_applied=True,
            deliverables_validated=True,
            tests_passed=True,
            rollback_performed=False,
        )

        assert result.fix_validated is True
        assert result.needs_retry is False
        assert result.validation_result is None


class TestExecuteDecisionWithValidation:
    """Integration tests for execute_decision with validation."""

    def test_execute_decision_passes_validation(self, tmp_path):
        """Test successful execution with passing validation."""
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

        # Mock deliverables validation and post-fix validation
        with patch.object(executor, "_validate_deliverables", return_value=True):
            with patch.object(
                executor,
                "_validate_fix",
                return_value=ValidationResult(resolved=True, reason="Error resolved"),
            ):
                result = executor.execute_decision(
                    decision, phase_spec, original_error="some error"
                )

        assert result.patch_applied is True
        assert result.fix_validated is True
        assert result.needs_retry is False

    def test_execute_decision_fails_validation(self, tmp_path):
        """Test execution rolls back when validation fails."""
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

        # Mock deliverables validation to pass, but post-fix validation to fail
        failed_validation = ValidationResult(
            resolved=False,
            reason="Original error still detected",
            original_error_still_present=True,
        )

        with patch.object(executor, "_validate_deliverables", return_value=True):
            with patch.object(executor, "_validate_fix", return_value=failed_validation):
                result = executor.execute_decision(
                    decision, phase_spec, original_error="some persistent error"
                )

        assert result.success is False
        assert result.patch_applied is True
        assert result.tests_passed is True
        assert result.fix_validated is False
        assert result.needs_retry is True
        assert result.rollback_performed is True
        assert "Validation failed" in result.error_message
        assert result.validation_result is not None
        assert result.validation_result.resolved is False

    def test_execute_decision_without_original_error(self, tmp_path):
        """Test execution without original_error skips validation."""
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

        # Mock deliverables validation
        with patch.object(executor, "_validate_deliverables", return_value=True):
            # Don't provide original_error - validation should be skipped
            result = executor.execute_decision(decision, phase_spec)

        assert result.patch_applied is True
        assert result.fix_validated is True  # Skipped validation counts as passed
