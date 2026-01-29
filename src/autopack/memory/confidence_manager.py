"""Confidence Score Lifecycle Manager.

IMP-LOOP-034: Manages confidence score decay and updates based
on task outcomes for the self-improvement feedback loop.

This module implements a confidence lifecycle where:
1. Insights start with high confidence when freshly observed
2. Confidence decays exponentially over time (configurable half-life)
3. Task outcomes adjust confidence (success boosts, failure penalizes)
4. Low-confidence insights are filtered from task generation

The decay model uses exponential decay:
    decayed_confidence = original_confidence * (0.5 ^ (age_days / half_life_days))

This ensures that old insights naturally lose relevance unless
reinforced by successful task outcomes.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from autopack.memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Default half-life for confidence decay (days)
# After this many days, confidence drops to 50% of original
DEFAULT_DECAY_HALF_LIFE_DAYS = 7.0

# Minimum confidence floor - insights never decay below this
MIN_CONFIDENCE = 0.1

# Maximum confidence ceiling
MAX_CONFIDENCE = 1.0

# Confidence adjustment factors for task outcomes
SUCCESS_CONFIDENCE_BOOST = 0.15  # Boost by 15% on success
FAILURE_CONFIDENCE_PENALTY = 0.20  # Reduce by 20% on failure
PARTIAL_CONFIDENCE_ADJUSTMENT = 0.05  # Small boost for partial success


@dataclass
class ConfidenceState:
    """Tracks the confidence state for an insight.

    IMP-LOOP-034: Captures the complete confidence state including
    original value, decay parameters, and outcome adjustments.

    Attributes:
        insight_id: Unique identifier for the insight.
        original_confidence: Initial confidence when insight was created.
        created_at: Timestamp when the insight was created.
        last_updated: Timestamp of last confidence update.
        outcome_adjustment: Cumulative adjustment from task outcomes.
        success_count: Number of successful tasks from this insight.
        failure_count: Number of failed tasks from this insight.
        partial_count: Number of partially successful tasks.
    """

    insight_id: str
    original_confidence: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    outcome_adjustment: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    partial_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "insight_id": self.insight_id,
            "original_confidence": self.original_confidence,
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "outcome_adjustment": self.outcome_adjustment,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "partial_count": self.partial_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfidenceState":
        """Create from dictionary."""
        created_at_str = data.get("created_at", "")
        last_updated_str = data.get("last_updated", "")

        # Parse timestamps
        try:
            if created_at_str.endswith("Z"):
                created_at_str = created_at_str[:-1] + "+00:00"
            created_at = datetime.fromisoformat(created_at_str)
        except (ValueError, TypeError, AttributeError):
            created_at = datetime.now(timezone.utc)

        try:
            if last_updated_str.endswith("Z"):
                last_updated_str = last_updated_str[:-1] + "+00:00"
            last_updated = datetime.fromisoformat(last_updated_str)
        except (ValueError, TypeError, AttributeError):
            last_updated = datetime.now(timezone.utc)

        return cls(
            insight_id=data.get("insight_id", ""),
            original_confidence=data.get("original_confidence", 1.0),
            created_at=created_at,
            last_updated=last_updated,
            outcome_adjustment=data.get("outcome_adjustment", 0.0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            partial_count=data.get("partial_count", 0),
        )


class ConfidenceManager:
    """Manages confidence score lifecycle for insights.

    IMP-LOOP-034: This class implements confidence decay over time and
    updates based on task outcomes. It ensures that:
    - Old insights naturally lose relevance (time decay)
    - Successful tasks reinforce insight confidence
    - Failed tasks reduce insight confidence
    - Confidence is bounded between MIN_CONFIDENCE and MAX_CONFIDENCE

    The decay model uses exponential decay:
        decayed = original * 0.5^(age / half_life)

    This models the intuition that older insights may be less relevant
    while still allowing task outcomes to reinforce or reduce confidence.

    Attributes:
        _half_life: Decay half-life in days.
        _min_confidence: Minimum confidence floor.
        _states: Dictionary mapping insight_id to ConfidenceState.
        _memory_service: Optional MemoryService for persistence.
    """

    def __init__(
        self,
        decay_half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS,
        min_confidence: float = MIN_CONFIDENCE,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        """Initialize the ConfidenceManager.

        Args:
            decay_half_life_days: Half-life for exponential decay in days.
                After this period, confidence is halved. Default: 7 days.
            min_confidence: Minimum confidence floor. Insights never decay
                below this value. Default: 0.1.
            memory_service: Optional MemoryService for persisting confidence
                updates. If provided, updates are propagated to stored insights.
        """
        self._half_life = decay_half_life_days
        self._min_confidence = min_confidence
        self._memory_service = memory_service
        self._states: Dict[str, ConfidenceState] = {}

        logger.debug(
            "[IMP-LOOP-034] ConfidenceManager initialized "
            "(half_life=%.1f days, min_confidence=%.2f)",
            self._half_life,
            self._min_confidence,
        )

    def set_memory_service(self, memory_service: MemoryService) -> None:
        """Set or update the memory service for persistence.

        Args:
            memory_service: MemoryService instance for confidence updates.
        """
        self._memory_service = memory_service
        logger.debug("[IMP-LOOP-034] Memory service connected to ConfidenceManager")

    def calculate_decayed_confidence(
        self,
        original_confidence: float,
        created_at: datetime,
        now: Optional[datetime] = None,
    ) -> float:
        """Calculate confidence with exponential decay applied.

        IMP-LOOP-034: Applies exponential decay based on age since creation.
        The formula is: decayed = original * 0.5^(age_days / half_life_days)

        Args:
            original_confidence: The original confidence value (0.0-1.0).
            created_at: Timestamp when the insight was created.
            now: Current time for age calculation. Defaults to UTC now.

        Returns:
            Decayed confidence value, bounded by min_confidence floor.
        """
        now = now or datetime.now(timezone.utc)

        # Ensure both datetimes are timezone-aware
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Calculate age in days
        age_seconds = (now - created_at).total_seconds()
        age_days = age_seconds / 86400.0

        # Handle edge case of negative age (future timestamps)
        if age_days < 0:
            logger.warning(
                "[IMP-LOOP-034] Insight has future created_at timestamp, using original confidence"
            )
            return original_confidence

        # Apply exponential decay
        decay_factor = math.pow(0.5, age_days / self._half_life)
        decayed = original_confidence * decay_factor

        # Apply minimum floor
        result = max(decayed, self._min_confidence)

        logger.debug(
            "[IMP-LOOP-034] Calculated decayed confidence: %.3f -> %.3f "
            "(age=%.1f days, decay_factor=%.3f)",
            original_confidence,
            result,
            age_days,
            decay_factor,
        )

        return result

    def get_effective_confidence(
        self,
        insight_id: str,
        original_confidence: float = 1.0,
        created_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> float:
        """Get the effective confidence for an insight including decay and adjustments.

        IMP-LOOP-034: Combines time decay with outcome-based adjustments to
        compute the final effective confidence score.

        Args:
            insight_id: The insight identifier.
            original_confidence: Original confidence if not in state cache.
            created_at: Creation timestamp if not in state cache.
            now: Current time for decay calculation.

        Returns:
            Effective confidence score (0.0-1.0).
        """
        now = now or datetime.now(timezone.utc)

        # Check if we have tracked state for this insight
        if insight_id in self._states:
            state = self._states[insight_id]
            base_confidence = state.original_confidence
            created_at = state.created_at
            outcome_adjustment = state.outcome_adjustment
        else:
            base_confidence = original_confidence
            created_at = created_at or now
            outcome_adjustment = 0.0

        # Calculate time-decayed confidence
        decayed = self.calculate_decayed_confidence(base_confidence, created_at, now)

        # Apply outcome adjustments
        effective = decayed + outcome_adjustment

        # Bound to valid range
        effective = max(self._min_confidence, min(MAX_CONFIDENCE, effective))

        return effective

    def register_insight(
        self,
        insight_id: str,
        confidence: float = 1.0,
        created_at: Optional[datetime] = None,
    ) -> ConfidenceState:
        """Register an insight for confidence tracking.

        Args:
            insight_id: Unique identifier for the insight.
            confidence: Initial confidence score.
            created_at: Creation timestamp. Defaults to now.

        Returns:
            ConfidenceState for the registered insight.
        """
        created_at = created_at or datetime.now(timezone.utc)

        state = ConfidenceState(
            insight_id=insight_id,
            original_confidence=confidence,
            created_at=created_at,
            last_updated=datetime.now(timezone.utc),
        )

        self._states[insight_id] = state

        logger.debug(
            "[IMP-LOOP-034] Registered insight %s for confidence tracking (confidence=%.2f)",
            insight_id,
            confidence,
        )

        return state

    def update_confidence_from_outcome(
        self,
        insight_id: str,
        task_outcome: str,
        persist: bool = True,
    ) -> float:
        """Update confidence score based on task outcome.

        IMP-LOOP-034: Adjusts confidence based on whether the task generated
        from this insight succeeded, failed, or partially succeeded.

        - Success: Boost confidence by SUCCESS_CONFIDENCE_BOOST
        - Failure: Reduce confidence by FAILURE_CONFIDENCE_PENALTY
        - Partial: Small boost by PARTIAL_CONFIDENCE_ADJUSTMENT

        Args:
            insight_id: The insight that generated the task.
            task_outcome: Outcome of the task ('success', 'failure', 'partial').
            persist: If True, persist the update to memory service.

        Returns:
            Updated effective confidence score.
        """
        # Get or create state for this insight
        if insight_id not in self._states:
            self._states[insight_id] = ConfidenceState(
                insight_id=insight_id,
                original_confidence=1.0,
                created_at=datetime.now(timezone.utc),
            )

        state = self._states[insight_id]
        outcome_lower = task_outcome.lower()

        # Calculate adjustment based on outcome
        if outcome_lower == "success":
            adjustment = SUCCESS_CONFIDENCE_BOOST
            state.success_count += 1
        elif outcome_lower == "failure":
            adjustment = -FAILURE_CONFIDENCE_PENALTY
            state.failure_count += 1
        elif outcome_lower == "partial":
            adjustment = PARTIAL_CONFIDENCE_ADJUSTMENT
            state.partial_count += 1
        else:
            logger.warning(
                "[IMP-LOOP-034] Unknown task outcome '%s' for insight %s, no adjustment",
                task_outcome,
                insight_id,
            )
            return self.get_effective_confidence(insight_id)

        # Apply adjustment
        state.outcome_adjustment += adjustment
        state.last_updated = datetime.now(timezone.utc)

        # Calculate new effective confidence
        new_confidence = self.get_effective_confidence(insight_id)

        logger.info(
            "[IMP-LOOP-034] Updated confidence for insight %s after %s: "
            "adjustment=%.2f, effective=%.2f "
            "(success=%d, failure=%d, partial=%d)",
            insight_id,
            task_outcome,
            adjustment,
            new_confidence,
            state.success_count,
            state.failure_count,
            state.partial_count,
        )

        # Persist to memory service if requested
        if persist:
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
                "[IMP-LOOP-034] No memory service configured, skipping confidence persistence"
            )
            return False

        try:
            if hasattr(self._memory_service, "update_insight_confidence"):
                self._memory_service.update_insight_confidence(insight_id, confidence)
                logger.debug(
                    "[IMP-LOOP-034] Persisted confidence %.2f for insight %s to memory",
                    confidence,
                    insight_id,
                )
                return True
            else:
                logger.debug("[IMP-LOOP-034] Memory service does not support confidence updates")
                return False
        except Exception as e:
            logger.warning(
                "[IMP-LOOP-034] Failed to persist confidence for insight %s: %s",
                insight_id,
                e,
            )
            return False

    def apply_decay_to_insights(
        self,
        insights: list,
        confidence_field: str = "confidence",
        created_at_field: str = "created_at",
        now: Optional[datetime] = None,
    ) -> list:
        """Apply decay to a list of insights in-place.

        IMP-LOOP-034: Convenience method to apply decay to a batch of insights
        before processing. Modifies the confidence field of each insight.

        Args:
            insights: List of insight dicts or objects.
            confidence_field: Name of the confidence field.
            created_at_field: Name of the created_at timestamp field.
            now: Current time for decay calculation.

        Returns:
            The same list with decayed confidence values.
        """
        now = now or datetime.now(timezone.utc)

        for insight in insights:
            # Get current values
            if isinstance(insight, dict):
                original_conf = insight.get(confidence_field, 1.0)
                created_at_str = insight.get(created_at_field)
            else:
                original_conf = getattr(insight, confidence_field, 1.0)
                created_at_str = getattr(insight, created_at_field, None)

            # Parse created_at timestamp
            if created_at_str is None:
                continue

            if isinstance(created_at_str, datetime):
                created_at = created_at_str
            else:
                try:
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    created_at = datetime.fromisoformat(created_at_str)
                except (ValueError, TypeError, AttributeError):
                    continue

            # Calculate decayed confidence
            decayed = self.calculate_decayed_confidence(original_conf, created_at, now)

            # Update the insight
            if isinstance(insight, dict):
                insight[confidence_field] = decayed
            else:
                setattr(insight, confidence_field, decayed)

        return insights

    def get_confidence_state(self, insight_id: str) -> Optional[ConfidenceState]:
        """Get the confidence state for an insight.

        Args:
            insight_id: The insight to query.

        Returns:
            ConfidenceState or None if not tracked.
        """
        return self._states.get(insight_id)

    def get_all_states(self) -> Dict[str, ConfidenceState]:
        """Get all tracked confidence states.

        Returns:
            Dictionary mapping insight_id to ConfidenceState.
        """
        return self._states.copy()

    def reset_state(self, insight_id: str) -> bool:
        """Reset the confidence state for an insight.

        Args:
            insight_id: The insight to reset.

        Returns:
            True if state was reset, False if insight was not tracked.
        """
        if insight_id in self._states:
            del self._states[insight_id]
            logger.debug("[IMP-LOOP-034] Reset confidence state for insight %s", insight_id)
            return True
        return False

    def clear_all_states(self) -> int:
        """Clear all tracked confidence states.

        Returns:
            Number of states cleared.
        """
        count = len(self._states)
        self._states.clear()
        logger.info("[IMP-LOOP-034] Cleared %d confidence states", count)
        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about confidence tracking.

        Returns:
            Dictionary containing tracking statistics.
        """
        total_insights = len(self._states)
        total_successes = sum(s.success_count for s in self._states.values())
        total_failures = sum(s.failure_count for s in self._states.values())
        total_partials = sum(s.partial_count for s in self._states.values())

        avg_original_confidence = (
            sum(s.original_confidence for s in self._states.values()) / total_insights
            if total_insights > 0
            else 0.0
        )

        return {
            "tracked_insights": total_insights,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "total_partials": total_partials,
            "avg_original_confidence": avg_original_confidence,
            "half_life_days": self._half_life,
            "min_confidence": self._min_confidence,
        }
