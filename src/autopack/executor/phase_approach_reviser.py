"""Phase approach revision for stuck/failed phases.

Extracted from autonomous_executor.py as part of PR-EXE-13.
Handles revising phase approach when current strategy isn't working.
"""

from dataclasses import dataclass
from typing import Dict, Optional, List, TYPE_CHECKING
import time
import logging

from autopack.archive_consolidator import log_build_event

if TYPE_CHECKING:
    from ..autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


@dataclass
class RevisedApproach:
    """Result of approach revision."""

    success: bool
    revised_phase: Optional[Dict] = None
    error_message: Optional[str] = None


class PhaseApproachReviser:
    """Revises phase approach when stuck or repeatedly failing.

    Responsibilities:
    1. Analyze phase failure patterns
    2. Generate alternative approaches
    3. Apply approach revisions
    4. Track revision history
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def revise_approach(
        self,
        phase: Dict,
        flaw_type: str,
        error_history: List[Dict],
    ) -> Optional[Dict]:
        """Revise phase approach based on failure history.

        Invoke LLM to revise the phase approach based on failure context.

        This is the core of mid-run re-planning: we ask the LLM to analyze
        what went wrong and provide a revised implementation approach.

        Per GPT_RESPONSE27: Now includes Goal Anchoring to prevent context drift:
        - Stores and references original_intent
        - Includes hard constraint in prompt
        - Classifies alignment of revision
        - Records telemetry for monitoring

        Args:
            phase: Original phase specification
            flaw_type: Detected flaw type
            error_history: History of errors for this phase

        Returns:
            Revised phase specification dict, or None if revision failed
        """
        phase_id = phase.get("phase_id")
        phase_name = phase.get("name", phase_id)
        current_description = phase.get("description", "")

        # [Goal Anchoring] Initialize if this is the first replan for this phase
        self.executor._initialize_phase_goal_anchor(phase)

        # Get the true original intent (before any replanning)
        original_intent = self.executor._phase_original_intent.get(phase_id, "")
        original_description = self.executor._phase_original_description.get(
            phase_id, current_description
        )
        replan_attempt = len(self.executor._phase_replan_history.get(phase_id, [])) + 1

        logger.info(
            f"[Re-Plan] Revising approach for {phase_id} due to {flaw_type} (attempt {replan_attempt})"
        )
        logger.info(f"[GoalAnchor] Original intent: {original_intent[:100]}...")

        # Build context from error history
        error_summary = "\n".join(
            [
                f"- Attempt {e['attempt'] + 1}: {e['error_type']} - {e['error_details'][:200]}"
                for e in error_history[-5:]  # Last 5 errors
            ]
        )

        # Get any run hints that might help
        learning_context = self.executor._get_learning_context_for_phase(phase) or {}
        hints_summary = "\n".join(
            [f"- {hint}" for hint in learning_context.get("run_hints", [])[:3]]
        )

        # [Goal Anchoring] Per GPT_RESPONSE27: Include original_intent with HARD CONSTRAINT
        replan_prompt = f"""You are a senior software architect. A phase in our automated build system has failed repeatedly with the same error pattern. Your task is to analyze the failures and provide a revised implementation approach.

## Original Phase Specification
**Phase**: {phase_name}
**Description**: {current_description}
**Category**: {phase.get('task_category', 'general')}
**Complexity**: {phase.get('complexity', 'medium')}

## Error Pattern Detected
**Flaw Type**: {flaw_type}
**Recent Errors**:
{error_summary}

## Learning Hints from Earlier Phases
{hints_summary if hints_summary else "(No hints available)"}

## CRITICAL CONSTRAINT - GOAL ANCHORING
The revised approach MUST still achieve this core goal:
**Original Intent**: {original_intent}

Do NOT reduce scope, skip functionality, or change what the phase achieves.
Only change HOW it achieves the goal, not WHAT it achieves.

## Your Task
Analyze why the current approach kept failing and provide a REVISED description that:
1. MAINTAINS the original intent and scope (CRITICAL - no scope reduction)
2. Addresses the root cause of the repeated failures
3. Uses a different implementation strategy if needed
4. Includes specific guidance to avoid the detected error pattern

