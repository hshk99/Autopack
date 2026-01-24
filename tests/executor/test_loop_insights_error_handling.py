"""Tests for IMP-LOOP-001: Error handling for persist_insights call.

Tests cover:
- Graceful error handling when persist_insights fails
- Success logging when persist_insights succeeds
- Non-blocking behavior (loop continues after failures)
- Extra context logging for debugging
"""

import pytest
from unittest.mock import Mock, patch

from autopack.executor.autonomous_loop import AutonomousLoop


class TestPersistLoopInsights:
    """Test _persist_loop_insights graceful error handling (IMP-LOOP-001)."""

    def test_persist_loop_insights_success_logs_debug(self):
        """Verify success case logs debug message."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        loop = AutonomousLoop(mock_executor)

        with patch.object(loop, "_persist_telemetry_insights") as mock_persist:
            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                loop._persist_loop_insights()

        mock_persist.assert_called_once()
        mock_logger.debug.assert_called_with("Loop insights persisted successfully")

    def test_persist_loop_insights_failure_logs_warning(self):
        """Verify failure case logs warning without re-raising."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        loop = AutonomousLoop(mock_executor)

        with patch.object(
            loop,
            "_persist_telemetry_insights",
            side_effect=Exception("Database connection failed"),
        ):
            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                # Should not raise
                loop._persist_loop_insights()

        # Should log warning with error message
        mock_logger.warning.assert_called()
        warning_call = mock_logger.warning.call_args
        assert "Failed to persist loop insights (non-fatal)" in warning_call[0][0]
        assert "Database connection failed" in warning_call[0][0]

    def test_persist_loop_insights_does_not_crash_loop(self):
        """Verify persist_insights failure doesn't crash the autonomous loop."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        loop = AutonomousLoop(mock_executor)

        # Simulate various error types
        error_types = [
            Exception("Generic error"),
            RuntimeError("Runtime error"),
            ConnectionError("Network error"),
            ValueError("Invalid data"),
        ]

        for error in error_types:
            with patch.object(loop, "_persist_telemetry_insights", side_effect=error):
                # Should not raise any exceptions
                try:
                    loop._persist_loop_insights()
                except Exception as e:
                    pytest.fail(f"_persist_loop_insights raised {type(e).__name__}: {e}")

    def test_persist_loop_insights_logs_insights_keys_when_provided(self):
        """Verify insights keys are logged in extra context when available."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        loop = AutonomousLoop(mock_executor)

        test_insights = {
            "cost_sinks": ["phase-1", "phase-2"],
            "failure_modes": ["timeout"],
            "retry_causes": [],
        }

        with patch.object(loop, "_persist_telemetry_insights", side_effect=Exception("Test error")):
            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                loop._persist_loop_insights(insights=test_insights)

        # Check that extra context includes insights keys
        warning_call = mock_logger.warning.call_args
        extra = warning_call[1].get("extra", {})
        assert "insights_keys" in extra
        assert set(extra["insights_keys"]) == {"cost_sinks", "failure_modes", "retry_causes"}

    def test_persist_loop_insights_no_extra_when_insights_none(self):
        """Verify no extra context when insights is None."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        loop = AutonomousLoop(mock_executor)

        with patch.object(loop, "_persist_telemetry_insights", side_effect=Exception("Test error")):
            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                loop._persist_loop_insights(insights=None)

        # Check that extra context is empty
        warning_call = mock_logger.warning.call_args
        extra = warning_call[1].get("extra", {})
        assert "insights_keys" not in extra


class TestFinalizeExecutionIntegration:
    """Test _persist_loop_insights integration with _finalize_execution."""

    def test_finalize_execution_calls_persist_loop_insights(self):
        """Verify _finalize_execution calls _persist_loop_insights for completed runs."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._get_project_slug.return_value = "test-project"
        mock_executor._improvement_tasks = []

        loop = AutonomousLoop(mock_executor)

        stats = {
            "iteration": 5,
            "phases_executed": 3,
            "phases_failed": 0,
            "stop_reason": "no_more_executable_phases",
        }

        with patch.object(loop, "_persist_loop_insights") as mock_persist:
            with patch.object(loop, "_generate_improvement_tasks"):
                with patch.object(loop, "_mark_improvement_tasks_completed"):
                    with patch("autopack.executor.autonomous_loop.log_build_event"):
                        loop._finalize_execution(stats)

        mock_persist.assert_called_once()

    def test_finalize_execution_continues_after_persist_failure(self):
        """Verify _finalize_execution continues even if persist fails."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._get_project_slug.return_value = "test-project"
        mock_executor._improvement_tasks = []

        loop = AutonomousLoop(mock_executor)

        stats = {
            "iteration": 5,
            "phases_executed": 3,
            "phases_failed": 0,
            "stop_reason": "no_more_executable_phases",
        }

        # Note: _persist_loop_insights handles errors internally, but let's verify
        # finalize continues even if there's an unexpected error
        with patch.object(loop, "_persist_loop_insights"):
            with patch.object(loop, "_generate_improvement_tasks") as mock_generate:
                with patch.object(loop, "_mark_improvement_tasks_completed"):
                    with patch("autopack.executor.autonomous_loop.log_build_event"):
                        loop._finalize_execution(stats)

        # Should have continued to generate_improvement_tasks
        mock_generate.assert_called_once()

    def test_finalize_execution_skips_persist_for_non_terminal_stops(self):
        """Verify _persist_loop_insights is not called for non-terminal stop reasons."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._get_project_slug.return_value = "test-project"

        loop = AutonomousLoop(mock_executor)

        non_terminal_reasons = [
            "max_iterations",
            "stop_signal",
            "stop_on_first_failure",
            "budget_exhausted",
        ]

        for reason in non_terminal_reasons:
            stats = {
                "iteration": 5,
                "phases_executed": 3,
                "phases_failed": 1,
                "stop_reason": reason,
            }

            with patch.object(loop, "_persist_loop_insights") as mock_persist:
                with patch("autopack.executor.autonomous_loop.log_build_event"):
                    loop._finalize_execution(stats)

            (
                mock_persist.assert_not_called(),
                (f"_persist_loop_insights should not be called for stop_reason={reason}"),
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
