"""Bridge component for persisting telemetry insights to memory service."""

from typing import List, Dict, Any, Optional

try:
    from src.autopack.memory.memory_service import MemoryService
except ImportError:
    MemoryService = None


class TelemetryToMemoryBridge:
    """Bridges telemetry insights to memory service for persistent storage."""

    def __init__(self, memory_service: Optional["MemoryService"] = None, enabled: bool = True):
        self.memory_service = memory_service
        self.enabled = enabled
        self._persisted_insights: set = set()  # For deduplication

    def persist_insights(
        self, ranked_issues: List[Dict[str, Any]], run_id: str, project_id: Optional[str] = None
    ) -> int:
        """Persist ranked issues to memory service.

        Args:
            ranked_issues: List of ranked issues from TelemetryAnalyzer
            run_id: Current run ID for correlation
            project_id: Optional project ID for namespacing

        Returns:
            Number of insights persisted
        """
        if not self.enabled or not self.memory_service:
            return 0

        if not self.memory_service.enabled:
            return 0

        persisted_count = 0

        for issue in ranked_issues:
            insight = self._convert_to_insight(issue, run_id)
            insight_key = f"{insight['insight_type']}:{insight['insight_id']}"

            # Deduplication: don't persist same insight multiple times
            if insight_key in self._persisted_insights:
                continue

            self._persist_single_insight(insight, project_id)
            self._persisted_insights.add(insight_key)
            persisted_count += 1

        return persisted_count

    def _convert_to_insight(self, issue: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """Convert issue dict to TelemetryInsight object."""
        insight_type = issue.get("issue_type", "unknown")
        insight_id = f"{run_id}_{insight_type}_{issue.get('rank', 0)}"

        return {
            "insight_id": insight_id,
            "insight_type": insight_type,
            "phase_id": issue.get("phase_id"),
            "severity": issue.get("severity", "medium"),
            "description": issue.get("details", ""),
            "metric_value": issue.get("metric_value", 0.0),
            "occurrences": issue.get("occurrences", 1),
            "suggested_action": issue.get("suggested_action"),
        }

    def _persist_single_insight(
        self, insight: Dict[str, Any], project_id: Optional[str] = None
    ) -> None:
        """Persist single insight to appropriate memory collection."""
        if not self.memory_service:
            return

        insight_type = insight.get("insight_type", "unknown")

        if insight_type == "cost_sink":
            # Write as phase summary with cost warning
            self.memory_service.write_phase_summary(
                phase_id=insight.get("phase_id") or "global",
                summary=insight.get("description", ""),
                metrics={
                    "cost_tokens": insight.get("metric_value", 0),
                    "occurrences": insight.get("occurrences", 1),
                },
                tags=["telemetry", "cost_sink", insight.get("severity", "medium")],
            )

        elif insight_type == "failure_mode":
            # Write as error with failure pattern
            self.memory_service.write_error(
                error_type=insight.get("description", ""),
                message=f"Recurring failure: {insight.get('suggested_action') or insight.get('description')}",
                context={
                    "phase_id": insight.get("phase_id"),
                    "occurrences": insight.get("occurrences", 1),
                },
                severity=insight.get("severity", "medium"),
                project_id=project_id,
            )

        elif insight_type == "retry_cause":
            # Write as doctor hint with resolution strategy
            self.memory_service.write_doctor_hint(
                hint=insight.get("suggested_action") or insight.get("description", ""),
                context={
                    "issue": insight.get("description"),
                    "occurrences": insight.get("occurrences", 1),
                },
                tags=["telemetry", "retry", insight.get("severity", "medium")],
            )

        else:
            # Generic write to phase summary
            self.memory_service.write_phase_summary(
                phase_id=insight.get("phase_id") or "unknown",
                summary=f"Telemetry insight: {insight.get('description')}",
                metrics={
                    "value": insight.get("metric_value", 0),
                    "occurrences": insight.get("occurrences", 1),
                },
                tags=["telemetry", insight_type, insight.get("severity", "medium")],
            )

    def clear_cache(self) -> None:
        """Clear deduplication cache (call between runs)."""
        self._persisted_insights.clear()