## Output Format
Provide ONLY the revised description text. Do not include JSON, markdown headers, or explanations.
Just the new description that should replace the current one while preserving the original goal.
"""

        try:
            # Use LlmService to invoke planner (use strongest model for replanning)
            if not self.executor.llm_service:
                logger.error("[Re-Plan] LlmService not initialized")
                return None

            # NOTE: Re-planning is best-effort. If Anthropic is disabled/unavailable (e.g., credits exhausted),
            # skip replanning rather than spamming repeated 400s.
            try:
                if hasattr(self.executor.llm_service, "model_router") and "anthropic" in getattr(
                    self.executor.llm_service.model_router, "disabled_providers", set()
                ):
                    logger.info(
                        "[Re-Plan] Skipping re-planning because provider 'anthropic' is disabled for this run/process"
                    )
                    return None
            except Exception:
                pass

            # Current implementation uses Anthropic directly for replanning; require key.
            import os

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.info("[Re-Plan] Skipping re-planning because ANTHROPIC_API_KEY is not set")
                return None

            # Use Claude for re-planning (strongest model)
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",  # Use strong model for re-planning
                max_tokens=2000,
                messages=[{"role": "user", "content": replan_prompt}],
            )

            # Defensive: ensure response has text content
            content_blocks = getattr(response, "content", None) or []
            first_block = content_blocks[0] if content_blocks else None
            revised_description = (getattr(first_block, "text", "") or "").strip()

            if not revised_description or len(revised_description) < 20:
                logger.error("[Re-Plan] LLM returned empty or too-short revision")
                # Record failed replan telemetry
                self.executor._record_replan_telemetry(
                    phase_id=phase_id,
                    attempt=replan_attempt,
                    original_description=original_description,
                    revised_description="",
                    reason=flaw_type,
                    alignment={"alignment": "failed", "notes": "LLM returned empty revision"},
                    success=False,
                )
                return None

            # [Goal Anchoring] Classify alignment of revision vs original intent
            alignment = self.executor._classify_replan_alignment(original_intent, revised_description)

            # Log alignment classification
            logger.info(
                f"[GoalAnchor] Alignment classification: {alignment.get('alignment')} - {alignment.get('notes')}"
            )

            # [Goal Anchoring] Warn if scope appears narrowed (but don't block in Phase 1)
            if alignment.get("alignment") == "narrower":
                logger.warning(
                    f"[GoalAnchor] WARNING: Revision appears to narrow scope for {phase_id}. "
                    f"Original intent: '{original_intent[:50]}...' "
                    f"This may indicate goal drift."
                )

            # Create revised phase spec
            revised_phase = phase.copy()
            revised_phase["description"] = revised_description
            revised_phase["_original_description"] = original_description
            revised_phase["_original_intent"] = original_intent  # [Goal Anchoring]
            revised_phase["_revision_reason"] = f"Approach flaw: {flaw_type}"
            revised_phase["_revision_timestamp"] = time.time()
            revised_phase["_revision_alignment"] = alignment  # [Goal Anchoring]

            logger.info(f"[Re-Plan] Successfully revised phase {phase_id}")
            logger.info(f"[Re-Plan] Original: {original_description[:100]}...")
            logger.info(f"[Re-Plan] Revised: {revised_description[:100]}...")

            # Store and track
            self.executor._phase_revised_specs[phase_id] = revised_phase
            self.executor._phase_revised_specs[f"_replan_count_{phase_id}"] = (
                self.executor._get_replan_count(phase_id) + 1
            )

            # Clear error history for fresh start with new approach
            self.executor._phase_error_history[phase_id] = []

            # [Goal Anchoring] Record telemetry (success will be updated later if phase succeeds)
            self.executor._record_replan_telemetry(
                phase_id=phase_id,
                attempt=replan_attempt,
                original_description=original_description,
                revised_description=revised_description,
                reason=flaw_type,
                alignment=alignment,
                success=False,  # Will be updated if phase eventually succeeds
            )

            # Record this re-planning event
            log_build_event(
                event_type="PHASE_REPLANNED",
                description=f"Phase {phase_id} replanned due to {flaw_type}. Alignment: {alignment.get('alignment')}. Original: '{original_description[:50]}...' -> Revised approach applied.",
                deliverables=[
                    f"Run: {self.executor.run_id}",
                    f"Phase: {phase_id}",
                    f"Flaw: {flaw_type}",
                    f"Alignment: {alignment.get('alignment')}",
                ],
                project_slug=self.executor._get_project_slug(),
            )

            # Record plan change + decision log for memory/DB
            try:
                self.executor._record_plan_change_entry(
                    summary=f"{phase_id} replanned (attempt {replan_attempt})",
                    rationale=f"flaw={flaw_type}; alignment={alignment.get('alignment')}",
                    phase_id=phase_id,
                    replaces_version=replan_attempt - 1 if replan_attempt > 1 else None,
                )
                self.executor._record_decision_entry(
                    trigger=f"replan:{flaw_type}",
                    choice="replan",
                    rationale=f"Replanned to address {flaw_type}",
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )
            except Exception as log_exc:
                logger.warning(f"[Re-Plan] Telemetry write failed: {log_exc}")

            return revised_phase

        except Exception as e:
            logger.error(f"[Re-Plan] Failed to revise phase: {e}")
            # Record failed replan telemetry
            self.executor._record_replan_telemetry(
                phase_id=phase_id,
                attempt=replan_attempt,
                original_description=original_description,
                revised_description="",
                reason=flaw_type,
                alignment={"alignment": "error", "notes": str(e)},
                success=False,
            )
            return None
