"""Tests for phase-type aware intention anchor validation.

Tests that IntentionAnchorV2 correctly validates against phase-specific
pivot type requirements.
"""

from datetime import datetime, timezone

import pytest

from src.autopack.intention_anchor.phase_type_registry import (
    PhaseTypeRegistry,
    PhaseTypePivots,
    CustomPivot,
)
from src.autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    NorthStarIntention,
    ScopeBoundariesIntention,
    SafetyRiskIntention,
    BudgetCostIntention,
    EvidenceVerificationIntention,
    PivotIntentions,
)


@pytest.fixture
def registry():
    """Create registry and load config."""
    reg = PhaseTypeRegistry()
    reg.load_from_config("config/phase_type_pivots.yaml")
    return reg


@pytest.fixture
def sample_anchor():
    """Create a sample IntentionAnchorV2 for testing."""
    return IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            north_star=NorthStarIntention(
                desired_outcomes=["Goal 1"],
                success_signals=["Signal 1"],
            ),
            scope_boundaries=ScopeBoundariesIntention(
                allowed_write_roots=["/src"],
            ),
        ),
    )


class TestPhaseTypeRegistry:
    """Test PhaseTypeRegistry functionality."""

    def test_registry_loads_config(self, registry):
        """Test that registry successfully loads YAML config."""
        assert len(registry.list_phase_types()) > 0

    def test_registry_has_build_phase(self, registry):
        """Test that 'build' phase type is registered."""
        assert "build" in registry.list_phase_types()

    def test_registry_has_tidy_phase(self, registry):
        """Test that 'tidy' phase type is registered."""
        assert "tidy" in registry.list_phase_types()

    def test_build_phase_requires_budget(self, registry):
        """Test that build phase requires budget_cost pivot."""
        pivots = registry.get_pivots_for_phase("build")
        assert "budget_cost" in pivots.required_pivots

    def test_build_phase_requires_north_star(self, registry):
        """Test that build phase requires north_star pivot."""
        pivots = registry.get_pivots_for_phase("build")
        assert "north_star" in pivots.required_pivots

    def test_tidy_phase_has_cleanliness_custom_pivot(self, registry):
        """Test that tidy phase has cleanliness_threshold custom pivot."""
        pivots = registry.get_pivots_for_phase("tidy")
        custom_names = {p.name for p in pivots.custom_pivots}
        assert "cleanliness_threshold" in custom_names

    def test_tidy_cleanliness_has_default(self, registry):
        """Test that cleanliness_threshold has default value."""
        pivots = registry.get_pivots_for_phase("tidy")
        cleanliness = next(p for p in pivots.custom_pivots if p.name == "cleanliness_threshold")
        assert cleanliness.default == 0.8

    def test_tidy_phase_has_preserve_patterns_custom_pivot(self, registry):
        """Test that tidy phase has preserve_patterns custom pivot."""
        pivots = registry.get_pivots_for_phase("tidy")
        custom_names = {p.name for p in pivots.custom_pivots}
        assert "preserve_patterns" in custom_names

    def test_doctor_phase_has_diagnosis_depth_custom_pivot(self, registry):
        """Test that doctor phase has diagnosis_depth custom pivot."""
        pivots = registry.get_pivots_for_phase("doctor")
        custom_names = {p.name for p in pivots.custom_pivots}
        assert "diagnosis_depth" in custom_names

    def test_doctor_phase_requires_safety_risk(self, registry):
        """Test that doctor phase requires safety_risk pivot."""
        pivots = registry.get_pivots_for_phase("doctor")
        assert "safety_risk" in pivots.required_pivots

    def test_audit_phase_requires_evidence(self, registry):
        """Test that audit phase requires evidence_verification pivot."""
        pivots = registry.get_pivots_for_phase("audit")
        assert "evidence_verification" in pivots.required_pivots

    def test_test_phase_optional_parallelism(self, registry):
        """Test that test phase has parallelism as optional."""
        pivots = registry.get_pivots_for_phase("test")
        assert "parallelism_isolation" in pivots.optional_pivots

    def test_default_pivot_config_for_unknown_phase(self, registry):
        """Test that unknown phase type gets default pivot config."""
        pivots = registry.get_pivots_for_phase("unknown_phase")
        assert "north_star" in pivots.required_pivots
        assert "scope_boundaries" in pivots.required_pivots

    def test_phase_type_pivots_all_pivot_names(self, registry):
        """Test all_pivot_names includes universal and custom pivots."""
        pivots = registry.get_pivots_for_phase("tidy")
        all_names = pivots.all_pivot_names()
        assert "north_star" in all_names
        assert "cleanliness_threshold" in all_names


