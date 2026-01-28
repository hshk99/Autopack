"""ROAD-K: Meta-Metrics for Feedback Loop Quality.

Measures the effectiveness of the self-improvement loop itself:
- ROAD-B analysis accuracy trends
- ROAD-C task generation quality
- ROAD-E validation coverage
- ROAD-F policy promotion effectiveness
- ROAD-G anomaly detection accuracy
- ROAD-J healing success rates
- ROAD-L model selection optimization

Second-order metrics: Measure whether the improvement loop is improving.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Stages in the self-improvement pipeline for SLA tracking."""

    PHASE_COMPLETE = "phase_complete"
    TELEMETRY_COLLECTED = "telemetry_collected"
    MEMORY_PERSISTED = "memory_persisted"
    TASK_GENERATED = "task_generated"
    TASK_EXECUTED = "task_executed"


@dataclass
class PipelineStageTimestamp:
    """Timestamp record for a specific pipeline stage.

    Used for end-to-end SLA tracking across the self-improvement loop.
    """

    stage: PipelineStage
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "stage": self.stage.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PipelineSLAConfig:
    """Configuration for pipeline SLA thresholds.

    Attributes:
        end_to_end_threshold_ms: Total pipeline SLA threshold (default 5 minutes)
        stage_thresholds_ms: Per-stage SLA thresholds (optional)
        alert_on_breach: Whether to generate alerts on SLA breach
    """

    end_to_end_threshold_ms: float = 300000  # 5 minutes default
    stage_thresholds_ms: Dict[str, float] = field(default_factory=dict)
    alert_on_breach: bool = True

    def __post_init__(self) -> None:
        """Set default stage thresholds if not provided."""
        default_thresholds = {
            "phase_complete_to_telemetry_collected": 60000,  # 1 minute
            "telemetry_collected_to_memory_persisted": 60000,  # 1 minute
            "memory_persisted_to_task_generated": 60000,  # 1 minute
            "task_generated_to_task_executed": 120000,  # 2 minutes
        }
        for key, value in default_thresholds.items():
            if key not in self.stage_thresholds_ms:
                self.stage_thresholds_ms[key] = value


@dataclass
class SLABreachAlert:
    """Alert generated when pipeline SLA is breached."""

    level: str  # "warning" or "critical"
    stage_from: Optional[str]
    stage_to: Optional[str]
    threshold_ms: float
    actual_ms: float
    breach_amount_ms: float
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "level": self.level,
            "stage_from": self.stage_from,
            "stage_to": self.stage_to,
            "threshold_ms": self.threshold_ms,
            "actual_ms": self.actual_ms,
            "breach_amount_ms": self.breach_amount_ms,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


