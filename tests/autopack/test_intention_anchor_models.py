"""
Tests for IntentionAnchor schema strictness and validation.

Intention behind these tests: ensure `extra="forbid"` catches unintended fields
and that required fields are properly enforced.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from autopack.intention_anchor import (IntentionAnchor, IntentionBudgets,
                                       IntentionConstraints,
                                       IntentionRiskProfile, IntentionScope)


def test_intention_anchor_minimal_valid():
    """A minimal valid anchor should parse successfully."""
    now = datetime.now(timezone.utc)
    anchor = IntentionAnchor(
        anchor_id="IA-test-001",
        run_id="test-run",
        project_id="test-project",
        created_at=now,
        updated_at=now,
        version=1,
        north_star="Build a reliable test harness for intention anchors.",
    )

    assert anchor.anchor_id == "IA-test-001"
    assert anchor.run_id == "test-run"
    assert anchor.project_id == "test-project"
    assert anchor.version == 1
    assert anchor.north_star == "Build a reliable test harness for intention anchors."
    assert anchor.success_criteria == []
    assert anchor.constraints.must == []
    assert anchor.constraints.must_not == []
    assert anchor.constraints.preferences == []


def test_intention_anchor_rejects_unknown_fields():
    """Unknown fields should be rejected (extra='forbid')."""
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError) as exc_info:
        IntentionAnchor(
            anchor_id="IA-test-002",
            run_id="test-run",
            project_id="test-project",
            created_at=now,
            updated_at=now,
            version=1,
            north_star="Test strictness.",
            unknown_field="should fail",  # This should trigger validation error
        )

    error_str = str(exc_info.value)
    assert "extra" in error_str.lower() or "unexpected" in error_str.lower()


def test_intention_constraints_rejects_unknown_fields():
    """IntentionConstraints should reject unknown fields."""
    with pytest.raises(ValidationError):
        IntentionConstraints(
            must=["field1"],
            must_not=["field2"],
            preferences=["field3"],
            unknown_constraint="should fail",
        )


def test_intention_scope_rejects_unknown_fields():
    """IntentionScope should reject unknown fields."""
    with pytest.raises(ValidationError):
        IntentionScope(
            allowed_paths=["src/"],
            out_of_scope=["tests/"],
            unknown_scope="should fail",
        )


def test_intention_budgets_rejects_unknown_fields():
    """IntentionBudgets should reject unknown fields."""
    with pytest.raises(ValidationError):
        IntentionBudgets(
            max_context_chars=50000,
            max_sot_chars=2000,
            unknown_budget="should fail",
        )


def test_intention_risk_profile_rejects_unknown_fields():
    """IntentionRiskProfile should reject unknown fields."""
    with pytest.raises(ValidationError):
        IntentionRiskProfile(
            safety_profile="normal",
            protected_paths=["src/core/"],
            unknown_risk="should fail",
        )


def test_intention_anchor_requires_north_star():
    """north_star is a required field."""
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        IntentionAnchor(
            anchor_id="IA-test-003",
            run_id="test-run",
            project_id="test-project",
            created_at=now,
            updated_at=now,
            version=1,
            # north_star is missing
        )


def test_intention_anchor_with_full_fields():
    """Test anchor with all fields populated."""
    now = datetime.now(timezone.utc)
    anchor = IntentionAnchor(
        anchor_id="IA-test-004",
        run_id="test-run",
        project_id="test-project",
        created_at=now,
        updated_at=now,
        version=2,
        north_star="Full-featured test anchor.",
        success_criteria=["SC1", "SC2", "SC3"],
        constraints=IntentionConstraints(
            must=["Use strict typing"],
            must_not=["Introduce breaking changes"],
            preferences=["Prefer functional style"],
        ),
        scope=IntentionScope(
            allowed_paths=["src/", "tests/"],
            out_of_scope=["docs/"],
        ),
        budgets=IntentionBudgets(
            max_context_chars=80000,
            max_sot_chars=3000,
        ),
        risk_profile=IntentionRiskProfile(
            safety_profile="strict",
            protected_paths=["src/core/", "src/models/"],
        ),
    )

    assert len(anchor.success_criteria) == 3
    assert len(anchor.constraints.must) == 1
    assert anchor.budgets.max_context_chars == 80000
    assert anchor.risk_profile.safety_profile == "strict"


def test_intention_anchor_defaults():
    """Test that default factories work correctly."""
    now = datetime.now(timezone.utc)
    anchor = IntentionAnchor(
        anchor_id="IA-test-005",
        run_id="test-run",
        project_id="test-project",
        created_at=now,
        updated_at=now,
        version=1,
        north_star="Test defaults.",
    )

    # Defaults should be empty lists / default objects
    assert isinstance(anchor.success_criteria, list)
    assert isinstance(anchor.constraints, IntentionConstraints)
    assert isinstance(anchor.scope, IntentionScope)
    assert isinstance(anchor.budgets, IntentionBudgets)
    assert isinstance(anchor.risk_profile, IntentionRiskProfile)

    # Budget defaults
    assert anchor.budgets.max_context_chars == 100_000
    assert anchor.budgets.max_sot_chars == 4_000

    # Risk profile defaults
    assert anchor.risk_profile.safety_profile == "normal"
    assert anchor.risk_profile.protected_paths == []


def test_risk_profile_literal_validation():
    """safety_profile should only accept 'normal' or 'strict'."""
    with pytest.raises(ValidationError):
        IntentionRiskProfile(
            safety_profile="invalid_mode",  # Should fail
        )
