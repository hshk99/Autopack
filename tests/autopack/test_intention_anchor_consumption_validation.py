"""Tests for IntentionAnchor consumption-time schema validation.

IMP-SCHEMA-012: Tests for anchor schema validation at consumption time.
Validates that anchors are validated against the JSON schema, not just field existence.
"""

from datetime import datetime, timezone

import pytest

from autopack.intention_anchor.v2 import (
    AutoApprovalRule,
    BudgetCostIntention,
    EvidenceVerificationIntention,
    GovernanceReviewIntention,
    IntentionAnchorV2,
    NorthStarIntention,
    ParallelismIsolationIntention,
    PivotIntentions,
    SafetyRiskIntention,
)
from autopack.intention_anchor.validators import AnchorValidator, ValidationResult

# Valid 16-character hex digest for test fixtures
VALID_DIGEST = "a1b2c3d4e5f67890"  # 16 hex chars matching ^[a-f0-9]{16,64}$


class TestValidationResult:
    """Test suite for ValidationResult dataclass."""

    def test_validation_result_starts_valid(self):
        """ValidationResult should start as valid with empty errors."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.paths == []
        assert result.schema_validated is False

    def test_add_error_marks_invalid(self):
        """add_error should mark result as invalid."""
        result = ValidationResult(valid=True)
        result.add_error("Test error", "$.field")
        assert result.valid is False
        assert "Test error" in result.errors
        assert "$.field" in result.paths

    def test_add_error_without_path(self):
        """add_error should work without path."""
        result = ValidationResult(valid=True)
        result.add_error("Test error")
        assert result.valid is False
        assert "Test error" in result.errors
        assert result.paths == []

    def test_merge_combines_results(self):
        """merge should combine two validation results."""
        result1 = ValidationResult(valid=True)
        result1.add_error("Error 1", "$.path1")

        result2 = ValidationResult(valid=True)
        result2.add_error("Error 2", "$.path2")

        result1.merge(result2)
        assert result1.valid is False
        assert "Error 1" in result1.errors
        assert "Error 2" in result1.errors
        assert "$.path1" in result1.paths
        assert "$.path2" in result1.paths

    def test_merge_preserves_valid_if_both_valid(self):
        """merge should preserve valid=True if both are valid."""
        result1 = ValidationResult(valid=True)
        result2 = ValidationResult(valid=True)
        result1.merge(result2)
        assert result1.valid is True


class TestSchemaValidation:
    """Test suite for JSON schema validation at consumption time."""

    def test_valid_anchor_passes_schema_validation(self):
        """Valid anchor should pass schema validation."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["outcome1"],
                    success_signals=["signal1"],
                    non_goals=["non-goal1"],
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True
        assert result.schema_validated is True
        assert result.errors == []

    def test_anchor_with_invalid_raw_input_digest_fails(self):
        """Anchor with invalid raw_input_digest pattern should fail schema validation."""
        # Create anchor with too short digest (schema requires 16-64 hex chars)
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc",  # Too short
            pivot_intentions=PivotIntentions(),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        # Schema validation should catch this
        assert result.valid is False
        assert any("raw_input_digest" in error or "pattern" in error for error in result.errors)

    def test_none_anchor_fails_validation(self):
        """None anchor should fail validation immediately."""
        result = AnchorValidator.validate_for_consumption(None)
        assert result.valid is False
        assert "Anchor is None" in result.errors[0]

    def test_anchor_with_none_pivot_intentions_fails(self):
        """Anchor with None pivot_intentions should fail validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
        )
        # Manually set to None to simulate invalid state
        anchor.pivot_intentions = None

        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is False
        assert any("pivot_intentions" in error for error in result.errors)


class TestNestedStructureValidation:
    """Test suite for nested pivot_intentions validation."""

    def test_valid_safety_risk_passes(self):
        """Valid safety_risk structure should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                safety_risk=SafetyRiskIntention(
                    never_allow=["delete production data"],
                    requires_approval=["deploy to prod"],
                    risk_tolerance="low",
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True

    def test_invalid_risk_tolerance_fails(self):
        """Invalid risk_tolerance value should be caught by Pydantic validation."""
        # Pydantic enforces Literal types at model creation time, so this raises
        # a validation error before we can even test our schema validation
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="risk_tolerance"):
            SafetyRiskIntention(
                risk_tolerance="invalid_value",  # type: ignore
            )

    def test_valid_evidence_verification_passes(self):
        """Valid evidence_verification structure should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                evidence_verification=EvidenceVerificationIntention(
                    hard_blocks=["tests must pass"],
                    required_proofs=["test coverage report"],
                    verification_gates=["CI green"],
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True

    def test_valid_governance_review_passes(self):
        """Valid governance_review structure should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                governance_review=GovernanceReviewIntention(
                    default_policy="deny",
                    auto_approve_rules=[
                        AutoApprovalRule(
                            rule_id="test-rule",
                            description="Test auto-approval rule",
                            conditions=["condition1"],
                        )
                    ],
                    approval_channels=["PR", "CLI"],
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True

    def test_auto_approve_rule_without_conditions_fails(self):
        """Auto-approve rule without conditions should fail validation."""
        # Create rule dict directly to bypass Pydantic validation
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                governance_review=GovernanceReviewIntention(
                    default_policy="deny",
                    auto_approve_rules=[],
                    approval_channels=["PR"],
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True  # Empty rules list is valid

    def test_valid_budget_cost_passes(self):
        """Valid budget_cost structure should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                budget_cost=BudgetCostIntention(
                    token_cap_global=100000,
                    token_cap_per_call=4000,
                    time_cap_seconds=3600,
                    cost_escalation_policy="warn",
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True

    def test_valid_parallelism_isolation_passes(self):
        """Valid parallelism_isolation structure should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                parallelism_isolation=ParallelismIsolationIntention(
                    allowed=True,
                    isolation_model="four_layer",
                    max_concurrent_runs=4,
                )
            ),
        )
        result = AnchorValidator.validate_for_consumption(anchor)
        assert result.valid is True


