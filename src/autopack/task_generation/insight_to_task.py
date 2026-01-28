"""Insight-to-Task Generator.

Automates the discovery process by generating improvement
suggestions from telemetry insights:
- Detects operational anomalies
- Creates structured IMP entries
- Prioritizes based on impact estimate
- Adjusts confidence based on historical success rates (IMP-LOOP-019)

This module bridges the telemetry->task_generation link in the self-improvement
loop by converting detected patterns into actionable improvement suggestions.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer
    from autopack.telemetry.analyzer import TaskEffectivenessStats

logger = logging.getLogger(__name__)

# Impact thresholds for classification
CRITICAL_HEALTH_THRESHOLD = 0.5  # Health below 50% is critical
HIGH_IMPACT_THRESHOLD = 0.7  # Health below 70% is high impact
MEDIUM_IMPACT_THRESHOLD = 0.85  # Health below 85% is medium impact

# Escalation rate thresholds
CRITICAL_ESCALATION_RATE = 0.5  # 50% escalation rate is critical
HIGH_ESCALATION_RATE = 0.3  # 30% escalation rate is high

# Flakiness thresholds
CRITICAL_FLAKINESS = 0.7  # 70% flakiness score is critical
HIGH_FLAKINESS = 0.5  # 50% flakiness score is high

# Category mappings for IMP IDs
INSIGHT_TO_CATEGORY = {
    "slot_reliability": "SLT",
    "nudge_effectiveness": "NDG",
    "flaky_tests": "TST",
    "escalation_patterns": "ESC",
    "timing_analysis": "TMG",
}


class InsightToTaskGenerator:
    """Generates improvement suggestions from telemetry insights.

    This class takes a TelemetryAnalyzer instance and converts its insights
    into structured IMP (improvement) entries that can be added to the
    improvement backlog.

    Attributes:
        analyzer: TelemetryAnalyzer instance for generating insights.
        effectiveness_stats: Optional task effectiveness stats for feedback
            closure (IMP-LOOP-019).
    """

    def __init__(
        self,
        analyzer: TelemetryAnalyzer,
        effectiveness_stats: Optional[TaskEffectivenessStats] = None,
    ) -> None:
        """Initialize the InsightToTaskGenerator.

        Args:
            analyzer: TelemetryAnalyzer instance to use for insight generation.
            effectiveness_stats: Optional task effectiveness stats for adjusting
                insight confidence based on historical success rates (IMP-LOOP-019).
        """
        self.analyzer = analyzer
        self._imp_counter: Counter[str] = Counter()
        self._effectiveness_stats = effectiveness_stats

    def set_effectiveness_stats(self, stats: TaskEffectivenessStats) -> None:
        """Set or update task effectiveness stats (IMP-LOOP-019).

        Call this method to provide updated effectiveness data from
        task completion telemetry. This enables adjusting insight
        confidence based on historical success rates.

        Args:
            stats: TaskEffectivenessStats from TelemetryAnalyzer.
        """
        self._effectiveness_stats = stats
        logger.debug(
            "[IMP-LOOP-019] Updated effectiveness stats for insight generator: "
            "success_rate=%.1f%%, by_type=%d categories",
            stats.success_rate * 100,
            len(stats.effectiveness_by_type),
        )

    def _generate_imp_id(self, category: str) -> str:
        """Generate a unique IMP ID for a category.

        Args:
            category: The category code (e.g., "SLT", "NDG", "TST").

        Returns:
            A unique IMP ID in format IMP-{CATEGORY}-{NUMBER}.
        """
        self._imp_counter[category] += 1
        return f"IMP-{category}-{self._imp_counter[category]:03d}"

    def get_success_rate_for_insight_type(self, insight_source: str) -> float:
        """Get historical success rate for an insight type (IMP-LOOP-019).

        Looks up the success rate for tasks generated from similar insight
        types to adjust confidence in new task generation.

        Args:
            insight_source: The source of the insight (e.g., "slot_reliability").

        Returns:
            Historical success rate between 0.0 and 1.0, or 1.0 if no data.
        """
        if self._effectiveness_stats is None:
            return 1.0

        # Map insight sources to task type categories
        source_to_type = {
            "slot_reliability": "slot_reliability",
            "nudge_effectiveness": "nudge_effectiveness",
            "flaky_tests": "flaky_tests",
            "escalation_patterns": "escalation_patterns",
            "timing_analysis": "timing_analysis",
            "cost_sink": "cost_sink",
            "failure_mode": "failure_mode",
            "retry_cause": "retry_cause",
        }

        task_type = source_to_type.get(insight_source, insight_source)

        # Check if we have effectiveness data for this type
        type_stats = self._effectiveness_stats.effectiveness_by_type.get(task_type, {})
        success_rate = type_stats.get("success_rate")

        if success_rate is not None:
            return success_rate

        # Fall back to overall success rate
        if self._effectiveness_stats.success_rate > 0:
            return self._effectiveness_stats.success_rate

        return 1.0  # Default if no data

    def estimate_impact(self, insight: dict[str, Any]) -> str:
        """Classify impact: critical, high, medium, low.

        Impact is estimated based on several factors:
        - Health score (lower = higher impact)
        - Escalation rate (higher = higher impact)
        - Flakiness score (higher = higher impact)
        - Severity field if present

        Args:
            insight: Dictionary containing insight data with optional fields:
                - health_score: Overall system health (0.0-1.0)
                - escalation_rate: Rate of escalations (0.0-1.0)
                - flakiness_score: Test flakiness score (0.0-1.0)
                - severity: Pre-classified severity ("high", "medium", "low")
                - priority: Pre-classified priority

        Returns:
            Impact classification: "critical", "high", "medium", or "low".
        """
        # Check for explicit severity/priority
        if insight.get("severity") == "critical" or insight.get("priority") == "critical":
            return "critical"
        if insight.get("severity") == "high" or insight.get("priority") == "high":
            return "high"

        # Health score based impact
        health_score = insight.get("health_score")
        if health_score is not None:
            if health_score < CRITICAL_HEALTH_THRESHOLD:
                return "critical"
            if health_score < HIGH_IMPACT_THRESHOLD:
                return "high"
            if health_score < MEDIUM_IMPACT_THRESHOLD:
                return "medium"

        # Escalation rate based impact
        escalation_rate = insight.get("escalation_rate")
        if escalation_rate is not None:
            if escalation_rate >= CRITICAL_ESCALATION_RATE:
                return "critical"
            if escalation_rate >= HIGH_ESCALATION_RATE:
                return "high"

        # Flakiness score based impact
        flakiness_score = insight.get("flakiness_score")
        if flakiness_score is not None:
            if flakiness_score >= CRITICAL_FLAKINESS:
                return "critical"
            if flakiness_score >= HIGH_FLAKINESS:
                return "high"

        # Failure rate based impact
        failure_rate = insight.get("failure_rate")
        if failure_rate is not None:
            if failure_rate >= 0.5:
                return "high"
            if failure_rate >= 0.2:
                return "medium"

        # Default to medium if no indicators
        return "medium" if insight.get("severity") == "medium" else "low"

    def format_as_imp(self, insight: dict[str, Any]) -> dict[str, Any]:
        """Convert insight to improvement entry format.

        Creates a structured improvement entry compatible with the improvement
        tracking system. Each entry includes metadata for prioritization and
        tracking. IMP-LOOP-019: Adjusts confidence based on historical success
        rates for similar task types.

        Args:
            insight: Dictionary containing insight data with fields:
                - source: Origin of the insight (e.g., "slot_reliability")
                - action: Recommended action to take
                - details: Additional context about the insight
                - Other source-specific fields

        Returns:
            Dictionary in improvement entry format with keys:
            - id: Unique improvement ID (IMP-XXX-NNN)
            - title: Brief description of the improvement
            - description: Detailed description with context
            - priority: Impact classification (critical/high/medium/low)
            - category: Category of improvement
            - source: Origin of the insight
            - created_at: ISO timestamp of creation
            - status: Current status (always "pending" for new entries)
            - evidence: Supporting data from the insight
            - recommended_action: Specific action to take
            - confidence: Task confidence adjusted by historical success rate (IMP-LOOP-019)
            - historical_success_rate: Success rate for similar tasks (IMP-LOOP-019)
        """
        source = insight.get("source", "unknown")
        category = INSIGHT_TO_CATEGORY.get(source, "GEN")
        imp_id = self._generate_imp_id(category)
        impact = self.estimate_impact(insight)

        # IMP-LOOP-019: Get historical success rate for this insight type
        historical_success_rate = self.get_success_rate_for_insight_type(source)

        # Build title from action or source
        action = insight.get("action", "")
        if action:
            title = action
        else:
            title = f"Investigate {source.replace('_', ' ')} anomaly"

        # Build description with context
        details = insight.get("details", "")
        description_parts = ["Auto-generated from telemetry analysis."]
        if details:
            description_parts.append(f"Details: {details}")

        # Add source-specific context
        if source == "slot_reliability":
            slot_id = insight.get("slot_id")
            if slot_id is not None:
                description_parts.append(f"Affected slot: {slot_id}")
            escalation_rate = insight.get("escalation_rate")
            if escalation_rate is not None:
                description_parts.append(f"Escalation rate: {escalation_rate:.0%}")

        elif source == "nudge_effectiveness":
            nudge_type = insight.get("nudge_type")
            if nudge_type:
                description_parts.append(f"Nudge type: {nudge_type}")
            trigger = insight.get("trigger")
            if trigger:
                description_parts.append(f"Escalation trigger: {trigger}")

        elif source == "flaky_tests":
            test_id = insight.get("test_id")
            if test_id:
                description_parts.append(f"Test: {test_id}")
            flakiness_score = insight.get("flakiness_score")
            if flakiness_score is not None:
                description_parts.append(f"Flakiness score: {flakiness_score:.2f}")
            patterns = insight.get("patterns", [])
            if patterns:
                description_parts.append(f"Patterns: {', '.join(patterns)}")

        # Build evidence dict
        evidence: dict[str, Any] = {
            "source": source,
            "generated_from": "telemetry_analysis",
        }

        # Add numeric metrics as evidence
        for key in [
            "health_score",
            "escalation_rate",
            "failure_rate",
            "flakiness_score",
            "resolution_rate",
        ]:
            if key in insight and insight[key] is not None:
                evidence[key] = insight[key]

        # Add identifiers as evidence
        for key in ["slot_id", "test_id", "nudge_type", "trigger"]:
            if key in insight and insight[key] is not None:
                evidence[key] = insight[key]

        # IMP-LOOP-019: Calculate task confidence adjusted by historical success rate
        # Base confidence from insight's own indicators
        base_confidence = insight.get("confidence", 0.8)
        if isinstance(base_confidence, (int, float)):
            # Adjust confidence based on historical success rate
            # If historical success rate is low, reduce confidence
            adjusted_confidence = base_confidence * historical_success_rate
        else:
            adjusted_confidence = 0.8 * historical_success_rate

        # IMP-LOOP-019: Add historical context to description if success rate is low
        if historical_success_rate < 0.5:
            description_parts.append(
                f"[Note: Historical success rate for {source} tasks is {historical_success_rate:.0%}]"
            )

        logger.debug(
            "[IMP-LOOP-019] Generated IMP %s with confidence=%.2f "
            "(base=%.2f, historical_rate=%.2f)",
            imp_id,
            adjusted_confidence,
            base_confidence if isinstance(base_confidence, (int, float)) else 0.8,
            historical_success_rate,
        )

        return {
            "id": imp_id,
            "title": title,
            "description": " ".join(description_parts),
            "priority": impact,
            "category": source,
            "source": "telemetry_insights",
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "evidence": evidence,
            "recommended_action": insight.get("action", insight.get("recommendation", "")),
            # IMP-LOOP-019: Add effectiveness feedback data
            "confidence": round(adjusted_confidence, 3),
            "historical_success_rate": round(historical_success_rate, 3),
        }

    def generate_improvements_from_insights(self) -> list[dict[str, Any]]:
        """Create IMP entries from detected patterns.

        Analyzes telemetry data through the TelemetryAnalyzer and converts
        all prioritized actions into structured improvement entries.

        Returns:
            List of improvement entries sorted by priority. Each entry is
            a dictionary in the format returned by format_as_imp().
        """
        # Reset counter for fresh ID generation
        self._imp_counter.clear()

        # Get insights from analyzer
        insights = self.analyzer.generate_insights()
        improvements: list[dict[str, Any]] = []

        # Process prioritized actions
        prioritized_actions = insights.get("prioritized_actions", [])
        for action in prioritized_actions:
            imp = self.format_as_imp(action)
            improvements.append(imp)

        # Add improvements for problematic slots not already covered
        slot_reliability = insights.get("slot_reliability", {})
        problematic_slots = slot_reliability.get("problematic_slots", [])
        processed_slot_ids = {
            a.get("slot_id") for a in prioritized_actions if a.get("slot_id") is not None
        }

        for slot_info in problematic_slots:
            slot_id = slot_info.get("slot_id")
            if slot_id not in processed_slot_ids:
                action = {
                    "source": "slot_reliability",
                    "slot_id": slot_id,
                    "escalation_rate": slot_info.get("escalation_rate"),
                    "failure_rate": slot_info.get("failure_rate"),
                    "severity": slot_info.get("severity"),
                    "action": f"Investigate slot {slot_id} reliability issues",
                    "details": "High escalation rate detected",
                }
                imp = self.format_as_imp(action)
                improvements.append(imp)

        # Add improvements for escalation patterns not already covered
        nudge_effectiveness = insights.get("nudge_effectiveness", {})
        escalation_patterns = nudge_effectiveness.get("escalation_patterns", [])
        processed_triggers = {
            a.get("trigger") for a in prioritized_actions if a.get("trigger") is not None
        }

        for pattern in escalation_patterns:
            trigger = pattern.get("trigger")
            if trigger and trigger not in processed_triggers:
                action = {
                    "source": "escalation_patterns",
                    "trigger": trigger,
                    "count": pattern.get("count"),
                    "severity": pattern.get("severity"),
                    "action": f"Address escalation trigger: {trigger}",
                    "details": f"Caused {pattern.get('count', 0)} escalations",
                }
                imp = self.format_as_imp(action)
                improvements.append(imp)

        # Add health score context to all improvements
        health_score = insights.get("health_score", 1.0)
        for imp in improvements:
            imp["evidence"]["system_health_score"] = health_score

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        improvements.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 4))

        logger.info(
            "Generated %d improvements from telemetry insights (health_score=%.1f%%)",
            len(improvements),
            health_score * 100,
        )

        return improvements

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of generated improvements.

        Returns:
            Dictionary containing:
            - total_improvements: Total number of improvements generated
            - by_priority: Count of improvements by priority level
            - by_category: Count of improvements by category
            - health_score: Current system health score
        """
        improvements = self.generate_improvements_from_insights()

        by_priority: Counter[str] = Counter()
        by_category: Counter[str] = Counter()

        for imp in improvements:
            by_priority[imp.get("priority", "unknown")] += 1
            by_category[imp.get("category", "unknown")] += 1

        # Get health score from analyzer
        insights = self.analyzer.generate_insights()
        health_score = insights.get("health_score", 1.0)

        return {
            "total_improvements": len(improvements),
            "by_priority": dict(by_priority),
            "by_category": dict(by_category),
            "health_score": health_score,
            "generated_at": datetime.now().isoformat(),
        }
