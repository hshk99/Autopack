"""
Tests for Phase intention_refs schema and validation (Milestone 1).

Intention behind these tests: ensure phase binding to intention anchors works
correctly in warn-first mode, with proper range validation and backwards compatibility.
"""

import pytest
from pydantic import ValidationError

from autopack.intention_anchor import IntentionConstraints, create_anchor
from autopack.plan_utils import validate_intention_refs
from autopack.schemas import IntentionRefs, PhaseCreate, PhaseResponse

# =============================================================================
# Schema Tests: IntentionRefs model
# =============================================================================


def test_intention_refs_minimal_valid():
    """Minimal valid IntentionRefs (all fields empty)."""
    refs = IntentionRefs()

    assert refs.success_criteria == []
    assert refs.constraints_must == []
    assert refs.constraints_must_not == []
    assert refs.constraints_preferences == []


def test_intention_refs_with_indices():
    """IntentionRefs with specific indices."""
    refs = IntentionRefs(
        success_criteria=[0, 2],
        constraints_must=[1],
        constraints_must_not=[0, 1],
        constraints_preferences=[2],
    )

    assert refs.success_criteria == [0, 2]
    assert refs.constraints_must == [1]
    assert refs.constraints_must_not == [0, 1]
    assert refs.constraints_preferences == [2]


def test_intention_refs_rejects_unknown_fields():
    """IntentionRefs should reject unknown fields (extra='forbid')."""
    with pytest.raises(ValidationError) as exc_info:
        IntentionRefs(
            success_criteria=[0],
            unknown_field="should fail",
        )

    error_str = str(exc_info.value)
    assert "extra" in error_str.lower() or "unexpected" in error_str.lower()


def test_intention_refs_requires_list_of_ints():
    """IntentionRefs fields must be lists of integers."""
    with pytest.raises(ValidationError):
        IntentionRefs(success_criteria="not a list")

    with pytest.raises(ValidationError):
        IntentionRefs(success_criteria=["not", "ints"])


# =============================================================================
# Schema Tests: PhaseCreate with intention_refs
# =============================================================================


def test_phase_create_without_intention_refs():
    """PhaseCreate works without intention_refs (backwards compatible)."""
    phase = PhaseCreate(
        phase_id="p1",
        phase_index=1,
        tier_id="t1",
        name="Test phase",
    )

    assert phase.phase_id == "p1"
    assert phase.intention_refs is None


def test_phase_create_with_intention_refs():
    """PhaseCreate accepts intention_refs."""
    refs = IntentionRefs(
        success_criteria=[0, 1],
        constraints_must=[0],
    )

    phase = PhaseCreate(
        phase_id="p2",
        phase_index=1,
        tier_id="t1",
        name="Test phase with refs",
        intention_refs=refs,
    )

    assert phase.intention_refs is not None
    assert phase.intention_refs.success_criteria == [0, 1]
    assert phase.intention_refs.constraints_must == [0]


def test_phase_create_with_inline_intention_refs():
    """PhaseCreate can accept intention_refs as a dict."""
    phase = PhaseCreate(
        phase_id="p3",
        phase_index=1,
        tier_id="t1",
        name="Test phase",
        intention_refs={
            "success_criteria": [0],
            "constraints_must": [1, 2],
            "constraints_must_not": [],
            "constraints_preferences": [],
        },
    )

    assert phase.intention_refs is not None
    assert phase.intention_refs.success_criteria == [0]
    assert phase.intention_refs.constraints_must == [1, 2]


# =============================================================================
# Schema Tests: PhaseResponse with intention_refs
# =============================================================================


def test_phase_response_without_intention_refs():
    """PhaseResponse works without intention_refs (backwards compatible)."""
    phase = PhaseResponse(
        id=1,
        phase_id="p1",
        run_id="run-001",
        tier_id=1,
        name="Test phase",
        state="pending",
        phase_index=1,
        description=None,
        task_category=None,
        complexity=None,
        builder_mode=None,
    )

    assert phase.intention_refs is None


def test_phase_response_with_intention_refs():
    """PhaseResponse includes intention_refs."""
    refs = IntentionRefs(success_criteria=[0, 1])

    phase = PhaseResponse(
        id=1,
        phase_id="p1",
        run_id="run-001",
        tier_id=1,
        name="Test phase",
        state="pending",
        phase_index=1,
        description=None,
        task_category=None,
        complexity=None,
        builder_mode=None,
        intention_refs=refs,
    )

    assert phase.intention_refs is not None
    assert phase.intention_refs.success_criteria == [0, 1]


# =============================================================================
# Validation Tests: validate_intention_refs (warn mode)
# =============================================================================


def test_validate_no_refs_no_anchor_warn_mode():
    """No refs + no anchor = no warnings in warn mode."""
    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=None,
        anchor_data=None,
        strict_mode=False,
    )

    assert len(warnings) == 0


def test_validate_no_refs_with_anchor_warn_mode():
    """No refs + anchor exists = warning in warn mode."""
    anchor = create_anchor(
        run_id="test-run",
        project_id="test-project",
        north_star="Test anchor",
    )
    anchor_dict = anchor.model_dump()

    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=None,
        anchor_data=anchor_dict,
        strict_mode=False,
    )

    assert len(warnings) == 1
    assert "no intention_refs provided" in warnings[0]
    assert "warn-first mode" in warnings[0]


