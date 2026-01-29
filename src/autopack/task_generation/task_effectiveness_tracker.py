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
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from autopack.memory.learning_db import LearningDatabase
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

# IMP-LOOP-017: Thresholds for automatic rule generation
MIN_SAMPLE_SIZE = 5  # Minimum observations before generating rules
LOW_SUCCESS_THRESHOLD = 0.5  # Below this → avoid_pattern rule
HIGH_SUCCESS_THRESHOLD = 0.8  # Above this → prefer_pattern rule

# IMP-LOOP-022: Corrective task generation thresholds
CORRECTIVE_TASK_FAILURE_THRESHOLD = 3  # Generate corrective task after this many failures


@dataclass
class RegisteredTask:
    """Represents a task registered for execution verification.

    IMP-LOOP-021: Tracks generated improvement tasks to verify they are
    actually executed, enabling closed-loop feedback validation.

    Attributes:
        task_id: Unique identifier for the task.
        priority: Priority level of the task (critical, high, medium, low).
        category: Category of the task for aggregation.
        registered_at: Timestamp when the task was registered.
        executed: Whether the task has been executed.
        executed_at: Timestamp when execution was recorded.
        execution_success: Whether the execution was successful.
    """

    task_id: str
    priority: str = ""
    category: str = ""
    registered_at: datetime = field(default_factory=datetime.now)
    executed: bool = False
    executed_at: datetime | None = None
    execution_success: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "priority": self.priority,
            "category": self.category,
            "registered_at": self.registered_at.isoformat(),
            "executed": self.executed,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_success": self.execution_success,
        }


@dataclass
class EffectivenessLearningRule:
    """Rule generated from task effectiveness patterns.

    IMP-LOOP-017: Automatically created when task patterns cross thresholds,
    enabling the learning system to guide future task generation.

    Attributes:
        rule_type: "avoid_pattern" for low success, "prefer_pattern" for high success
        pattern: The task category or pattern this rule applies to
        confidence: Confidence level derived from success rate (0.0-1.0)
        reason: Human-readable explanation for why this rule was created
        sample_size: Number of observations this rule is based on
        success_rate: The measured success rate that triggered the rule
        created_at: Timestamp when the rule was generated
    """

    rule_type: str  # "avoid_pattern" or "prefer_pattern"
    pattern: str  # Task category/type
    confidence: float  # Derived from success rate
    reason: str  # Human-readable explanation
    sample_size: int = 0
    success_rate: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "rule_type": self.rule_type,
            "pattern": self.pattern,
            "confidence": self.confidence,
            "reason": self.reason,
            "sample_size": self.sample_size,
            "success_rate": self.success_rate,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CorrectiveTask:
    """Represents a corrective task generated after repeated failures.

    IMP-LOOP-022: When a task fails repeatedly (3+ times), the system
    automatically generates a corrective task to investigate and fix
    the root cause of the failures.

    Attributes:
        corrective_id: Unique identifier for the corrective task.
        original_task_id: The task ID that triggered this corrective task.
        failure_count: Number of failures that triggered this task.
        error_patterns: Common error patterns detected across failures.
        priority: Priority level (always "high" for corrective tasks).
        category: Category of the original task.
        created_at: Timestamp when the corrective task was created.
    """

    corrective_id: str
    original_task_id: str
    failure_count: int
    error_patterns: list[str] = field(default_factory=list)
    priority: str = "high"
    category: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "corrective_id": self.corrective_id,
            "original_task_id": self.original_task_id,
            "failure_count": self.failure_count,
            "error_patterns": self.error_patterns,
            "priority": self.priority,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
            "type": "corrective",
        }


@dataclass
class TaskExecutionMapping:
    """Maps a generated task to its phase execution for attribution tracking.

    IMP-LOOP-028: Enables end-to-end tracing from task generation to execution
    outcome. This is the core linking mechanism for closed-loop learning.

    Attributes:
        task_id: The generated task identifier (e.g., IMP-LOOP-028).
        phase_id: The phase execution identifier where this task runs.
        registered_at: Timestamp when the mapping was created.
        outcome_recorded: Whether the outcome has been recorded.
        outcome_recorded_at: Timestamp when outcome was recorded.
    """

    task_id: str
    phase_id: str
    registered_at: datetime = field(default_factory=datetime.now)
    outcome_recorded: bool = False
    outcome_recorded_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "phase_id": self.phase_id,
            "registered_at": self.registered_at.isoformat(),
            "outcome_recorded": self.outcome_recorded,
            "outcome_recorded_at": (
                self.outcome_recorded_at.isoformat() if self.outcome_recorded_at else None
            ),
        }


