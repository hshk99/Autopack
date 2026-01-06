"""Scope reduction proposal flow (BUILD-181 Phase 3).

When stuck handling policy decides REDUCE_SCOPE, this module generates
a schema-validated proposal artifact. Never auto-applies.

Properties:
- Proposal-only: requires approval by default
- Schema-validated against docs/schemas/scope_reduction_proposal_v1.schema.json
- Written to run-local artifact path
- Includes anchor context for justification
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from autopack.file_layout import RunFileLayout
    from autopack.intention_anchor.v2 import IntentionAnchorV2

logger = logging.getLogger(__name__)


class ScopeReductionProposal(BaseModel):
    """Scope reduction proposal artifact.

    Generated when stuck handling decides REDUCE_SCOPE.
    Never auto-applies; requires approval by default.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(..., description="Unique proposal identifier")
    run_id: str = Field(..., description="Run this proposal belongs to")
    phase_id: str = Field(..., description="Phase that triggered scope reduction")
    anchor_digest: str = Field(..., description="Digest of intention anchor")
    current_scope: List[str] = Field(..., description="Current task scope")
    proposed_scope: List[str] = Field(..., description="Proposed reduced scope")
    dropped_items: List[str] = Field(..., description="Items being dropped")
    justification: str = Field(..., description="Why scope reduction is needed")
    budget_remaining: float = Field(..., ge=0.0, le=1.0, description="Budget fraction remaining")
    requires_approval: bool = Field(default=True, description="Whether approval is needed")
    auto_approved: bool = Field(default=False, description="Whether auto-approved by rules")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "proposal_id": self.proposal_id,
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "anchor_digest": self.anchor_digest,
            "current_scope": self.current_scope,
            "proposed_scope": self.proposed_scope,
            "dropped_items": self.dropped_items,
            "justification": self.justification,
            "budget_remaining": self.budget_remaining,
            "requires_approval": self.requires_approval,
            "auto_approved": self.auto_approved,
            "created_at": self.created_at.isoformat(),
        }


def build_scope_reduction_prompt(
    anchor: "IntentionAnchorV2",
    phase_state: Dict[str, Any],
    budget_remaining: float,
) -> str:
    """Build a prompt for generating scope reduction justification.

    Includes anchor context for informed decisions.

    Args:
        anchor: IntentionAnchorV2 with pivot intentions
        phase_state: Current phase state (tasks, progress, etc.)
        budget_remaining: Fraction of budget remaining

    Returns:
        Prompt string for scope reduction
    """
    # Extract relevant anchor context
    north_star_text = ""
    if anchor.pivot_intentions.north_star:
        ns = anchor.pivot_intentions.north_star
        outcomes = ", ".join(ns.desired_outcomes) if ns.desired_outcomes else "none"
        non_goals = ", ".join(ns.non_goals) if ns.non_goals else "none"
        north_star_text = f"Desired outcomes: {outcomes}\nNon-goals: {non_goals}"

    # Format phase state
    current_tasks = phase_state.get("current_tasks", [])
    completed_tasks = phase_state.get("completed_tasks", [])
    phase_id = phase_state.get("phase_id", "unknown")

    budget_pct = f"{budget_remaining * 100:.1f}%"

    prompt = f"""Scope Reduction Required

Project: {anchor.project_id}
Anchor Digest: {anchor.raw_input_digest}
Phase: {phase_id}
Budget Remaining: {budget_pct}

{north_star_text}

Current Tasks:
{chr(10).join(f"- {t}" for t in current_tasks) if current_tasks else "- None"}

Completed Tasks:
{chr(10).join(f"- {t}" for t in completed_tasks) if completed_tasks else "- None"}

Given the budget constraint ({budget_pct} remaining), propose which tasks to drop.
Prioritize tasks that align with desired outcomes and drop non-critical items.
"""
    return prompt


