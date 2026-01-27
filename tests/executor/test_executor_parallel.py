"""Tests for parallel phase execution in autonomous loop (IMP-AUTO-002).

Tests the ThreadPoolExecutor-based parallel execution of phases with non-overlapping scopes.
"""

from unittest.mock import Mock, patch

from autopack.executor.autonomous_loop import AutonomousLoop


class TestParallelExecutionSetup:
    """Tests for parallel execution initialization."""

    def test_parallel_execution_disabled_by_default(self):
        """Test that parallel execution is disabled by default."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            # No parallel_phase_execution_enabled set - should default to False
            delattr(mock_settings, "parallel_phase_execution_enabled")

            loop = AutonomousLoop(executor)

            assert loop._parallel_execution_enabled is False

    def test_parallel_execution_enabled_when_configured(self):
        """Test that parallel execution is enabled when configured."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 3

            loop = AutonomousLoop(executor)

            assert loop._parallel_execution_enabled is True
            assert loop._max_parallel_phases == 3


class TestParallelismCheckerInitialization:
    """Tests for parallelism checker initialization."""

    def test_initialize_parallelism_checker_when_disabled(self):
        """Test that parallelism checker is not initialized when disabled."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = False

            loop = AutonomousLoop(executor)
            loop._initialize_parallelism_checker()

            assert loop._parallelism_checker is None

    def test_initialize_parallelism_checker_with_intention_anchor(self):
        """Test parallelism checker initialization with intention anchor."""
        from datetime import datetime, timezone

        from autopack.intention_anchor.v2 import (
            IntentionAnchorV2,
            ParallelismIsolationIntention,
            PivotIntentions,
        )

        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"
        executor._intention_anchor_v2 = IntentionAnchorV2(
            format_version="v2",
            project_id="test",
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(
                parallelism_isolation=ParallelismIsolationIntention(
                    allowed=True,
                    isolation_model="four_layer",
                    max_concurrent_runs=3,
                )
            ),
        )

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 2

            loop = AutonomousLoop(executor)
            loop._initialize_parallelism_checker()

            assert loop._parallelism_checker is not None
            assert loop._parallelism_checker.policy_gate is not None


class TestGetQueuedPhasesForParallelCheck:
    """Tests for getting queued phases for parallel execution check."""

    def test_get_queued_phases_filters_status(self):
        """Test that only QUEUED phases are returned."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 2

            loop = AutonomousLoop(executor)

            run_data = {
                "phases": [
                    {"phase_id": "p1", "status": "QUEUED"},
                    {"phase_id": "p2", "status": "IN_PROGRESS"},
                    {"phase_id": "p3", "status": "QUEUED"},
                    {"phase_id": "p4", "status": "COMPLETED"},
                ]
            }

            queued = loop._get_queued_phases_for_parallel_check(run_data)

            assert len(queued) == 2
            assert queued[0]["phase_id"] == "p1"
            assert queued[1]["phase_id"] == "p3"


class TestExecutePhasesParallel:
    """Tests for parallel phase execution."""

    def test_single_phase_executes_directly(self):
        """Test that single phase executes directly without ThreadPoolExecutor."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"
        executor.execute_phase = Mock(return_value=(True, "COMPLETED"))

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 2

            loop = AutonomousLoop(executor)

            phases = [{"phase_id": "p1", "scope": {"paths": ["src/a/"]}}]

            results = loop._execute_phases_parallel(phases, {"p1": {}})

            assert len(results) == 1
            phase, success, status = results[0]
            assert phase["phase_id"] == "p1"
            assert success is True
            assert status == "COMPLETED"

    def test_multiple_phases_execute_in_parallel(self):
        """Test that multiple phases execute using ThreadPoolExecutor."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"
        executor.execute_phase = Mock(return_value=(True, "COMPLETED"))

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 2

            loop = AutonomousLoop(executor)

            phases = [
                {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
                {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
            ]

            results = loop._execute_phases_parallel(phases, {"p1": {}, "p2": {}})

            assert len(results) == 2
            assert loop._parallel_phases_executed == 2

            # Verify both phases completed
            phase_ids = {r[0]["phase_id"] for r in results}
            assert phase_ids == {"p1", "p2"}


class TestTryParallelExecution:
    """Tests for attempting parallel execution."""

    def test_try_parallel_returns_none_when_disabled(self):
        """Test that try_parallel returns None when disabled."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = False

            loop = AutonomousLoop(executor)

            run_data = {"phases": []}
            next_phase = {"phase_id": "p1"}

            result = loop._try_parallel_execution(run_data, next_phase)

            assert result is None

    def test_try_parallel_returns_none_when_not_enough_phases(self):
        """Test that try_parallel returns None when fewer than 2 queued phases."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 2

            loop = AutonomousLoop(executor)
            loop._parallelism_checker = Mock()

            run_data = {
                "phases": [
                    {"phase_id": "p1", "status": "QUEUED"},
                ]
            }
            next_phase = {"phase_id": "p1", "status": "QUEUED"}

            result = loop._try_parallel_execution(run_data, next_phase)

            assert result is None


class TestLoopStats:
    """Tests for loop statistics including parallel execution stats."""

    def test_get_loop_stats_includes_parallel_stats(self):
        """Test that loop stats include parallel execution statistics."""
        executor = Mock()
        executor.workspace = "/test"
        executor.run_id = "test-run"

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.circuit_breaker_enabled = False
            mock_settings.context_ceiling_tokens = 50000
            mock_settings.parallel_phase_execution_enabled = True
            mock_settings.max_parallel_phases = 3

            loop = AutonomousLoop(executor)
            loop._parallel_phases_executed = 4
            loop._parallel_phases_skipped = 2

            stats = loop.get_loop_stats()

            assert "parallel_execution" in stats
            assert stats["parallel_execution"]["enabled"] is True
            assert stats["parallel_execution"]["max_parallel_phases"] == 3
            assert stats["parallel_execution"]["parallel_phases_executed"] == 4
            assert stats["parallel_execution"]["parallel_phases_skipped"] == 2
