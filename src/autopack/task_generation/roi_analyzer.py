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
    from autopack.telemetry.cost_tracker import CostTracker

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
class ActualROIResult:
    """Result of actual ROI measurement after task completion.

    IMP-LOOP-031: Captures the actual ROI achieved by comparing estimated
    payback with actual costs and savings observed post-completion.

    Attributes:
        task_id: Unique identifier for the task.
        estimated_payback: Originally estimated payback period (phases).
        actual_payback: Actual payback period based on real costs/savings.
        actual_cost: Actual token cost incurred during task execution.
        actual_savings: Actual savings achieved (tokens saved per phase).
        actual_roi: Computed actual ROI (lifetime value / cost).
        measured_at: Timestamp when the measurement was taken.
    """

    task_id: str
    estimated_payback: int
    actual_payback: float  # Can be infinite if no savings
    actual_cost: float
    actual_savings: float
    actual_roi: float
    measured_at: datetime = field(default_factory=datetime.now)

    def achieved_payback(self) -> bool:
        """Check if task achieved payback within reasonable horizon.

        Returns:
            True if actual_payback is finite and <= 2x estimated payback.
        """
        if self.actual_payback == float("inf"):
            return False
        return self.actual_payback <= self.estimated_payback * 2

    def get_roi_grade(self) -> str:
        """Return a human-readable ROI grade for actual results.

        Returns:
            One of: "excellent", "good", "moderate", "poor"
        """
        if self.actual_roi >= EXCELLENT_ROI:
            return "excellent"
        elif self.actual_roi >= GOOD_ROI:
            return "good"
        elif self.actual_roi >= MODERATE_ROI:
            return "moderate"
        else:
            return "poor"


