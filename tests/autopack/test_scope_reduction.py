"""
Tests for intention-driven scope reduction.

Verifies scope reduction grounding in IntentionAnchor and plan diff generation.
"""

from datetime import datetime

import pytest

from autopack.intention_anchor.models import IntentionAnchor, IntentionConstraints, IntentionScope
from autopack.scope_reduction import (
    ScopeReductionDiff,
    ScopeReductionProposal,
    ScopeReductionRationale,
    generate_scope_reduction_prompt,
    validate_scope_reduction,
)


@pytest.fixture
def sample_anchor():
    """Sample intention anchor for testing."""
    return IntentionAnchor(
        anchor_id="anchor-1",
        run_id="test-run",
        project_id="test-project",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        north_star="Build a robust authentication system",
        success_criteria=[
            "User login works",
            "Password reset works",
            "Email verification works",
            "Two-factor auth works",
        ],
        constraints=IntentionConstraints(
            must=["No plaintext passwords", "HTTPS only"],
            must_not=["Store passwords in logs"],
            preferences=["Use bcrypt", "Support OAuth"],
        ),
        scope=IntentionScope(
            allowed_paths=["src/auth/"],
            out_of_scope=["src/billing/"],
        ),
    )


class TestScopeReductionRationale:
    """Test scope reduction rationale schema."""

    def test_rationale_schema_validation(self):
        """Rationale accepts valid data."""
        rationale = ScopeReductionRationale(
            success_criteria_preserved=["User login works"],
            success_criteria_deferred=["Two-factor auth works"],
            constraints_still_met=["No plaintext passwords"],
            reason="Budget constraints require focusing on core login flow",
        )
        assert len(rationale.success_criteria_preserved) == 1
        assert rationale.reason.startswith("Budget constraints")

    def test_rationale_reason_bounded(self):
        """Rationale reason is bounded to 1000 chars."""
        long_reason = "x" * 1100
        with pytest.raises(ValueError):
            ScopeReductionRationale(
                success_criteria_preserved=["User login works"],
                success_criteria_deferred=[],
                constraints_still_met=[],
                reason=long_reason,
            )

    def test_rationale_extra_fields_forbidden(self):
        """Rationale rejects unknown fields."""
        with pytest.raises(ValueError):
            ScopeReductionRationale(
                success_criteria_preserved=["User login works"],
                success_criteria_deferred=[],
                constraints_still_met=[],
                reason="Test",
                unknown_field="should fail",  # type: ignore
            )


class TestScopeReductionDiff:
    """Test scope reduction diff schema."""

    def test_diff_schema_validation(self):
        """Diff accepts valid data."""
        diff = ScopeReductionDiff(
            original_deliverables=["login", "password reset", "2FA"],
            kept_deliverables=["login"],
            dropped_deliverables=["password reset", "2FA"],
            rationale=ScopeReductionRationale(
                success_criteria_preserved=["User login works"],
                success_criteria_deferred=["Password reset works", "Two-factor auth works"],
                constraints_still_met=["No plaintext passwords"],
                reason="Focus on core login functionality",
            ),
        )
        assert len(diff.kept_deliverables) == 1
        assert len(diff.dropped_deliverables) == 2


