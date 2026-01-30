"""Memory-to-Task Promoter.

IMP-LOOP-032: Scans memory for recurring failure patterns and
automatically promotes them to tasks when threshold is exceeded.

The promoter enables automatic escalation of issues that appear
repeatedly in memory, ensuring that recurring problems are
addressed proactively without manual intervention.

Key features:
- Scans memory for insights with high occurrence counts
- Promotes insights exceeding threshold to actionable tasks
- Tracks which insights have been promoted to avoid duplicates
- Integrates with InsightCorrelationEngine for lineage tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from autopack.memory.memory_service import MemoryService
    from autopack.roadc.task_generator import AutonomousTaskGenerator
    from autopack.task_generation.insight_correlation import InsightCorrelationEngine

logger = logging.getLogger(__name__)

# Default threshold for promotion: insights with >= this many occurrences
# are considered candidates for automatic task generation
DEFAULT_PROMOTION_THRESHOLD = 3

# Minimum confidence required for promotion
# Low-confidence insights should not be promoted even if recurring
MIN_CONFIDENCE_FOR_PROMOTION = 0.5

# Maximum number of insights to promote in a single scan
MAX_PROMOTIONS_PER_SCAN = 10


@dataclass
class PromotableInsight:
    """An insight that is eligible for promotion to a task.

    IMP-LOOP-032: Captures insights from memory that have recurred
    enough times to warrant automatic task generation.

    Attributes:
        insight_id: Unique identifier for the insight in memory.
        content: The insight content/description.
        issue_type: Type of issue (cost_sink, failure_mode, retry_cause).
        occurrence_count: Number of times this insight has occurred.
        confidence: Current confidence score of the insight.
        last_occurrence: Timestamp of the most recent occurrence.
        severity: Severity level (high, medium, low).
        source_runs: List of run IDs where this insight was observed.
        details: Additional metadata about the insight.
    """

    insight_id: str
    content: str
    issue_type: str = "unknown"
    occurrence_count: int = 1
    confidence: float = 1.0
    last_occurrence: Optional[datetime] = None
    severity: str = "medium"
    source_runs: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "insight_id": self.insight_id,
            "content": self.content,
            "issue_type": self.issue_type,
            "occurrence_count": self.occurrence_count,
            "confidence": self.confidence,
            "last_occurrence": (self.last_occurrence.isoformat() if self.last_occurrence else None),
            "severity": self.severity,
            "source_runs": self.source_runs,
            "details": self.details,
        }


@dataclass
class PromotionResult:
    """Result of promoting an insight to a task.

    IMP-LOOP-032: Tracks the outcome of a promotion attempt,
    including the generated task ID if successful.

    Attributes:
        insight_id: The insight that was promoted.
        success: Whether the promotion succeeded.
        task_id: ID of the generated task (if successful).
        error: Error message (if failed).
        promoted_at: Timestamp of the promotion.
    """

    insight_id: str
    success: bool
    task_id: Optional[str] = None
    error: Optional[str] = None
    promoted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryTaskPromoter:
    """Promotes recurring memory insights to actionable tasks.

    IMP-LOOP-032: This component bridges memory (where patterns accumulate)
    and task generation (where actions are taken). It automatically scans
    memory for insights that have recurred multiple times and promotes them
    to tasks for execution.

    The promotion workflow:
    1. scan_for_promotable_insights() finds high-occurrence insights
    2. promote_insight_to_task() creates a task from an insight
    3. The task is persisted and executed via the normal task pipeline
    4. Task outcomes flow back to confidence scoring via correlation engine

    Attributes:
        _memory_service: MemoryService for insight retrieval.
        _task_generator: AutonomousTaskGenerator for task creation.
        _correlation_engine: InsightCorrelationEngine for tracking lineage.
        _threshold: Occurrence threshold for promotion eligibility.
        _promoted_insights: Set of insight IDs already promoted (dedup).
        _project_id: Project ID for namespace isolation.
    """

    def __init__(
        self,
        memory_service: Optional[MemoryService] = None,
        task_generator: Optional[AutonomousTaskGenerator] = None,
        correlation_engine: Optional[InsightCorrelationEngine] = None,
        promotion_threshold: int = DEFAULT_PROMOTION_THRESHOLD,
        project_id: str = "default",
    ) -> None:
        """Initialize the MemoryTaskPromoter.

        Args:
            memory_service: MemoryService instance for insight retrieval.
                If None, must be set later via set_memory_service().
            task_generator: AutonomousTaskGenerator for creating tasks.
                If None, must be set later via set_task_generator().
            correlation_engine: InsightCorrelationEngine for tracking
                insight-to-task lineage. Optional but recommended.
            promotion_threshold: Minimum occurrence count for an insight
                to be eligible for promotion. Default: 3.
            project_id: Project ID for namespace isolation (IMP-MEM-015).
        """
        self._memory_service = memory_service
        self._task_generator = task_generator
        self._correlation_engine = correlation_engine
        self._threshold = promotion_threshold
        self._project_id = project_id
        self._promoted_insights: Set[str] = set()

        logger.debug(
            "[IMP-LOOP-032] MemoryTaskPromoter initialized " "(threshold=%d, project=%s)",
            self._threshold,
            self._project_id,
        )

    def set_memory_service(self, memory_service: MemoryService) -> None:
        """Set or update the memory service.

        Args:
            memory_service: MemoryService instance.
        """
        self._memory_service = memory_service
        logger.debug("[IMP-LOOP-032] Memory service connected to promoter")

    def set_task_generator(self, task_generator: AutonomousTaskGenerator) -> None:
        """Set or update the task generator.

        Args:
            task_generator: AutonomousTaskGenerator instance.
        """
        self._task_generator = task_generator
        logger.debug("[IMP-LOOP-032] Task generator connected to promoter")

    def set_correlation_engine(self, correlation_engine: InsightCorrelationEngine) -> None:
        """Set or update the correlation engine.

        Args:
            correlation_engine: InsightCorrelationEngine instance.
        """
        self._correlation_engine = correlation_engine
        logger.debug("[IMP-LOOP-032] Correlation engine connected to promoter")

    def scan_for_promotable_insights(
        self,
        min_occurrences: Optional[int] = None,
        min_confidence: float = MIN_CONFIDENCE_FOR_PROMOTION,
        limit: int = MAX_PROMOTIONS_PER_SCAN,
        exclude_promoted: bool = True,
    ) -> List[PromotableInsight]:
        """Scan memory for insights that exceed the promotion threshold.

        IMP-LOOP-032: Queries memory for insights with high occurrence counts
        and sufficient confidence, returning candidates for promotion.

        Args:
            min_occurrences: Minimum occurrence count (defaults to threshold).
            min_confidence: Minimum confidence score required.
            limit: Maximum number of insights to return.
            exclude_promoted: If True, exclude already-promoted insights.

        Returns:
            List of PromotableInsight objects sorted by occurrence count.
        """
        if self._memory_service is None:
            logger.warning("[IMP-LOOP-032] Cannot scan: memory service not configured")
            return []

        effective_threshold = min_occurrences if min_occurrences is not None else self._threshold

        logger.debug(
            "[IMP-LOOP-032] Scanning for promotable insights "
            "(threshold=%d, min_confidence=%.2f, limit=%d)",
            effective_threshold,
            min_confidence,
            limit,
        )

        try:
            # Query memory for high-occurrence insights
            # Use a broad query to get failure patterns
            query = "failure error recurring pattern problem issue"
            raw_insights = self._memory_service.retrieve_insights(
                query=query,
                project_id=self._project_id,
                limit=limit * 3,  # Fetch extra to account for filtering
                min_confidence=min_confidence,
            )

            promotable: List[PromotableInsight] = []

            for raw in raw_insights:
                # Extract occurrence count from payload
                payload = raw.get("payload", {})
                if isinstance(raw, dict) and "occurrence_count" not in raw:
                    # Try to get from payload
                    occurrence_count = payload.get("occurrence_count", 1)
                else:
                    occurrence_count = raw.get("occurrence_count", 1)

                # Skip if below threshold
                if occurrence_count < effective_threshold:
                    continue

                # Get insight ID
                insight_id = raw.get("id", payload.get("id", ""))
                if not insight_id:
                    continue

                # Skip if already promoted (dedup)
                if exclude_promoted and insight_id in self._promoted_insights:
                    logger.debug(
                        "[IMP-LOOP-032] Skipping already-promoted insight %s",
                        insight_id,
                    )
                    continue

                # Extract confidence
                confidence = raw.get("confidence", payload.get("confidence", 1.0))
                if confidence < min_confidence:
                    continue

                # Build PromotableInsight
                # Parse last_occurrence timestamp
                last_occurrence_str = raw.get("last_occurrence", payload.get("last_occurrence"))
                last_occurrence = None
                if last_occurrence_str:
                    try:
                        if last_occurrence_str.endswith("Z"):
                            last_occurrence_str = last_occurrence_str[:-1] + "+00:00"
                        last_occurrence = datetime.fromisoformat(last_occurrence_str)
                    except (ValueError, TypeError):
                        pass

                promotable_insight = PromotableInsight(
                    insight_id=insight_id,
                    content=raw.get("content", payload.get("content", "")),
                    issue_type=raw.get("issue_type", payload.get("issue_type", "unknown")),
                    occurrence_count=occurrence_count,
                    confidence=confidence,
                    last_occurrence=last_occurrence,
                    severity=raw.get("severity", payload.get("severity", "medium")),
                    source_runs=payload.get("source_runs", []),
                    details=payload.get("details", {}),
                )

                promotable.append(promotable_insight)

            # Sort by occurrence count descending
            promotable.sort(key=lambda x: x.occurrence_count, reverse=True)

            # Apply limit
            promotable = promotable[:limit]

            logger.info(
                "[IMP-LOOP-032] Found %d promotable insights " "(scanned %d, threshold=%d)",
                len(promotable),
                len(raw_insights),
                effective_threshold,
            )

            return promotable

        except Exception as e:
            logger.error("[IMP-LOOP-032] Error scanning for promotable insights: %s", e)
            return []

    def promote_insight_to_task(
        self,
        insight: PromotableInsight,
        run_id: Optional[str] = None,
    ) -> PromotionResult:
        """Promote a specific insight to a task.

        IMP-LOOP-032: Creates a task from a promotable insight using the
        task generator, and records the correlation for lineage tracking.

        Args:
            insight: The PromotableInsight to promote.
            run_id: Optional run ID to associate with the task.

        Returns:
            PromotionResult indicating success/failure and task ID.
        """
        if self._task_generator is None:
            logger.warning("[IMP-LOOP-032] Cannot promote: task generator not configured")
            return PromotionResult(
                insight_id=insight.insight_id,
                success=False,
                error="Task generator not configured",
            )

        logger.info(
            "[IMP-LOOP-032] Promoting insight %s to task "
            "(occurrences=%d, type=%s, confidence=%.2f)",
            insight.insight_id,
            insight.occurrence_count,
            insight.issue_type,
            insight.confidence,
        )

        try:
            # Convert PromotableInsight to the format expected by task generator
            # We create a synthetic telemetry insight for the generator
            synthetic_insight = {
                "id": insight.insight_id,
                "issue_type": insight.issue_type,
                "content": insight.content,
                "severity": insight.severity,
                "confidence": insight.confidence,
                "details": {
                    **insight.details,
                    "occurrence_count": insight.occurrence_count,
                    "promoted_from_memory": True,
                    "promotion_threshold": self._threshold,
                },
            }

            # Use the task generator to create a task
            # We pass the insight through the unified insight interface
            from autopack.roadc.task_generator import InsightSource, UnifiedInsight

            _unified_insight = UnifiedInsight(  # noqa: F841 - kept for debugging/future use
                id=insight.insight_id,
                issue_type=insight.issue_type,
                content=insight.content,
                severity=insight.severity,
                confidence=insight.confidence,
                details=synthetic_insight["details"],
                source=InsightSource.MEMORY,
            )

            # Generate task via the generator's internal methods
            # Build a pattern from the single insight for task generation
            pattern = {
                "type": insight.issue_type,
                "occurrences": insight.occurrence_count,
                "confidence": insight.confidence,
                "examples": [synthetic_insight],
                "severity": self._calculate_severity_score(insight),
                "telemetry_boosted": False,
                "discovery_boosted": False,
                "promoted_from_memory": True,
            }

            task = self._task_generator._pattern_to_task(pattern)

            # Enhance task description with promotion context
            task.description = (
                f"[AUTO-PROMOTED] {task.description}\n\n"
                f"## Promotion Context\n"
                f"- Insight occurred {insight.occurrence_count} times\n"
                f"- Confidence score: {insight.confidence:.2f}\n"
                f"- Issue type: {insight.issue_type}\n"
                f"- Promotion threshold: {self._threshold}\n"
            )

            # Mark as promoted to prevent re-promotion
            self._promoted_insights.add(insight.insight_id)

            # Record correlation if engine is available
            if self._correlation_engine is not None:
                self._correlation_engine.record_task_creation(
                    insight_id=insight.insight_id,
                    task_id=task.task_id,
                    insight_source="memory",
                    insight_type=insight.issue_type,
                    confidence=insight.confidence,
                )

            # Persist the task
            if run_id:
                task.run_id = run_id

            persisted = self._task_generator.persist_tasks([task], run_id=run_id)

            logger.info(
                "[IMP-LOOP-032] Successfully promoted insight %s to task %s " "(persisted=%d)",
                insight.insight_id,
                task.task_id,
                persisted,
            )

            return PromotionResult(
                insight_id=insight.insight_id,
                success=True,
                task_id=task.task_id,
            )

        except Exception as e:
            logger.error(
                "[IMP-LOOP-032] Failed to promote insight %s: %s",
                insight.insight_id,
                e,
            )
            return PromotionResult(
                insight_id=insight.insight_id,
                success=False,
                error=str(e),
            )

    def promote_all_eligible(
        self,
        run_id: Optional[str] = None,
        max_promotions: int = MAX_PROMOTIONS_PER_SCAN,
    ) -> List[PromotionResult]:
        """Scan and promote all eligible insights in one operation.

        IMP-LOOP-032: Convenience method that combines scanning and
        promotion for batch processing.

        Args:
            run_id: Optional run ID to associate with generated tasks.
            max_promotions: Maximum number of promotions to perform.

        Returns:
            List of PromotionResult for each promotion attempt.
        """
        results: List[PromotionResult] = []

        # Scan for promotable insights
        promotable = self.scan_for_promotable_insights(limit=max_promotions)

        if not promotable:
            logger.debug("[IMP-LOOP-032] No eligible insights found for promotion")
            return results

        logger.info(
            "[IMP-LOOP-032] Promoting %d eligible insights to tasks",
            len(promotable),
        )

        # Promote each insight
        for insight in promotable:
            result = self.promote_insight_to_task(insight, run_id=run_id)
            results.append(result)

        # Summary logging
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        logger.info(
            "[IMP-LOOP-032] Promotion batch complete: %d successful, %d failed",
            successful,
            failed,
        )

        return results

    def _calculate_severity_score(self, insight: PromotableInsight) -> int:
        """Calculate numeric severity score for task generation.

        Args:
            insight: The insight to score.

        Returns:
            Severity score (0-10) for task priority calculation.
        """
        base_score = {"high": 8, "medium": 5, "low": 2}.get(insight.severity, 5)

        # Boost based on occurrence count
        occurrence_boost = min(insight.occurrence_count - self._threshold, 3)

        # Boost based on confidence
        confidence_boost = 1 if insight.confidence >= 0.8 else 0

        return min(10, base_score + occurrence_boost + confidence_boost)

    def get_promotion_stats(self) -> Dict[str, Any]:
        """Get statistics about promotions performed.

        Returns:
            Dictionary containing promotion statistics.
        """
        return {
            "promoted_count": len(self._promoted_insights),
            "promoted_insight_ids": list(self._promoted_insights),
            "threshold": self._threshold,
            "project_id": self._project_id,
        }

    def clear_promotion_history(self) -> int:
        """Clear the set of promoted insights, allowing re-promotion.

        Use with caution - this may lead to duplicate tasks.

        Returns:
            Number of insights cleared from history.
        """
        count = len(self._promoted_insights)
        self._promoted_insights.clear()
        logger.info("[IMP-LOOP-032] Cleared %d insights from promotion history", count)
        return count

    def is_already_promoted(self, insight_id: str) -> bool:
        """Check if an insight has already been promoted.

        Args:
            insight_id: The insight ID to check.

        Returns:
            True if already promoted, False otherwise.
        """
        return insight_id in self._promoted_insights
