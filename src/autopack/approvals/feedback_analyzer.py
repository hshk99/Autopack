"""Human approval feedback analysis (IMP-LOOP-014).

Captures structured feedback when humans approve, reject, or modify
generated tasks. Feeds patterns back to task generation to improve
future recommendations.

This module provides:
- HumanAction enum for categorizing user decisions
- ApprovalFeedback dataclass for structured feedback storage
- ApprovalFeedbackAnalyzer for pattern analysis and learning
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HumanAction(str, Enum):
    """Actions a human can take on a task.

    APPROVE: Task accepted as-is
    REJECT: Task declined, not executed
    MODIFY: Task modified before execution
    """

    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"


@dataclass
class ApprovalFeedback:
    """Structured feedback from human approval decision.

    Attributes:
        task_id: Unique identifier for the task
        action: Human action taken (approve/reject/modify)
        feedback_text: Optional free-text feedback
        reasoning: Structured reasoning with category keys
        recorded_at: Timestamp when feedback was recorded
        task_type: Optional type/category of the task
        priority_score: Original priority score of the task
        modifications: For MODIFY actions, what was changed
    """

    task_id: str
    action: HumanAction
    feedback_text: Optional[str]
    reasoning: Dict[str, str]
    recorded_at: datetime
    task_type: Optional[str] = None
    priority_score: Optional[float] = None
    modifications: Optional[Dict[str, Any]] = None


@dataclass
class RejectionPattern:
    """Pattern identified from rejection feedback.

    Attributes:
        pattern_type: Category of rejection pattern
        description: Human-readable description
        occurrence_count: Number of times this pattern occurred
        example_task_ids: Sample task IDs that match this pattern
        suggested_adjustment: Recommended adjustment to task generation
        confidence: Confidence score (0.0-1.0) based on sample size
    """

    pattern_type: str
    description: str
    occurrence_count: int
    example_task_ids: List[str]
    suggested_adjustment: str
    confidence: float


@dataclass
class PriorityWeightUpdate:
    """Update to priority engine weights based on feedback.

    Attributes:
        weight_name: Name of the weight to adjust
        current_value: Current weight value
        suggested_value: Recommended new value
        adjustment_reason: Why this adjustment is recommended
        supporting_patterns: Patterns that support this change
    """

    weight_name: str
    current_value: float
    suggested_value: float
    adjustment_reason: str
    supporting_patterns: List[str]


class ApprovalFeedbackAnalyzer:
    """Analyzes human approval feedback to improve task generation.

    IMP-LOOP-014: Provides structured feedback capture and pattern analysis
    to create a feedback loop for continuous improvement of task generation.

    Example usage:
        ```python
        analyzer = ApprovalFeedbackAnalyzer()

        # Capture feedback when human rejects a task
        feedback = analyzer.capture_feedback(
            task_id="task-001",
            action=HumanAction.REJECT,
            feedback_text="Task is too broad",
            reasoning={"scope": "too_large", "effort": "excessive"}
        )

        # Analyze patterns across all feedback
        patterns = analyzer.analyze_rejection_patterns()

        # Update priority engine based on patterns
        analyzer.update_priority_engine_weights(patterns)
        ```
    """

    def __init__(
        self,
        max_feedback_history: int = 1000,
        min_pattern_occurrences: int = 3,
        weight_adjustment_factor: float = 0.1,
    ):
        """Initialize the ApprovalFeedbackAnalyzer.

        Args:
            max_feedback_history: Maximum feedback entries to retain
            min_pattern_occurrences: Minimum occurrences to identify a pattern
            weight_adjustment_factor: Factor for weight adjustments (0.0-1.0)
        """
        self._feedback_history: List[ApprovalFeedback] = []
        self._max_history = max_feedback_history
        self._min_pattern_occurrences = min_pattern_occurrences
        self._weight_adjustment_factor = weight_adjustment_factor

        # Track current priority weights for adjustments
        self._priority_weights: Dict[str, float] = {
            "impact": 1.0,
            "urgency": 1.0,
            "effort": 1.0,
            "risk": 1.0,
            "dependencies": 1.0,
        }

        # Stats for monitoring
        self._stats = {
            "total_feedback": 0,
            "approvals": 0,
            "rejections": 0,
            "modifications": 0,
            "patterns_identified": 0,
            "weight_updates_applied": 0,
        }

        logger.info(
            f"[IMP-LOOP-014] ApprovalFeedbackAnalyzer initialized "
            f"(max_history={max_feedback_history}, min_pattern={min_pattern_occurrences})"
        )

    def capture_feedback(
        self,
        task_id: str,
        action: HumanAction,
        feedback_text: Optional[str] = None,
        reasoning: Optional[Dict[str, str]] = None,
        task_type: Optional[str] = None,
        priority_score: Optional[float] = None,
        modifications: Optional[Dict[str, Any]] = None,
    ) -> ApprovalFeedback:
        """Store structured feedback from human action.

        Args:
            task_id: Unique identifier for the task
            action: Human action taken
            feedback_text: Optional free-text feedback
            reasoning: Structured reasoning dictionary
            task_type: Optional task type/category
            priority_score: Original priority score
            modifications: For MODIFY actions, what was changed

        Returns:
            ApprovalFeedback instance with recorded data
        """
        feedback = ApprovalFeedback(
            task_id=task_id,
            action=action,
            feedback_text=feedback_text,
            reasoning=reasoning or {},
            recorded_at=datetime.now(timezone.utc),
            task_type=task_type,
            priority_score=priority_score,
            modifications=modifications,
        )

        # Add to history with size limit
        self._feedback_history.append(feedback)
        if len(self._feedback_history) > self._max_history:
            self._feedback_history = self._feedback_history[-self._max_history :]

        # Update stats
        self._stats["total_feedback"] += 1
        if action == HumanAction.APPROVE:
            self._stats["approvals"] += 1
        elif action == HumanAction.REJECT:
            self._stats["rejections"] += 1
        elif action == HumanAction.MODIFY:
            self._stats["modifications"] += 1

        logger.info(
            f"[IMP-LOOP-014] Captured feedback for task {task_id}: "
            f"action={action.value}, has_reasoning={bool(reasoning)}"
        )

        return feedback

    def analyze_rejection_patterns(self) -> List[RejectionPattern]:
        """Find patterns in why tasks are rejected.

        Analyzes the feedback history to identify common rejection reasons
        and suggests adjustments to improve task generation.

        Returns:
            List of RejectionPattern instances sorted by occurrence count
        """
        # Filter to rejections only
        rejections = [fb for fb in self._feedback_history if fb.action == HumanAction.REJECT]

        if not rejections:
            logger.debug("[IMP-LOOP-014] No rejections to analyze")
            return []

        # Collect reasoning categories
        reason_counter: Counter = Counter()
        reason_tasks: Dict[str, List[str]] = {}
        reason_texts: Dict[str, List[str]] = {}

        for fb in rejections:
            for category, value in fb.reasoning.items():
                key = f"{category}:{value}"
                reason_counter[key] += 1
                if key not in reason_tasks:
                    reason_tasks[key] = []
                    reason_texts[key] = []
                reason_tasks[key].append(fb.task_id)
                if fb.feedback_text:
                    reason_texts[key].append(fb.feedback_text)

        # Build patterns from significant occurrences
        patterns: List[RejectionPattern] = []
        total_rejections = len(rejections)

        for reason_key, count in reason_counter.items():
            if count >= self._min_pattern_occurrences:
                category, value = reason_key.split(":", 1)
                confidence = min(count / total_rejections, 1.0)

                pattern = RejectionPattern(
                    pattern_type=category,
                    description=self._generate_pattern_description(category, value),
                    occurrence_count=count,
                    example_task_ids=reason_tasks[reason_key][:5],
                    suggested_adjustment=self._suggest_adjustment(category, value),
                    confidence=confidence,
                )
                patterns.append(pattern)

        # Sort by occurrence count (descending)
        patterns.sort(key=lambda p: p.occurrence_count, reverse=True)

        self._stats["patterns_identified"] = len(patterns)
        logger.info(
            f"[IMP-LOOP-014] Identified {len(patterns)} rejection patterns "
            f"from {len(rejections)} rejections"
        )

        return patterns

    def analyze_modification_patterns(self) -> List[Dict[str, Any]]:
        """Find patterns in how tasks are modified.

        Analyzes modifications to understand what aspects of tasks
        humans commonly adjust.

        Returns:
            List of modification pattern dictionaries
        """
        modifications = [fb for fb in self._feedback_history if fb.action == HumanAction.MODIFY]

        if not modifications:
            return []

        # Track which fields are commonly modified
        field_counter: Counter = Counter()
        for fb in modifications:
            if fb.modifications:
                for field_name in fb.modifications.keys():
                    field_counter[field_name] += 1

        patterns = []
        for field_name, count in field_counter.most_common():
            if count >= self._min_pattern_occurrences:
                patterns.append(
                    {
                        "field": field_name,
                        "modification_count": count,
                        "percentage": count / len(modifications) * 100,
                        "suggestion": f"Review {field_name} generation logic",
                    }
                )

        logger.info(
            f"[IMP-LOOP-014] Identified {len(patterns)} modification patterns "
            f"from {len(modifications)} modifications"
        )

        return patterns

    def update_priority_engine_weights(
        self, patterns: List[RejectionPattern]
    ) -> List[PriorityWeightUpdate]:
        """Update task generation weights based on feedback patterns.

        Maps rejection patterns to priority weight adjustments to improve
        future task generation accuracy.

        Args:
            patterns: List of rejection patterns from analyze_rejection_patterns

        Returns:
            List of weight updates that were applied
        """
        updates: List[PriorityWeightUpdate] = []

        for pattern in patterns:
            weight_name = self._map_pattern_to_weight(pattern.pattern_type)
            if weight_name and weight_name in self._priority_weights:
                current_value = self._priority_weights[weight_name]

                # Calculate adjustment based on confidence and occurrence
                adjustment = (
                    self._weight_adjustment_factor
                    * pattern.confidence
                    * (pattern.occurrence_count / self._min_pattern_occurrences)
                )

                # Determine direction based on pattern type
                if self._should_decrease_weight(pattern.pattern_type):
                    suggested_value = max(0.1, current_value - adjustment)
                else:
                    suggested_value = min(2.0, current_value + adjustment)

                update = PriorityWeightUpdate(
                    weight_name=weight_name,
                    current_value=current_value,
                    suggested_value=suggested_value,
                    adjustment_reason=pattern.suggested_adjustment,
                    supporting_patterns=[pattern.pattern_type],
                )
                updates.append(update)

                # Apply the update
                self._priority_weights[weight_name] = suggested_value
                self._stats["weight_updates_applied"] += 1

                logger.info(
                    f"[IMP-LOOP-014] Updated weight {weight_name}: "
                    f"{current_value:.3f} -> {suggested_value:.3f} "
                    f"(reason: {pattern.pattern_type})"
                )

        return updates

    def get_approval_rate(self, task_type: Optional[str] = None) -> float:
        """Calculate approval rate, optionally filtered by task type.

        Args:
            task_type: Optional task type to filter by

        Returns:
            Approval rate as float (0.0-1.0), or 0.0 if no data
        """
        if task_type:
            relevant = [fb for fb in self._feedback_history if fb.task_type == task_type]
        else:
            relevant = self._feedback_history

        if not relevant:
            return 0.0

        approvals = sum(1 for fb in relevant if fb.action == HumanAction.APPROVE)
        return approvals / len(relevant)

    def get_feedback_summary(self) -> Dict[str, Any]:
        """Get summary statistics of feedback collected.

        Returns:
            Dictionary with feedback statistics
        """
        total = len(self._feedback_history)
        if total == 0:
            return {
                "total_feedback": 0,
                "approval_rate": 0.0,
                "rejection_rate": 0.0,
                "modification_rate": 0.0,
                "patterns_identified": 0,
            }

        approvals = sum(1 for fb in self._feedback_history if fb.action == HumanAction.APPROVE)
        rejections = sum(1 for fb in self._feedback_history if fb.action == HumanAction.REJECT)
        modifications = sum(1 for fb in self._feedback_history if fb.action == HumanAction.MODIFY)

        return {
            "total_feedback": total,
            "approval_rate": approvals / total,
            "rejection_rate": rejections / total,
            "modification_rate": modifications / total,
            "patterns_identified": self._stats["patterns_identified"],
            "weight_updates_applied": self._stats["weight_updates_applied"],
        }

    def get_priority_weights(self) -> Dict[str, float]:
        """Get current priority weights.

        Returns:
            Dictionary of weight names to current values
        """
        return dict(self._priority_weights)

    def reset_weights(self) -> None:
        """Reset priority weights to default values."""
        self._priority_weights = {
            "impact": 1.0,
            "urgency": 1.0,
            "effort": 1.0,
            "risk": 1.0,
            "dependencies": 1.0,
        }
        logger.info("[IMP-LOOP-014] Priority weights reset to defaults")

    def clear_history(self) -> int:
        """Clear feedback history.

        Returns:
            Number of feedback entries cleared
        """
        count = len(self._feedback_history)
        self._feedback_history.clear()
        logger.info(f"[IMP-LOOP-014] Cleared {count} feedback entries")
        return count

    def _generate_pattern_description(self, category: str, value: str) -> str:
        """Generate human-readable description for a pattern.

        Args:
            category: Pattern category
            value: Pattern value

        Returns:
            Human-readable description
        """
        descriptions = {
            "scope": {
                "too_large": "Tasks have scope that is too broad for single execution",
                "too_small": "Tasks are too granular and should be combined",
                "unclear": "Task scope is not clearly defined",
            },
            "effort": {
                "excessive": "Estimated effort exceeds acceptable threshold",
                "underestimated": "Effort was underestimated relative to complexity",
            },
            "priority": {
                "too_high": "Task priority was overestimated",
                "too_low": "Task priority was underestimated",
                "wrong_order": "Task ordering does not match business priorities",
            },
            "relevance": {
                "outdated": "Task addresses already-resolved issues",
                "not_applicable": "Task is not relevant to current project state",
            },
            "risk": {
                "too_risky": "Task carries unacceptable risk level",
                "understated": "Risk level was not adequately communicated",
            },
        }

        return descriptions.get(category, {}).get(value, f"Pattern: {category} = {value}")

    def _suggest_adjustment(self, category: str, value: str) -> str:
        """Suggest adjustment based on pattern.

        Args:
            category: Pattern category
            value: Pattern value

        Returns:
            Suggested adjustment string
        """
        adjustments = {
            "scope": {
                "too_large": "Reduce task scope threshold or enable automatic splitting",
                "too_small": "Increase minimum task scope or enable batching",
                "unclear": "Improve task description generation",
            },
            "effort": {
                "excessive": "Lower effort threshold for task acceptance",
                "underestimated": "Calibrate effort estimation model",
            },
            "priority": {
                "too_high": "Reduce impact weight in priority calculation",
                "too_low": "Increase urgency weight in priority calculation",
                "wrong_order": "Review dependency handling in priority engine",
            },
            "relevance": {
                "outdated": "Improve freshness checks before task generation",
                "not_applicable": "Enhance context filtering in task selection",
            },
            "risk": {
                "too_risky": "Increase risk weight in task filtering",
                "understated": "Improve risk assessment visibility",
            },
        }

        return adjustments.get(category, {}).get(
            value, f"Review {category} handling in task generation"
        )

    def _map_pattern_to_weight(self, pattern_type: str) -> Optional[str]:
        """Map pattern type to priority weight name.

        Args:
            pattern_type: Pattern type from rejection analysis

        Returns:
            Weight name or None if no mapping
        """
        mapping = {
            "scope": "effort",
            "effort": "effort",
            "priority": "urgency",
            "relevance": "impact",
            "risk": "risk",
            "dependencies": "dependencies",
        }
        return mapping.get(pattern_type)

    def _should_decrease_weight(self, pattern_type: str) -> bool:
        """Determine if pattern indicates weight should decrease.

        Args:
            pattern_type: Pattern type

        Returns:
            True if weight should decrease, False if increase
        """
        # Patterns that indicate over-weighting (should decrease)
        decrease_patterns = {"scope", "effort", "risk"}
        return pattern_type in decrease_patterns