class TestIntentionAnchorPhaseValidation:
    """Test IntentionAnchorV2 phase-specific validation."""

    def test_anchor_validates_for_test_phase(self, sample_anchor, registry):
        """Test that anchor with north_star and scope validates for test phase."""
        is_valid, errors = sample_anchor.validate_for_phase("test")
        assert is_valid
        assert len(errors) == 0

    def test_anchor_fails_validation_for_build_phase_missing_budget(self, sample_anchor, registry):
        """Test that anchor fails build phase validation without budget."""
        is_valid, errors = sample_anchor.validate_for_phase("build")
        assert not is_valid
        assert len(errors) > 0
        assert any("budget" in error.lower() for error in errors)

    def test_anchor_passes_validation_for_build_phase_with_budget(self, registry):
        """Test that anchor passes build phase validation with budget."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Goal 1"],
                    success_signals=["Signal 1"],
                ),
                scope_boundaries=ScopeBoundariesIntention(
                    allowed_write_roots=["/src"],
                ),
                budget_cost=BudgetCostIntention(
                    token_cap_global=100000,
                ),
            ),
        )
        is_valid, errors = anchor.validate_for_phase("build")
        assert is_valid
        assert len(errors) == 0

    def test_anchor_fails_validation_for_audit_phase_missing_evidence(
        self, sample_anchor, registry
    ):
        """Test that anchor fails audit phase validation without evidence."""
        is_valid, errors = sample_anchor.validate_for_phase("audit")
        assert not is_valid
        assert len(errors) > 0
        assert any("evidence" in error.lower() for error in errors)

    def test_anchor_passes_validation_for_audit_with_evidence(self, registry):
        """Test that anchor passes audit phase validation with evidence."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Goal 1"],
                    success_signals=["Signal 1"],
                ),
                scope_boundaries=ScopeBoundariesIntention(
                    allowed_write_roots=["/src"],
                ),
                evidence_verification=EvidenceVerificationIntention(
                    hard_blocks=["No data loss"],
                ),
            ),
        )
        is_valid, errors = anchor.validate_for_phase("audit")
        assert is_valid
        assert len(errors) == 0

    def test_anchor_fails_validation_for_doctor_phase_missing_safety_risk(
        self, sample_anchor, registry
    ):
        """Test that anchor fails doctor phase validation without safety_risk."""
        is_valid, errors = sample_anchor.validate_for_phase("doctor")
        assert not is_valid
        assert len(errors) > 0
        assert any("safety" in error.lower() for error in errors)

    def test_anchor_passes_validation_for_doctor_with_safety_risk(self, registry):
        """Test that anchor passes doctor phase validation with safety_risk."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Goal 1"],
                    success_signals=["Signal 1"],
                ),
                scope_boundaries=ScopeBoundariesIntention(
                    allowed_write_roots=["/src"],
                ),
                safety_risk=SafetyRiskIntention(
                    never_allow=["Data corruption"],
                ),
            ),
        )
        is_valid, errors = anchor.validate_for_phase("doctor")
        assert is_valid
        assert len(errors) == 0

    def test_anchor_can_store_custom_pivots(self):
        """Test that anchor can store custom pivot values."""
        anchor = IntentionAnchorV2(
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="abc123",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(
                    desired_outcomes=["Goal 1"],
                    success_signals=["Signal 1"],
                ),
            ),
            custom_pivots={
                "cleanliness_threshold": 0.9,
                "preserve_patterns": ["*.md", "docs/**"],
            },
        )
        assert anchor.custom_pivots["cleanliness_threshold"] == 0.9
        assert anchor.custom_pivots["preserve_patterns"] == ["*.md", "docs/**"]

    def test_custom_pivot_definition_has_metadata(self):
        """Test CustomPivot stores all metadata."""
        custom_pivot = CustomPivot(
            name="cleanliness_threshold",
            type="float",
            default=0.8,
            description="Minimum cleanliness score to achieve",
        )
        assert custom_pivot.name == "cleanliness_threshold"
        assert custom_pivot.type == "float"
        assert custom_pivot.default == 0.8
        assert "cleanliness" in custom_pivot.description.lower()


class TestPhaseTypePivots:
    """Test PhaseTypePivots dataclass."""

    def test_phase_type_pivots_all_pivot_names_includes_required(self):
        """Test that all_pivot_names includes required pivots."""
        pivots = PhaseTypePivots(
            phase_type="build",
            required_pivots=["north_star"],
            optional_pivots=["scope_boundaries"],
        )
        all_names = pivots.all_pivot_names()
        assert "north_star" in all_names
        assert "scope_boundaries" in all_names

    def test_phase_type_pivots_all_pivot_names_includes_custom(self):
        """Test that all_pivot_names includes custom pivots."""
        pivots = PhaseTypePivots(
            phase_type="tidy",
            required_pivots=["north_star"],
            custom_pivots=[
                CustomPivot(
                    name="cleanliness_threshold",
                    type="float",
                    default=0.8,
                )
            ],
        )
        all_names = pivots.all_pivot_names()
        assert "cleanliness_threshold" in all_names
        assert "north_star" in all_names
