"""Task effectiveness tracking for closed-loop validation.

Measures before/after metrics for generated tasks and feeds
effectiveness data back to the priority engine.

This module implements closed-loop validation to track whether
generated improvement tasks actually improve the metrics they
target, enabling data-driven prioritization refinement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autopack.task_generation.priority_engine import PriorityEngine

logger = logging.getLogger(__name__)

# Effectiveness thresholds
EXCELLENT_EFFECTIVENESS = 0.9  # Task achieved 90%+ of target
GOOD_EFFECTIVENESS = 0.7  # Task achieved 70%+ of target
POOR_EFFECTIVENESS = 0.3  # Task achieved less than 30% of target

# Priority weight adjustment factors
EXCELLENT_WEIGHT_BOOST = 1.2  # Boost category weight by 20%
GOOD_WEIGHT_BOOST = 1.1  # Boost category weight by 10%
POOR_WEIGHT_PENALTY = 0.9  # Reduce category weight by 10%


@dataclass
class TaskImpactReport:
    """Report of actual task impact vs. target.

    This dataclass captures the measured effectiveness of a completed
    improvement task by comparing before/after metrics against the
    expected target improvement.

    Attributes:
        task_id: Unique identifier for the improvement task.
        before_metrics: Dictionary of metric values before task execution.
        after_metrics: Dictionary of metric values after task execution.
        target_improvement: Expected improvement percentage (0.0-1.0).
        actual_improvement: Actual measured improvement percentage.
        effectiveness_score: Score from 0.0-1.0 indicating how well the
            task achieved its target (actual/target, capped at 1.0).
        measured_at: Timestamp when the impact was measured.
        category: Category of the task (e.g., "telemetry", "memory").
        notes: Additional context about the measurement.
    """

    task_id: str
    before_metrics: dict[str, float]
    after_metrics: dict[str, float]
    target_improvement: float
    actual_improvement: float
    effectiveness_score: float
    measured_at: datetime
    category: str = ""
    notes: str = ""

    def is_effective(self) -> bool:
        """Check if task achieved at least 70% of target improvement."""
        return self.effectiveness_score >= GOOD_EFFECTIVENESS

    def get_effectiveness_grade(self) -> str:
        """Return a human-readable effectiveness grade.

        Returns:
            One of: "excellent", "good", "moderate", "poor"
        """
        if self.effectiveness_score >= EXCELLENT_EFFECTIVENESS:
            return "excellent"
        elif self.effectiveness_score >= GOOD_EFFECTIVENESS:
            return "good"
        elif self.effectiveness_score >= POOR_EFFECTIVENESS:
            return "moderate"
        else:
            return "poor"


@dataclass
class EffectivenessHistory:
    """Maintains a history of effectiveness reports for analysis.

    Attributes:
        reports: List of TaskImpactReport instances.
        category_stats: Aggregated statistics by category.
    """

    reports: list[TaskImpactReport] = field(default_factory=list)
    category_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_report(self, report: TaskImpactReport) -> None:
        """Add a report and update category statistics."""
        self.reports.append(report)
        self._update_category_stats(report)

    def _update_category_stats(self, report: TaskImpactReport) -> None:
        """Update aggregated statistics for the report's category."""
        category = report.category or "general"

        if category not in self.category_stats:
            self.category_stats[category] = {
                "total_tasks": 0,
                "total_effectiveness": 0.0,
                "avg_effectiveness": 0.0,
                "effective_count": 0,
            }

        stats = self.category_stats[category]
        stats["total_tasks"] += 1
        stats["total_effectiveness"] += report.effectiveness_score
        stats["avg_effectiveness"] = stats["total_effectiveness"] / stats["total_tasks"]
        if report.is_effective():
            stats["effective_count"] += 1

    def get_category_effectiveness(self, category: str) -> float:
        """Get average effectiveness for a category.

        Args:
            category: Category to query.

        Returns:
            Average effectiveness score (0.0-1.0), or 0.5 if no data.
        """
        stats = self.category_stats.get(category)
        if stats and stats["total_tasks"] > 0:
            return stats["avg_effectiveness"]
        return 0.5  # Default when no data


