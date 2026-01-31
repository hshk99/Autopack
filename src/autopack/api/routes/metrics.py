"""Metrics endpoints for Prometheus monitoring.

IMP-OBS-001: Feedback loop observability dashboard and Prometheus metrics.
IMP-TELE-010: Real-time pipeline health dashboard.

Provides endpoints for exposing feedback loop health metrics to Prometheus
for monitoring and alerting on component degradation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from autopack.telemetry.autopilot_metrics import AutopilotHealthCollector
from autopack.telemetry.loop_metrics import LoopMetricsCollector
from autopack.telemetry.meta_metrics import (MetaMetricsTracker,
                                             PipelineLatencyTracker,
                                             PipelineSLAConfig)

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


# ---------------------------------------------------------------------------
# IMP-TELE-010: Real-Time Pipeline Health Dashboard
# ---------------------------------------------------------------------------


class LatencyMetrics(BaseModel):
    """Latency measurements for pipeline stages.

    IMP-TELE-010: Provides detailed latency tracking for the ROAD-B to ROAD-C
    pipeline stages.
    """

    telemetry_to_analysis_ms: float = Field(
        default=0.0, description="Latency from telemetry collection to analysis (ms)"
    )
    analysis_to_task_ms: float = Field(
        default=0.0, description="Latency from analysis to task generation (ms)"
    )
    total_latency_ms: float = Field(
        default=0.0, description="Total end-to-end pipeline latency (ms)"
    )
    sla_threshold_ms: float = Field(
        default=300000.0, description="SLA threshold for total latency (ms)"
    )
    stage_latencies: Dict[str, Optional[float]] = Field(
        default_factory=dict, description="Per-stage latency breakdown"
    )


class SLAComplianceMetrics(BaseModel):
    """SLA compliance status and metrics.

    IMP-TELE-010: Tracks whether the pipeline is meeting its SLA targets.
    """

    status: str = Field(
        default="unknown",
        description="SLA status: excellent, good, acceptable, warning, or breached",
    )
    is_within_sla: bool = Field(default=True, description="Whether SLA is being met")
    breach_amount_ms: float = Field(
        default=0.0, description="Amount by which SLA is breached (0 if within)"
    )
    threshold_ms: float = Field(default=300000.0, description="SLA threshold in ms")
    active_breaches: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of active SLA breach alerts"
    )


class ComponentHealthMetrics(BaseModel):
    """Health status for a single ROAD component.

    IMP-TELE-010: Provides per-component health scores and status.
    """

    component: str = Field(description="Component name (e.g., ROAD-B)")
    status: str = Field(description="Status: improving, stable, degrading, or insufficient_data")
    score: float = Field(description="Health score from 0.0 to 1.0")
    issues: List[str] = Field(default_factory=list, description="List of detected issues")


class PipelineHealthResponse(BaseModel):
    """Complete pipeline health response.

    IMP-TELE-010: Aggregates latency, SLA compliance, and component health
    metrics for the real-time pipeline health dashboard.
    """

    timestamp: str = Field(description="ISO 8601 timestamp of the response")
    latency: LatencyMetrics = Field(description="Pipeline latency metrics")
    sla_compliance: SLAComplianceMetrics = Field(description="SLA compliance status")
    component_health: Dict[str, ComponentHealthMetrics] = Field(
        description="Health metrics per ROAD component"
    )
    overall_health_score: float = Field(description="Overall pipeline health score (0.0-1.0)")
    overall_status: str = Field(
        description="Overall status: healthy, degraded, attention_required, or unknown"
    )


# Global pipeline latency tracker for real-time monitoring
_pipeline_latency_tracker: PipelineLatencyTracker | None = None


def get_pipeline_latency_tracker() -> PipelineLatencyTracker:
    """Get the global PipelineLatencyTracker instance.

    IMP-TELE-010: Provides access to the shared pipeline latency tracker
    for recording and querying pipeline stage timestamps.

    Returns:
        The global PipelineLatencyTracker instance.
    """
    global _pipeline_latency_tracker
    if _pipeline_latency_tracker is None:
        _pipeline_latency_tracker = PipelineLatencyTracker(sla_config=PipelineSLAConfig())
        logger.info("[IMP-TELE-010] Initialized global PipelineLatencyTracker")
    return _pipeline_latency_tracker


def reset_pipeline_latency_tracker() -> None:
    """Reset the global PipelineLatencyTracker instance.

    IMP-TELE-010: For testing purposes, allows resetting the tracker.
    """
    global _pipeline_latency_tracker
    _pipeline_latency_tracker = None
    logger.info("[IMP-TELE-010] Reset global PipelineLatencyTracker")


@router.get("/metrics/pipeline-health", response_model=PipelineHealthResponse)
async def get_pipeline_health() -> PipelineHealthResponse:
    """Return real-time pipeline health metrics from MetaMetricsTracker.

    IMP-TELE-010: Provides operational visibility into the self-improvement
    pipeline with:
    - ROAD-B to ROAD-C latency measurements
    - SLA compliance status and breach alerts
    - Per-component health indicators

    This endpoint powers the Pipeline Health Dashboard for monitoring
    pipeline performance in real-time.

    Returns:
        PipelineHealthResponse with latency, SLA compliance, and component health
    """
    tracker = MetaMetricsTracker()
    latency_tracker = get_pipeline_latency_tracker()

    # Get component health report
    health_report = tracker.analyze_feedback_loop_health({})

    # Build latency metrics from tracker
    latency_data = latency_tracker.to_feedback_loop_latency()
    latency = LatencyMetrics(
        telemetry_to_analysis_ms=latency_data.telemetry_to_analysis_ms,
        analysis_to_task_ms=latency_data.analysis_to_task_ms,
        total_latency_ms=latency_data.total_latency_ms,
        sla_threshold_ms=latency_data.sla_threshold_ms,
        stage_latencies=latency_tracker.get_stage_latencies(),
    )

    # Build SLA compliance metrics
    breaches = latency_tracker.check_sla_breaches()
    sla_compliance = SLAComplianceMetrics(
        status=latency_tracker.get_sla_status(),
        is_within_sla=latency_tracker.is_within_sla(),
        breach_amount_ms=latency_data.get_breach_amount_ms(),
        threshold_ms=latency_data.sla_threshold_ms,
        active_breaches=[breach.to_dict() for breach in breaches],
    )

    # Build component health metrics
    component_health: Dict[str, ComponentHealthMetrics] = {}
    for component_name, report in health_report.component_reports.items():
        component_health[component_name] = ComponentHealthMetrics(
            component=component_name,
            status=report.status.value,
            score=report.overall_score,
            issues=report.issues,
        )

    response = PipelineHealthResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        latency=latency,
        sla_compliance=sla_compliance,
        component_health=component_health,
        overall_health_score=health_report.overall_score,
        overall_status=health_report.overall_status.value,
    )

    logger.debug(
        "[IMP-TELE-010] Returning pipeline health: status=%s, score=%.2f, sla=%s",
        response.overall_status,
        response.overall_health_score,
        response.sla_compliance.status,
    )

    return response


# ---------------------------------------------------------------------------
# IMP-SEG-001: Autopilot Health Metrics Tracking
# ---------------------------------------------------------------------------

# Global AutopilotHealthCollector instance for metrics tracking
_autopilot_health_collector: AutopilotHealthCollector | None = None


def get_autopilot_health_collector() -> AutopilotHealthCollector:
    """Get the global AutopilotHealthCollector instance.

    IMP-SEG-001: Provides access to the shared autopilot health collector
    for monitoring autopilot execution, health gates, and research cycles.

    Returns:
        The global AutopilotHealthCollector instance.
    """
    global _autopilot_health_collector
    if _autopilot_health_collector is None:
        _autopilot_health_collector = AutopilotHealthCollector()
        logger.info("[IMP-SEG-001] Initialized global AutopilotHealthCollector")
    return _autopilot_health_collector


@router.get("/metrics/autopilot-health")
async def get_autopilot_health_metrics(
    include_sessions: bool = Query(
        default=False,
        description="Include recent session history in response",
    ),
    include_timeline: bool = Query(
        default=False,
        description="Include health timeline for trend analysis",
    ),
) -> Dict[str, Any]:
    """Expose autopilot health metrics for monitoring.

    IMP-SEG-001: Returns comprehensive autopilot health including:
    - Circuit breaker state and health score
    - Budget enforcement metrics
    - Health transition tracking
    - Research cycle outcomes
    - Session success/failure rates
    - Critical issues and warnings

    These metrics enable monitoring of autopilot execution health,
    identifying degradation patterns, and detecting issues with
    health gates and research cycles.

    Args:
        include_sessions: If True, includes recent session history (last 20)
        include_timeline: If True, includes health timeline for trend analysis

    Returns:
        Dict with autopilot health metrics, Prometheus format, and optional details
    """
    collector = get_autopilot_health_collector()
    metrics = collector.get_metrics()

    response: Dict[str, Any] = {
        "metrics": metrics.to_dict(),
        "prometheus": collector.export_to_prometheus(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dashboard_summary": collector.get_dashboard_summary(),
    }

    if include_sessions:
        response["recent_sessions"] = [s.to_dict() for s in collector.get_session_history(limit=20)]

    if include_timeline:
        response["health_timeline"] = collector.get_health_timeline()

    logger.debug(
        "[IMP-SEG-001] Returning autopilot health metrics: "
        "health_score=%.2f, sessions=%d, critical_issues=%d",
        metrics.overall_health_score,
        metrics.total_sessions,
        len(metrics.critical_issues),
    )

    return response
