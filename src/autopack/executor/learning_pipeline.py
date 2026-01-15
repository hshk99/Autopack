"""
Learning Pipeline Module

Records lessons learned during troubleshooting to help:
1. Later phases in the same run (Stage 0A - within-run hints)
2. Future runs after promotion (Stage 0B - cross-run hints)
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import time
import logging

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

    def __init__(self, run_id: str):
        """
        Initialize LearningPipeline.

        Args:
            run_id: Run identifier for tracking hints
        """
        self.run_id = run_id
        self._hints: List[LearningHint] = []

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

            # Note: Integration with actual hint storage system (save_run_hint)
            # is handled by the caller in autonomous_executor.py to maintain
            # backward compatibility during the refactoring.

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
