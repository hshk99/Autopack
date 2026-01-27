"""
Learning Pipeline Module

Records lessons learned during troubleshooting to help:
1. Later phases in the same run (Stage 0A - within-run hints)
2. Future runs after promotion (Stage 0B - cross-run hints)
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LearningHint:
    """Lesson learned during troubleshooting"""

    phase_id: str
    hint_type: str  # auditor_reject, ci_fail, patch_apply_error, etc.
    hint_text: str
    source_issue_keys: List[str]
    recorded_at: float
    task_category: Optional[str] = None


class LearningPipeline:
    """
    Records lessons learned during troubleshooting.

    Hints are lessons that can help:
    1. Later phases in the same run (Stage 0A)
    2. Future runs after promotion (Stage 0B)
    """

    def __init__(
        self,
        run_id: str,
        memory_service: Optional[Any] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize LearningPipeline.

        Args:
            run_id: Run identifier for tracking hints
            memory_service: Optional MemoryService instance for hint persistence
            project_id: Optional project identifier for namespacing persisted hints
        """
        self.run_id = run_id
        self._hints: List[LearningHint] = []
        self._memory_service = memory_service
        self._project_id = project_id

    def record_hint(self, phase: Dict, hint_type: str, details: str):
        """
        Record a hint for this run.

        Args:
            phase: Phase specification dict
            hint_type: Type of hint (e.g., auditor_reject, ci_fail)
            details: Human-readable details about what was learned
        """
        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_name = phase.get("name", phase_id)

            # Generate descriptive hint text based on type
            hint_templates = {
                "auditor_reject": f"Phase '{phase_name}' was rejected by auditor - ensure code quality and completeness",
                "ci_fail": f"Phase '{phase_name}' failed CI tests - verify tests pass before submitting",
                "patch_apply_error": f"Phase '{phase_name}' generated invalid patch - ensure proper diff format",
                "infra_error": f"Phase '{phase_name}' hit infrastructure error - check API connectivity",
                "success_after_retry": f"Phase '{phase_name}' succeeded after retries - model escalation was needed",
                "builder_churn_limit_exceeded": f"Phase '{phase_name}' exceeded churn limit - reduce change scope",
                "builder_guardrail": f"Phase '{phase_name}' blocked by builder guardrail - check output size",
            }

            hint_text = hint_templates.get(hint_type, f"Phase '{phase_name}': {hint_type}")
            hint_text = f"{hint_text}. Details: {details}"

            # Create hint
            hint = LearningHint(
                phase_id=phase_id,
                hint_type=hint_type,
                hint_text=hint_text,
                source_issue_keys=[f"{hint_type}_{phase_id}"],
                recorded_at=time.time(),
                task_category=phase.get("task_category"),
            )

            self._hints.append(hint)

            # IMP-INT-004: Persist hint immediately if memory_service is available
            self._persist_hint_to_memory(hint)

            logger.debug(f"[Learning] Recorded hint for {phase_id}: {hint_type}")

        except Exception as e:
            # Don't let hint recording break phase execution
            logger.warning(f"[Learning] Failed to record hint: {e}")

    def get_hints_for_phase(self, phase: Dict, task_category: Optional[str] = None) -> List[str]:
        """
        Get relevant hints for a phase.

        Args:
            phase: Phase specification dict
            task_category: Optional task category filter

        Returns:
            List of hint text strings
        """
        phase_id = phase.get("phase_id")
        phase_task_category = phase.get("task_category")

        # Filter hints by category or phase
        relevant_hints = []

        for hint in self._hints:
            # Same phase ID
            if hint.phase_id == phase_id:
                relevant_hints.append(hint.hint_text)
                continue

            # Same category (if available on both hint and phase)
            if (
                phase_task_category is not None
                and hint.task_category is not None
                and hint.task_category == phase_task_category
            ):
                relevant_hints.append(hint.hint_text)

        return relevant_hints[:10]  # Limit to top 10

    def get_all_hints(self) -> List[LearningHint]:
        """Get all recorded hints"""
        return self._hints

    def get_hint_count(self) -> int:
        """Get total number of hints recorded"""
        return len(self._hints)

    def clear_hints(self):
        """Clear all hints (useful for testing)"""
        self._hints = []
        logger.debug("[Learning] Cleared all hints")

    def _persist_hint_to_memory(self, hint: LearningHint) -> bool:
        """
        Persist a single hint to memory service immediately.

        This is called from record_hint() to ensure hints are not lost
        when the executor exits. Part of IMP-INT-004.

        Args:
            hint: The LearningHint to persist

        Returns:
            True if persistence succeeded, False otherwise
        """
        if not self._memory_service or not getattr(self._memory_service, "enabled", False):
            return False

        try:
            # Convert LearningHint to telemetry insight format
            insight = {
                "insight_type": self._map_hint_type_to_insight_type(hint.hint_type),
                "description": hint.hint_text,
                "phase_id": hint.phase_id,
                "run_id": self.run_id,
                "suggested_action": hint.hint_text,
                "severity": self._get_hint_severity(hint.hint_type),
                "source_issue_keys": hint.source_issue_keys,
                "task_category": hint.task_category,
            }

            # Use the unified write_telemetry_insight method
            result = self._memory_service.write_telemetry_insight(
                insight=insight,
                project_id=self._project_id,
                validate=True,
                strict=False,
            )

            if result:
                logger.debug(
                    f"[Learning] Persisted hint to memory: {hint.phase_id}/{hint.hint_type}"
                )
                return True

        except Exception as e:
            logger.warning(f"[Learning] Failed to persist hint {hint.phase_id}: {e}")

        return False

    def persist_to_memory(self, memory_service, project_id: Optional[str] = None) -> int:
        """
        Persist accumulated learning hints to memory service.

        This enables cross-run learning by writing hints as telemetry insights
        that can be retrieved in future runs.

        Args:
            memory_service: MemoryService instance (can be None if disabled)
            project_id: Optional project identifier for namespacing

        Returns:
            Number of hints successfully persisted
        """
        if not memory_service or not getattr(memory_service, "enabled", False):
            logger.debug("[Learning] Memory service disabled, skipping hint persistence")
            return 0

        if not self._hints:
            logger.debug("[Learning] No hints to persist")
            return 0

        persisted_count = 0

        for hint in self._hints:
            try:
                # Convert LearningHint to telemetry insight format
                insight = {
                    "insight_type": self._map_hint_type_to_insight_type(hint.hint_type),
                    "description": hint.hint_text,
                    "phase_id": hint.phase_id,
                    "run_id": self.run_id,
                    "suggested_action": hint.hint_text,
                    "severity": self._get_hint_severity(hint.hint_type),
                    "source_issue_keys": hint.source_issue_keys,
                    "task_category": hint.task_category,
                }

                # Use the unified write_telemetry_insight method
                result = memory_service.write_telemetry_insight(
                    insight=insight,
                    project_id=project_id,
                    validate=True,
                    strict=False,
                )

                if result:
                    persisted_count += 1
                    logger.debug(
                        f"[Learning] Persisted hint to memory: {hint.phase_id}/{hint.hint_type}"
                    )

            except Exception as e:
                logger.warning(f"[Learning] Failed to persist hint {hint.phase_id}: {e}")

        logger.info(f"[Learning] Persisted {persisted_count}/{len(self._hints)} hints to memory")
        return persisted_count

    def _map_hint_type_to_insight_type(self, hint_type: str) -> str:
        """Map learning hint types to telemetry insight types."""
        mapping = {
            "auditor_reject": "failure_mode",
            "ci_fail": "failure_mode",
            "patch_apply_error": "failure_mode",
            "infra_error": "retry_cause",
            "success_after_retry": "retry_cause",
            "builder_churn_limit_exceeded": "cost_sink",
            "builder_guardrail": "failure_mode",
            "deliverables_validation_failed": "failure_mode",
        }
        return mapping.get(hint_type, "unknown")

    def _get_hint_severity(self, hint_type: str) -> str:
        """Get severity level for hint type."""
        high_severity = {"ci_fail", "patch_apply_error", "builder_guardrail"}
        medium_severity = {"auditor_reject", "deliverables_validation_failed"}
        low_severity = {"success_after_retry", "infra_error", "builder_churn_limit_exceeded"}

        if hint_type in high_severity:
            return "high"
        elif hint_type in medium_severity:
            return "medium"
        elif hint_type in low_severity:
            return "low"
        return "medium"