class PipelineLatencyTracker:
    """Track timestamps and latencies across the self-improvement pipeline.

    Monitors the end-to-end latency from phase completion through task execution,
    enabling SLA enforcement and alerting when the feedback loop falls behind.

    Pipeline stages:
    1. phase_complete - A phase finishes executing
    2. telemetry_collected - Telemetry data is collected from the phase
    3. memory_persisted - Insights are persisted to memory
    4. task_generated - Improvement task is generated
    5. task_executed - Task is executed

    Usage:
        tracker = PipelineLatencyTracker()
        tracker.record_stage(PipelineStage.PHASE_COMPLETE)
        # ... later ...
        tracker.record_stage(PipelineStage.TELEMETRY_COLLECTED)
        latencies = tracker.get_stage_latencies()
        alerts = tracker.check_sla_breaches()
    """

    # Stage ordering for latency calculation
    STAGE_ORDER = [
        PipelineStage.PHASE_COMPLETE,
        PipelineStage.TELEMETRY_COLLECTED,
        PipelineStage.MEMORY_PERSISTED,
        PipelineStage.TASK_GENERATED,
        PipelineStage.TASK_EXECUTED,
    ]

    def __init__(
        self,
        pipeline_id: Optional[str] = None,
        sla_config: Optional[PipelineSLAConfig] = None,
    ):
        """Initialize the pipeline latency tracker.

        Args:
            pipeline_id: Optional identifier for this pipeline run
            sla_config: SLA configuration (uses defaults if not provided)
        """
        self.pipeline_id = pipeline_id or datetime.utcnow().isoformat()
        self.sla_config = sla_config or PipelineSLAConfig()
        self._stage_timestamps: Dict[PipelineStage, PipelineStageTimestamp] = {}

    def record_stage(
        self,
        stage: PipelineStage,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PipelineStageTimestamp:
        """Record a timestamp for a pipeline stage.

        Args:
            stage: The pipeline stage being recorded
            timestamp: Optional explicit timestamp (defaults to now)
            metadata: Optional metadata about this stage

        Returns:
            The recorded PipelineStageTimestamp
        """
        ts = timestamp or datetime.utcnow()
        stage_ts = PipelineStageTimestamp(
            stage=stage,
            timestamp=ts,
            metadata=metadata or {},
        )
        self._stage_timestamps[stage] = stage_ts
        logger.debug(f"Recorded pipeline stage {stage.value} at {ts.isoformat()}")
        return stage_ts

    def get_stage_timestamp(self, stage: PipelineStage) -> Optional[PipelineStageTimestamp]:
        """Get the recorded timestamp for a specific stage.

        Args:
            stage: The pipeline stage to query

        Returns:
            The PipelineStageTimestamp if recorded, None otherwise
        """
        return self._stage_timestamps.get(stage)

    def get_stage_latency_ms(
        self, from_stage: PipelineStage, to_stage: PipelineStage
    ) -> Optional[float]:
        """Calculate latency between two pipeline stages in milliseconds.

        Args:
            from_stage: Starting stage
            to_stage: Ending stage

        Returns:
            Latency in milliseconds, or None if timestamps not available
        """
        from_ts = self._stage_timestamps.get(from_stage)
        to_ts = self._stage_timestamps.get(to_stage)

        if from_ts is None or to_ts is None:
            return None

        delta = to_ts.timestamp - from_ts.timestamp
        return delta.total_seconds() * 1000

    def get_stage_latencies(self) -> Dict[str, Optional[float]]:
        """Get all stage-to-stage latencies.

        Returns:
            Dict mapping stage transition names to latencies in ms
        """
        latencies = {}
        for i in range(len(self.STAGE_ORDER) - 1):
            from_stage = self.STAGE_ORDER[i]
            to_stage = self.STAGE_ORDER[i + 1]
            key = f"{from_stage.value}_to_{to_stage.value}"
            latencies[key] = self.get_stage_latency_ms(from_stage, to_stage)
        return latencies

    def get_end_to_end_latency_ms(self) -> Optional[float]:
        """Calculate total end-to-end pipeline latency.

        Returns:
            Total latency from phase_complete to task_executed in ms,
            or None if endpoints not recorded
        """
        return self.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE,
            PipelineStage.TASK_EXECUTED,
        )

    def get_partial_latency_ms(self) -> Optional[float]:
        """Calculate latency from first to last recorded stage.

        Useful when pipeline hasn't completed all stages yet.

        Returns:
            Latency from earliest to latest recorded stage in ms,
            or None if no stages recorded
        """
        if not self._stage_timestamps:
            return None

        recorded_stages = [stage for stage in self.STAGE_ORDER if stage in self._stage_timestamps]

        if len(recorded_stages) < 2:
            return None

        first_stage = recorded_stages[0]
        last_stage = recorded_stages[-1]
        return self.get_stage_latency_ms(first_stage, last_stage)

    def is_within_sla(self) -> bool:
        """Check if the pipeline is within end-to-end SLA.

        Returns:
            True if within SLA or incomplete, False if SLA breached
        """
        e2e_latency = self.get_end_to_end_latency_ms()
        if e2e_latency is None:
            return True  # Can't determine, assume OK
        return e2e_latency <= self.sla_config.end_to_end_threshold_ms

    def check_sla_breaches(self) -> List[SLABreachAlert]:
        """Check for SLA breaches at each stage and end-to-end.

        Returns:
            List of SLABreachAlert for any detected breaches
        """
        alerts = []

        # Check end-to-end SLA
        e2e_latency = self.get_end_to_end_latency_ms()
        if e2e_latency is not None:
            threshold = self.sla_config.end_to_end_threshold_ms
            if e2e_latency > threshold:
                breach = e2e_latency - threshold
                level = "critical" if breach > threshold * 0.5 else "warning"
                alerts.append(
                    SLABreachAlert(
                        level=level,
                        stage_from=PipelineStage.PHASE_COMPLETE.value,
                        stage_to=PipelineStage.TASK_EXECUTED.value,
                        threshold_ms=threshold,
                        actual_ms=e2e_latency,
                        breach_amount_ms=breach,
                        message=f"End-to-end SLA breached: {e2e_latency:.0f}ms > {threshold:.0f}ms threshold",
                    )
                )

        # Check per-stage SLAs
        stage_latencies = self.get_stage_latencies()
        for transition, latency in stage_latencies.items():
            if latency is None:
                continue

            threshold = self.sla_config.stage_thresholds_ms.get(transition)
            if threshold is None:
                continue

            if latency > threshold:
                breach = latency - threshold
                level = "critical" if breach > threshold * 0.5 else "warning"
                parts = transition.split("_to_")
                alerts.append(
                    SLABreachAlert(
                        level=level,
                        stage_from=parts[0] if len(parts) > 0 else None,
                        stage_to=parts[1] if len(parts) > 1 else None,
                        threshold_ms=threshold,
                        actual_ms=latency,
                        breach_amount_ms=breach,
                        message=f"Stage SLA breached ({transition}): {latency:.0f}ms > {threshold:.0f}ms",
                    )
                )

        return alerts

    def get_sla_status(self) -> str:
        """Get human-readable SLA status.

        Returns:
            Status string: "excellent", "good", "acceptable", "warning", or "breached"
        """
        e2e_latency = self.get_end_to_end_latency_ms()
        if e2e_latency is None:
            return "unknown"

        threshold = self.sla_config.end_to_end_threshold_ms

        if e2e_latency <= threshold * 0.5:
            return "excellent"
        elif e2e_latency <= threshold * 0.8:
            return "good"
        elif e2e_latency <= threshold:
            return "acceptable"
        elif e2e_latency <= threshold * 1.5:
            return "warning"
        else:
            return "breached"

    def to_feedback_loop_latency(self) -> "FeedbackLoopLatency":
        """Convert to FeedbackLoopLatency for compatibility.

        Returns:
            FeedbackLoopLatency instance with available latency data
        """
        telemetry_to_analysis = self.get_stage_latency_ms(
            PipelineStage.PHASE_COMPLETE, PipelineStage.TELEMETRY_COLLECTED
        )
        analysis_to_task = self.get_stage_latency_ms(
            PipelineStage.TELEMETRY_COLLECTED, PipelineStage.TASK_GENERATED
        )
        total = self.get_end_to_end_latency_ms()

        return FeedbackLoopLatency(
            telemetry_to_analysis_ms=telemetry_to_analysis or 0,
            analysis_to_task_ms=analysis_to_task or 0,
            total_latency_ms=total or 0,
            sla_threshold_ms=self.sla_config.end_to_end_threshold_ms,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary for serialization.

        Returns:
            Dict with all tracker state and computed metrics
        """
        return {
            "pipeline_id": self.pipeline_id,
            "stages": {stage.value: ts.to_dict() for stage, ts in self._stage_timestamps.items()},
            "stage_latencies": self.get_stage_latencies(),
            "end_to_end_latency_ms": self.get_end_to_end_latency_ms(),
            "sla_status": self.get_sla_status(),
            "sla_config": {
                "end_to_end_threshold_ms": self.sla_config.end_to_end_threshold_ms,
                "stage_thresholds_ms": self.sla_config.stage_thresholds_ms,
            },
            "breaches": [alert.to_dict() for alert in self.check_sla_breaches()],
        }


class FeedbackLoopHealth(Enum):
    """Overall health status of the self-improvement loop."""

    HEALTHY = "healthy"  # All metrics within expected ranges
    DEGRADED = "degraded"  # Some metrics showing concerning trends
    ATTENTION_REQUIRED = "attention_required"  # Urgent issues detected
    UNKNOWN = "unknown"  # Insufficient data to determine health


@dataclass
class FeedbackLoopLatency:
    """Latency measurements for the feedback loop pipeline.

    Tracks the time from telemetry collection through analysis to task generation,
    with SLA enforcement to detect when the feedback loop is falling behind.
    """

    telemetry_to_analysis_ms: float
    analysis_to_task_ms: float
    total_latency_ms: float
    sla_threshold_ms: float = 300000  # 5 minutes default SLA

    def is_healthy(self) -> bool:
        """Check if latency is within SLA (5-minute threshold by default)."""
        return self.total_latency_ms <= self.sla_threshold_ms

    def get_sla_status(self) -> str:
        """Get human-readable SLA status."""
        if self.total_latency_ms <= self.sla_threshold_ms * 0.5:
            return "excellent"
        elif self.total_latency_ms <= self.sla_threshold_ms * 0.8:
            return "good"
        elif self.total_latency_ms <= self.sla_threshold_ms:
            return "acceptable"
        else:
            return "breached"

    def get_breach_amount_ms(self) -> float:
        """Get the amount by which SLA is breached (0 if within SLA)."""
        return max(0, self.total_latency_ms - self.sla_threshold_ms)


class ComponentStatus(Enum):
    """Health status for individual ROAD components."""

    IMPROVING = "improving"  # Metrics trending positively
    STABLE = "stable"  # Metrics within acceptable range
    DEGRADING = "degrading"  # Metrics trending negatively
    INSUFFICIENT_DATA = "insufficient_data"  # Not enough samples


@dataclass
class MetricTrend:
    """Trend analysis for a specific metric over time."""

    metric_name: str
    current_value: float
    baseline_value: float
    trend_direction: str  # "improving", "stable", "degrading"
    percent_change: float  # Positive = improvement, negative = degradation
    sample_count: int
    confidence: float  # 0.0-1.0 (low/high confidence in trend)


@dataclass
class ComponentHealthReport:
    """Health report for a single ROAD component."""

    component: str  # "ROAD-B", "ROAD-C", etc.
    status: ComponentStatus
    overall_score: float  # 0.0-1.0 (0 = poor, 1 = excellent)
    metrics: List[MetricTrend]
    issues: List[str]  # Human-readable issues detected
    recommendations: List[str]  # Suggested actions


@dataclass
class FeedbackLoopHealthReport:
    """Complete health report for the self-improvement feedback loop."""

    timestamp: str  # ISO 8601
    overall_status: FeedbackLoopHealth
    overall_score: float  # 0.0-1.0
    component_reports: Dict[str, ComponentHealthReport]
    critical_issues: List[str]
    warnings: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetaMetricsTracker:
    """Track and analyze meta-metrics for feedback loop quality.

    Monitors:
    - ROAD-B: Analysis accuracy (false positive rate, coverage)
    - ROAD-C: Task quality (completion rate, rework rate)
    - ROAD-E: Validation coverage (test pass rate, A-B validity)
    - ROAD-F: Policy effectiveness (promotion rate, rollback rate)
    - ROAD-G: Anomaly detection accuracy (alert precision, false positives)
    - ROAD-J: Healing effectiveness (success rate, escalation rate)
    - ROAD-L: Model optimization (success rate trends, token efficiency)
    """

    def __init__(
        self,
        min_samples_for_trend: int = 10,
        degradation_threshold: float = 0.10,  # 10% degradation triggers alert
        improvement_threshold: float = 0.05,  # 5% improvement considered meaningful
    ):
        """
        Args:
            min_samples_for_trend: Minimum samples needed for trend analysis
            degradation_threshold: Threshold for detecting degradation (0.0-1.0)
            improvement_threshold: Threshold for detecting improvement (0.0-1.0)
        """
        self.min_samples_for_trend = min_samples_for_trend
        self.degradation_threshold = degradation_threshold
        self.improvement_threshold = improvement_threshold

    def analyze_feedback_loop_health(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]] = None
    ) -> FeedbackLoopHealthReport:
        """Analyze overall feedback loop health from telemetry data.

        Args:
            telemetry_data: Recent telemetry data from all ROAD components
            baseline_data: Historical baseline for comparison (optional)

        Returns:
            FeedbackLoopHealthReport with comprehensive health analysis
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Analyze each component
        component_reports = {
            "ROAD-B": self._analyze_telemetry_analysis(telemetry_data, baseline_data),
            "ROAD-C": self._analyze_task_generation(telemetry_data, baseline_data),
            "ROAD-E": self._analyze_validation_coverage(telemetry_data, baseline_data),
            "ROAD-F": self._analyze_policy_promotion(telemetry_data, baseline_data),
            "ROAD-G": self._analyze_anomaly_detection(telemetry_data, baseline_data),
            "ROAD-J": self._analyze_auto_healing(telemetry_data, baseline_data),
            "ROAD-L": self._analyze_model_optimization(telemetry_data, baseline_data),
        }

        # Calculate overall health
        overall_status, overall_score = self._compute_overall_health(component_reports)

        # Collect critical issues and warnings
        critical_issues = []
        warnings = []

        for component_name, report in component_reports.items():
            if report.status == ComponentStatus.DEGRADING:
                for issue in report.issues:
                    critical_issues.append(f"[{component_name}] {issue}")

            if report.overall_score < 0.7:  # Below acceptable threshold
                warnings.append(
                    f"{component_name} health score is {report.overall_score:.2f} (below 0.7 threshold)"
                )

        return FeedbackLoopHealthReport(
            timestamp=timestamp,
            overall_status=overall_status,
            overall_score=overall_score,
            component_reports=component_reports,
            critical_issues=critical_issues,
            warnings=warnings,
            metadata={
                "min_samples_for_trend": self.min_samples_for_trend,
                "degradation_threshold": self.degradation_threshold,
                "improvement_threshold": self.improvement_threshold,
            },
        )

    def _analyze_telemetry_analysis(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-B: Telemetry Analysis component health.

        Metrics:
        - Issue detection accuracy (false positive/negative rates)
        - Analysis coverage (% of phases analyzed)
        - Ranking quality (are top issues actually impactful?)
        """
        metrics = []
        issues = []
        recommendations = []

        # Extract ROAD-B metrics from telemetry
        analysis_data = telemetry_data.get("road_b", {})
        baseline = baseline_data.get("road_b", {}) if baseline_data else {}

        # Metric 1: Issue detection coverage
        phases_analyzed = analysis_data.get("phases_analyzed", 0)
        total_phases = analysis_data.get("total_phases", 1)
        coverage_rate = phases_analyzed / max(total_phases, 1)

        baseline_coverage = baseline.get("coverage_rate", 0.8)  # 80% baseline

        metrics.append(
            self._compute_trend(
                metric_name="issue_detection_coverage",
                current_value=coverage_rate,
                baseline_value=baseline_coverage,
                sample_count=total_phases,
            )
        )

        if coverage_rate < 0.7:
            issues.append(f"Low analysis coverage: {coverage_rate:.1%} (target: >70%)")
            recommendations.append(
                "Enable PhaseOutcomeEvent recording for missing phases (TELEMETRY_DB_ENABLED=1)"
            )

        # Metric 2: False positive rate (issues flagged but not impactful)
        false_positives = analysis_data.get("false_positives", 0)
        total_issues = analysis_data.get("total_issues", 1)
        false_positive_rate = false_positives / max(total_issues, 1)

        baseline_fp_rate = baseline.get("false_positive_rate", 0.1)  # 10% baseline

        metrics.append(
            self._compute_trend(
                metric_name="false_positive_rate",
                current_value=false_positive_rate,
                baseline_value=baseline_fp_rate,
                sample_count=total_issues,
                lower_is_better=True,
            )
        )

        if false_positive_rate > 0.2:
            issues.append(f"High false positive rate: {false_positive_rate:.1%} (target: <20%)")
            recommendations.append("Review issue ranking thresholds in TelemetryAnalyzer")

        # Compute overall status
        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-B",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_task_generation(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-C: Task Generation component health.

        Metrics:
        - Task completion rate (% of generated tasks that complete successfully)
        - Rework rate (tasks requiring multiple attempts)
        - Constraint violation rate (tasks exceeding file/attempt limits)
        """
        metrics = []
        issues = []
        recommendations = []

        task_data = telemetry_data.get("road_c", {})
        baseline = baseline_data.get("road_c", {}) if baseline_data else {}

        # Metric 1: Task completion rate
        completed_tasks = task_data.get("completed_tasks", 0)
        total_tasks = task_data.get("total_tasks", 1)
        completion_rate = completed_tasks / max(total_tasks, 1)

        baseline_completion = baseline.get("completion_rate", 0.7)  # 70% baseline

        metrics.append(
            self._compute_trend(
                metric_name="task_completion_rate",
                current_value=completion_rate,
                baseline_value=baseline_completion,
                sample_count=total_tasks,
            )
        )

        if completion_rate < 0.5:
            issues.append(f"Low task completion rate: {completion_rate:.1%} (target: >50%)")
            recommendations.append("Review FollowupTask generation criteria and scope bounds")

        # Metric 2: Rework rate (tasks needing >1 attempt)
        rework_count = task_data.get("rework_count", 0)
        rework_rate = rework_count / max(total_tasks, 1)

        baseline_rework = baseline.get("rework_rate", 0.3)  # 30% baseline

        metrics.append(
            self._compute_trend(
                metric_name="rework_rate",
                current_value=rework_rate,
                baseline_value=baseline_rework,
                sample_count=total_tasks,
                lower_is_better=True,
            )
        )

        if rework_rate > 0.5:
            issues.append(f"High rework rate: {rework_rate:.1%} (target: <50%)")
            recommendations.append(
                "Reduce rework by improving task scope definition and test plan quality"
            )

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-C",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_validation_coverage(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-E: Validation Coverage component health.

        Metrics:
        - A-B test validity rate (% of tests with matching SHA/hash)
        - Test pass rate (% of validation tests passing)
        - Regression detection rate (% of regressions caught before merge)
        """
        metrics = []
        issues = []
        recommendations = []

        validation_data = telemetry_data.get("road_e", {})
        baseline = baseline_data.get("road_e", {}) if baseline_data else {}

        # Metric 1: A-B test validity rate
        valid_tests = validation_data.get("valid_ab_tests", 0)
        total_tests = validation_data.get("total_ab_tests", 1)
        validity_rate = valid_tests / max(total_tests, 1)

        baseline_validity = baseline.get("validity_rate", 0.9)  # 90% baseline

        metrics.append(
            self._compute_trend(
                metric_name="ab_test_validity_rate",
                current_value=validity_rate,
                baseline_value=baseline_validity,
                sample_count=total_tests,
            )
        )

        if validity_rate < 0.8:
            issues.append(f"Low A-B test validity rate: {validity_rate:.1%} (target: >80%)")
            recommendations.append(
                "Ensure control/treatment runs use matching commit SHA and model hash"
            )

        # Metric 2: Regression detection rate
        regressions_caught = validation_data.get("regressions_caught", 0)
        total_changes = validation_data.get("total_changes", 1)
        detection_rate = regressions_caught / max(total_changes, 1)

        baseline_detection = baseline.get("detection_rate", 0.95)  # 95% baseline

        metrics.append(
            self._compute_trend(
                metric_name="regression_detection_rate",
                current_value=detection_rate,
                baseline_value=baseline_detection,
                sample_count=total_changes,
            )
        )

        if detection_rate < 0.9:
            issues.append(f"Low regression detection rate: {detection_rate:.1%} (target: >90%)")
            recommendations.append("Increase A-B test coverage and tighten validation thresholds")

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-E",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_policy_promotion(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-F: Policy Promotion component health.

        Metrics:
        - Promotion effectiveness (% of promoted policies showing improvement)
        - Rollback rate (% of promoted policies requiring rollback)
        - Policy churn (rate of policy changes over time)
        """
        metrics = []
        issues = []
        recommendations = []

        policy_data = telemetry_data.get("road_f", {})
        baseline = baseline_data.get("road_f", {}) if baseline_data else {}

        # Metric 1: Promotion effectiveness
        effective_promotions = policy_data.get("effective_promotions", 0)
        total_promotions = policy_data.get("total_promotions", 1)
        effectiveness_rate = effective_promotions / max(total_promotions, 1)

        baseline_effectiveness = baseline.get("effectiveness_rate", 0.8)  # 80% baseline

        metrics.append(
            self._compute_trend(
                metric_name="policy_promotion_effectiveness",
                current_value=effectiveness_rate,
                baseline_value=baseline_effectiveness,
                sample_count=total_promotions,
            )
        )

        if effectiveness_rate < 0.6:
            issues.append(f"Low promotion effectiveness: {effectiveness_rate:.1%} (target: >60%)")
            recommendations.append(
                "Increase min_runs_for_candidate threshold or add validation gates"
            )

        # Metric 2: Rollback rate
        rollbacks = policy_data.get("rollbacks", 0)
        rollback_rate = rollbacks / max(total_promotions, 1)

        baseline_rollback = baseline.get("rollback_rate", 0.1)  # 10% baseline

        metrics.append(
            self._compute_trend(
                metric_name="policy_rollback_rate",
                current_value=rollback_rate,
                baseline_value=baseline_rollback,
                sample_count=total_promotions,
                lower_is_better=True,
            )
        )

        if rollback_rate > 0.2:
            issues.append(f"High rollback rate: {rollback_rate:.1%} (target: <20%)")
            recommendations.append(
                "Improve policy validation before promotion (require human approval)"
            )

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-F",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_anomaly_detection(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-G: Anomaly Detection component health.

        Metrics:
        - Alert precision (% of alerts that are actionable)
        - False positive rate (% of alerts that are false alarms)
        - Detection latency (time from anomaly to alert)
        """
        metrics = []
        issues = []
        recommendations = []

        anomaly_data = telemetry_data.get("road_g", {})
        baseline = baseline_data.get("road_g", {}) if baseline_data else {}

        # Metric 1: Alert precision
        actionable_alerts = anomaly_data.get("actionable_alerts", 0)
        total_alerts = anomaly_data.get("total_alerts", 1)
        precision = actionable_alerts / max(total_alerts, 1)

        baseline_precision = baseline.get("precision", 0.8)  # 80% baseline

        metrics.append(
            self._compute_trend(
                metric_name="alert_precision",
                current_value=precision,
                baseline_value=baseline_precision,
                sample_count=total_alerts,
            )
        )

        if precision < 0.6:
            issues.append(f"Low alert precision: {precision:.1%} (target: >60%)")
            recommendations.append(
                "Review anomaly detection thresholds (spike_multiplier, failure_threshold)"
            )

        # Metric 2: False positive rate
        false_positives = anomaly_data.get("false_positives", 0)
        false_positive_rate = false_positives / max(total_alerts, 1)

        baseline_fp_rate = baseline.get("false_positive_rate", 0.15)  # 15% baseline

        metrics.append(
            self._compute_trend(
                metric_name="anomaly_false_positive_rate",
                current_value=false_positive_rate,
                baseline_value=baseline_fp_rate,
                sample_count=total_alerts,
                lower_is_better=True,
            )
        )

        if false_positive_rate > 0.3:
            issues.append(f"High false positive rate: {false_positive_rate:.1%} (target: <30%)")
            recommendations.append("Increase window_size or adjust baseline calculation method")

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-G",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_auto_healing(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-J: Auto-Healing component health.

        Metrics:
        - Healing success rate (% of healing attempts that resolve issues)
        - Escalation rate (% of issues requiring human intervention)
        - Average healing attempts per issue
        """
        metrics = []
        issues = []
        recommendations = []

        healing_data = telemetry_data.get("road_j", {})
        baseline = baseline_data.get("road_j", {}) if baseline_data else {}

        # Metric 1: Healing success rate
        successful_heals = healing_data.get("successful_heals", 0)
        total_heal_attempts = healing_data.get("total_heal_attempts", 1)
        success_rate = successful_heals / max(total_heal_attempts, 1)

        baseline_success = baseline.get("success_rate", 0.7)  # 70% baseline

        metrics.append(
            self._compute_trend(
                metric_name="healing_success_rate",
                current_value=success_rate,
                baseline_value=baseline_success,
                sample_count=total_heal_attempts,
            )
        )

        if success_rate < 0.5:
            issues.append(f"Low healing success rate: {success_rate:.1%} (target: >50%)")
            recommendations.append("Review healing strategies or enable aggressive_healing mode")

        # Metric 2: Escalation rate
        escalations = healing_data.get("escalations", 0)
        escalation_rate = escalations / max(total_heal_attempts, 1)

        baseline_escalation = baseline.get("escalation_rate", 0.2)  # 20% baseline

        metrics.append(
            self._compute_trend(
                metric_name="healing_escalation_rate",
                current_value=escalation_rate,
                baseline_value=baseline_escalation,
                sample_count=total_heal_attempts,
                lower_is_better=True,
            )
        )

        if escalation_rate > 0.4:
            issues.append(f"High escalation rate: {escalation_rate:.1%} (target: <40%)")
            recommendations.append(
                "Improve auto-healing decision logic or increase max_healing_attempts"
            )

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-J",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _analyze_model_optimization(
        self, telemetry_data: Dict[str, Any], baseline_data: Optional[Dict[str, Any]]
    ) -> ComponentHealthReport:
        """Analyze ROAD-L: Model Optimization component health.

        Metrics:
        - Model routing accuracy (% of tasks routed to optimal model)
        - Token efficiency trend (tokens per successful outcome)
        - Success rate improvement from optimization
        """
        metrics = []
        issues = []
        recommendations = []

        model_data = telemetry_data.get("road_l", {})
        baseline = baseline_data.get("road_l", {}) if baseline_data else {}

        # Metric 1: Model routing accuracy
        optimal_routings = model_data.get("optimal_routings", 0)
        total_routings = model_data.get("total_routings", 1)
        routing_accuracy = optimal_routings / max(total_routings, 1)

        baseline_accuracy = baseline.get("routing_accuracy", 0.8)  # 80% baseline

        metrics.append(
            self._compute_trend(
                metric_name="model_routing_accuracy",
                current_value=routing_accuracy,
                baseline_value=baseline_accuracy,
                sample_count=total_routings,
            )
        )

        if routing_accuracy < 0.7:
            issues.append(f"Low routing accuracy: {routing_accuracy:.1%} (target: >70%)")
            recommendations.append(
                "Review model performance tracking thresholds and phase_type mappings"
            )

        # Metric 2: Token efficiency
        avg_tokens = model_data.get("avg_tokens_per_success", 1000)
        baseline_tokens = baseline.get("avg_tokens_per_success", 1200)

        # Lower tokens is better
        token_efficiency_change = (baseline_tokens - avg_tokens) / baseline_tokens

        metrics.append(
            MetricTrend(
                metric_name="token_efficiency",
                current_value=avg_tokens,
                baseline_value=baseline_tokens,
                trend_direction="improving" if token_efficiency_change > 0.05 else "stable",
                percent_change=token_efficiency_change * 100,
                sample_count=model_data.get("sample_count", 0),
                confidence=(
                    0.8 if model_data.get("sample_count", 0) >= self.min_samples_for_trend else 0.3
                ),
            )
        )

        if token_efficiency_change < -0.1:  # 10% worse
            issues.append(
                f"Token efficiency degraded: {token_efficiency_change:.1%} (target: improving)"
            )
            recommendations.append(
                "Review model selection policy and consider prompt optimizations"
            )

        status = self._determine_component_status(metrics)
        overall_score = self._compute_component_score(metrics)

        return ComponentHealthReport(
            component="ROAD-L",
            status=status,
            overall_score=overall_score,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
        )

    def _compute_trend(
        self,
        metric_name: str,
        current_value: float,
        baseline_value: float,
        sample_count: int,
        lower_is_better: bool = False,
    ) -> MetricTrend:
        """Compute trend for a metric comparing current to baseline.

        Args:
            metric_name: Name of the metric
            current_value: Current metric value
            baseline_value: Baseline/historical value
            sample_count: Number of samples in current measurement
            lower_is_better: If True, lower values indicate improvement

        Returns:
            MetricTrend with direction and confidence
        """
        if baseline_value == 0:
            percent_change = 0.0
        else:
            percent_change = ((current_value - baseline_value) / baseline_value) * 100

        # Determine trend direction
        if lower_is_better:
            # For metrics like error rates, lower is better
            if percent_change < -self.improvement_threshold * 100:
                trend_direction = "improving"
            elif percent_change > self.degradation_threshold * 100:
                trend_direction = "degrading"
            else:
                trend_direction = "stable"
        else:
            # For metrics like success rates, higher is better
            if percent_change > self.improvement_threshold * 100:
                trend_direction = "improving"
            elif percent_change < -self.degradation_threshold * 100:
                trend_direction = "degrading"
            else:
                trend_direction = "stable"

        # Compute confidence based on sample count
        if sample_count >= self.min_samples_for_trend:
            confidence = 0.9
        elif sample_count >= self.min_samples_for_trend // 2:
            confidence = 0.6
        else:
            confidence = 0.3

        return MetricTrend(
            metric_name=metric_name,
            current_value=current_value,
            baseline_value=baseline_value,
            trend_direction=trend_direction,
            percent_change=percent_change,
            sample_count=sample_count,
            confidence=confidence,
        )

    def _determine_component_status(self, metrics: List[MetricTrend]) -> ComponentStatus:
        """Determine overall component status from metric trends.

        Args:
            metrics: List of metric trends for the component

        Returns:
            ComponentStatus (improving, stable, degrading, insufficient_data)
        """
        if not metrics:
            return ComponentStatus.INSUFFICIENT_DATA

        # Check if we have enough data
        total_samples = sum(m.sample_count for m in metrics)
        if total_samples < self.min_samples_for_trend:
            return ComponentStatus.INSUFFICIENT_DATA

        # Count trend directions
        improving_count = sum(1 for m in metrics if m.trend_direction == "improving")
        degrading_count = sum(1 for m in metrics if m.trend_direction == "degrading")

        # Determine status
        if degrading_count > 0 and degrading_count >= improving_count:
            return ComponentStatus.DEGRADING
        elif improving_count > 0:
            return ComponentStatus.IMPROVING
        else:
            return ComponentStatus.STABLE

    def _compute_component_score(self, metrics: List[MetricTrend]) -> float:
        """Compute overall health score for a component (0.0-1.0).

        Args:
            metrics: List of metric trends for the component

        Returns:
            Score from 0.0 (poor) to 1.0 (excellent)
        """
        if not metrics:
            return 0.5  # Neutral score for no data

        # Base score
        score = 0.7  # Start at acceptable level

        # Adjust based on trends
        for metric in metrics:
            if metric.confidence < 0.5:
                continue  # Skip low-confidence metrics

            if metric.trend_direction == "improving":
                score += 0.1 * metric.confidence
            elif metric.trend_direction == "degrading":
                score -= 0.15 * metric.confidence  # Penalize degradation more

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, score))

    def _compute_overall_health(
        self, component_reports: Dict[str, ComponentHealthReport]
    ) -> tuple[FeedbackLoopHealth, float]:
        """Compute overall feedback loop health from component reports.

        Args:
            component_reports: Health reports for all components

        Returns:
            Tuple of (FeedbackLoopHealth, overall_score)
        """
        if not component_reports:
            return FeedbackLoopHealth.UNKNOWN, 0.5

        # Calculate weighted average score
        total_score = sum(report.overall_score for report in component_reports.values())
        overall_score = total_score / len(component_reports)

        # Count component statuses
        degrading_count = sum(
            1 for r in component_reports.values() if r.status == ComponentStatus.DEGRADING
        )
        insufficient_data_count = sum(
            1 for r in component_reports.values() if r.status == ComponentStatus.INSUFFICIENT_DATA
        )

        # Determine overall status
        if degrading_count >= 3:  # 3+ components degrading
            return FeedbackLoopHealth.ATTENTION_REQUIRED, overall_score
        elif degrading_count >= 1 or overall_score < 0.6:
            return FeedbackLoopHealth.DEGRADED, overall_score
        elif insufficient_data_count >= 4:  # Most components lack data
            return FeedbackLoopHealth.UNKNOWN, overall_score
        else:
            return FeedbackLoopHealth.HEALTHY, overall_score

    def should_pause_task_generation(self, health_report: FeedbackLoopHealthReport) -> bool:
        """Determine if task generation should be paused based on health status.

        IMP-REL-001: Returns True when the feedback loop health is in
        ATTENTION_REQUIRED state, indicating that automatic task generation
        should be paused until the underlying issues are resolved.

        Args:
            health_report: The current feedback loop health report

        Returns:
            True if task generation should be paused, False otherwise
        """
        return health_report.overall_status == FeedbackLoopHealth.ATTENTION_REQUIRED

    def export_to_prometheus(
        self, telemetry_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Export ROAD component health scores as Prometheus-compatible metrics.

        IMP-OBS-001: Provides Prometheus Gauge-compatible metrics for feedback loop
        health monitoring. Returns component health scores (0.0-1.0) that can be
        scraped by Prometheus and used for alerting on component degradation.

        Args:
            telemetry_data: Optional telemetry data for analysis. If not provided,
                uses empty dict which yields baseline scores.

        Returns:
            Dict of metric names to float values suitable for Prometheus Gauges:
            - autopack_feedback_loop_health: Overall loop health (0.0-1.0)
            - autopack_telemetry_health: ROAD-B telemetry analysis health
            - autopack_task_gen_health: ROAD-C task generation health
            - autopack_validation_health: ROAD-E validation coverage health
            - autopack_policy_health: ROAD-F policy promotion health
            - autopack_anomaly_health: ROAD-G anomaly detection health
            - autopack_healing_health: ROAD-J auto-healing health
            - autopack_model_health: ROAD-L model optimization health
        """
        # Use empty dict if no telemetry data provided - yields baseline scores
        data = telemetry_data or {}
        health = self.analyze_feedback_loop_health(data)

        # Map component names to metric-friendly keys
        component_mapping = {
            "ROAD-B": "autopack_telemetry_health",
            "ROAD-C": "autopack_task_gen_health",
            "ROAD-E": "autopack_validation_health",
            "ROAD-F": "autopack_policy_health",
            "ROAD-G": "autopack_anomaly_health",
            "ROAD-J": "autopack_healing_health",
            "ROAD-L": "autopack_model_health",
        }

        metrics: Dict[str, Any] = {
            "autopack_feedback_loop_health": health.overall_score,
        }

        # Add component health scores
        for component_name, metric_name in component_mapping.items():
            report = health.component_reports.get(component_name)
            if report:
                metrics[metric_name] = report.overall_score
            else:
                metrics[metric_name] = 0.0

        return metrics


# ---------------------------------------------------------------------------
# IMP-MEM-005: Memory Retrieval Quality Metrics
# ---------------------------------------------------------------------------


@dataclass
class MemoryRetrievalMetrics:
    """Metrics for a single memory retrieval operation.

    IMP-MEM-005: Captures quality signals for memory retrieval including
    freshness, relevance, and hit rate to assess if retrieved context is useful.

    Attributes:
        query_hash: Hash of the query for tracking repeat queries
        hit_count: Number of results returned
        avg_relevance: Average relevance score across all results (0.0-1.0)
        max_relevance: Maximum relevance score among results (0.0-1.0)
        min_relevance: Minimum relevance score among results (0.0-1.0)
        avg_freshness_hours: Average age of results in hours
        stale_count: Number of results older than freshness threshold
        collection: The collection searched (e.g., "code", "summaries", "hints")
        timestamp: When the retrieval occurred
    """

    query_hash: str
    hit_count: int
    avg_relevance: float
    max_relevance: float
    min_relevance: float
    avg_freshness_hours: float
    stale_count: int
    collection: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "query_hash": self.query_hash,
            "hit_count": self.hit_count,
            "avg_relevance": round(self.avg_relevance, 4),
            "max_relevance": round(self.max_relevance, 4),
            "min_relevance": round(self.min_relevance, 4),
            "avg_freshness_hours": round(self.avg_freshness_hours, 2),
            "stale_count": self.stale_count,
            "collection": self.collection,
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def hit_rate_quality(self) -> str:
        """Assess hit rate quality: 'good', 'sparse', or 'empty'."""
        if self.hit_count >= 3:
            return "good"
        elif self.hit_count >= 1:
            return "sparse"
        return "empty"

    @property
    def relevance_quality(self) -> str:
        """Assess relevance quality: 'high', 'medium', or 'low'."""
        if self.avg_relevance >= 0.7:
            return "high"
        elif self.avg_relevance >= 0.4:
            return "medium"
        return "low"

    @property
    def freshness_quality(self) -> str:
        """Assess freshness quality: 'fresh', 'aging', or 'stale'."""
        if self.avg_freshness_hours <= 24:
            return "fresh"
        elif self.avg_freshness_hours <= 168:  # 1 week
            return "aging"
        return "stale"


@dataclass
class RetrievalQualitySummary:
    """Aggregated summary of retrieval quality over multiple operations.

    IMP-MEM-005: Provides high-level quality assessment for memory retrieval
    operations to detect degradation trends.

    Attributes:
        total_retrievals: Total number of retrieval operations tracked
        avg_hit_count: Average number of results per retrieval
        avg_relevance: Average relevance score across all retrievals
        avg_freshness_hours: Average age of results in hours
        empty_retrieval_rate: Fraction of retrievals that returned no results
        low_relevance_rate: Fraction of retrievals with avg relevance < 0.4
        stale_result_rate: Fraction of results that were stale
        period_start: Start of the tracking period
        period_end: End of the tracking period
    """

    total_retrievals: int
    avg_hit_count: float
    avg_relevance: float
    avg_freshness_hours: float
    empty_retrieval_rate: float
    low_relevance_rate: float
    stale_result_rate: float
    period_start: datetime
    period_end: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_retrievals": self.total_retrievals,
            "avg_hit_count": round(self.avg_hit_count, 2),
            "avg_relevance": round(self.avg_relevance, 4),
            "avg_freshness_hours": round(self.avg_freshness_hours, 2),
            "empty_retrieval_rate": round(self.empty_retrieval_rate, 4),
            "low_relevance_rate": round(self.low_relevance_rate, 4),
            "stale_result_rate": round(self.stale_result_rate, 4),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
        }

    @property
    def overall_quality(self) -> str:
        """Assess overall retrieval quality: 'healthy', 'degraded', or 'poor'."""
        # Poor if too many empty or low-relevance retrievals
        if self.empty_retrieval_rate > 0.3 or self.low_relevance_rate > 0.5:
            return "poor"
        # Degraded if relevance is low or results are stale
        if self.avg_relevance < 0.5 or self.stale_result_rate > 0.4:
            return "degraded"
        return "healthy"


class RetrievalQualityTracker:
    """Track and analyze memory retrieval quality metrics over time.

    IMP-MEM-005: Monitors retrieval quality to detect when memory becomes
    stale, less relevant, or returns poor results. Enables alerting on
    degradation and provides data for tuning embedding/retrieval parameters.

    Usage:
        tracker = RetrievalQualityTracker()
        metrics = tracker.record_retrieval(
            query="error handling patterns",
            results=[...],
            collection="code"
        )
        summary = tracker.get_quality_summary()
    """

    # Freshness threshold in hours (results older than this are "stale")
    DEFAULT_FRESHNESS_THRESHOLD_HOURS = 168  # 1 week

    def __init__(
        self,
        freshness_threshold_hours: float = DEFAULT_FRESHNESS_THRESHOLD_HOURS,
        max_history_size: int = 1000,
    ):
        """Initialize the retrieval quality tracker.

        Args:
            freshness_threshold_hours: Hours after which results are stale
            max_history_size: Maximum number of retrieval records to keep
        """
        self.freshness_threshold_hours = freshness_threshold_hours
        self.max_history_size = max_history_size
        self._retrieval_history: List[MemoryRetrievalMetrics] = []
        self._lock = __import__("threading").Lock()

    def record_retrieval(
        self,
        query: str,
        results: List[Dict[str, Any]],
        collection: str,
        timestamp: Optional[datetime] = None,
    ) -> MemoryRetrievalMetrics:
        """Record metrics for a retrieval operation.

        Args:
            query: The search query string
            results: List of result dicts, each with 'score' and optional
                'payload' containing 'timestamp'
            collection: Name of the collection searched
            timestamp: When the retrieval occurred (defaults to now)

        Returns:
            MemoryRetrievalMetrics for this retrieval
        """
        ts = timestamp or datetime.utcnow()
        query_hash = self._hash_query(query)

        # Calculate relevance metrics
        scores = [r.get("score", 0.0) for r in results]
        avg_relevance = sum(scores) / len(scores) if scores else 0.0
        max_relevance = max(scores) if scores else 0.0
        min_relevance = min(scores) if scores else 0.0

        # Calculate freshness metrics
        freshness_hours = self._calculate_freshness_hours(results, ts)
        avg_freshness = sum(freshness_hours) / len(freshness_hours) if freshness_hours else 0.0
        stale_count = sum(1 for h in freshness_hours if h > self.freshness_threshold_hours)

        metrics = MemoryRetrievalMetrics(
            query_hash=query_hash,
            hit_count=len(results),
            avg_relevance=avg_relevance,
            max_relevance=max_relevance,
            min_relevance=min_relevance,
            avg_freshness_hours=avg_freshness,
            stale_count=stale_count,
            collection=collection,
            timestamp=ts,
        )

        # Store in history with thread safety
        with self._lock:
            self._retrieval_history.append(metrics)
            # Trim history if needed
            if len(self._retrieval_history) > self.max_history_size:
                self._retrieval_history = self._retrieval_history[-self.max_history_size :]

        logger.debug(
            f"[IMP-MEM-005] Recorded retrieval: collection={collection}, "
            f"hits={len(results)}, avg_relevance={avg_relevance:.3f}"
        )

        return metrics

    def _hash_query(self, query: str) -> str:
        """Create a hash of the query for tracking repeat queries."""
        import hashlib

        return hashlib.sha256(query.encode()).hexdigest()[:16]

    def _calculate_freshness_hours(
        self, results: List[Dict[str, Any]], now: datetime
    ) -> List[float]:
        """Calculate freshness (age in hours) for each result.

        Args:
            results: List of result dicts with optional timestamp in payload
            now: Current time for age calculation

        Returns:
            List of age values in hours (only for results with valid timestamps)
        """
        freshness_hours = []
        for r in results:
            payload = r.get("payload", {})
            timestamp_str = payload.get("timestamp") or payload.get("created_at")
            if timestamp_str:
                try:
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + "+00:00"
                    parsed = datetime.fromisoformat(timestamp_str)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=__import__("datetime").timezone.utc)
                    if now.tzinfo is None:
                        now = now.replace(tzinfo=__import__("datetime").timezone.utc)
                    age_hours = (now - parsed).total_seconds() / 3600
                    freshness_hours.append(max(0.0, age_hours))
                except (ValueError, TypeError):
                    pass  # Skip results with invalid timestamps
        return freshness_hours

    def get_quality_summary(
        self,
        since: Optional[datetime] = None,
        collection: Optional[str] = None,
    ) -> RetrievalQualitySummary:
        """Get aggregated quality summary for retrieval operations.

        Args:
            since: Only include retrievals after this time (defaults to all)
            collection: Only include retrievals for this collection (defaults to all)

        Returns:
            RetrievalQualitySummary with aggregated metrics
        """
        with self._lock:
            history = list(self._retrieval_history)

        # Filter by time and collection
        if since:
            history = [m for m in history if m.timestamp >= since]
        if collection:
            history = [m for m in history if m.collection == collection]

        if not history:
            now = datetime.utcnow()
            return RetrievalQualitySummary(
                total_retrievals=0,
                avg_hit_count=0.0,
                avg_relevance=0.0,
                avg_freshness_hours=0.0,
                empty_retrieval_rate=0.0,
                low_relevance_rate=0.0,
                stale_result_rate=0.0,
                period_start=since or now,
                period_end=now,
            )

        total = len(history)
        avg_hit_count = sum(m.hit_count for m in history) / total
        avg_relevance = sum(m.avg_relevance for m in history) / total

        # Calculate average freshness (excluding 0.0 for empty retrievals)
        freshness_values = [m.avg_freshness_hours for m in history if m.hit_count > 0]
        avg_freshness = sum(freshness_values) / len(freshness_values) if freshness_values else 0.0

        # Calculate rates
        empty_count = sum(1 for m in history if m.hit_count == 0)
        low_relevance_count = sum(1 for m in history if m.avg_relevance < 0.4)
        total_results = sum(m.hit_count for m in history)
        total_stale = sum(m.stale_count for m in history)
        stale_rate = total_stale / total_results if total_results > 0 else 0.0

        return RetrievalQualitySummary(
            total_retrievals=total,
            avg_hit_count=avg_hit_count,
            avg_relevance=avg_relevance,
            avg_freshness_hours=avg_freshness,
            empty_retrieval_rate=empty_count / total,
            low_relevance_rate=low_relevance_count / total,
            stale_result_rate=stale_rate,
            period_start=min(m.timestamp for m in history),
            period_end=max(m.timestamp for m in history),
        )

    def get_collection_breakdown(self) -> Dict[str, RetrievalQualitySummary]:
        """Get quality summaries broken down by collection.

        Returns:
            Dict mapping collection names to their quality summaries
        """
        with self._lock:
            history = list(self._retrieval_history)

        collections = set(m.collection for m in history)
        return {col: self.get_quality_summary(collection=col) for col in collections}

    def get_recent_metrics(self, count: int = 10) -> List[MemoryRetrievalMetrics]:
        """Get the most recent retrieval metrics.

        Args:
            count: Number of recent metrics to return

        Returns:
            List of recent MemoryRetrievalMetrics (newest first)
        """
        with self._lock:
            return list(reversed(self._retrieval_history[-count:]))

    def clear_history(self) -> None:
        """Clear all retrieval history."""
        with self._lock:
            self._retrieval_history.clear()
        logger.debug("[IMP-MEM-005] Cleared retrieval quality history")

    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary for serialization.

        Returns:
            Dict with summary and recent metrics
        """
        summary = self.get_quality_summary()
        recent = self.get_recent_metrics(5)

        return {
            "freshness_threshold_hours": self.freshness_threshold_hours,
            "summary": summary.to_dict(),
            "overall_quality": summary.overall_quality,
            "recent_retrievals": [m.to_dict() for m in recent],
            "collection_breakdown": {
                col: s.to_dict() for col, s in self.get_collection_breakdown().items()
            },
        }


# =============================================================================
# IMP-LOOP-023: Goal Drift Detection
# =============================================================================


@dataclass
class GoalDriftResult:
    """Result of goal drift analysis for generated tasks.

    IMP-LOOP-023: Tracks alignment between generated tasks and stated objectives.
    """

    drift_score: float  # 0.0 = perfect alignment, 1.0 = complete drift
    aligned_task_count: int
    total_task_count: int
    alignment_details: Dict[str, float]  # Per-task alignment scores
    misaligned_tasks: List[str]  # Task IDs with low alignment
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def is_drifting(self, threshold: float = 0.3) -> bool:
        """Check if drift score exceeds threshold.

        Args:
            threshold: Drift threshold (default 0.3 = 30% drift)

        Returns:
            True if drift score exceeds threshold
        """
        return self.drift_score > threshold

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "drift_score": self.drift_score,
            "aligned_task_count": self.aligned_task_count,
            "total_task_count": self.total_task_count,
            "alignment_details": self.alignment_details,
            "misaligned_tasks": self.misaligned_tasks,
            "timestamp": self.timestamp.isoformat(),
        }


