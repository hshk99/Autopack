"""Metrics endpoints for Prometheus monitoring.

IMP-OBS-001: Feedback loop observability dashboard and Prometheus metrics.

Provides endpoints for exposing feedback loop health metrics to Prometheus
for monitoring and alerting on component degradation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from autopack.telemetry.meta_metrics import MetaMetricsTracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics/feedback-loop")
async def get_feedback_loop_metrics(
    include_details: bool = Query(
        default=False,
        description="Include detailed component breakdown in response",
    ),
) -> Dict[str, Any]:
    """Expose feedback loop health metrics for Prometheus scraping.

    IMP-OBS-001: Returns ROAD component health scores as Prometheus-compatible
    Gauge metrics. These can be scraped by Prometheus and used for:
    - Alerting when component health drops below thresholds
    - Dashboards showing feedback loop health trends
    - Correlation with other system metrics

    Metrics returned:
    - autopack_feedback_loop_health: Overall loop health (0.0-1.0)
    - autopack_telemetry_health: ROAD-B telemetry analysis health
    - autopack_task_gen_health: ROAD-C task generation health
    - autopack_validation_health: ROAD-E validation coverage health
    - autopack_policy_health: ROAD-F policy promotion health
    - autopack_anomaly_health: ROAD-G anomaly detection health
    - autopack_healing_health: ROAD-J auto-healing health
    - autopack_model_health: ROAD-L model optimization health

    Args:
        include_details: If True, includes full health report details

    Returns:
        Dict with metrics and optional details for Prometheus scraping
    """
    tracker = MetaMetricsTracker()
    metrics = tracker.export_to_prometheus()

    response: Dict[str, Any] = {
        "metrics": metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if include_details:
        # Include full health report for debugging/dashboard use
        health_report = tracker.analyze_feedback_loop_health({})
        response["details"] = {
            "overall_status": health_report.overall_status.value,
            "overall_score": health_report.overall_score,
            "critical_issues": health_report.critical_issues,
            "warnings": health_report.warnings,
            "component_statuses": {
                name: {
                    "status": report.status.value,
                    "score": report.overall_score,
                    "issues": report.issues,
                }
                for name, report in health_report.component_reports.items()
            },
        }

    return response
