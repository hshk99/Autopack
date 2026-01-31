"""
Unit tests for autopilot health metrics collection and analysis.

IMP-SEG-001: Tests for AutopilotHealthCollector, dataclasses, metrics
calculation, persistence, and Prometheus export.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pytest

from autopack.telemetry.autopilot_metrics import (
    AutopilotHealthCollector,
    AutopilotHealthMetrics,
    BudgetEnforcementMetrics,
    CircuitBreakerMetrics,
    HealthTransitionMetrics,
    ResearchCycleSummary,
    SessionHealthSnapshot,
    HealthGateType,
    SessionOutcome,
    ResearchDecisionType,
    get_global_collector,
)


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestCircuitBreakerMetrics:
    """Tests for CircuitBreakerMetrics dataclass."""

    def test_defaults(self):
        """Test default values for circuit breaker metrics."""
        metrics = CircuitBreakerMetrics()
        assert metrics.total_checks == 0
        assert metrics.checks_passed == 0
        assert metrics.checks_failed == 0
        assert metrics.total_trips == 0
        assert metrics.consecutive_failures == 0
        assert metrics.current_state == "closed"
        assert metrics.last_health_score == 1.0

    def test_to_dict(self):
        """Test serialization to dictionary."""
        metrics = CircuitBreakerMetrics(
            total_checks=10,
            checks_passed=9,
            checks_failed=1,
            current_state="half_open",
            last_health_score=0.8,
        )
        result = metrics.to_dict()
        assert result["total_checks"] == 10
        assert result["checks_passed"] == 9
        assert result["current_state"] == "half_open"
        assert result["last_health_score"] == 0.8


class TestBudgetEnforcementMetrics:
    """Tests for BudgetEnforcementMetrics dataclass."""

    def test_defaults(self):
        """Test default values."""
        metrics = BudgetEnforcementMetrics()
        assert metrics.total_checks == 0
        assert metrics.budget_remaining_current == 1.0
        assert metrics.budget_remaining_min == 1.0
        assert metrics.budget_remaining_max == 1.0

    def test_to_dict(self):
        """Test serialization."""
        metrics = BudgetEnforcementMetrics(
            total_checks=5,
            checks_passed=4,
            budget_remaining_current=0.65,
            warning_count=1,
        )
        result = metrics.to_dict()
        assert result["total_checks"] == 5
        assert result["budget_remaining_current"] == 0.65
        assert result["warning_count"] == 1


class TestHealthTransitionMetrics:
    """Tests for HealthTransitionMetrics dataclass."""

    def test_defaults(self):
        """Test default values."""
        metrics = HealthTransitionMetrics()
        assert metrics.total_transitions == 0
        assert metrics.current_status == "healthy"
        assert metrics.task_generation_paused_count == 0
        assert len(metrics.pause_reasons) == 0

    def test_to_dict(self):
        """Test serialization."""
        metrics = HealthTransitionMetrics(
            total_transitions=3,
            current_status="degraded",
            task_generation_paused_count=1,
            pause_reasons={"health_degraded": 1},
        )
        result = metrics.to_dict()
        assert result["total_transitions"] == 3
        assert result["current_status"] == "degraded"
        assert result["pause_reasons"]["health_degraded"] == 1


class TestResearchCycleSummary:
    """Tests for ResearchCycleSummary dataclass."""

    def test_defaults(self):
        """Test default values."""
        summary = ResearchCycleSummary()
        assert summary.total_cycles_triggered == 0
        assert summary.successful_cycles == 0
        assert summary.failed_cycles == 0

    def test_success_rate_no_cycles(self):
        """Test success rate calculation with no cycles."""
        summary = ResearchCycleSummary()
        assert summary.success_rate == 0.0

    def test_success_rate_with_cycles(self):
        """Test success rate calculation with cycles."""
        summary = ResearchCycleSummary(
            successful_cycles=3,
            failed_cycles=1,
        )
        assert summary.success_rate == 0.75

    def test_to_dict_includes_success_rate(self):
        """Test that to_dict includes calculated success rate."""
        summary = ResearchCycleSummary(
            total_cycles_triggered=2,
            successful_cycles=1,
            failed_cycles=1,
        )
        result = summary.to_dict()
        assert result["success_rate"] == 0.5


class TestSessionHealthSnapshot:
    """Tests for SessionHealthSnapshot dataclass."""

    def test_to_dict(self):
        """Test serialization converts enum to string."""
        snapshot = SessionHealthSnapshot(
            session_id="session-123",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.65,
            health_status="healthy",
            health_gates_checked=10,
            health_gates_blocked=0,
            research_cycles_executed=1,
            actions_executed=5,
            actions_successful=5,
            actions_failed=0,
        )
        result = snapshot.to_dict()
        assert result["session_id"] == "session-123"
        assert result["outcome"] == "completed"  # Enum converted to string
        assert result["duration_seconds"] == 300.0


class TestAutopilotHealthMetrics:
    """Tests for AutopilotHealthMetrics dataclass."""

    def test_defaults(self):
        """Test default initialization."""
        metrics = AutopilotHealthMetrics()
        assert metrics.total_sessions == 0
        assert metrics.overall_health_score == 1.0
        assert metrics.circuit_breaker is not None
        assert metrics.budget_enforcement is not None
        assert metrics.health_transitions is not None
        assert metrics.research_cycles is not None

    def test_to_dict(self):
        """Test serialization includes all components."""
        metrics = AutopilotHealthMetrics(
            total_sessions=5,
            sessions_completed=4,
            overall_health_score=0.85,
        )
        result = metrics.to_dict()
        assert "circuit_breaker" in result
        assert "budget_enforcement" in result
        assert "health_transitions" in result
        assert "research_cycles" in result
        assert result["total_sessions"] == 5
        assert result["overall_health_score"] == 0.85


# ============================================================================
# COLLECTOR TESTS
# ============================================================================

class TestAutopilotHealthCollector:
    """Tests for AutopilotHealthCollector class."""

    def test_initialization(self):
        """Test collector initialization."""
        collector = AutopilotHealthCollector()
        assert collector._current_session_id is None
        assert collector._session_start_time is None
        assert len(collector.get_session_history()) == 0
        assert len(collector.get_health_timeline()) == 0

    def test_record_circuit_breaker_check_passed(self):
        """Test recording a passing circuit breaker check."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)

        metrics = collector.get_metrics()
        assert metrics.circuit_breaker.total_checks == 1
        assert metrics.circuit_breaker.checks_passed == 1
        assert metrics.circuit_breaker.checks_failed == 0
        assert metrics.circuit_breaker.current_state == "closed"
        assert metrics.circuit_breaker.last_health_score == 0.95

    def test_record_circuit_breaker_check_failed(self):
        """Test recording a failing circuit breaker check."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("open", False, 0.0)

        metrics = collector.get_metrics()
        assert metrics.circuit_breaker.total_checks == 1
        assert metrics.circuit_breaker.checks_passed == 0
        assert metrics.circuit_breaker.checks_failed == 1

    def test_record_circuit_breaker_trip(self):
        """Test recording a circuit breaker trip."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_trip()
        collector.record_circuit_breaker_trip()

        metrics = collector.get_metrics()
        assert metrics.circuit_breaker.total_trips == 2

    def test_record_budget_check_passed(self):
        """Test recording a passing budget check."""
        collector = AutopilotHealthCollector()
        collector.record_budget_check(True, 0.75, False)

        metrics = collector.get_metrics()
        assert metrics.budget_enforcement.total_checks == 1
        assert metrics.budget_enforcement.checks_passed == 1
        assert metrics.budget_enforcement.checks_blocked == 0
        assert metrics.budget_enforcement.budget_remaining_current == 0.75

    def test_record_budget_check_tracks_min_max(self):
        """Test that budget check tracks min and max values."""
        collector = AutopilotHealthCollector()
        collector.record_budget_check(True, 0.8, False)
        collector.record_budget_check(True, 0.6, False)
        collector.record_budget_check(True, 0.9, False)

        metrics = collector.get_metrics()
        assert metrics.budget_enforcement.budget_remaining_min == 0.6
        assert metrics.budget_enforcement.budget_remaining_max == 0.9
        assert metrics.budget_enforcement.budget_remaining_current == 0.9

    def test_record_budget_warning(self):
        """Test recording budget warning (below 20% threshold)."""
        collector = AutopilotHealthCollector()
        collector.record_budget_check(False, 0.15, True)

        metrics = collector.get_metrics()
        assert metrics.budget_enforcement.warning_count == 1

    def test_record_health_transition_healthy(self):
        """Test recording health transition to healthy."""
        collector = AutopilotHealthCollector()
        collector.record_health_transition("degraded", "healthy")

        metrics = collector.get_metrics()
        assert metrics.health_transitions.total_transitions == 1
        assert metrics.health_transitions.transitions_to_healthy == 1
        assert metrics.health_transitions.current_status == "healthy"

    def test_record_health_transition_degraded(self):
        """Test recording health transition to degraded."""
        collector = AutopilotHealthCollector()
        collector.record_health_transition("healthy", "degraded")

        metrics = collector.get_metrics()
        assert metrics.health_transitions.transitions_to_degraded == 1
        assert metrics.health_transitions.current_status == "degraded"

    def test_record_health_transition_attention_required(self):
        """Test recording health transition to attention_required."""
        collector = AutopilotHealthCollector()
        collector.record_health_transition("healthy", "attention_required")

        metrics = collector.get_metrics()
        assert metrics.health_transitions.transitions_to_attention_required == 1

    def test_record_task_pause(self):
        """Test recording task generation pause."""
        collector = AutopilotHealthCollector()
        collector.record_task_pause("health_degraded")
        collector.record_task_pause("budget_low")
        collector.record_task_pause("health_degraded")

        metrics = collector.get_metrics()
        assert metrics.health_transitions.task_generation_paused_count == 3
        assert metrics.health_transitions.pause_reasons["health_degraded"] == 2
        assert metrics.health_transitions.pause_reasons["budget_low"] == 1

    def test_record_task_resume(self):
        """Test recording task generation resume."""
        collector = AutopilotHealthCollector()
        collector.record_task_pause("health_degraded")
        collector.record_task_resume()
        collector.record_task_resume()

        metrics = collector.get_metrics()
        assert metrics.health_transitions.task_generation_resumed_count == 2

    def test_record_research_cycle_success(self):
        """Test recording a successful research cycle."""
        collector = AutopilotHealthCollector()
        collector.record_research_cycle(
            outcome="success",
            triggers_detected=2,
            triggers_executed=2,
            decision=ResearchDecisionType.PROCEED.value,
            gaps_addressed=1,
            gaps_remaining=0,
            execution_time_ms=500,
        )

        metrics = collector.get_metrics()
        assert metrics.research_cycles.total_cycles_triggered == 1
        assert metrics.research_cycles.successful_cycles == 1
        assert metrics.research_cycles.failed_cycles == 0
        assert metrics.research_cycles.total_triggers_detected == 2
        assert metrics.research_cycles.total_triggers_executed == 2
        assert metrics.research_cycles.decision_proceed == 1
        assert metrics.research_cycles.total_gaps_addressed == 1

    def test_record_research_cycle_failed(self):
        """Test recording a failed research cycle."""
        collector = AutopilotHealthCollector()
        collector.record_research_cycle(
            outcome="failed",
            triggers_detected=3,
            triggers_executed=0,
            decision=ResearchDecisionType.SKIP.value,
            gaps_addressed=0,
            gaps_remaining=3,
            execution_time_ms=1000,
        )

        metrics = collector.get_metrics()
        assert metrics.research_cycles.failed_cycles == 1
        assert metrics.research_cycles.decision_skip == 1

    def test_record_research_cycle_decisions(self):
        """Test recording all research decision types."""
        collector = AutopilotHealthCollector()

        decisions = [
            (ResearchDecisionType.PROCEED.value, "proceed"),
            (ResearchDecisionType.PAUSE_FOR_RESEARCH.value, "pause_for_research"),
            (ResearchDecisionType.ADJUST_PLAN.value, "adjust_plan"),
            (ResearchDecisionType.BLOCK.value, "block"),
            (ResearchDecisionType.SKIP.value, "skip"),
        ]

        for decision, attr_name in decisions:
            collector.record_research_cycle(
                outcome="success",
                triggers_detected=1,
                triggers_executed=1,
                decision=decision,
                gaps_addressed=0,
                gaps_remaining=0,
                execution_time_ms=100,
            )

        metrics = collector.get_metrics()
        assert metrics.research_cycles.decision_proceed == 1
        assert metrics.research_cycles.decision_pause_for_research == 1
        assert metrics.research_cycles.decision_adjust_plan == 1
        assert metrics.research_cycles.decision_block == 1
        assert metrics.research_cycles.decision_skip == 1

    def test_start_and_end_session(self):
        """Test session lifecycle tracking."""
        collector = AutopilotHealthCollector()
        collector.start_session("session-123")

        assert collector._current_session_id == "session-123"
        assert collector._session_start_time is not None

        snapshot = SessionHealthSnapshot(
            session_id="session-123",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.65,
            health_status="healthy",
            health_gates_checked=10,
            health_gates_blocked=0,
            research_cycles_executed=1,
            actions_executed=5,
            actions_successful=5,
            actions_failed=0,
        )

        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        assert collector._current_session_id is None
        assert collector._session_start_time is None
        assert collector.get_metrics().total_sessions == 1
        assert collector.get_metrics().sessions_completed == 1

    def test_session_history_limit(self):
        """Test that session history is limited to 100 sessions."""
        collector = AutopilotHealthCollector()

        # Add 110 sessions
        for i in range(110):
            collector.start_session(f"session-{i}")
            snapshot = SessionHealthSnapshot(
                session_id=f"session-{i}",
                outcome=SessionOutcome.COMPLETED,
                started_at="2026-01-31T10:00:00Z",
                completed_at="2026-01-31T10:05:00Z",
                duration_seconds=300.0,
                circuit_breaker_state="closed",
                circuit_breaker_health_score=0.95,
                budget_remaining=0.65,
                health_status="healthy",
                health_gates_checked=10,
                health_gates_blocked=0,
                research_cycles_executed=0,
                actions_executed=0,
                actions_successful=0,
                actions_failed=0,
            )
            collector.end_session(SessionOutcome.COMPLETED, snapshot)

        # Only last 100 should be kept
        history = collector.get_session_history()
        assert len(history) == 100
        assert history[0].session_id == "session-10"  # First 10 sessions removed

    def test_get_metrics_returns_current_state(self):
        """Test that get_metrics returns current aggregated state."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.9)
        collector.record_budget_check(True, 0.7, False)
        collector.record_health_transition("healthy", "healthy")

        metrics = collector.get_metrics()

        assert metrics.circuit_breaker.total_checks == 1
        assert metrics.budget_enforcement.total_checks == 1
        assert metrics.health_transitions.total_transitions == 1

    def test_session_outcome_tracking(self):
        """Test tracking of all session outcome types."""
        collector = AutopilotHealthCollector()

        outcomes = [
            SessionOutcome.COMPLETED,
            SessionOutcome.BLOCKED_APPROVAL,
            SessionOutcome.BLOCKED_CIRCUIT_BREAKER,
            SessionOutcome.BLOCKED_RESEARCH,
            SessionOutcome.FAILED,
        ]

        for i, outcome in enumerate(outcomes):
            collector.start_session(f"session-{i}")
            snapshot = SessionHealthSnapshot(
                session_id=f"session-{i}",
                outcome=outcome,
                started_at="2026-01-31T10:00:00Z",
                completed_at="2026-01-31T10:05:00Z",
                duration_seconds=300.0,
                circuit_breaker_state="closed",
                circuit_breaker_health_score=0.95,
                budget_remaining=0.65,
                health_status="healthy",
                health_gates_checked=10,
                health_gates_blocked=0,
                research_cycles_executed=0,
                actions_executed=0,
                actions_successful=0,
                actions_failed=0,
            )
            collector.end_session(outcome, snapshot)

        metrics = collector.get_metrics()
        assert metrics.total_sessions == 5
        assert metrics.sessions_completed == 1
        assert metrics.sessions_blocked_approval == 1
        assert metrics.sessions_blocked_circuit_breaker == 1
        assert metrics.sessions_blocked_research == 1
        assert metrics.sessions_failed == 1


# ============================================================================
# ANALYSIS AND CALCULATION TESTS
# ============================================================================

class TestHealthScoreCalculation:
    """Tests for health score calculation."""

    def test_overall_health_score_calculation(self):
        """Test overall health score calculation."""
        collector = AutopilotHealthCollector()

        # Set up some metrics
        for _ in range(10):
            collector.record_circuit_breaker_check("closed", True, 0.95)
        for _ in range(10):
            collector.record_budget_check(True, 0.7, False)
        collector.record_health_transition("healthy", "healthy")

        # End a successful session to trigger health score calculation
        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.7,
            health_status="healthy",
            health_gates_checked=20,
            health_gates_blocked=0,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        metrics = collector.get_metrics()
        # Should be relatively high (successful checks, healthy status, completed session)
        assert metrics.overall_health_score > 0.7

    def test_critical_issues_identification(self):
        """Test identification of critical issues."""
        collector = AutopilotHealthCollector()

        # Set up critical circuit breaker state
        collector.record_circuit_breaker_check("open", False, 0.0)

        # Trigger health calculation
        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.BLOCKED_CIRCUIT_BREAKER,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="open",
            circuit_breaker_health_score=0.0,
            budget_remaining=0.5,
            health_status="healthy",
            health_gates_checked=1,
            health_gates_blocked=1,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.BLOCKED_CIRCUIT_BREAKER, snapshot)

        metrics = collector.get_metrics()
        assert len(metrics.critical_issues) > 0
        assert any("Circuit breaker is OPEN" in issue for issue in metrics.critical_issues)

    def test_warnings_identification(self):
        """Test identification of warnings."""
        collector = AutopilotHealthCollector()

        # Record multiple circuit breaker trips
        for _ in range(5):
            collector.record_circuit_breaker_trip()

        # Trigger calculation
        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.5,
            budget_remaining=0.5,
            health_status="healthy",
            health_gates_checked=0,
            health_gates_blocked=0,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        metrics = collector.get_metrics()
        assert len(metrics.warnings) > 0


# ============================================================================
# EXPORT TESTS
# ============================================================================

class TestPrometheusExport:
    """Tests for Prometheus metrics export."""

    def test_prometheus_export_format(self):
        """Test Prometheus export returns valid dictionary."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_budget_check(True, 0.7, False)

        prometheus = collector.export_to_prometheus()

        assert isinstance(prometheus, dict)
        assert "autopack_autopilot_circuit_breaker_checks_total" in prometheus
        assert "autopack_autopilot_budget_remaining" in prometheus
        assert "autopack_autopilot_health_score" in prometheus

    def test_prometheus_metric_values(self):
        """Test Prometheus metrics have correct values."""
        collector = AutopilotHealthCollector()

        for _ in range(5):
            collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_circuit_breaker_trip()

        prometheus = collector.export_to_prometheus()

        assert prometheus["autopack_autopilot_circuit_breaker_checks_total"] == 5
        assert prometheus["autopack_autopilot_circuit_breaker_trips_total"] == 1

    def test_prometheus_all_expected_metrics(self):
        """Test Prometheus export includes all expected metrics."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.9)
        collector.record_budget_check(True, 0.7, False)
        collector.record_health_transition("healthy", "healthy")
        collector.record_research_cycle(
            outcome="success",
            triggers_detected=1,
            triggers_executed=1,
            decision="proceed",
            gaps_addressed=1,
            gaps_remaining=0,
            execution_time_ms=100,
        )

        prometheus = collector.export_to_prometheus()

        expected_metrics = [
            "autopack_autopilot_circuit_breaker_checks_total",
            "autopack_autopilot_circuit_breaker_trips_total",
            "autopack_autopilot_circuit_breaker_health_score",
            "autopack_autopilot_budget_checks_total",
            "autopack_autopilot_budget_remaining",
            "autopack_autopilot_budget_warnings_total",
            "autopack_autopilot_health_transitions_total",
            "autopack_autopilot_task_pauses_total",
            "autopack_autopilot_task_resumes_total",
            "autopack_autopilot_research_cycles_triggered_total",
            "autopack_autopilot_research_cycles_successful_total",
            "autopack_autopilot_research_cycles_failed_total",
            "autopack_autopilot_research_cycles_success_rate",
            "autopack_autopilot_sessions_total",
            "autopack_autopilot_sessions_completed",
            "autopack_autopilot_sessions_blocked_approval",
            "autopack_autopilot_sessions_blocked_circuit_breaker",
            "autopack_autopilot_sessions_blocked_research",
            "autopack_autopilot_sessions_failed",
            "autopack_autopilot_health_score",
        ]

        for metric in expected_metrics:
            assert metric in prometheus


# ============================================================================
# FILE PERSISTENCE TESTS
# ============================================================================

class TestFilePersistence:
    """Tests for file persistence of metrics."""

    def test_save_to_file(self):
        """Test saving metrics to a JSON file."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_budget_check(True, 0.7, False)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "metrics.json"
            collector.save_to_file(str(file_path))

            assert file_path.exists()

            with open(file_path, 'r') as f:
                data = json.load(f)

            assert data["format_version"] == "v1"
            assert data["project_id"] == "autopack"
            assert "metrics" in data
            assert "prometheus" in data

    def test_save_file_structure(self):
        """Test saved file has correct structure."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "metrics.json"
            collector.save_to_file(str(file_path))

            with open(file_path, 'r') as f:
                data = json.load(f)

            assert "format_version" in data
            assert "project_id" in data
            assert "collection_start" in data
            assert "collection_end" in data
            assert "metrics" in data
            assert "prometheus" in data
            assert "session_history" in data
            assert "health_timeline" in data

            # Check metrics structure
            metrics = data["metrics"]
            assert "circuit_breaker" in metrics
            assert "budget_enforcement" in metrics
            assert "health_transitions" in metrics
            assert "research_cycles" in metrics

    def test_save_file_creates_directories(self):
        """Test that save_to_file creates parent directories."""
        collector = AutopilotHealthCollector()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "subdir" / "nested" / "metrics.json"
            collector.save_to_file(str(file_path))

            assert file_path.exists()
            assert file_path.parent.exists()

    def test_load_from_file(self):
        """Test loading metrics from a JSON file."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "metrics.json"
            collector.save_to_file(str(file_path))

            # Load should not error
            collector2 = AutopilotHealthCollector()
            collector2.load_from_file(str(file_path))
            # Currently load_from_file is a placeholder for analysis


