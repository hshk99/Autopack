"""Insight provenance and explainability.

IMP-LOOP-015: Provides traceability from telemetry events to insights to tasks,
with human-readable explanations of recommendations.

This module tracks the complete lineage of how insights are derived from raw
telemetry data and how they lead to task recommendations, enabling:
- Audit trails for debugging and compliance
- Human-readable explanations of system decisions
- Confidence scoring based on evidence quality
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InsightProvenance:
    """Provenance chain for an insight.

    Tracks the complete lineage from telemetry events through analysis
    to the final insight, including supporting evidence.
    """

    insight_id: str
    source_telemetry_events: List[str]
    analysis_logic_id: str  # Which algorithm detected this
    supporting_data: Dict[str, Any]  # Stats, distributions, etc.
    confidence_evidence: List[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    insight_type: Optional[str] = None
    severity: Optional[str] = None

    def explain(self) -> str:
        """Generate human-readable explanation of insight.

        Returns:
            Multi-line string explaining the insight provenance.
        """
        lines = [
            f"Insight {self.insight_id}:",
            f"  Detected by: {self.analysis_logic_id}",
            f"  Based on {len(self.source_telemetry_events)} telemetry events",
        ]

        if self.insight_type:
            lines.append(f"  Type: {self.insight_type}")

        if self.severity:
            lines.append(f"  Severity: {self.severity}")

        if self.supporting_data:
            lines.append("  Supporting data:")
            for key, value in self.supporting_data.items():
                # Truncate long values for readability
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:97] + "..."
                lines.append(f"    {key}: {value_str}")

        if self.confidence_evidence:
            lines.append("  Evidence:")
            for evidence in self.confidence_evidence:
                lines.append(f"    - {evidence}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert provenance to dictionary for storage.

        Returns:
            Dictionary representation of the provenance.
        """
        return {
            "insight_id": self.insight_id,
            "source_telemetry_events": self.source_telemetry_events,
            "analysis_logic_id": self.analysis_logic_id,
            "supporting_data": self.supporting_data,
            "confidence_evidence": self.confidence_evidence,
            "created_at": self.created_at.isoformat(),
            "insight_type": self.insight_type,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InsightProvenance":
        """Create InsightProvenance from dictionary.

        Args:
            data: Dictionary containing provenance data.

        Returns:
            InsightProvenance instance.
        """
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now(timezone.utc)

        return cls(
            insight_id=data["insight_id"],
            source_telemetry_events=data.get("source_telemetry_events", []),
            analysis_logic_id=data.get("analysis_logic_id", "unknown"),
            supporting_data=data.get("supporting_data", {}),
            confidence_evidence=data.get("confidence_evidence", []),
            created_at=created_at,
            insight_type=data.get("insight_type"),
            severity=data.get("severity"),
        )


@dataclass
class TaskRecommendation:
    """A task recommendation with its provenance chain.

    Links a recommended task back to the insights that motivated it.
    """

    task_id: str
    task_description: str
    source_insight_ids: List[str]
    priority_score: float
    rationale: str
    expected_impact: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def explain(self) -> str:
        """Generate human-readable explanation of recommendation.

        Returns:
            Multi-line string explaining why this task was recommended.
        """
        lines = [
            f"Task Recommendation: {self.task_id}",
            f"  Description: {self.task_description}",
            f"  Priority Score: {self.priority_score:.2f}",
            f"  Expected Impact: {self.expected_impact}",
            f"  Rationale: {self.rationale}",
            f"  Based on {len(self.source_insight_ids)} insight(s):",
        ]
        for insight_id in self.source_insight_ids:
            lines.append(f"    - {insight_id}")

        return "\n".join(lines)


class ProvenanceTracker:
    """Tracks provenance chain for insights and recommendations.

    IMP-LOOP-015: Central tracking system for insight lineage, enabling
    explainability and traceability from telemetry to tasks.
    """

    def __init__(self) -> None:
        """Initialize the provenance tracker."""
        self._insights: Dict[str, InsightProvenance] = {}
        self._recommendations: Dict[str, TaskRecommendation] = {}
        self._insight_to_tasks: Dict[str, List[str]] = {}  # insight_id -> [task_ids]

    def record_insight_source(
        self,
        insight_id: str,
        telemetry_events: List[str],
        analysis_logic: str,
        supporting_data: Dict[str, Any],
        confidence_evidence: Optional[List[str]] = None,
        insight_type: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> InsightProvenance:
        """Record the source chain for an insight.

        Args:
            insight_id: Unique identifier for the insight.
            telemetry_events: List of telemetry event IDs that contributed.
            analysis_logic: Identifier of the algorithm/logic that detected this.
            supporting_data: Statistics, distributions, or other supporting data.
            confidence_evidence: List of evidence statements supporting confidence.
            insight_type: Type of insight (e.g., "cost_sink", "failure_mode").
            severity: Severity level (e.g., "low", "medium", "high", "critical").

        Returns:
            InsightProvenance instance for the recorded insight.
        """
        if confidence_evidence is None:
            confidence_evidence = []

        provenance = InsightProvenance(
            insight_id=insight_id,
            source_telemetry_events=telemetry_events,
            analysis_logic_id=analysis_logic,
            supporting_data=supporting_data,
            confidence_evidence=confidence_evidence,
            insight_type=insight_type,
            severity=severity,
        )

        self._insights[insight_id] = provenance
        logger.debug(f"[IMP-LOOP-015] Recorded provenance for insight: {insight_id}")

        return provenance

    def record_task_recommendation(
        self,
        task_id: str,
        task_description: str,
        source_insight_ids: List[str],
        priority_score: float,
        rationale: str,
        expected_impact: str,
    ) -> TaskRecommendation:
        """Record a task recommendation with its source insights.

        Args:
            task_id: Unique identifier for the task.
            task_description: Description of what the task does.
            source_insight_ids: List of insight IDs that motivated this task.
            priority_score: Priority score (0.0 to 1.0).
            rationale: Human-readable rationale for the recommendation.
            expected_impact: Expected impact if task is executed.

        Returns:
            TaskRecommendation instance.
        """
        recommendation = TaskRecommendation(
            task_id=task_id,
            task_description=task_description,
            source_insight_ids=source_insight_ids,
            priority_score=priority_score,
            rationale=rationale,
            expected_impact=expected_impact,
        )

        self._recommendations[task_id] = recommendation

        # Update insight-to-task mapping
        for insight_id in source_insight_ids:
            if insight_id not in self._insight_to_tasks:
                self._insight_to_tasks[insight_id] = []
            self._insight_to_tasks[insight_id].append(task_id)

        logger.debug(f"[IMP-LOOP-015] Recorded recommendation for task: {task_id}")

        return recommendation

    def get_insight_provenance(self, insight_id: str) -> Optional[InsightProvenance]:
        """Get provenance for a specific insight.

        Args:
            insight_id: The insight ID to look up.

        Returns:
            InsightProvenance if found, None otherwise.
        """
        return self._insights.get(insight_id)

    def get_recommendation(self, task_id: str) -> Optional[TaskRecommendation]:
        """Get recommendation details for a task.

        Args:
            task_id: The task ID to look up.

        Returns:
            TaskRecommendation if found, None otherwise.
        """
        return self._recommendations.get(task_id)

    def get_recommendation_explanation(self, task_id: str) -> str:
        """Get human-readable explanation for why task was recommended.

        This provides a complete trace from the task back through insights
        to the original telemetry events.

        Args:
            task_id: The task ID to explain.

        Returns:
            Human-readable explanation string.
        """
        recommendation = self._recommendations.get(task_id)
        if not recommendation:
            return f"No recommendation found for task: {task_id}"

        lines = [recommendation.explain(), "\n--- Insight Details ---"]

        for insight_id in recommendation.source_insight_ids:
            provenance = self._insights.get(insight_id)
            if provenance:
                lines.append("")
                lines.append(provenance.explain())
            else:
                lines.append(f"\nInsight {insight_id}: (provenance not recorded)")

        return "\n".join(lines)

    def get_tasks_for_insight(self, insight_id: str) -> List[str]:
        """Get all task IDs that were derived from an insight.

        Args:
            insight_id: The insight ID to look up.

        Returns:
            List of task IDs derived from this insight.
        """
        return self._insight_to_tasks.get(insight_id, [])

    def get_full_lineage(self, task_id: str) -> Dict[str, Any]:
        """Get the complete lineage for a task recommendation.

        Returns a structured representation of the entire provenance chain
        from telemetry events through insights to the task.

        Args:
            task_id: The task ID to trace.

        Returns:
            Dictionary containing the full lineage.
        """
        recommendation = self._recommendations.get(task_id)
        if not recommendation:
            return {"error": f"No recommendation found for task: {task_id}"}

        lineage = {
            "task": {
                "id": recommendation.task_id,
                "description": recommendation.task_description,
                "priority_score": recommendation.priority_score,
                "rationale": recommendation.rationale,
                "expected_impact": recommendation.expected_impact,
                "created_at": recommendation.created_at.isoformat(),
            },
            "insights": [],
            "telemetry_events": set(),
        }

        for insight_id in recommendation.source_insight_ids:
            provenance = self._insights.get(insight_id)
            if provenance:
                lineage["insights"].append(provenance.to_dict())
                lineage["telemetry_events"].update(provenance.source_telemetry_events)

        # Convert set to sorted list for consistent output
        lineage["telemetry_events"] = sorted(lineage["telemetry_events"])

        return lineage

    def generate_insight_id(
        self,
        analysis_logic: str,
        key_data: str,
    ) -> str:
        """Generate a deterministic insight ID from analysis logic and key data.

        Args:
            analysis_logic: The analysis algorithm identifier.
            key_data: Key data that uniquely identifies this insight.

        Returns:
            A deterministic insight ID.
        """
        combined = f"{analysis_logic}:{key_data}"
        hash_digest = hashlib.sha256(combined.encode()).hexdigest()[:12]
        return f"insight:{analysis_logic}:{hash_digest}"

    def clear(self) -> None:
        """Clear all tracked provenance data."""
        self._insights.clear()
        self._recommendations.clear()
        self._insight_to_tasks.clear()
        logger.debug("[IMP-LOOP-015] Cleared all provenance data")

    @property
    def insight_count(self) -> int:
        """Get the number of tracked insights."""
        return len(self._insights)

    @property
    def recommendation_count(self) -> int:
        """Get the number of tracked recommendations."""
        return len(self._recommendations)