class TestScopeReductionProposal:
    """Test scope reduction proposal schema."""

    def test_proposal_schema_validation(self):
        """Proposal accepts valid data."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["A", "B"],
                kept_deliverables=["A"],
                dropped_deliverables=["B"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["Criterion 1"],
                    success_criteria_deferred=["Criterion 2"],
                    constraints_still_met=["Must constraint"],
                    reason="Budget constraints",
                ),
            ),
            estimated_budget_savings=0.3,
        )
        assert proposal.run_id == "test-run"
        assert proposal.estimated_budget_savings == 0.3

    def test_proposal_budget_savings_bounded(self):
        """Budget savings must be between 0 and 1."""
        with pytest.raises(ValueError):
            ScopeReductionProposal(
                run_id="test-run",
                phase_id="phase-1",
                anchor_id="anchor-1",
                diff=ScopeReductionDiff(
                    original_deliverables=["A"],
                    kept_deliverables=["A"],
                    dropped_deliverables=[],
                    rationale=ScopeReductionRationale(
                        success_criteria_preserved=[],
                        success_criteria_deferred=[],
                        constraints_still_met=[],
                        reason="Test",
                    ),
                ),
                estimated_budget_savings=1.5,  # Invalid
            )


class TestGenerateScopeReductionPrompt:
    """Test scope reduction prompt generation."""

    def test_prompt_includes_north_star(self, sample_anchor):
        """Prompt includes north star from anchor."""
        plan = {"deliverables": ["login", "password reset"]}
        prompt = generate_scope_reduction_prompt(sample_anchor, plan, 0.2)

        assert "Build a robust authentication system" in prompt

    def test_prompt_includes_success_criteria(self, sample_anchor):
        """Prompt includes all success criteria."""
        plan = {"deliverables": ["login"]}
        prompt = generate_scope_reduction_prompt(sample_anchor, plan, 0.2)

        assert "User login works" in prompt
        assert "Password reset works" in prompt
        assert "Two-factor auth works" in prompt

    def test_prompt_includes_constraints(self, sample_anchor):
        """Prompt includes must/must_not constraints."""
        plan = {"deliverables": ["login"]}
        prompt = generate_scope_reduction_prompt(sample_anchor, plan, 0.2)

        assert "No plaintext passwords" in prompt
        assert "Store passwords in logs" in prompt

    def test_prompt_includes_budget(self, sample_anchor):
        """Prompt includes budget remaining."""
        plan = {"deliverables": ["login"]}
        prompt = generate_scope_reduction_prompt(sample_anchor, plan, 0.15)

        assert "15.0%" in prompt or "15%" in prompt

    def test_prompt_includes_deliverables(self, sample_anchor):
        """Prompt includes current deliverables."""
        plan = {"deliverables": ["login feature", "password reset"]}
        prompt = generate_scope_reduction_prompt(sample_anchor, plan, 0.2)

        assert "login feature" in prompt
        assert "password reset" in prompt


class TestValidateScopeReduction:
    """Test scope reduction validation."""

    def test_valid_proposal(self, sample_anchor):
        """Valid proposal passes validation."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["login", "password reset", "2FA"],
                kept_deliverables=["login"],
                dropped_deliverables=["password reset", "2FA"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["User login works"],
                    success_criteria_deferred=["Password reset works", "Two-factor auth works"],
                    constraints_still_met=[
                        "No plaintext passwords",
                        "HTTPS only",
                    ],  # ALL must constraints
                    reason="Budget constraints require focusing on core login",
                ),
            ),
            estimated_budget_savings=0.4,
        )

        is_valid, message = validate_scope_reduction(proposal, sample_anchor)
        assert is_valid
        assert "Valid" in message

    def test_no_success_criteria_preserved(self, sample_anchor):
        """Proposal with no preserved criteria fails."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["login"],
                kept_deliverables=["something else"],
                dropped_deliverables=["login"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=[],  # Empty!
                    success_criteria_deferred=["User login works"],
                    constraints_still_met=["No plaintext passwords"],
                    reason="Test",
                ),
            ),
            estimated_budget_savings=0.5,
        )

        is_valid, message = validate_scope_reduction(proposal, sample_anchor)
        assert not is_valid
        assert "preserve at least one" in message

    def test_no_deliverables_kept(self, sample_anchor):
        """Proposal with no kept deliverables fails."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["login"],
                kept_deliverables=[],  # Empty!
                dropped_deliverables=["login"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["User login works"],
                    success_criteria_deferred=[],
                    constraints_still_met=[
                        "No plaintext passwords",
                        "HTTPS only",
                    ],  # ALL must constraints
                    reason="Test",
                ),
            ),
            estimated_budget_savings=0.5,
        )

        is_valid, message = validate_scope_reduction(proposal, sample_anchor)
        assert not is_valid
        assert "keep at least one deliverable" in message

    def test_no_deliverables_dropped(self, sample_anchor):
        """Proposal with no dropped deliverables fails."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["login"],
                kept_deliverables=["login"],
                dropped_deliverables=[],  # Empty!
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["User login works"],
                    success_criteria_deferred=[],
                    constraints_still_met=[
                        "No plaintext passwords",
                        "HTTPS only",
                    ],  # ALL must constraints
                    reason="Test",
                ),
            ),
            estimated_budget_savings=0.5,
        )

        is_valid, message = validate_scope_reduction(proposal, sample_anchor)
        assert not is_valid
        assert "drop at least one deliverable" in message

    def test_must_constraints_not_acknowledged(self, sample_anchor):
        """Proposal that doesn't acknowledge 'must' constraints fails."""
        proposal = ScopeReductionProposal(
            run_id="test-run",
            phase_id="phase-1",
            anchor_id="anchor-1",
            diff=ScopeReductionDiff(
                original_deliverables=["login", "2FA"],
                kept_deliverables=["login"],
                dropped_deliverables=["2FA"],
                rationale=ScopeReductionRationale(
                    success_criteria_preserved=["User login works"],
                    success_criteria_deferred=["Two-factor auth works"],
                    constraints_still_met=[],  # Doesn't acknowledge must constraints!
                    reason="Test",
                ),
            ),
            estimated_budget_savings=0.3,
        )

        is_valid, message = validate_scope_reduction(proposal, sample_anchor)
        assert not is_valid
        assert "must" in message.lower()
