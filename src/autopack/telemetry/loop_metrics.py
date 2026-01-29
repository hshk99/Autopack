"""Closed-Loop Observability Metrics.

IMP-OBS-001: Tracks feedback loop effectiveness metrics for
monitoring self-improvement loop health and ROI.

This module provides metrics for:
- Issues detected -> tasks generated conversion funnel
- Task success rate by source
- Failure prevention rate
- Insight confidence calibration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InsightSource(Enum):
    """Source types for insights in the feedback loop."""

    TELEMETRY_ANALYZER = "telemetry_analyzer"
    MEMORY_SERVICE = "memory_service"
    ANOMALY_DETECTOR = "anomaly_detector"
    CAUSAL_ANALYSIS = "causal_analysis"
    REGRESSION_PROTECTOR = "regression_protector"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class TaskOutcome(Enum):
    """Possible outcomes for generated tasks."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    PENDING = "pending"
    SKIPPED = "skipped"


@dataclass
class LoopEffectivenessMetrics:
    """Metrics for feedback loop effectiveness.

    IMP-OBS-001: Aggregated metrics tracking the conversion funnel
    from insight detection through task execution and outcomes.

    Attributes:
        insights_detected: Total number of insights detected.
        insights_filtered: Insights filtered out (low confidence, duplicate, etc.).
        tasks_generated: Number of tasks generated from insights.
        tasks_succeeded: Number of tasks that completed successfully.
        tasks_failed: Number of tasks that failed.
        tasks_partial: Number of tasks with partial success.
        tasks_pending: Number of tasks awaiting execution.
        failures_prevented: Estimated failures prevented by tasks.
        conversion_rate: Ratio of tasks generated to insights detected.
        success_rate: Ratio of successful tasks to total completed tasks.
        success_rate_by_source: Success rates broken down by insight source.
        confidence_calibration: Measures how well confidence predicts success.
    """

    insights_detected: int = 0
    insights_filtered: int = 0
    tasks_generated: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_partial: int = 0
    tasks_pending: int = 0
    failures_prevented: int = 0
    conversion_rate: float = 0.0
    success_rate: float = 0.0
    success_rate_by_source: Dict[str, float] = field(default_factory=dict)
    confidence_calibration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "insights_detected": self.insights_detected,
            "insights_filtered": self.insights_filtered,
            "tasks_generated": self.tasks_generated,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "tasks_partial": self.tasks_partial,
            "tasks_pending": self.tasks_pending,
            "failures_prevented": self.failures_prevented,
            "conversion_rate": round(self.conversion_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "success_rate_by_source": {
                k: round(v, 4) for k, v in self.success_rate_by_source.items()
            },
            "confidence_calibration": round(self.confidence_calibration, 4),
        }


@dataclass
class InsightRecord:
    """Record of a detected insight for tracking.

    IMP-OBS-001: Tracks individual insights through the conversion funnel.

    Attributes:
        insight_id: Unique identifier for the insight.
        source: Source that generated the insight.
        confidence: Confidence score at detection time.
        detected_at: Timestamp when the insight was detected.
        was_filtered: Whether the insight was filtered out.
        filter_reason: Reason for filtering (if applicable).
        task_id: ID of generated task (if converted).
        task_outcome: Outcome of the task (if executed).
    """

    insight_id: str
    source: InsightSource
    confidence: float = 1.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    was_filtered: bool = False
    filter_reason: Optional[str] = None
    task_id: Optional[str] = None
    task_outcome: Optional[TaskOutcome] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "insight_id": self.insight_id,
            "source": self.source.value,
            "confidence": self.confidence,
            "detected_at": self.detected_at.isoformat(),
            "was_filtered": self.was_filtered,
            "filter_reason": self.filter_reason,
            "task_id": self.task_id,
            "task_outcome": self.task_outcome.value if self.task_outcome else None,
        }