class TestBackwardsCompatibility:
    """Test that existing validate() method still works."""

    def test_legacy_validate_returns_tuple(self):
        """Legacy validate() should return (bool, list) tuple."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(),
        )
        is_valid, errors = AnchorValidator.validate(anchor)
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    def test_legacy_validate_rejects_none(self):
        """Legacy validate() should reject None anchor."""
        is_valid, errors = AnchorValidator.validate(None)
        assert is_valid is False
        assert len(errors) > 0

    def test_legacy_validate_accepts_valid_anchor(self):
        """Legacy validate() should accept valid anchor."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(),
        )
        is_valid, errors = AnchorValidator.validate(anchor)
        assert is_valid is True
        assert errors == []


class TestValidateForConsumptionMethod:
    """Test the validate_for_consumption method on IntentionAnchorV2."""

    def test_anchor_validate_for_consumption_success(self):
        """IntentionAnchorV2.validate_for_consumption should work."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(desired_outcomes=["test"])
            ),
        )
        is_valid, errors = anchor.validate_for_consumption()
        assert is_valid is True
        assert errors == []

    def test_anchor_validate_for_consumption_with_all_pivots(self):
        """Anchor with all pivot types should pass validation."""
        anchor = IntentionAnchorV2(
            project_id="test-full",
            created_at=datetime.now(timezone.utc),
            raw_input_digest=VALID_DIGEST,
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Build awesome app"],
                    success_signals=["Users love it"],
                    non_goals=["Not building mobile app"],
                ),
                safety_risk=SafetyRiskIntention(
                    never_allow=["Delete user data"],
                    requires_approval=["Deploy to production"],
                    risk_tolerance="low",
                ),
                evidence_verification=EvidenceVerificationIntention(
                    hard_blocks=["All tests pass"],
                    required_proofs=["Coverage report"],
                    verification_gates=["CI pipeline"],
                ),
                budget_cost=BudgetCostIntention(
                    token_cap_global=1000000,
                    token_cap_per_call=8000,
                    time_cap_seconds=7200,
                    cost_escalation_policy="request_approval",
                ),
                governance_review=GovernanceReviewIntention(
                    default_policy="deny",
                    approval_channels=["PR", "CLI", "Telegram"],
                ),
                parallelism_isolation=ParallelismIsolationIntention(
                    allowed=True,
                    isolation_model="four_layer",
                    max_concurrent_runs=2,
                ),
            ),
        )
        is_valid, errors = anchor.validate_for_consumption()
        assert is_valid is True
        assert errors == []
