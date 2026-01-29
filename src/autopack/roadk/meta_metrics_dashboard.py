"""Meta-metrics dashboard for self-improvement loop health.

Provides user-facing dashboard capabilities for monitoring the health
of the self-improvement feedback loop, leveraging the existing
MetaMetricsTracker for analysis.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..telemetry.meta_metrics import (FeedbackLoopHealth,
                                      PipelineLatencyTracker,
                                      PipelineSLAConfig, SLABreachAlert)
from .dashboard_data import DashboardDataProvider, LoopHealthMetrics


class MetaMetricsDashboard:
    """Dashboard for monitoring self-improvement loop health.

    Provides a user-facing interface to:
    - View current loop health status and score
    - Monitor task generation, validation, promotion, and rollback rates
    - Track trends over time
    - Receive alerts for degraded conditions
    - Monitor pipeline SLA compliance with configurable thresholds
    """

    # Default SLA threshold: 5 minutes (300000 ms)
    DEFAULT_SLA_THRESHOLD_MS = 300000

    def __init__(
        self,
        data_provider: Optional[DashboardDataProvider] = None,
        sla_threshold_ms: Optional[float] = None,
        sla_config: Optional[PipelineSLAConfig] = None,
        pipeline_tracker: Optional[PipelineLatencyTracker] = None,
    ):
        """Initialize the dashboard.

        Args:
            data_provider: Optional DashboardDataProvider instance
            sla_threshold_ms: Optional custom end-to-end SLA threshold in milliseconds
                             (default: 5 minutes / 300000 ms)
            sla_config: Optional PipelineSLAConfig for detailed SLA configuration
            pipeline_tracker: Optional PipelineLatencyTracker for current pipeline state
        """
        self._data = data_provider or DashboardDataProvider()
        self._sla_threshold_ms = sla_threshold_ms or self.DEFAULT_SLA_THRESHOLD_MS
        self._sla_config = sla_config or PipelineSLAConfig(
            end_to_end_threshold_ms=self._sla_threshold_ms
        )
        self._pipeline_tracker = pipeline_tracker

    def get_dashboard_data(self, days: int = 30) -> Dict[str, Any]:
        """Get complete dashboard data.

        Args:
            days: Number of days to include in the analysis period

        Returns:
            Dict containing summary metrics, trends, alerts, and SLA status
        """
        health = self._data.get_loop_health(days)

        # Get SLA metrics
        sla_metrics = self._get_sla_metrics()

        # Combine health alerts with SLA alerts
        alerts = self._generate_alerts(health)
        sla_alerts = self._generate_sla_alerts()
        alerts.extend(sla_alerts)

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "period_days": days,
            "summary": {
                "loop_health_score": self._calculate_health_score(health),
                "status": self._get_health_status(health),
                "tasks_generated": health.tasks_generated,
                "tasks_validated": health.tasks_validated,
                "tasks_promoted": health.tasks_promoted,
                "tasks_rolled_back": health.tasks_rolled_back,
                "validation_success_rate": f"{health.validation_success_rate:.1%}",
                "promotion_rate": f"{health.promotion_rate:.1%}",
                "rollback_rate": f"{health.rollback_rate:.1%}",
                "avg_time_to_promotion_hours": health.avg_time_to_promotion_hours,
            },
            "sla": sla_metrics,
            "trends": {
                "generation": [
                    {"timestamp": p.timestamp.isoformat(), "value": p.value}
                    for p in self._data.get_generation_trend(days)
                ],
                "success_rate": [
                    {"timestamp": p.timestamp.isoformat(), "value": p.value}
                    for p in self._data.get_success_trend(days)
                ],
            },
            "alerts": alerts,
        }

    def _get_sla_metrics(self) -> Dict[str, Any]:
        """Get current pipeline SLA metrics.

        Returns:
            Dict containing SLA configuration and current status
        """
        sla_metrics = {
            "threshold_ms": self._sla_threshold_ms,
            "threshold_minutes": self._sla_threshold_ms / 60000,
            "status": "unknown",
            "current_latency_ms": None,
            "current_latency_minutes": None,
            "is_within_sla": True,
            "stage_latencies": {},
            "breaches": [],
        }

        if self._pipeline_tracker is not None:
            e2e_latency = self._pipeline_tracker.get_end_to_end_latency_ms()
            sla_metrics["status"] = self._pipeline_tracker.get_sla_status()
            sla_metrics["current_latency_ms"] = e2e_latency
            sla_metrics["current_latency_minutes"] = (
                e2e_latency / 60000 if e2e_latency is not None else None
            )
            sla_metrics["is_within_sla"] = self._pipeline_tracker.is_within_sla()
            sla_metrics["stage_latencies"] = self._pipeline_tracker.get_stage_latencies()
            sla_metrics["breaches"] = [
                breach.to_dict() for breach in self._pipeline_tracker.check_sla_breaches()
            ]

        return sla_metrics

    def _generate_sla_alerts(self) -> List[Dict[str, str]]:
        """Generate alerts based on SLA breaches.

        Returns:
            List of alert dicts for SLA violations
        """
        alerts = []

        if self._pipeline_tracker is None:
            return alerts

        breaches = self._pipeline_tracker.check_sla_breaches()
        for breach in breaches:
            alerts.append(
                {
                    "level": breach.level,
                    "message": breach.message,
                    "suggestion": self._get_sla_breach_suggestion(breach),
                }
            )

        return alerts

    def _get_sla_breach_suggestion(self, breach: SLABreachAlert) -> str:
        """Get a helpful suggestion for resolving an SLA breach.

        Args:
            breach: The SLA breach alert

        Returns:
            Suggestion string for resolving the breach
        """
        # End-to-end breach
        if breach.stage_from == "phase_complete" and breach.stage_to == "task_executed":
            return "Review pipeline bottlenecks; consider scaling telemetry processing"

        # Stage-specific suggestions
        stage_suggestions = {
            "phase_complete": "Check telemetry event publishing latency",
            "telemetry_collected": "Review memory persistence queue depth",
            "memory_persisted": "Optimize task generation queries",
            "task_generated": "Check task execution queue and worker availability",
        }

        if breach.stage_from:
            return stage_suggestions.get(
                breach.stage_from,
                "Review pipeline stage for performance bottlenecks",
            )

        return "Check overall pipeline health and resource availability"

    def set_pipeline_tracker(self, tracker: PipelineLatencyTracker) -> None:
        """Set or update the pipeline tracker for SLA monitoring.

        Args:
            tracker: PipelineLatencyTracker instance to use for SLA metrics
        """
        self._pipeline_tracker = tracker

    def configure_sla(
        self,
        end_to_end_threshold_ms: Optional[float] = None,
        stage_thresholds_ms: Optional[Dict[str, float]] = None,
    ) -> None:
        """Configure SLA thresholds.

        Args:
            end_to_end_threshold_ms: Total pipeline SLA threshold in milliseconds
            stage_thresholds_ms: Per-stage SLA thresholds
        """
        if end_to_end_threshold_ms is not None:
            self._sla_threshold_ms = end_to_end_threshold_ms

        self._sla_config = PipelineSLAConfig(
            end_to_end_threshold_ms=self._sla_threshold_ms,
            stage_thresholds_ms=stage_thresholds_ms or {},
        )

        # Update tracker config if present
        if self._pipeline_tracker is not None:
            self._pipeline_tracker.sla_config = self._sla_config

    def get_detailed_report(self, days: int = 30) -> Dict[str, Any]:
        """Get detailed health report including per-component analysis.

        Args:
            days: Number of days to include in the analysis period

        Returns:
            Dict containing summary, detailed component reports, and SLA details
        """
        dashboard_data = self.get_dashboard_data(days)
        full_report = self._data.get_full_health_report()

        # Convert component reports to serializable format
        component_details = {}
        for component, report in full_report.component_reports.items():
            component_details[component] = {
                "status": report.status.value,
                "score": report.overall_score,
                "metrics": [
                    {
                        "name": m.metric_name,
                        "current": m.current_value,
                        "baseline": m.baseline_value,
                        "trend": m.trend_direction,
                        "change_pct": m.percent_change,
                        "confidence": m.confidence,
                    }
                    for m in report.metrics
                ],
                "issues": report.issues,
                "recommendations": report.recommendations,
            }

        # Get detailed SLA information
        sla_details = self._get_detailed_sla_report()

        return {
            **dashboard_data,
            "detailed_report": {
                "overall_status": full_report.overall_status.value,
                "overall_score": full_report.overall_score,
                "timestamp": full_report.timestamp,
                "components": component_details,
                "critical_issues": full_report.critical_issues,
                "warnings": full_report.warnings,
                "sla_details": sla_details,
            },
        }

    def _get_detailed_sla_report(self) -> Dict[str, Any]:
        """Get detailed SLA report for the pipeline.

        Returns:
            Dict containing detailed SLA configuration and history
        """
        sla_details = {
            "configuration": {
                "end_to_end_threshold_ms": self._sla_config.end_to_end_threshold_ms,
                "end_to_end_threshold_minutes": self._sla_config.end_to_end_threshold_ms / 60000,
                "stage_thresholds_ms": self._sla_config.stage_thresholds_ms,
                "alert_on_breach": self._sla_config.alert_on_breach,
            },
            "current_pipeline": None,
        }

        if self._pipeline_tracker is not None:
            sla_details["current_pipeline"] = self._pipeline_tracker.to_dict()

        return sla_details

    def _calculate_health_score(self, health: LoopHealthMetrics) -> float:
        """Calculate overall loop health score (0-100).

        Args:
            health: LoopHealthMetrics with current metrics

        Returns:
            Health score from 0 (poor) to 100 (excellent)
        """
        if health.tasks_generated == 0:
            return 0.0

        # Weight factors for different metrics
        validation_weight = 0.4
        promotion_weight = 0.4
        rollback_penalty = 0.2

        # Calculate base score from positive metrics
        score = (
            health.validation_success_rate * validation_weight
            + health.promotion_rate * promotion_weight
            - health.rollback_rate * rollback_penalty
        ) * 100

        # Clamp to [0, 100]
        return max(0.0, min(100.0, score))

    def _get_health_status(self, health: LoopHealthMetrics) -> str:
        """Get health status string based on metrics.

        Args:
            health: LoopHealthMetrics with current metrics

        Returns:
            Status string: "healthy", "degraded", "warning", or "critical"
        """
        score = self._calculate_health_score(health)

        if score >= 80:
            return FeedbackLoopHealth.HEALTHY.value
        elif score >= 60:
            return FeedbackLoopHealth.DEGRADED.value
        elif score >= 40:
            return "warning"
        return "critical"

    def _generate_alerts(self, health: LoopHealthMetrics) -> List[Dict[str, str]]:
        """Generate alerts based on health metrics.

        Args:
            health: LoopHealthMetrics with current metrics

        Returns:
            List of alert dicts with level, message, and suggestion
        """
        alerts = []

        # Alert for high rollback rate
        if health.rollback_rate > 0.2:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"High rollback rate: {health.rollback_rate:.1%}",
                    "suggestion": "Review task validation criteria",
                }
            )

        # Alert for low validation success
        if health.validation_success_rate < 0.5 and health.tasks_validated > 0:
            alerts.append(
                {
                    "level": "critical",
                    "message": f"Low validation success: {health.validation_success_rate:.1%}",
                    "suggestion": "Check task generation quality",
                }
            )

        # Alert for no tasks generated
        if health.tasks_generated == 0:
            alerts.append(
                {
                    "level": "info",
                    "message": "No tasks generated in period",
                    "suggestion": "Check telemetry pipeline",
                }
            )

        # Alert for low promotion rate
        if health.promotion_rate < 0.3 and health.tasks_promoted >= 0:
            if health.tasks_generated > 0:  # Only alert if tasks exist
                alerts.append(
                    {
                        "level": "warning",
                        "message": f"Low promotion rate: {health.promotion_rate:.1%}",
                        "suggestion": "Review validation gate thresholds",
                    }
                )

        return alerts
