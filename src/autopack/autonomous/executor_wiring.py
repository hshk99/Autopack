"""
Minimal executor wiring for intention-first autonomy loop.

This module provides thin integration helpers that autonomous_executor.py can use
without requiring a massive refactor. Keeps wiring localized and testable.

Implements:
- Run-start initialization (IntentionFirstLoop + routing snapshot)
- Per-phase state tracking (PhaseLoopState dictionary)
- Stuck decision dispatch (REPLAN/ESCALATE/REDUCE_SCOPE/NEEDS_HUMAN/STOP)
- Phase proof persistence after completion

All wiring is minimal and preserves existing executor behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from autopack.autonomous.budgeting import BudgetInputs, compute_budget_remaining
from autopack.autonomous.intention_first_loop import (
    IntentionFirstLoop,
    PhaseLoopState,
    RunLoopState,
)
from autopack.config import settings
from autopack.intention_anchor.models import IntentionAnchor
from autopack.model_routing_snapshot import ModelRoutingEntry
from autopack.phase_proof import PhaseProof, PhaseProofStorage
from autopack.scope_reduction import ScopeReductionProposal
from autopack.stuck_handling import StuckReason, StuckResolutionDecision

logger = logging.getLogger(__name__)


# Deterministic tier-to-complexity mapping (for ModelRouter override integration)
TIER_TO_COMPLEXITY = {"haiku": "low", "sonnet": "medium", "opus": "high"}


@dataclass
class ExecutorWiringState:
    """
    State container for intention-first loop integration.

    Holds loop instance, run state, and per-phase state tracking.
    """

    loop: IntentionFirstLoop
    run_state: RunLoopState
    phase_states: dict[str, PhaseLoopState] = field(default_factory=dict)
    run_context: dict[str, Any] = field(default_factory=dict)


def initialize_intention_first_loop(
    run_id: str,
    project_id: str | None,
    intention_anchor: IntentionAnchor,
) -> ExecutorWiringState:
    """
    Initialize intention-first loop for run (INSERTION POINT 1).

    This is called once at run start, before any phases execute.

    Args:
        run_id: Run ID
        project_id: Project ID (optional)
        intention_anchor: Loaded intention anchor (authoritative)

    Returns:
        ExecutorWiringState with initialized loop and run state
    """
    logger.info(
        f"[IntentionFirstLoop] Initializing for run {run_id}, project {project_id}"
    )

    # Create loop instance
    loop = IntentionFirstLoop()

    # Initialize run state (creates/loads routing snapshot)
    run_state = loop.on_run_start(run_id=run_id, project_id=project_id)

    logger.info(
        f"[IntentionFirstLoop] Routing snapshot created: {run_state.routing_snapshot.snapshot_id}"
    )
    logger.info(
        f"[IntentionFirstLoop] Available tiers: {[e.tier for e in run_state.routing_snapshot.entries]}"
    )

    # Create run_context for LlmService calls with initial routing overrides
    run_context: dict[str, Any] = {"model_overrides": {"builder": {}, "auditor": {}}}

    # Apply initial routing snapshot entries as overrides (Phase E)
    # This ensures the snapshot actually influences model selection from the start
    for entry in run_state.routing_snapshot.entries:
        complexity = TIER_TO_COMPLEXITY.get(entry.tier, "medium")
        # Apply to all task categories for this complexity level
        # NOTE: This is a coarse-grained approach; phase-specific overrides during
        # escalation will use task_category from phase spec for fine-grained control
        for task_category in ["general", "code_generation", "code_review", "analysis"]:
            override_key = f"{task_category}:{complexity}"
            run_context["model_overrides"]["builder"][override_key] = entry.model_id
            run_context["model_overrides"]["auditor"][override_key] = entry.model_id

    logger.info(
        f"[IntentionFirstLoop] Applied {len(run_state.routing_snapshot.entries)} "
        f"routing overrides to run_context"
    )

    return ExecutorWiringState(
        loop=loop,
        run_state=run_state,
        phase_states={},
        run_context=run_context,
    )


def get_or_create_phase_state(
    wiring: ExecutorWiringState, phase_id: str
) -> PhaseLoopState:
    """
    Get or create phase state (INSERTION POINT 2).

    Maintains per-phase state dictionary for tracking iterations, failures, etc.

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID

    Returns:
        PhaseLoopState for this phase
    """
    if phase_id not in wiring.phase_states:
        wiring.phase_states[phase_id] = PhaseLoopState()
        logger.info(f"[IntentionFirstLoop] Created new phase state for {phase_id}")

    return wiring.phase_states[phase_id]


def decide_stuck_action(
    wiring: ExecutorWiringState,
    phase_id: str,
    phase_spec: dict[str, Any],
    anchor: IntentionAnchor,
    reason: StuckReason,
    tokens_used: int,
    context_chars_used: int,
    sot_chars_used: int,
) -> tuple[StuckResolutionDecision, str]:
    """
    Decide what to do when stuck (INSERTION POINT 3).

    This is the single choke point for stuck handling decisions.

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
        phase_spec: Phase specification dict
        anchor: Intention anchor (authoritative)
        reason: Why stuck
        tokens_used: Total tokens used so far in run
        context_chars_used: Context chars used
        sot_chars_used: SOT chars retrieved

    Returns:
        (decision, explanation)
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)

    # Compute deterministic budget remaining
    budget_inputs = BudgetInputs(
        token_cap=settings.run_token_cap,
        tokens_used=tokens_used,
        max_context_chars=anchor.budgets.max_context_chars,
        context_chars_used=context_chars_used,
        max_sot_chars=anchor.budgets.max_sot_chars,
        sot_chars_used=sot_chars_used,
    )
    budget_remaining = compute_budget_remaining(budget_inputs)

    logger.info(
        f"[IntentionFirstLoop] Phase {phase_id}: budget_remaining={budget_remaining:.2%}"
    )

    # Call policy
    decision = wiring.loop.decide_when_stuck(
        reason=reason,
        phase_state=phase_state,
        budget_remaining=budget_remaining,
    )

    explanation = f"Stuck reason: {reason.value}, decision: {decision.value}, budget: {budget_remaining:.1%}"
    logger.info(f"[IntentionFirstLoop] {explanation}")

    return decision, explanation


