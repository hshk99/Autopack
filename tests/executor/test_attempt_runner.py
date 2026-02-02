"""
Tests for Attempt Runner Module

Tests for single attempt execution wrapper (IMP-ARCH-007).
Verifies that attempts are properly executed with error recovery.
"""

from unittest.mock import Mock

import pytest

from autopack.executor.attempt_runner import AttemptRunResult, run_single_attempt_with_recovery


class TestAttemptRunResult:
    """Tests for AttemptRunResult dataclass."""

    def test_attempt_run_result_creation(self):
        """Verify AttemptRunResult can be created."""
        result = AttemptRunResult(success=True, status="COMPLETE")
        assert result.success is True
        assert result.status == "COMPLETE"

    def test_attempt_run_result_frozen(self):
        """Verify AttemptRunResult is immutable."""
        result = AttemptRunResult(success=True, status="COMPLETE")
        with pytest.raises(AttributeError):
            result.success = False

    def test_attempt_run_result_failure_state(self):
        """Verify AttemptRunResult can represent failures."""
        result = AttemptRunResult(success=False, status="FAILED")
        assert result.success is False
        assert result.status == "FAILED"

    def test_attempt_run_result_various_statuses(self):
        """Verify AttemptRunResult handles various status values."""
        statuses = ["COMPLETE", "FAILED", "BLOCKED", "TOKEN_ESCALATION"]
        for status in statuses:
            result = AttemptRunResult(success=False, status=status)
            assert result.status == status


