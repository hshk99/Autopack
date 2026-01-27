"""Autonomous execution loop for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles the main autonomous execution loop that processes backlog phases.

IMP-AUTO-002: Extended to support parallel phase execution when file scopes don't overlap.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from autopack.archive_consolidator import log_build_event
from autopack.autonomous.budgeting import (BudgetExhaustedError,
                                           get_budget_remaining_pct,
                                           is_budget_exhausted)
from autopack.autonomy.parallelism_gate import (ParallelismPolicyGate,
                                                ScopeBasedParallelismChecker)
from autopack.config import settings
from autopack.database import (SESSION_HEALTH_CHECK_INTERVAL,
                               ensure_session_healthy)
from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome
from autopack.learned_rules import promote_hints_to_rules
from autopack.memory import extract_goal_from_description
from autopack.memory.context_injector import ContextInjector
from autopack.task_generation.task_effectiveness_tracker import \
    TaskEffectivenessTracker
from autopack.telemetry.analyzer import CostRecommendation, TelemetryAnalyzer
from autopack.telemetry.anomaly_detector import (AlertSeverity,
                                                 TelemetryAnomalyDetector)
from autopack.telemetry.meta_metrics import (FeedbackLoopHealth,
                                             FeedbackLoopHealthReport,
                                             MetaMetricsTracker)
from autopack.telemetry.telemetry_to_memory_bridge import \
    TelemetryToMemoryBridge

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)

# IMP-REL-004: Default max iteration limit for the execution loop
# This prevents unbounded loops when max_iterations is not explicitly set
DEFAULT_MAX_ITERATIONS = 10000


class SOTDriftError(Exception):
    """Raised when SOT drift is detected and drift_blocks_execution is enabled."""

    pass


class CircuitBreakerState(Enum):
    """States for the circuit breaker pattern.

    IMP-LOOP-006: Circuit breaker prevents runaway execution by tracking
    consecutive failures and temporarily halting execution when threshold
    is exceeded.

    States:
        CLOSED: Normal operation, requests are allowed
        OPEN: Circuit is tripped, requests are blocked
        HALF_OPEN: Testing if service has recovered, limited requests allowed
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and execution is blocked.

    IMP-LOOP-006: This exception signals that the autonomous loop has
    experienced too many consecutive failures and execution has been
    temporarily halted to prevent resource exhaustion.
    """

    def __init__(self, message: str, consecutive_failures: int, reset_time: float):
        super().__init__(message)
        self.consecutive_failures = consecutive_failures
        self.reset_time = reset_time


class CircuitBreaker:
    """Circuit breaker pattern implementation for autonomous loop protection.

    IMP-LOOP-006: Tracks consecutive failures and trips when threshold is exceeded.
    Prevents runaway execution and resource exhaustion by temporarily blocking
    execution until the circuit resets.

    States:
        CLOSED: Normal operation, failures are counted
        OPEN: Circuit tripped, execution blocked until reset timeout
        HALF_OPEN: After reset timeout, allow limited test calls

    Attributes:
        failure_threshold: Number of consecutive failures to trip circuit
        reset_timeout_seconds: Time to wait before attempting reset
        half_open_max_calls: Max calls in half-open state before decision
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 300,
        half_open_max_calls: int = 1,
        health_threshold: float = 0.5,
    ):
        """Initialize the circuit breaker.

        Args:
            failure_threshold: Consecutive failures before circuit trips (default: 5)
            reset_timeout_seconds: Seconds to wait before reset attempt (default: 300)
            half_open_max_calls: Max test calls in half-open state (default: 1)
            health_threshold: Minimum health score to allow OPEN->HALF_OPEN transition (default: 0.5)

        IMP-FBK-002: Enhanced with meta_metrics health check support.
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout_seconds = reset_timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        self.health_threshold = health_threshold

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._total_trips = 0  # Track total number of times circuit has tripped

        # IMP-FBK-002: Health check providers for smarter state transitions
        self._meta_metrics_tracker: Optional[MetaMetricsTracker] = None
        self._anomaly_detector: Optional[TelemetryAnomalyDetector] = None
        self._last_health_report: Optional[FeedbackLoopHealthReport] = None
        self._health_blocked_transitions = 0  # Count of blocked OPEN->HALF_OPEN transitions

    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state, checking for timeout-based transitions.

        IMP-FBK-002: Enhanced to check meta_metrics health before OPEN->HALF_OPEN
        transition. If health score is below threshold, keeps circuit OPEN even
        if timeout has elapsed.
        """
        if self._state == CircuitBreakerState.OPEN:
            # Check if reset timeout has elapsed
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.reset_timeout_seconds:
                    # IMP-FBK-002: Check health before transitioning
                    health_ok, health_score, reason = self._check_health_for_transition()

                    if health_ok:
                        logger.info(
                            f"[IMP-LOOP-006] Circuit breaker transitioning to HALF_OPEN "
                            f"after {elapsed:.1f}s timeout (health score: {health_score:.2f})"
                        )
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._half_open_calls = 0
                    else:
                        # Health check failed - keep circuit OPEN
                        self._health_blocked_transitions += 1
                        logger.warning(
                            f"[IMP-FBK-002] Circuit breaker reset BLOCKED by health check. "
                            f"Score: {health_score:.2f} < threshold {self.health_threshold}. "
                            f"Reason: {reason}. Blocked count: {self._health_blocked_transitions}"
                        )
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Get current consecutive failure count."""
        return self._consecutive_failures

    @property
    def total_trips(self) -> int:
        """Get total number of times circuit has tripped."""
        return self._total_trips

    @property
    def health_blocked_transitions(self) -> int:
        """Get count of OPEN->HALF_OPEN transitions blocked by health check.

        IMP-FBK-002: Tracks how often health-based blocking prevented premature reset.
        """
        return self._health_blocked_transitions

    def set_health_providers(
        self,
        meta_metrics_tracker: Optional[MetaMetricsTracker] = None,
        anomaly_detector: Optional[TelemetryAnomalyDetector] = None,
    ) -> None:
        """Set health check providers for smarter state transitions.

        IMP-FBK-002: Allows injection of meta_metrics and anomaly detection
        for holistic health assessment before circuit reset.

        Args:
            meta_metrics_tracker: Tracker for feedback loop health metrics
            anomaly_detector: Detector for telemetry anomalies
        """
        self._meta_metrics_tracker = meta_metrics_tracker
        self._anomaly_detector = anomaly_detector
        logger.debug(
            f"[IMP-FBK-002] Circuit breaker health providers set: "
            f"meta_metrics={meta_metrics_tracker is not None}, "
            f"anomaly_detector={anomaly_detector is not None}"
        )

    def update_health_report(self, health_report: FeedbackLoopHealthReport) -> None:
        """Update the latest health report for state transition decisions.

        IMP-FBK-002: Called after telemetry aggregation to provide fresh
        health data for circuit breaker decisions.

        Args:
            health_report: Latest FeedbackLoopHealthReport from meta_metrics
        """
        self._last_health_report = health_report
        logger.debug(
            f"[IMP-FBK-002] Circuit breaker health report updated: "
            f"status={health_report.overall_status.value}, "
            f"score={health_report.overall_score:.2f}"
        )

    def _check_health_for_transition(self) -> Tuple[bool, float, str]:
        """Check if health conditions allow OPEN->HALF_OPEN transition.

        IMP-FBK-002: Performs holistic health assessment using:
        1. FeedbackLoopHealthReport overall score and status
        2. Anomaly detector for active critical alerts
        3. Component-level health scores

        Returns:
            Tuple of (health_ok, health_score, reason):
                - health_ok: True if transition should be allowed
                - health_score: Current health score (0.0-1.0)
                - reason: Human-readable reason if blocked
        """
        # Default to allowing transition if no health providers configured
        if self._meta_metrics_tracker is None and self._anomaly_detector is None:
            if self._last_health_report is None:
                return (True, 1.0, "No health providers configured")

        # Check FeedbackLoopHealthReport if available
        health_score = 1.0
        reasons = []

        if self._last_health_report is not None:
            health_score = self._last_health_report.overall_score
            status = self._last_health_report.overall_status

            # Block transition if status is ATTENTION_REQUIRED
            if status == FeedbackLoopHealth.ATTENTION_REQUIRED:
                reasons.append(
                    f"Feedback loop status is ATTENTION_REQUIRED "
                    f"({len(self._last_health_report.critical_issues)} critical issues)"
                )

            # Block transition if score is below threshold
            if health_score < self.health_threshold:
                reasons.append(
                    f"Health score {health_score:.2f} below threshold {self.health_threshold}"
                )

            # Check for degrading components
            degrading_components = [
                name
                for name, report in self._last_health_report.component_reports.items()
                if report.status.value == "degrading"
            ]
            if len(degrading_components) >= 2:
                reasons.append(
                    f"{len(degrading_components)} components degrading: "
                    f"{', '.join(degrading_components[:3])}"
                )

        # Check anomaly detector for critical alerts
        if self._anomaly_detector is not None:
            pending_alerts = self._anomaly_detector.get_pending_alerts(clear=False)
            critical_alerts = [a for a in pending_alerts if a.severity == AlertSeverity.CRITICAL]
            if critical_alerts:
                reasons.append(f"{len(critical_alerts)} critical anomaly alert(s) active")

        # Determine if transition should be allowed
        if reasons:
            return (False, health_score, "; ".join(reasons))

        return (True, health_score, "Health check passed")

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitBreakerState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking execution)."""
        return self.state == CircuitBreakerState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitBreakerState.HALF_OPEN

    def record_success(self) -> None:
        """Record a successful operation, potentially closing the circuit.

        In CLOSED state: Resets failure counter
        In HALF_OPEN state: Transitions to CLOSED if success threshold met
        """
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                logger.info(
                    f"[IMP-LOOP-006] Circuit breaker closing after "
                    f"{self._half_open_calls} successful half-open call(s)"
                )
                self._state = CircuitBreakerState.CLOSED
                self._consecutive_failures = 0
                self._last_failure_time = None
                self._half_open_calls = 0
        elif self._state == CircuitBreakerState.CLOSED:
            # Reset consecutive failures on success in closed state
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        """Record a failed operation, potentially opening the circuit.

        In CLOSED state: Increments failure counter, trips if threshold exceeded
        In HALF_OPEN state: Immediately trips back to OPEN
        """
        self._consecutive_failures += 1
        self._last_failure_time = time.time()

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open state trips back to open
            logger.warning(
                f"[IMP-LOOP-006] Circuit breaker re-opening after failure in HALF_OPEN state. "
                f"Consecutive failures: {self._consecutive_failures}"
            )
            self._state = CircuitBreakerState.OPEN
            self._total_trips += 1
            self._half_open_calls = 0
        elif self._state == CircuitBreakerState.CLOSED:
            if self._consecutive_failures >= self.failure_threshold:
                logger.critical(
                    f"[IMP-LOOP-006] Circuit breaker TRIPPED! "
                    f"{self._consecutive_failures} consecutive failures (threshold: {self.failure_threshold}). "
                    f"Execution blocked for {self.reset_timeout_seconds}s."
                )
                self._state = CircuitBreakerState.OPEN
                self._total_trips += 1

    def check_state(self) -> None:
        """Check if circuit allows execution, raising if blocked.

        Raises:
            CircuitBreakerOpenError: If circuit is open and blocking execution
        """
        current_state = self.state  # This triggers timeout-based transitions

        if current_state == CircuitBreakerState.OPEN:
            time_until_reset = 0.0
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                time_until_reset = max(0, self.reset_timeout_seconds - elapsed)

            raise CircuitBreakerOpenError(
                f"Circuit breaker is OPEN. {self._consecutive_failures} consecutive failures. "
                f"Retry in {time_until_reset:.0f}s.",
                consecutive_failures=self._consecutive_failures,
                reset_time=time_until_reset,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state.

        Use with caution - typically the circuit should auto-reset via timeout.
        """
        logger.info("[IMP-LOOP-006] Circuit breaker manually reset to CLOSED")
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time = None
        self._half_open_calls = 0

    def get_stats(self) -> Dict:
        """Get circuit breaker statistics for monitoring.

        Returns:
            Dictionary with state, failures, trips, timing, and health info

        IMP-FBK-002: Extended to include health-related statistics.
        """
        time_in_current_state = None
        if self._last_failure_time is not None:
            time_in_current_state = time.time() - self._last_failure_time

        # IMP-FBK-002: Include health-related stats
        health_stats = {
            "health_threshold": self.health_threshold,
            "health_blocked_transitions": self._health_blocked_transitions,
            "has_meta_metrics_tracker": self._meta_metrics_tracker is not None,
            "has_anomaly_detector": self._anomaly_detector is not None,
        }

        if self._last_health_report is not None:
            health_stats["last_health_score"] = self._last_health_report.overall_score
            health_stats["last_health_status"] = self._last_health_report.overall_status.value
            health_stats["critical_issues_count"] = len(self._last_health_report.critical_issues)

        return {
            "state": self.state.value,
            "consecutive_failures": self._consecutive_failures,
            "total_trips": self._total_trips,
            "failure_threshold": self.failure_threshold,
            "reset_timeout_seconds": self.reset_timeout_seconds,
            "time_in_current_state_seconds": time_in_current_state,
            "half_open_calls": self._half_open_calls,
            **health_stats,
        }


class AutonomousLoop:
    """Main autonomous execution loop.

    Responsibilities:
    1. Process backlog phases sequentially or in parallel
    2. Handle phase execution orchestration
    3. Monitor execution health
    4. Handle loop termination conditions

    IMP-AUTO-002: Extended to support parallel phase execution when file scopes don't overlap.
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor
        self.poll_interval = 0.5  # Base polling interval
        self.idle_backoff_multiplier = 2.0  # Backoff when idle
        self.max_idle_sleep = 5.0  # Maximum sleep time when idle
        self._last_session_health_check = time.time()  # Track last health check
        self._telemetry_analyzer: Optional[TelemetryAnalyzer] = None

        # IMP-INT-002: TelemetryToMemoryBridge for persisting insights after aggregation
        self._telemetry_to_memory_bridge: Optional[TelemetryToMemoryBridge] = None

        # IMP-PERF-002: Context ceiling tracking
        # Prevents unbounded context injection across phases
        self._total_context_tokens = 0
        self._context_ceiling = settings.context_ceiling_tokens

        # IMP-LOOP-006: Circuit breaker for runaway execution protection
        # Tracks consecutive failures and trips when threshold exceeded
        self._circuit_breaker: Optional[CircuitBreaker] = None
        if settings.circuit_breaker_enabled:
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=settings.circuit_breaker_failure_threshold,
                reset_timeout_seconds=settings.circuit_breaker_reset_timeout_seconds,
                half_open_max_calls=settings.circuit_breaker_half_open_max_calls,
            )
            logger.info(
                f"[IMP-LOOP-006] Circuit breaker initialized "
                f"(threshold={settings.circuit_breaker_failure_threshold}, "
                f"reset={settings.circuit_breaker_reset_timeout_seconds}s)"
            )

        # IMP-LOOP-006: Iteration counter for loop tracking
        self._iteration_count = 0
        self._total_phases_executed = 0
        self._total_phases_failed = 0

        # IMP-AUTO-002: Scope-based parallel execution support
        self._parallelism_checker: Optional[ScopeBasedParallelismChecker] = None
        self._parallel_execution_enabled = getattr(
            settings, "parallel_phase_execution_enabled", False
        )
        self._max_parallel_phases = getattr(settings, "max_parallel_phases", 2)
        self._parallel_phases_executed = 0
        self._parallel_phases_skipped = 0

        # IMP-LOOP-001: Unified feedback pipeline for self-improvement loop
        self._feedback_pipeline: Optional[FeedbackPipeline] = None
        self._feedback_pipeline_enabled = getattr(settings, "feedback_pipeline_enabled", True)

        # IMP-INT-001: Telemetry aggregation tracking for self-improvement loop
        # Controls how often aggregate_telemetry() is called during execution
        self._telemetry_aggregation_interval = getattr(
            settings, "telemetry_aggregation_interval", 3
        )  # Aggregate every N phases
        self._phases_since_last_aggregation = 0

        # IMP-FBK-001: Task effectiveness tracker for closed-loop learning
        # Records task outcomes and feeds back to priority engine
        self._task_effectiveness_tracker: Optional[TaskEffectivenessTracker] = None
        self._task_effectiveness_enabled = getattr(
            settings, "task_effectiveness_tracking_enabled", True
        )

        # IMP-FBK-002: Meta-metrics and anomaly detection for circuit breaker health checks
        # These enable holistic health assessment before circuit breaker reset
        self._meta_metrics_tracker: Optional[MetaMetricsTracker] = None
        self._anomaly_detector: Optional[TelemetryAnomalyDetector] = None
        self._meta_metrics_enabled = getattr(settings, "meta_metrics_health_check_enabled", True)

        # Initialize health providers and wire to circuit breaker
        if self._meta_metrics_enabled:
            self._meta_metrics_tracker = MetaMetricsTracker()
            self._anomaly_detector = TelemetryAnomalyDetector()
            logger.info("[IMP-FBK-002] Meta-metrics health check initialized for circuit breaker")

            # Wire health providers to circuit breaker
            if self._circuit_breaker is not None:
                health_threshold = getattr(settings, "circuit_breaker_health_threshold", 0.5)
                self._circuit_breaker.health_threshold = health_threshold
                self._circuit_breaker.set_health_providers(
                    meta_metrics_tracker=self._meta_metrics_tracker,
                    anomaly_detector=self._anomaly_detector,
                )
                logger.info(
                    f"[IMP-FBK-002] Circuit breaker health providers wired "
                    f"(threshold={health_threshold})"
                )

    def get_loop_stats(self) -> Dict:
        """Get current loop statistics for monitoring (IMP-LOOP-006, IMP-AUTO-002).

        Returns:
            Dictionary with iteration count, phase counts, circuit breaker stats,
            and parallel execution stats.
        """
        stats = {
            "iteration_count": self._iteration_count,
            "total_phases_executed": self._total_phases_executed,
            "total_phases_failed": self._total_phases_failed,
            "context_tokens_used": self._total_context_tokens,
            "context_ceiling": self._context_ceiling,
        }

        if self._circuit_breaker is not None:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()

        # IMP-AUTO-002: Add parallel execution statistics
        stats["parallel_execution"] = {
            "enabled": self._parallel_execution_enabled,
            "max_parallel_phases": self._max_parallel_phases,
            "parallel_phases_executed": self._parallel_phases_executed,
            "parallel_phases_skipped": self._parallel_phases_skipped,
        }

        # IMP-LOOP-001: Add feedback pipeline statistics
        if self._feedback_pipeline is not None:
            stats["feedback_pipeline"] = self._feedback_pipeline.get_stats()
        else:
            stats["feedback_pipeline"] = {"enabled": self._feedback_pipeline_enabled}

        # IMP-FBK-001: Add task effectiveness statistics
        if self._task_effectiveness_tracker is not None:
            stats["task_effectiveness"] = self._task_effectiveness_tracker.get_summary()
        else:
            stats["task_effectiveness"] = {"enabled": self._task_effectiveness_enabled}

        return stats

    def reset_circuit_breaker(self) -> bool:
        """Manually reset the circuit breaker (IMP-LOOP-006).

        Use with caution - typically the circuit should auto-reset via timeout.

        Returns:
            True if circuit breaker was reset, False if not enabled
        """
        if self._circuit_breaker is not None:
            self._circuit_breaker.reset()
            return True
        return False

    # =========================================================================
    # IMP-AUTO-002: Parallel Phase Execution Support
    # =========================================================================

    def _initialize_parallelism_checker(self) -> None:
        """Initialize the scope-based parallelism checker.

        IMP-AUTO-002: Creates the parallelism checker with policy gate from
        the executor's intention anchor (if available).
        """
        if not self._parallel_execution_enabled:
            logger.debug("[IMP-AUTO-002] Parallel execution disabled by configuration")
            return

        # Get policy gate from intention anchor if available
        policy_gate: Optional[ParallelismPolicyGate] = None
        intention_anchor_v2 = getattr(self.executor, "_intention_anchor_v2", None)

        if intention_anchor_v2 is not None:
            try:
                policy_gate = ParallelismPolicyGate(intention_anchor_v2)
                if policy_gate.is_parallel_allowed():
                    logger.info(
                        f"[IMP-AUTO-002] Parallelism allowed by intention anchor "
                        f"(max_concurrent={policy_gate.get_max_concurrent_runs()})"
                    )
                else:
                    logger.info("[IMP-AUTO-002] Parallelism not allowed by intention anchor policy")
            except Exception as e:
                logger.warning(f"[IMP-AUTO-002] Failed to create parallelism policy gate: {e}")

        self._parallelism_checker = ScopeBasedParallelismChecker(policy_gate)
        logger.info(
            f"[IMP-AUTO-002] Parallelism checker initialized "
            f"(max_parallel_phases={self._max_parallel_phases})"
        )

    def _initialize_feedback_pipeline(self) -> None:
        """Initialize the unified feedback pipeline.

        IMP-LOOP-001: Creates the FeedbackPipeline for telemetry-memory-learning
        loop orchestration. Integrates with memory service and telemetry analyzer.
        """
        if not self._feedback_pipeline_enabled:
            logger.debug("[IMP-LOOP-001] Feedback pipeline disabled by configuration")
            return

        if self._feedback_pipeline is not None:
            logger.debug("[IMP-LOOP-001] Feedback pipeline already initialized")
            return

        # Get services from executor
        memory_service = getattr(self.executor, "memory_service", None)
        run_id = getattr(self.executor, "run_id", None)
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        # Initialize telemetry analyzer if not already present
        if self._telemetry_analyzer is None and hasattr(self.executor, "db_session"):
            try:
                self._telemetry_analyzer = TelemetryAnalyzer(
                    db_session=self.executor.db_session,
                    memory_service=memory_service,
                )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-001] Failed to initialize telemetry analyzer: {e}")

        # Create feedback pipeline
        self._feedback_pipeline = FeedbackPipeline(
            memory_service=memory_service,
            telemetry_analyzer=self._telemetry_analyzer,
            learning_pipeline=None,  # Will be set if available
            run_id=run_id,
            project_id=project_id,
            enabled=True,
        )

        logger.info(
            f"[IMP-LOOP-001] FeedbackPipeline initialized "
            f"(run_id={run_id}, project_id={project_id})"
        )

    def _get_feedback_pipeline_context(self, phase_type: str, phase_goal: str) -> str:
        """Get enhanced context from feedback pipeline.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to retrieve context
        from previous executions, including insights, errors, and success patterns.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test')
            phase_goal: Goal/description of the phase

        Returns:
            Formatted context string for prompt injection
        """
        if not self._feedback_pipeline_enabled or self._feedback_pipeline is None:
            return ""

        try:
            context = self._feedback_pipeline.get_context_for_phase(
                phase_type=phase_type,
                phase_goal=phase_goal,
                max_insights=5,
                max_age_hours=72.0,
                include_errors=True,
                include_success_patterns=True,
            )

            if context.formatted_context:
                logger.info(
                    f"[IMP-LOOP-001] Retrieved feedback pipeline context "
                    f"(insights={len(context.relevant_insights)}, "
                    f"errors={len(context.similar_errors)}, "
                    f"patterns={len(context.success_patterns)})"
                )

            return context.formatted_context

        except Exception as e:
            logger.warning(f"[IMP-LOOP-001] Failed to get feedback pipeline context: {e}")
            return ""

    def _process_phase_with_feedback_pipeline(
        self,
        phase: Dict,
        success: bool,
        status: str,
        execution_start_time: float,
    ) -> None:
        """Process phase outcome through the feedback pipeline.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to capture and persist
        phase execution feedback for the self-improvement loop.

        Args:
            phase: Phase dictionary with execution details
            success: Whether the phase executed successfully
            status: Final status string from execution
            execution_start_time: Unix timestamp when execution started
        """
        if not self._feedback_pipeline_enabled or self._feedback_pipeline is None:
            return

        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_type = phase.get("phase_type")
            run_id = getattr(self.executor, "run_id", "unknown")
            project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

            # Calculate execution time
            execution_time = time.time() - execution_start_time

            # Get tokens used (approximate)
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)

            # Build error message for failures
            error_message = None
            if not success:
                error_message = f"Phase failed with status: {status}"
                phase_result = getattr(self.executor, "_last_phase_result", None)
                if phase_result and isinstance(phase_result, dict):
                    error_detail = phase_result.get("error") or phase_result.get("message")
                    if error_detail:
                        error_message = f"{error_message}. Detail: {error_detail}"

            # Create PhaseOutcome
            outcome = PhaseOutcome(
                phase_id=phase_id,
                phase_type=phase_type,
                success=success,
                status=status,
                execution_time_seconds=execution_time,
                tokens_used=tokens_used,
                error_message=error_message,
                run_id=run_id,
                project_id=project_id,
            )

            # Process through feedback pipeline
            result = self._feedback_pipeline.process_phase_outcome(outcome)

            if result.get("success"):
                logger.debug(
                    f"[IMP-LOOP-001] Processed phase {phase_id} through feedback pipeline "
                    f"(insights={result.get('insights_created', 0)})"
                )

        except Exception as e:
            logger.warning(f"[IMP-LOOP-001] Failed to process phase through feedback pipeline: {e}")

    def _get_queued_phases_for_parallel_check(self, run_data: Dict) -> List[Dict]:
        """Get QUEUED phases suitable for parallel execution check.

        Args:
            run_data: Current run data from API

        Returns:
            List of QUEUED phases
        """
        phases = run_data.get("phases", [])
        queued_phases = []

        for phase in phases:
            status = phase.get("status", "").upper()
            if status == "QUEUED":
                queued_phases.append(phase)

        return queued_phases

    def _execute_phases_parallel(
        self, phases: List[Dict], phase_adjustments_map: Dict[str, Dict]
    ) -> List[Tuple[Dict, bool, str]]:
        """Execute multiple phases in parallel using ThreadPoolExecutor.

        IMP-AUTO-002: Executes phases with non-overlapping scopes concurrently.

        Args:
            phases: List of phases to execute in parallel
            phase_adjustments_map: Map of phase_id -> adjustments dict

        Returns:
            List of (phase, success, status) tuples for each executed phase
        """
        results: List[Tuple[Dict, bool, str]] = []

        if len(phases) == 1:
            # Single phase - execute directly
            phase = phases[0]
            adjustments = phase_adjustments_map.get(phase.get("phase_id", ""), {})
            success, status = self.executor.execute_phase(phase, **adjustments)
            return [(phase, success, status)]

        logger.info(
            f"[IMP-AUTO-002] Executing {len(phases)} phases in parallel: "
            f"{[p.get('phase_id', 'unknown') for p in phases]}"
        )

        # Use ThreadPoolExecutor for parallel execution
        # Note: Using threads (not processes) to share executor state
        with ThreadPoolExecutor(max_workers=len(phases)) as executor:
            # Submit all phases for execution
            future_to_phase = {}
            for phase in phases:
                phase_id = phase.get("phase_id", "unknown")
                adjustments = phase_adjustments_map.get(phase_id, {})

                future = executor.submit(
                    self._execute_single_phase_thread_safe,
                    phase,
                    adjustments,
                )
                future_to_phase[future] = phase

            # Collect results as they complete
            for future in as_completed(future_to_phase):
                phase = future_to_phase[future]
                phase_id = phase.get("phase_id", "unknown")

                try:
                    success, status = future.result()
                    results.append((phase, success, status))
                    logger.info(
                        f"[IMP-AUTO-002] Parallel phase {phase_id} completed: "
                        f"success={success}, status={status}"
                    )
                except Exception as e:
                    logger.error(f"[IMP-AUTO-002] Parallel phase {phase_id} failed with error: {e}")
                    results.append((phase, False, f"PARALLEL_EXECUTION_ERROR: {e}"))

        self._parallel_phases_executed += len(phases)
        return results

    def _execute_single_phase_thread_safe(self, phase: Dict, adjustments: Dict) -> Tuple[bool, str]:
        """Execute a single phase in a thread-safe manner.

        IMP-AUTO-002: Wrapper for execute_phase to handle thread-safety concerns.

        Args:
            phase: Phase specification
            adjustments: Telemetry-driven adjustments

        Returns:
            Tuple of (success, status)
        """
        phase_id = phase.get("phase_id", "unknown")

        try:
            # Execute via the executor
            # Note: The executor's execute_phase method handles its own locking
            success, status = self.executor.execute_phase(phase, **adjustments)
            return success, status
        except Exception as e:
            logger.error(f"[IMP-AUTO-002] Thread execution error for phase {phase_id}: {e}")
            return False, f"THREAD_ERROR: {str(e)}"

    def _try_parallel_execution(
        self, run_data: Dict, next_phase: Dict
    ) -> Optional[Tuple[List[Tuple[Dict, bool, str]], int]]:
        """Attempt to find and execute phases in parallel.

        IMP-AUTO-002: Checks if there are additional phases that can run in parallel
        with the next_phase based on scope isolation.

        Args:
            run_data: Current run data
            next_phase: The primary phase to execute

        Returns:
            If parallel execution occurred: (results, phases_count)
            If sequential execution needed: None
        """
        if not self._parallel_execution_enabled or self._parallelism_checker is None:
            return None

        # Get all queued phases
        queued_phases = self._get_queued_phases_for_parallel_check(run_data)

        if len(queued_phases) < 2:
            return None

        # Put next_phase first, then find compatible phases
        next_phase_id = next_phase.get("phase_id")
        other_phases = [p for p in queued_phases if p.get("phase_id") != next_phase_id]

        if not other_phases:
            return None

        # Find phases that can run in parallel with next_phase
        parallel_group = [next_phase]

        for candidate in other_phases:
            if len(parallel_group) >= self._max_parallel_phases:
                break

            can_parallel, reason = self._parallelism_checker.can_execute_parallel(
                parallel_group + [candidate]
            )

            if can_parallel:
                parallel_group.append(candidate)
            else:
                logger.debug(
                    f"[IMP-AUTO-002] Cannot add phase {candidate.get('phase_id')} "
                    f"to parallel group: {reason}"
                )

        if len(parallel_group) < 2:
            self._parallel_phases_skipped += 1
            return None

        # Prepare adjustments for all phases in the group
        phase_adjustments_map: Dict[str, Dict] = {}
        for phase in parallel_group:
            phase_id = phase.get("phase_id", "unknown")
            phase_type = phase.get("phase_type")
            phase_goal = phase.get("description", "")

            # Get telemetry adjustments
            adjustments = self._get_telemetry_adjustments(phase_type)

            # Get memory context
            memory_context = self._get_memory_context(phase_type, phase_goal)
            improvement_context = self._get_improvement_task_context()

            combined_context = ""
            if memory_context:
                combined_context = memory_context
            if improvement_context:
                combined_context = (
                    combined_context + "\n\n" + improvement_context
                    if combined_context
                    else improvement_context
                )

            if combined_context:
                combined_context = self._inject_context_with_ceiling(combined_context)
                if combined_context:
                    adjustments["memory_context"] = combined_context

            phase_adjustments_map[phase_id] = adjustments

        # Execute phases in parallel
        results = self._execute_phases_parallel(parallel_group, phase_adjustments_map)
        return results, len(parallel_group)

    def _get_telemetry_analyzer(self) -> Optional[TelemetryAnalyzer]:
        """Get or create the telemetry analyzer instance.

        Returns:
            TelemetryAnalyzer instance if database session is available, None otherwise.
        """
        if self._telemetry_analyzer is None:
            if hasattr(self.executor, "db_session") and self.executor.db_session:
                # IMP-ARCH-015: Pass memory_service to enable telemetry -> memory bridge
                memory_service = getattr(self.executor, "memory_service", None)
                self._telemetry_analyzer = TelemetryAnalyzer(
                    self.executor.db_session,
                    memory_service=memory_service,
                )
        return self._telemetry_analyzer

    def _get_telemetry_to_memory_bridge(self) -> Optional[TelemetryToMemoryBridge]:
        """Get or create the TelemetryToMemoryBridge instance.

        IMP-INT-002: Provides a bridge for persisting telemetry insights to memory
        after aggregation. The bridge is lazily initialized and reused.

        Returns:
            TelemetryToMemoryBridge instance if memory_service is available, None otherwise.
        """
        if self._telemetry_to_memory_bridge is None:
            memory_service = getattr(self.executor, "memory_service", None)
            if memory_service and memory_service.enabled:
                self._telemetry_to_memory_bridge = TelemetryToMemoryBridge(
                    memory_service=memory_service,
                    enabled=True,
                )
        return self._telemetry_to_memory_bridge

    def _flatten_ranked_issues_to_dicts(self, ranked_issues: Dict) -> list:
        """Convert ranked issues from aggregate_telemetry() to a flat list of dicts.

        IMP-INT-002: Converts RankedIssue objects to dictionaries suitable for
        TelemetryToMemoryBridge.persist_insights().

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.

        Returns:
            Flat list of dictionaries ready for bridge.persist_insights().
        """
        flat_issues = []

        for issue in ranked_issues.get("top_cost_sinks", []):
            flat_issues.append(
                {
                    "issue_type": "cost_sink",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "high",
                    "description": f"Phase {issue.phase_id} consuming {issue.metric_value:,.0f} tokens",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Optimize token usage for {issue.phase_type}",
                }
            )

        for issue in ranked_issues.get("top_failure_modes", []):
            flat_issues.append(
                {
                    "issue_type": "failure_mode",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "high",
                    "description": f"Failure: {issue.details.get('outcome', '')} - {issue.details.get('stop_reason', '')}",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Fix {issue.phase_type} failure pattern",
                }
            )

        for issue in ranked_issues.get("top_retry_causes", []):
            flat_issues.append(
                {
                    "issue_type": "retry_cause",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "medium",
                    "description": f"Retry cause: {issue.details.get('stop_reason', '')}",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Increase timeout or optimize {issue.phase_type}",
                }
            )

        return flat_issues

    def _persist_insights_to_memory(
        self, ranked_issues: Dict, context: str = "phase_telemetry"
    ) -> int:
        """Persist ranked issues to memory via TelemetryToMemoryBridge.

        IMP-INT-002: Invokes TelemetryToMemoryBridge.persist_insights() after
        telemetry aggregation to store insights in memory for future retrieval.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of insights persisted, or 0 if persistence failed/skipped.
        """
        bridge = self._get_telemetry_to_memory_bridge()
        if not bridge:
            logger.debug(f"[IMP-INT-002] No bridge available for {context} persistence")
            return 0

        run_id = getattr(self.executor, "run_id", "unknown")
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        try:
            # Flatten ranked issues to dicts for bridge
            flat_issues = self._flatten_ranked_issues_to_dicts(ranked_issues)

            if not flat_issues:
                logger.debug(f"[IMP-INT-002] No issues to persist for {context}")
                return 0

            # Persist to memory
            persisted_count = bridge.persist_insights(
                ranked_issues=flat_issues,
                run_id=run_id,
                project_id=project_id,
            )

            logger.info(
                f"[IMP-INT-002] Persisted {persisted_count} insights to memory "
                f"(context={context}, run_id={run_id})"
            )
            return persisted_count

        except Exception as e:
            # Non-fatal - persistence failure should not block execution
            logger.warning(
                f"[IMP-INT-002] Failed to persist insights to memory "
                f"(context={context}, non-fatal): {e}"
            )
            return 0

    def _generate_tasks_from_ranked_issues(
        self, ranked_issues: Dict, context: str = "phase_telemetry"
    ) -> int:
        """Generate improvement tasks from ranked issues and queue them for execution.

        IMP-INT-003: Wires ROADC TaskGenerator into executor loop. After telemetry
        insights are persisted to memory, this method generates improvement tasks
        from those same insights and persists them to the database for execution.

        This completes the insight→task→execution cycle by ensuring tasks are
        generated directly from persisted insights without re-aggregating telemetry.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of tasks generated and persisted, or 0 if generation failed/skipped.
        """
        try:
            from autopack.config import settings as config_settings
            from autopack.roadc import AutonomousTaskGenerator
        except ImportError:
            logger.debug("[IMP-INT-003] ROADC module not available for task generation")
            return 0

        # Check if task generation is enabled
        try:
            task_gen_config = getattr(config_settings, "task_generation", {})
            if not task_gen_config:
                task_gen_config = {"enabled": False}
        except Exception:
            task_gen_config = {"enabled": False}

        if not task_gen_config.get("enabled", False):
            logger.debug("[IMP-INT-003] Task generation not enabled in settings")
            return 0

        # Check if we have any issues to generate tasks from
        total_issues = (
            len(ranked_issues.get("top_cost_sinks", []))
            + len(ranked_issues.get("top_failure_modes", []))
            + len(ranked_issues.get("top_retry_causes", []))
        )

        if total_issues == 0:
            logger.debug(f"[IMP-INT-003] No ranked issues for task generation ({context})")
            return 0

        try:
            # IMP-INT-003: Generate tasks directly from the ranked issues that were just persisted
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)

            run_id = getattr(self.executor, "run_id", None)
            result = generator.generate_tasks(
                max_tasks=task_gen_config.get("max_tasks_per_run", 10),
                min_confidence=task_gen_config.get("min_confidence", 0.7),
                telemetry_insights=ranked_issues,
                run_id=run_id,
            )

            tasks_generated = len(result.tasks_generated)
            logger.info(
                f"[IMP-INT-003] Generated {tasks_generated} tasks from {total_issues} "
                f"ranked issues ({context}, {result.generation_time_ms:.0f}ms)"
            )

            # Persist generated tasks to database for execution queue
            if result.tasks_generated:
                try:
                    persisted_count = generator.persist_tasks(result.tasks_generated, run_id)
                    logger.info(
                        f"[IMP-INT-003] Queued {persisted_count} tasks for execution ({context})"
                    )
                    return persisted_count
                except Exception as persist_err:
                    logger.warning(
                        f"[IMP-INT-003] Failed to queue tasks for execution "
                        f"(context={context}, non-fatal): {persist_err}"
                    )
                    return 0

            return 0

        except Exception as e:
            # Non-fatal - task generation failure should not block execution
            logger.warning(
                f"[IMP-INT-003] Failed to generate tasks from ranked issues "
                f"(context={context}, non-fatal): {e}"
            )
            return 0

    def _aggregate_phase_telemetry(self, phase_id: str, force: bool = False) -> Optional[Dict]:
        """Aggregate telemetry after phase completion for self-improvement feedback.

        IMP-INT-001: Wires TelemetryAnalyzer.aggregate_telemetry() into the autonomous
        execution loop after phase completion. This enables the self-improvement
        architecture by ensuring telemetry insights are aggregated and persisted
        during execution, not just at the end of the run.

        Uses throttling to avoid expensive database queries after every phase.
        By default, aggregates every N phases (controlled by telemetry_aggregation_interval).

        Args:
            phase_id: ID of the phase that just completed (for logging)
            force: If True, bypass throttling and aggregate immediately

        Returns:
            Dictionary of ranked issues from aggregate_telemetry(), or None if
            aggregation was skipped (throttled) or failed.
        """
        # Increment phase counter
        self._phases_since_last_aggregation += 1

        # Check if we should aggregate (throttling)
        should_aggregate = force or (
            self._phases_since_last_aggregation >= self._telemetry_aggregation_interval
        )

        if not should_aggregate:
            logger.debug(
                f"[IMP-INT-001] Skipping telemetry aggregation after phase {phase_id} "
                f"({self._phases_since_last_aggregation}/{self._telemetry_aggregation_interval} phases)"
            )
            return None

        analyzer = self._get_telemetry_analyzer()
        if not analyzer:
            logger.debug("[IMP-INT-001] No telemetry analyzer available for aggregation")
            return None

        try:
            # Aggregate telemetry from database
            ranked_issues = analyzer.aggregate_telemetry(window_days=7)

            # Reset throttle counter
            self._phases_since_last_aggregation = 0

            # Log aggregation results
            total_issues = (
                len(ranked_issues.get("top_cost_sinks", []))
                + len(ranked_issues.get("top_failure_modes", []))
                + len(ranked_issues.get("top_retry_causes", []))
            )
            logger.info(
                f"[IMP-INT-001] Aggregated telemetry after phase {phase_id}: "
                f"{total_issues} issues found "
                f"(cost_sinks={len(ranked_issues.get('top_cost_sinks', []))}, "
                f"failure_modes={len(ranked_issues.get('top_failure_modes', []))}, "
                f"retry_causes={len(ranked_issues.get('top_retry_causes', []))})"
            )

            # IMP-INT-002: Persist aggregated insights to memory via bridge
            self._persist_insights_to_memory(ranked_issues, context="phase_telemetry")

            # IMP-FBK-002: Update circuit breaker health report from meta-metrics
            self._update_circuit_breaker_health(ranked_issues)

            return ranked_issues

        except Exception as e:
            # Non-fatal - telemetry aggregation failure should not block execution
            logger.warning(
                f"[IMP-INT-001] Failed to aggregate telemetry after phase {phase_id} "
                f"(non-fatal): {e}"
            )
            return None

    def _get_task_effectiveness_tracker(self) -> Optional[TaskEffectivenessTracker]:
        """Get or create the TaskEffectivenessTracker instance.

        IMP-FBK-001: Lazy initialization of the task effectiveness tracker.
        Creates the tracker on first access if effectiveness tracking is enabled.

        Returns:
            TaskEffectivenessTracker instance, or None if tracking is disabled.
        """
        if not self._task_effectiveness_enabled:
            return None

        if self._task_effectiveness_tracker is None:
            try:
                # Try to get priority engine from executor for feedback integration
                priority_engine = getattr(self.executor, "_priority_engine", None)
                self._task_effectiveness_tracker = TaskEffectivenessTracker(
                    priority_engine=priority_engine
                )
                logger.info(
                    "[IMP-FBK-001] TaskEffectivenessTracker initialized "
                    f"(priority_engine={'enabled' if priority_engine else 'disabled'})"
                )
            except Exception as e:
                logger.warning(f"[IMP-FBK-001] Failed to initialize TaskEffectivenessTracker: {e}")
                return None

        return self._task_effectiveness_tracker

    def _update_circuit_breaker_health(self, ranked_issues: Optional[Dict]) -> None:
        """Update circuit breaker with latest health report from meta-metrics.

        IMP-FBK-002: Generates a FeedbackLoopHealthReport from aggregated telemetry
        and updates the circuit breaker to enable health-aware state transitions.
        This prevents premature circuit reset when the system is still unhealthy.

        Args:
            ranked_issues: Ranked issues from telemetry aggregation (used to build
                          telemetry data for health analysis)
        """
        if not self._meta_metrics_enabled:
            return

        if self._circuit_breaker is None:
            return

        if self._meta_metrics_tracker is None:
            return

        try:
            # Build telemetry data structure from ranked issues and loop stats
            telemetry_data = self._build_telemetry_data_for_health(ranked_issues)

            # Analyze feedback loop health
            health_report = self._meta_metrics_tracker.analyze_feedback_loop_health(
                telemetry_data=telemetry_data
            )

            # Update circuit breaker with health report
            self._circuit_breaker.update_health_report(health_report)

            # Log health status
            if health_report.overall_status == FeedbackLoopHealth.ATTENTION_REQUIRED:
                logger.warning(
                    f"[IMP-FBK-002] Feedback loop health: ATTENTION_REQUIRED "
                    f"(score={health_report.overall_score:.2f}, "
                    f"critical_issues={len(health_report.critical_issues)})"
                )
            elif health_report.overall_status == FeedbackLoopHealth.DEGRADED:
                logger.info(
                    f"[IMP-FBK-002] Feedback loop health: DEGRADED "
                    f"(score={health_report.overall_score:.2f})"
                )
            else:
                logger.debug(
                    f"[IMP-FBK-002] Feedback loop health: {health_report.overall_status.value} "
                    f"(score={health_report.overall_score:.2f})"
                )

        except Exception as e:
            # Non-fatal - health check failure should not block execution
            logger.warning(
                f"[IMP-FBK-002] Failed to update circuit breaker health (non-fatal): {e}"
            )

    def _build_telemetry_data_for_health(self, ranked_issues: Optional[Dict]) -> Dict:
        """Build telemetry data structure for meta-metrics health analysis.

        IMP-FBK-002: Converts ranked issues and loop statistics into the format
        expected by MetaMetricsTracker.analyze_feedback_loop_health().

        Args:
            ranked_issues: Ranked issues from telemetry aggregation

        Returns:
            Dictionary formatted for meta-metrics health analysis
        """
        # Initialize with loop statistics
        telemetry_data: Dict = {
            "road_b": {  # Telemetry Analysis
                "phases_analyzed": self._total_phases_executed,
                "total_phases": self._total_phases_executed + self._total_phases_failed,
                "false_positives": 0,
                "total_issues": 0,
            },
            "road_c": {  # Task Generation
                "completed_tasks": self._total_phases_executed,
                "total_tasks": self._total_phases_executed + self._total_phases_failed,
                "rework_count": 0,
            },
            "road_e": {  # Validation Coverage
                "valid_ab_tests": 0,
                "total_ab_tests": 0,
                "regressions_caught": 0,
                "total_changes": 0,
            },
            "road_f": {  # Policy Promotion
                "effective_promotions": 0,
                "total_promotions": 0,
                "rollbacks": 0,
            },
            "road_g": {  # Anomaly Detection
                "actionable_alerts": 0,
                "total_alerts": 0,
                "false_positives": 0,
            },
            "road_j": {  # Auto-Healing
                "successful_heals": 0,
                "total_heal_attempts": 0,
                "escalations": 0,
            },
            "road_l": {  # Model Optimization
                "optimal_routings": 0,
                "total_routings": 0,
                "avg_tokens_per_success": 0,
                "sample_count": 0,
            },
        }

        # Add data from ranked issues if available
        if ranked_issues:
            cost_sinks = ranked_issues.get("top_cost_sinks", [])
            failure_modes = ranked_issues.get("top_failure_modes", [])
            retry_causes = ranked_issues.get("top_retry_causes", [])

            total_issues = len(cost_sinks) + len(failure_modes) + len(retry_causes)
            telemetry_data["road_b"]["total_issues"] = total_issues

            # Estimate task quality from failure modes
            if failure_modes:
                telemetry_data["road_c"]["rework_count"] = len(failure_modes)

        # Add anomaly detector stats if available
        if self._anomaly_detector is not None:
            pending_alerts = self._anomaly_detector.get_pending_alerts(clear=False)
            telemetry_data["road_g"]["total_alerts"] = len(pending_alerts)
            telemetry_data["road_g"]["actionable_alerts"] = len(
                [a for a in pending_alerts if a.severity == AlertSeverity.CRITICAL]
            )

        return telemetry_data

    def _update_task_effectiveness(
        self,
        phase_id: str,
        phase_type: Optional[str],
        success: bool,
        execution_time_seconds: float,
        tokens_used: int = 0,
    ) -> None:
        """Update task effectiveness tracking after phase completion.

        IMP-FBK-001: Records phase execution outcomes to the TaskEffectivenessTracker
        for closed-loop learning. This enables the priority engine to adjust task
        prioritization based on historical effectiveness.

        IMP-FBK-002: Also records outcomes to anomaly detector for pattern detection.

        Args:
            phase_id: ID of the completed phase
            phase_type: Type of the phase (e.g., "build", "test")
            success: Whether the phase executed successfully
            execution_time_seconds: Time taken to execute the phase
            tokens_used: Number of tokens consumed during execution
        """
        # IMP-FBK-002: Record to anomaly detector for pattern detection
        self._record_phase_to_anomaly_detector(
            phase_id=phase_id,
            phase_type=phase_type,
            success=success,
            tokens_used=tokens_used,
            duration_seconds=execution_time_seconds,
        )

        tracker = self._get_task_effectiveness_tracker()
        if not tracker:
            return

        try:
            # Record the task outcome
            report = tracker.record_task_outcome(
                task_id=phase_id,
                success=success,
                execution_time_seconds=execution_time_seconds,
                tokens_used=tokens_used,
                category=phase_type or "general",
                notes="Phase execution outcome from autonomous loop",
            )

            # Feed back to priority engine if available
            tracker.feed_back_to_priority_engine(report)

            logger.debug(
                f"[IMP-FBK-001] Updated task effectiveness for phase {phase_id}: "
                f"effectiveness={report.effectiveness_score:.2f} ({report.get_effectiveness_grade()})"
            )

        except Exception as e:
            # Non-fatal - effectiveness tracking failure should not block execution
            logger.warning(
                f"[IMP-FBK-001] Failed to update task effectiveness for phase {phase_id} "
                f"(non-fatal): {e}"
            )

    def _record_phase_to_anomaly_detector(
        self,
        phase_id: str,
        phase_type: Optional[str],
        success: bool,
        tokens_used: int,
        duration_seconds: float,
    ) -> None:
        """Record phase outcome to anomaly detector for pattern detection.

        IMP-FBK-002: Records phase outcomes to TelemetryAnomalyDetector which
        tracks token spikes, failure rate breaches, and duration anomalies.
        These anomalies are used by the circuit breaker for health-aware
        state transitions.

        Args:
            phase_id: ID of the completed phase
            phase_type: Type of the phase (e.g., "build", "test")
            success: Whether the phase executed successfully
            tokens_used: Number of tokens consumed during execution
            duration_seconds: Time taken to execute the phase
        """
        if self._anomaly_detector is None:
            return

        try:
            alerts = self._anomaly_detector.record_phase_outcome(
                phase_id=phase_id,
                phase_type=phase_type or "general",
                success=success,
                tokens_used=tokens_used,
                duration_seconds=duration_seconds,
            )

            # Log any alerts generated
            if alerts:
                for alert in alerts:
                    if alert.severity == AlertSeverity.CRITICAL:
                        logger.warning(
                            f"[IMP-FBK-002] Critical anomaly detected: {alert.metric} "
                            f"(value={alert.current_value:.2f}, threshold={alert.threshold:.2f})"
                        )
                    else:
                        logger.debug(
                            f"[IMP-FBK-002] Anomaly detected: {alert.metric} "
                            f"(value={alert.current_value:.2f})"
                        )

        except Exception as e:
            # Non-fatal - anomaly detection failure should not block execution
            logger.debug(
                f"[IMP-FBK-002] Failed to record phase to anomaly detector " f"(non-fatal): {e}"
            )

    def _get_telemetry_adjustments(self, phase_type: Optional[str]) -> Dict:
        """Get telemetry-driven adjustments for phase execution.

        Queries the telemetry analyzer for recommendations and returns
        adjustments to apply to the phase execution.

        Args:
            phase_type: The type of phase being executed

        Returns:
            Dictionary of adjustments to pass to execute_phase:
            - context_reduction_factor: Factor to reduce context by (e.g., 0.7 for 30% reduction)
            - model_downgrade: Target model to use instead (e.g., "sonnet", "haiku")
            - timeout_increase_factor: Factor to increase timeout by (e.g., 1.5 for 50% increase)
        """
        adjustments: Dict = {}

        if not phase_type:
            return adjustments

        analyzer = self._get_telemetry_analyzer()
        if not analyzer:
            return adjustments

        try:
            recommendations = analyzer.get_recommendations_for_phase(phase_type)
        except Exception as e:
            logger.warning(f"[Telemetry] Failed to get recommendations for {phase_type}: {e}")
            return adjustments

        # Model downgrade hierarchy: opus -> sonnet -> haiku
        model_hierarchy = ["opus", "sonnet", "haiku"]

        for rec in recommendations:
            severity = rec.get("severity")
            action = rec.get("action")
            reason = rec.get("reason", "")
            metric_value = rec.get("metric_value")

            if severity == "CRITICAL":
                # Apply mitigations for CRITICAL recommendations
                if action == "reduce_context_size":
                    adjustments["context_reduction_factor"] = 0.7  # Reduce by 30%
                    logger.warning(
                        f"[Telemetry] CRITICAL: Reducing context size by 30% for {phase_type}. "
                        f"Reason: {reason}"
                    )
                elif action == "switch_to_smaller_model":
                    # Downgrade model: opus -> sonnet -> haiku
                    current_model = getattr(settings, "default_model", "opus").lower()
                    current_idx = -1
                    for i, model in enumerate(model_hierarchy):
                        if model in current_model:
                            current_idx = i
                            break
                    if current_idx >= 0 and current_idx < len(model_hierarchy) - 1:
                        adjustments["model_downgrade"] = model_hierarchy[current_idx + 1]
                        logger.warning(
                            f"[Telemetry] CRITICAL: Downgrading model to {adjustments['model_downgrade']} "
                            f"for {phase_type}. Reason: {reason}"
                        )
                elif action == "increase_timeout":
                    adjustments["timeout_increase_factor"] = 1.5  # Increase by 50%
                    logger.warning(
                        f"[Telemetry] CRITICAL: Increasing timeout by 50% for {phase_type}. "
                        f"Reason: {reason}"
                    )
            elif severity == "HIGH":
                # Log HIGH recommendations for informational tracking only
                logger.info(
                    f"[Telemetry] HIGH: {action} recommended for {phase_type}. "
                    f"Reason: {reason} (metric: {metric_value})"
                )

        return adjustments

    def _check_cost_recommendations(self) -> CostRecommendation:
        """Check if telemetry recommends pausing for cost reasons (IMP-COST-005).

        Queries the telemetry analyzer for cost recommendations based on
        current token usage against the run's budget cap.

        Returns:
            CostRecommendation with pause decision and details
        """
        analyzer = self._get_telemetry_analyzer()
        tokens_used = getattr(self.executor, "_run_tokens_used", 0)
        token_cap = settings.run_token_cap

        if not analyzer:
            # No analyzer available, create a basic recommendation
            if token_cap > 0:
                usage_pct = tokens_used / token_cap
                budget_remaining_pct = max(0.0, (1.0 - usage_pct) * 100)
                should_pause = usage_pct >= 0.95
                return CostRecommendation(
                    should_pause=should_pause,
                    reason="Basic cost check (no telemetry analyzer)",
                    current_spend=float(tokens_used),
                    budget_remaining_pct=budget_remaining_pct,
                    severity="critical" if should_pause else "info",
                )
            return CostRecommendation(
                should_pause=False,
                reason="No token cap configured",
                current_spend=float(tokens_used),
                budget_remaining_pct=100.0,
                severity="info",
            )

        return analyzer.get_cost_recommendations(tokens_used, token_cap)

    def _pause_for_cost_limit(self, recommendation: CostRecommendation) -> None:
        """Handle pause when cost limits are approached (IMP-COST-005).

        Logs the cost pause event and could trigger notifications or
        graceful shutdown procedures in the future.

        Args:
            recommendation: The CostRecommendation that triggered the pause
        """
        logger.warning(
            f"[IMP-COST-005] Cost pause triggered: {recommendation.reason}. "
            f"Current spend: {recommendation.current_spend:,.0f} tokens. "
            f"Budget remaining: {recommendation.budget_remaining_pct:.1f}%"
        )

        # Log to build event for visibility
        try:
            from autopack.archive_consolidator import log_build_event

            log_build_event(
                event_type="COST_PAUSE",
                description=f"Execution paused due to cost limits: {recommendation.reason}",
                deliverables=[
                    f"Tokens used: {recommendation.current_spend:,.0f}",
                    f"Budget remaining: {recommendation.budget_remaining_pct:.1f}%",
                    f"Severity: {recommendation.severity}",
                ],
                project_slug=self.executor._get_project_slug(),
            )
        except Exception as e:
            logger.warning(f"[IMP-COST-005] Failed to log cost pause event: {e}")

    def _get_memory_context(self, phase_type: str, goal: str) -> str:
        """Retrieve memory context for builder injection.

        Queries vector memory for historical context (past errors, successful strategies,
        doctor hints) related to the phase and injects it into the builder prompt.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            goal: Phase goal/description

        Returns:
            Formatted context string for prompt injection, or empty string if memory disabled
        """
        # Get project ID for memory queries
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        try:
            injector = ContextInjector()
            injection = injector.get_context_for_phase(
                phase_type=phase_type,
                current_goal=goal,
                project_id=project_id,
                max_tokens=500,
            )

            if injection.total_token_estimate > 0:
                logger.info(
                    f"[IMP-ARCH-002] Injecting {injection.total_token_estimate} tokens of memory context "
                    f"({len(injection.past_errors)} errors, "
                    f"{len(injection.successful_strategies)} strategies, "
                    f"{len(injection.doctor_hints)} hints, "
                    f"{len(injection.relevant_insights)} insights)"
                )

            return injector.format_for_prompt(injection)
        except Exception as e:
            logger.warning(f"[IMP-ARCH-002] Failed to retrieve memory context: {e}")
            return ""

    def _get_improvement_task_context(self) -> str:
        """Get improvement tasks as context for phase execution (IMP-ARCH-019).

        Formats loaded improvement tasks into a context string that guides
        the Builder to address self-improvement opportunities.

        Returns:
            Formatted context string, or empty string if no tasks
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return ""

        # Format tasks for injection
        lines = ["## Self-Improvement Tasks (from previous runs)"]
        lines.append("The following improvement opportunities were identified from telemetry:")
        lines.append("")

        for i, task in enumerate(improvement_tasks[:5], 1):  # Limit to 5 tasks
            priority = task.get("priority", "medium")
            title = task.get("title", "Unknown task")
            description = task.get("description", "")[:200]  # Truncate long descriptions
            files = task.get("suggested_files", [])

            lines.append(f"### {i}. [{priority.upper()}] {title}")
            if description:
                lines.append(f"{description}")
            if files:
                lines.append(f"Suggested files: {', '.join(files[:3])}")
            lines.append("")

        lines.append("Consider addressing these issues if relevant to the current phase.")

        context = "\n".join(lines)
        logger.info(
            f"[IMP-ARCH-019] Injecting {len(improvement_tasks)} improvement tasks into phase context"
        )
        return context

    def _estimate_tokens(self, context: str) -> int:
        """Estimate token count for a context string.

        Uses a rough heuristic of ~4 characters per token (common for English text).
        This is a fast approximation; actual token counts vary by model and content.

        Args:
            context: The context string to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not context:
            return 0
        # Rough estimate: ~4 characters per token (typical for English)
        return len(context) // 4

    def _truncate_to_budget(self, context: str, token_budget: int) -> str:
        """Truncate context to fit within a token budget.

        Prioritizes keeping the most recent content (end of string).
        Truncates from the beginning to preserve recent context.

        Args:
            context: The context string to truncate.
            token_budget: Maximum tokens allowed.

        Returns:
            Truncated context string that fits within budget.
        """
        if token_budget <= 0:
            return ""

        current_tokens = self._estimate_tokens(context)
        if current_tokens <= token_budget:
            return context

        # Calculate approximate character limit (4 chars per token)
        char_budget = token_budget * 4

        # Truncate from beginning, keeping most recent content
        truncated = context[-char_budget:]

        # Try to find a clean break point (newline or space)
        clean_break = truncated.find("\n")
        if clean_break == -1:
            clean_break = truncated.find(" ")

        if clean_break > 0 and clean_break < len(truncated) // 2:
            truncated = truncated[clean_break + 1 :]

        return truncated

    def _inject_context_with_ceiling(self, context: str) -> str:
        """Inject context while enforcing the total context ceiling.

        IMP-PERF-002: Prevents unbounded context accumulation across phases.
        Tracks total context tokens injected and truncates when ceiling is reached.

        Args:
            context: The context string to inject.

        Returns:
            The context string (potentially truncated to fit within ceiling).
        """
        if not context:
            return ""

        context_tokens = self._estimate_tokens(context)

        if self._total_context_tokens + context_tokens > self._context_ceiling:
            remaining_budget = self._context_ceiling - self._total_context_tokens

            if remaining_budget <= 0:
                logger.warning(
                    f"[IMP-PERF-002] Context ceiling reached ({self._context_ceiling} tokens). "
                    f"Skipping context injection entirely."
                )
                return ""

            logger.warning(
                f"[IMP-PERF-002] Context ceiling approaching ({self._total_context_tokens}/{self._context_ceiling} tokens). "
                f"Truncating injection from {context_tokens} to {remaining_budget} tokens."
            )
            # Prioritize most recent context
            context = self._truncate_to_budget(context, remaining_budget)
            context_tokens = self._estimate_tokens(context)

        self._total_context_tokens += context_tokens
        logger.debug(
            f"[IMP-PERF-002] Context injected: {context_tokens} tokens "
            f"(total: {self._total_context_tokens}/{self._context_ceiling})"
        )
        return context

    def _mark_improvement_tasks_completed(self) -> None:
        """Mark improvement tasks as completed after successful run (IMP-ARCH-019).

        Called when run finishes with no failed phases, indicating the improvement
        tasks were successfully addressed.
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)
            completed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    result = generator.mark_task_status(
                        task_id, "completed", executed_in_run_id=self.executor.run_id
                    )
                    if result == "updated":
                        completed_count += 1

            if completed_count > 0:
                logger.info(
                    f"[IMP-ARCH-019] Marked {completed_count} improvement tasks as completed"
                )

        except Exception as e:
            logger.warning(f"[IMP-ARCH-019] Failed to mark tasks completed: {e}")

    def _mark_improvement_tasks_failed(self, phases_failed: int) -> None:
        """Mark improvement tasks as failed/retry when run has failures (IMP-LOOP-005).

        Called when run finishes with failed phases, indicating the improvement
        tasks were not successfully addressed and need retry or failure tracking.

        Args:
            phases_failed: Number of phases that failed in this run
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)
            retry_count = 0
            failed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    result = generator.mark_task_status(
                        task_id,
                        status=None,  # Let method decide based on retry count
                        increment_retry=True,
                        failure_run_id=self.executor.run_id,
                    )
                    if result == "retry":
                        retry_count += 1
                    elif result == "failed":
                        failed_count += 1

            if retry_count > 0 or failed_count > 0:
                logger.info(
                    f"[IMP-LOOP-005] Task status update: {retry_count} tasks returned to pending, "
                    f"{failed_count} tasks marked as failed"
                )

        except Exception as e:
            logger.warning(f"[IMP-LOOP-005] Failed to update task status: {e}")

    def _adaptive_sleep(self, is_idle: bool = False, base_interval: Optional[float] = None):
        """Sleep with adaptive backoff when idle to reduce CPU usage.

        Args:
            is_idle: If True, apply backoff multiplier to reduce CPU usage when no phases available
            base_interval: Override base interval for this sleep (defaults to self.poll_interval)
        """
        interval = base_interval if base_interval is not None else self.poll_interval
        if is_idle:
            # Apply backoff multiplier and cap at max_idle_sleep
            sleep_time = min(interval * self.idle_backoff_multiplier, self.max_idle_sleep)
        else:
            sleep_time = interval
        # NOTE: time.sleep() intentional - autonomous loop runs in sync context
        time.sleep(sleep_time)
        return sleep_time

    def _log_db_pool_health(self) -> None:
        """Log database pool health to telemetry (IMP-DB-001).

        Monitors connection pool for:
        - Pool exhaustion (high utilization)
        - Connection leaks (long-held connections)
        - Hot code paths (frequent connections)
        """
        from autopack.database import get_pool_health

        if not settings.db_pool_monitoring_enabled:
            return

        try:
            pool_health = get_pool_health()

            # Log high utilization warning
            if pool_health.utilization_pct > 80:
                logger.warning(
                    f"[IMP-DB-001] Database pool utilization high: {pool_health.utilization_pct:.1f}% "
                    f"({pool_health.checked_out}/{pool_health.pool_size})"
                )

            # Log potential leaks
            if pool_health.potential_leaks:
                logger.warning(
                    f"[IMP-DB-001] Detected {len(pool_health.potential_leaks)} potential connection leaks. "
                    f"Longest checkout: {pool_health.longest_checkout_sec:.1f}s"
                )

            # Debug logging for monitoring
            logger.debug(
                f"[IMP-DB-001] Pool health - "
                f"Size: {pool_health.pool_size}, "
                f"CheckedOut: {pool_health.checked_out}, "
                f"Overflow: {pool_health.overflow}, "
                f"Utilization: {pool_health.utilization_pct:.1f}%"
            )
        except Exception as e:
            logger.warning(f"[IMP-DB-001] Failed to collect pool health metrics: {e}")

    def run(
        self,
        poll_interval: float = 0.5,
        max_iterations: int = 50,
        stop_on_first_failure: bool = False,
    ):
        """Run autonomous execution loop.

        Args:
            poll_interval: Seconds to wait between polling for next phase (default: 0.5s, reduced from 1.0s for better performance)
            max_iterations: Maximum number of phases to execute (default: 50 to prevent runaway execution)
            stop_on_first_failure: If True, stop immediately when any phase fails

        Returns:
            Execution statistics dictionary
        """
        logger.info("Starting autonomous execution loop...")
        logger.info(f"Poll interval: {poll_interval}s")
        if max_iterations:
            logger.info(f"Max iterations: {max_iterations}")

        # Ensure API server is running (auto-start if needed)
        if not self.executor._ensure_api_server_running():
            logger.error("Cannot proceed without API server. Exiting.")
            return

        # P0: Sanity check - verify run exists in API database before proceeding
        # This detects DB identity mismatch (API using different DB than expected)
        self._verify_run_exists()

        # Initialize infrastructure
        self.executor._init_infrastructure()

        # Initialize intention-first loop
        self._initialize_intention_loop()

        # IMP-AUTO-002: Initialize parallelism checker after intention loop
        # (needs intention anchor for policy checks)
        self._initialize_parallelism_checker()

        # IMP-LOOP-001: Initialize feedback pipeline for self-improvement loop
        self._initialize_feedback_pipeline()

        # Main execution loop
        stats = self._execute_loop(poll_interval, max_iterations, stop_on_first_failure)

        # Handle cleanup and finalization
        self._finalize_execution(stats)

    def _verify_run_exists(self):
        """Verify that the run exists in the API database."""
        from autopack.supervisor.api_client import SupervisorApiHttpError

        try:
            self.executor.api_client.get_run(self.executor.run_id, timeout=10)
            logger.info(f"✅ Run '{self.executor.run_id}' verified in API database")
        except SupervisorApiHttpError as e:
            if e.status_code == 404:
                logger.error("=" * 70)
                logger.error("[DB_MISMATCH] RUN NOT FOUND IN API DATABASE")
                logger.error("=" * 70)
                logger.error(f"API server is healthy but run '{self.executor.run_id}' not found")
                logger.error("This indicates database identity mismatch:")
                logger.error(
                    f"  - Executor DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}"
                )
                logger.error("  - API server may be using different database")
                logger.error("")
                logger.error("Recommended fixes:")
                logger.error("  1. Verify DATABASE_URL is set correctly before starting executor")
                logger.error("  2. Verify run was seeded in the correct database")
                logger.error("  3. Check API server logs for actual DATABASE_URL used")
                logger.error("  4. Use absolute paths for SQLite (not relative)")
                logger.error("=" * 70)
                raise RuntimeError(
                    f"Run '{self.executor.run_id}' not found in API database. "
                    f"Database identity mismatch detected. "
                    f"Cannot proceed - would cause 404 errors on every API call."
                )
            else:
                # Non-404 error
                logger.warning(f"Could not verify run existence (non-404 error): {e}")
                # Continue anyway - might be transient API error
        except Exception as e:
            logger.warning(f"Could not verify run existence: {e}")
            # Continue anyway - don't block execution on sanity check failure

    def _load_improvement_tasks(self) -> List[dict]:
        """Load pending improvement tasks from previous runs (IMP-ARCH-012).

        Part of the self-improvement feedback loop:
        - Tasks are generated from telemetry insights (IMP-ARCH-009)
        - Tasks are persisted to database (IMP-ARCH-011)
        - This method retrieves pending tasks for execution

        Returns:
            List of task dicts compatible with phase planning
        """
        # Check if task generation is enabled
        if not getattr(settings, "task_generation_enabled", False):
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)
            max_tasks = getattr(settings, "task_generation_max_tasks_per_run", 5)
            pending_tasks = generator.get_pending_tasks(status="pending", limit=max_tasks)

            if not pending_tasks:
                logger.debug("[IMP-ARCH-012] No pending improvement tasks found")
                return []

            # Convert to planning-compatible format
            task_items = []
            for task in pending_tasks:
                task_items.append(
                    {
                        "task_id": task.task_id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "suggested_files": task.suggested_files,
                        "source": "self_improvement",
                        "estimated_effort": task.estimated_effort,
                    }
                )
                # Mark as in_progress
                generator.mark_task_status(
                    task.task_id, "in_progress", executed_in_run_id=self.executor.run_id
                )

            logger.info(f"[IMP-ARCH-012] Loaded {len(task_items)} improvement tasks for this run")
            return task_items

        except Exception as e:
            logger.warning(f"[IMP-ARCH-012] Failed to load improvement tasks: {e}")
            return []

    def _fetch_generated_tasks(self) -> List[Dict]:
        """Fetch generated tasks and convert them to executable phase specs (IMP-LOOP-004).

        This method closes the autonomous improvement loop by:
        1. Retrieving pending tasks from the database via task_generator.get_pending_tasks()
        2. Converting GeneratedTask objects into executable phase specifications
        3. Marking tasks as "in_progress" when they start execution

        The generated phases use the "generated-task-execution" phase type which
        routes to the specialized handler in phase_dispatch.py.

        Returns:
            List of phase spec dicts ready for execution, or empty list if disabled/no tasks.
        """
        # Check if task execution is enabled (separate from task generation)
        if not settings.task_generation_auto_execute:
            logger.debug("[IMP-LOOP-004] Generated task execution is disabled")
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)

            # Fetch pending tasks (limit to avoid overwhelming the run)
            max_tasks_per_run = settings.task_generation_max_tasks_per_run
            pending_tasks = generator.get_pending_tasks(status="pending", limit=max_tasks_per_run)

            if not pending_tasks:
                logger.debug("[IMP-LOOP-004] No pending generated tasks to execute")
                return []

            # Convert GeneratedTask objects to executable phase specs
            phase_specs = []
            for task in pending_tasks:
                # Map task priority to phase priority
                priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4}
                priority_order = priority_map.get(task.priority, 3)

                # Build phase spec from GeneratedTask
                phase_spec = {
                    "phase_id": f"generated-task-execution-{task.task_id}",
                    "phase_type": "generated-task-execution",
                    "description": f"[AUTO] {task.title}\n\n{task.description}",
                    "status": "QUEUED",
                    "priority_order": priority_order,
                    "category": "improvement",
                    "scope": {
                        "paths": task.suggested_files or [],
                    },
                    # Store task metadata for handler access
                    "_generated_task": {
                        "task_id": task.task_id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "source_insights": task.source_insights,
                        "suggested_files": task.suggested_files,
                        "estimated_effort": task.estimated_effort,
                        "run_id": task.run_id,
                    },
                }
                phase_specs.append(phase_spec)

                # Mark task as in_progress
                generator.mark_task_status(
                    task.task_id, "in_progress", executed_in_run_id=self.executor.run_id
                )
                logger.info(
                    f"[IMP-LOOP-004] Queued generated task {task.task_id} for execution: {task.title}"
                )

            logger.info(f"[IMP-LOOP-004] Fetched {len(phase_specs)} generated tasks for execution")
            return phase_specs

        except Exception as e:
            logger.warning(f"[IMP-LOOP-004] Failed to fetch generated tasks: {e}")
            return []

    def _inject_generated_tasks_into_backlog(self, run_data: Dict) -> Dict:
        """Inject generated tasks into the phase backlog before execution (IMP-LOOP-004).

        This method modifies the run_data to include generated task phases,
        allowing them to be picked up by get_next_queued_phase() and executed
        alongside regular phases.

        Args:
            run_data: The current run data dict containing phases

        Returns:
            Modified run_data with generated task phases injected
        """
        generated_phases = self._fetch_generated_tasks()
        if not generated_phases:
            return run_data

        # Get existing phases
        existing_phases = run_data.get("phases", [])

        # Inject generated task phases at the end (after user-defined phases)
        # They will be picked up when no other queued phases remain
        run_data["phases"] = existing_phases + generated_phases

        logger.info(
            f"[IMP-LOOP-004] Injected {len(generated_phases)} generated task phases into backlog"
        )
        return run_data

    def _initialize_intention_loop(self):
        """Initialize intention-first loop for the run."""
        from autopack.autonomous.executor_wiring import \
            initialize_intention_first_loop
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        # IMP-ARCH-012: Load pending improvement tasks from self-improvement loop
        improvement_tasks = self._load_improvement_tasks()
        if improvement_tasks:
            # Store improvement tasks for injection into phase planning
            self.executor._improvement_tasks = improvement_tasks
        else:
            self.executor._improvement_tasks = []

        # Load intention anchor for this run
        try:
            intention_anchor = IntentionAnchorStorage.load_anchor(self.executor.run_id)
            if intention_anchor is None:
                logger.warning(
                    f"[IntentionFirst] No intention anchor found for run {self.executor.run_id}, using defaults"
                )
                # Create minimal default anchor if none exists
                from datetime import datetime, timezone

                from autopack.intention_anchor.models import (
                    IntentionAnchor, IntentionBudgets, IntentionConstraints)

                intention_anchor = IntentionAnchor(
                    anchor_id=f"default-{self.executor.run_id}",
                    run_id=self.executor.run_id,
                    project_id="default",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    version=1,
                    north_star="Execute run according to phase specifications",
                    success_criteria=["All phases complete successfully"],
                    constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
                    budgets=IntentionBudgets(
                        max_context_chars=settings.run_token_cap * 4,  # Rough char estimate
                        max_sot_chars=500_000,
                    ),
                )
            logger.info(
                f"[IntentionFirst] Loaded intention anchor: {intention_anchor.anchor_id} (v{intention_anchor.version})"
            )

            # Initialize the intention-first loop with routing snapshot + state tracking
            wiring = initialize_intention_first_loop(
                run_id=self.executor.run_id,
                project_id=intention_anchor.project_id,
                intention_anchor=intention_anchor,
            )
            logger.info(
                f"[IntentionFirst] Initialized loop with routing snapshot: {wiring.run_state.routing_snapshot.snapshot_id}"
            )
            # Store wiring state as instance variable for phase execution
            self.executor._intention_wiring = wiring
            self.executor._intention_anchor = intention_anchor
        except Exception as e:
            logger.warning(
                f"[IntentionFirst] Failed to initialize intention-first loop: {e}, continuing without it"
            )
            self.executor._intention_wiring = None
            self.executor._intention_anchor = None

    def _execute_loop(
        self, poll_interval: float, max_iterations: int, stop_on_first_failure: bool
    ) -> Dict:
        """Execute the main autonomous loop.

        Returns:
            Dictionary with execution statistics
        """
        iteration = 0
        phases_executed = 0
        phases_failed = 0
        stop_signal_file = Path(".autonomous_runs/.stop_executor")
        stop_reason: str | None = None

        # IMP-REL-004: Use effective max iterations with fallback to default
        effective_max_iterations = max_iterations if max_iterations else DEFAULT_MAX_ITERATIONS

        while iteration < effective_max_iterations:
            # Check for stop signal (from monitor script)
            if stop_signal_file.exists():
                signal_content = stop_signal_file.read_text().strip()
                if signal_content.startswith(f"stop:{self.executor.run_id}"):
                    logger.critical(f"[STOP_SIGNAL] Stop signal detected: {signal_content}")
                    logger.info("Stopping execution as requested by monitor")
                    stop_signal_file.unlink()  # Remove signal file
                    stop_reason = "stop_signal"
                    break

            # Periodic database session health check (prevents stale connections in long runs)
            current_time = time.time()
            if current_time - self._last_session_health_check >= SESSION_HEALTH_CHECK_INTERVAL:
                if hasattr(self.executor, "db_session") and self.executor.db_session:
                    ensure_session_healthy(self.executor.db_session)
                    self._last_session_health_check = current_time
                    logger.debug("[SessionHealth] Periodic session health check completed")

            iteration += 1

            # IMP-DB-001: Log database pool health at start of each iteration
            self._log_db_pool_health()

            # IMP-SAFETY-005: Check budget exhaustion EARLY, before any token-consuming operations
            # This prevents operations like context loading from consuming tokens when budget is already exhausted
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)
            token_cap = settings.run_token_cap
            if is_budget_exhausted(token_cap, tokens_used):
                budget_remaining = get_budget_remaining_pct(token_cap, tokens_used)
                error_msg = (
                    f"Run aborted: token budget exhausted ({tokens_used}/{token_cap} tokens used). "
                    f"Budget remaining: {budget_remaining:.1%}. "
                    f"Increase run_token_cap in config or review phase efficiency."
                )
                logger.critical(f"[BUDGET_EXHAUSTED] {error_msg}")
                stop_reason = "budget_exhausted"
                raise BudgetExhaustedError(error_msg)

            # IMP-COST-005: Check cost recommendations before proceeding
            # This provides a softer pause at 95% budget to prevent reaching hard stop
            cost_recommendation = self._check_cost_recommendations()
            if cost_recommendation.should_pause:
                logger.warning(
                    f"[IMP-COST-005] Cost pause recommended: {cost_recommendation.reason}. "
                    f"Current spend: {cost_recommendation.current_spend:,.0f} tokens"
                )
                self._pause_for_cost_limit(cost_recommendation)
                stop_reason = "cost_limit_reached"
                break

            # IMP-LOOP-006: Check circuit breaker state before proceeding
            if self._circuit_breaker is not None:
                try:
                    self._circuit_breaker.check_state()
                except CircuitBreakerOpenError as e:
                    logger.critical(
                        f"[IMP-LOOP-006] Circuit breaker OPEN - execution blocked. "
                        f"{e.consecutive_failures} consecutive failures. "
                        f"Reset in {e.reset_time:.0f}s."
                    )
                    stop_reason = "circuit_breaker_open"
                    break

            # Fetch run status
            logger.info(f"Iteration {iteration}: Fetching run status...")
            try:
                run_data = self.executor.get_run_status()
            except Exception as e:
                logger.error(f"Failed to fetch run status: {e}")
                logger.info(f"Waiting {poll_interval}s before retry...")
                self._adaptive_sleep(is_idle=True, base_interval=poll_interval)
                continue

            # IMP-LOOP-004: Inject generated tasks into backlog for execution
            # This closes the autonomous improvement loop by executing tasks generated
            # from telemetry insights in previous runs
            try:
                run_data = self._inject_generated_tasks_into_backlog(run_data)
            except Exception as e:
                logger.warning(
                    f"[IMP-LOOP-004] Failed to inject generated tasks (non-blocking): {e}"
                )

            # Auto-fix queued phases (normalize deliverables/scope, tune CI timeouts) before selection.
            try:
                self.executor._autofix_queued_phases(run_data)
            except Exception as e:
                logger.warning(f"[AutoFix] Failed to auto-fix queued phases (non-blocking): {e}")

            # NEW: Initialize goal anchor on first iteration (for drift detection)
            if iteration == 1 and not hasattr(self.executor, "_run_goal_anchor"):
                # Try to get goal_anchor from run data, or extract from first phase
                goal_anchor = run_data.get("goal_anchor")
                if not goal_anchor:
                    # Fall back to extracting from run description or first phase description
                    run_description = run_data.get("description", "")
                    if run_description:
                        goal_anchor = extract_goal_from_description(run_description)
                    else:
                        # Try first phase
                        phases = run_data.get("phases", [])
                        if phases:
                            first_phase_desc = phases[0].get("description", "")
                            goal_anchor = extract_goal_from_description(first_phase_desc)
                if goal_anchor:
                    self.executor._run_goal_anchor = goal_anchor
                    logger.info(f"[GoalAnchor] Initialized: {goal_anchor[:100]}...")

            # IMP-SOT-001: Check SOT drift at runtime during autonomous execution
            try:
                self._check_sot_drift()
            except SOTDriftError as e:
                logger.critical(f"[IMP-SOT-001] {str(e)}")
                stop_reason = "sot_drift_detected"
                raise

            # Phase 1.6-1.7: Detect and reset stale EXECUTING phases
            try:
                self.executor._detect_and_reset_stale_phases(run_data)
            except Exception as e:
                logger.warning(f"Stale phase detection failed: {e}")
                # Continue even if stale detection fails

            # BUILD-115: Use API-based phase selection instead of obsolete database queries
            next_phase = self.executor.get_next_queued_phase(run_data)

            if not next_phase:
                logger.info("No more executable phases, execution complete")
                stop_reason = "no_more_executable_phases"
                break

            phase_id = next_phase.get("phase_id")
            phase_type = next_phase.get("phase_type")
            logger.info(f"[BUILD-041] Next phase: {phase_id}")

            # Log budget status before each phase (budget check moved to top of loop per IMP-SAFETY-005)
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)
            token_cap = settings.run_token_cap
            budget_pct = get_budget_remaining_pct(token_cap, tokens_used) * 100
            logger.info(
                f"Phase {phase_id}: Budget remaining {budget_pct:.1f}% ({tokens_used}/{token_cap} tokens)"
            )

            # IMP-AUTO-002: Try parallel execution if enabled and possible
            parallel_result = None
            try:
                parallel_result = self._try_parallel_execution(run_data, next_phase)
            except Exception as parallel_err:
                logger.warning(
                    f"[IMP-AUTO-002] Parallel execution attempt failed (falling back to sequential): "
                    f"{parallel_err}"
                )

            if parallel_result is not None:
                # Parallel execution occurred
                results, parallel_count = parallel_result
                logger.info(f"[IMP-AUTO-002] Parallel execution completed: {parallel_count} phases")

                # Process results from parallel execution
                for phase, success, status in results:
                    phase_id_result = phase.get("phase_id", "unknown")
                    phase_type_result = phase.get("phase_type")

                    # IMP-FBK-001: Update task effectiveness for parallel phase
                    try:
                        # Note: For parallel phases we don't have precise execution time
                        # Use a default estimate based on typical parallel execution
                        tokens_used = getattr(self.executor, "_run_tokens_used", 0)
                        self._update_task_effectiveness(
                            phase_id=phase_id_result,
                            phase_type=phase_type_result,
                            success=success,
                            execution_time_seconds=0.0,  # Unknown for parallel execution
                            tokens_used=tokens_used // max(1, parallel_count),  # Estimate per phase
                        )
                    except Exception as effectiveness_err:
                        logger.warning(
                            f"[IMP-FBK-001] Task effectiveness tracking failed (non-fatal): {effectiveness_err}"
                        )

                    if success:
                        logger.info(f"Phase {phase_id_result} completed successfully (parallel)")
                        phases_executed += 1
                        self.executor._phase_failure_counts[phase_id_result] = 0

                        if self._circuit_breaker is not None:
                            self._circuit_breaker.record_success()

                        # IMP-INT-001: Aggregate telemetry after parallel phase completion
                        try:
                            self._aggregate_phase_telemetry(phase_id_result)
                        except Exception as agg_err:
                            logger.warning(
                                f"[IMP-INT-001] Telemetry aggregation failed (non-fatal): {agg_err}"
                            )
                    else:
                        logger.warning(
                            f"Phase {phase_id_result} finished with status: {status} (parallel)"
                        )
                        phases_failed += 1

                        if self._circuit_breaker is not None:
                            self._circuit_breaker.record_failure()
                            if self._circuit_breaker.is_open:
                                logger.critical(
                                    f"[IMP-LOOP-006] Circuit breaker tripped after parallel "
                                    f"phase {phase_id_result} failure."
                                )
                                stop_reason = "circuit_breaker_tripped"
                                break

                        if stop_on_first_failure:
                            logger.critical(
                                f"[STOP_ON_FAILURE] Parallel phase {phase_id_result} failed. "
                                f"Stopping execution."
                            )
                            stop_reason = "stop_on_first_failure"
                            break

                # Check if we need to break from the main loop
                if stop_reason in ("circuit_breaker_tripped", "stop_on_first_failure"):
                    break

                # IMP-INT-005: Immediate cost check after parallel execution completes
                # Check cost recommendations before waiting, to stop faster if budget is exceeded
                parallel_cost = self._check_cost_recommendations()
                if parallel_cost.should_pause:
                    logger.warning(
                        f"[IMP-INT-005] Cost pause triggered after parallel execution: "
                        f"{parallel_cost.reason}. "
                        f"Current spend: {parallel_cost.current_spend:,.0f} tokens. "
                        f"Budget remaining: {parallel_cost.budget_remaining_pct:.1f}%"
                    )
                    self._pause_for_cost_limit(parallel_cost)
                    stop_reason = "cost_limit_reached"
                    break

                # Skip to next iteration since we handled all phases in parallel
                if iteration < max_iterations:
                    logger.info(f"Waiting {poll_interval}s before next phase...")
                    self._adaptive_sleep(is_idle=False, base_interval=poll_interval)
                continue

            # Sequential execution path (original logic)
            # Telemetry-driven phase adjustments (IMP-TEL-002)
            phase_adjustments = self._get_telemetry_adjustments(phase_type)

            # IMP-ARCH-002: Retrieve memory context for builder injection
            phase_goal = next_phase.get("description", "")
            memory_context = self._get_memory_context(phase_type, phase_goal)

            # IMP-LOOP-001: Retrieve enhanced context from feedback pipeline
            feedback_context = self._get_feedback_pipeline_context(phase_type, phase_goal)

            # IMP-ARCH-019: Inject improvement tasks into phase context
            improvement_context = self._get_improvement_task_context()

            # Combine all context sources
            combined_context = ""
            if memory_context:
                combined_context = memory_context
            if feedback_context:
                combined_context = (
                    combined_context + "\n\n" + feedback_context
                    if combined_context
                    else feedback_context
                )
            if improvement_context:
                combined_context = (
                    combined_context + "\n\n" + improvement_context
                    if combined_context
                    else improvement_context
                )

            # IMP-PERF-002: Apply context ceiling enforcement
            if combined_context:
                combined_context = self._inject_context_with_ceiling(combined_context)
                if combined_context:
                    phase_adjustments["memory_context"] = combined_context

            # IMP-LOOP-005: Record execution start time for feedback
            execution_start_time = time.time()

            # Execute phase (with any telemetry-driven adjustments and memory context)
            success, status = self.executor.execute_phase(next_phase, **phase_adjustments)

            # IMP-LOOP-005: Record execution feedback to memory for learning
            try:
                self._record_execution_feedback(
                    phase=next_phase,
                    success=success,
                    status=status,
                    execution_start_time=execution_start_time,
                    memory_context=combined_context if combined_context else None,
                )
            except Exception as feedback_err:
                # Non-fatal - continue execution even if feedback fails
                logger.warning(
                    f"[IMP-LOOP-005] Execution feedback recording failed (non-fatal): {feedback_err}"
                )

            # IMP-LOOP-001: Process outcome through unified feedback pipeline
            try:
                self._process_phase_with_feedback_pipeline(
                    phase=next_phase,
                    success=success,
                    status=status,
                    execution_start_time=execution_start_time,
                )
            except Exception as pipeline_err:
                # Non-fatal - continue execution even if feedback pipeline fails
                logger.warning(
                    f"[IMP-LOOP-001] Feedback pipeline processing failed (non-fatal): {pipeline_err}"
                )

            # IMP-FBK-001: Update task effectiveness tracking for closed-loop learning
            try:
                execution_time = time.time() - execution_start_time
                tokens_used = getattr(self.executor, "_run_tokens_used", 0)
                self._update_task_effectiveness(
                    phase_id=phase_id,
                    phase_type=phase_type,
                    success=success,
                    execution_time_seconds=execution_time,
                    tokens_used=tokens_used,
                )
            except Exception as effectiveness_err:
                # Non-fatal - continue execution even if effectiveness tracking fails
                logger.warning(
                    f"[IMP-FBK-001] Task effectiveness tracking failed (non-fatal): {effectiveness_err}"
                )

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
                phases_executed += 1
                # Reset failure count on success
                self.executor._phase_failure_counts[phase_id] = 0

                # IMP-LOOP-006: Record success with circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_success()

                # IMP-INT-001: Aggregate telemetry after phase completion for self-improvement
                try:
                    self._aggregate_phase_telemetry(phase_id)
                except Exception as agg_err:
                    # Non-fatal - continue execution even if telemetry aggregation fails
                    logger.warning(
                        f"[IMP-INT-001] Telemetry aggregation failed (non-fatal): {agg_err}"
                    )

                # IMP-AUTOPILOT-001: Periodic autopilot invocation after successful phases
                if (
                    hasattr(self.executor, "autopilot")
                    and self.executor.autopilot
                    and hasattr(self.executor, "_autopilot_phase_count")
                    and isinstance(self.executor._autopilot_phase_count, int)
                ):
                    self.executor._autopilot_phase_count += 1
                    if (
                        self.executor._autopilot_phase_count % settings.autopilot_gap_scan_frequency
                        == 0
                    ):
                        logger.info(
                            f"[IMP-AUTOPILOT-001] Invoking autopilot after {self.executor._autopilot_phase_count} phases"
                        )
                        try:
                            self._invoke_autopilot_session()
                        except Exception as e:
                            logger.warning(
                                f"[IMP-AUTOPILOT-001] Autopilot session failed (non-blocking): {e}"
                            )
            else:
                logger.warning(f"Phase {phase_id} finished with status: {status}")
                phases_failed += 1

                # IMP-LOOP-006: Record failure with circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                    # Check if circuit just tripped
                    if self._circuit_breaker.is_open:
                        logger.critical(
                            f"[IMP-LOOP-006] Circuit breaker tripped after phase {phase_id} failure. "
                            f"Total trips: {self._circuit_breaker.total_trips}. "
                            f"Execution will be blocked until reset."
                        )
                        stop_reason = "circuit_breaker_tripped"
                        break

                # NEW: Stop on first failure if requested (saves token usage)
                if stop_on_first_failure:
                    logger.critical(
                        f"[STOP_ON_FAILURE] Phase {phase_id} failed with status: {status}. "
                        f"Stopping execution to save token usage."
                    )
                    logger.info(
                        f"Total phases executed: {phases_executed}, failed: {phases_failed}"
                    )
                    stop_reason = "stop_on_first_failure"
                    break

            # IMP-INT-005: Immediate cost check after phase completion
            # Check cost recommendations before waiting, to stop faster if budget is exceeded
            post_phase_cost = self._check_cost_recommendations()
            if post_phase_cost.should_pause:
                logger.warning(
                    f"[IMP-INT-005] Cost pause triggered after phase {phase_id}: "
                    f"{post_phase_cost.reason}. "
                    f"Current spend: {post_phase_cost.current_spend:,.0f} tokens. "
                    f"Budget remaining: {post_phase_cost.budget_remaining_pct:.1f}%"
                )
                self._pause_for_cost_limit(post_phase_cost)
                stop_reason = "cost_limit_reached"
                break

            # Wait before next iteration
            if iteration < effective_max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                self._adaptive_sleep(is_idle=False, base_interval=poll_interval)
        else:
            # IMP-REL-004: Max iterations reached - log warning and set stop reason
            logger.warning(
                f"Execution loop reached max iterations ({effective_max_iterations}), "
                "stopping to prevent resource exhaustion"
            )
            stop_reason = "max_iterations"

        logger.info("Autonomous execution loop finished")

        # IMP-LOOP-006: Update instance-level counters
        self._iteration_count = iteration
        self._total_phases_executed = phases_executed
        self._total_phases_failed = phases_failed

        # Build stats with optional circuit breaker info
        stats = {
            "iteration": iteration,
            "phases_executed": phases_executed,
            "phases_failed": phases_failed,
            "stop_reason": stop_reason,
        }

        # IMP-LOOP-006: Include circuit breaker statistics
        if self._circuit_breaker is not None:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()

        return stats

    def _finalize_execution(self, stats: Dict):
        """Finalize execution and handle cleanup.

        Args:
            stats: Execution statistics dictionary
        """
        iteration = stats["iteration"]
        phases_executed = stats["phases_executed"]
        phases_failed = stats["phases_failed"]
        stop_reason = stats["stop_reason"]

        # IMPORTANT: Only finalize a run when there are no executable phases remaining.
        # If we stop due to max-iterations/stop-signal/stop-on-failure, the run should remain resumable
        # (i.e., do NOT force it into a DONE_* state).
        if stop_reason == "no_more_executable_phases":
            # IMP-LOOP-001: Persist telemetry insights with graceful error handling
            self._persist_loop_insights()

            # IMP-ARCH-009: Generate improvement tasks from telemetry for self-improvement loop
            try:
                self._generate_improvement_tasks()
            except Exception as e:
                logger.warning(f"Failed to generate improvement tasks: {e}")

            # Log run completion summary to CONSOLIDATED_BUILD.md
            try:
                log_build_event(
                    event_type="RUN_COMPLETE",
                    description=f"Run {self.executor.run_id} completed. Phases: {phases_executed} successful, {phases_failed} failed. Total iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.executor.run_id}",
                        f"Successful: {phases_executed}",
                        f"Failed: {phases_failed}",
                    ],
                    project_slug=self.executor._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run completion: {e}")

            # Best-effort fallback: ensure run_summary.md reflects terminal state even if API-side hook fails
            # Here we are truly finalizing the run (no executable phases remaining),
            # so allow mutating run.state to a terminal DONE_* state if needed.
            self.executor._best_effort_write_run_summary(
                phases_failed=phases_failed, allow_run_state_mutation=True
            )

            # IMP-ARCH-019: Mark improvement tasks as completed when run finishes successfully
            if phases_failed == 0:
                try:
                    self._mark_improvement_tasks_completed()
                except Exception as e:
                    logger.warning(f"Failed to mark improvement tasks as completed: {e}")
            else:
                # IMP-LOOP-005: Mark tasks as failed/retry when run has failures
                try:
                    self._mark_improvement_tasks_failed(phases_failed)
                except Exception as e:
                    logger.warning(f"Failed to mark improvement tasks as failed: {e}")

            # Learning Pipeline: Promote hints to persistent rules (Stage 0B)
            try:
                project_id = self.executor._get_project_slug()
                promoted_count = promote_hints_to_rules(self.executor.run_id, project_id)
                if promoted_count > 0:
                    logger.info(
                        f"Learning Pipeline: Promoted {promoted_count} hints to persistent project rules"
                    )
                    # Mark that rules have changed for future planning updates
                    self.executor._mark_rules_updated(project_id, promoted_count)
                else:
                    logger.info(
                        "Learning Pipeline: No hints qualified for promotion (need 2+ occurrences)"
                    )
            except Exception as e:
                logger.warning(f"Failed to promote hints to rules: {e}")
        else:
            # Non-terminal stop: keep the run resumable.
            # Still log a lightweight event for visibility.
            try:
                log_build_event(
                    event_type="RUN_PAUSED",
                    description=f"Run {self.executor.run_id} paused (reason={stop_reason}). Iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.executor.run_id}",
                        f"Reason: {stop_reason}",
                        f"Iterations: {iteration}",
                    ],
                    project_slug=self.executor._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run pause: {e}")

    def _check_sot_drift(self) -> None:
        """Check for SOT drift at runtime.

        Implements IMP-SOT-001: Runtime validation that SOT documents (BUILD_HISTORY, DEBUG_LOG)
        remain consistent throughout autonomous execution. Detects drift early to prevent
        accumulation of stale documentation.

        Raises:
            SOTDriftError: If drift is detected and sot_drift_blocks_execution is enabled
        """
        # Import here to avoid circular imports
        from autopack.gaps.doc_drift import SOTDriftDetector

        # Check if runtime enforcement is enabled
        if not settings.sot_runtime_enforcement_enabled:
            return

        # Get project root (use executor's root if available)
        project_root = getattr(self.executor, "project_root", ".")

        # Run quick SOT consistency check
        detector = SOTDriftDetector(project_root=project_root)
        is_consistent, issues = detector.quick_check()

        if not is_consistent:
            issue_msg = "\n  - ".join(issues)
            warning_msg = f"SOT drift detected:\n  - {issue_msg}"
            logger.warning(f"[IMP-SOT-001] {warning_msg}")

            # Check if drift blocks execution
            if settings.sot_drift_blocks_execution:
                raise SOTDriftError(f"SOT drift blocking execution: {issues}")

    def _record_execution_feedback(
        self,
        phase: Dict,
        success: bool,
        status: str,
        execution_start_time: float,
        memory_context: Optional[str] = None,
    ) -> None:
        """Record task execution feedback to memory for learning.

        IMP-LOOP-005: Captures execution results (success/failure) and stores them
        in memory to enable learning from past executions and improve future context.

        Args:
            phase: The phase dictionary with execution details
            success: Whether the phase executed successfully
            status: The final status string from execution
            execution_start_time: Unix timestamp when execution started
            memory_context: Optional memory context that was injected for this phase
        """
        # Check if memory service is available
        memory_service = getattr(self.executor, "memory_service", None)
        if memory_service is None:
            logger.debug("[IMP-LOOP-005] Memory service not available, skipping feedback")
            return

        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_type = phase.get("phase_type")
            project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()
            run_id = getattr(self.executor, "run_id", "unknown")

            # Calculate execution time
            execution_time = time.time() - execution_start_time

            # Get tokens used for this phase (approximate)
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)

            # Build error message for failures
            error_message = None
            if not success:
                error_message = f"Phase failed with status: {status}"
                # Try to get more specific error info if available
                phase_result = getattr(self.executor, "_last_phase_result", None)
                if phase_result and isinstance(phase_result, dict):
                    error_detail = phase_result.get("error") or phase_result.get("message")
                    if error_detail:
                        error_message = f"{error_message}. Detail: {error_detail}"

            # Build context summary
            context_summary = None
            if memory_context:
                # Summarize the context that was used
                context_lines = memory_context.split("\n")[:10]
                context_summary = "\n".join(context_lines)

            # Extract learnings based on outcome
            learnings = []
            if success:
                learnings.append(f"Phase type '{phase_type}' completed successfully")
                if execution_time < 30:
                    learnings.append("Fast execution - phase was efficient")
                elif execution_time > 300:
                    learnings.append("Long execution time - may need optimization")
            else:
                learnings.append(f"Phase type '{phase_type}' failed with status: {status}")
                if "timeout" in status.lower():
                    learnings.append(
                        "Timeout occurred - consider increasing timeout or reducing scope"
                    )
                elif "budget" in status.lower():
                    learnings.append("Budget exhausted - consider reducing token usage")

            # Write feedback to memory
            memory_service.write_task_execution_feedback(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id,
                success=success,
                phase_type=phase_type,
                execution_time_seconds=execution_time,
                error_message=error_message,
                tokens_used=tokens_used,
                context_summary=context_summary,
                learnings=learnings,
            )

            logger.info(
                f"[IMP-LOOP-005] Recorded execution feedback for phase {phase_id} "
                f"(success={success}, time={execution_time:.1f}s)"
            )

        except Exception as e:
            # Non-fatal error - log and continue
            logger.warning(f"[IMP-LOOP-005] Failed to record execution feedback: {e}")

    def _invoke_autopilot_session(self):
        """Invoke autopilot to scan for gaps and execute approved improvements.

        IMP-AUTOPILOT-001: Periodic autopilot invocation during autonomous execution.
        Runs gap scanning, proposes improvements, and executes auto-approved actions.
        """
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        logger.info("[IMP-AUTOPILOT-001] Starting autopilot gap scan session...")

        # Load intention anchor for this run (provides constraints for autopilot)
        try:
            intention_anchor = IntentionAnchorStorage.load_anchor(self.executor.run_id)
            if intention_anchor is None:
                logger.warning(
                    f"[IMP-AUTOPILOT-001] No intention anchor found for run {self.executor.run_id}, "
                    f"using cached anchor or defaults"
                )
                # Fall back to cached anchor if available
                intention_anchor = getattr(self.executor, "_intention_anchor", None)
        except Exception as e:
            logger.warning(f"[IMP-AUTOPILOT-001] Failed to load intention anchor: {e}")
            intention_anchor = getattr(self.executor, "_intention_anchor", None)

        # Run autopilot session (gap scanning + proposal generation)
        try:
            proposals = self.executor.autopilot.run_session(
                intention_anchor=intention_anchor,
                max_proposals=settings.autopilot_max_proposals_per_session,
            )
            logger.info(
                f"[IMP-AUTOPILOT-001] Autopilot generated {len(proposals)} improvement proposals"
            )
        except Exception as e:
            logger.error(f"[IMP-AUTOPILOT-001] Autopilot session failed: {e}")
            return

        # Filter for auto-approved proposals
        auto_approved = [p for p in proposals if p.get("auto_approved", False)]
        if not auto_approved:
            logger.info(
                "[IMP-AUTOPILOT-001] No auto-approved proposals. "
                f"{len(proposals)} proposals require manual approval (see IMP-AUTOPILOT-002)."
            )
            return

        logger.info(
            f"[IMP-AUTOPILOT-001] Executing {len(auto_approved)} auto-approved improvement proposals"
        )

        # Execute auto-approved proposals
        for i, proposal in enumerate(auto_approved, 1):
            proposal_id = proposal.get("proposal_id", f"autopilot-{i}")
            gap_type = proposal.get("gap_type", "unknown")
            description = proposal.get("description", "No description")

            logger.info(
                f"[IMP-AUTOPILOT-001] [{i}/{len(auto_approved)}] Executing proposal {proposal_id}: "
                f"{gap_type} - {description[:80]}"
            )

            try:
                # Execute proposal through autopilot controller
                self.executor.autopilot.execute_proposal(proposal)
                logger.info(f"[IMP-AUTOPILOT-001] ✅ Proposal {proposal_id} executed successfully")
            except Exception as e:
                logger.warning(
                    f"[IMP-AUTOPILOT-001] ⚠️ Proposal {proposal_id} execution failed: {e}"
                )
                # Continue with next proposal (non-blocking)

        logger.info("[IMP-AUTOPILOT-001] Autopilot session completed")

    def _validate_telemetry_feedback(
        self,
        ranked_issues: Dict,
    ) -> tuple[bool, Dict, int]:
        """Validate telemetry feedback data before memory storage.

        IMP-LOOP-002: Ensures data integrity and proper feedback propagation
        between telemetry collection and memory service.

        Args:
            ranked_issues: Dictionary containing telemetry analysis results with
                          'top_cost_sinks', 'top_failure_modes', 'top_retry_causes'.

        Returns:
            Tuple of (is_valid, validated_issues, validation_error_count).
        """
        from autopack.memory.memory_service import TelemetryFeedbackValidator

        if not isinstance(ranked_issues, dict):
            logger.warning(
                f"[IMP-LOOP-002] Invalid telemetry feedback type: {type(ranked_issues).__name__}"
            )
            return False, {}, 1

        validated_issues: Dict = {}
        total_errors = 0

        issue_categories = ["top_cost_sinks", "top_failure_modes", "top_retry_causes"]
        insight_type_map = {
            "top_cost_sinks": "cost_sink",
            "top_failure_modes": "failure_mode",
            "top_retry_causes": "retry_cause",
        }

        for category in issue_categories:
            issues = ranked_issues.get(category, [])
            if not isinstance(issues, list):
                logger.warning(
                    f"[IMP-LOOP-002] Invalid {category} type: {type(issues).__name__}, expected list"
                )
                total_errors += 1
                validated_issues[category] = []
                continue

            validated_list = []
            for issue in issues:
                # Convert issue to insight format for validation
                insight = {
                    "insight_type": insight_type_map.get(category, "unknown"),
                    "description": issue.get("description", str(issue)),
                    "phase_id": issue.get("phase_id"),
                    "run_id": issue.get("run_id"),
                    "suggested_action": issue.get("suggested_action"),
                }

                is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
                if is_valid:
                    validated_list.append(issue)
                else:
                    total_errors += 1
                    logger.debug(f"[IMP-LOOP-002] Skipping invalid {category} issue: {errors}")
                    # Sanitize and include anyway for non-critical validation errors
                    sanitized = TelemetryFeedbackValidator.sanitize_insight(insight)
                    # Merge sanitized fields back into original issue
                    issue_copy = dict(issue)
                    issue_copy["description"] = sanitized.get("description", "")
                    validated_list.append(issue_copy)

            validated_issues[category] = validated_list

        is_valid = total_errors == 0
        if total_errors > 0:
            logger.info(
                f"[IMP-LOOP-002] Telemetry feedback validation: "
                f"{total_errors} issues sanitized/corrected"
            )

        return is_valid, validated_issues, total_errors

    def _persist_telemetry_insights(self) -> None:
        """Analyze and persist telemetry insights to memory after run completion.

        Implements IMP-ARCH-001: Wire Telemetry Analyzer to Memory Service.
        IMP-INT-002: Explicit bridge invocation after aggregation.
        IMP-LOOP-002: Added validation to ensure data integrity before persistence.

        Closes the ROAD-B feedback loop by persisting ranked issues to vector memory
        for retrieval in future runs.
        """
        analyzer = self._get_telemetry_analyzer()
        if not analyzer:
            logger.debug("[IMP-ARCH-001] No telemetry analyzer available")
            return

        try:
            # Analyze telemetry from the run and aggregate issues
            ranked_issues = analyzer.aggregate_telemetry(window_days=7)

            # IMP-INT-002: Persist aggregated insights to memory via bridge
            # This ensures insights are persisted before validation processing
            self._persist_insights_to_memory(ranked_issues, context="run_finalization")

            # IMP-LOOP-002: Validate telemetry feedback before memory storage
            is_valid, validated_issues, error_count = self._validate_telemetry_feedback(
                ranked_issues
            )
            if not is_valid:
                logger.info(
                    f"[IMP-LOOP-002] Telemetry feedback validated with {error_count} corrections"
                )
            # Use validated issues for logging and further processing
            ranked_issues = validated_issues

            logger.info(
                f"[IMP-ARCH-001] Analyzed telemetry: "
                f"{len(ranked_issues.get('top_cost_sinks', []))} cost sinks, "
                f"{len(ranked_issues.get('top_failure_modes', []))} failure modes, "
                f"{len(ranked_issues.get('top_retry_causes', []))} retry causes"
            )

            # IMP-INT-003: Generate tasks from the validated ranked issues and queue for execution
            # This completes the insight→task→execution cycle by ensuring tasks are generated
            # directly from the insights that were just persisted to memory
            self._generate_tasks_from_ranked_issues(ranked_issues, context="run_finalization")

        except Exception as e:
            logger.warning(f"[IMP-ARCH-001] Failed to analyze telemetry: {e}")
            return

    def _persist_loop_insights(self, insights: dict | None = None) -> None:
        """Persist loop insights with graceful error handling.

        IMP-LOOP-001: Wraps persist_insights call with try/except for graceful degradation.
        Insight persistence is non-critical; failures should not crash the autonomous loop.

        Args:
            insights: Optional insights dictionary for logging context.
        """
        try:
            self._persist_telemetry_insights()
            logger.debug("Loop insights persisted successfully")
        except Exception as e:
            # Log warning with extra context but don't re-raise
            extra = {}
            if insights:
                extra["insights_keys"] = list(insights.keys())
            logger.warning(
                f"Failed to persist loop insights (non-fatal): {e}",
                extra=extra,
            )
            # Continue loop execution - insight persistence is non-critical

        # IMP-LOOP-001: Flush pending insights from feedback pipeline
        if self._feedback_pipeline is not None:
            try:
                flushed = self._feedback_pipeline.flush_pending_insights()
                if flushed > 0:
                    logger.info(
                        f"[IMP-LOOP-001] Flushed {flushed} pending feedback pipeline insights"
                    )

                # Also persist any learning hints
                hints_persisted = self._feedback_pipeline.persist_learning_hints()
                if hints_persisted > 0:
                    logger.info(
                        f"[IMP-LOOP-001] Persisted {hints_persisted} learning hints from feedback pipeline"
                    )

                # Log final stats
                stats = self._feedback_pipeline.get_stats()
                logger.info(
                    f"[IMP-LOOP-001] Feedback pipeline stats: "
                    f"outcomes_processed={stats.get('outcomes_processed', 0)}, "
                    f"insights_persisted={stats.get('insights_persisted', 0)}, "
                    f"context_retrievals={stats.get('context_retrievals', 0)}"
                )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-001] Failed to flush feedback pipeline (non-fatal): {e}")

    def _generate_improvement_tasks(self) -> list:
        """Generate improvement tasks from telemetry (ROAD-C).

        Implements IMP-ARCH-004: Autonomous Task Generator.
        Implements IMP-FEAT-001: Wire TelemetryAnalyzer output to TaskGenerator.

        Converts telemetry insights into improvement tasks for self-improvement feedback loop.
        The ROAD-C pipeline connects:
        1. TelemetryAnalyzer.aggregate_telemetry() -> ranked issues
        2. AutonomousTaskGenerator.generate_tasks(telemetry_insights=...) -> improvement tasks

        Returns:
            List of GeneratedTask objects
        """
        try:
            from autopack.config import settings as config_settings
            from autopack.roadc import AutonomousTaskGenerator
        except ImportError:
            logger.debug("[IMP-ARCH-004] ROAD-C module not available")
            return []

        # Load task generation configuration
        try:
            # Try to load from settings if available
            task_gen_config = getattr(config_settings, "task_generation", {})
            if not task_gen_config:
                task_gen_config = {"enabled": False}
        except Exception:
            task_gen_config = {"enabled": False}

        if not task_gen_config.get("enabled", False):
            logger.debug("[IMP-ARCH-004] Task generation not enabled")
            return []

        try:
            # IMP-FEAT-001: Get telemetry insights to wire to task generation
            telemetry_insights = None
            analyzer = self._get_telemetry_analyzer()
            if analyzer:
                try:
                    telemetry_insights = analyzer.aggregate_telemetry(window_days=7)
                    total_issues = (
                        len(telemetry_insights.get("top_cost_sinks", []))
                        + len(telemetry_insights.get("top_failure_modes", []))
                        + len(telemetry_insights.get("top_retry_causes", []))
                    )
                    logger.info(
                        f"[IMP-FEAT-001] Retrieved {total_issues} telemetry issues for task generation"
                    )
                except Exception as tel_err:
                    logger.warning(
                        f"[IMP-FEAT-001] Failed to get telemetry insights, "
                        f"falling back to memory retrieval: {tel_err}"
                    )
                    telemetry_insights = None

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation in task generator
            # The generator can now call aggregate_telemetry() internally if no insights provided
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(db_session=db_session)
            result = generator.generate_tasks(
                max_tasks=task_gen_config.get("max_tasks_per_run", 10),
                min_confidence=task_gen_config.get("min_confidence", 0.7),
                telemetry_insights=telemetry_insights,
            )

            logger.info(
                f"[IMP-ARCH-004] Generated {len(result.tasks_generated)} tasks "
                f"from {result.insights_processed} insights "
                f"({result.generation_time_ms:.0f}ms)"
            )

            # IMP-ARCH-014: Persist generated tasks to database
            if result.tasks_generated:
                try:
                    run_id = getattr(self.executor, "run_id", None)
                    persisted_count = generator.persist_tasks(result.tasks_generated, run_id)
                    logger.info(f"[IMP-ARCH-014] Persisted {persisted_count} tasks to database")
                except Exception as persist_err:
                    logger.warning(f"[IMP-ARCH-014] Failed to persist tasks: {persist_err}")

            return result.tasks_generated
        except Exception as e:
            logger.warning(f"[IMP-ARCH-004] Failed to generate improvement tasks: {e}")
            return []
