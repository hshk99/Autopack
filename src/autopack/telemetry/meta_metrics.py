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
from datetime import datetime, timezone
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


# Type alias for health transition callbacks
HealthTransitionCallback = Any  # Callable[[FeedbackLoopHealth, FeedbackLoopHealth], None]


# =============================================================================
# IMP-LOOP-025: Task Generation Throughput Metrics
# =============================================================================


@dataclass
class TaskGenerationEvent:
    """Record of a single task generation event for throughput tracking.

    IMP-LOOP-025: Captures individual task generation events to enable
    throughput analysis and verify execution wiring.

    Attributes:
        task_id: Unique identifier for the generated task
        source: Source of the insight that triggered task generation
        generation_time_ms: Time taken to generate this task
        insights_consumed: Number of insights that contributed to this task
        timestamp: When the task was generated
        run_id: Optional run ID for context
        queued_for_execution: Whether the task was queued for execution
    """

    task_id: str
    source: str  # "direct", "analyzer", "memory"
    generation_time_ms: float
    insights_consumed: int = 1
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: Optional[str] = None
    queued_for_execution: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "source": self.source,
            "generation_time_ms": round(self.generation_time_ms, 2),
            "insights_consumed": self.insights_consumed,
            "timestamp": self.timestamp.isoformat(),
            "run_id": self.run_id,
            "queued_for_execution": self.queued_for_execution,
        }


@dataclass
class TaskGenerationThroughputMetrics:
    """Aggregated metrics for task generation throughput.

    IMP-LOOP-025: Provides observability into the task generation pipeline,
    enabling verification that tasks are being generated and queued for execution.

    Attributes:
        total_tasks_generated: Total number of tasks generated in the window
        tasks_queued_for_execution: Number of tasks queued for execution
        total_insights_consumed: Total insights that led to tasks
        avg_generation_time_ms: Average time to generate a task
        generation_rate_per_minute: Rate of task generation
        insights_per_task_ratio: Average insights consumed per task
        queue_rate: Fraction of generated tasks that were queued
        window_start: Start of the measurement window
        window_end: End of the measurement window
        by_source: Breakdown by insight source
    """

    total_tasks_generated: int
    tasks_queued_for_execution: int
    total_insights_consumed: int
    avg_generation_time_ms: float
    generation_rate_per_minute: float
    insights_per_task_ratio: float
    queue_rate: float
    window_start: datetime
    window_end: datetime
    by_source: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_tasks_generated": self.total_tasks_generated,
            "tasks_queued_for_execution": self.tasks_queued_for_execution,
            "total_insights_consumed": self.total_insights_consumed,
            "avg_generation_time_ms": round(self.avg_generation_time_ms, 2),
            "generation_rate_per_minute": round(self.generation_rate_per_minute, 4),
            "insights_per_task_ratio": round(self.insights_per_task_ratio, 2),
            "queue_rate": round(self.queue_rate, 4),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "by_source": self.by_source,
        }

    @property
    def execution_wiring_verified(self) -> bool:
        """Check if execution wiring is verified (tasks are being queued).

        IMP-LOOP-025: Returns True if at least some generated tasks are
        being queued for execution, verifying the wiring is working.
        """
        return self.tasks_queued_for_execution > 0 if self.total_tasks_generated > 0 else True

    @property
    def throughput_status(self) -> str:
        """Get human-readable throughput status.

        Returns:
            Status string: "healthy", "low", "stalled", or "unknown"
        """
        if self.total_tasks_generated == 0:
            return "unknown"
        if self.generation_rate_per_minute >= 0.1:  # At least 1 task per 10 minutes
            return "healthy"
        if self.generation_rate_per_minute >= 0.01:  # At least 1 task per 100 minutes
            return "low"
        return "stalled"


