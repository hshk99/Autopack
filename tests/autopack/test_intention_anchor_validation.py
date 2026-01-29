"""Tests for IntentionAnchor runtime validation.

These tests verify that the validation utilities work correctly for safe field access
at consumption time, ensuring that code doesn't assume fields exist without null checks.
"""

from datetime import datetime, timezone

import pytest

from autopack.intention_anchor.v2 import IntentionAnchorV2, NorthStarIntention, PivotIntentions
from autopack.intention_anchor.validators import (
    AnchorValidator,
    safe_anchor_access,
    validate_anchor_field,
)


class TestValidateAnchorField:
    """Test suite for validate_anchor_field function."""

    def test_validate_anchor_field_returns_none_for_missing_optional(self):
        """validate_anchor_field should return None for missing optional fields."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        result = validate_anchor_field(anchor, "nonexistent_field", required=False)
        assert result is None

    def test_validate_anchor_field_raises_for_required_missing(self):
        """validate_anchor_field should raise ValueError for required missing fields."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        with pytest.raises(ValueError, match="Required anchor field"):
            validate_anchor_field(anchor, "nonexistent_field", required=True)

    def test_validate_anchor_field_returns_value_when_present(self):
        """validate_anchor_field should return the value when present."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        result = validate_anchor_field(anchor, "project_id", required=False)
        assert result == "test-project"

    def test_validate_anchor_field_handles_none_anchor(self):
        """validate_anchor_field should handle None anchor gracefully."""
        result = validate_anchor_field(None, "any_field", required=False)
        assert result is None

    def test_validate_anchor_field_raises_for_none_anchor_required(self):
        """validate_anchor_field should raise for None anchor when field is required."""
        with pytest.raises(ValueError, match="Anchor is None"):
            validate_anchor_field(None, "any_field", required=True)

    def test_validate_anchor_field_with_nested_object(self):
        """validate_anchor_field should work with nested objects."""
        north_star = NorthStarIntention(desired_outcomes=["outcome1", "outcome2"])
        pivot_intentions = PivotIntentions(north_star=north_star)
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=pivot_intentions,
        )
        result = validate_anchor_field(anchor, "pivot_intentions", required=False)
        assert result is not None
        assert result.north_star.desired_outcomes == ["outcome1", "outcome2"]


class TestAnchorValidator:
    """Test suite for AnchorValidator class."""

    def test_anchor_validator_accepts_valid_anchor(self):
        """AnchorValidator should accept anchor with required fields."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(),
        )
        is_valid, errors = AnchorValidator.validate(anchor)
        assert is_valid is True
        assert errors == []

    def test_anchor_validator_rejects_none_anchor(self):
        """AnchorValidator should reject None anchor."""
        is_valid, errors = AnchorValidator.validate(None)
        assert is_valid is False
        assert "Anchor is None" in errors

    def test_anchor_validator_detects_missing_required_fields(self):
        """AnchorValidator should detect missing required fields."""
        # Create an anchor with None pivot_intentions
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        # Manually set pivot_intentions to None to test validation
        anchor.pivot_intentions = None

        is_valid, errors = AnchorValidator.validate(anchor)
        assert is_valid is False
        assert any("pivot_intentions" in error for error in errors)

    def test_anchor_validator_validate_pivot_intentions_success(self):
        """validate_pivot_intentions should return pivot when present."""
        north_star = NorthStarIntention(desired_outcomes=["test"])
        pivot_intentions = PivotIntentions(north_star=north_star)
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=pivot_intentions,
        )
        result = AnchorValidator.validate_pivot_intentions(anchor, "north_star", required=False)
        assert result is not None
        assert result.desired_outcomes == ["test"]

    def test_anchor_validator_validate_pivot_intentions_missing_optional(self):
        """validate_pivot_intentions should return None for missing optional pivot."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(),
        )
        result = AnchorValidator.validate_pivot_intentions(anchor, "safety_risk", required=False)
        assert result is None

    def test_anchor_validator_validate_pivot_intentions_raises_when_required(self):
        """validate_pivot_intentions should raise when required pivot is missing."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(),
        )
        with pytest.raises(ValueError, match="Required pivot intention"):
            AnchorValidator.validate_pivot_intentions(anchor, "north_star", required=True)

    def test_anchor_validator_validate_pivot_intentions_none_anchor(self):
        """validate_pivot_intentions should handle None anchor gracefully."""
        result = AnchorValidator.validate_pivot_intentions(None, "north_star", required=False)
        assert result is None

    def test_anchor_validator_validate_pivot_intentions_none_anchor_required(self):
        """validate_pivot_intentions should raise for None anchor when required."""
        with pytest.raises(ValueError, match="Anchor is None"):
            AnchorValidator.validate_pivot_intentions(None, "north_star", required=True)


class TestIntentionAnchorV2Methods:
    """Test suite for IntentionAnchorV2 validation methods."""

    def test_anchor_validate_for_consumption_success(self):
        """validate_for_consumption should succeed for valid anchor."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(),
        )
        is_valid, errors = anchor.validate_for_consumption()
        assert is_valid is True
        assert errors == []

    def test_anchor_validate_for_consumption_fails_for_invalid(self):
        """validate_for_consumption should fail for invalid anchor."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        anchor.pivot_intentions = None

        is_valid, errors = anchor.validate_for_consumption()
        assert is_valid is False
        assert len(errors) > 0

    def test_anchor_get_safe_returns_value(self):
        """get_safe should return the field value when present."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(),
        )
        result = anchor.get_safe("project_id", default="default")
        assert result == "test-project"

    def test_anchor_get_safe_returns_default_for_missing(self):
        """get_safe should return default for missing field."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        result = anchor.get_safe("nonexistent_field", default="default_value")
        assert result == "default_value"

    def test_anchor_get_safe_returns_default_for_none_value(self):
        """get_safe should return default when field is None."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            updated_at=None,  # Explicitly None
        )
        result = anchor.get_safe("updated_at", default="default_value")
        assert result == "default_value"

    def test_anchor_get_safe_with_none_default(self):
        """get_safe should handle None as default value."""
        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        result = anchor.get_safe("nonexistent_field", default=None)
        assert result is None


class TestSafeAnchorAccessDecorator:
    """Test suite for safe_anchor_access decorator."""

    def test_safe_anchor_access_decorator_with_present_field(self):
        """Decorator should work when field is present."""

        class TestClass:
            def __init__(self, anchor):
                self.anchor = anchor

            @safe_anchor_access("project_id", default="default")
            def get_project(self):
                return self.anchor.project_id.upper()

        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        obj = TestClass(anchor)
        result = obj.get_project()
        assert result == "TEST"

    def test_safe_anchor_access_decorator_with_missing_field(self):
        """Decorator should return default when field is missing."""

        class TestClass:
            def __init__(self, anchor):
                self.anchor = anchor

            @safe_anchor_access("nonexistent_field", default="default_value")
            def get_field(self):
                return "should not be called"

        anchor = IntentionAnchorV2(
            project_id="test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
        )
        obj = TestClass(anchor)
        result = obj.get_field()
        assert result == "default_value"

    def test_safe_anchor_access_decorator_with_none_anchor(self):
        """Decorator should handle None anchor."""

        class TestClass:
            def __init__(self):
                self.anchor = None

            @safe_anchor_access("any_field", default="safe_default")
            def get_field(self):
                return "should not be called"

        obj = TestClass()
        result = obj.get_field()
        assert result == "safe_default"