def test_validate_refs_no_anchor_warn_mode():
    """Refs provided + no anchor = warning in warn mode."""
    refs_dict = {"success_criteria": [0]}

    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=refs_dict,
        anchor_data=None,
        strict_mode=False,
    )

    assert len(warnings) == 1
    assert "has intention_refs but no anchor found" in warnings[0]


def test_validate_valid_refs_no_warnings():
    """Valid refs → no warnings."""
    anchor = create_anchor(
        run_id="test-run",
        project_id="test-project",
        north_star="Test anchor",
        success_criteria=["SC1", "SC2", "SC3"],
        constraints=IntentionConstraints(
            must=["M1", "M2"],
            must_not=["MN1"],
        ),
    )
    anchor_dict = anchor.model_dump()

    refs_dict = {
        "success_criteria": [0, 2],  # Valid: 0 and 2 exist
        "constraints_must": [1],  # Valid: index 1 exists
        "constraints_must_not": [0],  # Valid: index 0 exists
        "constraints_preferences": [],
    }

    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=refs_dict,
        anchor_data=anchor_dict,
        strict_mode=False,
    )

    assert len(warnings) == 0


def test_validate_out_of_range_warns():
    """Out-of-range refs → warnings in warn mode."""
    anchor = create_anchor(
        run_id="test-run",
        project_id="test-project",
        north_star="Test anchor",
        success_criteria=["SC1", "SC2"],  # Only 2 items (indices 0, 1)
    )
    anchor_dict = anchor.model_dump()

    refs_dict = {
        "success_criteria": [0, 1, 2, 5],  # 2 and 5 are out of range
    }

    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=refs_dict,
        anchor_data=anchor_dict,
        strict_mode=False,
    )

    assert len(warnings) == 2
    assert "success_criteria[2]" in warnings[0]
    assert "out of range" in warnings[0]
    assert "success_criteria[5]" in warnings[1]


def test_validate_negative_index_warns():
    """Negative indices → warnings."""
    anchor = create_anchor(
        run_id="test-run",
        project_id="test-project",
        north_star="Test anchor",
        success_criteria=["SC1"],
    )
    anchor_dict = anchor.model_dump()

    refs_dict = {"success_criteria": [-1]}

    warnings = validate_intention_refs(
        phase_id="p1",
        intention_refs=refs_dict,
        anchor_data=anchor_dict,
        strict_mode=False,
    )

    assert len(warnings) == 1
    assert "out of range" in warnings[0]


# =============================================================================
# Validation Tests: strict mode (future-proofing)
# =============================================================================


def test_validate_strict_mode_raises_on_missing_anchor():
    """Strict mode raises ValueError if anchor missing."""
    refs_dict = {"success_criteria": [0]}

    with pytest.raises(ValueError) as exc_info:
        validate_intention_refs(
            phase_id="p1",
            intention_refs=refs_dict,
            anchor_data=None,
            strict_mode=True,
        )

    assert "no anchor found" in str(exc_info.value)


def test_validate_strict_mode_raises_on_out_of_range():
    """Strict mode raises ValueError on out-of-range refs."""
    anchor = create_anchor(
        run_id="test-run",
        project_id="test-project",
        north_star="Test anchor",
        success_criteria=["SC1"],
    )
    anchor_dict = anchor.model_dump()

    refs_dict = {"success_criteria": [0, 5]}  # 5 is out of range

    with pytest.raises(ValueError) as exc_info:
        validate_intention_refs(
            phase_id="p1",
            intention_refs=refs_dict,
            anchor_data=anchor_dict,
            strict_mode=True,
        )

    assert "out of range" in str(exc_info.value)


# =============================================================================
# Backwards Compatibility Tests
# =============================================================================


def test_existing_phases_without_refs_still_work():
    """Existing phases (no intention_refs) continue to work."""
    # Simulate legacy phase (no intention_refs field)
    phase_dict = {
        "phase_id": "legacy-phase",
        "phase_index": 1,
        "tier_id": "t1",
        "name": "Legacy phase",
        "description": "A phase from before Milestone 1",
        "task_category": "refactor",
        "complexity": "medium",
    }

    phase = PhaseCreate(**phase_dict)

    assert phase.phase_id == "legacy-phase"
    assert phase.intention_refs is None


def test_phase_response_from_db_without_refs():
    """PhaseResponse can be constructed from DB rows without intention_refs."""
    # Simulate DB row (old schema, no intention_refs column)
    db_row_dict = {
        "id": 1,
        "phase_id": "db-phase",
        "run_id": "run-001",
        "tier_id": 1,
        "name": "DB phase",
        "state": "complete",
        "phase_index": 1,
        "description": None,
        "task_category": None,
        "complexity": None,
        "builder_mode": None,
        "scope": None,
        # No intention_refs field
    }

    phase = PhaseResponse(**db_row_dict)

    assert phase.phase_id == "db-phase"
    assert phase.intention_refs is None


def test_mixed_phases_some_with_refs_some_without():
    """Can have phases with and without refs in the same run."""
    phase_with_refs = PhaseCreate(
        phase_id="p1",
        phase_index=1,
        tier_id="t1",
        name="Phase with refs",
        intention_refs=IntentionRefs(success_criteria=[0]),
    )

    phase_without_refs = PhaseCreate(
        phase_id="p2",
        phase_index=2,
        tier_id="t1",
        name="Phase without refs",
    )

    assert phase_with_refs.intention_refs is not None
    assert phase_without_refs.intention_refs is None
