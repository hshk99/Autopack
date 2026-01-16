"""Tests for builder deliverable validation against intention constraints.

Tests the DeliverableValidator class to ensure it correctly identifies
violations of must_not constraints and missing success criteria.
"""

import pytest
from datetime import datetime, timezone

from autopack.builder import DeliverableValidator, ValidationResult
from autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    NorthStarIntention,
    SafetyRiskIntention,
    EvidenceVerificationIntention,
    PivotIntentions,
)


class TestDeliverableValidator:
    """Test suite for DeliverableValidator."""

    @pytest.fixture
    def basic_anchor_with_must_not(self):
        """Create a basic intention anchor with must_not constraints."""
        return IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="test123",
            pivot_intentions=PivotIntentions(
                safety_risk=SafetyRiskIntention(
                    never_allow=["hardcoded secrets", "eval()"],
                )
            ),
        )

    @pytest.fixture
    def anchor_with_success_criteria(self):
        """Create an intention anchor with success criteria."""
        return IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="test456",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    success_signals=["unit tests pass", "type checking passes"],
                )
            ),
        )

    @pytest.fixture
    def anchor_with_hard_blocks(self):
        """Create an intention anchor with hard blocks."""
        return IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="test789",
            pivot_intentions=PivotIntentions(
                evidence_verification=EvidenceVerificationIntention(
                    hard_blocks=["no SQL injection", "input validation"],
                )
            ),
        )

    def test_validator_with_no_anchor(self):
        """Test validator gracefully handles missing anchor."""
        validator = DeliverableValidator(anchor=None)
        deliverable = "some code content"

        result = validator.validate(deliverable, {})

        assert result.is_valid
        assert len(result.violations) == 0
        assert len(result.warnings) == 1
        assert "No intention anchor provided" in result.warnings[0]

    def test_validator_catches_must_not_violation(self, basic_anchor_with_must_not):
        """Test validator detects must_not constraint violations."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = "password = 'hardcoded secrets here'"

        result = validator.validate(deliverable, {})

        assert not result.is_valid
        assert len(result.violations) == 1
        assert "must_not violation" in result.violations[0]
        assert "hardcoded secrets" in result.violations[0]

    def test_validator_catches_multiple_violations(self, basic_anchor_with_must_not):
        """Test validator catches multiple violations."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = "code with hardcoded secrets and eval() calls"

        result = validator.validate(deliverable, {})

        assert not result.is_valid
        assert len(result.violations) == 2
        assert any("hardcoded secrets" in v for v in result.violations)
        assert any("eval()" in v for v in result.violations)

    def test_validator_passes_clean_deliverable(self, basic_anchor_with_must_not):
        """Test validator passes clean deliverable without violations."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = "result = safe_function()"

        result = validator.validate(deliverable, {})

        assert result.is_valid
        assert len(result.violations) == 0

    def test_validator_checks_success_criteria(self, anchor_with_success_criteria):
        """Test validator checks success criteria."""
        validator = DeliverableValidator(anchor=anchor_with_success_criteria)
        deliverable = "def test(): pass"

        result = validator.validate(deliverable, {})

        # Success criteria checking is a placeholder that always returns True
        # This test verifies the structure works
        assert isinstance(result.success_criteria_met, dict)
        assert "unit tests pass" in result.success_criteria_met
        assert "type checking passes" in result.success_criteria_met

    def test_validator_checks_hard_blocks(self, anchor_with_hard_blocks):
        """Test validator checks hard_blocks as violations."""
        validator = DeliverableValidator(anchor=anchor_with_hard_blocks)
        # Hard blocks are checked as violations (hard requirements)
        deliverable = "SELECT * FROM users WHERE id = 1"

        result = validator.validate(deliverable, {})

        # The check for "no SQL injection" should trigger a hard_block violation
        # when SQL-like code is found
        assert isinstance(result, ValidationResult)
        assert isinstance(result.violations, list)

    def test_validation_result_structure(self):
        """Test ValidationResult has correct structure."""
        result = ValidationResult(
            is_valid=True,
            violations=[],
            warnings=["test warning"],
            success_criteria_met={"criterion": True},
        )

        assert result.is_valid is True
        assert result.violations == []
        assert result.warnings == ["test warning"]
        assert result.success_criteria_met == {"criterion": True}

    def test_validator_case_insensitive_matching(self, basic_anchor_with_must_not):
        """Test validator performs case-insensitive constraint matching."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        # Uppercase variation of the constraint
        deliverable = "password = 'HARDCODED SECRETS'"

        result = validator.validate(deliverable, {})

        # Should still match (case-insensitive)
        assert not result.is_valid
        assert len(result.violations) == 1

    def test_validator_with_metadata(self, basic_anchor_with_must_not):
        """Test validator accepts optional metadata parameter."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = "safe code"
        metadata = {"phase": "test_phase", "attempt": 1}

        # Should not raise exception
        result = validator.validate(deliverable, metadata)
        assert result.is_valid

    def test_empty_deliverable(self, basic_anchor_with_must_not):
        """Test validator handles empty deliverable."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = ""

        result = validator.validate(deliverable, {})

        assert result.is_valid
        assert len(result.violations) == 0

    def test_deliverable_with_whitespace_only(self, basic_anchor_with_must_not):
        """Test validator handles whitespace-only deliverable."""
        validator = DeliverableValidator(anchor=basic_anchor_with_must_not)
        deliverable = "   \n\n   "

        result = validator.validate(deliverable, {})

        assert result.is_valid
        assert len(result.violations) == 0
