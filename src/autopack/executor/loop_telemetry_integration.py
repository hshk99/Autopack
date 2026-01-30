"""Telemetry integration for autonomous execution loop.

Extracted from autonomous_loop.py as part of IMP-MAINT-004.
Handles circuit breaker health updates, task effectiveness tracking,
anomaly detection, telemetry-driven adjustments, and cost recommendations.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from autopack.config import settings
from autopack.telemetry.analyzer import CostRecommendation
from autopack.telemetry.anomaly_detector import AlertSeverity

if TYPE_CHECKING:
    from autopack.executor.circuit_breaker import CircuitBreaker
    from autopack.task_generation.task_effectiveness_tracker import \
        TaskEffectivenessTracker
    from autopack.telemetry.analyzer import TelemetryAnalyzer
    from autopack.telemetry.anomaly_detector import TelemetryAnomalyDetector
    from autopack.telemetry.meta_metrics import (FeedbackLoopHealth,
                                                 MetaMetricsTracker)

logger = logging.getLogger(__name__)


class LoopTelemetryIntegration:
    """Handles telemetry integration for the autonomous execution loop.

    IMP-MAINT-004: Extracted from AutonomousLoop to improve maintainability.
    Encapsulates logic for:
    1. Circuit breaker health updates from meta-metrics
    2. Task effectiveness tracking and feedback
    3. Anomaly detection recording
    4. Telemetry-driven phase adjustments
    5. Cost recommendations and pause handling

    This class bridges telemetry collection with execution control decisions,
    enabling data-driven adjustments during autonomous execution.
    """

    def __init__(
        self,
        circuit_breaker: Optional["CircuitBreaker"] = None,
        meta_metrics_tracker: Optional["MetaMetricsTracker"] = None,
        anomaly_detector: Optional["TelemetryAnomalyDetector"] = None,
        meta_metrics_enabled: bool = True,
        task_effectiveness_enabled: bool = True,
        get_telemetry_analyzer: Optional[Callable[[], Optional["TelemetryAnalyzer"]]] = None,
        emit_alert: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the LoopTelemetryIntegration.

        Args:
            circuit_breaker: CircuitBreaker instance for health-aware state transitions
            meta_metrics_tracker: MetaMetricsTracker for health analysis
            anomaly_detector: TelemetryAnomalyDetector for pattern detection
            meta_metrics_enabled: Whether meta-metrics health checks are enabled
            task_effectiveness_enabled: Whether task effectiveness tracking is enabled
            get_telemetry_analyzer: Callable to get the TelemetryAnalyzer instance
            emit_alert: Callable to emit alerts for operator notification
        """
        self._circuit_breaker = circuit_breaker
        self._meta_metrics_tracker = meta_metrics_tracker
        self._anomaly_detector = anomaly_detector
        self._meta_metrics_enabled = meta_metrics_enabled
        self._task_effectiveness_enabled = task_effectiveness_enabled
        self._get_telemetry_analyzer = get_telemetry_analyzer
        self._emit_alert = emit_alert

        # Task effectiveness tracker (lazy initialized)
        self._task_effectiveness_tracker: Optional["TaskEffectivenessTracker"] = None

        # Task generation pause flag for auto-remediation
        self._task_generation_paused: bool = False

        # Phase statistics for health data building
        self._total_phases_executed: int = 0
        self._total_phases_failed: int = 0

    def set_phase_stats(self, executed: int, failed: int) -> None:
        """Update phase statistics for health data building.

        Args:
            executed: Total phases executed successfully
            failed: Total phases that failed
        """
        self._total_phases_executed = executed
        self._total_phases_failed = failed

    def set_task_effectiveness_tracker(self, tracker: Optional["TaskEffectivenessTracker"]) -> None:
        """Set the task effectiveness tracker instance.

        Args:
            tracker: TaskEffectivenessTracker instance
        """
        self._task_effectiveness_tracker = tracker

    @property
    def task_generation_paused(self) -> bool:
        """Check if task generation is paused due to health issues."""
        return self._task_generation_paused

    @task_generation_paused.setter
    def task_generation_paused(self, value: bool) -> None:
        """Set task generation pause state."""
        self._task_generation_paused = value

    def update_circuit_breaker_health(self, ranked_issues: Optional[Dict]) -> None:
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
            # Import here to avoid circular imports
            from autopack.telemetry.meta_metrics import FeedbackLoopHealth

            # Build telemetry data structure from ranked issues and loop stats
            telemetry_data = self.build_telemetry_data_for_health(ranked_issues)

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
                # IMP-REL-001: Auto-pause task generation when health is critical
                if self._meta_metrics_tracker.should_pause_task_generation(health_report):
                    if not self._task_generation_paused:
                        logger.warning(
                            "[IMP-REL-001] Auto-pausing task generation due to "
                            "ATTENTION_REQUIRED status"
                        )
                        self._task_generation_paused = True
                        if self._emit_alert is not None:
                            self._emit_alert(
                                "Task generation auto-paused - manual intervention required. "
                                f"Health score: {health_report.overall_score:.2f}"
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

    def build_telemetry_data_for_health(self, ranked_issues: Optional[Dict]) -> Dict:
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

    def update_task_effectiveness(
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
        self.record_phase_to_anomaly_detector(
            phase_id=phase_id,
            phase_type=phase_type,
            success=success,
            tokens_used=tokens_used,
            duration_seconds=execution_time_seconds,
        )

        if not self._task_effectiveness_enabled:
            return

        tracker = self._task_effectiveness_tracker
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

            # IMP-LOOP-021: Verify execution for generated improvement tasks
            # Generated task phases have IDs like "generated-task-execution-{task_id}"
            generated_task_prefix = "generated-task-execution-"
            if phase_id.startswith(generated_task_prefix):
                original_task_id = phase_id[len(generated_task_prefix) :]
                if tracker.record_execution(original_task_id, success):
                    logger.info(
                        f"[IMP-LOOP-021] Verified execution of generated task {original_task_id}: "
                        f"success={success}"
                    )

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

    def record_phase_to_anomaly_detector(
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
                f"[IMP-FBK-002] Failed to record phase to anomaly detector (non-fatal): {e}"
            )

    def get_telemetry_adjustments(
        self,
        phase_type: Optional[str],
        analyzer: Optional[Any] = None,
    ) -> Dict:
        """Get telemetry-driven adjustments for phase execution.

        Queries the telemetry analyzer for recommendations and returns
        adjustments to apply to the phase execution.

        Args:
            phase_type: The type of phase being executed
            analyzer: Optional TelemetryAnalyzer instance. If not provided,
                     uses the stored get_telemetry_analyzer callback.

        Returns:
            Dictionary of adjustments to pass to execute_phase:
            - context_reduction_factor: Factor to reduce context by (e.g., 0.7 for 30% reduction)
            - model_downgrade: Target model to use instead (e.g., "sonnet", "haiku")
            - timeout_increase_factor: Factor to increase timeout by (e.g., 1.5 for 50% increase)
        """
        adjustments: Dict = {}

        if not phase_type:
            return adjustments

        # Use provided analyzer or fall back to callback
        if analyzer is None:
            if self._get_telemetry_analyzer is None:
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
                            f"[Telemetry] CRITICAL: Downgrading model to "
                            f"{adjustments['model_downgrade']} for {phase_type}. Reason: {reason}"
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

    def check_cost_recommendations(
        self,
        tokens_used: int,
        token_cap: int,
        analyzer: Optional[Any] = None,
    ) -> CostRecommendation:
        """Check if telemetry recommends pausing for cost reasons (IMP-COST-005).

        Queries the telemetry analyzer for cost recommendations based on
        current token usage against the run's budget cap.

        Args:
            tokens_used: Current token usage count
            token_cap: Token budget cap for the run
            analyzer: Optional TelemetryAnalyzer instance. If not provided,
                     uses the stored get_telemetry_analyzer callback.

        Returns:
            CostRecommendation with pause decision and details
        """
        # Use provided analyzer or fall back to callback
        if analyzer is None and self._get_telemetry_analyzer is not None:
            analyzer = self._get_telemetry_analyzer()

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

    def pause_for_cost_limit(
        self,
        recommendation: CostRecommendation,
        project_slug: str = "unknown",
    ) -> None:
        """Handle pause when cost limits are approached (IMP-COST-005).

        Logs the cost pause event and could trigger notifications or
        graceful shutdown procedures in the future.

        Args:
            recommendation: The CostRecommendation that triggered the pause
            project_slug: Project identifier for logging
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
                project_slug=project_slug,
            )
        except Exception as e:
            logger.warning(f"[IMP-COST-005] Failed to log cost pause event: {e}")
