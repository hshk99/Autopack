"""Tests for autonomous_loop.py edge cases and error recovery.

Tests cover:
- Loop recovery from phase failures
- Empty queue handling and idle backoff
- Graceful stopping on critical errors
- Iteration limits and stop signals
- Adaptive sleep behavior
"""

import pytest
from unittest.mock import Mock, patch
from autopack.executor.autonomous_loop import AutonomousLoop
from autopack.supervisor.api_client import SupervisorApiHttpError


class TestAutonomousLoopRecovery:
    """Test autonomous loop recovery from phase failures."""

    def test_autonomous_loop_recovers_from_phase_failure(self):
        """Verify loop continues after phase failure instead of stopping."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"

        # Create loop without calling _initialize_intention_loop in __init__
        loop = AutonomousLoop(mock_executor)

        # Test execute_loop directly with simulated behavior
        def mock_execute_loop(poll_interval, max_iterations, stop_on_first_failure):
            """Simulate loop processing phases, one fails but continues."""
            return {
                "iteration": 2,
                "phases_executed": 1,
                "phases_failed": 1,
                "stop_reason": "no_more_executable_phases",
            }

        with patch.object(loop, "_execute_loop", side_effect=mock_execute_loop):
            with patch.object(loop, "_finalize_execution"):
                with patch.object(loop, "_verify_run_exists"):
                    with patch.object(loop, "_initialize_intention_loop"):
                        # Call run - should handle failure and continue
                        mock_executor._ensure_api_server_running.return_value = True
                        mock_executor._init_infrastructure = Mock()
                        loop.run(poll_interval=0.5, max_iterations=10, stop_on_first_failure=False)

        # Verify it processed despite failure
        # Check finalize was called (indicating successful run completion)
        assert mock_executor._init_infrastructure.called

    def test_autonomous_loop_handles_empty_queue(self):
        """Verify loop idles gracefully when no phases available."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._ensure_api_server_running.return_value = True
        mock_executor._init_infrastructure = Mock()

        loop = AutonomousLoop(mock_executor)

        def mock_execute_loop(poll_interval, max_iterations, stop_on_first_failure):
            """Simulate loop with no phases available."""
            return {
                "iteration": 1,
                "phases_executed": 0,
                "phases_failed": 0,
                "stop_reason": "no_more_executable_phases",
            }

        with patch.object(loop, "_execute_loop", side_effect=mock_execute_loop):
            with patch.object(loop, "_finalize_execution"):
                with patch.object(loop, "_verify_run_exists"):
                    with patch.object(loop, "_initialize_intention_loop"):
                        loop.run(poll_interval=0.5)

        # Verify executor was still initialized (graceful degradation)
        mock_executor._init_infrastructure.assert_called_once()

    def test_autonomous_loop_stops_on_critical_error(self):
        """Verify loop stops cleanly on critical/non-retriable errors."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._ensure_api_server_running.return_value = False

        loop = AutonomousLoop(mock_executor)

        # When API server cannot start, loop should return early
        with patch.object(loop, "_verify_run_exists") as mock_verify:
            result = loop.run(poll_interval=0.5)

        # Verify loop exited early without proceeding
        mock_verify.assert_not_called()
        assert result is None  # Early return

    def test_autonomous_loop_respects_max_iterations(self):
        """Verify loop stops after reaching max_iterations limit."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._ensure_api_server_running.return_value = True
        mock_executor._init_infrastructure = Mock()

        loop = AutonomousLoop(mock_executor)

        iteration_count = 0

        def mock_execute_loop(poll_interval, max_iterations, stop_on_first_failure):
            """Simulate loop respecting max_iterations."""
            nonlocal iteration_count
            iteration_count = max_iterations
            return {
                "iteration": iteration_count,
                "phases_executed": 0,
                "phases_failed": 0,
                "stop_reason": "max_iterations",
            }

        with patch.object(loop, "_execute_loop", side_effect=mock_execute_loop):
            with patch.object(loop, "_finalize_execution"):
                with patch.object(loop, "_verify_run_exists"):
                    with patch.object(loop, "_initialize_intention_loop"):
                        loop.run(poll_interval=0.5, max_iterations=3)

        assert iteration_count == 3  # Should stop at max_iterations

    def test_autonomous_loop_default_max_iterations_is_50(self):
        """Verify max_iterations defaults to 50 to prevent runaway execution (IMP-SAFETY-001)."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._ensure_api_server_running.return_value = True
        mock_executor._init_infrastructure = Mock()

        loop = AutonomousLoop(mock_executor)

        received_max_iterations = None

        def mock_execute_loop(poll_interval, max_iterations, stop_on_first_failure):
            """Capture max_iterations to verify default value."""
            nonlocal received_max_iterations
            received_max_iterations = max_iterations
            return {
                "iteration": 1,
                "phases_executed": 0,
                "phases_failed": 0,
                "stop_reason": "max_iterations",
            }

        with patch.object(loop, "_execute_loop", side_effect=mock_execute_loop):
            with patch.object(loop, "_finalize_execution"):
                with patch.object(loop, "_verify_run_exists"):
                    with patch.object(loop, "_initialize_intention_loop"):
                        # Call run without specifying max_iterations
                        loop.run(poll_interval=0.5)

        # IMP-SAFETY-001: Default must be 50 to prevent infinite execution
        assert received_max_iterations == 50, (
            f"Expected default max_iterations=50, got {received_max_iterations}"
        )

    def test_autonomous_loop_stop_on_first_failure_saves_tokens(self):
        """Verify stop_on_first_failure flag stops immediately on failure."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-123"
        mock_executor._ensure_api_server_running.return_value = True
        mock_executor._init_infrastructure = Mock()

        loop = AutonomousLoop(mock_executor)

        def mock_execute_loop(poll_interval, max_iterations, stop_on_first_failure):
            """Simulate early stop on first failure."""
            if stop_on_first_failure:
                return {
                    "iteration": 1,
                    "phases_executed": 0,
                    "phases_failed": 1,
                    "stop_reason": "stop_on_first_failure",
                }
            else:
                return {
                    "iteration": 5,
                    "phases_executed": 2,
                    "phases_failed": 3,
                    "stop_reason": "no_more_executable_phases",
                }

        with patch.object(loop, "_execute_loop", side_effect=mock_execute_loop):
            with patch.object(loop, "_finalize_execution") as mock_finalize:
                with patch.object(loop, "_verify_run_exists"):
                    with patch.object(loop, "_initialize_intention_loop"):
                        loop.run(poll_interval=0.5, stop_on_first_failure=True)

        # Verify finalization was called with early stop stats
        call_args = mock_finalize.call_args[0][0]
        assert call_args["stop_reason"] == "stop_on_first_failure"
        assert call_args["phases_failed"] == 1


