"""
Intention-driven scope reduction for intention-first autonomy.

Implements:
- Scope reduction prompt grounded in IntentionAnchor fields
- Plan diff showing what's kept vs. dropped and why
- Explicit citation of intention success_criteria, constraints, scope
- Reversible reductions (no destructive apply)

All scope reductions explicitly justify against the Intention Anchor.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autopack.intention_anchor.models import IntentionAnchor


class ScopeReductionRationale(BaseModel):
    """
    Rationale for scope reduction decision.

    Explicitly cites which intention fields justify the reduction.
    """

    model_config = ConfigDict(extra="forbid")

    success_criteria_preserved: list[str] = Field(
        default_factory=list,
        description="Which success criteria remain satisfied after reduction",
    )
    success_criteria_deferred: list[str] = Field(
        default_factory=list, description="Which success criteria are deferred"
    )
    constraints_still_met: list[str] = Field(
        default_factory=list, description="Which constraints are still satisfied"
    )
    reason: str = Field(
        ..., max_length=1000, description="Why scope reduction is necessary"
    )


class ScopeReductionDiff(BaseModel):
    """
    Plan diff showing what changed due to scope reduction.

    Designed to be reviewable and reversible.
    """

    model_config = ConfigDict(extra="forbid")

    original_deliverables: list[str] = Field(
        default_factory=list, description="Original planned deliverables"
    )
    kept_deliverables: list[str] = Field(
        default_factory=list, description="Deliverables kept after reduction"
    )
    dropped_deliverables: list[str] = Field(
        default_factory=list, description="Deliverables dropped in reduction"
    )
    rationale: ScopeReductionRationale


class ScopeReductionProposal(BaseModel):
    """
    Complete scope reduction proposal with intention grounding.

    Intention: make all reductions explicit, justified, and reviewable.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    phase_id: str
    anchor_id: str
    diff: ScopeReductionDiff
    estimated_budget_savings: float = Field(
        ..., ge=0.0, le=1.0, description="Estimated fraction of budget saved (0-1)"
    )


def generate_scope_reduction_prompt(
    anchor: IntentionAnchor,
    current_plan: dict[str, Any],
    budget_remaining: float,
) -> str:
    """
    Generate prompt for scope reduction grounded in IntentionAnchor.

    Args:
        anchor: Intention anchor
        current_plan: Current plan dict with 'deliverables' key
        budget_remaining: Fraction of budget remaining (0.0 to 1.0)

    Returns:
        Prompt string
    """
    # Extract current deliverables
    deliverables = current_plan.get("deliverables", [])
    deliverable_list = "\n".join(f"- {d}" for d in deliverables)

    # Extract intention fields
    success_criteria = "\n".join(f"- {c}" for c in anchor.success_criteria)
    must_constraints = "\n".join(f"- {c}" for c in anchor.constraints.must)
    must_not_constraints = "\n".join(f"- {c}" for c in anchor.constraints.must_not)
    preferences = "\n".join(f"- {c}" for c in anchor.constraints.preferences)

    prompt = f"""You are proposing a scope reduction for a phase that is stuck.

**CRITICAL**: You must explicitly cite which Intention Anchor fields justify your reduction.

## Current Situation
- Budget remaining: {budget_remaining:.1%}
- Current deliverables:
{deliverable_list}

## Intention Anchor (Authoritative)

**North Star**:
{anchor.north_star}

**Success Criteria** (which must you preserve? which can you defer?):
{success_criteria}

**Must Constraints** (non-negotiable):
{must_constraints}

**Must Not Constraints** (forbidden):
{must_not_constraints}

**Preferences** (nice-to-have):
{preferences}

## Your Task

1. Propose a reduced scope that:
   - Preserves as many success criteria as possible
   - Respects all "must" and "must not" constraints
   - Fits within the remaining budget
   - Explicitly states which success criteria are deferred (not dropped permanently)

2. Provide:
   - List of kept deliverables
   - List of dropped deliverables
   - For each kept deliverable: which success criteria it satisfies
   - For each dropped deliverable: which success criteria are deferred
   - Estimated budget savings (as fraction 0.0-1.0)

3. Format your response as JSON matching ScopeReductionProposal schema.

**Remember**: All reductions must be justified against the Intention Anchor. Never drop deliverables arbitrarily.
"""
    return prompt


def validate_scope_reduction(
    proposal: ScopeReductionProposal, anchor: IntentionAnchor
) -> tuple[bool, str]:
    """
    Validate that scope reduction respects intention constraints.

    Args:
        proposal: Scope reduction proposal
        anchor: Intention anchor

    Returns:
        (is_valid, error_message)
    """
    # Check that at least some success criteria are preserved
    if not proposal.diff.rationale.success_criteria_preserved:
        return False, "Scope reduction must preserve at least one success criterion"

    # Check that ALL "must" constraints are explicitly acknowledged
    # Per Phase C.1: require set(must) ⊆ set(constraints_still_met)
    must_constraints = set(anchor.constraints.must)
    acknowledged = set(proposal.diff.rationale.constraints_still_met)

    # If there are "must" constraints, ALL must be acknowledged
    if must_constraints and not must_constraints.issubset(acknowledged):
        missing = must_constraints - acknowledged
        return (
            False,
            f"Scope reduction must acknowledge ALL 'must' constraints. Missing: {sorted(missing)}",
        )

    # Check that at least one deliverable is kept
    if not proposal.diff.kept_deliverables:
        return False, "Scope reduction must keep at least one deliverable"

    # Check that some deliverables were actually dropped
    if not proposal.diff.dropped_deliverables:
        return False, "Scope reduction must drop at least one deliverable"

    return True, "Valid scope reduction"
