"""Data-Driven Task Priority Engine.

Prioritizes tasks based on historical learnings:
- Past success rate by category/complexity
- Blocking pattern detection (skip likely blockers)
- Dependency chain optimization

This module bridges the memory->task_generation link in the self-improvement loop
by using historical outcomes to inform what tasks to work on next.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory.learning_db import LearningDatabase

logger = logging.getLogger(__name__)

# Priority levels and their base scores
PRIORITY_BASE_SCORES: dict[str, float] = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}

# Category patterns for extracting category from improvement IDs
CATEGORY_PATTERNS: dict[str, str] = {
    "TEL": "telemetry",
    "MEM": "memory",
    "TGN": "task_generation",
    "GEN": "generation",
    "LOG": "logging",
    "API": "api",
    "CI": "ci",
    "TEST": "testing",
    "DOC": "documentation",
    "PERF": "performance",
    "SEC": "security",
    "FIX": "bugfix",
}

# Complexity indicators that may affect success likelihood
COMPLEXITY_KEYWORDS: dict[str, float] = {
    "refactor": 0.85,  # Refactoring is usually successful
    "add": 0.90,  # Adding new features is straightforward
    "fix": 0.80,  # Bug fixes can be tricky
    "migrate": 0.60,  # Migrations are complex
    "rewrite": 0.50,  # Rewrites have high risk
    "integrate": 0.70,  # Integration work varies
    "optimize": 0.75,  # Optimization is moderately risky
    "remove": 0.95,  # Removal is usually simple
    "update": 0.85,  # Updates are usually safe
}


class PriorityEngine:
    """Data-driven task priority engine.

    Uses historical learning data to prioritize improvements based on:
    - Category success rates (e.g., "memory" improvements succeed 80% of the time)
    - Known blocking patterns (e.g., "dependency conflict" blocks 30% of tasks)
    - Complexity estimation from improvement descriptions
    - Recent trend analysis

    Attributes:
        learning_db: The learning database containing historical outcomes.
    """

    # Weight factors for priority calculation
    CATEGORY_SUCCESS_WEIGHT = 0.35
    BLOCKING_RISK_WEIGHT = 0.25
    PRIORITY_LEVEL_WEIGHT = 0.25
    COMPLEXITY_WEIGHT = 0.15

    # Thresholds
    HIGH_BLOCKING_RISK_THRESHOLD = 0.3
    LOW_SUCCESS_RATE_THRESHOLD = 0.4

    def __init__(self, learning_db: LearningDatabase) -> None:
        """Initialize the PriorityEngine.

        Args:
            learning_db: The learning database containing historical outcomes.
        """
        self.learning_db = learning_db
        self._patterns_cache: dict[str, Any] | None = None

    def _get_cached_patterns(self) -> dict[str, Any]:
        """Get historical patterns, caching for performance."""
        if self._patterns_cache is None:
            self._patterns_cache = self.learning_db.get_historical_patterns()
        return self._patterns_cache

    def clear_cache(self) -> None:
        """Clear the cached patterns to force reload."""
        self._patterns_cache = None

    def _extract_category(self, improvement: dict[str, Any]) -> str:
        """Extract the category from an improvement record.

        Args:
            improvement: The improvement record.

        Returns:
            Category string (e.g., "telemetry", "memory").
        """
        # First check for explicit category field
        category = improvement.get("category")
        if category:
            return category.lower()

        # Try to extract from improvement ID (e.g., "IMP-TEL-001" -> "telemetry")
        imp_id = improvement.get("imp_id", improvement.get("id", ""))
        if imp_id:
            # Match patterns like IMP-TEL-001, IMP-MEM-002
            match = re.search(r"IMP-([A-Z]+)-\d+", str(imp_id).upper())
            if match:
                code = match.group(1)
                return CATEGORY_PATTERNS.get(code, code.lower())

        # Fallback to "general"
        return "general"

    def _extract_priority_level(self, improvement: dict[str, Any]) -> str:
        """Extract the priority level from an improvement record.

        Args:
            improvement: The improvement record.

        Returns:
            Priority level string (e.g., "critical", "high", "medium", "low").
        """
        priority = improvement.get("priority", "medium")
        priority_lower = str(priority).lower()

        if priority_lower in PRIORITY_BASE_SCORES:
            return priority_lower

        return "medium"

    def _estimate_complexity(self, improvement: dict[str, Any]) -> float:
        """Estimate complexity based on improvement description.

        Args:
            improvement: The improvement record.

        Returns:
            Complexity factor between 0.0 (very complex) and 1.0 (simple).
            Higher values indicate simpler tasks with higher success likelihood.
        """
        # Gather text fields to analyze
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("problem", "")),
            str(improvement.get("implementation", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        if not combined_text.strip():
            return 0.75  # Default to moderate complexity

        # Check for complexity keywords
        complexity_scores: list[float] = []
        for keyword, score in COMPLEXITY_KEYWORDS.items():
            if keyword in combined_text:
                complexity_scores.append(score)

        if complexity_scores:
            # Use average of all matching keywords
            return sum(complexity_scores) / len(complexity_scores)

        return 0.75  # Default

    def _calculate_blocking_risk(
        self, improvement: dict[str, Any], likely_blockers: list[dict[str, Any]]
    ) -> float:
        """Calculate the risk of blocking based on historical patterns.

        Args:
            improvement: The improvement record.
            likely_blockers: List of likely blocker records from learning DB.

        Returns:
            Blocking risk between 0.0 (no risk) and 1.0 (high risk).
        """
        if not likely_blockers:
            return 0.0

        # Check if any likely blockers match this improvement's characteristics
        category = self._extract_category(improvement)
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("files_to_modify", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        total_risk = 0.0
        matched_blockers = 0

        for blocker in likely_blockers:
            reason = str(blocker.get("reason", "")).lower()
            frequency = blocker.get("frequency", 1)
            likelihood = blocker.get("likelihood", "medium")

            # Check if this blocker reason might apply
            reason_applies = False

            # Check for keyword matches
            if any(word in combined_text for word in reason.split() if len(word) > 3):
                reason_applies = True

            # Check for category-specific blockers
            if category in reason:
                reason_applies = True

            if reason_applies:
                matched_blockers += 1
                # Weight by frequency and likelihood
                likelihood_weight = 0.8 if likelihood == "high" else 0.5
                total_risk += min(1.0, (frequency / 10) * likelihood_weight)

        if matched_blockers == 0:
            return 0.0

        # Normalize and cap at 1.0
        return min(1.0, total_risk / matched_blockers)

    def calculate_priority_score(self, improvement: dict[str, Any]) -> float:
        """Score improvement based on historical success likelihood.

        The score combines multiple factors:
        - Category success rate: How often improvements in this category succeed
        - Blocking risk: Likelihood of hitting known blockers
        - Priority level: The assigned priority (critical, high, medium, low)
        - Complexity estimate: Estimated complexity from description

        Args:
            improvement: The improvement record to score. Expected keys:
                - imp_id or id: Improvement identifier
                - priority: Priority level (critical, high, medium, low)
                - category: Optional explicit category
                - title, description: Text for complexity estimation

        Returns:
            Priority score between 0.0 and 1.0, where higher is better priority.
        """
        category = self._extract_category(improvement)
        priority_level = self._extract_priority_level(improvement)

        # Get category success rate
        category_success_rate = self.learning_db.get_success_rate(category)
        if category_success_rate == 0.0:
            # No historical data - use default
            category_success_rate = 0.5

        # Get likely blockers for this category
        likely_blockers = self.learning_db.get_likely_blockers(category)
        blocking_risk = self._calculate_blocking_risk(improvement, likely_blockers)

        # Get priority level base score
        priority_base = PRIORITY_BASE_SCORES.get(priority_level, 0.5)

        # Estimate complexity
        complexity_factor = self._estimate_complexity(improvement)

        # Calculate weighted score
        # Higher category success rate -> higher score
        # Lower blocking risk -> higher score (invert the risk)
        # Higher priority level -> higher score
        # Higher complexity factor (simpler tasks) -> higher score
        score = (
            (category_success_rate * self.CATEGORY_SUCCESS_WEIGHT)
            + ((1.0 - blocking_risk) * self.BLOCKING_RISK_WEIGHT)
            + (priority_base * self.PRIORITY_LEVEL_WEIGHT)
            + (complexity_factor * self.COMPLEXITY_WEIGHT)
        )

        logger.debug(
            "Priority score for %s: %.3f (category=%.2f, block_risk=%.2f, "
            "priority=%.2f, complexity=%.2f)",
            improvement.get("imp_id", improvement.get("id", "unknown")),
            score,
            category_success_rate,
            blocking_risk,
            priority_base,
            complexity_factor,
        )

        return round(score, 3)

    def rank_improvements(
        self,
        improvements: list[dict[str, Any]],
        include_scores: bool = False,
    ) -> list[dict[str, Any]]:
        """Return improvements sorted by data-driven priority.

        Args:
            improvements: List of improvement records to rank.
            include_scores: If True, add 'priority_score' field to each record.

        Returns:
            List of improvements sorted by priority score (highest first).
        """
        if not improvements:
            return []

        # Calculate scores and pair with improvements
        scored_improvements: list[tuple[float, dict[str, Any]]] = []

        for imp in improvements:
            score = self.calculate_priority_score(imp)
            if include_scores:
                imp = dict(imp)  # Copy to avoid mutating original
                imp["priority_score"] = score
            scored_improvements.append((score, imp))

        # Sort by score descending
        scored_improvements.sort(key=lambda x: x[0], reverse=True)

        ranked = [imp for _, imp in scored_improvements]

        logger.info(
            "Ranked %d improvements by data-driven priority",
            len(ranked),
        )

        return ranked

    def detect_likely_blockers(self, improvement: dict[str, Any]) -> list[str]:
        """Predict what might block this improvement.

        Analyzes the improvement against historical blocking patterns
        to identify potential blockers before starting work.

        Args:
            improvement: The improvement record to analyze.

        Returns:
            List of likely blocker descriptions.
        """
        category = self._extract_category(improvement)
        likely_blockers = self.learning_db.get_likely_blockers(category)

        if not likely_blockers:
            return []

        # Get improvement text for matching
        text_fields = [
            str(improvement.get("title", "")),
            str(improvement.get("description", "")),
            str(improvement.get("problem", "")),
            str(improvement.get("files_to_modify", "")),
        ]
        combined_text = " ".join(text_fields).lower()

        detected_blockers: list[str] = []

        for blocker in likely_blockers:
            reason = str(blocker.get("reason", ""))
            reason_lower = reason.lower()

            # Check for keyword matches
            keywords = [word for word in reason_lower.split() if len(word) > 3]
            matches = sum(1 for kw in keywords if kw in combined_text)

            # If enough keywords match, or category-specific blocker
            if matches >= 2 or category in reason_lower:
                frequency = blocker.get("frequency", 1)
                likelihood = blocker.get("likelihood", "medium")
                detected_blockers.append(
                    f"{reason} (frequency: {frequency}, likelihood: {likelihood})"
                )

        logger.debug(
            "Detected %d likely blockers for %s",
            len(detected_blockers),
            improvement.get("imp_id", improvement.get("id", "unknown")),
        )

        return detected_blockers

    def get_priority_summary(
        self,
        improvements: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a summary of priority analysis for a set of improvements.

        Args:
            improvements: List of improvement records to analyze.

        Returns:
            Summary dictionary containing:
            - total_improvements: Total count
            - by_priority_level: Counts by priority level
            - by_category: Counts and avg scores by category
            - high_risk_items: Improvements with high blocking risk
            - recommended_order: Top 5 recommended improvements to work on
        """
        if not improvements:
            return {
                "total_improvements": 0,
                "by_priority_level": {},
                "by_category": {},
                "high_risk_items": [],
                "recommended_order": [],
            }

        by_priority: dict[str, int] = {}
        by_category: dict[str, dict[str, Any]] = {}
        high_risk_items: list[dict[str, Any]] = []

        for imp in improvements:
            # Count by priority level
            priority_level = self._extract_priority_level(imp)
            by_priority[priority_level] = by_priority.get(priority_level, 0) + 1

            # Analyze by category
            category = self._extract_category(imp)
            if category not in by_category:
                by_category[category] = {"count": 0, "scores": []}

            score = self.calculate_priority_score(imp)
            by_category[category]["count"] += 1
            by_category[category]["scores"].append(score)

            # Check for high blocking risk
            likely_blockers = self.learning_db.get_likely_blockers(category)
            blocking_risk = self._calculate_blocking_risk(imp, likely_blockers)
            if blocking_risk >= self.HIGH_BLOCKING_RISK_THRESHOLD:
                high_risk_items.append(
                    {
                        "imp_id": imp.get("imp_id", imp.get("id", "unknown")),
                        "blocking_risk": round(blocking_risk, 3),
                        "likely_blockers": self.detect_likely_blockers(imp)[:3],
                    }
                )

        # Calculate average scores by category
        for category, data in by_category.items():
            scores = data["scores"]
            data["avg_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
            del data["scores"]  # Remove raw scores from output

        # Get recommended order (top 5)
        ranked = self.rank_improvements(improvements, include_scores=True)
        recommended_order = [
            {
                "imp_id": imp.get("imp_id", imp.get("id", "unknown")),
                "priority_score": imp.get("priority_score", 0.0),
                "priority_level": self._extract_priority_level(imp),
                "category": self._extract_category(imp),
            }
            for imp in ranked[:5]
        ]

        return {
            "total_improvements": len(improvements),
            "by_priority_level": by_priority,
            "by_category": by_category,
            "high_risk_items": high_risk_items,
            "recommended_order": recommended_order,
        }