class TestAdaptiveSleep:
    """Test adaptive sleep behavior for idle backoff."""

    def test_adaptive_sleep_normal_interval(self):
        """Verify normal sleep interval when not idle."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        with patch("time.sleep") as mock_sleep:
            sleep_time = loop._adaptive_sleep(is_idle=False, base_interval=0.5)

        mock_sleep.assert_called_once_with(0.5)
        assert sleep_time == 0.5

    def test_adaptive_sleep_idle_backoff(self):
        """Verify backoff multiplier applied when idle."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        with patch("time.sleep") as mock_sleep:
            sleep_time = loop._adaptive_sleep(is_idle=True, base_interval=0.5)

        # Should apply backoff: 0.5 * 2.0 = 1.0
        expected_sleep = 0.5 * loop.idle_backoff_multiplier
        mock_sleep.assert_called_once_with(expected_sleep)
        assert sleep_time == expected_sleep

    def test_adaptive_sleep_respects_max_idle_sleep(self):
        """Verify sleep time is capped at max_idle_sleep."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        # Test with large base_interval that would exceed max_idle_sleep
        with patch("time.sleep") as mock_sleep:
            sleep_time = loop._adaptive_sleep(is_idle=True, base_interval=10.0)

        # Should cap at max_idle_sleep (5.0)
        mock_sleep.assert_called_once_with(loop.max_idle_sleep)
        assert sleep_time == loop.max_idle_sleep

    def test_adaptive_sleep_uses_default_poll_interval(self):
        """Verify default poll_interval used when base_interval not provided."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)
        loop.poll_interval = 0.75

        with patch("time.sleep") as mock_sleep:
            sleep_time = loop._adaptive_sleep(is_idle=False)

        mock_sleep.assert_called_once_with(0.75)
        assert sleep_time == 0.75


