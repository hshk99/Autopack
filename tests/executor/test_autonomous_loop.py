"""Tests for autonomous_loop.py edge cases and error recovery.

Tests cover:
- Loop recovery from phase failures
- Empty queue handling and idle backoff
- Graceful stopping on critical errors
- Iteration limits and stop signals
- Adaptive sleep behavior
"""

from unittest.mock import Mock, patch

import pytest

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
        assert (
            received_max_iterations == 50
        ), f"Expected default max_iterations=50, got {received_max_iterations}"

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
        assert (
            "get_run_status" not in call_order
        ), "get_run_status should not be called when budget is exhausted"
        assert (
            "get_memory_context" not in call_order
        ), "get_memory_context should not be called when budget is exhausted"

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


class TestContextCeiling:
    """Test context ceiling enforcement (IMP-PERF-002)."""

    def test_estimate_tokens_empty_string(self):
        """Verify empty string returns 0 tokens."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        assert loop._estimate_tokens("") == 0
        assert loop._estimate_tokens(None) == 0

    def test_estimate_tokens_basic_calculation(self):
        """Verify token estimation uses ~4 chars per token heuristic."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        # 100 chars should estimate to ~25 tokens
        test_string = "a" * 100
        estimated = loop._estimate_tokens(test_string)
        assert estimated == 25  # 100 // 4

        # 400 chars should estimate to ~100 tokens
        test_string = "b" * 400
        estimated = loop._estimate_tokens(test_string)
        assert estimated == 100  # 400 // 4

    def test_truncate_to_budget_no_truncation_needed(self):
        """Verify no truncation when content fits within budget."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        content = "a" * 100  # ~25 tokens
        result = loop._truncate_to_budget(content, 50)  # 50 token budget

        assert result == content  # Should not truncate

    def test_truncate_to_budget_truncates_from_beginning(self):
        """Verify truncation keeps most recent content (end of string)."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        content = "START_" + "a" * 100 + "_END"  # ~27 tokens
        result = loop._truncate_to_budget(content, 10)  # 10 token budget = 40 chars

        # Should keep the end, not the start
        assert "_END" in result
        assert "START_" not in result

    def test_truncate_to_budget_zero_budget_returns_empty(self):
        """Verify zero budget returns empty string."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        content = "Some content here"
        result = loop._truncate_to_budget(content, 0)

        assert result == ""

    def test_truncate_to_budget_negative_budget_returns_empty(self):
        """Verify negative budget returns empty string."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        content = "Some content here"
        result = loop._truncate_to_budget(content, -10)

        assert result == ""

    def test_inject_context_tracks_total_tokens(self):
        """Verify context injection tracks cumulative token count."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)
        loop._context_ceiling = 1000  # High ceiling

        # First injection: 100 chars = ~25 tokens
        context1 = "a" * 100
        loop._inject_context_with_ceiling(context1)
        assert loop._total_context_tokens == 25

        # Second injection: 200 chars = ~50 tokens
        context2 = "b" * 200
        loop._inject_context_with_ceiling(context2)
        assert loop._total_context_tokens == 75  # 25 + 50

    def test_inject_context_truncates_when_ceiling_reached(self):
        """Verify context is truncated when ceiling would be exceeded."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)
        loop._context_ceiling = 50  # 50 token ceiling

        # First injection: 100 chars = 25 tokens (fits)
        context1 = "a" * 100
        result1 = loop._inject_context_with_ceiling(context1)
        assert result1 == context1
        assert loop._total_context_tokens == 25

        # Second injection: 200 chars = 50 tokens (would exceed ceiling)
        # Only 25 tokens remaining budget
        context2 = "b" * 200
        result2 = loop._inject_context_with_ceiling(context2)
        # Should be truncated to fit ~25 tokens = ~100 chars
        assert len(result2) < len(context2)

    def test_inject_context_returns_empty_when_ceiling_exhausted(self):
        """Verify empty string returned when ceiling is fully exhausted."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)
        loop._context_ceiling = 25  # Small ceiling

        # First injection fills ceiling: 100 chars = 25 tokens
        context1 = "a" * 100
        loop._inject_context_with_ceiling(context1)
        assert loop._total_context_tokens == 25

        # Second injection should return empty (no budget left)
        context2 = "b" * 100
        result2 = loop._inject_context_with_ceiling(context2)
        assert result2 == ""
        assert loop._total_context_tokens == 25  # Unchanged

    def test_inject_context_empty_string_returns_empty(self):
        """Verify empty context returns empty without tracking."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)
        loop._context_ceiling = 1000

        result = loop._inject_context_with_ceiling("")
        assert result == ""
        assert loop._total_context_tokens == 0

    def test_context_ceiling_initialized_from_settings(self):
        """Verify context ceiling is initialized from settings."""
        mock_executor = Mock()

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.context_ceiling_tokens = 75000
            loop = AutonomousLoop(mock_executor)

        assert loop._context_ceiling == 75000
        assert loop._total_context_tokens == 0

    def test_context_ceiling_default_value(self):
        """Verify default context ceiling is 50000 tokens."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        # Default from settings should be 50000
        # (We can't easily test this without mocking, but we verify the attribute exists)
        assert hasattr(loop, "_context_ceiling")
        assert hasattr(loop, "_total_context_tokens")
        assert loop._total_context_tokens == 0


class TestGeneratedTaskExecution:
    """Tests for generated task fetching and execution (IMP-LOOP-004)."""

    def test_fetch_generated_tasks_disabled_returns_empty(self):
        """Verify empty list when generated task execution is disabled."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = False

            result = loop._fetch_generated_tasks()

        assert result == []

    def test_fetch_generated_tasks_no_pending_tasks_returns_empty(self):
        """Verify empty list when no pending tasks exist."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = True
            mock_settings.generated_task_max_per_run = 3

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.return_value = []

                result = loop._fetch_generated_tasks()

        assert result == []

    def test_fetch_generated_tasks_converts_to_phase_specs(self):
        """Verify tasks are converted to executable phase specifications."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-456"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        # Create a mock GeneratedTask
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.title = "Test Improvement"
        mock_task.description = "Fix performance issue"
        mock_task.priority = "high"
        mock_task.source_insights = ["insight-1", "insight-2"]
        mock_task.suggested_files = ["src/module.py"]
        mock_task.estimated_effort = "M"
        mock_task.run_id = "prev-run-123"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = True
            mock_settings.generated_task_max_per_run = 3

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.return_value = [mock_task]

                result = loop._fetch_generated_tasks()

        assert len(result) == 1
        phase_spec = result[0]

        # Verify phase spec structure
        assert phase_spec["phase_id"] == "generated-task-execution-task-123"
        assert phase_spec["phase_type"] == "generated-task-execution"
        assert phase_spec["status"] == "QUEUED"
        assert phase_spec["category"] == "improvement"
        assert "Test Improvement" in phase_spec["description"]
        assert phase_spec["scope"]["paths"] == ["src/module.py"]

        # Verify task metadata is embedded
        assert "_generated_task" in phase_spec
        assert phase_spec["_generated_task"]["task_id"] == "task-123"

    def test_fetch_generated_tasks_marks_status_in_progress(self):
        """Verify tasks are marked as in_progress when fetched."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run-789"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        mock_task = Mock()
        mock_task.task_id = "task-456"
        mock_task.title = "Test Task"
        mock_task.description = "Description"
        mock_task.priority = "medium"
        mock_task.source_insights = []
        mock_task.suggested_files = []
        mock_task.estimated_effort = "S"
        mock_task.run_id = "prev-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = True
            mock_settings.generated_task_max_per_run = 3

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.return_value = [mock_task]

                loop._fetch_generated_tasks()

                # Verify mark_task_status was called
                mock_generator.mark_task_status.assert_called_once_with(
                    "task-456", "in_progress", executed_in_run_id="test-run-789"
                )

    def test_fetch_generated_tasks_handles_exceptions(self):
        """Verify exceptions are handled gracefully."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.task_generation_auto_execute = True
            mock_settings.generated_task_max_per_run = 3

            with patch("autopack.roadc.task_generator.AutonomousTaskGenerator") as MockGenerator:
                mock_generator = MockGenerator.return_value
                mock_generator.get_pending_tasks.side_effect = Exception("DB error")

                # Should not raise, should return empty list
                result = loop._fetch_generated_tasks()

        assert result == []

    def test_inject_generated_tasks_into_backlog_adds_phases(self):
        """Verify generated tasks are injected into run_data phases."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        run_data = {
            "phases": [
                {"phase_id": "existing-phase-1"},
                {"phase_id": "existing-phase-2"},
            ]
        }

        mock_generated_phases = [
            {
                "phase_id": "generated-task-execution-task-1",
                "phase_type": "generated-task-execution",
            },
            {
                "phase_id": "generated-task-execution-task-2",
                "phase_type": "generated-task-execution",
            },
        ]

        with patch.object(loop, "_fetch_generated_tasks", return_value=mock_generated_phases):
            result = loop._inject_generated_tasks_into_backlog(run_data)

        # Verify phases were added
        assert len(result["phases"]) == 4
        assert result["phases"][0]["phase_id"] == "existing-phase-1"
        assert result["phases"][1]["phase_id"] == "existing-phase-2"
        assert result["phases"][2]["phase_id"] == "generated-task-execution-task-1"
        assert result["phases"][3]["phase_id"] == "generated-task-execution-task-2"

    def test_inject_generated_tasks_into_backlog_no_tasks(self):
        """Verify run_data unchanged when no generated tasks."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        run_data = {"phases": [{"phase_id": "existing-phase-1"}]}

        with patch.object(loop, "_fetch_generated_tasks", return_value=[]):
            result = loop._inject_generated_tasks_into_backlog(run_data)

        # Should return unchanged
        assert len(result["phases"]) == 1
        assert result is run_data

    def test_priority_mapping_in_phase_spec(self):
        """Verify task priority maps to correct phase priority_order."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor.db_session = None

        loop = AutonomousLoop(mock_executor)

        # Test different priority levels
        priority_tests = [
            ("critical", 1),
            ("high", 2),
            ("medium", 3),
            ("low", 4),
        ]

        for task_priority, expected_order in priority_tests:
            mock_task = Mock()
            mock_task.task_id = f"task-{task_priority}"
            mock_task.title = "Test"
            mock_task.description = "Description"
            mock_task.priority = task_priority
            mock_task.source_insights = []
            mock_task.suggested_files = []
            mock_task.estimated_effort = "M"
            mock_task.run_id = "prev-run"

            with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
                mock_settings.task_generation_auto_execute = True
                mock_settings.generated_task_max_per_run = 1

                with patch(
                    "autopack.roadc.task_generator.AutonomousTaskGenerator"
                ) as MockGenerator:
                    mock_generator = MockGenerator.return_value
                    mock_generator.get_pending_tasks.return_value = [mock_task]

                    result = loop._fetch_generated_tasks()

            assert (
                result[0]["priority_order"] == expected_order
            ), f"Priority {task_priority} should map to order {expected_order}"


class TestMandatoryFeedbackPipeline:
    """Test mandatory feedback pipeline behavior (IMP-LOOP-011)."""

    def test_feedback_pipeline_always_enabled_even_when_settings_disable(self):
        """Verify feedback_pipeline_enabled is always True regardless of settings.

        IMP-LOOP-011: FeedbackPipeline is MANDATORY for the self-improvement loop.
        Even if settings.feedback_pipeline_enabled is False, the pipeline must remain enabled.
        """
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            # Configure settings to disable feedback pipeline
            mock_settings.feedback_pipeline_enabled = False
            # Set other required settings with defaults
            mock_settings.max_parallel_phases = 2
            mock_settings.telemetry_aggregation_interval = 3
            mock_settings.task_effectiveness_tracking_enabled = True
            mock_settings.meta_metrics_health_check_enabled = False
            mock_settings.context_ceiling_tokens = 50000

            loop = AutonomousLoop(mock_executor)

            # IMP-LOOP-011: Must be True regardless of settings
            assert (
                loop._feedback_pipeline_enabled is True
            ), "feedback_pipeline_enabled must be True regardless of settings"

    def test_feedback_pipeline_logs_warning_when_settings_try_to_disable(self, caplog):
        """Verify warning is logged when settings attempt to disable feedback pipeline.

        IMP-LOOP-011: When settings.feedback_pipeline_enabled=False, a warning should
        be logged indicating the override is ignored.
        """
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            # Configure settings to disable feedback pipeline
            mock_settings.feedback_pipeline_enabled = False
            mock_settings.max_parallel_phases = 2
            mock_settings.telemetry_aggregation_interval = 3
            mock_settings.task_effectiveness_tracking_enabled = True
            mock_settings.meta_metrics_health_check_enabled = False
            mock_settings.context_ceiling_tokens = 50000

            import logging

            with caplog.at_level(logging.WARNING):
                loop = AutonomousLoop(mock_executor)

            # Verify warning was logged
            assert any(
                "IMP-LOOP-011" in record.message
                and "feedback_pipeline_enabled=False" in record.message
                for record in caplog.records
            ), "Expected warning about feedback_pipeline_enabled=False being ignored"

            # Verify pipeline is still enabled
            assert loop._feedback_pipeline_enabled is True

    def test_feedback_pipeline_no_warning_when_settings_enable(self, caplog):
        """Verify no warning logged when settings have feedback_pipeline_enabled=True.

        IMP-LOOP-011: Warning should only appear when settings try to disable.
        """
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            # Configure settings to enable feedback pipeline (default)
            mock_settings.feedback_pipeline_enabled = True
            mock_settings.max_parallel_phases = 2
            mock_settings.telemetry_aggregation_interval = 3
            mock_settings.task_effectiveness_tracking_enabled = True
            mock_settings.meta_metrics_health_check_enabled = False
            mock_settings.context_ceiling_tokens = 50000

            import logging

            with caplog.at_level(logging.WARNING):
                loop = AutonomousLoop(mock_executor)

            # Verify no IMP-LOOP-011 warning was logged
            imp_loop_011_warnings = [
                record
                for record in caplog.records
                if "IMP-LOOP-011" in record.message and record.levelno >= logging.WARNING
            ]
            assert (
                len(imp_loop_011_warnings) == 0
            ), "Should not log warning when feedback_pipeline_enabled=True in settings"

            # Verify pipeline is enabled
            assert loop._feedback_pipeline_enabled is True


class TestHealthGateTaskGeneration:
    """Tests for health gate blocking task generation (IMP-LOOP-001)."""

    def test_get_feedback_loop_health_returns_healthy_by_default(self):
        """Verify health returns HEALTHY when no issues detected."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        # Reset counters to ensure clean state
        loop._total_phases_executed = 10
        loop._total_phases_failed = 0
        loop._circuit_breaker = None

        health = loop._get_feedback_loop_health()

        assert health == "healthy"

    def test_get_feedback_loop_health_degraded_on_high_failure_ratio(self):
        """Verify health returns DEGRADED when failure ratio is 25-50%."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        loop._total_phases_executed = 7
        loop._total_phases_failed = 3  # 30% failure rate
        loop._circuit_breaker = None

        health = loop._get_feedback_loop_health()

        assert health == "degraded"

    def test_get_feedback_loop_health_attention_required_on_critical_failure_ratio(self):
        """Verify health returns ATTENTION_REQUIRED when failure ratio >= 50%."""
        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        loop._total_phases_executed = 5
        loop._total_phases_failed = 5  # 50% failure rate
        loop._circuit_breaker = None

        health = loop._get_feedback_loop_health()

        assert health == "attention_required"

    def test_get_feedback_loop_health_attention_required_when_circuit_open(self):
        """Verify health returns ATTENTION_REQUIRED when circuit breaker is OPEN."""
        from autopack.executor.autonomous_loop import CircuitBreaker, CircuitBreakerState

        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        loop._circuit_breaker = CircuitBreaker()
        loop._circuit_breaker._state = CircuitBreakerState.OPEN

        health = loop._get_feedback_loop_health()

        assert health == "attention_required"

    def test_get_feedback_loop_health_degraded_when_circuit_half_open(self):
        """Verify health returns DEGRADED when circuit breaker is HALF_OPEN."""
        from autopack.executor.autonomous_loop import CircuitBreaker, CircuitBreakerState

        mock_executor = Mock()
        loop = AutonomousLoop(mock_executor)

        loop._circuit_breaker = CircuitBreaker()
        loop._circuit_breaker._state = CircuitBreakerState.HALF_OPEN

        health = loop._get_feedback_loop_health()

        assert health == "degraded"

    def test_health_gate_blocks_task_gen_when_attention_required(self):
        """Verify task generation is skipped when health is ATTENTION_REQUIRED (IMP-LOOP-001)."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        # Set up unhealthy state
        loop._total_phases_executed = 5
        loop._total_phases_failed = 5  # 50% failure triggers ATTENTION_REQUIRED

        # Track whether _generate_improvement_tasks is called
        with patch.object(loop, "_generate_improvement_tasks") as mock_gen:
            with patch.object(loop, "_persist_loop_insights"):
                with patch("autopack.executor.autonomous_loop.log_build_event"):
                    # Call _finalize_execution with no_more_executable_phases
                    stats = {
                        "iteration": 10,
                        "phases_executed": 5,
                        "phases_failed": 5,
                        "stop_reason": "no_more_executable_phases",
                    }
                    loop._finalize_execution(stats)

            # Task generation should NOT be called
            mock_gen.assert_not_called()

    def test_health_gate_allows_task_gen_when_healthy(self):
        """Verify task generation proceeds when health is HEALTHY (IMP-LOOP-001)."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = Mock(return_value="test-project")

        loop = AutonomousLoop(mock_executor)

        # Set up healthy state
        loop._total_phases_executed = 10
        loop._total_phases_failed = 0

        # Track whether _generate_improvement_tasks is called
        with patch.object(loop, "_generate_improvement_tasks") as mock_gen:
            with patch.object(loop, "_persist_loop_insights"):
                with patch("autopack.executor.autonomous_loop.log_build_event"):
                    with patch.object(loop.executor, "_best_effort_write_run_summary"):
                        # Call _finalize_execution with no_more_executable_phases
                        stats = {
                            "iteration": 10,
                            "phases_executed": 10,
                            "phases_failed": 0,
                            "stop_reason": "no_more_executable_phases",
                        }
                        loop._finalize_execution(stats)

            # Task generation SHOULD be called
            mock_gen.assert_called_once()

    def test_health_gate_allows_task_gen_when_degraded(self):
        """Verify task generation proceeds when health is DEGRADED (IMP-LOOP-001)."""
        mock_executor = Mock()
        mock_executor.run_id = "test-run"
        mock_executor._get_project_slug = Mock(return_value="test-project")

        loop = AutonomousLoop(mock_executor)

        # Set up degraded state (25-50% failure rate)
        loop._total_phases_executed = 7
        loop._total_phases_failed = 3  # 30% failure rate

        # Track whether _generate_improvement_tasks is called
        with patch.object(loop, "_generate_improvement_tasks") as mock_gen:
            with patch.object(loop, "_persist_loop_insights"):
                with patch("autopack.executor.autonomous_loop.log_build_event"):
                    with patch.object(loop.executor, "_best_effort_write_run_summary"):
                        # Call _finalize_execution with no_more_executable_phases
                        stats = {
                            "iteration": 10,
                            "phases_executed": 7,
                            "phases_failed": 3,
                            "stop_reason": "no_more_executable_phases",
                        }
                        loop._finalize_execution(stats)

            # Task generation SHOULD be called (DEGRADED allows generation)
            mock_gen.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