def validate_scope_reduction_json(
    proposal_data: Dict[str, Any],
    anchor: "IntentionAnchorV2",
) -> Tuple[bool, str]:
    """Validate scope reduction proposal against schema and anchor.

    Args:
        proposal_data: Proposal as dictionary
        anchor: IntentionAnchorV2 to validate against

    Returns:
        Tuple of (is_valid, reason)
    """
    # Check required fields
    required_fields = [
        "proposal_id",
        "run_id",
        "phase_id",
        "anchor_digest",
        "current_scope",
        "proposed_scope",
        "dropped_items",
        "justification",
        "budget_remaining",
    ]

    for field in required_fields:
        if field not in proposal_data:
            return False, f"Missing required field: {field}"

    # Validate anchor digest matches
    if proposal_data.get("anchor_digest") != anchor.raw_input_digest:
        return False, f"Anchor digest mismatch: expected {anchor.raw_input_digest}"

    # Validate proposed_scope is not empty
    proposed_scope = proposal_data.get("proposed_scope", [])
    if not proposed_scope:
        return False, "Proposed scope cannot be empty (cannot reduce to nothing)"

    # Validate budget_remaining is valid
    budget = proposal_data.get("budget_remaining", -1)
    if not (0.0 <= budget <= 1.0):
        return False, f"Invalid budget_remaining: {budget} (must be 0.0-1.0)"

    # Validate dropped items are from current scope
    current_scope = set(proposal_data.get("current_scope", []))
    dropped = set(proposal_data.get("dropped_items", []))

    if dropped and not dropped.issubset(current_scope):
        invalid_drops = dropped - current_scope
        return False, f"Dropped items not in current scope: {invalid_drops}"

    return True, "Valid"


def write_scope_reduction_proposal(
    layout: "RunFileLayout",
    proposal: ScopeReductionProposal,
) -> Path:
    """Write scope reduction proposal to run-local artifact path.

    Args:
        layout: RunFileLayout for the run
        proposal: ScopeReductionProposal to write

    Returns:
        Path where proposal was written
    """
    # Ensure proposals directory exists
    proposals_dir = layout.base_dir / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    # Write proposal
    artifact_path = proposals_dir / f"scope_reduction_{proposal.proposal_id}.json"
    artifact_path.write_text(
        json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        f"[ScopeReduction] Wrote proposal {proposal.proposal_id} to {artifact_path}"
    )
    return artifact_path


def generate_scope_reduction_proposal(
    run_id: str,
    phase_id: str,
    anchor: "IntentionAnchorV2",
    current_scope: List[str],
    budget_remaining: float,
    items_to_drop: Optional[List[str]] = None,
    justification: Optional[str] = None,
) -> ScopeReductionProposal:
    """Generate a scope reduction proposal.

    Args:
        run_id: Run identifier
        phase_id: Phase identifier
        anchor: IntentionAnchorV2 with pivot intentions
        current_scope: Current list of tasks
        budget_remaining: Fraction of budget remaining
        items_to_drop: Optional explicit list of items to drop
        justification: Optional justification text

    Returns:
        ScopeReductionProposal instance
    """
    # Generate proposal ID deterministically
    content_hash = hashlib.sha256(
        f"{run_id}:{phase_id}:{','.join(sorted(current_scope))}".encode()
    ).hexdigest()[:8]
    proposal_id = f"sr-{content_hash}"

    # Determine what to drop
    if items_to_drop is None:
        # Default: drop items beyond first N based on budget
        keep_count = max(1, int(len(current_scope) * budget_remaining))
        items_to_drop = current_scope[keep_count:]

    proposed_scope = [t for t in current_scope if t not in items_to_drop]

    # Default justification
    if justification is None:
        justification = (
            f"Budget constraint ({budget_remaining * 100:.1f}% remaining). "
            f"Dropping {len(items_to_drop)} non-critical items to complete within budget."
        )

    return ScopeReductionProposal(
        proposal_id=proposal_id,
        run_id=run_id,
        phase_id=phase_id,
        anchor_digest=anchor.raw_input_digest,
        current_scope=current_scope,
        proposed_scope=proposed_scope,
        dropped_items=items_to_drop,
        justification=justification,
        budget_remaining=budget_remaining,
        requires_approval=True,  # Always requires approval by default
        auto_approved=False,
    )
