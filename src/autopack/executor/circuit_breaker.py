"""Circuit breaker pattern implementation for autonomous loop protection.

Extracted from autonomous_loop.py as part of IMP-MAINT-002 refactoring.
Provides resilient execution by preventing runaway failures.

IMP-LOOP-006: Tracks consecutive failures and trips when threshold is exceeded.
"""

import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional, Tuple

if TYPE_CHECKING:
    from autopack.telemetry.anomaly_detector import TelemetryAnomalyDetector
    from autopack.telemetry.meta_metrics import (FeedbackLoopHealthReport,
                                                 MetaMetricsTracker)

logger = logging.getLogger(__name__)


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
        self._meta_metrics_tracker: Optional["MetaMetricsTracker"] = None
        self._anomaly_detector: Optional["TelemetryAnomalyDetector"] = None
        self._last_health_report: Optional["FeedbackLoopHealthReport"] = None
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
        meta_metrics_tracker: Optional["MetaMetricsTracker"] = None,
        anomaly_detector: Optional["TelemetryAnomalyDetector"] = None,
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

    def update_health_report(self, health_report: "FeedbackLoopHealthReport") -> None:
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
        # Import here to avoid circular imports
        from autopack.telemetry.anomaly_detector import AlertSeverity
        from autopack.telemetry.meta_metrics import FeedbackLoopHealth

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

    def is_available(self) -> bool:
        """Check if circuit breaker allows operations.

        IMP-LOOP-002: Used to gate task generation when circuit is OPEN.
        Returns True when circuit is CLOSED or HALF_OPEN (allowing requests).
        Returns False when circuit is OPEN (blocking requests).

        Returns:
            True if operations are allowed, False if blocked.
        """
        return self.state != CircuitBreakerState.OPEN

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
