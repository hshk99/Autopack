"""
Comprehensive health metrics tracking for the Autopilot system.

IMP-SEG-001: Tracks autopilot health gates, research triggers, and research cycle outcomes.
This module provides observability into:
- Circuit breaker health and state transitions
- Budget enforcement and remaining budget
- Health transitions (feedback loop health)
- Research cycle execution metrics
- Session-level outcomes and diagnostics

Usage:
    from autopack.telemetry.autopilot_metrics import AutopilotHealthCollector

    collector = AutopilotHealthCollector()
    collector.start_session("session-123")
    collector.record_circuit_breaker_check(
        state="closed",
        passed=True,
        health_score=0.95
    )
    collector.end_session(outcome="completed", snapshot={...})

    metrics = collector.get_metrics()
    print(metrics.to_dict())

    prometheus_metrics = collector.export_to_prometheus()
    collector.save_to_file("autopilot_health.json")
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class HealthGateType(str, Enum):
    """Types of health gates that can gate execution."""

    CIRCUIT_BREAKER = "circuit_breaker"
    FEEDBACK_LOOP = "feedback_loop"
    BUDGET_ENFORCEMENT = "budget_enforcement"
    RESEARCH_CYCLE = "research_cycle"


class SessionOutcome(str, Enum):
    """Possible outcomes for an autopilot session."""

    COMPLETED = "completed"
    BLOCKED_APPROVAL = "blocked_approval_required"
    BLOCKED_CIRCUIT_BREAKER = "blocked_circuit_breaker"
    BLOCKED_RESEARCH = "blocked_research"
    FAILED = "failed"
    ABORTED = "aborted"


class ResearchDecisionType(str, Enum):
    """Types of research cycle decisions."""

    PROCEED = "proceed"
    PAUSE_FOR_RESEARCH = "pause_for_research"
    ADJUST_PLAN = "adjust_plan"
    BLOCK = "block"
    SKIP = "skip"


# ============================================================================
# DATACLASSES FOR METRICS
# ============================================================================


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker health gate."""

    total_checks: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    total_trips: int = 0  # Times circuit opened
    consecutive_failures: int = 0
    current_state: str = "closed"  # closed, open, half_open
    last_health_score: float = 1.0
    time_in_current_state_seconds: float = 0.0
    last_failure_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class BudgetEnforcementMetrics:
    """Metrics for budget enforcement health gate."""

    total_checks: int = 0
    checks_passed: int = 0
    checks_blocked: int = 0
    budget_remaining_current: float = 1.0
    budget_remaining_min: float = 1.0
    budget_remaining_max: float = 0.0
    total_budget_used: float = 0.0
    warning_count: int = 0  # Times budget fell below 20% threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class HealthTransitionMetrics:
    """Metrics for feedback loop health transitions."""

    total_transitions: int = 0
    transitions_to_healthy: int = 0
    transitions_to_degraded: int = 0
    transitions_to_attention_required: int = 0
    current_status: str = "healthy"
    task_generation_paused_count: int = 0
    task_generation_resumed_count: int = 0
    total_pause_time_seconds: float = 0.0
    pause_reasons: Dict[str, int] = field(default_factory=dict)
    last_transition_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class ResearchCycleSummary:
    """Metrics for research cycle execution."""

    total_cycles_triggered: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    skipped_budget: int = 0  # Cycles skipped due to budget constraints
    skipped_health: int = 0  # Cycles skipped due to health gates
    skipped_max_cycles: int = 0
    total_triggers_detected: int = 0
    total_triggers_executed: int = 0

    # Decision distribution
    decision_proceed: int = 0
    decision_pause_for_research: int = 0
    decision_adjust_plan: int = 0
    decision_block: int = 0
    decision_skip: int = 0

    # Performance metrics
    total_execution_time_ms: int = 0
    avg_execution_time_ms: int = 0

    # Gap tracking
    total_gaps_addressed: int = 0
    gaps_remaining_last_cycle: int = 0

    last_cycle_time: Optional[str] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate of research cycles."""
        total = self.successful_cycles + self.failed_cycles
        if total == 0:
            return 0.0
        return self.successful_cycles / total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["success_rate"] = self.success_rate
        return result


@dataclass
class SessionHealthSnapshot:
    """Per-session health data snapshot."""

    session_id: str
    outcome: SessionOutcome
    started_at: str  # ISO format
    completed_at: str  # ISO format
    duration_seconds: float

    # Gate states at end of session
    circuit_breaker_state: str
    circuit_breaker_health_score: float
    budget_remaining: float
    health_status: str

    # Counts during session
    health_gates_checked: int
    health_gates_blocked: int
    research_cycles_executed: int
    actions_executed: int
    actions_successful: int
    actions_failed: int

    # Details
    blocking_reason: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["outcome"] = self.outcome.value
        return result


@dataclass
class AutopilotHealthMetrics:
    """Top-level aggregated autopilot health metrics."""

    circuit_breaker: CircuitBreakerMetrics = field(default_factory=CircuitBreakerMetrics)
    budget_enforcement: BudgetEnforcementMetrics = field(default_factory=BudgetEnforcementMetrics)
    health_transitions: HealthTransitionMetrics = field(default_factory=HealthTransitionMetrics)
    research_cycles: ResearchCycleSummary = field(default_factory=ResearchCycleSummary)

    # Aggregated session metrics
    total_sessions: int = 0
    sessions_completed: int = 0
    sessions_blocked_approval: int = 0
    sessions_blocked_circuit_breaker: int = 0
    sessions_blocked_research: int = 0
    sessions_failed: int = 0

    # Overall health
    overall_health_score: float = 1.0
    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "circuit_breaker": self.circuit_breaker.to_dict(),
            "budget_enforcement": self.budget_enforcement.to_dict(),
            "health_transitions": self.health_transitions.to_dict(),
            "research_cycles": self.research_cycles.to_dict(),
            "total_sessions": self.total_sessions,
            "sessions_completed": self.sessions_completed,
            "sessions_blocked_approval": self.sessions_blocked_approval,
            "sessions_blocked_circuit_breaker": self.sessions_blocked_circuit_breaker,
            "sessions_blocked_research": self.sessions_blocked_research,
            "sessions_failed": self.sessions_failed,
            "overall_health_score": self.overall_health_score,
            "critical_issues": self.critical_issues,
            "warnings": self.warnings,
        }


# ============================================================================
# MAIN COLLECTOR CLASS
# ============================================================================


class AutopilotHealthCollector:
    """Central metrics collector for autopilot health monitoring.

    Tracks health gates, session outcomes, and research cycle metrics.
    Provides persistence, export, and analysis capabilities.

    Example:
        collector = AutopilotHealthCollector()
        collector.start_session("session-123")

        # Record health gate checks
        collector.record_circuit_breaker_check("closed", True, 0.95)
        collector.record_budget_check(True, 0.65, False)
        collector.record_health_transition("healthy", "healthy")

        # Record session outcome
        collector.end_session("completed", snapshot)

        # Export metrics
        metrics = collector.get_metrics()
        prometheus = collector.export_to_prometheus()
        collector.save_to_file("autopilot_health.json")
    """

    def __init__(self):
        """Initialize the health collector."""
        self._metrics = AutopilotHealthMetrics()
        self._session_history: List[SessionHealthSnapshot] = []
        self._current_session_id: Optional[str] = None
        self._session_start_time: Optional[datetime] = None
        self._health_timeline: List[Dict[str, Any]] = []

    # ========================================================================
    # RECORDING METHODS FOR HEALTH GATES
    # ========================================================================

    def record_circuit_breaker_check(self, state: str, passed: bool, health_score: float) -> None:
        """Record a circuit breaker health gate check.

        Args:
            state: Current circuit breaker state (closed, open, half_open)
            passed: Whether the check passed (True = can proceed)
            health_score: Health score (0.0-1.0)
        """
        cb = self._metrics.circuit_breaker
        cb.total_checks += 1
        cb.current_state = state
        cb.last_health_score = health_score

        if passed:
            cb.checks_passed += 1
        else:
            cb.checks_failed += 1

    def record_circuit_breaker_trip(self) -> None:
        """Record a circuit breaker trip (opening the circuit)."""
        self._metrics.circuit_breaker.total_trips += 1

    def record_budget_check(self, passed: bool, remaining_budget: float, blocked: bool) -> None:
        """Record a budget enforcement check.

        Args:
            passed: Whether the check passed (True = sufficient budget)
            remaining_budget: Current budget remaining (0.0-1.0)
            blocked: Whether this check blocked execution
        """
        be = self._metrics.budget_enforcement
        be.total_checks += 1
        be.budget_remaining_current = remaining_budget

        if be.total_checks == 1:
            # First check - initialize min/max
            be.budget_remaining_min = remaining_budget
            be.budget_remaining_max = remaining_budget
        else:
            # Update min/max
            if remaining_budget < be.budget_remaining_min:
                be.budget_remaining_min = remaining_budget
            if remaining_budget > be.budget_remaining_max:
                be.budget_remaining_max = remaining_budget

        if passed:
            be.checks_passed += 1
        else:
            be.checks_blocked += 1

        if blocked:
            if remaining_budget < 0.2:  # Below 20% threshold
                be.warning_count += 1

    def record_health_transition(self, old_status: str, new_status: str) -> None:
        """Record a health status transition (feedback loop health).

        Args:
            old_status: Previous health status (healthy, degraded, attention_required)
            new_status: New health status
        """
        ht = self._metrics.health_transitions
        ht.total_transitions += 1
        ht.current_status = new_status
        ht.last_transition_time = datetime.now(timezone.utc).isoformat()

        if new_status == "healthy":
            ht.transitions_to_healthy += 1
        elif new_status == "degraded":
            ht.transitions_to_degraded += 1
        elif new_status == "attention_required":
            ht.transitions_to_attention_required += 1

    def record_task_pause(self, reason: str) -> None:
        """Record task generation being paused.

        Args:
            reason: Reason for the pause (e.g., "health_degraded")
        """
        ht = self._metrics.health_transitions
        ht.task_generation_paused_count += 1
        ht.pause_reasons[reason] = ht.pause_reasons.get(reason, 0) + 1

    def record_task_resume(self) -> None:
        """Record task generation being resumed."""
        self._metrics.health_transitions.task_generation_resumed_count += 1

    def record_research_cycle(
        self,
        outcome: str,
        triggers_detected: int,
        triggers_executed: int,
        decision: str,
        gaps_addressed: int,
        gaps_remaining: int,
        execution_time_ms: int,
    ) -> None:
        """Record a research cycle execution.

        Args:
            outcome: Research cycle outcome (success, failed)
            triggers_detected: Number of triggers detected
            triggers_executed: Number of triggers executed
            decision: Decision outcome (proceed, block, adjust_plan, pause, skip)
            gaps_addressed: Number of gaps addressed
            gaps_remaining: Number of gaps remaining
            execution_time_ms: Execution time in milliseconds
        """
        rc = self._metrics.research_cycles
        rc.total_cycles_triggered += 1
        rc.total_triggers_detected += triggers_detected
        rc.total_triggers_executed += triggers_executed
        rc.total_execution_time_ms += execution_time_ms
        rc.total_gaps_addressed += gaps_addressed
        rc.gaps_remaining_last_cycle = gaps_remaining
        rc.last_cycle_time = datetime.now(timezone.utc).isoformat()

        if outcome == "success":
            rc.successful_cycles += 1
        elif outcome == "failed":
            rc.failed_cycles += 1

        # Record decision
        if decision == ResearchDecisionType.PROCEED.value:
            rc.decision_proceed += 1
        elif decision == ResearchDecisionType.PAUSE_FOR_RESEARCH.value:
            rc.decision_pause_for_research += 1
        elif decision == ResearchDecisionType.ADJUST_PLAN.value:
            rc.decision_adjust_plan += 1
        elif decision == ResearchDecisionType.BLOCK.value:
            rc.decision_block += 1
        elif decision == ResearchDecisionType.SKIP.value:
            rc.decision_skip += 1

        # Calculate average execution time
        total_cycles = rc.successful_cycles + rc.failed_cycles
        if total_cycles > 0:
            rc.avg_execution_time_ms = rc.total_execution_time_ms // total_cycles

    # ========================================================================
    # SESSION LIFECYCLE MANAGEMENT
    # ========================================================================

    def start_session(self, session_id: str) -> None:
        """Start tracking a new autopilot session.

        Args:
            session_id: Unique identifier for the session
        """
        self._current_session_id = session_id
        self._session_start_time = datetime.now(timezone.utc)

    def end_session(self, outcome: SessionOutcome, snapshot: SessionHealthSnapshot) -> None:
        """End the current autopilot session and record its outcome.

        Args:
            outcome: Final outcome of the session
            snapshot: Health snapshot at end of session
        """
        # Update session counts
        self._metrics.total_sessions += 1

        if outcome == SessionOutcome.COMPLETED:
            self._metrics.sessions_completed += 1
        elif outcome == SessionOutcome.BLOCKED_APPROVAL:
            self._metrics.sessions_blocked_approval += 1
        elif outcome == SessionOutcome.BLOCKED_CIRCUIT_BREAKER:
            self._metrics.sessions_blocked_circuit_breaker += 1
        elif outcome == SessionOutcome.BLOCKED_RESEARCH:
            self._metrics.sessions_blocked_research += 1
        elif outcome == SessionOutcome.FAILED:
            self._metrics.sessions_failed += 1

        # Store session in history (keep last 100)
        self._session_history.append(snapshot)
        if len(self._session_history) > 100:
            self._session_history.pop(0)

        # Update health timeline
        self._update_health_timeline()

        # Calculate overall health score
        self._calculate_overall_health_score()

        # Reset session state
        self._current_session_id = None
        self._session_start_time = None

    # ========================================================================
    # METRICS RETRIEVAL AND ANALYSIS
    # ========================================================================

    def get_metrics(self) -> AutopilotHealthMetrics:
        """Get current aggregated health metrics.

        Returns:
            AutopilotHealthMetrics object with all collected metrics
        """
        return self._metrics

    def get_session_history(self, limit: int = 100) -> List[SessionHealthSnapshot]:
        """Get recent session history.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of recent session snapshots
        """
        return self._session_history[-limit:] if self._session_history else []

    def get_health_timeline(self) -> List[Dict[str, Any]]:
        """Get health timeline for trend analysis.

        Returns:
            List of health snapshots over time
        """
        return self._health_timeline

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get complete dashboard summary for visualization.

        Returns:
            Dictionary with health gates, research metrics, and recent sessions
        """
        return {
            "overview": {
                "overall_health_score": self._metrics.overall_health_score,
                "critical_issues": self._metrics.critical_issues,
                "warnings": self._metrics.warnings,
                "total_sessions": self._metrics.total_sessions,
            },
            "health_gates": {
                "circuit_breaker": {
                    "current_state": self._metrics.circuit_breaker.current_state,
                    "health_score": self._metrics.circuit_breaker.last_health_score,
                    "total_checks": self._metrics.circuit_breaker.total_checks,
                    "total_trips": self._metrics.circuit_breaker.total_trips,
                    "check_pass_rate": (
                        self._metrics.circuit_breaker.checks_passed
                        / self._metrics.circuit_breaker.total_checks
                        if self._metrics.circuit_breaker.total_checks > 0
                        else 0.0
                    ),
                },
                "budget": {
                    "remaining": self._metrics.budget_enforcement.budget_remaining_current,
                    "min_remaining": self._metrics.budget_enforcement.budget_remaining_min,
                    "warning_count": self._metrics.budget_enforcement.warning_count,
                },
                "health_transitions": {
                    "current_status": self._metrics.health_transitions.current_status,
                    "total_transitions": self._metrics.health_transitions.total_transitions,
                    "pauses": self._metrics.health_transitions.task_generation_paused_count,
                    "resumes": self._metrics.health_transitions.task_generation_resumed_count,
                },
            },
            "research_cycles": {
                "total_triggered": self._metrics.research_cycles.total_cycles_triggered,
                "success_rate": self._metrics.research_cycles.success_rate,
                "avg_time_ms": self._metrics.research_cycles.avg_execution_time_ms,
                "decision_breakdown": {
                    "proceed": self._metrics.research_cycles.decision_proceed,
                    "pause_for_research": self._metrics.research_cycles.decision_pause_for_research,
                    "adjust_plan": self._metrics.research_cycles.decision_adjust_plan,
                    "block": self._metrics.research_cycles.decision_block,
                    "skip": self._metrics.research_cycles.decision_skip,
                },
            },
            "session_outcomes": {
                "completed": self._metrics.sessions_completed,
                "blocked_approval": self._metrics.sessions_blocked_approval,
                "blocked_circuit_breaker": self._metrics.sessions_blocked_circuit_breaker,
                "blocked_research": self._metrics.sessions_blocked_research,
                "failed": self._metrics.sessions_failed,
            },
            "recent_sessions": [s.to_dict() for s in self.get_session_history(limit=20)],
            "health_timeline": self._health_timeline[-100:] if self._health_timeline else [],
        }

    # ========================================================================
    # EXPORT MECHANISMS
    # ========================================================================

    def export_to_prometheus(self) -> Dict[str, float]:
        """Export metrics in Prometheus format.

        Returns:
            Dictionary of Prometheus metrics as key-value pairs
        """
        metrics = {}

        # Circuit breaker metrics
        metrics["autopack_autopilot_circuit_breaker_checks_total"] = (
            self._metrics.circuit_breaker.total_checks
        )
        metrics["autopack_autopilot_circuit_breaker_trips_total"] = (
            self._metrics.circuit_breaker.total_trips
        )
        metrics["autopack_autopilot_circuit_breaker_health_score"] = (
            self._metrics.circuit_breaker.last_health_score
        )

        # Budget metrics
        metrics["autopack_autopilot_budget_checks_total"] = (
            self._metrics.budget_enforcement.total_checks
        )
        metrics["autopack_autopilot_budget_remaining"] = (
            self._metrics.budget_enforcement.budget_remaining_current
        )
        metrics["autopack_autopilot_budget_warnings_total"] = (
            self._metrics.budget_enforcement.warning_count
        )

        # Health transition metrics
        metrics["autopack_autopilot_health_transitions_total"] = (
            self._metrics.health_transitions.total_transitions
        )
        metrics["autopack_autopilot_task_pauses_total"] = (
            self._metrics.health_transitions.task_generation_paused_count
        )
        metrics["autopack_autopilot_task_resumes_total"] = (
            self._metrics.health_transitions.task_generation_resumed_count
        )

        # Research cycle metrics
        metrics["autopack_autopilot_research_cycles_triggered_total"] = (
            self._metrics.research_cycles.total_cycles_triggered
        )
        metrics["autopack_autopilot_research_cycles_successful_total"] = (
            self._metrics.research_cycles.successful_cycles
        )
        metrics["autopack_autopilot_research_cycles_failed_total"] = (
            self._metrics.research_cycles.failed_cycles
        )
        metrics["autopack_autopilot_research_cycles_success_rate"] = (
            self._metrics.research_cycles.success_rate
        )

        # Session metrics
        metrics["autopack_autopilot_sessions_total"] = self._metrics.total_sessions
        metrics["autopack_autopilot_sessions_completed"] = self._metrics.sessions_completed
        metrics["autopack_autopilot_sessions_blocked_approval"] = (
            self._metrics.sessions_blocked_approval
        )
        metrics["autopack_autopilot_sessions_blocked_circuit_breaker"] = (
            self._metrics.sessions_blocked_circuit_breaker
        )
        metrics["autopack_autopilot_sessions_blocked_research"] = (
            self._metrics.sessions_blocked_research
        )
        metrics["autopack_autopilot_sessions_failed"] = self._metrics.sessions_failed

        # Overall health
        metrics["autopack_autopilot_health_score"] = self._metrics.overall_health_score

        return metrics

    def save_to_file(self, file_path: str) -> None:
        """Save metrics to a JSON file.

        Args:
            file_path: Path to save the metrics file
        """
        output_file = Path(file_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "format_version": "v1",
            "project_id": "autopack",
            "collection_start": (
                self._session_start_time.isoformat()
                if self._session_start_time
                else datetime.now(timezone.utc).isoformat()
            ),
            "collection_end": datetime.now(timezone.utc).isoformat(),
            "metrics": self._metrics.to_dict(),
            "prometheus": self.export_to_prometheus(),
            "session_history": [s.to_dict() for s in self._session_history],
            "health_timeline": self._health_timeline,
        }

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved autopilot health metrics to {file_path}")

    def load_from_file(self, file_path: str) -> None:
        """Load metrics from a JSON file (for testing/analysis).

        Args:
            file_path: Path to load metrics from
        """
        file = Path(file_path)
        if not file.exists():
            logger.warning(f"Metrics file not found: {file_path}")
            return

        try:
            with open(file, "r") as f:
                data = json.load(f)

            # Note: This is a simplified load for analysis
            # In production, would fully reconstruct metrics objects
            logger.info(f"Loaded autopilot health metrics from {file_path}")
        except Exception as e:
            logger.error(f"Error loading metrics from {file_path}: {e}")

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _update_health_timeline(self) -> None:
        """Update the health timeline with current state."""
        timeline_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_health_score": self._metrics.overall_health_score,
            "circuit_breaker_state": self._metrics.circuit_breaker.current_state,
            "circuit_breaker_health": self._metrics.circuit_breaker.last_health_score,
            "budget_remaining": self._metrics.budget_enforcement.budget_remaining_current,
            "health_status": self._metrics.health_transitions.current_status,
            "total_sessions": self._metrics.total_sessions,
            "sessions_completed": self._metrics.sessions_completed,
        }
        self._health_timeline.append(timeline_entry)

        # Keep only last 1000 entries
        if len(self._health_timeline) > 1000:
            self._health_timeline.pop(0)

    def _calculate_overall_health_score(self) -> None:
        """Calculate overall health score based on component metrics."""
        components = []

        # Circuit breaker contribution (20%)
        if self._metrics.circuit_breaker.total_checks > 0:
            cb_pass_rate = (
                self._metrics.circuit_breaker.checks_passed
                / self._metrics.circuit_breaker.total_checks
            )
            components.append(("circuit_breaker", cb_pass_rate, 0.2))

        # Budget contribution (20%)
        budget_score = min(1.0, self._metrics.budget_enforcement.budget_remaining_current * 1.5)
        components.append(("budget", budget_score, 0.2))

        # Health transitions contribution (20%)
        if self._metrics.health_transitions.total_transitions > 0:
            healthy_rate = (
                self._metrics.health_transitions.transitions_to_healthy
                / self._metrics.health_transitions.total_transitions
            )
            components.append(("health", healthy_rate, 0.2))

        # Research cycles contribution (20%)
        research_score = self._metrics.research_cycles.success_rate
        components.append(("research", research_score, 0.2))

        # Session success contribution (20%)
        if self._metrics.total_sessions > 0:
            session_score = self._metrics.sessions_completed / self._metrics.total_sessions
            components.append(("sessions", session_score, 0.2))

        # Calculate weighted average
        total_weight = sum(w for _, _, w in components)
        if total_weight > 0:
            weighted_sum = sum(score * weight for _, score, weight in components)
            self._metrics.overall_health_score = weighted_sum / total_weight

        # Identify critical issues
        self._identify_critical_issues()
        self._identify_warnings()

    def _identify_critical_issues(self) -> None:
        """Identify critical issues in health metrics."""
        issues = []

        if self._metrics.circuit_breaker.current_state == "open":
            issues.append("Circuit breaker is OPEN - execution blocked")

        if self._metrics.circuit_breaker.current_state == "half_open":
            issues.append("Circuit breaker is HALF_OPEN - limited execution")

        if self._metrics.budget_enforcement.budget_remaining_current < 0.05:
            issues.append("Critical: Budget below 5% threshold")

        if self._metrics.health_transitions.current_status == "attention_required":
            issues.append("Health status requires attention")

        if (
            self._metrics.research_cycles.success_rate < 0.3
            and self._metrics.research_cycles.total_cycles_triggered > 5
        ):
            issues.append("Research cycle success rate critically low (<30%)")

        if self._metrics.overall_health_score < 0.5:
            issues.append("Overall health score is critically low")

        self._metrics.critical_issues = issues

    def _identify_warnings(self) -> None:
        """Identify warnings in health metrics."""
        warnings = []

        if self._metrics.circuit_breaker.total_trips > 3:
            warnings.append(
                f"Circuit breaker has tripped {self._metrics.circuit_breaker.total_trips} times"
            )

        if self._metrics.budget_enforcement.budget_remaining_current < 0.2:
            warnings.append("Budget below 20% threshold")

        if self._metrics.health_transitions.current_status == "degraded":
            warnings.append("Health status is degraded")

        if (
            self._metrics.research_cycles.failed_cycles
            > self._metrics.research_cycles.successful_cycles
        ):
            warnings.append("More failed research cycles than successful")

        if self._metrics.sessions_failed > self._metrics.sessions_completed:
            warnings.append("More failed sessions than completed")

        if self._metrics.budget_enforcement.warning_count > 3:
            warnings.append(
                f"Budget warnings triggered {self._metrics.budget_enforcement.warning_count} times"
            )

        self._metrics.warnings = warnings


# ============================================================================
# GLOBAL SINGLETON INSTANCE (Optional, for convenience)
# ============================================================================

_global_collector: Optional[AutopilotHealthCollector] = None


def get_global_collector() -> AutopilotHealthCollector:
    """Get or create the global health collector instance.

    Returns:
        The global AutopilotHealthCollector instance
    """
    global _global_collector
    if _global_collector is None:
        _global_collector = AutopilotHealthCollector()
    return _global_collector