# ============================================================================
# DASHBOARD TESTS
# ============================================================================

class TestDashboardSummary:
    """Tests for dashboard summary generation."""

    def test_dashboard_summary_structure(self):
        """Test dashboard summary has expected structure."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_budget_check(True, 0.7, False)
        collector.record_health_transition("healthy", "healthy")

        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.7,
            health_status="healthy",
            health_gates_checked=1,
            health_gates_blocked=0,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        summary = collector.get_dashboard_summary()

        assert "overview" in summary
        assert "health_gates" in summary
        assert "research_cycles" in summary
        assert "session_outcomes" in summary
        assert "recent_sessions" in summary
        assert "health_timeline" in summary

    def test_dashboard_overview_metrics(self):
        """Test dashboard overview includes expected metrics."""
        collector = AutopilotHealthCollector()
        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.7,
            health_status="healthy",
            health_gates_checked=0,
            health_gates_blocked=0,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        summary = collector.get_dashboard_summary()

        overview = summary["overview"]
        assert "overall_health_score" in overview
        assert "critical_issues" in overview
        assert "warnings" in overview
        assert "total_sessions" in overview
        assert overview["total_sessions"] == 1

    def test_dashboard_health_gates(self):
        """Test dashboard health gates section."""
        collector = AutopilotHealthCollector()
        collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_budget_check(True, 0.7, False)
        collector.record_health_transition("healthy", "degraded")

        collector.start_session("session-1")
        snapshot = SessionHealthSnapshot(
            session_id="session-1",
            outcome=SessionOutcome.COMPLETED,
            started_at="2026-01-31T10:00:00Z",
            completed_at="2026-01-31T10:05:00Z",
            duration_seconds=300.0,
            circuit_breaker_state="closed",
            circuit_breaker_health_score=0.95,
            budget_remaining=0.7,
            health_status="degraded",
            health_gates_checked=2,
            health_gates_blocked=0,
            research_cycles_executed=0,
            actions_executed=0,
            actions_successful=0,
            actions_failed=0,
        )
        collector.end_session(SessionOutcome.COMPLETED, snapshot)

        summary = collector.get_dashboard_summary()
        health_gates = summary["health_gates"]

        assert "circuit_breaker" in health_gates
        assert health_gates["circuit_breaker"]["current_state"] == "closed"
        assert health_gates["circuit_breaker"]["health_score"] == 0.95

        assert "budget" in health_gates
        assert health_gates["budget"]["remaining"] == 0.7

        assert "health_transitions" in health_gates
        assert health_gates["health_transitions"]["current_status"] == "degraded"


# ============================================================================
# GLOBAL COLLECTOR TESTS
# ============================================================================

class TestGlobalCollector:
    """Tests for global collector singleton."""

    def test_get_global_collector(self):
        """Test getting the global collector instance."""
        collector1 = get_global_collector()
        collector2 = get_global_collector()

        assert collector1 is collector2  # Same instance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
