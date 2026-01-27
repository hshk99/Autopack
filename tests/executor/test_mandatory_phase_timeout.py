"""
Tests for IMP-SAFETY-004: Mandatory Phase Timeout

Verifies that:
1. time_watchdog is mandatory in ExecutionContext (cannot be None)
2. PhaseRunner requires time_watchdog
3. create_default_time_watchdog() factory returns properly configured watchdog
4. Phase timeout is enforced when watchdog is provided
"""

from unittest.mock import Mock

import pytest

from autopack.executor.phase_orchestrator import (
    ExecutionContext,
    PhaseOrchestrator,
    create_default_time_watchdog,
)
from autopack.executor.phase_runner import PhaseRunner
from autopack.time_watchdog import TimeWatchdog


class TestMandatoryTimeWatchdog:
    """Tests for IMP-SAFETY-004: time_watchdog must be provided."""

    def test_create_default_time_watchdog_returns_watchdog(self):
        """Factory function should return a configured TimeWatchdog."""
        watchdog = create_default_time_watchdog()

        assert watchdog is not None
        assert isinstance(watchdog, TimeWatchdog)
        # Should have default config values
        assert watchdog.max_duration > 0
        assert watchdog.max_phase_duration > 0

    def test_create_default_time_watchdog_uses_config_values(self):
        """Factory should use values from settings."""
        from autopack.config import settings

        watchdog = create_default_time_watchdog()

        expected_run_timeout = settings.run_max_duration_minutes * 60
        expected_phase_timeout = settings.phase_timeout_minutes * 60

        assert watchdog.max_duration == expected_run_timeout
        assert watchdog.max_phase_duration == expected_phase_timeout

    def test_execution_context_with_time_watchdog(self):
        """ExecutionContext should accept time_watchdog."""
        watchdog = create_default_time_watchdog()

        phase = {"phase_id": "test-phase", "description": "Test"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run-123",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        assert context.time_watchdog is watchdog
        assert context.time_watchdog is not None


class TestPhaseRunnerRequiresWatchdog:
    """Tests for PhaseRunner time_watchdog requirement."""

    def test_phase_runner_raises_without_time_watchdog(self):
        """PhaseRunner should raise ValueError if time_watchdog is None."""
        with pytest.raises(ValueError) as exc_info:
            PhaseRunner(
                llm_service=Mock(),
                builder_orchestrator=Mock(),
                auditor_orchestrator=Mock(),
                quality_gate=Mock(),
                patch_flow=Mock(),
                ci_flow=Mock(),
                phase_state_mgr=Mock(),
                time_watchdog=None,  # This should raise
            )

        assert "time_watchdog is required" in str(exc_info.value)
        assert "IMP-SAFETY-004" in str(exc_info.value)

    def test_phase_runner_accepts_time_watchdog(self):
        """PhaseRunner should accept time_watchdog when provided."""
        watchdog = create_default_time_watchdog()

        runner = PhaseRunner(
            llm_service=Mock(),
            builder_orchestrator=Mock(),
            auditor_orchestrator=Mock(),
            quality_gate=Mock(),
            patch_flow=Mock(),
            ci_flow=Mock(),
            phase_state_mgr=Mock(),
            time_watchdog=watchdog,
        )

        assert runner.time_watchdog is watchdog


class TestPhaseTimeoutEnforcement:
    """Tests for phase timeout enforcement with mandatory watchdog."""

    def test_orchestrator_tracks_phase_start(self):
        """PhaseOrchestrator._initialize_phase should track phase start time."""
        watchdog = create_default_time_watchdog()
        watchdog.start()

        phase = {"phase_id": "timeout-test-phase"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        orchestrator = PhaseOrchestrator()
        orchestrator._initialize_phase(context)

        # Phase should be tracked
        assert "timeout-test-phase" in watchdog.phase_timers

    def test_orchestrator_clears_phase_timer_on_success(self):
        """Phase timer should be cleared when phase completes successfully."""
        watchdog = create_default_time_watchdog()
        watchdog.start()
        watchdog.track_phase_start("success-phase")

        phase = {"phase_id": "success-phase", "category": "implementation"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
            mark_phase_complete_in_db=Mock(),
            record_learning_hint=Mock(),
            record_token_efficiency_telemetry=Mock(),
        )

        # Mock a successful result
        mock_result = Mock()
        mock_result.success = True
        mock_result.status = "COMPLETE"

        orchestrator = PhaseOrchestrator()
        orchestrator._handle_success(context, mock_result)

        # Phase timer should be cleared
        assert "success-phase" not in watchdog.phase_timers

    def test_check_phase_timeout_no_timeout(self):
        """_check_phase_timeout should return None when not exceeded."""
        watchdog = TimeWatchdog(
            max_run_wall_clock_sec=7200,
            max_phase_wall_clock_sec=900,  # 15 minutes
        )
        watchdog.start()
        watchdog.track_phase_start("no-timeout-phase")

        phase = {"phase_id": "no-timeout-phase"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        orchestrator = PhaseOrchestrator()
        result = orchestrator._check_phase_timeout(context)

        # Should return None (no timeout)
        assert result is None


class TestTimeWatchdogIntegration:
    """Integration tests for TimeWatchdog with phase orchestration."""

    def test_watchdog_phase_timeout_exceeded(self):
        """TimeWatchdog should detect exceeded phase timeout."""
        import time

        # Create watchdog with very short timeout for testing
        watchdog = TimeWatchdog(
            max_run_wall_clock_sec=7200,
            max_phase_wall_clock_sec=0.1,  # 100ms for testing
        )
        watchdog.start()
        watchdog.track_phase_start("fast-timeout-phase")

        # Wait for timeout to exceed
        time.sleep(0.15)

        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout("fast-timeout-phase", 0.1)

        assert exceeded is True
        assert elapsed >= 0.1

    def test_watchdog_soft_warning_at_50_percent(self):
        """TimeWatchdog should trigger soft warning at 50% of timeout."""
        import time

        # Create watchdog with short timeout for testing
        watchdog = TimeWatchdog(
            max_run_wall_clock_sec=7200,
            max_phase_wall_clock_sec=0.2,  # 200ms
        )
        watchdog.start()
        watchdog.track_phase_start("soft-warning-phase")

        # Wait for 60% of timeout (past 50% warning threshold)
        time.sleep(0.12)

        exceeded, elapsed, soft_warning = watchdog.check_phase_timeout("soft-warning-phase", 0.2)

        # Should not be exceeded but should have soft warning
        assert exceeded is False
        assert soft_warning is True