@dataclass
class SourceStats:
    """Statistics for a specific insight source.

    IMP-OBS-001: Tracks metrics per source for source-level analysis.
    """

    source: InsightSource
    insights_count: int = 0
    filtered_count: int = 0
    tasks_generated: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_partial: int = 0
    total_confidence: float = 0.0
    successful_confidence_sum: float = 0.0
    failed_confidence_sum: float = 0.0

    @property
    def conversion_rate(self) -> float:
        """Calculate conversion rate from insights to tasks."""
        if self.insights_count == 0:
            return 0.0
        return self.tasks_generated / self.insights_count

    @property
    def success_rate(self) -> float:
        """Calculate success rate for completed tasks."""
        completed = self.tasks_succeeded + self.tasks_failed + self.tasks_partial
        if completed == 0:
            return 0.0
        return self.tasks_succeeded / completed

    @property
    def avg_confidence(self) -> float:
        """Calculate average confidence for insights from this source."""
        if self.insights_count == 0:
            return 0.0
        return self.total_confidence / self.insights_count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source.value,
            "insights_count": self.insights_count,
            "filtered_count": self.filtered_count,
            "tasks_generated": self.tasks_generated,
            "tasks_succeeded": self.tasks_succeeded,
            "tasks_failed": self.tasks_failed,
            "tasks_partial": self.tasks_partial,
            "conversion_rate": round(self.conversion_rate, 4),
            "success_rate": round(self.success_rate, 4),
            "avg_confidence": round(self.avg_confidence, 4),
        }