class TestRunSingleAttemptWithRecovery:
    """Tests for run_single_attempt_with_recovery function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_executor = Mock()
        self.phase = {"phase_id": "test-phase-1", "type": "BUILD"}

    def test_successful_attempt_execution(self):
        """Verify successful attempt execution returns correct result."""
        # Setup: executor returns success
        self.mock_executor._execute_phase_with_recovery.return_value = (True, "COMPLETE")
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        # Execute
        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=["/src", "/tests"],
        )

        # Verify
        assert result.success is True
        assert result.status == "COMPLETE"

    def test_failed_attempt_execution(self):
        """Verify failed attempt execution returns correct result."""
        # Setup: executor returns failure
        self.mock_executor.error_recovery.execute_with_retry.return_value = (False, "FAILED")

        # Execute
        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=["/src"],
        )

        # Verify
        assert result.success is False
        assert result.status == "FAILED"

    def test_attempt_index_passed_to_executor(self):
        """Verify attempt_index is passed through to executor."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        # Execute with different attempt indices
        for attempt_idx in [0, 1, 2, 3]:
            run_single_attempt_with_recovery(
                executor=self.mock_executor,
                phase=self.phase,
                attempt_index=attempt_idx,
                allowed_paths=[],
            )

            # Get the inner function that was called
            inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
            # Execute the inner function to verify it calls _execute_phase_with_recovery with correct index
            inner_func()

            # Verify executor was called with correct attempt_index
            self.mock_executor._execute_phase_with_recovery.assert_called()
            call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
            assert call_kwargs["attempt_index"] == attempt_idx

    def test_allowed_paths_passed_to_executor(self):
        """Verify allowed_paths are passed through to executor."""
        allowed_paths = ["/src/autopack", "/tests/autopack"]
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=allowed_paths,
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify executor was called with correct allowed_paths
        self.mock_executor._execute_phase_with_recovery.assert_called()
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["allowed_paths"] == allowed_paths

    def test_memory_context_passed_to_executor(self):
        """Verify memory_context is passed through to executor."""
        memory_context = "Some memory context data"
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
            memory_context=memory_context,
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify executor was called with correct memory_context
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["memory_context"] == memory_context

    def test_context_reduction_factor_passed_to_executor(self):
        """Verify context_reduction_factor is passed through to executor."""
        reduction_factor = 0.5
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
            context_reduction_factor=reduction_factor,
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify executor was called with correct context_reduction_factor
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["context_reduction_factor"] == reduction_factor

    def test_model_downgrade_passed_to_executor(self):
        """Verify model_downgrade is passed through to executor."""
        model_downgrade = "claude-3-sonnet"
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
            model_downgrade=model_downgrade,
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify executor was called with correct model_downgrade
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["model_downgrade"] == model_downgrade

    def test_phase_id_extracted_from_phase_dict(self):
        """Verify phase_id is correctly extracted and used in operation name."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        phase_id = "complex-phase-123"
        phase = {"phase_id": phase_id, "type": "DEPLOY"}

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=[],
        )

        # Verify operation_name includes phase_id
        call_kwargs = self.mock_executor.error_recovery.execute_with_retry.call_args[1]
        operation_name = call_kwargs["operation_name"]
        assert phase_id in operation_name
        assert "Phase execution:" in operation_name

    def test_missing_phase_id_handled_gracefully(self):
        """Verify missing phase_id is handled gracefully."""
        phase_no_id = {"type": "BUILD"}
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=phase_no_id,
            attempt_index=0,
            allowed_paths=[],
        )

        # Should still work, just with None as phase_id
        assert result.success is True

    def test_error_recovery_max_retries_is_one(self):
        """Verify error_recovery is called with max_retries=1."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
        )

        # Verify max_retries is 1
        call_kwargs = self.mock_executor.error_recovery.execute_with_retry.call_args[1]
        assert call_kwargs["max_retries"] == 1

    def test_token_escalation_status_propagated(self):
        """Verify TOKEN_ESCALATION status is correctly propagated."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (
            False,
            "TOKEN_ESCALATION",
        )

        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
        )

        assert result.success is False
        assert result.status == "TOKEN_ESCALATION"

    def test_blocked_status_propagated(self):
        """Verify BLOCKED status is correctly propagated."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (False, "BLOCKED")

        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
        )

        assert result.success is False
        assert result.status == "BLOCKED"

    def test_multiple_sequential_attempts(self):
        """Verify multiple sequential attempts can be run."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        results = []
        for attempt_idx in range(3):
            result = run_single_attempt_with_recovery(
                executor=self.mock_executor,
                phase=self.phase,
                attempt_index=attempt_idx,
                allowed_paths=[],
            )
            results.append(result)

        # Verify all attempts completed
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_none_allowed_paths(self):
        """Verify None allowed_paths is handled correctly."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=None,
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify allowed_paths was passed as None
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["allowed_paths"] is None

    def test_empty_allowed_paths(self):
        """Verify empty allowed_paths list is handled correctly."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=0,
            allowed_paths=[],
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify allowed_paths was passed as empty list
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["allowed_paths"] == []

    def test_all_optional_parameters_together(self):
        """Verify all optional parameters can be passed together."""
        self.mock_executor.error_recovery.execute_with_retry.return_value = (True, "COMPLETE")

        result = run_single_attempt_with_recovery(
            executor=self.mock_executor,
            phase=self.phase,
            attempt_index=1,
            allowed_paths=["/src/autopack"],
            memory_context="Memory data",
            context_reduction_factor=0.7,
            model_downgrade="claude-3-haiku",
        )

        # Get inner function and execute it
        inner_func = self.mock_executor.error_recovery.execute_with_retry.call_args[1]["func"]
        inner_func()

        # Verify all parameters were passed
        call_kwargs = self.mock_executor._execute_phase_with_recovery.call_args[1]
        assert call_kwargs["attempt_index"] == 1
        assert call_kwargs["allowed_paths"] == ["/src/autopack"]
        assert call_kwargs["memory_context"] == "Memory data"
        assert call_kwargs["context_reduction_factor"] == 0.7
        assert call_kwargs["model_downgrade"] == "claude-3-haiku"

        assert result.success is True


class TestAttemptRunnerIntegration:
    """Integration tests for attempt runner."""

    def test_executor_exception_handling(self):
        """Verify executor exceptions are handled gracefully."""
        mock_executor = Mock()
        phase = {"phase_id": "test-phase"}

        # Setup error recovery to propagate exceptions
        def error_recovery_side_effect(func, **kwargs):
            try:
                return func()
            except Exception as e:
                return (False, str(e))

        mock_executor.error_recovery.execute_with_retry.side_effect = error_recovery_side_effect
        mock_executor._execute_phase_with_recovery.side_effect = RuntimeError("Test error")

        result = run_single_attempt_with_recovery(
            executor=mock_executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=[],
        )

        assert result.success is False

    def test_recovery_retry_mechanism(self):
        """Verify error recovery retry mechanism is invoked."""
        mock_executor = Mock()
        phase = {"phase_id": "test-phase"}

        # Track how many times execute_with_retry is called
        call_count = 0

        def execute_with_retry_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return (True, "COMPLETE")

        mock_executor.error_recovery.execute_with_retry.side_effect = execute_with_retry_side_effect

        run_single_attempt_with_recovery(
            executor=mock_executor,
            phase=phase,
            attempt_index=0,
            allowed_paths=[],
        )

        # Verify execute_with_retry was called exactly once
        assert call_count == 1
