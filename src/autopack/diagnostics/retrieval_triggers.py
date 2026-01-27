"""Stage 2A: Retrieval Triggers - Detect when Stage 1 evidence lacks sufficient signal.

This module analyzes handoff bundles from Stage 1 (health_checks.py) to determine
if deep retrieval escalation is needed. Triggers fire when:
- Handoff bundle is empty or minimal
- Error messages lack actionable context
- Recent phase history shows repeated failures
- No clear root cause identified in Stage 1

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class RetrievalTrigger:
    """Analyzes Stage 1 handoff bundles to determine if deep retrieval is needed."""

    def __init__(self, run_dir: Path):
        """Initialize retrieval trigger analyzer.

        Args:
            run_dir: Path to .autonomous_runs/<run_id> directory
        """
        self.run_dir = run_dir
        self.logger = logger

    def should_escalate(
        self, handoff_bundle: Dict[str, Any], phase_id: str, attempt_number: int
    ) -> bool:
        """Determine if deep retrieval escalation is needed.

        Args:
            handoff_bundle: Stage 1 evidence bundle from health_checks.py
            phase_id: Current phase identifier
            attempt_number: Current attempt number (1-indexed)

        Returns:
            True if deep retrieval should be triggered, False otherwise
        """
        # Trigger 1: Empty or minimal handoff bundle
        if self._is_bundle_insufficient(handoff_bundle):
            self.logger.info(
                f"[RetrievalTrigger] Phase {phase_id} attempt {attempt_number}: "
                f"Handoff bundle insufficient - triggering deep retrieval"
            )
            return True

        # Trigger 2: Error messages lack actionable context
        if self._lacks_actionable_context(handoff_bundle):
            self.logger.info(
                f"[RetrievalTrigger] Phase {phase_id} attempt {attempt_number}: "
                f"Error messages lack context - triggering deep retrieval"
            )
            return True

        # Trigger 3: Repeated failures in recent history
        if attempt_number >= 2 and self._has_repeated_failures(phase_id):
            self.logger.info(
                f"[RetrievalTrigger] Phase {phase_id} attempt {attempt_number}: "
                f"Repeated failures detected - triggering deep retrieval"
            )
            return True

        # Trigger 4: No clear root cause in Stage 1
        if not self._has_clear_root_cause(handoff_bundle):
            self.logger.info(
                f"[RetrievalTrigger] Phase {phase_id} attempt {attempt_number}: "
                f"No clear root cause - triggering deep retrieval"
            )
            return True

        self.logger.debug(
            f"[RetrievalTrigger] Phase {phase_id} attempt {attempt_number}: "
            f"Stage 1 evidence sufficient - no escalation needed"
        )
        return False

    def _is_bundle_insufficient(self, bundle: Dict[str, Any]) -> bool:
        """Check if handoff bundle is empty or minimal.

        Args:
            bundle: Stage 1 handoff bundle

        Returns:
            True if bundle lacks sufficient evidence
        """
        if not bundle:
            return True

        # Check for minimal content
        error_msg = bundle.get("error_message", "")
        stack_trace = bundle.get("stack_trace", "")
        recent_changes = bundle.get("recent_changes", [])

        # Bundle is insufficient if all fields are empty/minimal
        has_error = len(error_msg) > 20
        has_trace = len(stack_trace) > 50
        has_changes = len(recent_changes) > 0

        return not (has_error or has_trace or has_changes)

    def _lacks_actionable_context(self, bundle: Dict[str, Any]) -> bool:
        """Check if error messages lack actionable debugging context.

        Args:
            bundle: Stage 1 handoff bundle

        Returns:
            True if errors are too generic to act on
        """
        error_msg = bundle.get("error_message", "")
        if not error_msg:
            return True

        # Generic error patterns that lack actionable context
        generic_patterns = [
            "unknown error",
            "internal error",
            "something went wrong",
            "failed to execute",
            "unexpected error",
        ]

        error_lower = error_msg.lower()
        for pattern in generic_patterns:
            if pattern in error_lower:
                return True

        # Check if error message is too short to be useful
        if len(error_msg) < 30:
            return True

        return False

    def _has_repeated_failures(self, phase_id: str) -> bool:
        """Check if phase has failed multiple times recently.

        Args:
            phase_id: Phase identifier

        Returns:
            True if phase has 2+ failures in recent history
        """
        # Look for phase-specific log files in run directory
        log_pattern = f"*{phase_id}*.log"
        log_files = list(self.run_dir.glob(log_pattern))

        if not log_files:
            return False

        # Count failure markers in recent logs
        failure_count = 0
        for log_file in log_files:
            try:
                content = log_file.read_text(encoding="utf-8")
                # Look for failure indicators
                if "ERROR" in content or "FAILED" in content:
                    failure_count += 1
            except Exception as e:
                self.logger.debug(f"Could not read log {log_file}: {e}")
                continue

        return failure_count >= 2

    def _has_clear_root_cause(self, bundle: Dict[str, Any]) -> bool:
        """Check if Stage 1 identified a clear root cause.

        Args:
            bundle: Stage 1 handoff bundle

        Returns:
            True if root cause is clearly identified
        """
        root_cause = bundle.get("root_cause", "")
        if not root_cause:
            return False

        # Root cause should be specific and actionable
        # Generic phrases indicate unclear diagnosis
        unclear_patterns = [
            "unknown",
            "unclear",
            "investigat",  # Matches both "investigate" and "investigation"
            "needs analysis",
            "not determined",
        ]

        root_cause_lower = root_cause.lower()
        for pattern in unclear_patterns:
            if pattern in root_cause_lower:
                return False

        # Root cause should have reasonable length
        if len(root_cause) < 20:
            return False

        return True

    def get_retrieval_priority(self, bundle: Dict[str, Any]) -> str:
        """Determine retrieval priority based on bundle analysis.

        Args:
            bundle: Stage 1 handoff bundle

        Returns:
            Priority level: 'high', 'medium', or 'low'
        """
        # High priority: Multiple triggers fired
        trigger_count = sum(
            [
                self._is_bundle_insufficient(bundle),
                self._lacks_actionable_context(bundle),
                not self._has_clear_root_cause(bundle),
            ]
        )

        if trigger_count >= 2:
            return "high"
        elif trigger_count == 1:
            return "medium"
        else:
            return "low"


# --- Compatibility API used by tests (BUILD-112 validation suite) ---


class RetrievalTriggerDetector:
    """Simple Stage-2 escalation detector used by unit tests.

    This class intentionally implements a minimal heuristic contract:
    - Escalate on 3rd attempt (or later) if failures persist.
    - Escalate on 'complex' error patterns (multiple distinct error types).
    - Do not escalate on first attempt or trivial single-error scenarios.
    """

    def should_escalate_to_stage2(
        self,
        phase_id: str,
        attempt_number: int,
        previous_errors: List[str],
        stage1_retrieval_count: int,
    ) -> bool:
        # Never on first attempt.
        if attempt_number <= 1:
            return False

        # Escalate after 3 attempts regardless of error type.
        if attempt_number >= 3:
            return True

        # Attempt 2: escalate if we see multiple distinct error categories.
        kinds = set()
        for e in previous_errors:
            if not e:
                continue
            head = e.split(":")[0].strip()
            kinds.add(head)

        if len(kinds) >= 3:
            return True

        return False