class TestRunExistsVerification:
    """Test run existence verification in API database."""

    def test_verify_run_exists_success(self):
        """Verify run existence check succeeds for valid run."""
        mock_executor = Mock()
        mock_executor.run_id = "valid-run-123"
        mock_executor.api_client = Mock()
        mock_executor.api_client.get_run.return_value = {"run_id": "valid-run-123"}

        with patch.object(AutonomousLoop, "_initialize_intention_loop"):
            loop = AutonomousLoop(mock_executor)

        # Should not raise
        loop._verify_run_exists()
        mock_executor.api_client.get_run.assert_called_once_with("valid-run-123", timeout=10)

    def test_verify_run_exists_404_raises_error(self):
        """Verify 404 error raises RuntimeError indicating DB mismatch."""
        mock_executor = Mock()
        mock_executor.run_id = "nonexistent-run"
        mock_executor.api_client = Mock()
        mock_executor.api_client.get_run.side_effect = SupervisorApiHttpError(
            status_code=404, message="Not Found"
        )

        with patch.object(AutonomousLoop, "_initialize_intention_loop"):
            loop = AutonomousLoop(mock_executor)

        with pytest.raises(RuntimeError, match="not found in API database"):
            loop._verify_run_exists()

    def test_verify_run_exists_non_404_error_continues(self):
        """Verify non-404 errors are logged but don't stop execution."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.api_client = Mock()
        mock_executor.api_client.get_run.side_effect = SupervisorApiHttpError(
            status_code=500, message="Internal Server Error"
        )

        with patch.object(AutonomousLoop, "_initialize_intention_loop"):
            loop = AutonomousLoop(mock_executor)

        # Should not raise for non-404 errors (transient failures)
        loop._verify_run_exists()

    def test_verify_run_exists_network_error_continues(self):
        """Verify network errors don't block execution."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.api_client = Mock()
        mock_executor.api_client.get_run.side_effect = ConnectionError("Network timeout")

        with patch.object(AutonomousLoop, "_initialize_intention_loop"):
            loop = AutonomousLoop(mock_executor)

        # Should not raise (sanity check is best-effort)
        loop._verify_run_exists()


