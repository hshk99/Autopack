"""Meta-metrics dashboard for self-improvement loop health.

Provides user-facing dashboard capabilities for monitoring the health
of the self-improvement feedback loop, leveraging the existing
MetaMetricsTracker for analysis.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from .dashboard_data import DashboardDataProvider, LoopHealthMetrics
from ..telemetry.meta_metrics import FeedbackLoopHealth


class MetaMetricsDashboard:
    """Dashboard for monitoring self-improvement loop health.

    Provides a user-facing interface to:
    - View current loop health status and score
    - Monitor task generation, validation, promotion, and rollback rates
    - Track trends over time
    - Receive alerts for degraded conditions
    """

    def __init__(self, data_provider: Optional[DashboardDataProvider] = None):
        """Initialize the dashboard.

        Args:
            data_provider: Optional DashboardDataProvider instance
        """
        self._data = data_provider or DashboardDataProvider()

    def get_dashboard_data(self, days: int = 30) -> Dict[str, Any]:
        """Get complete dashboard data.

        Args:
            days: Number of days to include in the analysis period

        Returns:
            Dict containing summary metrics, trends, and alerts
        """
        health = self._data.get_loop_health(days)

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
            "alerts": self._generate_alerts(health),
        }

    def get_detailed_report(self, days: int = 30) -> Dict[str, Any]:
        """Get detailed health report including per-component analysis.

        Args:
            days: Number of days to include in the analysis period

        Returns:
            Dict containing summary and detailed component reports
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

        return {
            **dashboard_data,
            "detailed_report": {
                "overall_status": full_report.overall_status.value,
                "overall_score": full_report.overall_score,
                "timestamp": full_report.timestamp,
                "components": component_details,
                "critical_issues": full_report.critical_issues,
                "warnings": full_report.warnings,
            },
        }

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
