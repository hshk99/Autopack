"""Metrics endpoints for Prometheus monitoring.

IMP-OBS-001: Feedback loop observability dashboard and Prometheus metrics.

Provides endpoints for exposing feedback loop health metrics to Prometheus
for monitoring and alerting on component degradation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Query

from autopack.telemetry.loop_metrics import LoopMetricsCollector
from autopack.telemetry.meta_metrics import MetaMetricsTracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])

# IMP-OBS-001: Global LoopMetricsCollector instance for closed-loop observability
# This instance is shared across the application to track feedback loop effectiveness
_loop_metrics_collector: LoopMetricsCollector | None = None


def get_loop_metrics_collector() -> LoopMetricsCollector:
    """Get the global LoopMetricsCollector instance.

    IMP-OBS-001: Provides access to the shared loop metrics collector
    for recording insight detections, task generations, and outcomes.

    Returns:
        The global LoopMetricsCollector instance.
    """
    global _loop_metrics_collector
    if _loop_metrics_collector is None:
        _loop_metrics_collector = LoopMetricsCollector()
        logger.info("[IMP-OBS-001] Initialized global LoopMetricsCollector")
    return _loop_metrics_collector


def reset_loop_metrics_collector() -> None:
    """Reset the global LoopMetricsCollector instance.

    IMP-OBS-001: For testing purposes, allows resetting the collector.
    """
    global _loop_metrics_collector
    if _loop_metrics_collector is not None:
        _loop_metrics_collector.reset()
        logger.info("[IMP-OBS-001] Reset global LoopMetricsCollector")


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


@router.get("/metrics/loop-effectiveness")
async def get_loop_effectiveness_metrics(
    include_funnel: bool = Query(
        default=True,
        description="Include conversion funnel breakdown in response",
    ),
    include_sources: bool = Query(
        default=True,
        description="Include source-level breakdown in response",
    ),
    include_calibration: bool = Query(
        default=False,
        description="Include confidence calibration breakdown in response",
    ),
) -> Dict[str, Any]:
    """Expose closed-loop effectiveness metrics for dashboard and monitoring.

    IMP-OBS-001: Returns feedback loop effectiveness metrics including:
    - Conversion funnel: insights -> tasks -> outcomes
    - Success rates by insight source
    - Failure prevention count
    - Confidence calibration score

    These metrics enable monitoring of the self-improvement loop's ROI
    and identifying which insight sources produce the most effective tasks.

    Args:
        include_funnel: If True, includes conversion funnel breakdown
        include_sources: If True, includes per-source metrics
        include_calibration: If True, includes confidence calibration data

    Returns:
        Dict with effectiveness metrics and optional breakdowns
    """
    collector = get_loop_metrics_collector()
    metrics = collector.get_metrics()

    response: Dict[str, Any] = {
        "metrics": metrics.to_dict(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if include_funnel:
        response["conversion_funnel"] = collector.get_conversion_funnel()

    if include_sources:
        response["source_breakdown"] = collector.get_source_breakdown()

    if include_calibration:
        response["calibration_breakdown"] = collector.get_calibration_breakdown()

    logger.debug(
        "[IMP-OBS-001] Returning loop effectiveness metrics: "
        "insights=%d, tasks=%d, success_rate=%.2f%%",
        metrics.insights_detected,
        metrics.tasks_generated,
        metrics.success_rate * 100,
    )

    return response


@router.get("/metrics/loop-summary")
async def get_loop_summary() -> Dict[str, Any]:
    """Get a comprehensive summary of all loop metrics.

    IMP-OBS-001: Returns the complete summary including all metrics,
    breakdowns, and conversion funnel data in a single response.
    Useful for dashboard widgets that need all data at once.

    Returns:
        Dict with complete loop metrics summary
    """
    collector = get_loop_metrics_collector()
    summary = collector.get_summary()
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    return summary