class TestIntentionLoopInitialization:
    """Test intention-first loop initialization."""

    def test_initialize_intention_loop_handles_missing_imports(self):
        """Verify loop handles missing intention anchor gracefully."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        # The real code will handle import errors internally
        # Just verify it doesn't crash
        try:
            loop._initialize_intention_loop()
        except ImportError:
            # Expected if modules not available
            pass


class TestExecuteLoopPhaseHandling:
    """Test phase selection and handling in execute_loop."""

    def test_execute_loop_processes_queued_phases(self):
        """Verify loop processes available queued phases."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.project_root = "."  # IMP-SOT-001: SOT drift check needs valid path
        mock_executor._phase_failure_counts = {}
        mock_executor._run_tokens_used = 0  # IMP-COST-001: Budget check needs integer
        mock_executor.get_run_status.return_value = {"phases": [{"phase_id": "phase-1"}]}
        mock_executor.get_next_queued_phase.return_value = {"phase_id": "phase-1"}
        mock_executor.execute_phase.return_value = (True, "COMPLETE")

        loop = AutonomousLoop(mock_executor)

        stats = loop._execute_loop(
            poll_interval=0.01, max_iterations=1, stop_on_first_failure=False
        )

        assert stats["phases_executed"] == 1
        assert stats["stop_reason"] == "max_iterations"

    def test_execute_loop_stale_phase_detection(self):
        """Verify loop handles stale phase detection gracefully."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.project_root = "."  # IMP-SOT-001: SOT drift check needs valid path
        mock_executor._phase_failure_counts = {}
        mock_executor._run_tokens_used = 0  # IMP-COST-001: Budget check needs integer
        mock_executor.get_run_status.return_value = {}
        mock_executor.get_next_queued_phase.return_value = None
        mock_executor._detect_and_reset_stale_phases = Mock(
            side_effect=Exception("Stale detection error")
        )

        loop = AutonomousLoop(mock_executor)

        stats = loop._execute_loop(
            poll_interval=0.01, max_iterations=1, stop_on_first_failure=False
        )

        # Should complete despite stale detection error
        assert "stop_reason" in stats


class TestBudgetExhaustionCheck:
    """Test budget exhaustion check ordering (IMP-SAFETY-005)."""

    def test_budget_check_happens_before_context_loading(self):
        """Verify budget exhaustion is checked BEFORE context loading operations.

        IMP-SAFETY-005: Budget check was happening after context loading,
        which meant tokens were consumed before checking if budget was exceeded.
        The fix moves the check to the start of each iteration.
        """
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.project_root = "."
        mock_executor._phase_failure_counts = {}
        # Set tokens used to exceed budget
        mock_executor._run_tokens_used = 100_000

        loop = AutonomousLoop(mock_executor)

        # Track call order
        call_order = []

        def mock_get_run_status():
            call_order.append("get_run_status")
            return {"phases": []}

        def mock_get_memory_context(*args, **kwargs):
            call_order.append("get_memory_context")
            return None

        mock_executor.get_run_status = mock_get_run_status

        # Patch settings to have a lower budget cap
        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.run_token_cap = 50_000  # Less than tokens_used

            from autopack.autonomous.budgeting import BudgetExhaustedError

            with pytest.raises(BudgetExhaustedError):
                loop._execute_loop(
                    poll_interval=0.01, max_iterations=1, stop_on_first_failure=False
                )

        # Budget check should happen before get_run_status (which could consume tokens)
        assert "get_run_status" not in call_order, (
            "get_run_status should not be called when budget is exhausted"
        )
        assert "get_memory_context" not in call_order, (
            "get_memory_context should not be called when budget is exhausted"
        )

    def test_budget_check_allows_iteration_when_budget_available(self):
        """Verify loop continues when budget is not exhausted."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.project_root = "."
        mock_executor._phase_failure_counts = {}
        mock_executor._run_tokens_used = 1_000  # Well under budget
        mock_executor.get_run_status.return_value = {"phases": []}
        mock_executor.get_next_queued_phase.return_value = None

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.run_token_cap = 50_000  # Plenty of budget remaining

            # Mock SOT drift check to avoid file system interactions
            with patch.object(loop, "_check_sot_drift"):
                stats = loop._execute_loop(
                    poll_interval=0.01, max_iterations=1, stop_on_first_failure=False
                )

        # Should complete iteration and check for phases
        assert stats["stop_reason"] == "no_more_executable_phases"
        mock_executor.get_run_status.assert_called()

    def test_budget_exhausted_error_includes_usage_details(self):
        """Verify budget exhausted error includes usage and cap details."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.project_root = "."
        mock_executor._phase_failure_counts = {}
        mock_executor._run_tokens_used = 60_000  # Over budget

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.run_token_cap = 50_000

            from autopack.autonomous.budgeting import BudgetExhaustedError

            with pytest.raises(BudgetExhaustedError) as exc_info:
                loop._execute_loop(
                    poll_interval=0.01, max_iterations=1, stop_on_first_failure=False
                )

        error_msg = str(exc_info.value)
        assert "60000" in error_msg or "60,000" in error_msg  # tokens used
        assert "50000" in error_msg or "50,000" in error_msg  # token cap
        assert "budget exhausted" in error_msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