@dataclass
class ConfidenceCalibrationBucket:
    """Bucket for confidence calibration analysis.

    IMP-OBS-001: Groups insights by confidence range to measure
    how well confidence scores predict actual success rates.
    """

    min_confidence: float
    max_confidence: float
    insight_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def midpoint(self) -> float:
        """Get the midpoint confidence for this bucket."""
        return (self.min_confidence + self.max_confidence) / 2

    @property
    def actual_success_rate(self) -> float:
        """Calculate actual success rate in this bucket."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def calibration_error(self) -> float:
        """Calculate calibration error (difference from expected success rate)."""
        if self.success_count + self.failure_count == 0:
            return 0.0
        return abs(self.midpoint - self.actual_success_rate)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "confidence_range": f"{self.min_confidence:.1f}-{self.max_confidence:.1f}",
            "midpoint": round(self.midpoint, 2),
            "insight_count": self.insight_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "actual_success_rate": round(self.actual_success_rate, 4),
            "calibration_error": round(self.calibration_error, 4),
        }


class LoopMetricsCollector:
    """Collects and reports feedback loop effectiveness metrics.

    IMP-OBS-001: Central collector for closed-loop observability metrics.
    Tracks insights through the conversion funnel from detection to task
    execution, enabling measurement of feedback loop ROI.

    The collector tracks:
    1. Conversion funnel: insights -> filtered -> tasks -> outcomes
    2. Success rates by insight source
    3. Failure prevention (estimated)
    4. Confidence calibration (predicted vs actual success)

    Usage:
        collector = LoopMetricsCollector()
        collector.record_insight_detected("insight-1", InsightSource.TELEMETRY_ANALYZER, 0.8)
        collector.record_task_generated("insight-1", "task-1")
        collector.record_task_outcome("task-1", TaskOutcome.SUCCESS)
        metrics = collector.get_metrics()
    """

    # Confidence calibration bucket boundaries
    CALIBRATION_BUCKETS = [
        (0.0, 0.2),
        (0.2, 0.4),
        (0.4, 0.6),
        (0.6, 0.8),
        (0.8, 1.0),
    ]

    def __init__(self) -> None:
        """Initialize the LoopMetricsCollector."""
        self._insights: Dict[str, InsightRecord] = {}
        self._task_to_insight: Dict[str, str] = {}  # task_id -> insight_id
        self._source_stats: Dict[InsightSource, SourceStats] = {}
        self._failures_prevented: int = 0
        self._calibration_buckets: List[ConfidenceCalibrationBucket] = [
            ConfidenceCalibrationBucket(min_conf, max_conf)
            for min_conf, max_conf in self.CALIBRATION_BUCKETS
        ]

        logger.debug("[IMP-OBS-001] LoopMetricsCollector initialized")

    def record_insight_detected(
        self,
        insight_id: str,
        source: InsightSource | str,
        confidence: float = 1.0,
    ) -> InsightRecord:
        """Record that an insight was detected.

        IMP-OBS-001: Entry point for the conversion funnel. Records an
        insight detection event with its source and confidence.

        Args:
            insight_id: Unique identifier for the insight.
            source: Source that generated the insight (enum or string).
            confidence: Confidence score for the insight (0.0-1.0).

        Returns:
            InsightRecord tracking this insight.
        """
        # Convert string source to enum if needed
        if isinstance(source, str):
            try:
                source = InsightSource(source)
            except ValueError:
                source = InsightSource.UNKNOWN

        # Create or update insight record
        if insight_id in self._insights:
            record = self._insights[insight_id]
            logger.debug(
                "[IMP-OBS-001] Insight %s already recorded, updating",
                insight_id,
            )
        else:
            record = InsightRecord(
                insight_id=insight_id,
                source=source,
                confidence=confidence,
            )
            self._insights[insight_id] = record

        # Update source stats
        if source not in self._source_stats:
            self._source_stats[source] = SourceStats(source=source)
        stats = self._source_stats[source]
        stats.insights_count += 1
        stats.total_confidence += confidence

        logger.info(
            "[IMP-OBS-001] Recorded insight detected: id=%s, source=%s, confidence=%.2f",
            insight_id,
            source.value,
            confidence,
        )

        return record

    def record_insight_filtered(
        self,
        insight_id: str,
        reason: str = "low_confidence",
    ) -> Optional[InsightRecord]:
        """Record that an insight was filtered out.

        IMP-OBS-001: Records when an insight is filtered from task generation,
        tracking why insights don't convert to tasks.

        Args:
            insight_id: The insight ID to mark as filtered.
            reason: Reason for filtering (e.g., "low_confidence", "duplicate").

        Returns:
            Updated InsightRecord or None if insight not found.
        """
        if insight_id not in self._insights:
            logger.warning(
                "[IMP-OBS-001] Cannot filter unknown insight: %s",
                insight_id,
            )
            return None

        record = self._insights[insight_id]
        record.was_filtered = True
        record.filter_reason = reason

        # Update source stats
        if record.source in self._source_stats:
            self._source_stats[record.source].filtered_count += 1

        logger.info(
            "[IMP-OBS-001] Recorded insight filtered: id=%s, reason=%s",
            insight_id,
            reason,
        )

        return record

    def record_task_generated(
        self,
        insight_id: str,
        task_id: str,
    ) -> Optional[InsightRecord]:
        """Record that a task was generated from an insight.

        IMP-OBS-001: Records the conversion from insight to task,
        the key metric for conversion funnel analysis.

        Args:
            insight_id: The source insight ID.
            task_id: The generated task ID.

        Returns:
            Updated InsightRecord or None if insight not found.
        """
        if insight_id not in self._insights:
            # Auto-create insight record if needed
            logger.debug(
                "[IMP-OBS-001] Creating implicit insight record for: %s",
                insight_id,
            )
            self.record_insight_detected(insight_id, InsightSource.UNKNOWN)

        record = self._insights[insight_id]
        record.task_id = task_id
        record.task_outcome = TaskOutcome.PENDING
        self._task_to_insight[task_id] = insight_id

        # Update source stats
        if record.source in self._source_stats:
            self._source_stats[record.source].tasks_generated += 1

        logger.info(
            "[IMP-OBS-001] Recorded task generated: insight=%s -> task=%s",
            insight_id,
            task_id,
        )

        return record

    def record_task_outcome(
        self,
        task_id: str,
        outcome: TaskOutcome | str,
    ) -> Optional[InsightRecord]:
        """Record the outcome of a task.

        IMP-OBS-001: Records task completion, enabling success rate
        calculation and confidence calibration analysis.

        Args:
            task_id: The task ID to record outcome for.
            outcome: Task outcome (enum or string).

        Returns:
            Updated InsightRecord or None if task not found.
        """
        # Convert string outcome to enum if needed
        if isinstance(outcome, str):
            try:
                outcome = TaskOutcome(outcome)
            except ValueError:
                logger.warning(
                    "[IMP-OBS-001] Invalid outcome '%s', defaulting to FAILURE",
                    outcome,
                )
                outcome = TaskOutcome.FAILURE

        if task_id not in self._task_to_insight:
            logger.warning(
                "[IMP-OBS-001] Cannot record outcome for unknown task: %s",
                task_id,
            )
            return None

        insight_id = self._task_to_insight[task_id]
        record = self._insights[insight_id]
        record.task_outcome = outcome

        # Update source stats
        if record.source in self._source_stats:
            stats = self._source_stats[record.source]
            if outcome == TaskOutcome.SUCCESS:
                stats.tasks_succeeded += 1
                stats.successful_confidence_sum += record.confidence
            elif outcome == TaskOutcome.FAILURE:
                stats.tasks_failed += 1
                stats.failed_confidence_sum += record.confidence
            elif outcome == TaskOutcome.PARTIAL:
                stats.tasks_partial += 1

        # Update calibration buckets
        self._update_calibration(record.confidence, outcome)

        logger.info(
            "[IMP-OBS-001] Recorded task outcome: task=%s, outcome=%s, insight=%s",
            task_id,
            outcome.value,
            insight_id,
        )

        return record

    def record_failure_prevented(self, count: int = 1) -> None:
        """Record that failures were prevented by the feedback loop.

        IMP-OBS-001: Tracks the ROI of the feedback loop by counting
        failures that were prevented by generated tasks.

        Args:
            count: Number of failures prevented.
        """
        self._failures_prevented += count
        logger.info(
            "[IMP-OBS-001] Recorded %d failure(s) prevented, total=%d",
            count,
            self._failures_prevented,
        )

    def _update_calibration(
        self,
        confidence: float,
        outcome: TaskOutcome,
    ) -> None:
        """Update confidence calibration buckets.

        Args:
            confidence: Confidence score of the insight.
            outcome: Task outcome (success/failure).
        """
        # Find the appropriate bucket
        for bucket in self._calibration_buckets:
            if bucket.min_confidence <= confidence < bucket.max_confidence:
                bucket.insight_count += 1
                if outcome == TaskOutcome.SUCCESS:
                    bucket.success_count += 1
                elif outcome == TaskOutcome.FAILURE:
                    bucket.failure_count += 1
                break
        # Handle edge case for confidence = 1.0
        if confidence == 1.0:
            bucket = self._calibration_buckets[-1]
            bucket.insight_count += 1
            if outcome == TaskOutcome.SUCCESS:
                bucket.success_count += 1
            elif outcome == TaskOutcome.FAILURE:
                bucket.failure_count += 1

    def _calculate_calibration_score(self) -> float:
        """Calculate overall confidence calibration score.

        Returns 1.0 for perfect calibration (confidence matches success rate),
        0.0 for worst calibration.

        Returns:
            Calibration score between 0.0 and 1.0.
        """
        total_error = 0.0
        total_weight = 0.0

        for bucket in self._calibration_buckets:
            weight = bucket.success_count + bucket.failure_count
            if weight > 0:
                total_error += bucket.calibration_error * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        # Convert average error to score (1.0 = perfect, 0.0 = worst)
        avg_error = total_error / total_weight
        return max(0.0, 1.0 - avg_error)

    def get_metrics(self) -> LoopEffectivenessMetrics:
        """Get aggregated feedback loop effectiveness metrics.

        IMP-OBS-001: Returns the complete metrics snapshot for
        dashboard display and monitoring.

        Returns:
            LoopEffectivenessMetrics with all calculated metrics.
        """
        # Count insights by status
        total_insights = len(self._insights)
        filtered = sum(1 for r in self._insights.values() if r.was_filtered)
        with_tasks = sum(1 for r in self._insights.values() if r.task_id is not None)

        # Count task outcomes
        succeeded = sum(1 for r in self._insights.values() if r.task_outcome == TaskOutcome.SUCCESS)
        failed = sum(1 for r in self._insights.values() if r.task_outcome == TaskOutcome.FAILURE)
        partial = sum(1 for r in self._insights.values() if r.task_outcome == TaskOutcome.PARTIAL)
        pending = sum(1 for r in self._insights.values() if r.task_outcome == TaskOutcome.PENDING)

        # Calculate rates
        conversion_rate = with_tasks / total_insights if total_insights > 0 else 0.0
        completed = succeeded + failed + partial
        success_rate = succeeded / completed if completed > 0 else 0.0

        # Build success rate by source
        success_rate_by_source = {
            source.value: stats.success_rate
            for source, stats in self._source_stats.items()
            if stats.tasks_succeeded + stats.tasks_failed + stats.tasks_partial > 0
        }

        # Calculate calibration score
        calibration = self._calculate_calibration_score()

        metrics = LoopEffectivenessMetrics(
            insights_detected=total_insights,
            insights_filtered=filtered,
            tasks_generated=with_tasks,
            tasks_succeeded=succeeded,
            tasks_failed=failed,
            tasks_partial=partial,
            tasks_pending=pending,
            failures_prevented=self._failures_prevented,
            conversion_rate=conversion_rate,
            success_rate=success_rate,
            success_rate_by_source=success_rate_by_source,
            confidence_calibration=calibration,
        )

        logger.debug(
            "[IMP-OBS-001] Generated metrics: insights=%d, tasks=%d, "
            "success_rate=%.2f%%, calibration=%.2f",
            total_insights,
            with_tasks,
            success_rate * 100,
            calibration,
        )

        return metrics

    def get_source_breakdown(self) -> List[Dict[str, Any]]:
        """Get detailed metrics breakdown by insight source.

        IMP-OBS-001: Returns per-source metrics for identifying
        which sources produce the most effective insights.

        Returns:
            List of source statistics dictionaries.
        """
        return [stats.to_dict() for stats in self._source_stats.values()]

    def get_calibration_breakdown(self) -> List[Dict[str, Any]]:
        """Get confidence calibration breakdown by bucket.

        IMP-OBS-001: Returns calibration data showing how well
        confidence scores predict actual success rates.

        Returns:
            List of calibration bucket dictionaries.
        """
        return [bucket.to_dict() for bucket in self._calibration_buckets]

    def get_conversion_funnel(self) -> Dict[str, Any]:
        """Get conversion funnel visualization data.

        IMP-OBS-001: Returns funnel data for visualizing the
        insight-to-outcome conversion pipeline.

        Returns:
            Dictionary with funnel stage counts and conversion rates.
        """
        total = len(self._insights)
        filtered = sum(1 for r in self._insights.values() if r.was_filtered)
        not_filtered = total - filtered
        with_tasks = sum(1 for r in self._insights.values() if r.task_id is not None)
        completed = sum(
            1
            for r in self._insights.values()
            if r.task_outcome in (TaskOutcome.SUCCESS, TaskOutcome.FAILURE, TaskOutcome.PARTIAL)
        )
        succeeded = sum(1 for r in self._insights.values() if r.task_outcome == TaskOutcome.SUCCESS)

        return {
            "stages": [
                {"name": "Insights Detected", "count": total},
                {"name": "Passed Filtering", "count": not_filtered},
                {"name": "Tasks Generated", "count": with_tasks},
                {"name": "Tasks Completed", "count": completed},
                {"name": "Tasks Succeeded", "count": succeeded},
            ],
            "conversion_rates": {
                "detection_to_filtering": (not_filtered / total if total > 0 else 0.0),
                "filtering_to_task": (with_tasks / not_filtered if not_filtered > 0 else 0.0),
                "task_to_completion": (completed / with_tasks if with_tasks > 0 else 0.0),
                "completion_to_success": (succeeded / completed if completed > 0 else 0.0),
                "end_to_end": (succeeded / total if total > 0 else 0.0),
            },
        }

    def get_insight_record(self, insight_id: str) -> Optional[InsightRecord]:
        """Get the record for a specific insight.

        Args:
            insight_id: The insight ID to look up.

        Returns:
            InsightRecord or None if not found.
        """
        return self._insights.get(insight_id)

    def get_summary(self) -> Dict[str, Any]:
        """Get a comprehensive summary of loop metrics.

        IMP-OBS-001: Returns all metrics in a single dictionary
        suitable for dashboard display or API response.

        Returns:
            Dictionary containing all metrics and breakdowns.
        """
        metrics = self.get_metrics()
        return {
            "metrics": metrics.to_dict(),
            "source_breakdown": self.get_source_breakdown(),
            "calibration_breakdown": self.get_calibration_breakdown(),
            "conversion_funnel": self.get_conversion_funnel(),
            "failures_prevented": self._failures_prevented,
        }

    def reset(self) -> None:
        """Reset all metrics to initial state.

        IMP-OBS-001: Clears all tracked data for a fresh start.
        Useful for testing or when starting a new monitoring period.
        """
        self._insights.clear()
        self._task_to_insight.clear()
        self._source_stats.clear()
        self._failures_prevented = 0
        self._calibration_buckets = [
            ConfidenceCalibrationBucket(min_conf, max_conf)
            for min_conf, max_conf in self.CALIBRATION_BUCKETS
        ]
        logger.info("[IMP-OBS-001] LoopMetricsCollector reset")