def apply_model_escalation(
    wiring: ExecutorWiringState,
    phase_id: str,
    phase_spec: dict[str, Any],
    current_tier: str,
    safety_profile: Literal["normal", "strict"],
) -> ModelRoutingEntry | None:
    """
    Apply model tier escalation (part of INSERTION POINT 3).

    Escalates tier (haiku→sonnet→opus) and updates run_context overrides.

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
        phase_spec: Phase specification dict
        current_tier: Current tier
        safety_profile: Safety profile from anchor

    Returns:
        Escalated ModelRoutingEntry, or None if escalation not possible
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)

    # Enforce max 1 escalation per phase
    if phase_state.escalations_used >= 1:
        logger.warning(
            f"[IntentionFirstLoop] Phase {phase_id}: max escalations (1) already used"
        )
        return None

    # Escalate tier via loop
    entry = wiring.loop.escalate_model(
        wiring.run_state, phase_state, current_tier, safety_profile
    )

    if entry is None:
        logger.warning(
            f"[IntentionFirstLoop] Phase {phase_id}: no escalation available from {current_tier}"
        )
        return None

    # Apply tier override to run_context for ModelRouter consumption
    task_category = phase_spec.get("task_category", "general")
    complexity = TIER_TO_COMPLEXITY.get(entry.tier, "medium")
    override_key = f"{task_category}:{complexity}"

    wiring.run_context["model_overrides"]["builder"][override_key] = entry.model_id
    wiring.run_context["model_overrides"]["auditor"][override_key] = entry.model_id

    logger.info(
        f"[IntentionFirstLoop] Phase {phase_id}: escalated {current_tier}→{entry.tier}, "
        f"override={override_key}→{entry.model_id}"
    )

    return entry


def generate_scope_reduction_proposal(
    wiring: ExecutorWiringState,
    anchor: IntentionAnchor,
    current_plan: dict[str, Any],
    budget_remaining: float,
) -> ScopeReductionProposal | None:
    """
    Generate scope reduction proposal (part of INSERTION POINT 3).

    Generates prompt, parses JSON response into proposal, validates.
    This is proposal-only (reversible); does NOT apply destructively.

    Args:
        wiring: Executor wiring state
        anchor: Intention anchor
        current_plan: Current plan dict with deliverables
        budget_remaining: Budget remaining fraction

    Returns:
        Validated ScopeReductionProposal, or None if generation/validation failed
    """
    # Generate prompt
    prompt = wiring.loop.build_scope_reduction_prompt(
        anchor, current_plan, budget_remaining
    )

    logger.info(
        f"[IntentionFirstLoop] Generated scope reduction prompt ({len(prompt)} chars)"
    )

    # TODO: Call LLM to get JSON proposal (requires LlmService integration)
    # For now, return None (implementation deferred to executor integration)
    logger.warning(
        "[IntentionFirstLoop] Scope reduction LLM call not yet wired (deferred)"
    )
    return None


def write_phase_proof(
    proof: PhaseProof,
) -> None:
    """
    Write phase proof to run-local artifact (INSERTION POINT 4).

    Called after every phase completion (success OR failure).

    Args:
        proof: Phase proof to persist
    """
    PhaseProofStorage.save_proof(proof)
    logger.info(
        f"[IntentionFirstLoop] Wrote phase proof: {proof.run_id}/{proof.phase_id} "
        f"(success={proof.success})"
    )


def increment_phase_iteration(wiring: ExecutorWiringState, phase_id: str) -> None:
    """
    Increment phase iteration counter.

    Call once per attempt cycle (builder+auditor/quality gate).

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)
    phase_state.iterations_used += 1
    logger.debug(
        f"[IntentionFirstLoop] Phase {phase_id}: iterations_used={phase_state.iterations_used}"
    )


def increment_consecutive_failures(
    wiring: ExecutorWiringState, phase_id: str
) -> None:
    """
    Increment consecutive failures counter.

    Call when a phase attempt fails.

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)
    phase_state.consecutive_failures += 1
    logger.debug(
        f"[IntentionFirstLoop] Phase {phase_id}: consecutive_failures={phase_state.consecutive_failures}"
    )


def reset_consecutive_failures(wiring: ExecutorWiringState, phase_id: str) -> None:
    """
    Reset consecutive failures counter (on success).

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)
    phase_state.consecutive_failures = 0
    logger.debug(f"[IntentionFirstLoop] Phase {phase_id}: consecutive_failures reset")


def mark_replan_attempted(wiring: ExecutorWiringState, phase_id: str) -> None:
    """
    Mark that replan was attempted for this phase.

    Args:
        wiring: Executor wiring state
        phase_id: Phase ID
    """
    phase_state = get_or_create_phase_state(wiring, phase_id)
    phase_state.replan_attempted = True
    logger.info(f"[IntentionFirstLoop] Phase {phase_id}: marked replan_attempted=True")