@dataclass
class TaskAttributionOutcome:
    """Outcome metrics for a task execution, linked via attribution.

    IMP-LOOP-028: Captures the outcome of a task execution with full
    traceability back to the generated task. Enables measuring whether
    generated tasks achieve their intended improvements.

    Attributes:
        task_id: The generated task identifier.
        phase_id: The phase execution identifier.
        success: Whether the execution was successful.
        execution_time_seconds: Duration of execution.
        tokens_used: Number of tokens consumed.
        error_message: Error message if execution failed.
        effectiveness_score: Computed effectiveness (0.0-1.0).
        recorded_at: Timestamp when the outcome was recorded.
        metadata: Additional outcome metadata.
    """

    task_id: str
    phase_id: str
    success: bool
    execution_time_seconds: float = 0.0
    tokens_used: int = 0
    error_message: str | None = None
    effectiveness_score: float = 0.0
    recorded_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "phase_id": self.phase_id,
            "success": self.success,
            "execution_time_seconds": self.execution_time_seconds,
            "tokens_used": self.tokens_used,
            "error_message": self.error_message,
            "effectiveness_score": self.effectiveness_score,
            "recorded_at": self.recorded_at.isoformat(),
            "metadata": self.metadata,
        }


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
        learning_db: Optional LearningDatabase for persisting effectiveness data.
    """

    def __init__(
        self,
        priority_engine: PriorityEngine | None = None,
        learning_db: LearningDatabase | None = None,
    ) -> None:
        """Initialize the TaskEffectivenessTracker.

        Args:
            priority_engine: Optional PriorityEngine instance for feedback.
                If not provided, feedback will be stored but not applied.
            learning_db: Optional LearningDatabase for persisting effectiveness
                data across runs. IMP-TASK-001: Enables effectiveness feedback
                to influence future task prioritization.
        """
        self.history = EffectivenessHistory()
        self.priority_engine = priority_engine
        self._learning_db = learning_db
        # IMP-LOOP-021: Track registered tasks for execution verification
        self._registered_tasks: dict[str, RegisteredTask] = {}

        # IMP-LOOP-022: Track failure counts and corrective tasks
        self._failure_counts: dict[str, int] = {}
        self._failure_errors: dict[str, list[str]] = {}
        self._corrective_tasks: list[CorrectiveTask] = []
        self._corrective_task_counter: int = 0

        # IMP-LOOP-028: Task attribution tracking for end-to-end traceability
        self._task_execution_mappings: dict[str, TaskExecutionMapping] = {}
        self._task_attribution_outcomes: list[TaskAttributionOutcome] = []

        # IMP-TASK-001: Load historical effectiveness from learning database
        if self._learning_db is not None:
            self._load_from_learning_db()

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

        IMP-TASK-003: Adjusts the priority engine's category weighting based on
        the measured effectiveness of completed tasks. Effective tasks boost
        their category's weight, while ineffective tasks reduce it.

        The adjustment is cumulative - the new multiplier is based on the
        current multiplier combined with the adjustment factor for this report.

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

        # IMP-TASK-003: Get current multiplier and apply adjustment
        current_multiplier = self.priority_engine.get_category_weight_multiplier(category)
        new_multiplier = current_multiplier * adjustment

        # Apply the updated multiplier to the priority engine
        self.priority_engine.update_category_weight_multiplier(category, new_multiplier)

        # Clear cache to force recalculation with new data
        self.priority_engine.clear_cache()

        logger.info(
            "[IMP-TASK-003] Fed back effectiveness for task %s to priority engine: "
            "category=%s, grade=%s, adjustment=%.2f, new_multiplier=%.2f",
            report.task_id,
            category,
            grade,
            adjustment,
            new_multiplier,
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

    def get_savings(self, task_id: str) -> float:
        """Get the computed savings achieved by a task.

        IMP-LOOP-031: Computes savings based on actual improvement achieved
        during task execution. This enables ROI feedback loop closure by
        providing actual savings data for comparison against estimates.

        Savings are computed as:
        - For successful tasks: actual_improvement * base_savings_estimate
        - For failed tasks: 0.0

        The base_savings_estimate is derived from the target improvement
        and effectiveness metrics.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            Computed savings value (tokens saved per phase), or 0.0 if task not found.
        """
        # Find the task's impact report
        for report in self.history.reports:
            if report.task_id == task_id:
                # Savings proportional to actual improvement achieved
                # Use a base estimate of 1000 tokens/phase as baseline
                base_savings = 1000.0
                actual_savings = base_savings * report.actual_improvement
                return max(0.0, actual_savings)

        logger.debug(
            "[IMP-LOOP-031] No impact report found for task %s, returning 0 savings",
            task_id,
        )
        return 0.0

    def get_task_cost_estimate(self, task_id: str) -> float:
        """Get the estimated cost for a task based on execution metrics.

        IMP-LOOP-031: Computes an estimated cost based on tokens used
        during task execution. This enables ROI feedback loop closure.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            Estimated cost (tokens), or 0.0 if task not found.
        """
        # Check attribution outcomes for token usage
        for outcome in self._task_attribution_outcomes:
            if outcome.task_id == task_id:
                return float(outcome.tokens_used)

        logger.debug(
            "[IMP-LOOP-031] No attribution outcome found for task %s, returning 0 cost",
            task_id,
        )
        return 0.0

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

    def analyze_effectiveness_patterns(self) -> List[EffectivenessLearningRule]:
        """Generate learning rules when task patterns cross thresholds.

        IMP-LOOP-017: Analyzes effectiveness data by category and creates
        learning rules when patterns show consistent success or failure.

        Rules are generated when:
        - Category has at least MIN_SAMPLE_SIZE observations
        - Success rate < LOW_SUCCESS_THRESHOLD → "avoid_pattern" rule
        - Success rate > HIGH_SUCCESS_THRESHOLD → "prefer_pattern" rule

        Returns:
            List of EffectivenessLearningRule objects for patterns crossing thresholds
        """
        rules: List[EffectivenessLearningRule] = []

        for category, stats in self.history.category_stats.items():
            total_tasks = stats.get("total_tasks", 0)

            # Require minimum sample size for statistical significance
            if total_tasks < MIN_SAMPLE_SIZE:
                continue

            # Calculate success rate from effective_count
            effective_count = stats.get("effective_count", 0)
            success_rate = effective_count / total_tasks

            # Generate avoid_pattern rule for low success rate
            if success_rate < LOW_SUCCESS_THRESHOLD:
                confidence = 1.0 - success_rate  # Higher confidence when success is lower
                rule = EffectivenessLearningRule(
                    rule_type="avoid_pattern",
                    pattern=category,
                    confidence=confidence,
                    reason=f"Low success rate: {success_rate:.2%} ({effective_count}/{total_tasks} effective)",
                    sample_size=total_tasks,
                    success_rate=success_rate,
                )
                rules.append(rule)
                logger.info(
                    "[IMP-LOOP-017] Generated avoid_pattern rule for '%s': "
                    "success_rate=%.2f%%, confidence=%.2f",
                    category,
                    success_rate * 100,
                    confidence,
                )

            # Generate prefer_pattern rule for high success rate
            elif success_rate > HIGH_SUCCESS_THRESHOLD:
                confidence = success_rate  # Confidence matches success rate
                rule = EffectivenessLearningRule(
                    rule_type="prefer_pattern",
                    pattern=category,
                    confidence=confidence,
                    reason=f"High success rate: {success_rate:.2%} ({effective_count}/{total_tasks} effective)",
                    sample_size=total_tasks,
                    success_rate=success_rate,
                )
                rules.append(rule)
                logger.info(
                    "[IMP-LOOP-017] Generated prefer_pattern rule for '%s': "
                    "success_rate=%.2f%%, confidence=%.2f",
                    category,
                    success_rate * 100,
                    confidence,
                )

        logger.info(
            "[IMP-LOOP-017] Analyzed effectiveness patterns: %d categories, %d rules generated",
            len(self.history.category_stats),
            len(rules),
        )

        return rules

    def register_task(
        self,
        task_id: str,
        priority: str = "",
        category: str = "",
    ) -> RegisteredTask:
        """Register a generated task for execution verification.

        IMP-LOOP-021: Records a generated improvement task for later verification
        that it was actually executed. This enables closed-loop tracking to ensure
        generated tasks don't get lost.

        Args:
            task_id: Unique identifier for the task (typically the IMP ID).
            priority: Priority level of the task (critical, high, medium, low).
            category: Category of the task for aggregation.

        Returns:
            RegisteredTask instance tracking the task.
        """
        if task_id in self._registered_tasks:
            logger.debug(
                "[IMP-LOOP-021] Task %s already registered, updating metadata",
                task_id,
            )
            existing = self._registered_tasks[task_id]
            # Update metadata if provided
            if priority:
                existing.priority = priority
            if category:
                existing.category = category
            return existing

        registered = RegisteredTask(
            task_id=task_id,
            priority=priority,
            category=category,
        )
        self._registered_tasks[task_id] = registered

        logger.info(
            "[IMP-LOOP-021] Registered task for execution verification: "
            "task_id=%s, priority=%s, category=%s",
            task_id,
            priority,
            category,
        )

        return registered

    def record_execution(
        self,
        task_id: str,
        success: bool,
    ) -> bool:
        """Record that a registered task was executed.

        IMP-LOOP-021: Marks a registered task as executed, completing the
        verification loop. This confirms the generated task was actually
        run and records its outcome.

        Args:
            task_id: The task ID to mark as executed.
            success: Whether the execution was successful.

        Returns:
            True if task was found and updated, False if task was not registered.
        """
        if task_id not in self._registered_tasks:
            logger.debug(
                "[IMP-LOOP-021] Task %s not registered, cannot record execution",
                task_id,
            )
            return False

        registered = self._registered_tasks[task_id]
        registered.executed = True
        registered.executed_at = datetime.now()
        registered.execution_success = success

        logger.info(
            "[IMP-LOOP-021] Recorded execution for task %s: success=%s",
            task_id,
            success,
        )

        return True

    def get_unexecuted_tasks(self) -> list[RegisteredTask]:
        """Get all registered tasks that have not been executed.

        IMP-LOOP-021: Returns tasks that were generated but never executed,
        indicating a gap in the feedback loop.

        Returns:
            List of RegisteredTask instances that have not been executed.
        """
        return [task for task in self._registered_tasks.values() if not task.executed]

    # IMP-LOOP-028: End-to-end task attribution methods

    def register_task_execution(self, task_id: str, phase_id: str) -> TaskExecutionMapping:
        """Link a generated task to its phase execution for attribution tracking.

        IMP-LOOP-028: Creates the mapping that enables end-to-end tracing from
        task generation through phase execution to outcome metrics. This is the
        critical link that closes the feedback loop.

        Args:
            task_id: The generated task identifier (e.g., IMP-LOOP-028).
            phase_id: The phase execution identifier where this task runs.

        Returns:
            TaskExecutionMapping instance representing the link.
        """
        # Check if mapping already exists
        if task_id in self._task_execution_mappings:
            existing = self._task_execution_mappings[task_id]
            logger.debug(
                "[IMP-LOOP-028] Task %s already mapped to phase %s, updating to %s",
                task_id,
                existing.phase_id,
                phase_id,
            )
            existing.phase_id = phase_id
            return existing

        mapping = TaskExecutionMapping(
            task_id=task_id,
            phase_id=phase_id,
        )
        self._task_execution_mappings[task_id] = mapping

        logger.info(
            "[IMP-LOOP-028] Registered task execution: task_id=%s -> phase_id=%s",
            task_id,
            phase_id,
        )

        return mapping

    def record_task_attribution_outcome(
        self,
        task_id: str,
        phase_id: str,
        success: bool,
        execution_time_seconds: float = 0.0,
        tokens_used: int = 0,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskAttributionOutcome:
        """Record the outcome of a task execution for attribution tracking.

        IMP-LOOP-028: Closes the attribution loop by recording the outcome
        metrics linked to a generated task. This enables measuring whether
        generated tasks achieve their intended improvements.

        Args:
            task_id: The generated task identifier.
            phase_id: The phase execution identifier.
            success: Whether the execution was successful.
            execution_time_seconds: Duration of execution.
            tokens_used: Number of tokens consumed.
            error_message: Error message if execution failed.
            metadata: Additional outcome metadata.

        Returns:
            TaskAttributionOutcome instance with computed effectiveness.
        """
        # Compute effectiveness score based on success and efficiency
        if success:
            base_effectiveness = 0.8
            efficiency_bonus = 0.0

            # Fast execution bonus (< 60 seconds)
            if execution_time_seconds > 0 and execution_time_seconds < 60:
                efficiency_bonus += 0.1

            # Low token usage bonus (< 10000 tokens)
            if tokens_used > 0 and tokens_used < 10000:
                efficiency_bonus += 0.1

            effectiveness_score = min(1.0, base_effectiveness + efficiency_bonus)
        else:
            effectiveness_score = 0.0

        outcome = TaskAttributionOutcome(
            task_id=task_id,
            phase_id=phase_id,
            success=success,
            execution_time_seconds=execution_time_seconds,
            tokens_used=tokens_used,
            error_message=error_message,
            effectiveness_score=effectiveness_score,
            metadata=metadata or {},
        )

        self._task_attribution_outcomes.append(outcome)

        # Update the mapping if it exists
        if task_id in self._task_execution_mappings:
            mapping = self._task_execution_mappings[task_id]
            mapping.outcome_recorded = True
            mapping.outcome_recorded_at = datetime.now()

        logger.info(
            "[IMP-LOOP-028] Recorded task attribution outcome: "
            "task_id=%s, phase_id=%s, success=%s, effectiveness=%.2f",
            task_id,
            phase_id,
            success,
            effectiveness_score,
        )

        # Also record to the standard outcome tracking for corrective task generation
        self.record_outcome(
            task_id=task_id,
            success=success,
            error=error_message,
            category=metadata.get("category", "") if metadata else "",
        )

        return outcome

    def get_task_execution_mapping(self, task_id: str) -> TaskExecutionMapping | None:
        """Get the execution mapping for a task.

        IMP-LOOP-028: Retrieves the task-to-phase mapping for a given task.

        Args:
            task_id: The generated task identifier.

        Returns:
            TaskExecutionMapping if found, None otherwise.
        """
        return self._task_execution_mappings.get(task_id)

    def get_attribution_outcomes_for_task(self, task_id: str) -> list[TaskAttributionOutcome]:
        """Get all attribution outcomes for a specific task.

        IMP-LOOP-028: Retrieves outcome history for a generated task,
        useful for analyzing task effectiveness over multiple executions.

        Args:
            task_id: The generated task identifier.

        Returns:
            List of TaskAttributionOutcome instances for the task.
        """
        return [o for o in self._task_attribution_outcomes if o.task_id == task_id]

    def get_attribution_outcomes_for_phase(self, phase_id: str) -> list[TaskAttributionOutcome]:
        """Get all attribution outcomes for a specific phase.

        IMP-LOOP-028: Retrieves outcomes linked to a phase execution,
        useful for analyzing what generated tasks contributed to a phase.

        Args:
            phase_id: The phase execution identifier.

        Returns:
            List of TaskAttributionOutcome instances for the phase.
        """
        return [o for o in self._task_attribution_outcomes if o.phase_id == phase_id]

    def get_task_attribution_summary(self) -> dict[str, Any]:
        """Get a summary of task attribution tracking status.

        IMP-LOOP-028: Provides visibility into the end-to-end attribution
        pipeline, showing how many tasks are mapped, how many outcomes
        recorded, and the overall success rate.

        Returns:
            Dictionary containing:
            - total_mappings: Number of task-to-phase mappings
            - mappings_with_outcomes: Mappings that have recorded outcomes
            - total_outcomes: Total number of outcome records
            - successful_outcomes: Number of successful outcomes
            - success_rate: Overall success rate of attributed tasks
            - avg_effectiveness: Average effectiveness score
            - unmapped_tasks: List of task IDs without mappings
        """
        mappings = list(self._task_execution_mappings.values())
        mappings_with_outcomes = [m for m in mappings if m.outcome_recorded]
        outcomes = self._task_attribution_outcomes

        successful = [o for o in outcomes if o.success]
        total_effectiveness = sum(o.effectiveness_score for o in outcomes)

        # Find tasks that were registered but never mapped
        registered_task_ids = set(self._registered_tasks.keys())
        mapped_task_ids = set(self._task_execution_mappings.keys())
        unmapped_tasks = list(registered_task_ids - mapped_task_ids)

        return {
            "total_mappings": len(mappings),
            "mappings_with_outcomes": len(mappings_with_outcomes),
            "total_outcomes": len(outcomes),
            "successful_outcomes": len(successful),
            "success_rate": len(successful) / len(outcomes) if outcomes else 0.0,
            "avg_effectiveness": total_effectiveness / len(outcomes) if outcomes else 0.0,
            "unmapped_tasks": unmapped_tasks,
        }

    # IMP-LOOP-022: Corrective task generation methods

    def record_outcome(
        self,
        task_id: str,
        success: bool,
        error: str | None = None,
        category: str = "",
    ) -> None:
        """Record task outcome and trigger corrective task if threshold reached.

        IMP-LOOP-022: Records the outcome of a task execution and tracks failures.
        When a task fails repeatedly (3+ times), automatically generates a
        corrective task to investigate and fix the root cause.

        Args:
            task_id: Unique identifier for the task.
            success: Whether the task completed successfully.
            error: Optional error message if the task failed.
            category: Optional category of the task.
        """
        if not success:
            # Increment failure count
            self._failure_counts[task_id] = self._failure_counts.get(task_id, 0) + 1
            failure_count = self._failure_counts[task_id]

            # Track error patterns
            if error:
                if task_id not in self._failure_errors:
                    self._failure_errors[task_id] = []
                self._failure_errors[task_id].append(error)

            logger.info(
                "[IMP-LOOP-022] Recorded failure for task %s: count=%d, error=%s",
                task_id,
                failure_count,
                error[:100] if error else "None",
            )

            # Check if threshold reached for corrective task generation
            if failure_count >= CORRECTIVE_TASK_FAILURE_THRESHOLD:
                # Only generate corrective task once per threshold crossing
                if failure_count == CORRECTIVE_TASK_FAILURE_THRESHOLD:
                    self._generate_corrective_task(task_id, category)
        else:
            # Reset failure count on success
            if task_id in self._failure_counts:
                logger.debug(
                    "[IMP-LOOP-022] Task %s succeeded, resetting failure count from %d",
                    task_id,
                    self._failure_counts[task_id],
                )
                self._failure_counts[task_id] = 0

    def _find_common_error_pattern(self, errors: list[str]) -> str:
        """Find common pattern across error messages.

        IMP-LOOP-022: Analyzes error messages to find common patterns that
        might indicate the root cause of repeated failures.

        Args:
            errors: List of error messages to analyze.

        Returns:
            Common error pattern or a summary of the errors.
        """
        if not errors:
            return "Unknown error pattern"

        # Simple pattern detection: find common substrings
        if len(errors) == 1:
            return errors[0][:200] if len(errors[0]) > 200 else errors[0]

        # Find common words across all errors
        word_sets = [set(err.lower().split()) for err in errors]
        common_words = word_sets[0]
        for ws in word_sets[1:]:
            common_words = common_words.intersection(ws)

        # Remove common stop words
        stop_words = {"the", "a", "an", "in", "on", "at", "to", "for", "is", "was", "error"}
        common_words = common_words - stop_words

        if common_words:
            return f"Common pattern: {', '.join(sorted(common_words)[:10])}"

        # Fall back to first error summary
        return errors[0][:200] if len(errors[0]) > 200 else errors[0]

    def _generate_corrective_task(self, task_id: str, category: str = "") -> CorrectiveTask:
        """Generate a corrective task after repeated failures.

        IMP-LOOP-022: Creates a corrective task to investigate and fix the
        root cause of repeated task failures. The corrective task includes
        information about the failure patterns to aid investigation.

        Args:
            task_id: The original task ID that failed repeatedly.
            category: Category of the original task.

        Returns:
            CorrectiveTask instance representing the generated task.
        """
        self._corrective_task_counter += 1
        corrective_id = f"CORR-{self._corrective_task_counter:03d}"

        failure_count = self._failure_counts.get(task_id, CORRECTIVE_TASK_FAILURE_THRESHOLD)
        errors = self._failure_errors.get(task_id, [])
        error_pattern = self._find_common_error_pattern(errors)

        corrective_task = CorrectiveTask(
            corrective_id=corrective_id,
            original_task_id=task_id,
            failure_count=failure_count,
            error_patterns=[error_pattern] if error_pattern else [],
            priority="high",
            category=category,
        )

        self._corrective_tasks.append(corrective_task)

        logger.info(
            "[IMP-LOOP-022] Generated corrective task %s for %s: "
            "failure_count=%d, error_pattern=%s",
            corrective_id,
            task_id,
            failure_count,
            error_pattern[:50] if error_pattern else "None",
        )

        return corrective_task

    def get_corrective_tasks(self) -> list[CorrectiveTask]:
        """Get all generated corrective tasks.

        IMP-LOOP-022: Returns the list of corrective tasks that have been
        generated due to repeated failures.

        Returns:
            List of CorrectiveTask instances.
        """
        return list(self._corrective_tasks)

    def get_failure_count(self, task_id: str) -> int:
        """Get the current failure count for a task.

        IMP-LOOP-022: Returns how many times a task has failed consecutively.

        Args:
            task_id: The task ID to check.

        Returns:
            Number of consecutive failures, or 0 if no failures recorded.
        """
        return self._failure_counts.get(task_id, 0)

    def get_corrective_task_summary(self) -> dict[str, Any]:
        """Get a summary of corrective task generation status.

        IMP-LOOP-022: Provides visibility into the corrective task pipeline,
        showing tasks at risk of triggering corrective action and tasks
        that have already triggered corrective tasks.

        Returns:
            Dictionary containing:
            - total_corrective_tasks: Number of corrective tasks generated
            - tasks_at_risk: Tasks with failures but below threshold
            - tasks_exceeded_threshold: Tasks that triggered corrective tasks
            - corrective_tasks: List of corrective task summaries
        """
        tasks_at_risk = [
            {"task_id": tid, "failure_count": count}
            for tid, count in self._failure_counts.items()
            if 0 < count < CORRECTIVE_TASK_FAILURE_THRESHOLD
        ]

        tasks_exceeded = [
            {"task_id": tid, "failure_count": count}
            for tid, count in self._failure_counts.items()
            if count >= CORRECTIVE_TASK_FAILURE_THRESHOLD
        ]

        return {
            "total_corrective_tasks": len(self._corrective_tasks),
            "failure_threshold": CORRECTIVE_TASK_FAILURE_THRESHOLD,
            "tasks_at_risk": tasks_at_risk,
            "tasks_exceeded_threshold": tasks_exceeded,
            "corrective_tasks": [ct.to_dict() for ct in self._corrective_tasks],
        }

    def get_execution_verification_summary(self) -> dict[str, Any]:
        """Get a summary of task execution verification status.

        IMP-LOOP-021: Provides visibility into the task verification pipeline,
        showing how many generated tasks were actually executed.

        Returns:
            Dictionary containing:
            - total_registered: Total number of registered tasks
            - executed_count: Number of tasks that were executed
            - unexecuted_count: Number of tasks not yet executed
            - execution_rate: Percentage of registered tasks that were executed
            - success_rate: Percentage of executed tasks that succeeded
            - by_priority: Breakdown by priority level
            - unexecuted_tasks: List of task IDs not yet executed
        """
        total = len(self._registered_tasks)
        executed = [t for t in self._registered_tasks.values() if t.executed]
        unexecuted = [t for t in self._registered_tasks.values() if not t.executed]
        successful = [t for t in executed if t.execution_success]

        # Breakdown by priority
        by_priority: dict[str, dict[str, int]] = {}
        for task in self._registered_tasks.values():
            priority = task.priority or "unknown"
            if priority not in by_priority:
                by_priority[priority] = {"registered": 0, "executed": 0, "successful": 0}
            by_priority[priority]["registered"] += 1
            if task.executed:
                by_priority[priority]["executed"] += 1
                if task.execution_success:
                    by_priority[priority]["successful"] += 1

        return {
            "total_registered": total,
            "executed_count": len(executed),
            "unexecuted_count": len(unexecuted),
            "execution_rate": len(executed) / total if total > 0 else 0.0,
            "success_rate": len(successful) / len(executed) if executed else 0.0,
            "by_priority": by_priority,
            "unexecuted_tasks": [t.task_id for t in unexecuted],
        }

    # IMP-LOOP-021: Real-time feedback callback methods

    def on_task_complete(
        self,
        task_id: str,
        success: bool,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Callback for real-time task completion feedback to PriorityEngine.

        IMP-LOOP-021: This method bridges TaskEffectivenessTracker to PriorityEngine,
        enabling session-local learning. When a task completes, this callback
        notifies the priority engine to update its session penalties.

        This creates a real-time feedback loop where:
        - Task failures immediately decrease priority for similar tasks
        - The priority engine can adjust its scoring during the current run
        - Historical learning (via feed_back_to_priority_engine) handles long-term

        Args:
            task_id: The task identifier (e.g., improvement ID).
            success: Whether the task completed successfully.
            metrics: Optional dict with additional context. Expected keys:
                - failure_count: Number of failures for this task
                - error_type: Type of error encountered
                - execution_time: Time taken to execute
                - tokens_used: Tokens consumed
        """
        if metrics is None:
            metrics = {}

        # Get category from registered task if available
        category = ""
        if task_id in self._registered_tasks:
            category = self._registered_tasks[task_id].category

        # Include category in metrics for priority engine
        if category and "category" not in metrics:
            metrics["category"] = category

        # Forward to priority engine if connected
        if self.priority_engine is not None:
            self.priority_engine.update_from_effectiveness(
                task_id=task_id,
                success=success,
                metrics=metrics,
            )
            logger.info(
                "[IMP-LOOP-021] Sent real-time feedback to priority engine: "
                "task_id=%s, success=%s, category=%s",
                task_id,
                success,
                category,
            )
        else:
            logger.debug("[IMP-LOOP-021] No priority engine connected, skipping real-time feedback")

        # Also record execution status for verification tracking
        self.record_execution(task_id, success)

    def notify_task_outcome(
        self,
        task_id: str,
        success: bool,
        execution_time_seconds: float = 0.0,
        tokens_used: int = 0,
        failure_count: int = 1,
        error_type: str = "",
        category: str = "",
    ) -> TaskImpactReport:
        """Combined method for recording outcome and sending real-time feedback.

        IMP-LOOP-021: Convenience method that combines record_task_outcome with
        on_task_complete, ensuring both historical tracking and real-time
        priority adjustment happen together.

        Args:
            task_id: Unique identifier for the task/phase.
            success: Whether the task completed successfully.
            execution_time_seconds: Time taken to execute the task.
            tokens_used: Number of tokens consumed during execution.
            failure_count: Number of failures for this task (for repeated failures).
            error_type: Type of error encountered (for pattern detection).
            category: Category for aggregation (e.g., "build", "test").

        Returns:
            TaskImpactReport with calculated effectiveness metrics.
        """
        # Record the outcome for historical tracking
        report = self.record_task_outcome(
            task_id=task_id,
            success=success,
            execution_time_seconds=execution_time_seconds,
            tokens_used=tokens_used,
            category=category,
        )

        # Send real-time feedback to priority engine
        self.on_task_complete(
            task_id=task_id,
            success=success,
            metrics={
                "failure_count": failure_count,
                "error_type": error_type,
                "category": category,
                "execution_time": execution_time_seconds,
                "tokens_used": tokens_used,
            },
        )

        return report

    # IMP-TASK-001: Persistence methods for effectiveness feedback loop

    def set_learning_db(self, learning_db: LearningDatabase) -> None:
        """Set or update the learning database for persistence.

        IMP-TASK-001: Allows connecting the effectiveness tracker to a learning
        database after initialization.

        Args:
            learning_db: LearningDatabase instance for persistence.
        """
        self._learning_db = learning_db
        logger.debug("[IMP-TASK-001] Connected effectiveness tracker to learning database")

    def persist_effectiveness_report(self, report: TaskImpactReport) -> bool:
        """Persist an effectiveness report to the learning database.

        IMP-TASK-001: Stores effectiveness data to influence future task
        prioritization. Maps effectiveness scores to improvement outcomes.

        Args:
            report: TaskImpactReport to persist.

        Returns:
            True if persistence was successful, False otherwise.
        """
        if self._learning_db is None:
            logger.debug("[IMP-TASK-001] No learning database configured, skipping persistence")
            return False

        # Map effectiveness score to outcome
        grade = report.get_effectiveness_grade()
        if grade == "excellent":
            outcome = "implemented"
        elif grade == "good":
            outcome = "implemented"
        elif grade == "moderate":
            outcome = "partial"
        else:
            outcome = "blocked"

        # Create notes with effectiveness details
        notes = (
            f"effectiveness={report.effectiveness_score:.2f}, "
            f"actual_improvement={report.actual_improvement:.2%}, "
            f"target={report.target_improvement:.2%}"
        )

        # Record to learning database
        success = self._learning_db.record_improvement_outcome(
            imp_id=report.task_id,
            outcome=outcome,
            notes=notes,
            category=report.category or "general",
            priority=None,  # Priority not tracked in report
        )

        if success:
            logger.info(
                "[IMP-TASK-001] Persisted effectiveness report for %s: "
                "category=%s, grade=%s, outcome=%s",
                report.task_id,
                report.category,
                grade,
                outcome,
            )
        else:
            logger.warning(
                "[IMP-TASK-001] Failed to persist effectiveness report for %s",
                report.task_id,
            )

        return success

    def persist_all_reports(self) -> int:
        """Persist all effectiveness reports to the learning database.

        IMP-TASK-001: Batch persistence of all tracked effectiveness reports.
        Useful at the end of a run to ensure all data is saved.

        Returns:
            Number of reports successfully persisted.
        """
        if self._learning_db is None:
            logger.debug(
                "[IMP-TASK-001] No learning database configured, skipping batch persistence"
            )
            return 0

        persisted_count = 0
        for report in self.history.reports:
            if self.persist_effectiveness_report(report):
                persisted_count += 1

        logger.info(
            "[IMP-TASK-001] Batch persisted %d of %d effectiveness reports",
            persisted_count,
            len(self.history.reports),
        )

        return persisted_count

    def _load_from_learning_db(self) -> None:
        """Load historical effectiveness data from the learning database.

        IMP-TASK-001: Initializes category stats from persisted historical data,
        enabling effectiveness-based prioritization from the start of a run.
        """
        if self._learning_db is None:
            return

        try:
            patterns = self._learning_db.get_historical_patterns()
            category_rates = patterns.get("category_success_rates", {})

            for category, stats in category_rates.items():
                total = stats.get("total", 0)
                implemented = stats.get("implemented", 0)

                if total > 0:
                    # Create synthetic stats for the category
                    success_rate = implemented / total

                    # Initialize category stats if not present
                    if category not in self.history.category_stats:
                        self.history.category_stats[category] = {
                            "total_tasks": total,
                            "total_effectiveness": success_rate * total,
                            "avg_effectiveness": success_rate,
                            "effective_count": implemented,
                        }
                        logger.debug(
                            "[IMP-TASK-001] Loaded historical effectiveness for %s: "
                            "success_rate=%.2f%% (%d/%d)",
                            category,
                            success_rate * 100,
                            implemented,
                            total,
                        )

            logger.info(
                "[IMP-TASK-001] Loaded historical effectiveness for %d categories",
                len(category_rates),
            )

        except Exception as e:
            logger.warning(
                "[IMP-TASK-001] Failed to load historical effectiveness: %s",
                e,
            )

    def get_category_effectiveness_with_history(
        self,
        category: str,
        default: float = 0.5,
    ) -> float:
        """Get category effectiveness combining current and historical data.

        IMP-TASK-001: Enhanced method that combines in-memory effectiveness
        data with historical data from the learning database.

        Args:
            category: Category to query.
            default: Default value if no data available. Use -1.0 as sentinel
                to distinguish "no data" from "0% effectiveness".

        Returns:
            Effectiveness score between 0.0 and 1.0, or default if no data.
        """
        # First check in-memory history
        if category in self.history.category_stats:
            stats = self.history.category_stats[category]
            if stats.get("total_tasks", 0) > 0:
                # Return actual avg_effectiveness even if it's 0.0
                return stats["avg_effectiveness"]

        # Fall back to learning database
        if self._learning_db is not None:
            historical_rate = self._learning_db.get_success_rate(category)
            # Note: get_success_rate returns 0.0 for unknown categories,
            # but also for categories with 0% success. Check if category exists.
            patterns = self._learning_db.get_historical_patterns()
            category_rates = patterns.get("category_success_rates", {})
            if category in category_rates:
                logger.debug(
                    "[IMP-TASK-001] Using historical effectiveness for %s: %.2f%%",
                    category,
                    historical_rate * 100,
                )
                return historical_rate

        return default
