"""Insight-to-Task Correlation Engine.

IMP-LOOP-031: Tracks which insights generated which tasks and
updates confidence scores based on task outcomes. This closes the
feedback loop between insight generation and task effectiveness.

The correlation engine enables:
- Tracking insight -> task lineage for attribution
- Recording task outcomes (success, failure, partial)
- Updating insight confidence based on historical task success rates
- Identifying high-ROI insight sources for prioritization
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Confidence adjustment factors based on task outcomes
SUCCESS_CONFIDENCE_BOOST = 0.1  # Boost confidence by 10% on success
FAILURE_CONFIDENCE_PENALTY = 0.15  # Reduce confidence by 15% on failure
PARTIAL_CONFIDENCE_ADJUSTMENT = 0.0  # No change for partial outcomes

# Minimum and maximum confidence bounds
MIN_CONFIDENCE = 0.1
MAX_CONFIDENCE = 1.0

# Minimum sample size for reliable confidence updates
MIN_SAMPLE_SIZE_FOR_UPDATE = 3


@dataclass
class InsightTaskCorrelation:
    """Tracks relationship between an insight and resulting task.

    IMP-LOOP-031: This dataclass maintains the lineage between an insight
    that triggered task generation and the task itself, including
    outcome tracking for feedback loop closure.

    Attributes:
        insight_id: Unique identifier for the source insight.
        task_id: Unique identifier for the generated task.
        insight_source: Source type of the insight (direct, analyzer, memory).
        insight_type: Type of insight (cost_sink, failure_mode, retry_cause, etc.).
        created_at: Timestamp when the correlation was recorded.
        task_outcome: Outcome of the task (success, failure, partial, or None if pending).
        outcome_timestamp: Timestamp when the outcome was recorded.
        confidence_before: Insight confidence at task creation time.
        confidence_after: Insight confidence after outcome processing.
    """

    insight_id: str
    task_id: str
    insight_source: str = "unknown"
    insight_type: str = "unknown"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_outcome: Optional[str] = None  # success, failure, partial
    outcome_timestamp: Optional[datetime] = None
    confidence_before: float = 1.0
    confidence_after: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "insight_id": self.insight_id,
            "task_id": self.task_id,
            "insight_source": self.insight_source,
            "insight_type": self.insight_type,
            "created_at": self.created_at.isoformat(),
            "task_outcome": self.task_outcome,
            "outcome_timestamp": (
                self.outcome_timestamp.isoformat() if self.outcome_timestamp else None
            ),
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
        }


@dataclass
class InsightEffectivenessStats:
    """Statistics about an insight's effectiveness based on task outcomes.

    IMP-LOOP-031: Aggregates task outcomes for a specific insight to
    calculate its updated confidence score.

    Attributes:
        insight_id: The insight being tracked.
        total_tasks: Total number of tasks generated from this insight.
        successful_tasks: Number of tasks that succeeded.
        failed_tasks: Number of tasks that failed.
        partial_tasks: Number of tasks with partial success.
        success_rate: Proportion of successful tasks.
        current_confidence: Current calculated confidence score.
    """

    insight_id: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    partial_tasks: int = 0
    success_rate: float = 0.0
    current_confidence: float = 1.0


class InsightCorrelationEngine:
    """Correlates insights with task outcomes for confidence scoring.

    IMP-LOOP-031: This engine maintains the mapping between insights and
    the tasks they generate, tracks task outcomes, and updates insight
    confidence scores to improve future task generation quality.

    The feedback loop works as follows:
    1. When a task is generated from an insight, record_task_creation() is called
    2. When a task completes, record_task_outcome() is called
    3. update_insight_confidence() recalculates confidence based on historical outcomes
    4. MemoryService can query updated confidence for future insight retrieval

    Attributes:
        _correlations: Dict mapping task_id to InsightTaskCorrelation.
        _insight_stats: Dict mapping insight_id to aggregated stats.
        _memory_service: Optional MemoryService for confidence persistence.
    """

    def __init__(
        self,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        """Initialize the InsightCorrelationEngine.

        Args:
            memory_service: Optional MemoryService for persisting confidence updates
                to the memory layer. When provided, confidence changes are propagated
                to stored insights.
        """
        self._correlations: Dict[str, InsightTaskCorrelation] = {}
        self._insight_to_tasks: Dict[str, List[str]] = {}  # insight_id -> [task_ids]
        self._insight_stats: Dict[str, InsightEffectivenessStats] = {}
        self._memory_service = memory_service

        logger.debug("[IMP-LOOP-031] InsightCorrelationEngine initialized")

    def set_memory_service(self, memory_service: MemoryService) -> None:
        """Set or update the memory service for confidence persistence.

        Args:
            memory_service: MemoryService instance for confidence updates.
        """
        self._memory_service = memory_service
        logger.debug("[IMP-LOOP-031] Memory service connected to correlation engine")

    def record_task_creation(
        self,
        insight_id: str,
        task_id: str,
        insight_source: str = "unknown",
        insight_type: str = "unknown",
        confidence: float = 1.0,
    ) -> InsightTaskCorrelation:
        """Record that a task was created from an insight.

        IMP-LOOP-031: Creates a correlation record linking the insight to
        the generated task. This is called by the task generator when
        creating tasks from insights.

        Args:
            insight_id: Unique identifier for the source insight.
            task_id: Unique identifier for the generated task.
            insight_source: Source type (direct, analyzer, memory).
            insight_type: Type of insight (cost_sink, failure_mode, etc.).
            confidence: Current confidence score of the insight.

        Returns:
            InsightTaskCorrelation record tracking the relationship.
        """
        correlation = InsightTaskCorrelation(
            insight_id=insight_id,
            task_id=task_id,
            insight_source=insight_source,
            insight_type=insight_type,
            confidence_before=confidence,
        )

        self._correlations[task_id] = correlation

        # Track tasks by insight for aggregation
        if insight_id not in self._insight_to_tasks:
            self._insight_to_tasks[insight_id] = []
        self._insight_to_tasks[insight_id].append(task_id)

        # Initialize stats if needed
        if insight_id not in self._insight_stats:
            self._insight_stats[insight_id] = InsightEffectivenessStats(
                insight_id=insight_id,
                current_confidence=confidence,
            )

        self._insight_stats[insight_id].total_tasks += 1

        logger.info(
            "[IMP-LOOP-031] Recorded task creation: insight=%s -> task=%s "
            "(source=%s, type=%s, confidence=%.2f)",
            insight_id,
            task_id,
            insight_source,
            insight_type,
            confidence,
        )

        return correlation

    def record_task_outcome(
        self,
        task_id: str,
        outcome: str,
        auto_update_confidence: bool = True,
    ) -> Optional[InsightTaskCorrelation]:
        """Record the outcome of a task and optionally update insight confidence.

        IMP-LOOP-031: Records the task outcome (success, failure, partial) and
        updates the correlation record. Optionally triggers confidence update
        for the source insight.

        Args:
            task_id: The task ID to record outcome for.
            outcome: Task outcome - one of "success", "failure", "partial".
            auto_update_confidence: If True, automatically update the source
                insight's confidence based on the outcome.

        Returns:
            Updated InsightTaskCorrelation, or None if task not found.
        """
        if task_id not in self._correlations:
            logger.warning(
                "[IMP-LOOP-031] Task %s not found in correlations, cannot record outcome",
                task_id,
            )
            return None

        # Validate outcome
        valid_outcomes = {"success", "failure", "partial"}
        if outcome not in valid_outcomes:
            logger.warning(
                "[IMP-LOOP-031] Invalid outcome '%s' for task %s, expected one of %s",
                outcome,
                task_id,
                valid_outcomes,
            )
            return None

        correlation = self._correlations[task_id]
        correlation.task_outcome = outcome
        correlation.outcome_timestamp = datetime.now(timezone.utc)

        # Update insight stats
        insight_id = correlation.insight_id
        if insight_id in self._insight_stats:
            stats = self._insight_stats[insight_id]
            if outcome == "success":
                stats.successful_tasks += 1
            elif outcome == "failure":
                stats.failed_tasks += 1
            elif outcome == "partial":
                stats.partial_tasks += 1

            # Recalculate success rate
            completed = stats.successful_tasks + stats.failed_tasks + stats.partial_tasks
            if completed > 0:
                stats.success_rate = stats.successful_tasks / completed

        logger.info(
            "[IMP-LOOP-031] Recorded task outcome: task=%s, outcome=%s, insight=%s",
            task_id,
            outcome,
            insight_id,
        )

        # Auto-update confidence if enabled
        if auto_update_confidence:
            new_confidence = self.update_insight_confidence(insight_id)
            correlation.confidence_after = new_confidence

        return correlation

    def update_insight_confidence(self, insight_id: str) -> float:
        """Update confidence score for an insight based on task outcomes.

        IMP-LOOP-031: Recalculates the confidence score for an insight based
        on the historical success rate of tasks generated from it. Higher
        success rates boost confidence; lower rates reduce it.

        The algorithm:
        - Requires MIN_SAMPLE_SIZE_FOR_UPDATE tasks before adjusting
        - Successful tasks boost confidence by SUCCESS_CONFIDENCE_BOOST
        - Failed tasks reduce confidence by FAILURE_CONFIDENCE_PENALTY
        - Confidence is bounded between MIN_CONFIDENCE and MAX_CONFIDENCE

        Args:
            insight_id: The insight to update confidence for.

        Returns:
            Updated confidence score (0.0-1.0).
        """
        if insight_id not in self._insight_stats:
            logger.debug(
                "[IMP-LOOP-031] No stats for insight %s, returning default confidence",
                insight_id,
            )
            return 1.0

        stats = self._insight_stats[insight_id]
        completed = stats.successful_tasks + stats.failed_tasks + stats.partial_tasks

        # Require minimum sample size for reliable updates
        if completed < MIN_SAMPLE_SIZE_FOR_UPDATE:
            logger.debug(
                "[IMP-LOOP-031] Insufficient samples for insight %s (%d < %d), "
                "keeping current confidence %.2f",
                insight_id,
                completed,
                MIN_SAMPLE_SIZE_FOR_UPDATE,
                stats.current_confidence,
            )
            return stats.current_confidence

        # Calculate confidence adjustment based on outcomes
        success_boost = stats.successful_tasks * SUCCESS_CONFIDENCE_BOOST
        failure_penalty = stats.failed_tasks * FAILURE_CONFIDENCE_PENALTY
        partial_adjustment = stats.partial_tasks * PARTIAL_CONFIDENCE_ADJUSTMENT

        # Start from base confidence of 0.5 and adjust based on outcomes
        base_confidence = 0.5
        adjustment = success_boost - failure_penalty + partial_adjustment

        # Normalize adjustment by number of completed tasks
        normalized_adjustment = adjustment / completed

        new_confidence = base_confidence + normalized_adjustment

        # Bound confidence to valid range
        new_confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, new_confidence))

        old_confidence = stats.current_confidence
        stats.current_confidence = new_confidence

        logger.info(
            "[IMP-LOOP-031] Updated confidence for insight %s: %.2f -> %.2f "
            "(success=%d, failure=%d, partial=%d)",
            insight_id,
            old_confidence,
            new_confidence,
            stats.successful_tasks,
            stats.failed_tasks,
            stats.partial_tasks,
        )

        # Persist to memory service if available
        self._persist_confidence_update(insight_id, new_confidence)

        return new_confidence

    def _persist_confidence_update(
        self,
        insight_id: str,
        confidence: float,
    ) -> bool:
        """Persist confidence update to memory service.

        Args:
            insight_id: The insight to update.
            confidence: New confidence score.

        Returns:
            True if persistence was successful, False otherwise.
        """
        if self._memory_service is None:
            logger.debug(
                "[IMP-LOOP-031] No memory service configured, skipping confidence persistence"
            )
            return False

        try:
            # Update confidence in memory service
            # This requires memory_service to support confidence updates
            if hasattr(self._memory_service, "update_insight_confidence"):
                self._memory_service.update_insight_confidence(insight_id, confidence)
                logger.debug(
                    "[IMP-LOOP-031] Persisted confidence %.2f for insight %s to memory",
                    confidence,
                    insight_id,
                )
                return True
            else:
                logger.debug("[IMP-LOOP-031] Memory service does not support confidence updates")
                return False
        except Exception as e:
            logger.warning(
                "[IMP-LOOP-031] Failed to persist confidence for insight %s: %s",
                insight_id,
                e,
            )
            return False

    def get_insight_confidence(self, insight_id: str) -> float:
        """Get the current confidence score for an insight.

        Args:
            insight_id: The insight to query.

        Returns:
            Current confidence score, or 1.0 if insight not tracked.
        """
        if insight_id in self._insight_stats:
            return self._insight_stats[insight_id].current_confidence
        return 1.0

    def get_insight_stats(self, insight_id: str) -> Optional[InsightEffectivenessStats]:
        """Get effectiveness statistics for an insight.

        Args:
            insight_id: The insight to query.

        Returns:
            InsightEffectivenessStats or None if not tracked.
        """
        return self._insight_stats.get(insight_id)

    def get_correlation(self, task_id: str) -> Optional[InsightTaskCorrelation]:
        """Get the correlation record for a task.

        Args:
            task_id: The task to query.

        Returns:
            InsightTaskCorrelation or None if not tracked.
        """
        return self._correlations.get(task_id)

    def get_tasks_for_insight(self, insight_id: str) -> List[str]:
        """Get all task IDs generated from an insight.

        Args:
            insight_id: The insight to query.

        Returns:
            List of task IDs.
        """
        return self._insight_to_tasks.get(insight_id, [])

    def get_correlation_summary(self) -> Dict[str, Any]:
        """Get a summary of correlation tracking status.

        Returns:
            Dictionary containing:
            - total_correlations: Total insight-task correlations tracked
            - total_insights: Number of unique insights tracked
            - outcomes_recorded: Number of task outcomes recorded
            - pending_outcomes: Number of tasks awaiting outcomes
            - avg_confidence: Average confidence across all insights
            - by_outcome: Breakdown by outcome type
            - by_source: Breakdown by insight source
        """
        total_correlations = len(self._correlations)
        total_insights = len(self._insight_stats)

        outcomes_recorded = sum(
            1 for c in self._correlations.values() if c.task_outcome is not None
        )
        pending_outcomes = total_correlations - outcomes_recorded

        # Calculate average confidence
        if self._insight_stats:
            avg_confidence = sum(s.current_confidence for s in self._insight_stats.values()) / len(
                self._insight_stats
            )
        else:
            avg_confidence = 1.0

        # Breakdown by outcome
        by_outcome: Dict[str, int] = {"success": 0, "failure": 0, "partial": 0}
        for c in self._correlations.values():
            if c.task_outcome in by_outcome:
                by_outcome[c.task_outcome] += 1

        # Breakdown by source
        by_source: Dict[str, int] = {}
        for c in self._correlations.values():
            source = c.insight_source
            by_source[source] = by_source.get(source, 0) + 1

        return {
            "total_correlations": total_correlations,
            "total_insights": total_insights,
            "outcomes_recorded": outcomes_recorded,
            "pending_outcomes": pending_outcomes,
            "avg_confidence": round(avg_confidence, 3),
            "by_outcome": by_outcome,
            "by_source": by_source,
        }

    def get_high_performing_insights(
        self,
        min_success_rate: float = 0.7,
        min_tasks: int = MIN_SAMPLE_SIZE_FOR_UPDATE,
    ) -> List[InsightEffectivenessStats]:
        """Get insights with high task success rates.

        IMP-LOOP-031: Identifies insights that consistently generate
        successful tasks, which can be prioritized for future task generation.

        Args:
            min_success_rate: Minimum success rate to include.
            min_tasks: Minimum number of completed tasks required.

        Returns:
            List of InsightEffectivenessStats for high-performing insights.
        """
        high_performers = []
        for stats in self._insight_stats.values():
            completed = stats.successful_tasks + stats.failed_tasks + stats.partial_tasks
            if completed >= min_tasks and stats.success_rate >= min_success_rate:
                high_performers.append(stats)

        # Sort by success rate descending
        high_performers.sort(key=lambda s: s.success_rate, reverse=True)

        logger.debug(
            "[IMP-LOOP-031] Found %d high-performing insights (success_rate >= %.2f, tasks >= %d)",
            len(high_performers),
            min_success_rate,
            min_tasks,
        )

        return high_performers

    def get_low_performing_insights(
        self,
        max_success_rate: float = 0.3,
        min_tasks: int = MIN_SAMPLE_SIZE_FOR_UPDATE,
    ) -> List[InsightEffectivenessStats]:
        """Get insights with low task success rates.

        IMP-LOOP-031: Identifies insights that consistently generate
        failed tasks, which should have reduced confidence or be filtered.

        Args:
            max_success_rate: Maximum success rate to include.
            min_tasks: Minimum number of completed tasks required.

        Returns:
            List of InsightEffectivenessStats for low-performing insights.
        """
        low_performers = []
        for stats in self._insight_stats.values():
            completed = stats.successful_tasks + stats.failed_tasks + stats.partial_tasks
            if completed >= min_tasks and stats.success_rate <= max_success_rate:
                low_performers.append(stats)

        # Sort by success rate ascending (worst first)
        low_performers.sort(key=lambda s: s.success_rate)

        logger.debug(
            "[IMP-LOOP-031] Found %d low-performing insights (success_rate <= %.2f, tasks >= %d)",
            len(low_performers),
            max_success_rate,
            min_tasks,
        )

        return low_performers
