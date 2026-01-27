"""ROI and payback analysis for task prioritization.

Calculates the return on investment for generated tasks,
including payback period and lifetime value. This enables
data-driven task prioritization based on expected returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from autopack.task_generation.task_effectiveness_tracker import (
        TaskEffectivenessTracker,
    )

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

    Attributes:
        effectiveness_tracker: TaskEffectivenessTracker for historical data.
        history: ROIHistory containing all calculated analyses.
        phases_horizon: Number of phases to consider for lifetime value.
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

        Tries to get task-specific effectiveness first, then category
        effectiveness, then falls back to default.

        Args:
            task_id: Task ID to look up.
            category: Category for fallback lookup.

        Returns:
            Effectiveness score (0.0-1.0).
        """
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
