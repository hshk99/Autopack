"""
Tests for Phase E: Routing override consumption.

Verifies that routing snapshot entries are applied as model overrides
and consumed by ModelRouter during execution.
"""


from autopack.autonomous.executor_wiring import (
    TIER_TO_COMPLEXITY,
    initialize_intention_first_loop,
)
from autopack.intention_anchor.models import (
    IntentionAnchor,
    IntentionBudgets,
    IntentionConstraints,
)
from datetime import datetime, timezone


class TestInitialRoutingOverrides:
    """Test that routing snapshot entries are applied as overrides at run start."""

    def test_snapshot_entries_applied_to_run_context(self, tmp_path):
        """Routing snapshot entries are applied to run_context at initialization."""
        # Create minimal intention anchor
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run-phase-e",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=1,
            north_star="Test routing override consumption",
            success_criteria=["Overrides applied"],
            constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
            budgets=IntentionBudgets(max_context_chars=100_000, max_sot_chars=50_000),
        )

        # Initialize wiring (will create routing snapshot)
        wiring = initialize_intention_first_loop(
            run_id="test-run-phase-e",
            project_id="test-project",
            intention_anchor=anchor,
        )

        # Verify run_context has model_overrides
        assert "model_overrides" in wiring.run_context
        assert "builder" in wiring.run_context["model_overrides"]
        assert "auditor" in wiring.run_context["model_overrides"]

        # Verify overrides are populated (not empty)
        builder_overrides = wiring.run_context["model_overrides"]["builder"]
        auditor_overrides = wiring.run_context["model_overrides"]["auditor"]

        assert len(builder_overrides) > 0, "Builder overrides should be populated"
        assert len(auditor_overrides) > 0, "Auditor overrides should be populated"

    def test_tier_to_complexity_mapping(self):
        """TIER_TO_COMPLEXITY mapping is deterministic and complete."""
        assert TIER_TO_COMPLEXITY["haiku"] == "low"
        assert TIER_TO_COMPLEXITY["sonnet"] == "medium"
        assert TIER_TO_COMPLEXITY["opus"] == "high"

    def test_override_keys_match_expected_format(self, tmp_path):
        """Override keys follow the {task_category}:{complexity} format."""
        # Create minimal intention anchor
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run-override-keys",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=1,
            north_star="Test override key format",
            success_criteria=["Keys valid"],
            constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
            budgets=IntentionBudgets(max_context_chars=100_000, max_sot_chars=50_000),
        )

        # Initialize wiring
        wiring = initialize_intention_first_loop(
            run_id="test-run-override-keys",
            project_id="test-project",
            intention_anchor=anchor,
        )

        # Check override keys match expected format
        builder_overrides = wiring.run_context["model_overrides"]["builder"]

        for key in builder_overrides.keys():
            # Should be in format "{task_category}:{complexity}"
            assert ":" in key, f"Override key {key} missing colon separator"
            task_category, complexity = key.split(":", 1)
            assert task_category in [
                "general",
                "code_generation",
                "code_review",
                "analysis",
            ]
            assert complexity in ["low", "medium", "high"]

    def test_all_tiers_get_overrides(self, tmp_path):
        """All tiers in snapshot get corresponding overrides."""
        # Create minimal intention anchor
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run-all-tiers",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=1,
            north_star="Test all tiers",
            success_criteria=["All tiers covered"],
            constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
            budgets=IntentionBudgets(max_context_chars=100_000, max_sot_chars=50_000),
        )

        # Initialize wiring
        wiring = initialize_intention_first_loop(
            run_id="test-run-all-tiers",
            project_id="test-project",
            intention_anchor=anchor,
        )

        # Get snapshot entries
        snapshot = wiring.run_state.routing_snapshot
        builder_overrides = wiring.run_context["model_overrides"]["builder"]

        # For each tier in snapshot, verify overrides exist
        for entry in snapshot.entries:
            complexity = TIER_TO_COMPLEXITY.get(entry.tier, "medium")
            # Check at least one override exists for this complexity
            matching_keys = [k for k in builder_overrides.keys() if k.endswith(f":{complexity}")]
            assert len(matching_keys) > 0, f"No overrides found for tier {entry.tier} (complexity {complexity})"

    def test_overrides_contain_valid_model_ids(self, tmp_path):
        """Override values are valid model IDs from snapshot."""
        # Create minimal intention anchor
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run-valid-models",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=1,
            north_star="Test valid model IDs",
            success_criteria=["Model IDs valid"],
            constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
            budgets=IntentionBudgets(max_context_chars=100_000, max_sot_chars=50_000),
        )

        # Initialize wiring
        wiring = initialize_intention_first_loop(
            run_id="test-run-valid-models",
            project_id="test-project",
            intention_anchor=anchor,
        )

        # Get snapshot model IDs
        snapshot = wiring.run_state.routing_snapshot
        valid_model_ids = {entry.model_id for entry in snapshot.entries}

        # Verify all override values are valid model IDs from snapshot
        builder_overrides = wiring.run_context["model_overrides"]["builder"]
        for model_id in builder_overrides.values():
            assert model_id in valid_model_ids, f"Model ID {model_id} not in snapshot"


class TestEscalationOverrides:
    """Test that tier escalation updates run_context overrides."""

    def test_escalation_updates_run_context(self, tmp_path):
        """Tier escalation updates run_context with escalated model override."""
        from autopack.autonomous.executor_wiring import apply_model_escalation

        # Create minimal intention anchor
        anchor = IntentionAnchor(
            anchor_id="test-anchor",
            run_id="test-run-escalation",
            project_id="test-project",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            version=1,
            north_star="Test escalation overrides",
            success_criteria=["Escalation works"],
            constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
            budgets=IntentionBudgets(max_context_chars=100_000, max_sot_chars=50_000),
        )

        # Initialize wiring
        wiring = initialize_intention_first_loop(
            run_id="test-run-escalation",
            project_id="test-project",
            intention_anchor=anchor,
        )

        # Get initial haiku model for general:low
        initial_haiku_model = wiring.run_context["model_overrides"]["builder"]["general:low"]

        # Apply escalation from haiku to sonnet
        phase_spec = {"task_category": "general"}
        escalated_entry = apply_model_escalation(
            wiring=wiring,
            phase_id="test-phase",
            phase_spec=phase_spec,
            current_tier="haiku",
            safety_profile="normal",
        )

        # Verify escalation succeeded
        assert escalated_entry is not None, "Escalation should succeed"
        assert escalated_entry.tier == "sonnet", "Should escalate to sonnet tier"

        # Verify override was applied for escalated tier
        escalated_complexity = TIER_TO_COMPLEXITY.get("sonnet", "medium")
        override_key = f"general:{escalated_complexity}"
        assert override_key in wiring.run_context["model_overrides"]["builder"]
        assert wiring.run_context["model_overrides"]["builder"][override_key] == escalated_entry.model_id

        # Verify original haiku override unchanged
        assert wiring.run_context["model_overrides"]["builder"]["general:low"] == initial_haiku_model
