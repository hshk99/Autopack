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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer
    from autopack.memory.memory_service import MemoryService
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
    # New categories (IMP-TASK-001)
    "cost_sink": "CST",
    "retry_cause": "RTY",
    "ci_fail": "CI",
    "infra_error": "INF",
    "auditor_reject": "AUD",
    "promoted_rule": "RUL",
}

# IMP-MEM-001: Freshness filtering constants for task generation
# Default maximum age for insights to be considered fresh (hours)
# IMP-LOOP-023: Increased to 30 days for cross-cycle learning
DEFAULT_INSIGHT_FRESHNESS_HOURS = 720  # 30 days - matches MemoryService default

# Impact validation constants (IMP-TASK-002)
IMPACT_LEVELS = ["critical", "high", "medium", "low"]
IMPACT_LEVEL_TO_NUMERIC = {"critical": 3, "high": 2, "medium": 1, "low": 0}
NUMERIC_TO_IMPACT_LEVEL = {3: "critical", 2: "high", 1: "medium", 0: "low"}

# Threshold adjustment limits (IMP-TASK-002)
MIN_THRESHOLD_ADJUSTMENT = -0.15  # Max decrease from base threshold
MAX_THRESHOLD_ADJUSTMENT = 0.15  # Max increase from base threshold
MIN_HISTORY_FOR_CALIBRATION = 10  # Minimum records before calibration kicks in