@dataclass
class MemoryFreshnessMetrics:
    """Metrics tracking memory freshness for observability.

    IMP-MEDIUM-001: Exposes memory system health metrics for monitoring
    memory degradation and tracking maintenance effectiveness.

    Attributes:
        freshness_ratio: Percentage of entries within freshness window (0.0-1.0)
        stale_entries_count: Number of entries past TTL window
        total_entries: Total entries in memory
        ttl_days: TTL threshold used for staleness
        pruning_effectiveness: Ratio of entries pruned vs. total operations
        timestamp: When metrics were recorded
    """

    freshness_ratio: float
    stale_entries_count: int
    total_entries: int
    ttl_days: int
    pruning_effectiveness: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "freshness_ratio": round(self.freshness_ratio, 4),
            "stale_entries_count": self.stale_entries_count,
            "total_entries": self.total_entries,
            "ttl_days": self.ttl_days,
            "pruning_effectiveness": round(self.pruning_effectiveness, 4),
            "timestamp": self.timestamp.isoformat(),
        }

    @property
    def health_status(self) -> str:
        """Get human-readable memory health status.

        Returns:
            Status string: "healthy", "degrading", "critical", or "empty"
        """
        if self.total_entries == 0:
            return "empty"
        if self.freshness_ratio >= 0.8:  # 80%+ fresh
            return "healthy"
        if self.freshness_ratio >= 0.5:  # 50%+ fresh
            return "degrading"
        return "critical"  # Less than 50% fresh


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

    IMP-REL-001: Includes health transition monitoring with callback support
    for auto-resume of task generation when health recovers.
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

        # IMP-REL-001: Track previous health state for transition detection
        self._previous_health_status: Optional[FeedbackLoopHealth] = None
        self._health_transition_callbacks: List[HealthTransitionCallback] = []
        self._task_generation_paused: bool = False

        # IMP-LOOP-025: Task generation throughput tracking
        self._task_generation_events: List[TaskGenerationEvent] = []
        self._max_generation_events: int = 1000  # Rolling window size
        self._task_generation_lock = __import__("threading").Lock()

    # =========================================================================
    # IMP-LOOP-025: Task Generation Throughput Tracking
    # =========================================================================

    def record_task_generated(
        self,
        task_id: str,
        source: str = "unknown",
        generation_time_ms: float = 0.0,
        insights_consumed: int = 1,
        run_id: Optional[str] = None,
        queued_for_execution: bool = False,
    ) -> TaskGenerationEvent:
        """Record a task generation event for throughput tracking.

        IMP-LOOP-025: Captures task generation events to enable throughput
        analysis and verify the wiring between task generator and execution loop.

        Args:
            task_id: Unique identifier for the generated task
            source: Source of insights ("direct", "analyzer", "memory")
            generation_time_ms: Time taken to generate this task
            insights_consumed: Number of insights that contributed to this task
            run_id: Optional run ID for context
            queued_for_execution: Whether the task was queued for execution

        Returns:
            TaskGenerationEvent that was recorded
        """
        event = TaskGenerationEvent(
            task_id=task_id,
            source=source,
            generation_time_ms=generation_time_ms,
            insights_consumed=insights_consumed,
            run_id=run_id,
            queued_for_execution=queued_for_execution,
        )

        with self._task_generation_lock:
            self._task_generation_events.append(event)
            # Trim to max size (rolling window)
            if len(self._task_generation_events) > self._max_generation_events:
                self._task_generation_events = self._task_generation_events[
                    -self._max_generation_events :
                ]

        logger.info(
            f"[IMP-LOOP-025] Recorded task generation: task_id={task_id}, "
            f"source={source}, queued={queued_for_execution}, "
            f"generation_time={generation_time_ms:.1f}ms"
        )

        return event

    def mark_task_queued(self, task_id: str) -> bool:
        """Mark a previously generated task as queued for execution.

        IMP-LOOP-025: Updates the queued_for_execution flag for a task,
        enabling verification of the execution wiring.

        Args:
            task_id: The task ID to mark as queued

        Returns:
            True if task was found and updated, False otherwise
        """
        with self._task_generation_lock:
            for event in reversed(self._task_generation_events):
                if event.task_id == task_id:
                    event.queued_for_execution = True
                    logger.debug(f"[IMP-LOOP-025] Marked task {task_id} as queued for execution")
                    return True
        logger.warning(f"[IMP-LOOP-025] Task {task_id} not found for queue marking")
        return False

    def get_task_generation_throughput(
        self,
        window_minutes: float = 60.0,
    ) -> TaskGenerationThroughputMetrics:
        """Get task generation throughput metrics for a time window.

        IMP-LOOP-025: Calculates throughput metrics to verify that tasks
        are being generated and queued for execution at expected rates.

        Args:
            window_minutes: Time window in minutes to analyze

        Returns:
            TaskGenerationThroughputMetrics with throughput analysis
        """
        now = datetime.now(timezone.utc)
        window_start = now - __import__("datetime").timedelta(minutes=window_minutes)

        with self._task_generation_lock:
            # Filter events within the window
            window_events = [e for e in self._task_generation_events if e.timestamp >= window_start]

        if not window_events:
            return TaskGenerationThroughputMetrics(
                total_tasks_generated=0,
                tasks_queued_for_execution=0,
                total_insights_consumed=0,
                avg_generation_time_ms=0.0,
                generation_rate_per_minute=0.0,
                insights_per_task_ratio=0.0,
                queue_rate=0.0,
                window_start=window_start,
                window_end=now,
                by_source={},
            )

        # Calculate metrics
        total_tasks = len(window_events)
        tasks_queued = sum(1 for e in window_events if e.queued_for_execution)
        total_insights = sum(e.insights_consumed for e in window_events)
        total_generation_time = sum(e.generation_time_ms for e in window_events)

        # Calculate actual window duration
        if len(window_events) >= 2:
            actual_start = min(e.timestamp for e in window_events)
            actual_end = max(e.timestamp for e in window_events)
            actual_duration_minutes = (actual_end - actual_start).total_seconds() / 60.0
        else:
            actual_duration_minutes = window_minutes

        # Avoid division by zero
        actual_duration_minutes = max(actual_duration_minutes, 0.001)

        # Breakdown by source
        by_source: Dict[str, int] = {}
        for event in window_events:
            by_source[event.source] = by_source.get(event.source, 0) + 1

        metrics = TaskGenerationThroughputMetrics(
            total_tasks_generated=total_tasks,
            tasks_queued_for_execution=tasks_queued,
            total_insights_consumed=total_insights,
            avg_generation_time_ms=total_generation_time / total_tasks,
            generation_rate_per_minute=total_tasks / actual_duration_minutes,
            insights_per_task_ratio=total_insights / total_tasks if total_tasks > 0 else 0.0,
            queue_rate=tasks_queued / total_tasks if total_tasks > 0 else 0.0,
            window_start=window_start,
            window_end=now,
            by_source=by_source,
        )

        logger.debug(
            f"[IMP-LOOP-025] Task generation throughput: "
            f"tasks={total_tasks}, queued={tasks_queued}, "
            f"rate={metrics.generation_rate_per_minute:.3f}/min, "
            f"queue_rate={metrics.queue_rate:.1%}"
        )

        return metrics

    def verify_execution_wiring(self, window_minutes: float = 60.0) -> Dict[str, Any]:
        """Verify that the task generation to execution wiring is working.

        IMP-LOOP-025: Checks that generated tasks are being queued for execution,
        providing a diagnostic report on the wiring health.

        Args:
            window_minutes: Time window in minutes to analyze

        Returns:
            Dict with wiring verification results:
            - wiring_verified: True if wiring appears healthy
            - tasks_generated: Number of tasks generated
            - tasks_queued: Number of tasks queued for execution
            - queue_rate: Fraction of tasks that were queued
            - status: Human-readable status message
            - recommendations: List of recommendations if wiring issues detected
        """
        throughput = self.get_task_generation_throughput(window_minutes)

        recommendations = []
        status = "healthy"

        if throughput.total_tasks_generated == 0:
            status = "no_tasks"
            recommendations.append(
                "No tasks generated in window. Check if insights are being produced "
                "by TelemetryAnalyzer and if task_generation is enabled in settings."
            )
        elif throughput.queue_rate < 0.5:
            status = "low_queue_rate"
            recommendations.append(
                f"Only {throughput.queue_rate:.1%} of generated tasks are being queued. "
                "Check BacklogMaintenance.inject_tasks() wiring and "
                "task_generation_auto_execute setting."
            )
        elif not throughput.execution_wiring_verified:
            status = "wiring_issue"
            recommendations.append(
                "No tasks have been queued for execution. "
                "Verify AutonomousLoop._generate_and_inject_tasks() is being called."
            )

        return {
            "wiring_verified": throughput.execution_wiring_verified
            and throughput.queue_rate >= 0.5,
            "tasks_generated": throughput.total_tasks_generated,
            "tasks_queued": throughput.tasks_queued_for_execution,
            "queue_rate": throughput.queue_rate,
            "throughput_status": throughput.throughput_status,
            "status": status,
            "recommendations": recommendations,
            "metrics": throughput.to_dict(),
        }

    def record_memory_freshness(
        self,
        freshness_ratio: float,
        stale_entries_count: int,
        total_entries: int,
        ttl_days: int,
        pruning_effectiveness: float = 0.0,
    ) -> MemoryFreshnessMetrics:
        """Record memory freshness metrics for observability.

        IMP-MEDIUM-001: Captures memory system health metrics including freshness
        ratio, stale entries count, and pruning effectiveness. Used for monitoring
        memory degradation and tracking maintenance effectiveness.

        Args:
            freshness_ratio: Percentage of entries within freshness window (0.0-1.0)
            stale_entries_count: Number of entries past TTL window
            total_entries: Total entries in memory
            ttl_days: TTL threshold used for staleness
            pruning_effectiveness: Ratio of entries pruned vs. total operations

        Returns:
            MemoryFreshnessMetrics with recorded metrics
        """
        metrics = MemoryFreshnessMetrics(
            freshness_ratio=freshness_ratio,
            stale_entries_count=stale_entries_count,
            total_entries=total_entries,
            ttl_days=ttl_days,
            pruning_effectiveness=pruning_effectiveness,
        )

        logger.info(
            f"[IMP-MEDIUM-001] Memory freshness recorded: "
            f"ratio={metrics.freshness_ratio:.2%}, stale={stale_entries_count}, "
            f"total={total_entries}, status={metrics.health_status}"
        )

        return metrics

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

        Also triggers health transition callbacks if the health status has changed,
        enabling auto-resume when health recovers.

        Args:
            health_report: The current feedback loop health report

        Returns:
            True if task generation should be paused, False otherwise
        """
        current_status = health_report.overall_status
        should_pause = current_status == FeedbackLoopHealth.ATTENTION_REQUIRED

        # IMP-REL-001: Detect and handle health transitions
        if self._previous_health_status is not None:
            if current_status != self._previous_health_status:
                self._on_health_transition(self._previous_health_status, current_status)

        # Update previous status and pause state
        self._previous_health_status = current_status
        self._task_generation_paused = should_pause

        return should_pause

    def register_health_transition_callback(self, callback: HealthTransitionCallback) -> None:
        """Register a callback to be invoked when health status changes.

        IMP-REL-001: Callbacks are invoked with (old_status, new_status) when
        the feedback loop health transitions between states. This enables
        auto-resume of task generation when health recovers.

        Args:
            callback: Function that takes (old_status, new_status) as arguments
        """
        self._health_transition_callbacks.append(callback)
        logger.debug(
            f"[IMP-REL-001] Registered health transition callback "
            f"(total callbacks: {len(self._health_transition_callbacks)})"
        )

    def unregister_health_transition_callback(self, callback: HealthTransitionCallback) -> bool:
        """Unregister a previously registered health transition callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._health_transition_callbacks.remove(callback)
            logger.debug("[IMP-REL-001] Unregistered health transition callback")
            return True
        except ValueError:
            return False

    def _on_health_transition(
        self, old_status: FeedbackLoopHealth, new_status: FeedbackLoopHealth
    ) -> None:
        """Handle health state transitions for auto-resume logic.

        IMP-REL-001: Called when health status changes. Invokes all registered
        callbacks and logs the transition. Specifically handles the recovery
        case where health transitions from ATTENTION_REQUIRED to HEALTHY,
        which should trigger auto-resume of task generation.

        Args:
            old_status: Previous health status
            new_status: New health status
        """
        logger.info(
            f"[IMP-REL-001] Health transition detected: "
            f"{old_status.value} -> {new_status.value}"
        )

        # Check for recovery transition (auto-resume trigger)
        if (
            old_status == FeedbackLoopHealth.ATTENTION_REQUIRED
            and new_status == FeedbackLoopHealth.HEALTHY
        ):
            logger.info(
                "[IMP-REL-001] Health recovered from ATTENTION_REQUIRED to HEALTHY. "
                "Task generation can resume."
            )
            self._task_generation_paused = False

        # Invoke all registered callbacks
        for callback in self._health_transition_callbacks:
            try:
                callback(old_status, new_status)
            except Exception as e:
                logger.warning(f"[IMP-REL-001] Health transition callback failed: {e}")

    def is_task_generation_paused(self) -> bool:
        """Check if task generation is currently paused.

        IMP-REL-001: Returns the current pause state of task generation.
        This is updated by should_pause_task_generation() based on health status.

        Returns:
            True if task generation is paused, False otherwise
        """
        return self._task_generation_paused

    def get_previous_health_status(self) -> Optional[FeedbackLoopHealth]:
        """Get the previous health status for transition analysis.

        IMP-REL-001: Returns the last known health status, useful for
        understanding recent health transitions.

        Returns:
            Previous FeedbackLoopHealth status or None if not yet established
        """
        return self._previous_health_status

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

    def realignment_action(
        self, tasks: List[Any], metrics: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Generate corrective tasks when drift exceeds threshold.

        IMP-LOOP-028: Automatic goal drift correction. When drift is detected,
        this method analyzes the drift direction and generates corrective tasks
        to realign the system with stated objectives.

        Args:
            tasks: List of generated tasks to analyze for drift
            metrics: Optional additional metrics for context

        Returns:
            List of corrective task dictionaries, empty if no correction needed
        """
        drift_result = self.calculate_drift(tasks)

        if not drift_result.is_drifting(self.drift_threshold):
            logger.debug(
                f"[IMP-LOOP-028] No drift correction needed: "
                f"score={drift_result.drift_score:.3f} < threshold={self.drift_threshold}"
            )
            return []

        logger.warning(
            f"[IMP-LOOP-028] Goal drift detected, generating corrective tasks: "
            f"score={drift_result.drift_score:.3f}"
        )

        # Analyze what's causing the drift
        drift_analysis = self._analyze_drift_direction(tasks, drift_result, metrics)

        corrective_tasks = []
        for issue in drift_analysis:
            task = {
                "type": "drift_correction",
                "priority": "high",
                "task_id": f"drift_correction_{issue['objective']}_{len(corrective_tasks)}",
                "title": f"Correct drift: Refocus on {issue['objective'].replace('_', ' ')}",
                "description": issue["description"],
                "corrective_action": issue["corrective_action"],
                "source": "goal_drift_detector",
                "drift_score": drift_result.drift_score,
                "target_objective": issue["objective"],
            }
            corrective_tasks.append(task)
            logger.info(f"[IMP-LOOP-028] Generated corrective task: {task['title']}")

        return corrective_tasks

    def _analyze_drift_direction(
        self,
        tasks: List[Any],
        drift_result: "GoalDriftResult",
        metrics: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Analyze what's causing drift and suggest corrections.

        IMP-LOOP-028: Determines which objectives are being neglected and
        generates specific corrective actions to address the drift.

        Args:
            tasks: The tasks that were analyzed for drift
            drift_result: The drift analysis result
            metrics: Optional additional metrics for context

        Returns:
            List of drift issues with descriptions and corrective actions
        """
        issues = []

        # Calculate coverage for each objective
        objective_coverage: Dict[str, int] = {obj: 0 for obj in self.objectives}

        for task in tasks:
            title = getattr(task, "title", "").lower()
            description = getattr(task, "description", "").lower()
            text = f"{title} {description}"

            for objective, keywords in self.objectives.items():
                if any(kw in text for kw in keywords):
                    objective_coverage[objective] += 1

        # Identify neglected objectives (zero or low coverage)
        total_tasks = len(tasks) if tasks else 1
        for objective, count in objective_coverage.items():
            coverage_ratio = count / total_tasks

            if coverage_ratio < 0.1:  # Less than 10% coverage
                # Generate corrective action based on objective type
                corrective_action = self._get_corrective_action_for_objective(objective, metrics)
                issues.append(
                    {
                        "objective": objective,
                        "coverage_ratio": coverage_ratio,
                        "description": (
                            f"Objective '{objective.replace('_', ' ')}' is underrepresented "
                            f"in generated tasks ({coverage_ratio:.1%} coverage). "
                            f"Consider generating tasks that address this objective."
                        ),
                        "corrective_action": corrective_action,
                    }
                )

        # If there are misaligned tasks, add a general realignment issue
        if drift_result.misaligned_tasks:
            misaligned_count = len(drift_result.misaligned_tasks)
            issues.append(
                {
                    "objective": "task_realignment",
                    "coverage_ratio": 0.0,
                    "description": (
                        f"{misaligned_count} tasks are misaligned with stated objectives. "
                        f"Review task generation criteria to ensure alignment."
                    ),
                    "corrective_action": {
                        "action_type": "review_task_generation",
                        "target": "task_generator",
                        "parameters": {
                            "misaligned_task_ids": drift_result.misaligned_tasks[:5],
                            "review_criteria": list(self.objectives.keys()),
                        },
                    },
                }
            )

        # Sort by coverage ratio (lowest first - most urgent)
        issues.sort(key=lambda x: x["coverage_ratio"])

        logger.debug(f"[IMP-LOOP-028] Analyzed drift direction: {len(issues)} issues found")

        return issues

    def _get_corrective_action_for_objective(
        self, objective: str, metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a corrective action for a specific neglected objective.

        Args:
            objective: The objective that needs attention
            metrics: Optional metrics for context

        Returns:
            Dictionary describing the corrective action
        """
        # Default corrective actions per objective type
        corrective_actions = {
            "reduce_cost": {
                "action_type": "generate_cost_optimization_tasks",
                "target": "cost_analyzer",
                "parameters": {
                    "focus_areas": ["token_usage", "api_calls", "resource_allocation"],
                    "priority": "high",
                },
            },
            "improve_success": {
                "action_type": "generate_success_improvement_tasks",
                "target": "success_analyzer",
                "parameters": {
                    "focus_areas": ["accuracy", "quality", "effectiveness"],
                    "priority": "high",
                },
            },
            "fix_failures": {
                "action_type": "generate_failure_fix_tasks",
                "target": "error_analyzer",
                "parameters": {
                    "focus_areas": ["recurring_errors", "bug_fixes", "issue_resolution"],
                    "priority": "critical",
                },
            },
            "reduce_retries": {
                "action_type": "generate_retry_reduction_tasks",
                "target": "retry_analyzer",
                "parameters": {
                    "focus_areas": ["redundancy", "duplicate_prevention", "efficiency"],
                    "priority": "medium",
                },
            },
            "improve_performance": {
                "action_type": "generate_performance_tasks",
                "target": "performance_analyzer",
                "parameters": {
                    "focus_areas": ["speed", "latency", "throughput"],
                    "priority": "high",
                },
            },
            "enhance_reliability": {
                "action_type": "generate_reliability_tasks",
                "target": "reliability_analyzer",
                "parameters": {
                    "focus_areas": ["stability", "consistency", "uptime"],
                    "priority": "high",
                },
            },
        }

        return corrective_actions.get(
            objective,
            {
                "action_type": "generate_objective_aligned_tasks",
                "target": "task_generator",
                "parameters": {
                    "objective": objective,
                    "priority": "medium",
                },
            },
        )

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


# =============================================================================
# IMP-LOOP-025: Loop Completeness Observability Metrics
# =============================================================================


@dataclass
class LoopCompletenessSnapshot:
    """A point-in-time snapshot of loop completeness metrics.

    IMP-LOOP-025: Captures the state of feedback loop health at a given moment.
    """

    total_insights: int
    insights_to_tasks: int
    task_successes: int
    task_total: int
    completeness_score: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_insights": self.total_insights,
            "insights_to_tasks": self.insights_to_tasks,
            "task_successes": self.task_successes,
            "task_total": self.task_total,
            "completeness_score": round(self.completeness_score, 4),
            "timestamp": self.timestamp.isoformat(),
        }


class LoopCompletenessMetric:
    """Tracks overall feedback loop health and completeness.

    IMP-LOOP-025: Provides a single metric answering 'how well is the feedback
    loop working?' by measuring the ratio of insights that convert to successful
    tasks.

    Formula: (insights_converted_to_tasks * task_success_rate) / total_insights
    Target: >70% completeness score

    The metric captures two key aspects:
    1. Conversion rate: What fraction of insights become actionable tasks?
    2. Success rate: What fraction of those tasks succeed?

    A high completeness score indicates a healthy feedback loop where:
    - Insights are being acted upon (high conversion)
    - Actions are effective (high success rate)

    Usage:
        metric = LoopCompletenessMetric()
        metric.record_insight(converted_to_task=True)
        metric.record_task_outcome(success=True)
        score = metric.calculate()  # Returns 0.0-1.0
        if score >= 0.7:
            print("Loop is healthy!")
    """

    # Target completeness score (70%)
    TARGET_COMPLETENESS: float = 0.70

    def __init__(self) -> None:
        """Initialize the loop completeness metric tracker."""
        self.total_insights: int = 0
        self.insights_to_tasks: int = 0
        self.task_successes: int = 0
        self.task_total: int = 0
        self._history: List[LoopCompletenessSnapshot] = []
        self._lock = __import__("threading").Lock()

    def record_insight(self, converted_to_task: bool) -> None:
        """Record an insight and whether it was converted to a task.

        Args:
            converted_to_task: True if the insight resulted in a task
        """
        with self._lock:
            self.total_insights += 1
            if converted_to_task:
                self.insights_to_tasks += 1

        logger.debug(
            f"[IMP-LOOP-025] Recorded insight: converted={converted_to_task}, "
            f"total={self.total_insights}, converted_count={self.insights_to_tasks}"
        )

    def record_task_outcome(self, success: bool) -> None:
        """Record a task execution outcome.

        Args:
            success: True if the task completed successfully
        """
        with self._lock:
            self.task_total += 1
            if success:
                self.task_successes += 1

        logger.debug(
            f"[IMP-LOOP-025] Recorded task outcome: success={success}, "
            f"total={self.task_total}, successes={self.task_successes}"
        )

    def _calculate_unlocked(self) -> float:
        """Calculate the loop completeness score (internal, no lock).

        Must be called with self._lock held.

        Returns:
            Completeness score from 0.0 to 1.0
        """
        if self.total_insights == 0:
            return 0.0

        conversion_rate = self.insights_to_tasks / self.total_insights
        success_rate = self.task_successes / self.task_total if self.task_total > 0 else 0.0
        return conversion_rate * success_rate

    def calculate(self) -> float:
        """Calculate the loop completeness score.

        Formula: (insights_to_tasks / total_insights) * (task_successes / task_total)

        This gives a combined score that reflects both:
        1. How many insights become tasks (conversion rate)
        2. How many tasks succeed (success rate)

        Returns:
            Completeness score from 0.0 to 1.0
        """
        with self._lock:
            return self._calculate_unlocked()

    def _get_conversion_rate_unlocked(self) -> float:
        """Get the insight-to-task conversion rate (internal, no lock).

        Must be called with self._lock held.

        Returns:
            Conversion rate from 0.0 to 1.0
        """
        if self.total_insights == 0:
            return 0.0
        return self.insights_to_tasks / self.total_insights

    def get_conversion_rate(self) -> float:
        """Get the insight-to-task conversion rate.

        Returns:
            Conversion rate from 0.0 to 1.0
        """
        with self._lock:
            return self._get_conversion_rate_unlocked()

    def _get_success_rate_unlocked(self) -> float:
        """Get the task success rate (internal, no lock).

        Must be called with self._lock held.

        Returns:
            Success rate from 0.0 to 1.0
        """
        if self.task_total == 0:
            return 0.0
        return self.task_successes / self.task_total

    def get_success_rate(self) -> float:
        """Get the task success rate.

        Returns:
            Success rate from 0.0 to 1.0
        """
        with self._lock:
            return self._get_success_rate_unlocked()

    def _is_healthy_unlocked(self) -> bool:
        """Check if the loop completeness meets the target threshold (internal, no lock).

        Must be called with self._lock held.

        Returns:
            True if completeness score >= 70%
        """
        return self._calculate_unlocked() >= self.TARGET_COMPLETENESS

    def is_healthy(self) -> bool:
        """Check if the loop completeness meets the target threshold.

        Returns:
            True if completeness score >= 70%
        """
        with self._lock:
            return self._is_healthy_unlocked()

    def _get_health_status_unlocked(self) -> str:
        """Get human-readable health status based on completeness score (internal, no lock).

        Must be called with self._lock held.

        Returns:
            Status string: "excellent", "good", "acceptable", "degraded", or "poor"
        """
        score = self._calculate_unlocked()

        if score >= 0.85:
            return "excellent"
        elif score >= self.TARGET_COMPLETENESS:
            return "good"
        elif score >= 0.50:
            return "acceptable"
        elif score >= 0.30:
            return "degraded"
        else:
            return "poor"

    def get_health_status(self) -> str:
        """Get human-readable health status based on completeness score.

        Returns:
            Status string: "excellent", "good", "acceptable", "degraded", or "poor"
        """
        with self._lock:
            return self._get_health_status_unlocked()

    def take_snapshot(self) -> LoopCompletenessSnapshot:
        """Take a point-in-time snapshot of current metrics.

        Returns:
            LoopCompletenessSnapshot with current state
        """
        with self._lock:
            snapshot = LoopCompletenessSnapshot(
                total_insights=self.total_insights,
                insights_to_tasks=self.insights_to_tasks,
                task_successes=self.task_successes,
                task_total=self.task_total,
                completeness_score=self._calculate_unlocked(),
            )
            self._history.append(snapshot)
            return snapshot

    def get_trend(self, window_size: int = 5) -> Optional[str]:
        """Analyze trend in completeness scores over recent snapshots.

        Args:
            window_size: Number of recent snapshots to analyze

        Returns:
            Trend direction: "improving", "stable", "degrading", or None if insufficient data
        """
        if len(self._history) < window_size:
            return None

        recent = self._history[-window_size:]
        scores = [s.completeness_score for s in recent]

        # Calculate trend direction
        first_half_avg = sum(scores[: window_size // 2]) / (window_size // 2)
        second_half_avg = sum(scores[window_size // 2 :]) / (window_size - window_size // 2)

        diff = second_half_avg - first_half_avg

        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        else:
            return "stable"

    def reset(self) -> None:
        """Reset all counters to zero."""
        with self._lock:
            self.total_insights = 0
            self.insights_to_tasks = 0
            self.task_successes = 0
            self.task_total = 0
            self._history.clear()

        logger.debug("[IMP-LOOP-025] Reset loop completeness metrics")

    def to_dict(self) -> Dict[str, Any]:
        """Convert current state to dictionary for serialization.

        Returns:
            Dict with all metric values and derived scores
        """
        with self._lock:
            return {
                "total_insights": self.total_insights,
                "insights_to_tasks": self.insights_to_tasks,
                "task_successes": self.task_successes,
                "task_total": self.task_total,
                "conversion_rate": round(self._get_conversion_rate_unlocked(), 4),
                "success_rate": round(self._get_success_rate_unlocked(), 4),
                "completeness_score": round(self._calculate_unlocked(), 4),
                "target_completeness": self.TARGET_COMPLETENESS,
                "is_healthy": self._is_healthy_unlocked(),
                "health_status": self._get_health_status_unlocked(),
                "trend": self.get_trend(),
                "history_size": len(self._history),
            }

    def export_to_prometheus(self) -> Dict[str, float]:
        """Export metrics in Prometheus-compatible format.

        Returns:
            Dict of metric names to float values suitable for Prometheus Gauges
        """
        return {
            "autopack_loop_completeness_score": self.calculate(),
            "autopack_loop_conversion_rate": self.get_conversion_rate(),
            "autopack_loop_task_success_rate": self.get_success_rate(),
            "autopack_loop_total_insights": float(self.total_insights),
            "autopack_loop_total_tasks": float(self.task_total),
        }


class LoopLatencyMetric:
    """Tracks time from insight generation to task execution.

    IMP-LOOP-025: Measures how quickly the feedback loop responds to insights.
    A lower latency indicates a more responsive self-improvement system.

    Key latencies tracked:
    - Insight to task creation
    - Task creation to task execution
    - End-to-end (insight to task completion)

    Target: < 5 minutes end-to-end latency
    """

    # Target end-to-end latency (5 minutes in ms)
    TARGET_LATENCY_MS: float = 300000

    def __init__(self) -> None:
        """Initialize the loop latency metric tracker."""
        self._insight_timestamps: Dict[str, datetime] = {}
        self._task_timestamps: Dict[str, datetime] = {}
        self._completion_timestamps: Dict[str, datetime] = {}
        self._latencies: List[Dict[str, Any]] = []
        self._lock = __import__("threading").Lock()

    def record_insight_created(self, insight_id: str) -> None:
        """Record when an insight is created.

        Args:
            insight_id: Unique identifier for the insight
        """
        with self._lock:
            self._insight_timestamps[insight_id] = datetime.utcnow()

    def record_task_created(self, insight_id: str, task_id: str) -> None:
        """Record when a task is created from an insight.

        Args:
            insight_id: The source insight identifier
            task_id: The created task identifier
        """
        with self._lock:
            self._task_timestamps[task_id] = datetime.utcnow()
            # Link task to insight for latency calculation
            if insight_id in self._insight_timestamps:
                insight_time = self._insight_timestamps[insight_id]
                task_time = self._task_timestamps[task_id]
                latency_ms = (task_time - insight_time).total_seconds() * 1000
                self._latencies.append(
                    {
                        "type": "insight_to_task",
                        "insight_id": insight_id,
                        "task_id": task_id,
                        "latency_ms": latency_ms,
                        "timestamp": task_time,
                    }
                )

    def record_task_completed(self, task_id: str) -> None:
        """Record when a task completes execution.

        Args:
            task_id: The completed task identifier
        """
        with self._lock:
            self._completion_timestamps[task_id] = datetime.utcnow()
            if task_id in self._task_timestamps:
                task_time = self._task_timestamps[task_id]
                completion_time = self._completion_timestamps[task_id]
                latency_ms = (completion_time - task_time).total_seconds() * 1000
                self._latencies.append(
                    {
                        "type": "task_to_completion",
                        "task_id": task_id,
                        "latency_ms": latency_ms,
                        "timestamp": completion_time,
                    }
                )

    def get_average_latency_ms(self, latency_type: Optional[str] = None) -> float:
        """Get average latency across recorded measurements.

        Args:
            latency_type: Optional filter for "insight_to_task" or "task_to_completion"

        Returns:
            Average latency in milliseconds
        """
        with self._lock:
            latencies = self._latencies
            if latency_type:
                latencies = [lat for lat in latencies if lat["type"] == latency_type]
            if not latencies:
                return 0.0
            return sum(lat["latency_ms"] for lat in latencies) / len(latencies)

    def is_within_target(self) -> bool:
        """Check if average latency is within target.

        Returns:
            True if average latency <= target
        """
        return self.get_average_latency_ms() <= self.TARGET_LATENCY_MS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "avg_insight_to_task_ms": self.get_average_latency_ms("insight_to_task"),
            "avg_task_to_completion_ms": self.get_average_latency_ms("task_to_completion"),
            "avg_total_latency_ms": self.get_average_latency_ms(),
            "target_latency_ms": self.TARGET_LATENCY_MS,
            "is_within_target": self.is_within_target(),
            "measurement_count": len(self._latencies),
        }


class LoopFidelityMetric:
    """Tracks accuracy of insight-to-task translation.

    IMP-LOOP-025: Measures whether generated tasks accurately address the
    original insights. High fidelity means tasks correctly target the issues
    identified by insights.

    Key aspects tracked:
    - Task relevance to original insight
    - Task scope accuracy (not too broad/narrow)
    - Task actionability (can be completed)

    Target: >80% fidelity score
    """

    # Target fidelity score (80%)
    TARGET_FIDELITY: float = 0.80

    def __init__(self) -> None:
        """Initialize the loop fidelity metric tracker."""
        self._fidelity_scores: List[Dict[str, Any]] = []
        self._lock = __import__("threading").Lock()

    def record_task_fidelity(
        self,
        task_id: str,
        insight_id: str,
        relevance_score: float,
        scope_accuracy: float,
        actionability_score: float,
    ) -> float:
        """Record fidelity scores for a task relative to its source insight.

        Args:
            task_id: The task identifier
            insight_id: The source insight identifier
            relevance_score: How relevant the task is to the insight (0.0-1.0)
            scope_accuracy: Whether task scope matches insight severity (0.0-1.0)
            actionability_score: Whether the task can be completed (0.0-1.0)

        Returns:
            Combined fidelity score (0.0-1.0)
        """
        # Weighted average: relevance most important
        fidelity = relevance_score * 0.5 + scope_accuracy * 0.3 + actionability_score * 0.2

        with self._lock:
            self._fidelity_scores.append(
                {
                    "task_id": task_id,
                    "insight_id": insight_id,
                    "relevance_score": relevance_score,
                    "scope_accuracy": scope_accuracy,
                    "actionability_score": actionability_score,
                    "fidelity_score": fidelity,
                    "timestamp": datetime.utcnow(),
                }
            )

        return fidelity

    def get_average_fidelity(self) -> float:
        """Get average fidelity score across all recorded tasks.

        Returns:
            Average fidelity score (0.0-1.0)
        """
        with self._lock:
            if not self._fidelity_scores:
                return 0.0
            return sum(f["fidelity_score"] for f in self._fidelity_scores) / len(
                self._fidelity_scores
            )

    def is_healthy(self) -> bool:
        """Check if average fidelity meets target.

        Returns:
            True if fidelity >= 80%
        """
        return self.get_average_fidelity() >= self.TARGET_FIDELITY

    def get_low_fidelity_tasks(self, threshold: float = 0.5) -> List[str]:
        """Get task IDs with fidelity below threshold.

        Args:
            threshold: Fidelity threshold (default 0.5)

        Returns:
            List of task IDs with low fidelity
        """
        with self._lock:
            return [f["task_id"] for f in self._fidelity_scores if f["fidelity_score"] < threshold]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "average_fidelity": round(self.get_average_fidelity(), 4),
            "target_fidelity": self.TARGET_FIDELITY,
            "is_healthy": self.is_healthy(),
            "total_measurements": len(self._fidelity_scores),
            "low_fidelity_count": len(self.get_low_fidelity_tasks()),
        }


# =============================================================================
# IMP-LOOP-029: Context Injection Effectiveness Measurement
# =============================================================================


@dataclass
class ContextInjectionEffectivenessResult:
    """Result of context injection effectiveness analysis.

    IMP-LOOP-029: Captures the comparative success rates of phases
    with and without context injection to measure memory system effectiveness.
    """

    with_context_success_rate: float  # Success rate when context was injected
    without_context_success_rate: float  # Success rate when no context
    delta: float  # Improvement from context (with - without)
    with_context_count: int  # Number of samples with context
    without_context_count: int  # Number of samples without context
    improvement_percent: float  # Percentage improvement
    is_significant: bool  # True if statistically meaningful (n>=10, delta>=5%)
    avg_memory_items_injected: float  # Average items when context present
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "with_context_success_rate": round(self.with_context_success_rate, 4),
            "without_context_success_rate": round(self.without_context_success_rate, 4),
            "delta": round(self.delta, 4),
            "with_context_count": self.with_context_count,
            "without_context_count": self.without_context_count,
            "improvement_percent": round(self.improvement_percent, 2),
            "is_significant": self.is_significant,
            "avg_memory_items_injected": round(self.avg_memory_items_injected, 2),
            "timestamp": self.timestamp.isoformat(),
        }


class ContextInjectionEffectivenessTracker:
    """Track effectiveness of context injection on phase outcomes.

    IMP-LOOP-029: Measures whether injecting memory context into phases
    improves their success rates. This enables data-driven decisions about
    memory retrieval strategies and context injection approaches.

    The tracker compares success rates between:
    - Phases with context injection (memory items provided)
    - Phases without context injection (no memory items)

    A positive delta indicates context injection is beneficial.

    Usage:
        tracker = ContextInjectionEffectivenessTracker()
        tracker.record_result(had_context=True, success=True, memory_count=5)
        tracker.record_result(had_context=False, success=False, memory_count=0)
        effectiveness = tracker.calculate_effectiveness()
        if effectiveness.is_significant and effectiveness.delta > 0:
            logger.info("Context injection is improving outcomes!")
    """

    # Thresholds for significance
    MIN_SAMPLES_FOR_SIGNIFICANCE: int = 10
    MIN_DELTA_FOR_SIGNIFICANCE: float = 0.05  # 5% improvement

    def __init__(self, min_samples: int = MIN_SAMPLES_FOR_SIGNIFICANCE):
        """Initialize the effectiveness tracker.

        Args:
            min_samples: Minimum samples required for statistical significance
        """
        self.min_samples = min_samples
        self._with_context_results: List[Dict[str, Any]] = []
        self._without_context_results: List[Dict[str, Any]] = []
        self._history: List[ContextInjectionEffectivenessResult] = []

    def record_result(
        self,
        had_context: bool,
        success: bool,
        memory_count: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a phase result for effectiveness comparison.

        Args:
            had_context: Whether context was injected for this phase
            success: Whether the phase succeeded
            memory_count: Number of memory items injected (if any)
            metrics: Optional additional metrics from phase execution
        """
        result = {
            "success": success,
            "memory_count": memory_count,
            "metrics": metrics or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if had_context:
            self._with_context_results.append(result)
        else:
            self._without_context_results.append(result)

        logger.debug(
            f"[IMP-LOOP-029] Recorded result: had_context={had_context}, "
            f"success={success}, memory_count={memory_count}"
        )

    def calculate_effectiveness(self) -> ContextInjectionEffectivenessResult:
        """Calculate context injection effectiveness metrics.

        Returns:
            ContextInjectionEffectivenessResult with comparison metrics
        """
        # Calculate success rates
        with_count = len(self._with_context_results)
        without_count = len(self._without_context_results)

        with_success = sum(1 for r in self._with_context_results if r["success"])
        without_success = sum(1 for r in self._without_context_results if r["success"])

        with_rate = with_success / with_count if with_count > 0 else 0.0
        without_rate = without_success / without_count if without_count > 0 else 0.0

        delta = with_rate - without_rate
        improvement_percent = (delta / without_rate * 100) if without_rate > 0 else 0.0

        # Calculate average memory items injected
        total_memory = sum(r["memory_count"] for r in self._with_context_results)
        avg_memory = total_memory / with_count if with_count > 0 else 0.0

        # Determine significance
        total_samples = with_count + without_count
        is_significant = (
            total_samples >= self.min_samples and abs(delta) >= self.MIN_DELTA_FOR_SIGNIFICANCE
        )

        result = ContextInjectionEffectivenessResult(
            with_context_success_rate=with_rate,
            without_context_success_rate=without_rate,
            delta=delta,
            with_context_count=with_count,
            without_context_count=without_count,
            improvement_percent=improvement_percent,
            is_significant=is_significant,
            avg_memory_items_injected=avg_memory,
        )

        # Track history
        self._history.append(result)

        logger.info(
            f"[IMP-LOOP-029] Context injection effectiveness: "
            f"with_context={with_rate:.2%} ({with_count}), "
            f"without_context={without_rate:.2%} ({without_count}), "
            f"delta={delta:+.2%}, significant={is_significant}"
        )

        return result

    def get_trend(self, window_size: int = 5) -> Optional[str]:
        """Analyze trend in effectiveness over recent measurements.

        Args:
            window_size: Number of recent measurements to analyze

        Returns:
            Trend direction: "improving", "stable", "declining", or None if insufficient data
        """
        if len(self._history) < window_size:
            return None

        recent = self._history[-window_size:]
        deltas = [r.delta for r in recent]

        first_half_avg = sum(deltas[: window_size // 2]) / (window_size // 2)
        second_half_avg = sum(deltas[window_size // 2 :]) / (window_size - window_size // 2)

        diff = second_half_avg - first_half_avg

        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        else:
            return "stable"

    def get_average_delta(self, window_size: int = 10) -> float:
        """Get average effectiveness delta over recent measurements.

        Args:
            window_size: Number of recent measurements to average

        Returns:
            Average delta value
        """
        if not self._history:
            return 0.0

        recent = self._history[-window_size:]
        return sum(r.delta for r in recent) / len(recent)

    def is_context_beneficial(self) -> bool:
        """Determine if context injection is beneficial based on current data.

        Returns:
            True if context injection shows statistically significant improvement
        """
        if not self._history:
            effectiveness = self.calculate_effectiveness()
        else:
            effectiveness = self._history[-1]

        return effectiveness.is_significant and effectiveness.delta > 0

    def get_recommendation(self) -> str:
        """Get a recommendation based on effectiveness data.

        Returns:
            Human-readable recommendation string
        """
        effectiveness = self.calculate_effectiveness()

        if (
            effectiveness.with_context_count + effectiveness.without_context_count
            < self.min_samples
        ):
            return (
                f"Insufficient data for recommendation. "
                f"Need {self.min_samples} samples, have "
                f"{effectiveness.with_context_count + effectiveness.without_context_count}."
            )

        if effectiveness.is_significant:
            if effectiveness.delta > 0:
                return (
                    f"Context injection is beneficial! "
                    f"Success rate improves by {effectiveness.delta:.1%} "
                    f"({effectiveness.improvement_percent:.1f}% relative improvement). "
                    f"Recommendation: Continue using context injection."
                )
            else:
                return (
                    f"Context injection may be harmful. "
                    f"Success rate decreases by {abs(effectiveness.delta):.1%}. "
                    f"Recommendation: Review context retrieval strategy."
                )
        else:
            return (
                f"No significant impact detected. "
                f"Delta is {effectiveness.delta:+.1%} which is below the "
                f"{self.MIN_DELTA_FOR_SIGNIFICANCE:.0%} threshold. "
                f"Recommendation: Continue monitoring with more data."
            )

    def clear_results(self) -> int:
        """Clear all recorded results.

        Returns:
            Number of results cleared
        """
        count = len(self._with_context_results) + len(self._without_context_results)
        self._with_context_results.clear()
        self._without_context_results.clear()
        logger.debug(f"[IMP-LOOP-029] Cleared {count} effectiveness results")
        return count

    def clear_history(self) -> int:
        """Clear effectiveness measurement history.

        Returns:
            Number of history entries cleared
        """
        count = len(self._history)
        self._history.clear()
        logger.debug(f"[IMP-LOOP-029] Cleared {count} effectiveness history entries")
        return count

    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary for serialization.

        Returns:
            Dict with all tracker state and computed metrics
        """
        current_effectiveness = (
            self._history[-1].to_dict()
            if self._history
            else self.calculate_effectiveness().to_dict()
        )

        return {
            "with_context_count": len(self._with_context_results),
            "without_context_count": len(self._without_context_results),
            "history_size": len(self._history),
            "current_effectiveness": current_effectiveness,
            "trend": self.get_trend(),
            "average_delta": round(self.get_average_delta(), 4),
            "is_context_beneficial": self.is_context_beneficial(),
            "recommendation": self.get_recommendation(),
        }


# =============================================================================
# IMP-SEG-002: Research Cycle Effectiveness Tracking
# =============================================================================


class ResearchCycleEffectivenessTracker:
    """Tracks research cycle effectiveness metrics for feedback loop optimization.

    IMP-SEG-002: Monitors whether follow-up research improved decision quality
    and enables feedback loops for continuous improvement.

    This tracker aggregates research cycle outcomes and provides metrics for:
    - Success rates of research cycles
    - Decision quality improvements
    - Follow-up research effectiveness
    - Cost and time efficiency
    - Feedback for future improvements
    """

    def __init__(self):
        """Initialize the research cycle effectiveness tracker."""
        self.cycle_count = 0
        self.successful_cycles = 0
        self.total_confidence_improvement = 0.0
        self.total_quality_improvement = 0.0
        self.total_roi = 0.0
        self.followup_triggers_executed = 0
        self.followup_triggers_successful = 0
        self.total_cost = 0.0
        self.total_time_seconds = 0

    def record_cycle_outcome(
        self,
        cycle_id: str,
        was_successful: bool,
        confidence_improvement: int = 0,
        quality_improvement: int = 0,
        roi: float = 1.0,
        followup_triggers_executed: int = 0,
        followup_triggers_successful: int = 0,
        cost: float = 0.0,
        time_seconds: int = 0,
    ) -> None:
        """Record a research cycle outcome.

        IMP-SEG-002: Tracks research cycle outcomes for effectiveness analysis.

        Args:
            cycle_id: Unique identifier for the cycle
            was_successful: Whether the cycle achieved its objectives
            confidence_improvement: Improvement in decision confidence (0-100)
            quality_improvement: Improvement in decision quality (0-100)
            roi: Return on investment ratio
            followup_triggers_executed: Number of follow-up triggers executed
            followup_triggers_successful: Number of successful follow-up triggers
            cost: Cost of the research cycle
            time_seconds: Time spent on the cycle
        """
        self.cycle_count += 1
        if was_successful:
            self.successful_cycles += 1
        self.total_confidence_improvement += confidence_improvement
        self.total_quality_improvement += quality_improvement
        self.total_roi += roi
        self.followup_triggers_executed += followup_triggers_executed
        self.followup_triggers_successful += followup_triggers_successful
        self.total_cost += cost
        self.total_time_seconds += time_seconds

    def get_success_rate(self) -> float:
        """Get the success rate of research cycles.

        Returns:
            Success rate as a percentage (0-100).
        """
        if self.cycle_count == 0:
            return 0.0
        return (self.successful_cycles / self.cycle_count) * 100

    def get_avg_confidence_improvement(self) -> float:
        """Get the average confidence improvement per cycle.

        Returns:
            Average confidence improvement.
        """
        if self.cycle_count == 0:
            return 0.0
        return self.total_confidence_improvement / self.cycle_count

    def get_avg_quality_improvement(self) -> float:
        """Get the average quality improvement per cycle.

        Returns:
            Average quality improvement.
        """
        if self.cycle_count == 0:
            return 0.0
        return self.total_quality_improvement / self.cycle_count

    def get_avg_roi(self) -> float:
        """Get the average ROI per cycle.

        Returns:
            Average return on investment.
        """
        if self.cycle_count == 0:
            return 1.0
        return self.total_roi / self.cycle_count

    def get_followup_trigger_success_rate(self) -> float:
        """Get the success rate of follow-up research triggers.

        Returns:
            Success rate as a ratio (0.0-1.0).
        """
        if self.followup_triggers_executed == 0:
            return 0.0
        return self.followup_triggers_successful / self.followup_triggers_executed

    def get_avg_cost_per_cycle(self) -> float:
        """Get the average cost per research cycle.

        Returns:
            Average cost.
        """
        if self.cycle_count == 0:
            return 0.0
        return self.total_cost / self.cycle_count

    def get_avg_time_per_cycle(self) -> float:
        """Get the average time per research cycle.

        Returns:
            Average time in seconds.
        """
        if self.cycle_count == 0:
            return 0.0
        return self.total_time_seconds / self.cycle_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert tracker state to dictionary for serialization.

        Returns:
            Dict with all tracker state and computed metrics
        """
        return {
            "total_cycles": self.cycle_count,
            "successful_cycles": self.successful_cycles,
            "success_rate_percent": round(self.get_success_rate(), 2),
            "avg_confidence_improvement": round(self.get_avg_confidence_improvement(), 2),
            "avg_quality_improvement": round(self.get_avg_quality_improvement(), 2),
            "avg_roi": round(self.get_avg_roi(), 2),
            "followup_triggers_executed": self.followup_triggers_executed,
            "followup_triggers_successful": self.followup_triggers_successful,
            "followup_trigger_success_rate": round(self.get_followup_trigger_success_rate(), 4),
            "total_cost": round(self.total_cost, 2),
            "avg_cost_per_cycle": round(self.get_avg_cost_per_cycle(), 2),
            "total_time_seconds": self.total_time_seconds,
            "avg_time_per_cycle_seconds": round(self.get_avg_time_per_cycle(), 2),
        }