class GoalDriftDetector:
    """Detect goal drift in the self-improvement loop.

    IMP-LOOP-023: Monitors whether generated improvement tasks align with
    the stated objectives of the self-improvement system. Detects when the
    loop starts optimizing for unintended metrics or drifting from core goals.

    Default objectives for self-improvement:
    - Reduce execution cost (tokens, API calls)
    - Improve success rate
    - Fix recurring failures
    - Reduce retry frequency
    - Improve system performance
    - Enhance reliability

    Usage:
        detector = GoalDriftDetector()
        tasks = [GeneratedTask(...), ...]
        result = detector.calculate_drift(tasks)
        if result.is_drifting():
            alert("Goal drift detected!")
    """

    # Default stated objectives with associated keywords
    DEFAULT_OBJECTIVES: Dict[str, List[str]] = {
        "reduce_cost": [
            "cost",
            "token",
            "budget",
            "expensive",
            "efficiency",
            "optimize",
            "reduce",
            "save",
            "spending",
        ],
        "improve_success": [
            "success",
            "improve",
            "enhance",
            "better",
            "increase",
            "accuracy",
            "quality",
            "effective",
        ],
        "fix_failures": [
            "fail",
            "error",
            "bug",
            "fix",
            "repair",
            "resolve",
            "issue",
            "problem",
            "broken",
        ],
        "reduce_retries": [
            "retry",
            "attempt",
            "repeat",
            "loop",
            "redundant",
            "duplicate",
            "excessive",
        ],
        "improve_performance": [
            "performance",
            "speed",
            "latency",
            "fast",
            "slow",
            "timeout",
            "delay",
            "throughput",
        ],
        "enhance_reliability": [
            "reliable",
            "stable",
            "consistent",
            "robust",
            "resilient",
            "availability",
            "uptime",
        ],
    }

    # Default threshold for drift alerting
    DEFAULT_DRIFT_THRESHOLD: float = 0.3  # 30% drift triggers alert

    def __init__(
        self,
        objectives: Optional[Dict[str, List[str]]] = None,
        drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
        min_alignment_score: float = 0.2,
    ):
        """Initialize the goal drift detector.

        Args:
            objectives: Custom objectives with keywords (uses defaults if None)
            drift_threshold: Threshold for drift alerts (0.0-1.0)
            min_alignment_score: Minimum score for a task to be considered aligned
        """
        self.objectives = objectives or self.DEFAULT_OBJECTIVES
        self.drift_threshold = drift_threshold
        self.min_alignment_score = min_alignment_score
        self._drift_history: List[GoalDriftResult] = []

    def calculate_drift(self, tasks: List[Any]) -> GoalDriftResult:
        """Calculate goal drift for a set of generated tasks.

        Analyzes each task's title and description to determine alignment
        with stated objectives using keyword-based similarity scoring.

        Args:
            tasks: List of GeneratedTask objects (or objects with title/description)

        Returns:
            GoalDriftResult with drift analysis
        """
        if not tasks:
            return GoalDriftResult(
                drift_score=0.0,
                aligned_task_count=0,
                total_task_count=0,
                alignment_details={},
                misaligned_tasks=[],
            )

        alignment_scores: Dict[str, float] = {}
        misaligned_tasks: List[str] = []
        aligned_count = 0

        for task in tasks:
            task_id = getattr(task, "task_id", str(id(task)))
            title = getattr(task, "title", "").lower()
            description = getattr(task, "description", "").lower()
            text = f"{title} {description}"

            # Calculate alignment score for this task
            score = self._calculate_task_alignment(text)
            alignment_scores[task_id] = score

            if score >= self.min_alignment_score:
                aligned_count += 1
            else:
                misaligned_tasks.append(task_id)

        # Calculate overall drift score (inverse of alignment)
        total_tasks = len(tasks)
        avg_alignment = sum(alignment_scores.values()) / total_tasks
        drift_score = 1.0 - avg_alignment

        result = GoalDriftResult(
            drift_score=drift_score,
            aligned_task_count=aligned_count,
            total_task_count=total_tasks,
            alignment_details=alignment_scores,
            misaligned_tasks=misaligned_tasks,
        )

        # Track history for trend analysis
        self._drift_history.append(result)

        logger.debug(
            f"[IMP-LOOP-023] Goal drift calculated: score={drift_score:.3f}, "
            f"aligned={aligned_count}/{total_tasks}"
        )

        return result

    def _calculate_task_alignment(self, text: str) -> float:
        """Calculate alignment score for a task text against objectives.

        Uses keyword matching to determine how well the task aligns with
        stated objectives. Higher score = better alignment.

        Args:
            text: Combined title and description text (lowercase)

        Returns:
            Alignment score (0.0-1.0)
        """
        if not text:
            return 0.0

        # Count keyword matches across all objectives
        total_keywords = 0
        matched_keywords = 0
        objective_matches: Dict[str, int] = {}

        for objective, keywords in self.objectives.items():
            matches = sum(1 for kw in keywords if kw in text)
            objective_matches[objective] = matches
            matched_keywords += matches
            total_keywords += len(keywords)

        # Base score from keyword density
        if total_keywords == 0:
            return 0.0

        keyword_score = min(1.0, matched_keywords / 3)  # Cap at 3 matches = 1.0

        # Bonus for matching multiple objectives (diverse alignment)
        objectives_hit = sum(1 for m in objective_matches.values() if m > 0)
        diversity_bonus = min(0.2, objectives_hit * 0.05)

        return min(1.0, keyword_score + diversity_bonus)

    def get_drift_trend(self, window_size: int = 5) -> Optional[str]:
        """Analyze trend in drift scores over recent measurements.

        Args:
            window_size: Number of recent measurements to analyze

        Returns:
            Trend direction: "improving", "stable", "worsening", or None if insufficient data
        """
        if len(self._drift_history) < window_size:
            return None

        recent = self._drift_history[-window_size:]
        scores = [r.drift_score for r in recent]

        # Calculate trend direction
        first_half_avg = sum(scores[: window_size // 2]) / (window_size // 2)
        second_half_avg = sum(scores[window_size // 2 :]) / (window_size - window_size // 2)

        diff = second_half_avg - first_half_avg

        if diff < -0.05:
            return "improving"  # Drift decreasing
        elif diff > 0.05:
            return "worsening"  # Drift increasing
        else:
            return "stable"

    def get_average_drift(self, window_size: int = 10) -> float:
        """Get average drift score over recent measurements.

        Args:
            window_size: Number of recent measurements to average

        Returns:
            Average drift score (0.0-1.0)
        """
        if not self._drift_history:
            return 0.0

        recent = self._drift_history[-window_size:]
        return sum(r.drift_score for r in recent) / len(recent)

    def clear_history(self) -> None:
        """Clear drift measurement history."""
        self._drift_history.clear()
        logger.debug("[IMP-LOOP-023] Cleared goal drift history")

    def to_dict(self) -> Dict[str, Any]:
        """Convert detector state to dictionary for serialization.

        Returns:
            Dict with configuration and recent measurements
        """
        return {
            "drift_threshold": self.drift_threshold,
            "min_alignment_score": self.min_alignment_score,
            "objectives": list(self.objectives.keys()),
            "history_size": len(self._drift_history),
            "average_drift": self.get_average_drift(),
            "drift_trend": self.get_drift_trend(),
            "recent_measurements": [r.to_dict() for r in self._drift_history[-5:]],
        }
