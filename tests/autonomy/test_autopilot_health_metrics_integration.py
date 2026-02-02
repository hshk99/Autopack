"""
Integration tests for autopilot health metrics with AutopilotController.

IMP-SEG-001: Tests that metrics are collected during autopilot sessions.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from autopack.autonomy.autopilot import AutopilotController
from autopack.autonomy.models import AutopilotSessionV1
from autopack.intention_anchor.v2 import IntentionAnchorV2
from autopack.telemetry.autopilot_metrics import SessionOutcome


class TestAutopilotMetricsIntegration:
    """Integration tests for autopilot health metrics collection."""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace for testing."""
        workspace = tmp_path / "test_workspace"
        workspace.mkdir()
        (workspace / ".github").mkdir()
        (workspace / "src").mkdir()
        return workspace

    @pytest.fixture
    def autopilot_controller(self, temp_workspace):
        """Create an autopilot controller for testing."""
        return AutopilotController(
            workspace_root=temp_workspace,
            project_id="test-project",
            run_id="test-run-123",
            enabled=True,
        )

    @pytest.fixture
    def sample_anchor(self):
        """Create a sample intention anchor."""
        anchor = MagicMock(spec=IntentionAnchorV2)
        anchor.raw_input_digest = "anchor-123"
        return anchor

    def test_health_collector_initialized(self, autopilot_controller):
        """Test that health collector is initialized."""
        assert autopilot_controller._health_collector is not None
        assert autopilot_controller._last_cb_state_open is False

    def test_circuit_breaker_metrics_recorded(self, autopilot_controller):
        """Test that circuit breaker checks are recorded."""
        # Simulate executor context with circuit breaker
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.is_available.return_value = True
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.95
        executor_ctx.circuit_breaker.total_checks = 0
        executor_ctx.circuit_breaker.checks_passed = 0

        autopilot_controller.executor_ctx = executor_ctx

        # Check circuit breaker health
        result = autopilot_controller._check_circuit_breaker_health()
        assert result is True

        # Verify metrics were recorded
        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.circuit_breaker.total_checks == 1
        assert metrics.circuit_breaker.checks_passed == 1
        assert metrics.circuit_breaker.current_state == "closed"

    def test_circuit_breaker_blocked_recorded(self, autopilot_controller):
        """Test that circuit breaker blocking is recorded."""
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.is_available.return_value = False
        executor_ctx.circuit_breaker.state.value = "open"
        executor_ctx.circuit_breaker.health_score = 0.0
        executor_ctx.circuit_breaker.total_checks = 0
        executor_ctx.circuit_breaker.checks_passed = 0

        autopilot_controller.executor_ctx = executor_ctx

        # Check circuit breaker health
        result = autopilot_controller._check_circuit_breaker_health()
        assert result is False

        # Verify metrics were recorded
        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.circuit_breaker.total_checks == 1
        assert metrics.circuit_breaker.checks_failed == 1

    def test_health_transition_recorded(self, autopilot_controller):
        """Test that health transitions are recorded."""
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        # Record a transition
        autopilot_controller.on_health_transition(
            FeedbackLoopHealth.HEALTHY,
            FeedbackLoopHealth.DEGRADED,
        )

        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.health_transitions.total_transitions == 1
        assert metrics.health_transitions.transitions_to_degraded == 1

    def test_task_pause_resume_recorded(self, autopilot_controller):
        """Test that task pause/resume is recorded."""
        autopilot_controller._pause_task_generation("test reason")

        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.health_transitions.task_generation_paused_count == 1
        assert "test reason" in metrics.health_transitions.pause_reasons

        # Now trigger resume
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

        autopilot_controller.on_health_transition(
            FeedbackLoopHealth.ATTENTION_REQUIRED,
            FeedbackLoopHealth.HEALTHY,
        )

        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.health_transitions.task_generation_resumed_count == 1

    def test_session_metrics_recorded_on_completion(self, autopilot_controller):
        """Test that session metrics are recorded when session completes."""
        # Set up session
        autopilot_controller._health_collector.start_session("session-123")

        # Create executor context mock
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.9
        executor_ctx.circuit_breaker.total_checks = 1
        executor_ctx.circuit_breaker.checks_passed = 1
        executor_ctx.get_budget_remaining.return_value = 0.8

        autopilot_controller.executor_ctx = executor_ctx

        # Create a session
        autopilot_controller.session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="session-123",
            started_at=datetime.now(timezone.utc),
            status="completed",
            anchor_id="test-anchor-id",
            gap_report_id="test-gap-report-id",
            plan_proposal_id="test-plan-proposal-id",
        )

        # Record completion
        autopilot_controller._record_session_metrics(SessionOutcome.COMPLETED)

        # Verify session was recorded
        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.total_sessions == 1
        assert metrics.sessions_completed == 1

        history = autopilot_controller._health_collector.get_session_history()
        assert len(history) == 1
        assert history[0].session_id == "session-123"

    def test_session_blocked_outcomes_recorded(self, autopilot_controller):
        """Test that all blocked session outcomes are recorded."""
        outcomes_to_test = [
            SessionOutcome.BLOCKED_APPROVAL,
            SessionOutcome.BLOCKED_CIRCUIT_BREAKER,
            SessionOutcome.BLOCKED_RESEARCH,
            SessionOutcome.FAILED,
        ]

        # Map SessionOutcome to valid AutopilotSessionV1.status values
        # AutopilotSessionV1.status only accepts: running, completed, blocked_approval_required, failed, aborted
        outcome_to_status = {
            SessionOutcome.BLOCKED_APPROVAL: "blocked_approval_required",
            SessionOutcome.BLOCKED_CIRCUIT_BREAKER: "aborted",
            SessionOutcome.BLOCKED_RESEARCH: "aborted",
            SessionOutcome.FAILED: "failed",
        }

        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.9
        executor_ctx.circuit_breaker.total_checks = 0
        executor_ctx.circuit_breaker.checks_passed = 0
        executor_ctx.get_budget_remaining.return_value = 0.5

        autopilot_controller.executor_ctx = executor_ctx

        for outcome in outcomes_to_test:
            autopilot_controller._health_collector.start_session(f"session-{outcome.value}")

            autopilot_controller.session = AutopilotSessionV1(
                format_version="v1",
                project_id="test-project",
                run_id="test-run",
                session_id=f"session-{outcome.value}",
                started_at=datetime.now(timezone.utc),
                status=outcome_to_status[outcome],
                anchor_id="test-anchor-id",
                gap_report_id="test-gap-report-id",
                plan_proposal_id="test-plan-proposal-id",
            )

            autopilot_controller._record_session_metrics(outcome)

        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.total_sessions == 4
        assert metrics.sessions_blocked_approval == 1
        assert metrics.sessions_blocked_circuit_breaker == 1
        assert metrics.sessions_blocked_research == 1
        assert metrics.sessions_failed == 1

    def test_health_score_calculation(self, autopilot_controller):
        """Test that overall health score is calculated."""
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.95
        executor_ctx.circuit_breaker.total_checks = 10
        executor_ctx.circuit_breaker.checks_passed = 10
        executor_ctx.get_budget_remaining.return_value = 0.7

        autopilot_controller.executor_ctx = executor_ctx

        # Record some metrics
        for _ in range(10):
            autopilot_controller._check_circuit_breaker_health()

        # Complete a session to trigger health calculation
        autopilot_controller._health_collector.start_session("session-test")
        autopilot_controller.session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="session-test",
            started_at=datetime.now(timezone.utc),
            status="completed",
            anchor_id="test-anchor-id",
            gap_report_id="test-gap-report-id",
            plan_proposal_id="test-plan-proposal-id",
        )
        autopilot_controller._record_session_metrics(SessionOutcome.COMPLETED)

        metrics = autopilot_controller._health_collector.get_metrics()
        assert metrics.overall_health_score > 0.0
        assert metrics.overall_health_score <= 1.0

    def test_prometheus_export_functional(self, autopilot_controller):
        """Test that Prometheus export works."""
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.95
        executor_ctx.circuit_breaker.total_checks = 5
        executor_ctx.circuit_breaker.checks_passed = 5

        autopilot_controller.executor_ctx = executor_ctx

        # Record some metrics
        for _ in range(5):
            autopilot_controller._check_circuit_breaker_health()

        prometheus = autopilot_controller._health_collector.export_to_prometheus()

        assert isinstance(prometheus, dict)
        assert "autopack_autopilot_circuit_breaker_checks_total" in prometheus
        assert prometheus["autopack_autopilot_circuit_breaker_checks_total"] == 5

    def test_metrics_persistence(self, autopilot_controller, tmp_path):
        """Test that metrics can be saved and loaded from file."""
        executor_ctx = MagicMock()
        executor_ctx.circuit_breaker.state.value = "closed"
        executor_ctx.circuit_breaker.health_score = 0.95
        executor_ctx.circuit_breaker.total_checks = 1
        executor_ctx.circuit_breaker.checks_passed = 1
        executor_ctx.get_budget_remaining.return_value = 0.8

        autopilot_controller.executor_ctx = executor_ctx

        # Record metrics
        autopilot_controller._health_collector.start_session("session-123")
        autopilot_controller.session = AutopilotSessionV1(
            format_version="v1",
            project_id="test-project",
            run_id="test-run",
            session_id="session-123",
            started_at=datetime.now(timezone.utc),
            status="completed",
            anchor_id="test-anchor-id",
            gap_report_id="test-gap-report-id",
            plan_proposal_id="test-plan-proposal-id",
        )
        autopilot_controller._record_session_metrics(SessionOutcome.COMPLETED)

        # Save to file
        metrics_file = tmp_path / "metrics.json"
        autopilot_controller._health_collector.save_to_file(str(metrics_file))

        assert metrics_file.exists()

        # Verify file contents
        import json

        with open(metrics_file) as f:
            data = json.load(f)

        assert data["format_version"] == "v1"
        assert "metrics" in data
        assert data["metrics"]["total_sessions"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
