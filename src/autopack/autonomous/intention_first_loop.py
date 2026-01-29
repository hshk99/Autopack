"""
Intention-first autonomy loop orchestrator.

Implements the glue layer between executor and intention-first components:
- Stuck handling policy decisions
- Scope reduction (grounded in IntentionAnchor)
- Model routing snapshot (budget-aware escalation)
- Phase proof artifacts (bounded, auditable)

All routing decisions are deterministic and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from autopack.model_routing_snapshot import (ModelRoutingEntry,
                                             ModelRoutingSnapshot,
                                             refresh_or_load_snapshot)
from autopack.phase_proof import PhaseProof, PhaseProofStorage
from autopack.scope_reduction import (ScopeReductionProposal,
                                      generate_scope_reduction_prompt,
                                      validate_scope_reduction)
from autopack.stuck_handling import (StuckHandlingPolicy, StuckReason,
                                     StuckResolutionDecision)

if TYPE_CHECKING:
    from autopack.intention_anchor.artifacts import IntentionAnchor


@dataclass
class PhaseLoopState:
    """
    Per-phase execution state for stuck handling.

    Tracks attempts, failures, and escalations within a single phase.
    """

    iterations_used: int = 0
    consecutive_failures: int = 0
    replan_attempted: bool = False
    escalations_used: int = 0


@dataclass
class RunLoopState:
    """
    Per-run execution state.

    Holds the routing snapshot and run identifiers.
    """

    run_id: str
    project_id: str | None
    routing_snapshot: ModelRoutingSnapshot


class IntentionFirstLoop:
    """
    Orchestrates intention-first autonomy loop.

    Provides deterministic stuck handling, scope reduction, model escalation,
    and proof artifact generation.
    """

    def __init__(self, policy: StuckHandlingPolicy | None = None) -> None:
        """
        Initialize the intention-first loop.

        Args:
            policy: Stuck handling policy (defaults to StuckHandlingPolicy())
        """
        self.policy = policy or StuckHandlingPolicy()

    def on_run_start(self, run_id: str, project_id: str | None = None) -> RunLoopState:
        """
        Initialize run-level state at run start.

        Refreshes/loads routing snapshot and persists it as run-local artifact.

        Args:
            run_id: Run identifier
            project_id: Optional project identifier

        Returns:
            RunLoopState with routing snapshot
        """
        snapshot = refresh_or_load_snapshot(run_id, force_refresh=False)
        return RunLoopState(run_id=run_id, project_id=project_id, routing_snapshot=snapshot)

    def decide_when_stuck(
        self,
        *,
        reason: StuckReason,
        phase_state: PhaseLoopState,
        budget_remaining: float,
    ) -> StuckResolutionDecision:
        """
        Decide how to proceed when phase is stuck.

        Uses deterministic policy with hierarchy:
        1. needs-human for safety/ambiguity
        2. stop if iterations exhausted
        3. reduce_scope if budget low
        4. replan before escalation
        5. escalate_model after replan fails

        Args:
            reason: Why the phase is stuck
            phase_state: Current phase loop state
            budget_remaining: Fraction of budget remaining (0..1)

        Returns:
            Deterministic decision
        """
        return self.policy.decide(
            reason=reason,
            iterations_used=phase_state.iterations_used,
            budget_remaining=budget_remaining,
            escalations_used=phase_state.escalations_used,
            consecutive_failures=phase_state.consecutive_failures,
            replan_attempted=phase_state.replan_attempted,
        )

    def escalate_model(
        self,
        run_state: RunLoopState,
        phase_state: PhaseLoopState,
        current_tier: str,
        safety_profile: str = "normal",
    ) -> ModelRoutingEntry | None:
        """
        Escalate to next model tier (max 1 per phase).

        Args:
            run_state: Run loop state with routing snapshot
            phase_state: Phase loop state (will increment escalations_used)
            current_tier: Current model tier
            safety_profile: Safety profile ("normal" or "strict")

        Returns:
            Next tier entry if available, else None
        """
        entry = run_state.routing_snapshot.escalate_tier(
            current_tier, safety_profile=safety_profile
        )
        if entry is not None:
            phase_state.escalations_used += 1
        return entry

    def build_scope_reduction_prompt(
        self,
        anchor: IntentionAnchor,
        current_plan: dict[str, Any],
        budget_remaining: float,
    ) -> str:
        """
        Generate scope reduction prompt grounded in IntentionAnchor.

        Args:
            anchor: Intention anchor with goal/criteria/constraints
            current_plan: Current plan to reduce
            budget_remaining: Fraction of budget remaining

        Returns:
            Prompt for scope reduction
        """
        return generate_scope_reduction_prompt(anchor, current_plan, budget_remaining)

    def validate_scope_reduction(
        self, proposal: ScopeReductionProposal, anchor: IntentionAnchor
    ) -> tuple[bool, str]:
        """
        Validate scope reduction proposal against IntentionAnchor.

        Args:
            proposal: Scope reduction proposal
            anchor: Intention anchor

        Returns:
            (is_valid, error_message)
        """
        return validate_scope_reduction(proposal, anchor)

    def write_phase_proof(self, proof: PhaseProof) -> None:
        """
        Persist phase proof as run-local artifact.

        Args:
            proof: Phase proof to save
        """
        PhaseProofStorage.save_proof(proof)