@dataclass
class ImpactValidationRecord:
    """Record of predicted vs actual impact for calibration (IMP-TASK-002).

    Attributes:
        task_id: Unique identifier for the task.
        predicted: The predicted impact level (critical/high/medium/low).
        actual: The actual impact level observed after completion.
        timestamp: When the validation occurred.
    """

    task_id: str
    predicted: str
    actual: str
    timestamp: datetime = field(default_factory=datetime.now)


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
        memory_service: Optional[MemoryService] = None,
        freshness_hours: Optional[float] = None,
    ) -> None:
        """Initialize the InsightToTaskGenerator.

        Args:
            analyzer: TelemetryAnalyzer instance to use for insight generation.
            effectiveness_stats: Optional task effectiveness stats for adjusting
                insight confidence based on historical success rates (IMP-LOOP-019).
            memory_service: Optional MemoryService for freshness checking
                (IMP-MEM-001). When provided, enables stale insight filtering.
            freshness_hours: Optional freshness threshold in hours (IMP-MEM-001).
                Defaults to DEFAULT_INSIGHT_FRESHNESS_HOURS (720 hours / 30 days).
        """
        self.analyzer = analyzer
        self._imp_counter: Counter[str] = Counter()
        self._effectiveness_stats = effectiveness_stats

        # IMP-MEM-001: Memory service for freshness checking
        self._memory_service = memory_service
        self._freshness_hours = freshness_hours or DEFAULT_INSIGHT_FRESHNESS_HOURS

        # IMP-TASK-002: Impact validation tracking
        self._impact_history: list[ImpactValidationRecord] = []
        self._threshold_adjustments: dict[str, float] = {
            "critical": 0.0,
            "high": 0.0,
            "medium": 0.0,
        }

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

    def set_memory_service(
        self, memory_service: MemoryService, freshness_hours: Optional[float] = None
    ) -> None:
        """Set or update the memory service for freshness checking (IMP-MEM-001).

        Call this method to enable freshness filtering of insights.
        Stale insights (older than freshness threshold) will be filtered
        before task generation to prevent duplicate/stale task creation.

        Args:
            memory_service: MemoryService instance for freshness checking.
            freshness_hours: Optional freshness threshold in hours.
                Defaults to the current value or DEFAULT_INSIGHT_FRESHNESS_HOURS.
        """
        self._memory_service = memory_service
        if freshness_hours is not None:
            self._freshness_hours = freshness_hours
        logger.debug(
            "[IMP-MEM-001] Memory service connected for freshness filtering "
            "(threshold=%d hours)",
            self._freshness_hours,
        )

    def _parse_insight_timestamp(self, insight: dict[str, Any]) -> Optional[datetime]:
        """Parse timestamp from an insight record (IMP-MEM-001).

        Handles multiple timestamp field names and formats that may be
        present in insights from different sources.

        Args:
            insight: The insight dictionary.

        Returns:
            Parsed datetime or None if no valid timestamp found.
        """
        # Check common timestamp field names
        timestamp_fields = ["timestamp", "created_at", "detected_at", "time"]
        for field_name in timestamp_fields:
            ts_value = insight.get(field_name)
            if ts_value is not None:
                # Handle datetime objects directly
                if isinstance(ts_value, datetime):
                    # Ensure timezone-aware
                    if ts_value.tzinfo is None:
                        return ts_value.replace(tzinfo=timezone.utc)
                    return ts_value

                # Handle ISO format strings
                if isinstance(ts_value, str):
                    try:
                        # Try parsing ISO format
                        parsed = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        return parsed
                    except ValueError:
                        continue

        return None

    def _is_insight_fresh(self, insight: dict[str, Any]) -> bool:
        """Check if an insight is within the freshness window (IMP-MEM-001).

        Args:
            insight: The insight dictionary to check.

        Returns:
            True if insight is fresh or has no timestamp (assumed fresh),
            False if insight is stale (older than freshness threshold).
        """
        timestamp = self._parse_insight_timestamp(insight)
        if timestamp is None:
            # No timestamp - assume fresh (just created)
            return True

        now = datetime.now(timezone.utc)
        age_hours = (now - timestamp).total_seconds() / 3600

        is_fresh = age_hours <= self._freshness_hours

        if not is_fresh:
            logger.debug(
                "[IMP-MEM-001] Stale insight detected (age=%.1f hours > threshold=%d hours): %s",
                age_hours,
                self._freshness_hours,
                insight.get("source", "unknown"),
            )

        return is_fresh

    def _filter_stale_insights(self, insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter out stale insights before task generation (IMP-MEM-001).

        Removes insights that are older than the freshness threshold to prevent
        duplicate or stale task creation. This is the primary freshness check
        in the task generation pipeline.

        Args:
            insights: List of insight dictionaries to filter.

        Returns:
            List of fresh insights (within freshness window).
        """
        if not insights:
            return []

        fresh_insights = [i for i in insights if self._is_insight_fresh(i)]
        stale_count = len(insights) - len(fresh_insights)

        if stale_count > 0:
            logger.info(
                "[IMP-MEM-001] Filtered %d stale insights (threshold=%d hours), "
                "kept %d fresh insights",
                stale_count,
                self._freshness_hours,
                len(fresh_insights),
            )

        return fresh_insights

    def get_freshness_stats(self) -> dict[str, Any]:
        """Get freshness filtering statistics (IMP-MEM-001).

        Returns:
            Dictionary containing:
            - freshness_threshold_hours: Current threshold
            - memory_service_connected: Whether memory service is available
        """
        return {
            "freshness_threshold_hours": self._freshness_hours,
            "memory_service_connected": self._memory_service is not None,
        }

    def validate_impact_estimate(self, task_id: str, predicted: str, actual: str) -> None:
        """Record and validate an impact estimate against actual outcome (IMP-TASK-002).

        This method compares the predicted impact level against the actual
        observed impact and records the result for threshold calibration.
        When enough history is accumulated, thresholds are automatically
        recalibrated to improve accuracy.

        Args:
            task_id: Unique identifier for the task.
            predicted: The predicted impact level (critical/high/medium/low).
            actual: The actual observed impact level (critical/high/medium/low).
        """
        # Validate inputs
        predicted_lower = predicted.lower()
        actual_lower = actual.lower()

        if predicted_lower not in IMPACT_LEVELS:
            logger.warning("[IMP-TASK-002] Invalid predicted impact level: %s", predicted)
            return
        if actual_lower not in IMPACT_LEVELS:
            logger.warning("[IMP-TASK-002] Invalid actual impact level: %s", actual)
            return

        # Record the validation
        record = ImpactValidationRecord(
            task_id=task_id,
            predicted=predicted_lower,
            actual=actual_lower,
        )
        self._impact_history.append(record)

        # Log the validation
        if predicted_lower != actual_lower:
            logger.info(
                "[IMP-TASK-002] Impact mismatch for task %s: predicted=%s, actual=%s",
                task_id,
                predicted_lower,
                actual_lower,
            )
        else:
            logger.debug(
                "[IMP-TASK-002] Impact validated for task %s: %s",
                task_id,
                predicted_lower,
            )

        # Trigger recalibration if we have enough history
        self._recalibrate_thresholds()

    def _get_calibrated_thresholds(self) -> dict[str, float]:
        """Get dynamically adjusted impact thresholds based on validation history (IMP-TASK-002).

        Returns threshold values that have been calibrated based on historical
        prediction accuracy. If predictions have been systematically over- or
        under-estimating impact, thresholds are adjusted accordingly.

        For health-based thresholds (lower health = higher impact), adjustments
        are SUBTRACTED because:
        - Over-predicting (positive adjustment) means we need to be MORE conservative
        - Being more conservative means LOWERING the threshold (fewer things qualify)
        - Under-predicting (negative adjustment) means we need to be LESS conservative
        - Being less conservative means RAISING the threshold (more things qualify)

        Returns:
            Dictionary mapping impact levels to their calibrated thresholds:
            - critical: Health threshold for critical classification
            - high: Health threshold for high classification
            - medium: Health threshold for medium classification
        """
        return {
            "critical": CRITICAL_HEALTH_THRESHOLD - self._threshold_adjustments["critical"],
            "high": HIGH_IMPACT_THRESHOLD - self._threshold_adjustments["high"],
            "medium": MEDIUM_IMPACT_THRESHOLD - self._threshold_adjustments["medium"],
        }

    def _recalibrate_thresholds(self) -> None:
        """Recalibrate impact thresholds based on validation history (IMP-TASK-002).

        Analyzes the history of predicted vs actual impact levels and adjusts
        thresholds to reduce systematic prediction errors. Only recalibrates
        when sufficient history has been accumulated.

        The algorithm:
        - For each impact level, count over-predictions (predicted higher than actual)
          and under-predictions (predicted lower than actual)
        - If over-predicting, increase threshold (make it harder to classify as that level)
        - If under-predicting, decrease threshold (make it easier to classify)
        - Adjustments are bounded to prevent extreme drift
        """
        if len(self._impact_history) < MIN_HISTORY_FOR_CALIBRATION:
            return

        # Count prediction errors by level
        over_predictions: Counter[str] = Counter()
        under_predictions: Counter[str] = Counter()
        total_by_level: Counter[str] = Counter()

        for record in self._impact_history:
            predicted_num = IMPACT_LEVEL_TO_NUMERIC[record.predicted]
            actual_num = IMPACT_LEVEL_TO_NUMERIC[record.actual]
            total_by_level[record.predicted] += 1

            if predicted_num > actual_num:
                # Over-predicted (e.g., predicted critical but was actually medium)
                over_predictions[record.predicted] += 1
            elif predicted_num < actual_num:
                # Under-predicted (e.g., predicted low but was actually high)
                under_predictions[record.predicted] += 1

        # Calculate adjustment for each threshold
        for level in ["critical", "high", "medium"]:
            if total_by_level[level] == 0:
                continue

            over_rate = over_predictions[level] / total_by_level[level]
            under_rate = under_predictions[level] / total_by_level[level]

            # Calculate adjustment: positive if over-predicting, negative if under-predicting
            # Scale by the error rate difference
            adjustment_delta = (over_rate - under_rate) * 0.05

            # Apply bounded adjustment
            new_adjustment = self._threshold_adjustments[level] + adjustment_delta
            self._threshold_adjustments[level] = max(
                MIN_THRESHOLD_ADJUSTMENT,
                min(MAX_THRESHOLD_ADJUSTMENT, new_adjustment),
            )

        logger.debug(
            "[IMP-TASK-002] Recalibrated thresholds: critical=%.3f, high=%.3f, medium=%.3f",
            self._threshold_adjustments["critical"],
            self._threshold_adjustments["high"],
            self._threshold_adjustments["medium"],
        )

    def get_impact_validation_stats(self) -> dict[str, Any]:
        """Get statistics on impact validation accuracy (IMP-TASK-002).

        Returns:
            Dictionary containing:
            - total_validations: Total number of validated predictions
            - accuracy: Proportion of correct predictions
            - by_level: Breakdown by impact level with hits/misses
            - threshold_adjustments: Current calibration adjustments
        """
        if not self._impact_history:
            return {
                "total_validations": 0,
                "accuracy": 0.0,
                "by_level": {},
                "threshold_adjustments": dict(self._threshold_adjustments),
            }

        correct = sum(1 for r in self._impact_history if r.predicted == r.actual)
        total = len(self._impact_history)

        by_level: dict[str, dict[str, int]] = {}
        for level in IMPACT_LEVELS:
            level_records = [r for r in self._impact_history if r.predicted == level]
            hits = sum(1 for r in level_records if r.actual == level)
            by_level[level] = {
                "predicted_count": len(level_records),
                "correct": hits,
                "accuracy": hits / len(level_records) if level_records else 0.0,
            }

        return {
            "total_validations": total,
            "accuracy": correct / total if total > 0 else 0.0,
            "by_level": by_level,
            "threshold_adjustments": dict(self._threshold_adjustments),
        }

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

        IMP-TASK-002: Uses dynamically calibrated thresholds based on
        historical validation of predictions vs actual outcomes.

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

        # IMP-TASK-002: Get calibrated thresholds
        calibrated = self._get_calibrated_thresholds()
        critical_threshold = calibrated["critical"]
        high_threshold = calibrated["high"]
        medium_threshold = calibrated["medium"]

        # Health score based impact (using calibrated thresholds)
        health_score = insight.get("health_score")
        if health_score is not None:
            if health_score < critical_threshold:
                return "critical"
            if health_score < high_threshold:
                return "high"
            if health_score < medium_threshold:
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

        IMP-MEM-001: Filters stale insights before task generation to prevent
        duplicate/stale task creation. Insights older than the freshness
        threshold (default 72 hours) are excluded.

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

        # IMP-MEM-001: Filter stale prioritized actions before task generation
        fresh_actions = self._filter_stale_insights(prioritized_actions)
        stale_action_count = len(prioritized_actions) - len(fresh_actions)
        if stale_action_count > 0:
            logger.info(
                "[IMP-MEM-001] Filtered %d stale prioritized actions from task generation",
                stale_action_count,
            )

        for action in fresh_actions:
            imp = self.format_as_imp(action)
            improvements.append(imp)

        # Add improvements for problematic slots not already covered
        slot_reliability = insights.get("slot_reliability", {})
        problematic_slots = slot_reliability.get("problematic_slots", [])

        # IMP-MEM-001: Filter stale problematic slots
        fresh_slots = self._filter_stale_insights(problematic_slots)

        processed_slot_ids = {
            a.get("slot_id") for a in fresh_actions if a.get("slot_id") is not None
        }

        for slot_info in fresh_slots:
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

        # IMP-MEM-001: Filter stale escalation patterns
        fresh_patterns = self._filter_stale_insights(escalation_patterns)

        processed_triggers = {
            a.get("trigger") for a in fresh_actions if a.get("trigger") is not None
        }

        for pattern in fresh_patterns:
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

    # IMP-LOOP-022: Corrective task creation

    def create_corrective_task(self, corrective_task: Any) -> dict[str, Any]:
        """Create an improvement entry from a corrective task.

        IMP-LOOP-022: Converts a CorrectiveTask (generated by TaskEffectivenessTracker
        after repeated failures) into a structured improvement entry that can be
        added to the improvement backlog.

        Args:
            corrective_task: CorrectiveTask instance or dict with corrective task data.
                Expected fields:
                - corrective_id: Unique ID for the corrective task
                - original_task_id: The task that failed repeatedly
                - failure_count: Number of failures that triggered this
                - error_patterns: List of detected error patterns
                - category: Category of the original task

        Returns:
            Dictionary in improvement entry format with:
            - id: The corrective task ID
            - title: Description of the corrective action needed
            - priority: Always "high" for corrective tasks
            - type: "corrective" to identify as auto-generated correction
        """
        # Handle both CorrectiveTask objects and dicts
        if hasattr(corrective_task, "to_dict"):
            task_data = corrective_task.to_dict()
        else:
            task_data = corrective_task

        corrective_id = task_data.get("corrective_id", "CORR-UNKNOWN")
        original_task_id = task_data.get("original_task_id", "unknown")
        failure_count = task_data.get("failure_count", 0)
        error_patterns = task_data.get("error_patterns", [])
        category = task_data.get("category", "general")

        # Build description with failure context
        description_parts = [
            "Auto-generated corrective task for repeated failures.",
            f"Original task '{original_task_id}' failed {failure_count} times.",
        ]

        if error_patterns:
            description_parts.append(f"Error patterns: {'; '.join(error_patterns[:3])}")

        description_parts.append(
            "Investigate root cause and implement fix to prevent future failures."
        )

        # Build evidence
        evidence = {
            "source": "corrective_task_generation",
            "original_task_id": original_task_id,
            "failure_count": failure_count,
            "error_patterns": error_patterns,
            "generated_by": "TaskEffectivenessTracker",
        }

        imp_entry = {
            "id": corrective_id,
            "title": f"Fix repeated failures in {original_task_id}",
            "description": " ".join(description_parts),
            "priority": "high",
            "category": category,
            "source": "corrective_task_feedback",
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "evidence": evidence,
            "recommended_action": f"Investigate and fix root cause of {original_task_id} failures",
            "type": "corrective",
            "original_task_id": original_task_id,
            "failure_count": failure_count,
        }

        logger.info(
            "[IMP-LOOP-022] Created corrective improvement entry: id=%s, "
            "original_task=%s, failures=%d",
            corrective_id,
            original_task_id,
            failure_count,
        )

        return imp_entry