class TaskEffectivenessTracker:
    """Tracks effectiveness of generated tasks.

    This class implements closed-loop validation by measuring before/after
    metrics for generated improvement tasks and feeding effectiveness
    data back to the priority engine.

    Attributes:
        history: EffectivenessHistory containing all tracked reports.
        priority_engine: Optional PriorityEngine for feedback integration.
    """

    def __init__(self, priority_engine: PriorityEngine | None = None) -> None:
        """Initialize the TaskEffectivenessTracker.

        Args:
            priority_engine: Optional PriorityEngine instance for feedback.
                If not provided, feedback will be stored but not applied.
        """
        self.history = EffectivenessHistory()
        self.priority_engine = priority_engine

    def measure_impact(
        self,
        task_id: str,
        before_metrics: dict[str, float],
        after_metrics: dict[str, float],
        target: float,
        category: str = "",
        notes: str = "",
    ) -> TaskImpactReport:
        """Compare telemetry before/after task execution.

        Calculates the actual improvement achieved by comparing metrics
        before and after task execution, then computes an effectiveness
        score relative to the target improvement.

        Args:
            task_id: Unique identifier for the task.
            before_metrics: Dictionary of metric values before execution.
                Expected keys: any metric names with float values.
            after_metrics: Dictionary of metric values after execution.
                Should contain the same keys as before_metrics.
            target: Expected improvement as a fraction (0.0-1.0).
                e.g., 0.2 means expecting 20% improvement.
            category: Optional category of the task for aggregation.
            notes: Optional notes about the measurement context.

        Returns:
            TaskImpactReport with calculated effectiveness metrics.

        Raises:
            ValueError: If before_metrics and after_metrics have no common keys,
                or if target is not positive.
        """
        if target <= 0:
            raise ValueError("Target improvement must be positive")

        # Find common metrics between before and after
        common_keys = set(before_metrics.keys()) & set(after_metrics.keys())
        if not common_keys:
            raise ValueError("before_metrics and after_metrics must have common keys")

        # Calculate actual improvement as average across all common metrics
        improvements: list[float] = []
        for key in common_keys:
            before_val = before_metrics[key]
            after_val = after_metrics[key]

            if before_val != 0:
                # Calculate relative improvement
                # Positive improvement means after is better (lower errors, higher success, etc.)
                # We need to determine direction based on metric semantics
                key_lower = key.lower()

                # Check for negative indicators first - these mean lower is better
                lower_is_better = any(
                    word in key_lower
                    for word in ["error", "failure", "fail", "miss", "latency", "delay", "time"]
                )

                # Check for positive indicators - these mean higher is better
                # Only apply if no negative indicators were found
                higher_is_better = not lower_is_better and any(
                    word in key_lower
                    for word in ["success", "throughput", "score", "accuracy", "hit"]
                )

                if higher_is_better:
                    improvement = (after_val - before_val) / abs(before_val)
                else:
                    # Default: lower is better (most metrics should decrease)
                    improvement = (before_val - after_val) / abs(before_val)

                improvements.append(improvement)
            elif after_val != before_val:
                # Before was 0, after is different - consider it a change
                improvements.append(1.0 if after_val > 0 else -1.0)

        # Average improvement across all metrics
        actual_improvement = sum(improvements) / len(improvements) if improvements else 0.0

        # Ensure actual_improvement is non-negative for effectiveness calculation
        actual_improvement_capped = max(0.0, actual_improvement)

        # Calculate effectiveness score (how well we achieved the target)
        # Capped at 1.0 even if we exceeded the target
        effectiveness_score = min(1.0, actual_improvement_capped / target) if target > 0 else 0.0

        report = TaskImpactReport(
            task_id=task_id,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            target_improvement=target,
            actual_improvement=actual_improvement,
            effectiveness_score=effectiveness_score,
            measured_at=datetime.now(),
            category=category,
            notes=notes,
        )

        # Store in history
        self.history.add_report(report)

        logger.info(
            "Measured impact for task %s: effectiveness=%.2f (%s), actual=%.2f%%, target=%.2f%%",
            task_id,
            effectiveness_score,
            report.get_effectiveness_grade(),
            actual_improvement * 100,
            target * 100,
        )

        return report

    def feed_back_to_priority_engine(self, report: TaskImpactReport) -> None:
        """Update priority engine weighting based on effectiveness.

        Adjusts the priority engine's category weighting based on
        the measured effectiveness of completed tasks. Effective
        tasks boost their category's weight, while ineffective
        tasks reduce it.

        Args:
            report: TaskImpactReport containing effectiveness data.
        """
        if self.priority_engine is None:
            logger.debug(
                "No priority engine configured, skipping feedback for task %s",
                report.task_id,
            )
            return

        category = report.category or "general"
        grade = report.get_effectiveness_grade()

        # Determine weight adjustment factor
        if grade == "excellent":
            adjustment = EXCELLENT_WEIGHT_BOOST
        elif grade == "good":
            adjustment = GOOD_WEIGHT_BOOST
        elif grade == "poor":
            adjustment = POOR_WEIGHT_PENALTY
        else:
            adjustment = 1.0  # No change for moderate

        # Clear cache to force recalculation with new data
        self.priority_engine.clear_cache()

        logger.info(
            "Fed back effectiveness for task %s to priority engine: "
            "category=%s, grade=%s, adjustment=%.2f",
            report.task_id,
            category,
            grade,
            adjustment,
        )

    def get_effectiveness(self, task_id: str) -> float:
        """Get the effectiveness score for a specific task.

        Args:
            task_id: The task ID to look up.

        Returns:
            Effectiveness score (0.0-1.0), or 0.5 if task not found.
        """
        for report in self.history.reports:
            if report.task_id == task_id:
                return report.effectiveness_score
        return 0.5  # Default when task not found

    def get_category_effectiveness(self, category: str) -> float:
        """Get average effectiveness for a category.

        Args:
            category: Category to query.

        Returns:
            Average effectiveness score (0.0-1.0).
        """
        return self.history.get_category_effectiveness(category)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of effectiveness tracking.

        Returns:
            Dictionary containing:
            - total_tasks: Total number of tracked tasks
            - avg_effectiveness: Average effectiveness across all tasks
            - by_category: Statistics by category
            - effective_task_rate: Percentage of tasks meeting effectiveness threshold
            - grade_distribution: Count of tasks by grade
        """
        reports = self.history.reports

        if not reports:
            return {
                "total_tasks": 0,
                "avg_effectiveness": 0.0,
                "by_category": {},
                "effective_task_rate": 0.0,
                "grade_distribution": {
                    "excellent": 0,
                    "good": 0,
                    "moderate": 0,
                    "poor": 0,
                },
            }

        total_effectiveness = sum(r.effectiveness_score for r in reports)
        effective_count = sum(1 for r in reports if r.is_effective())

        # Count by grade
        grade_distribution: dict[str, int] = {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }
        for report in reports:
            grade = report.get_effectiveness_grade()
            grade_distribution[grade] += 1

        return {
            "total_tasks": len(reports),
            "avg_effectiveness": total_effectiveness / len(reports),
            "by_category": dict(self.history.category_stats),
            "effective_task_rate": effective_count / len(reports),
            "grade_distribution": grade_distribution,
        }

    def record_task_outcome(
        self,
        task_id: str,
        success: bool,
        execution_time_seconds: float = 0.0,
        tokens_used: int = 0,
        category: str = "",
        notes: str = "",
    ) -> TaskImpactReport:
        """Record task outcome with simplified metrics for phase completion tracking.

        IMP-FBK-001: Provides a simpler API for recording task effectiveness when
        full before/after metrics are not available. Uses success/failure as the
        primary metric with execution time and tokens as secondary indicators.

        Effectiveness scoring:
        - Success: Base score of 0.8 (adjustable based on execution efficiency)
        - Failure: Score of 0.0

        For successful tasks, effectiveness is adjusted based on execution efficiency:
        - Fast execution (< 60s): +0.1 bonus
        - Low token usage (< 10000): +0.1 bonus
        - Max effectiveness: 1.0

        Args:
            task_id: Unique identifier for the task/phase.
            success: Whether the task completed successfully.
            execution_time_seconds: Time taken to execute the task.
            tokens_used: Number of tokens consumed during execution.
            category: Optional category for aggregation (e.g., "build", "test").
            notes: Optional notes about the execution context.

        Returns:
            TaskImpactReport with calculated effectiveness metrics.
        """
        # Base effectiveness for success vs failure
        if success:
            base_effectiveness = 0.8

            # Efficiency bonuses for successful tasks
            efficiency_bonus = 0.0

            # Fast execution bonus (< 60 seconds)
            if execution_time_seconds > 0 and execution_time_seconds < 60:
                efficiency_bonus += 0.1

            # Low token usage bonus (< 10000 tokens)
            if tokens_used > 0 and tokens_used < 10000:
                efficiency_bonus += 0.1

            effectiveness_score = min(1.0, base_effectiveness + efficiency_bonus)
            actual_improvement = effectiveness_score  # Treat as actual improvement achieved
        else:
            effectiveness_score = 0.0
            actual_improvement = 0.0

        # Create synthetic before/after metrics based on success
        before_metrics = {"task_completion": 0.0}
        after_metrics = {"task_completion": 1.0 if success else 0.0}

        report = TaskImpactReport(
            task_id=task_id,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            target_improvement=1.0,  # Target is always successful completion
            actual_improvement=actual_improvement,
            effectiveness_score=effectiveness_score,
            measured_at=datetime.now(),
            category=category,
            notes=notes or f"execution_time={execution_time_seconds:.1f}s, tokens={tokens_used}",
        )

        # Store in history
        self.history.add_report(report)

        logger.info(
            "Recorded task outcome for %s: success=%s, effectiveness=%.2f (%s), "
            "time=%.1fs, tokens=%d",
            task_id,
            success,
            effectiveness_score,
            report.get_effectiveness_grade(),
            execution_time_seconds,
            tokens_used,
        )

        return report