@dataclass
class ROIAccuracyReport:
    """Report comparing estimated vs actual ROI for prioritization calibration.

    IMP-LOOP-031: Enables calibration of the prioritization engine by
    measuring the accuracy of ROI predictions. The calibration_factor
    can be used to adjust future predictions.

    Attributes:
        task_id: Unique identifier for the task.
        estimated_payback: Originally predicted payback period.
        actual_payback: Actual payback period observed.
        prediction_error: Absolute difference between estimated and actual.
        calibration_factor: Ratio for adjusting future predictions.
        accuracy_grade: Human-readable grade of prediction accuracy.
        category: Category of the task for pattern analysis.
        measured_at: Timestamp when the comparison was made.
    """

    task_id: str
    estimated_payback: int
    actual_payback: float
    prediction_error: float
    calibration_factor: float
    accuracy_grade: str
    category: str = ""
    measured_at: datetime = field(default_factory=datetime.now)

    def is_calibration_needed(self) -> bool:
        """Check if calibration adjustment is significant.

        Returns:
            True if calibration_factor deviates more than 20% from 1.0.
        """
        return abs(self.calibration_factor - 1.0) > 0.2


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

    IMP-LOOP-031: Enhanced with actual ROI measurement and
    comparison for prioritization engine calibration.

    Attributes:
        effectiveness_tracker: TaskEffectivenessTracker for historical data.
        cost_tracker: CostTracker for actual cost data.
        history: ROIHistory containing all calculated analyses.
        phases_horizon: Number of phases to consider for lifetime value.
        _roi_predictions: List of ROI prediction records for validation.
        _category_effectiveness: Learned effectiveness by category.
        _prediction_accuracy: Tracked accuracy metrics by category.
        _actual_roi_results: List of actual ROI measurements.
        _accuracy_reports: List of ROI accuracy comparison reports.
    """

    def __init__(
        self,
        effectiveness_tracker: TaskEffectivenessTracker | None = None,
        cost_tracker: CostTracker | None = None,
        phases_horizon: int = DEFAULT_PHASES_HORIZON,
    ) -> None:
        """Initialize the ROIAnalyzer.

        Args:
            effectiveness_tracker: Optional TaskEffectivenessTracker instance.
                If not provided, uses default effectiveness assumptions.
            cost_tracker: Optional CostTracker instance for actual cost data.
                IMP-LOOP-031: Required for actual ROI measurement.
            phases_horizon: Number of phases to consider for lifetime value.
        """
        self.effectiveness_tracker = effectiveness_tracker
        self.cost_tracker = cost_tracker
        self.history = ROIHistory()
        self.phases_horizon = phases_horizon

        # IMP-TASK-003: ROI prediction validation tracking
        self._roi_predictions: list[ROIPredictionRecord] = []
        self._category_effectiveness: dict[str, dict[str, float]] = {}
        self._pending_predictions: dict[str, dict[str, Any]] = {}

        # IMP-LOOP-031: Actual ROI measurement tracking
        self._actual_roi_results: list[ActualROIResult] = []
        self._accuracy_reports: list[ROIAccuracyReport] = []
        self._task_actual_costs: dict[str, float] = {}
        self._task_actual_savings: dict[str, float] = {}

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

    # IMP-LOOP-031: Actual ROI measurement methods

    def record_task_cost(self, task_id: str, cost: float) -> None:
        """Record the actual cost incurred for a task.

        IMP-LOOP-031: Stores actual cost data for later ROI measurement.

        Args:
            task_id: Unique identifier for the task.
            cost: Actual token cost incurred during execution.
        """
        self._task_actual_costs[task_id] = cost
        logger.debug(
            "[IMP-LOOP-031] Recorded actual cost for task %s: %.2f tokens",
            task_id,
            cost,
        )

    def record_task_savings(self, task_id: str, savings: float) -> None:
        """Record the actual savings achieved by a task.

        IMP-LOOP-031: Stores actual savings data for later ROI measurement.

        Args:
            task_id: Unique identifier for the task.
            savings: Actual token savings per phase achieved.
        """
        self._task_actual_savings[task_id] = savings
        logger.debug(
            "[IMP-LOOP-031] Recorded actual savings for task %s: %.2f tokens/phase",
            task_id,
            savings,
        )

    def get_task_cost(self, task_id: str) -> float:
        """Get the actual cost for a task.

        IMP-LOOP-031: Retrieves recorded cost or estimates from cost tracker.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            Actual cost if recorded, or estimated cost from original analysis.
        """
        # First check if we have recorded actual cost
        if task_id in self._task_actual_costs:
            return self._task_actual_costs[task_id]

        # Fall back to original estimated cost from payback analysis
        for analysis in self.history.analyses:
            if analysis.task_id == task_id:
                return analysis.execution_cost_tokens

        logger.debug(
            "[IMP-LOOP-031] No cost data found for task %s, returning 0",
            task_id,
        )
        return 0.0

    def get_task_savings(self, task_id: str) -> float:
        """Get the actual savings for a task.

        IMP-LOOP-031: Retrieves recorded savings or computes from effectiveness data.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            Actual savings per phase if recorded, or 0 if no data.
        """
        # First check if we have recorded actual savings
        if task_id in self._task_actual_savings:
            return self._task_actual_savings[task_id]

        # Try to compute from effectiveness tracker
        if self.effectiveness_tracker is not None:
            effectiveness = self.effectiveness_tracker.get_effectiveness(task_id)
            # If we have a payback analysis, use it to estimate savings
            for analysis in self.history.analyses:
                if analysis.task_id == task_id:
                    # Actual savings = estimated savings * actual effectiveness / estimated effectiveness
                    return analysis.estimated_savings_per_phase * effectiveness

        logger.debug(
            "[IMP-LOOP-031] No savings data found for task %s, returning 0",
            task_id,
        )
        return 0.0

    def measure_actual_roi(self, task_id: str) -> ActualROIResult | None:
        """Measure actual ROI after task completion.

        IMP-LOOP-031: Computes the actual ROI based on real cost and savings
        data, comparing against the original estimated payback period.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            ActualROIResult with measured ROI, or None if task not found.
        """
        # Find the original payback analysis
        original_analysis: PaybackAnalysis | None = None
        for analysis in self.history.analyses:
            if analysis.task_id == task_id:
                original_analysis = analysis
                break

        if original_analysis is None:
            logger.warning(
                "[IMP-LOOP-031] No original analysis found for task %s, cannot measure ROI",
                task_id,
            )
            return None

        # Get actual cost and savings
        actual_cost = self.get_task_cost(task_id)
        actual_savings = self.get_task_savings(task_id)

        # Calculate actual payback period
        if actual_savings > MIN_SAVINGS_PER_PHASE:
            actual_payback = actual_cost / actual_savings
        else:
            actual_payback = float("inf")

        # Calculate actual ROI (lifetime value / cost)
        if actual_cost > 0 and actual_savings > 0:
            lifetime_value = (actual_savings * self.phases_horizon) - actual_cost
            actual_roi = lifetime_value / actual_cost
        else:
            actual_roi = 0.0

        result = ActualROIResult(
            task_id=task_id,
            estimated_payback=original_analysis.payback_phases,
            actual_payback=actual_payback,
            actual_cost=actual_cost,
            actual_savings=actual_savings,
            actual_roi=actual_roi,
        )

        # Store the result
        self._actual_roi_results.append(result)

        logger.info(
            "[IMP-LOOP-031] Measured actual ROI for task %s: "
            "estimated_payback=%d, actual_payback=%.1f, "
            "actual_roi=%.2f (%s), cost=%.0f, savings=%.2f/phase",
            task_id,
            original_analysis.payback_phases,
            actual_payback if actual_payback != float("inf") else -1,
            actual_roi,
            result.get_roi_grade(),
            actual_cost,
            actual_savings,
        )

        return result

    def compare_estimated_vs_actual(self, task_id: str) -> ROIAccuracyReport | None:
        """Compare ROI prediction accuracy for calibration.

        IMP-LOOP-031: Computes the prediction error and calibration factor
        by comparing estimated payback against actual payback. The calibration
        factor can be used to adjust future predictions for improved accuracy.

        Args:
            task_id: Unique identifier for the task.

        Returns:
            ROIAccuracyReport with comparison metrics, or None if measurement fails.
        """
        # First ensure we have an actual ROI measurement
        actual_result: ActualROIResult | None = None
        for result in self._actual_roi_results:
            if result.task_id == task_id:
                actual_result = result
                break

        # If no existing measurement, try to measure now
        if actual_result is None:
            actual_result = self.measure_actual_roi(task_id)

        if actual_result is None:
            return None

        # Calculate prediction error
        if actual_result.actual_payback == float("inf"):
            # If no actual payback achieved, error is the full estimated payback
            prediction_error = float(actual_result.estimated_payback)
        else:
            prediction_error = abs(actual_result.estimated_payback - actual_result.actual_payback)

        # Calculate calibration factor
        # calibration_factor > 1 means we under-estimated payback (actual takes longer)
        # calibration_factor < 1 means we over-estimated payback (actual is faster)
        if actual_result.estimated_payback > 0:
            if actual_result.actual_payback == float("inf"):
                calibration_factor = float("inf")
            else:
                calibration_factor = actual_result.actual_payback / actual_result.estimated_payback
        else:
            calibration_factor = 1.0

        # Determine accuracy grade
        if actual_result.actual_payback == float("inf"):
            accuracy_grade = "poor"
        else:
            relative_error = prediction_error / max(actual_result.estimated_payback, 1)
            if relative_error <= 0.1:
                accuracy_grade = "excellent"
            elif relative_error <= 0.25:
                accuracy_grade = "good"
            elif relative_error <= 0.5:
                accuracy_grade = "moderate"
            else:
                accuracy_grade = "poor"

        # Get category from original analysis
        category = ""
        for analysis in self.history.analyses:
            if analysis.task_id == task_id:
                category = analysis.category
                break

        report = ROIAccuracyReport(
            task_id=task_id,
            estimated_payback=actual_result.estimated_payback,
            actual_payback=actual_result.actual_payback,
            prediction_error=prediction_error,
            calibration_factor=calibration_factor if calibration_factor != float("inf") else 10.0,
            accuracy_grade=accuracy_grade,
            category=category,
        )

        # Store the report
        self._accuracy_reports.append(report)

        # Update category calibration for future predictions
        self._update_category_calibration(category, report.calibration_factor)

        logger.info(
            "[IMP-LOOP-031] ROI accuracy report for task %s: "
            "estimated=%d, actual=%.1f, error=%.1f, "
            "calibration_factor=%.2f, grade=%s",
            task_id,
            actual_result.estimated_payback,
            actual_result.actual_payback if actual_result.actual_payback != float("inf") else -1,
            prediction_error,
            report.calibration_factor,
            accuracy_grade,
        )

        return report

    def _update_category_calibration(self, category: str, calibration_factor: float) -> None:
        """Update category-level calibration based on accuracy report.

        IMP-LOOP-031: Maintains running average of calibration factors per
        category to improve future predictions.

        Args:
            category: Category to update.
            calibration_factor: New calibration factor to incorporate.
        """
        if calibration_factor == float("inf") or calibration_factor > 10.0:
            # Cap extreme values to prevent runaway calibration
            calibration_factor = 10.0

        cat_key = category or "general"

        if cat_key not in self._category_effectiveness:
            self._category_effectiveness[cat_key] = {}

        stats = self._category_effectiveness[cat_key]

        if "calibration_factor" not in stats:
            stats["calibration_factor"] = calibration_factor
            stats["calibration_samples"] = 1
        else:
            # Exponential moving average for smooth calibration
            old_calibration = stats["calibration_factor"]
            sample_count = stats.get("calibration_samples", 1)
            alpha = max(EFFECTIVENESS_LEARNING_RATE, 1.0 / (sample_count + 1))
            stats["calibration_factor"] = old_calibration * (1 - alpha) + calibration_factor * alpha
            stats["calibration_samples"] = sample_count + 1

        logger.debug(
            "[IMP-LOOP-031] Updated calibration for category '%s': factor=%.2f, samples=%d",
            cat_key,
            stats["calibration_factor"],
            stats.get("calibration_samples", 1),
        )

    def get_category_calibration_factor(self, category: str) -> float:
        """Get the calibration factor for a category.

        IMP-LOOP-031: Returns the learned calibration factor for adjusting
        future ROI predictions in this category.

        Args:
            category: Category to query.

        Returns:
            Calibration factor (1.0 means no adjustment needed).
        """
        cat_key = category or "general"
        if cat_key in self._category_effectiveness:
            return self._category_effectiveness[cat_key].get("calibration_factor", 1.0)
        return 1.0

    def get_roi_feedback_summary(self) -> dict[str, Any]:
        """Get a summary of ROI feedback loop status.

        IMP-LOOP-031: Provides visibility into the ROI feedback loop,
        showing measured vs estimated accuracy and calibration factors.

        Returns:
            Dictionary containing:
            - total_measurements: Number of actual ROI measurements
            - total_accuracy_reports: Number of accuracy comparison reports
            - avg_prediction_error: Average payback prediction error
            - avg_calibration_factor: Average calibration adjustment
            - accuracy_distribution: Count by accuracy grade
            - category_calibration: Calibration factors by category
            - tasks_achieving_payback: Count of tasks that achieved payback
        """
        if not self._actual_roi_results:
            return {
                "total_measurements": 0,
                "total_accuracy_reports": 0,
                "avg_prediction_error": 0.0,
                "avg_calibration_factor": 1.0,
                "accuracy_distribution": {
                    "excellent": 0,
                    "good": 0,
                    "moderate": 0,
                    "poor": 0,
                },
                "category_calibration": {},
                "tasks_achieving_payback": 0,
                "tasks_total": 0,
            }

        # Count tasks achieving payback
        tasks_achieving = sum(1 for r in self._actual_roi_results if r.achieved_payback())

        # Calculate average prediction error and calibration factor from reports
        if self._accuracy_reports:
            total_error = sum(r.prediction_error for r in self._accuracy_reports)
            total_calibration = sum(
                r.calibration_factor
                for r in self._accuracy_reports
                if r.calibration_factor != float("inf")
            )
            valid_calibrations = sum(
                1 for r in self._accuracy_reports if r.calibration_factor != float("inf")
            )
            avg_error = total_error / len(self._accuracy_reports)
            avg_calibration = (
                total_calibration / valid_calibrations if valid_calibrations > 0 else 1.0
            )
        else:
            avg_error = 0.0
            avg_calibration = 1.0

        # Count by accuracy grade
        accuracy_distribution: dict[str, int] = {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }
        for report in self._accuracy_reports:
            accuracy_distribution[report.accuracy_grade] += 1

        # Prepare category calibration summary
        category_calibration: dict[str, float] = {}
        for category, stats in self._category_effectiveness.items():
            if "calibration_factor" in stats:
                category_calibration[category] = stats["calibration_factor"]

        return {
            "total_measurements": len(self._actual_roi_results),
            "total_accuracy_reports": len(self._accuracy_reports),
            "avg_prediction_error": avg_error,
            "avg_calibration_factor": avg_calibration,
            "accuracy_distribution": accuracy_distribution,
            "category_calibration": category_calibration,
            "tasks_achieving_payback": tasks_achieving,
            "tasks_total": len(self._actual_roi_results),
        }
