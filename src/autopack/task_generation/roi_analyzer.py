"""ROI and payback analysis for task prioritization.

Calculates the return on investment for generated tasks,
including payback period and lifetime value. This enables
data-driven task prioritization based on expected returns.

IMP-TASK-003: Adds ROI prediction validation and effectiveness learning
to improve prediction accuracy over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autopack.task_generation.task_effectiveness_tracker import \
        TaskEffectivenessTracker

logger = logging.getLogger(__name__)

# Default assumptions for ROI calculations
DEFAULT_EFFECTIVENESS = 0.5  # Assumed effectiveness when no historical data
DEFAULT_PHASES_HORIZON = 100  # Number of phases to consider for lifetime value
MIN_SAVINGS_PER_PHASE = 0.001  # Minimum savings to prevent division by zero

# ROI classification thresholds
EXCELLENT_ROI = 5.0  # 500%+ return
GOOD_ROI = 2.0  # 200%+ return
MODERATE_ROI = 1.0  # 100%+ return (break-even)
POOR_ROI = 0.5  # Less than break-even

# IMP-TASK-003: Configuration for learned effectiveness
MIN_SAMPLES_FOR_LEARNING = 3  # Minimum samples before using learned effectiveness
EFFECTIVENESS_LEARNING_RATE = 0.2  # How quickly to adapt to new data (0-1)


@dataclass
class PaybackAnalysis:
    """Analysis of task ROI and payback period.

    This dataclass captures the calculated ROI metrics for a task,
    including execution cost, expected savings, payback period,
    and risk-adjusted return on investment.

    Attributes:
        task_id: Unique identifier for the improvement task.
        execution_cost_tokens: Estimated token cost to execute the task.
        estimated_savings_per_phase: Expected token savings per execution phase.
        payback_phases: Number of phases until savings exceed execution cost.
        lifetime_value_tokens: Total expected value over the analysis horizon.
        risk_adjusted_roi: ROI adjusted for confidence/uncertainty.
        confidence: Confidence level used for risk adjustment (0.0-1.0).
        category: Category of the task for grouping analysis.
    """

    task_id: str
    execution_cost_tokens: float
    estimated_savings_per_phase: float
    payback_phases: int
    lifetime_value_tokens: float
    risk_adjusted_roi: float
    confidence: float = 0.8
    category: str = ""

    def get_roi_grade(self) -> str:
        """Return a human-readable ROI grade.

        Returns:
            One of: "excellent", "good", "moderate", "poor"
        """
        if self.risk_adjusted_roi >= EXCELLENT_ROI:
            return "excellent"
        elif self.risk_adjusted_roi >= GOOD_ROI:
            return "good"
        elif self.risk_adjusted_roi >= MODERATE_ROI:
            return "moderate"
        else:
            return "poor"

    def is_profitable(self) -> bool:
        """Check if task has positive lifetime value.

        Returns:
            True if lifetime value is positive, False otherwise.
        """
        return self.lifetime_value_tokens > 0

    def has_quick_payback(self, threshold_phases: int = 10) -> bool:
        """Check if task pays back within threshold phases.

        Args:
            threshold_phases: Maximum phases for quick payback.

        Returns:
            True if payback_phases is within threshold.
        """
        return self.payback_phases <= threshold_phases


@dataclass
class ROIPredictionRecord:
    """Record of an ROI prediction vs actual outcome.

    IMP-TASK-003: Tracks prediction accuracy to enable learning and
    calibration of the effectiveness model over time.

    Attributes:
        task_id: Unique identifier for the task.
        predicted_roi: ROI that was predicted at task creation.
        actual_roi: Actual ROI measured after task completion.
        predicted_effectiveness: Effectiveness used in prediction.
        actual_effectiveness: Actual effectiveness observed.
        error: Absolute error between predicted and actual ROI.
        category: Category of the task for grouping analysis.
        recorded_at: Timestamp when the record was created.
    """

    task_id: str
    predicted_roi: float
    actual_roi: float
    predicted_effectiveness: float
    actual_effectiveness: float
    error: float
    category: str = ""
    recorded_at: datetime = field(default_factory=datetime.now)

    def get_accuracy_grade(self) -> str:
        """Return a human-readable accuracy grade based on prediction error.

        Returns:
            One of: "excellent", "good", "moderate", "poor"
        """
        relative_error = self.error / max(abs(self.predicted_roi), 0.01)
        if relative_error <= 0.1:
            return "excellent"
        elif relative_error <= 0.25:
            return "good"
        elif relative_error <= 0.5:
            return "moderate"
        else:
            return "poor"


@dataclass
class ROIHistory:
    """Maintains a history of ROI analyses for tracking.

    Attributes:
        analyses: List of PaybackAnalysis instances.
        category_stats: Aggregated ROI statistics by category.
    """

    analyses: list[PaybackAnalysis] = field(default_factory=list)
    category_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def add_analysis(self, analysis: PaybackAnalysis) -> None:
        """Add an analysis and update category statistics."""
        self.analyses.append(analysis)
        self._update_category_stats(analysis)

    def _update_category_stats(self, analysis: PaybackAnalysis) -> None:
        """Update aggregated statistics for the analysis category."""
        category = analysis.category or "general"

        if category not in self.category_stats:
            self.category_stats[category] = {
                "total_analyses": 0,
                "total_roi": 0.0,
                "avg_roi": 0.0,
                "avg_payback_phases": 0.0,
                "profitable_count": 0,
            }

        stats = self.category_stats[category]
        stats["total_analyses"] += 1
        stats["total_roi"] += analysis.risk_adjusted_roi

        # Calculate running averages
        total = stats["total_analyses"]
        stats["avg_roi"] = stats["total_roi"] / total

        # Update average payback (weighted)
        old_avg = stats["avg_payback_phases"]
        stats["avg_payback_phases"] = old_avg + (analysis.payback_phases - old_avg) / total

        if analysis.is_profitable():
            stats["profitable_count"] += 1

    def get_category_avg_roi(self, category: str) -> float:
        """Get average ROI for a category.

        Args:
            category: Category to query.

        Returns:
            Average ROI, or 1.0 if no data (neutral expectation).
        """
        stats = self.category_stats.get(category)
        if stats and stats["total_analyses"] > 0:
            return stats["avg_roi"]
        return 1.0  # Default neutral ROI


class ROIAnalyzer:
    """Analyzes return on investment for improvement tasks.

    This class calculates ROI metrics for generated tasks using
    historical effectiveness data from TaskEffectivenessTracker.
    It enables prioritization of tasks based on expected returns.

    IMP-TASK-003: Enhanced with ROI prediction validation and
    effectiveness learning from historical outcomes.

    Attributes:
        effectiveness_tracker: TaskEffectivenessTracker for historical data.
        history: ROIHistory containing all calculated analyses.
        phases_horizon: Number of phases to consider for lifetime value.
        _roi_predictions: List of ROI prediction records for validation.
        _category_effectiveness: Learned effectiveness by category.
        _prediction_accuracy: Tracked accuracy metrics by category.
    """

    def __init__(
        self,
        effectiveness_tracker: TaskEffectivenessTracker | None = None,
        phases_horizon: int = DEFAULT_PHASES_HORIZON,
    ) -> None:
        """Initialize the ROIAnalyzer.

        Args:
            effectiveness_tracker: Optional TaskEffectivenessTracker instance.
                If not provided, uses default effectiveness assumptions.
            phases_horizon: Number of phases to consider for lifetime value.
        """
        self.effectiveness_tracker = effectiveness_tracker
        self.history = ROIHistory()
        self.phases_horizon = phases_horizon

        # IMP-TASK-003: ROI prediction validation tracking
        self._roi_predictions: list[ROIPredictionRecord] = []
        self._category_effectiveness: dict[str, dict[str, float]] = {}
        self._pending_predictions: dict[str, dict[str, Any]] = {}

    def calculate_payback_period(
        self,
        task_id: str,
        estimated_token_reduction: float,
        execution_cost: float,
        confidence: float = 0.8,
        category: str = "",
    ) -> PaybackAnalysis:
        """Calculate when task savings exceed execution cost.

        Computes the payback period, lifetime value, and risk-adjusted
        ROI for a task based on estimated token reduction and execution
        cost. Uses historical effectiveness data when available.

        Args:
            task_id: Unique identifier for the task.
            estimated_token_reduction: Expected token savings per phase
                before effectiveness adjustment.
            execution_cost: Token cost to execute the task.
            confidence: Confidence level for risk adjustment (0.0-1.0).
            category: Optional category for the task.

        Returns:
            PaybackAnalysis with calculated ROI metrics.

        Raises:
            ValueError: If execution_cost is not positive, or if
                confidence is not in valid range.
        """
        if execution_cost <= 0:
            raise ValueError("Execution cost must be positive")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")

        # Get effectiveness from tracker or use default
        effectiveness = self._get_task_effectiveness(task_id, category)

        # Calculate savings per phase adjusted by effectiveness
        savings_per_phase = estimated_token_reduction * effectiveness
        savings_per_phase = max(savings_per_phase, MIN_SAVINGS_PER_PHASE)

        # Calculate payback period (phases until break-even)
        payback_phases = int(execution_cost / savings_per_phase) + 1

        # Calculate lifetime value over the analysis horizon
        lifetime_value = (savings_per_phase * self.phases_horizon) - execution_cost

        # Calculate risk-adjusted ROI
        if execution_cost > 0:
            raw_roi = lifetime_value / execution_cost
            risk_adjusted_roi = raw_roi * confidence
        else:
            risk_adjusted_roi = 0.0

        analysis = PaybackAnalysis(
            task_id=task_id,
            execution_cost_tokens=execution_cost,
            estimated_savings_per_phase=savings_per_phase,
            payback_phases=payback_phases,
            lifetime_value_tokens=lifetime_value,
            risk_adjusted_roi=risk_adjusted_roi,
            confidence=confidence,
            category=category,
        )

        # Store in history
        self.history.add_analysis(analysis)

        # IMP-TASK-003: Record prediction for later validation
        self.record_prediction(
            task_id=task_id,
            predicted_roi=risk_adjusted_roi,
            predicted_effectiveness=effectiveness,
            category=category,
        )

        logger.info(
            "Calculated ROI for task %s: roi=%.2f (%s), payback=%d phases, "
            "lifetime_value=%.0f tokens",
            task_id,
            risk_adjusted_roi,
            analysis.get_roi_grade(),
            payback_phases,
            lifetime_value,
        )

        return analysis

    def _get_task_effectiveness(self, task_id: str, category: str) -> float:
        """Get effectiveness for a task, with fallbacks.

        IMP-TASK-003: Enhanced to use learned effectiveness from ROI validation
        before falling back to tracker and default values.

        Tries (in order):
        1. Learned effectiveness from ROI validation history
        2. Task-specific effectiveness from tracker
        3. Category effectiveness from tracker
        4. Default effectiveness

        Args:
            task_id: Task ID to look up.
            category: Category for fallback lookup.

        Returns:
            Effectiveness score (0.0-1.0).
        """
        # IMP-TASK-003: Try learned effectiveness first
        learned = self._get_learned_effectiveness(category)
        if learned is not None:
            logger.debug(
                "[IMP-TASK-003] Using learned effectiveness for category '%s': %.3f",
                category,
                learned,
            )
            return learned

        if self.effectiveness_tracker is None:
            return DEFAULT_EFFECTIVENESS

        # Try task-specific effectiveness first
        effectiveness = self.effectiveness_tracker.get_effectiveness(task_id)

        # If default was returned (0.5), try category effectiveness
        if effectiveness == DEFAULT_EFFECTIVENESS and category:
            category_effectiveness = self.effectiveness_tracker.get_category_effectiveness(category)
            if category_effectiveness != DEFAULT_EFFECTIVENESS:
                effectiveness = category_effectiveness

        return effectiveness

    def _get_learned_effectiveness(self, category: str) -> float | None:
        """Get learned effectiveness for a category from ROI validation history.

        IMP-TASK-003: Returns learned effectiveness if sufficient data exists,
        otherwise returns None to signal fallback to other sources.

        Args:
            category: Category to look up.

        Returns:
            Learned effectiveness (0.0-1.0) if sufficient data, None otherwise.
        """
        cat_key = category or "general"

        if cat_key not in self._category_effectiveness:
            return None

        stats = self._category_effectiveness[cat_key]
        sample_count = stats.get("sample_count", 0)

        if sample_count < MIN_SAMPLES_FOR_LEARNING:
            return None

        return stats.get("learned_effectiveness")

    def validate_roi_prediction(
        self,
        task_id: str,
        actual_roi: float,
        actual_effectiveness: float,
    ) -> ROIPredictionRecord | None:
        """Validate a predicted ROI against actual outcome.

        IMP-TASK-003: Compares predicted ROI with actual ROI after task
        completion, records the prediction accuracy, and updates the
        effectiveness model for future predictions.

        Args:
            task_id: The task ID to validate (must have pending prediction).
            actual_roi: The actual ROI measured after task completion.
            actual_effectiveness: Actual effectiveness observed (0.0-1.0).

        Returns:
            ROIPredictionRecord with validation results, or None if task not found.
        """
        if task_id not in self._pending_predictions:
            logger.debug(
                "[IMP-TASK-003] No pending prediction found for task %s",
                task_id,
            )
            return None

        prediction = self._pending_predictions.pop(task_id)
        predicted_roi = prediction["predicted_roi"]
        predicted_effectiveness = prediction["predicted_effectiveness"]
        category = prediction["category"]

        error = abs(predicted_roi - actual_roi)

        record = ROIPredictionRecord(
            task_id=task_id,
            predicted_roi=predicted_roi,
            actual_roi=actual_roi,
            predicted_effectiveness=predicted_effectiveness,
            actual_effectiveness=actual_effectiveness,
            error=error,
            category=category,
        )

        self._roi_predictions.append(record)

        # Update effectiveness model with new data
        self._update_effectiveness_model(category, actual_effectiveness)

        logger.info(
            "[IMP-TASK-003] Validated ROI prediction for task %s: "
            "predicted=%.2f, actual=%.2f, error=%.2f (%s), "
            "effectiveness: predicted=%.2f, actual=%.2f",
            task_id,
            predicted_roi,
            actual_roi,
            error,
            record.get_accuracy_grade(),
            predicted_effectiveness,
            actual_effectiveness,
        )

        return record

    def _update_effectiveness_model(self, category: str, actual_effectiveness: float) -> None:
        """Update learned effectiveness for a category based on new outcome.

        IMP-TASK-003: Uses exponential moving average to update the learned
        effectiveness, balancing historical data with new observations.

        Args:
            category: Category to update.
            actual_effectiveness: Newly observed effectiveness (0.0-1.0).
        """
        cat_key = category or "general"

        if cat_key not in self._category_effectiveness:
            self._category_effectiveness[cat_key] = {
                "learned_effectiveness": actual_effectiveness,
                "sample_count": 1,
                "total_effectiveness": actual_effectiveness,
                "prediction_errors": [],
            }
            logger.debug(
                "[IMP-TASK-003] Initialized effectiveness model for '%s': %.3f",
                cat_key,
                actual_effectiveness,
            )
            return

        stats = self._category_effectiveness[cat_key]
        old_effectiveness = stats["learned_effectiveness"]
        sample_count = stats["sample_count"]

        # Use exponential moving average for smooth learning
        # More weight on new data when we have fewer samples
        alpha = max(EFFECTIVENESS_LEARNING_RATE, 1.0 / (sample_count + 1))
        new_effectiveness = old_effectiveness * (1 - alpha) + actual_effectiveness * alpha

        stats["learned_effectiveness"] = new_effectiveness
        stats["sample_count"] = sample_count + 1
        stats["total_effectiveness"] = stats.get("total_effectiveness", 0) + actual_effectiveness

        logger.debug(
            "[IMP-TASK-003] Updated effectiveness model for '%s': "
            "%.3f -> %.3f (sample %d, alpha=%.3f)",
            cat_key,
            old_effectiveness,
            new_effectiveness,
            stats["sample_count"],
            alpha,
        )

    def record_prediction(
        self,
        task_id: str,
        predicted_roi: float,
        predicted_effectiveness: float,
        category: str = "",
    ) -> None:
        """Record a prediction for later validation.

        IMP-TASK-003: Stores prediction details so they can be validated
        against actual outcomes when the task completes.

        Args:
            task_id: Unique identifier for the task.
            predicted_roi: The ROI prediction being made.
            predicted_effectiveness: Effectiveness used in the prediction.
            category: Category of the task.
        """
        self._pending_predictions[task_id] = {
            "predicted_roi": predicted_roi,
            "predicted_effectiveness": predicted_effectiveness,
            "category": category,
            "recorded_at": datetime.now(),
        }
        logger.debug(
            "[IMP-TASK-003] Recorded ROI prediction for task %s: "
            "roi=%.2f, effectiveness=%.2f, category='%s'",
            task_id,
            predicted_roi,
            predicted_effectiveness,
            category,
        )

    def rank_tasks_by_roi(self, analyses: list[PaybackAnalysis]) -> list[PaybackAnalysis]:
        """Sort tasks by risk-adjusted ROI (descending).

        Args:
            analyses: List of PaybackAnalysis objects to rank.

        Returns:
            List sorted by risk_adjusted_roi in descending order.
        """
        return sorted(analyses, key=lambda t: t.risk_adjusted_roi, reverse=True)

    def rank_tasks_by_payback(self, analyses: list[PaybackAnalysis]) -> list[PaybackAnalysis]:
        """Sort tasks by payback period (ascending).

        Shorter payback periods are ranked higher.

        Args:
            analyses: List of PaybackAnalysis objects to rank.

        Returns:
            List sorted by payback_phases in ascending order.
        """
        return sorted(analyses, key=lambda t: t.payback_phases)

    def filter_profitable_tasks(self, analyses: list[PaybackAnalysis]) -> list[PaybackAnalysis]:
        """Filter to only profitable tasks.

        Args:
            analyses: List of PaybackAnalysis objects to filter.

        Returns:
            List containing only tasks with positive lifetime value.
        """
        return [a for a in analyses if a.is_profitable()]

    def filter_quick_payback_tasks(
        self,
        analyses: list[PaybackAnalysis],
        threshold_phases: int = 10,
    ) -> list[PaybackAnalysis]:
        """Filter to tasks with quick payback.

        Args:
            analyses: List of PaybackAnalysis objects to filter.
            threshold_phases: Maximum phases for quick payback.

        Returns:
            List containing only tasks with payback within threshold.
        """
        return [a for a in analyses if a.has_quick_payback(threshold_phases)]

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of ROI analysis history.

        Returns:
            Dictionary containing:
            - total_analyses: Total number of analyzed tasks
            - avg_roi: Average risk-adjusted ROI
            - by_category: Statistics by category
            - profitable_rate: Percentage of profitable tasks
            - grade_distribution: Count of tasks by ROI grade
        """
        analyses = self.history.analyses

        if not analyses:
            return {
                "total_analyses": 0,
                "avg_roi": 0.0,
                "avg_payback_phases": 0.0,
                "by_category": {},
                "profitable_rate": 0.0,
                "grade_distribution": {
                    "excellent": 0,
                    "good": 0,
                    "moderate": 0,
                    "poor": 0,
                },
            }

        total_roi = sum(a.risk_adjusted_roi for a in analyses)
        total_payback = sum(a.payback_phases for a in analyses)
        profitable_count = sum(1 for a in analyses if a.is_profitable())

        # Count by grade
        grade_distribution: dict[str, int] = {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }
        for analysis in analyses:
            grade = analysis.get_roi_grade()
            grade_distribution[grade] += 1

        return {
            "total_analyses": len(analyses),
            "avg_roi": total_roi / len(analyses),
            "avg_payback_phases": total_payback / len(analyses),
            "by_category": dict(self.history.category_stats),
            "profitable_rate": profitable_count / len(analyses),
            "grade_distribution": grade_distribution,
        }

    def get_validation_summary(self) -> dict[str, Any]:
        """Get a summary of ROI prediction validation.

        IMP-TASK-003: Provides visibility into prediction accuracy and
        learned effectiveness values.

        Returns:
            Dictionary containing:
            - total_validations: Total number of validated predictions
            - avg_error: Average absolute error between predicted and actual ROI
            - accuracy_distribution: Count of validations by accuracy grade
            - learned_effectiveness: Learned effectiveness by category
            - pending_predictions: Count of predictions awaiting validation
        """
        if not self._roi_predictions:
            return {
                "total_validations": 0,
                "avg_error": 0.0,
                "avg_effectiveness_error": 0.0,
                "accuracy_distribution": {
                    "excellent": 0,
                    "good": 0,
                    "moderate": 0,
                    "poor": 0,
                },
                "learned_effectiveness": {},
                "pending_predictions": len(self._pending_predictions),
            }

        total_error = sum(r.error for r in self._roi_predictions)
        total_effectiveness_error = sum(
            abs(r.predicted_effectiveness - r.actual_effectiveness) for r in self._roi_predictions
        )

        # Count by accuracy grade
        accuracy_distribution: dict[str, int] = {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }
        for record in self._roi_predictions:
            grade = record.get_accuracy_grade()
            accuracy_distribution[grade] += 1

        # Prepare learned effectiveness summary
        learned_summary: dict[str, dict[str, Any]] = {}
        for category, stats in self._category_effectiveness.items():
            learned_summary[category] = {
                "effectiveness": stats.get("learned_effectiveness", DEFAULT_EFFECTIVENESS),
                "sample_count": stats.get("sample_count", 0),
            }

        return {
            "total_validations": len(self._roi_predictions),
            "avg_error": total_error / len(self._roi_predictions),
            "avg_effectiveness_error": total_effectiveness_error / len(self._roi_predictions),
            "accuracy_distribution": accuracy_distribution,
            "learned_effectiveness": learned_summary,
            "pending_predictions": len(self._pending_predictions),
        }
