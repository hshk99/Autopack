"""
Intention-First Stuck Handler Module

Extracted from autonomous_executor.py to handle stuck scenarios in intention-first mode (BUILD-161).
When a phase gets stuck (repeated failures, budget exceeded, output truncation), this module
applies intention-aware policies to decide recovery actions.

Key responsibilities:
- Map failure status to stuck reason
- Invoke intention-first stuck policy (decide_stuck_action)
- Handle policy decisions: REPLAN, ESCALATE_MODEL, REDUCE_SCOPE, NEEDS_HUMAN, STOP
- Apply model escalation via routing snapshots
- Generate and apply scope reduction proposals
- Integrate with safety profiles (BUILD-188)

Related modules:
- phase_orchestrator.py: Main execution orchestrator that uses stuck handling
- autopack.autonomous.executor_wiring: Stuck policy implementation
- autopack.stuck_handling: StuckReason and StuckResolutionDecision enums
"""

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class IntentionStuckHandler:
    """
    Handles stuck scenarios in intention-first mode (BUILD-161).

    Uses intention-aware policies to decide appropriate recovery actions
    based on the nature of the stuck scenario and budget constraints.
    """

    def __init__(self):
        """Initialize intention stuck handler."""
        pass

    def handle_stuck_scenario(
        self,
        wiring: Any,
        phase_id: str,
        phase_spec: dict,
        anchor: Any,
        status: str,
        tokens_used: int,
        context_chars_used: int,
        sot_chars_used: int,
        run_budget_tokens: int = 0,
        llm_service: Optional[Any] = None,
    ) -> Tuple[str, str]:
        """
        Handle stuck scenario in intention-first mode.

        Invokes the intention-first stuck policy to decide appropriate action,
        then applies the recommended recovery strategy.

        Args:
            wiring: Intention-first wiring context
            phase_id: Phase identifier
            phase_spec: Phase specification dict
            anchor: Intention anchor
            status: Current failure status
            tokens_used: Tokens used so far (run-level)
            context_chars_used: Context chars used (run-level)
            sot_chars_used: SOT chars used (run-level)
            run_budget_tokens: Total run budget in tokens
            llm_service: LLM service for model escalation

        Returns:
            Tuple of (decision: str, message: str)
            - decision: Action taken (REPLAN, ESCALATE_MODEL, REDUCE_SCOPE, NEEDS_HUMAN, STOP, CONTINUE)
            - message: Human-readable message about the decision
        """
        from autopack.autonomous.executor_wiring import decide_stuck_action
        from autopack.stuck_handling import (StuckReason,
                                             StuckResolutionDecision)

        # Map failure status to stuck reason
        stuck_reason = StuckReason.REPEATED_FAILURES  # Default
        if "BUDGET" in status.upper():
            stuck_reason = StuckReason.BUDGET_EXCEEDED
        elif "TRUNCAT" in status.upper():
            stuck_reason = StuckReason.OUTPUT_TRUNCATION

        try:
            decision, decision_msg = decide_stuck_action(
                wiring=wiring,
                phase_id=phase_id,
                phase_spec=phase_spec,
                anchor=anchor,
                reason=stuck_reason,
                tokens_used=tokens_used,
                context_chars_used=context_chars_used,
                sot_chars_used=sot_chars_used,
            )

            logger.info(f"[IntentionFirst] {decision_msg}")

            # Dispatch based on decision
            if decision == StuckResolutionDecision.REPLAN:
                logger.info(f"[IntentionFirst] Policy decided REPLAN for {phase_id}")
                return "REPLAN", decision_msg

            elif decision == StuckResolutionDecision.ESCALATE_MODEL:
                # Apply model escalation via routing snapshot
                escalation_result = self._apply_model_escalation(
                    wiring=wiring,
                    phase_id=phase_id,
                    phase_spec=phase_spec,
                    anchor=anchor,
                    llm_service=llm_service,
                )
                if escalation_result:
                    return (
                        "ESCALATE_MODEL",
                        f"Escalated to tier {escalation_result['tier']}, {decision_msg}",
                    )
                else:
                    logger.warning(
                        f"[IntentionFirst] Escalation failed for {phase_id}, falling back"
                    )
                    return "CONTINUE", decision_msg

            elif decision == StuckResolutionDecision.REDUCE_SCOPE:
                # Apply scope reduction with proposal generation
                scope_result = self._apply_scope_reduction(
                    phase_id=phase_id,
                    phase_spec=phase_spec,
                    anchor=anchor,
                    tokens_used=tokens_used,
                    run_budget_tokens=run_budget_tokens,
                )
                if scope_result:
                    return (
                        "REDUCE_SCOPE",
                        f"Reduced scope from {scope_result['original_count']} to {scope_result['new_count']} tasks, {decision_msg}",
                    )
                else:
                    logger.warning(
                        "[IntentionFirst] Scope reduction failed, falling back to existing logic"
                    )
                    return "CONTINUE", decision_msg

            elif decision == StuckResolutionDecision.NEEDS_HUMAN:
                logger.critical(f"[IntentionFirst] Policy decided NEEDS_HUMAN for {phase_id}")
                return "BLOCKED_NEEDS_HUMAN", decision_msg

            elif decision == StuckResolutionDecision.STOP:
                logger.critical(
                    f"[IntentionFirst] Policy decided STOP for {phase_id} - budget exhausted or max retries"
                )
                return "STOP", decision_msg

            # Default: continue with retry
            return "CONTINUE", decision_msg

        except Exception as e:
            logger.warning(
                f"[IntentionFirst] Stuck decision failed: {e}, falling back to existing logic"
            )
            return "CONTINUE", f"Stuck handling failed: {e}"

    def _apply_model_escalation(
        self,
        wiring: Any,
        phase_id: str,
        phase_spec: dict,
        anchor: Any,
        llm_service: Optional[Any],
    ) -> Optional[dict]:
        """
        Apply model escalation via routing snapshot.

        Args:
            wiring: Intention-first wiring context
            phase_id: Phase identifier
            phase_spec: Phase specification dict
            anchor: Intention anchor
            llm_service: LLM service for escalation

        Returns:
            Dict with escalation result (tier, model_id) or None if failed
        """
        try:
            from autopack.autonomous.executor_wiring import \
                apply_model_escalation
            from autopack.executor.safety_profile import derive_safety_profile

            current_tier = phase_spec.get("_current_tier", "haiku")  # Default to haiku

            # BUILD-188 P5.5: Derive safety profile from intention anchor
            # Validate anchor exists and is usable before passing to derive_safety_profile
            if anchor is None:
                logger.debug("No anchor provided, using default safety profile")
                safety_profile = "strict"  # Fail-safe default
            else:
                is_valid, errors = anchor.validate_for_consumption()
                if not is_valid:
                    logger.warning(
                        f"Anchor validation failed: {errors}, using default safety profile"
                    )
                    safety_profile = "strict"
                else:
                    safety_profile = derive_safety_profile(anchor)

            escalated_entry = apply_model_escalation(
                wiring=wiring,
                phase_id=phase_id,
                phase_spec=phase_spec,
                current_tier=current_tier,
                safety_profile=safety_profile,
            )

            if escalated_entry:
                logger.info(
                    f"[IntentionFirst] Escalated {phase_id} to tier {escalated_entry.tier} "
                    f"(model: {escalated_entry.model_id})"
                )
                phase_spec["_current_tier"] = escalated_entry.tier
                # The run_context overrides are now set, llm_service will use them
                return {
                    "tier": escalated_entry.tier,
                    "model_id": escalated_entry.model_id,
                }
            else:
                return None

        except Exception as e:
            logger.warning(f"[IntentionFirst] Model escalation failed: {e}")
            return None

    def _apply_scope_reduction(
        self,
        phase_id: str,
        phase_spec: dict,
        anchor: Any,
        tokens_used: int,
        run_budget_tokens: int,
    ) -> Optional[dict]:
        """
        Apply scope reduction with proposal generation (BUILD-190).

        Args:
            phase_id: Phase identifier
            phase_spec: Phase specification dict
            anchor: Intention anchor
            tokens_used: Tokens used so far
            run_budget_tokens: Total run budget in tokens

        Returns:
            Dict with scope reduction result (original_count, new_count, dropped_items) or None
        """
        try:
            from autopack.executor.scope_reduction_flow import \
                generate_scope_reduction_proposal as gen_scope_proposal
            from autopack.executor.scope_reduction_flow import \
                write_scope_reduction_proposal
            from autopack.run_file_layout import RunFileLayout

            logger.info(f"[IntentionFirst] Policy decided REDUCE_SCOPE for {phase_id}")

            # Extract current scope from phase
            current_tasks = phase_spec.get("tasks", [])
            if not current_tasks:
                # Fallback: use deliverables as scope proxy
                current_tasks = phase_spec.get("deliverables", [])

            if not current_tasks:
                logger.warning("[IntentionFirst] No tasks to reduce scope from")
                return None

            # Compute budget remaining
            budget_remaining = 1.0 - (tokens_used / max(run_budget_tokens, 1))
            budget_remaining = max(0.0, min(1.0, budget_remaining))

            # Generate scope reduction proposal
            proposal = gen_scope_proposal(
                run_id="",  # Would need run_id
                phase_id=phase_id,
                anchor=anchor,
                current_scope=current_tasks,
                budget_remaining=budget_remaining,
            )

            if not (proposal and proposal.proposed_scope):
                logger.warning("[IntentionFirst] Scope reduction proposal was empty")
                return None

            # Write proposal as artifact (best effort)
            try:
                layout = RunFileLayout("", project_id="")  # Would need actual values
                write_scope_reduction_proposal(layout, proposal)
            except Exception as write_err:
                logger.warning(f"[IntentionFirst] Failed to write scope proposal: {write_err}")

            # Apply reduced scope to phase
            original_count = len(current_tasks)
            phase_spec["tasks"] = proposal.proposed_scope
            phase_spec["_scope_reduced"] = True
            phase_spec["_dropped_tasks"] = proposal.dropped_items

            logger.info(
                f"[IntentionFirst] Reduced scope from {original_count} to "
                f"{len(proposal.proposed_scope)} tasks (dropped: {proposal.dropped_items})"
            )

            return {
                "original_count": original_count,
                "new_count": len(proposal.proposed_scope),
                "dropped_items": proposal.dropped_items,
            }

        except Exception as e:
            logger.warning(f"[IntentionFirst] Scope reduction failed: {e}")
            return None
