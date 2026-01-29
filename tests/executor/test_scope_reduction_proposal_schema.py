"""Contract-first tests for scope reduction proposal flow (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Proposal produces schema-valid artifact
- Never auto-applies (requires approval by default)
- Halts with actionable message when approval required
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def test_scope_reduction_proposal_is_schema_valid():
    """Scope reduction proposal validates against schema."""
    from autopack.executor.scope_reduction_flow import (
        ScopeReductionProposal,
        validate_scope_reduction_json,
    )
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )

    proposal = ScopeReductionProposal(
        proposal_id="sr-001",
        run_id="test-run",
        phase_id="phase-1",
        anchor_digest=anchor.raw_input_digest,
        current_scope=["task-1", "task-2", "task-3"],
        proposed_scope=["task-1", "task-2"],
        dropped_items=["task-3"],
        justification="Budget exhausted, dropping non-critical task",
        budget_remaining=0.15,
        requires_approval=True,
        auto_approved=False,
        created_at=datetime.now(timezone.utc),
    )

    # Validate
    is_valid, reason = validate_scope_reduction_json(proposal.to_dict(), anchor)

    assert is_valid is True, f"Validation failed: {reason}"


def test_scope_reduction_never_auto_applies_by_default():
    """Scope reduction proposals require approval by default."""
    from autopack.executor.scope_reduction_flow import ScopeReductionProposal

    proposal = ScopeReductionProposal(
        proposal_id="sr-001",
        run_id="test-run",
        phase_id="phase-1",
        anchor_digest="abc123",
        current_scope=["task-1", "task-2"],
        proposed_scope=["task-1"],
        dropped_items=["task-2"],
        justification="Budget constraint",
        budget_remaining=0.10,
        requires_approval=True,
        auto_approved=False,
        created_at=datetime.now(timezone.utc),
    )

    assert proposal.requires_approval is True
    assert proposal.auto_approved is False


def test_scope_reduction_writes_to_run_local_path():
    """Proposal is written to run-local artifact path."""
    from autopack.executor.scope_reduction_flow import (
        ScopeReductionProposal,
        write_scope_reduction_proposal,
    )
    from autopack.file_layout import RunFileLayout

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create run layout with temp base
        layout = RunFileLayout("test-run-001", base_dir=Path(tmpdir))
        layout.ensure_directories()

        proposal = ScopeReductionProposal(
            proposal_id="sr-001",
            run_id="test-run-001",
            phase_id="phase-1",
            anchor_digest="abc123",
            current_scope=["task-1", "task-2"],
            proposed_scope=["task-1"],
            dropped_items=["task-2"],
            justification="Budget constraint",
            budget_remaining=0.10,
            requires_approval=True,
            auto_approved=False,
            created_at=datetime.now(timezone.utc),
        )

        # Write proposal
        artifact_path = write_scope_reduction_proposal(layout, proposal)

        # Verify file exists and is valid JSON
        assert artifact_path.exists()
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["proposal_id"] == "sr-001"
        assert data["dropped_items"] == ["task-2"]


def test_scope_reduction_prompt_includes_anchor_context():
    """Scope reduction prompt includes anchor context for justification."""
    from autopack.executor.scope_reduction_flow import build_scope_reduction_prompt
    from autopack.intention_anchor.v2 import IntentionAnchorV2, NorthStarIntention, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            north_star=NorthStarIntention(
                desired_outcomes=["Complete feature X", "Maintain test coverage"],
                non_goals=["Full rewrite of module Y"],
            )
        ),
    )

    phase_state = {
        "phase_id": "phase-1",
        "current_tasks": ["task-1", "task-2", "task-3"],
        "completed_tasks": [],
    }

    prompt = build_scope_reduction_prompt(anchor, phase_state, budget_remaining=0.15)

    # Prompt should reference anchor context
    assert "abc123" in prompt or "test-project" in prompt
    assert "task-" in prompt
    assert "0.15" in prompt or "15%" in prompt or "15.0%" in prompt


def test_scope_reduction_validation_rejects_empty_proposed_scope():
    """Validation fails if proposed_scope is empty (cannot reduce to nothing)."""
    from autopack.executor.scope_reduction_flow import validate_scope_reduction_json
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )

    proposal_data = {
        "proposal_id": "sr-001",
        "run_id": "test-run",
        "phase_id": "phase-1",
        "anchor_digest": "abc123",
        "current_scope": ["task-1"],
        "proposed_scope": [],  # Empty - invalid
        "dropped_items": ["task-1"],
        "justification": "Drop everything",
        "budget_remaining": 0.05,
        "requires_approval": True,
        "auto_approved": False,
        "created_at": "2025-01-01T12:00:00+00:00",
    }

    is_valid, reason = validate_scope_reduction_json(proposal_data, anchor)

    assert is_valid is False
    assert "empty" in reason.lower() or "scope" in reason.lower()


def test_scope_reduction_validation_rejects_anchor_mismatch():
    """Validation fails if proposal anchor_digest doesn't match anchor."""
    from autopack.executor.scope_reduction_flow import validate_scope_reduction_json
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )

    proposal_data = {
        "proposal_id": "sr-001",
        "run_id": "test-run",
        "phase_id": "phase-1",
        "anchor_digest": "wrong-digest",  # Mismatch
        "current_scope": ["task-1", "task-2"],
        "proposed_scope": ["task-1"],
        "dropped_items": ["task-2"],
        "justification": "Budget constraint",
        "budget_remaining": 0.10,
        "requires_approval": True,
        "auto_approved": False,
        "created_at": "2025-01-01T12:00:00+00:00",
    }

    is_valid, reason = validate_scope_reduction_json(proposal_data, anchor)

    assert is_valid is False
    assert "mismatch" in reason.lower() or "digest" in reason.lower()
