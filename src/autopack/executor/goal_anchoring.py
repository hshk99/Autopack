"""
Goal Anchoring Module

Extracted from autonomous_executor.py to manage goal anchoring and re-planning telemetry.
Per GPT_RESPONSE27: Prevents context drift during re-planning by tracking original intent.

Key responsibilities:
- Extract and store one-line intent from phase descriptions
- Initialize goal anchors before any re-planning occurs
- Detect scope narrowing using heuristics
- Classify alignment of revised descriptions vs original intent
- Record re-planning telemetry for monitoring
- Persist plan changes and decision logs to memory

Related modules:
- phase_approach_reviser.py: Uses goal anchoring for approach revision
- replan_trigger.py: Triggers re-planning based on error patterns
- learning_pipeline.py: Records learning hints based on phase outcomes
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GoalAnchorState:
    """State container for goal anchoring tracking."""

    # Per-phase tracking
    phase_original_intent: Dict[str, str] = field(default_factory=dict)
    phase_original_description: Dict[str, str] = field(default_factory=dict)
    phase_replan_history: Dict[str, List[Dict]] = field(default_factory=dict)

    # Run-level telemetry
    run_replan_telemetry: List[Dict] = field(default_factory=list)


class GoalAnchoringManager:
    """
    Manages goal anchoring and re-planning telemetry.

    Per GPT_RESPONSE27: Stores original intent before any re-planning occurs
    to prevent context drift.
    """

    def __init__(self, run_id: str, memory_service: Optional[Any] = None):
        """
        Initialize goal anchoring manager.

        Args:
            run_id: Run identifier for telemetry
            memory_service: Optional MemoryService for persisting plan changes
        """
        self.run_id = run_id
        self.memory_service = memory_service
        self.state = GoalAnchorState()

    def extract_one_line_intent(self, description: str) -> str:
        """
        Extract a concise one-line intent from a phase description.

        Per GPT_RESPONSE27: The original_intent should be a short, clear statement
        of WHAT the phase achieves (not HOW it achieves it).

        Args:
            description: Full phase description

        Returns:
            One-line intent statement (first sentence, capped at 200 chars)
        """
        if not description:
            return ""

        # Get first sentence (ends with . ! or ?)
        first_sentence_match = re.match(r"^[^.!?]*[.!?]", description.strip())
        if first_sentence_match:
            intent = first_sentence_match.group(0).strip()
        else:
            # No sentence ending found, use first 200 chars
            intent = description.strip()[:200]
            if len(description.strip()) > 200:
                intent += "..."

        # Cap at 200 chars
        if len(intent) > 200:
            intent = intent[:197] + "..."

        return intent

    def initialize_phase_goal_anchor(self, phase: Dict) -> None:
        """
        Initialize goal anchoring for a phase on first execution.

        Per GPT_RESPONSE27 Phase 1 Implementation: Store original intent and description
        before any re-planning occurs.

        Args:
            phase: Phase specification dict
        """
        phase_id = phase.get("phase_id")
        if not phase_id:
            return

        # Only initialize once (on first execution)
        if phase_id not in self.state.phase_original_intent:
            description = phase.get("description", "")
            self.state.phase_original_intent[phase_id] = self.extract_one_line_intent(description)
            self.state.phase_original_description[phase_id] = description
            self.state.phase_replan_history[phase_id] = []

            logger.debug(
                f"[GoalAnchor] Initialized for {phase_id}: "
                f"intent='{self.state.phase_original_intent[phase_id][:50]}...'"
            )

    def detect_scope_narrowing(self, original: str, revised: str) -> bool:
        """
        Detect obvious scope narrowing using heuristics.

        Per GPT_RESPONSE27: Fast pre-filter to detect when revision reduces scope.

        Args:
            original: Original phase description
            revised: Revised phase description

        Returns:
            True if scope narrowing is detected
        """
        if not original or not revised:
            return False

        # Heuristic 1: Significant length shrinkage (>50%)
        if len(revised) < len(original) * 0.5:
            logger.debug("[GoalAnchor] Scope narrowing detected: length shrinkage")
            return True

        # Heuristic 2: Scope-reducing keywords
        scope_reducing_keywords = [
            "only",
            "just",
            "skip",
            "ignore",
            "defer",
            "later",
            "simplified",
            "minimal",
            "basic",
            "stub",
            "placeholder",
            "without",
            "except",
            "excluding",
            "partial",
        ]

        original_lower = original.lower()
        revised_lower = revised.lower()

        for keyword in scope_reducing_keywords:
            # Check if keyword was added in revision
            if keyword in revised_lower and keyword not in original_lower:
                logger.debug(f"[GoalAnchor] Scope narrowing detected: added keyword '{keyword}'")
                return True

        return False

    def classify_replan_alignment(
        self, original_intent: str, revised_description: str
    ) -> Dict[str, Any]:
        """
        Classify alignment of revised description vs original intent.

        Per GPT_RESPONSE27: Use heuristics to semantically compare original intent with
        revised approach to detect goal drift.

        Args:
            original_intent: One-line intent from original description
            revised_description: New description after re-planning

        Returns:
            Dict with {"alignment": "same_scope|narrower|broader|different_domain", "notes": "..."}
        """
        # First, apply fast heuristic pre-filter
        if self.detect_scope_narrowing(original_intent, revised_description):
            return {
                "alignment": "narrower",
                "notes": "Heuristic detection: revision appears to reduce scope",
            }

        # For Phase 1, we use simple heuristics + logging (no LLM call)
        # Per GPT_RESPONSE27: Full semantic classification is Phase 2

        # Simple keyword-based classification
        revised_lower = revised_description.lower()

        # Check for scope expansion
        expansion_keywords = ["also", "additionally", "expand", "enhance", "add more", "including"]
        has_expansion = any(kw in revised_lower for kw in expansion_keywords)

        # Check for domain change (different technology/approach)
        if has_expansion:
            return {"alignment": "broader", "notes": "Revision appears to expand scope"}

        # Default: assume same scope (conservative for Phase 1)
        return {
            "alignment": "same_scope",
            "notes": "No obvious scope change detected (Phase 1 heuristic)",
        }

    def record_replan_telemetry(
        self,
        phase_id: str,
        attempt: int,
        original_description: str,
        revised_description: str,
        reason: str,
        alignment: Dict[str, Any],
        success: bool,
    ) -> None:
        """
        Record re-planning telemetry for monitoring and analysis.

        Per GPT_RESPONSE27: Track replan_count, alignment, and outcomes.

        Args:
            phase_id: Phase identifier
            attempt: Re-plan attempt number
            original_description: Description before revision
            revised_description: Description after revision
            reason: Why re-planning was triggered
            alignment: Alignment classification result
            success: Whether the re-planning resulted in eventual phase success
        """
        telemetry_record = {
            "run_id": self.run_id,
            "phase_id": phase_id,
            "attempt": attempt,
            "timestamp": time.time(),
            "reason": reason,
            "alignment": alignment.get("alignment", "unknown"),
            "alignment_notes": alignment.get("notes", ""),
            "original_description_preview": original_description[:100],
            "revised_description_preview": revised_description[:100],
            "success": success,
        }

        # Add to phase-level history
        if phase_id not in self.state.phase_replan_history:
            self.state.phase_replan_history[phase_id] = []
        self.state.phase_replan_history[phase_id].append(telemetry_record)

        # Add to run-level telemetry
        self.state.run_replan_telemetry.append(telemetry_record)

        # Log for observability
        logger.info(
            f"[GoalAnchor] REPLAN_TELEMETRY: run_id={self.run_id} phase_id={phase_id} "
            f"attempt={attempt} alignment={alignment.get('alignment')} "
            f"replan_count_phase={len(self.state.phase_replan_history.get(phase_id, []))} "
            f"replan_count_run={len(self.state.run_replan_telemetry)}"
        )

    def record_plan_change_entry(
        self,
        summary: str,
        rationale: str,
        phase_id: Optional[str],
        project_id: str,
        replaces_version: Optional[int] = None,
    ) -> None:
        """
        Persist plan change to memory.

        Args:
            summary: Brief summary of the plan change
            rationale: Reason for the change
            phase_id: Phase identifier (if applicable)
            project_id: Project identifier
            replaces_version: Version being replaced (if applicable)
        """
        timestamp = datetime.now(timezone.utc)

        if self.memory_service:
            try:
                self.memory_service.write_plan_change(
                    summary=summary,
                    rationale=rationale,
                    project_id=project_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    replaces_version=replaces_version,
                    timestamp=timestamp.isoformat(),
                )
            except Exception as e:
                logger.warning(f"[PlanChange] Failed to write to memory: {e}")

        # BUILD-115: models.PlanChange removed - skip database write
        logger.debug("[PlanChange] Skipped DB write (models.py removed)")

    def record_decision_entry(
        self,
        trigger: str,
        choice: str,
        rationale: str,
        phase_id: Optional[str],
        project_id: str,
        alternatives: Optional[str] = None,
    ) -> None:
        """
        Persist decision log with memory embedding.

        Args:
            trigger: What triggered the decision (e.g., "doctor", "replan")
            choice: The decision made
            rationale: Reason for the decision
            phase_id: Phase identifier (if applicable)
            project_id: Project identifier
            alternatives: Alternative choices considered
        """
        timestamp = datetime.now(timezone.utc)

        if self.memory_service:
            try:
                self.memory_service.write_decision_log(
                    trigger=trigger,
                    choice=choice,
                    rationale=rationale,
                    project_id=project_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    alternatives=alternatives,
                    timestamp=timestamp.isoformat(),
                )
            except Exception as e:
                logger.warning(f"[DecisionLog] Failed to write to memory: {e}")

        # BUILD-115: models.DecisionLog removed - skip database write
        logger.debug("[DecisionLog] Skipped DB write (models.py removed)")

    def get_original_intent(self, phase_id: str) -> Optional[str]:
        """Get the original intent for a phase."""
        return self.state.phase_original_intent.get(phase_id)

    def get_original_description(self, phase_id: str) -> Optional[str]:
        """Get the original description for a phase."""
        return self.state.phase_original_description.get(phase_id)

    def get_replan_history(self, phase_id: str) -> List[Dict]:
        """Get the replan history for a phase."""
        return self.state.phase_replan_history.get(phase_id, [])

    def mark_replan_successful(self, phase_id: str) -> bool:
        """
        Mark the most recent replan as successful.

        Called when a phase completes successfully after re-planning.

        Args:
            phase_id: Phase identifier

        Returns:
            True if a replan record was updated
        """
        if phase_id not in self.state.phase_replan_history:
            return False

        history = self.state.phase_replan_history[phase_id]
        if not history:
            return False

        # Mark the most recent replan as successful
        for replan_record in reversed(history):
            if not replan_record.get("success", False):
                replan_record["success"] = True
                logger.debug(
                    f"[GoalAnchor] Marked replan attempt {replan_record.get('attempt')} "
                    f"as successful for {phase_id}"
                )
                return True

        return False
