"""Tests for IMP-LOOP-018: Rule Effectiveness Tracking Activation

Tests cover:
- RuleAgingTracker persistence and loading
- Recording validation success/failure
- Deprecation filtering in get_active_rules_for_phase
- Integration with LearningPipeline for phase outcome tracking
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


from autopack.learned_rules import (
    DiscoveryStage,
    LearnedRule,
    RuleAgingTracker,
    get_active_rules_for_phase,
    record_rule_validation_outcome,
)

# ============================================================================
# RuleAgingTracker Tests
# ============================================================================


class TestRuleAgingTracker:
    """Tests for RuleAgingTracker persistence layer."""

    def test_init_creates_empty_aging_data(self, tmp_path):
        """Tracker should initialize with empty aging data when file doesn't exist."""
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=tmp_path / "RULE_AGING.json",
        ):
            tracker = RuleAgingTracker("test-project")
            assert tracker._aging_data == {}

    def test_record_validation_success_creates_entry(self, tmp_path):
        """Recording success should create a new entry if none exists."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            tracker.record_validation_success("test.rule_001")

            assert "test.rule_001" in tracker._aging_data
            assert tracker._aging_data["test.rule_001"]["validation_failures"] == 0
            assert aging_file.exists()

    def test_record_validation_failure_increments_failures(self, tmp_path):
        """Recording failure should increment failure count."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            tracker.record_validation_failure("test.rule_001")
            tracker.record_validation_failure("test.rule_001")

            assert tracker._aging_data["test.rule_001"]["validation_failures"] == 2

    def test_should_deprecate_fresh_rule(self, tmp_path):
        """Fresh rules should not be deprecated."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            tracker.record_validation_success("test.rule_001")

            assert tracker.should_deprecate("test.rule_001") is False

    def test_should_deprecate_high_failure_rule(self, tmp_path):
        """Rules with many failures should be deprecated when combined with age."""
        aging_file = tmp_path / "RULE_AGING.json"

        # Create aging data directly with high failures AND age to exceed 0.7
        # (failure_factor capped at 0.5, need age_factor > 0.2 to exceed 0.7)
        now = datetime.now(timezone.utc)
        old_creation = now - timedelta(days=150)  # ~0.41 age factor

        aging_data = {
            "test.rule_001": {
                "creation_date": old_creation.isoformat(),
                "last_validation_date": now.isoformat(),
                "age_days": 150,
                "validation_failures": 8,  # 0.5 capped
                "decay_score": 0.91,  # 0.41 (age) + 0.5 (failures) = 0.91
            }
        }

        aging_file.parent.mkdir(parents=True, exist_ok=True)
        with open(aging_file, "w") as f:
            json.dump({"aging": aging_data}, f)

        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            assert tracker.should_deprecate("test.rule_001") is True

    def test_should_deprecate_unknown_rule(self, tmp_path):
        """Unknown rules should not be deprecated."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            assert tracker.should_deprecate("nonexistent.rule") is False

    def test_persistence_survives_reload(self, tmp_path):
        """Aging data should persist across tracker instances."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            # Create and save
            tracker1 = RuleAgingTracker("test-project")
            tracker1.record_validation_failure("test.rule_001")
            tracker1.record_validation_failure("test.rule_001")

            # Reload and verify
            tracker2 = RuleAgingTracker("test-project")
            assert tracker2._aging_data["test.rule_001"]["validation_failures"] == 2

    def test_get_aging_creates_from_rule_if_not_tracked(self, tmp_path):
        """get_or_create_aging should create tracker from rule if not tracked."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")
            rule = LearnedRule(
                rule_id="test.rule_001",
                task_category="testing",
                scope_pattern="*.py",
                constraint="Always use type hints",
                source_hint_ids=["run1:phase1"],
                promotion_count=3,
                first_seen=datetime.now(timezone.utc).isoformat(),
                last_seen=datetime.now(timezone.utc).isoformat(),
                status="active",
                stage=DiscoveryStage.RULE.value,
            )

            aging = tracker.get_or_create_aging(rule)
            assert aging.rule_id == "test.rule_001"
            assert aging.validation_failures == 0


# ============================================================================
# record_rule_validation_outcome Tests
# ============================================================================


class TestRecordRuleValidationOutcome:
    """Tests for the record_rule_validation_outcome function."""

    def test_records_success_for_multiple_rules(self, tmp_path):
        """Should record success for all provided rule IDs."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            rule_ids = ["rule1", "rule2", "rule3"]
            record_rule_validation_outcome("test-project", rule_ids, success=True)

            # Verify all rules were recorded
            tracker = RuleAgingTracker("test-project")
            for rule_id in rule_ids:
                assert rule_id in tracker._aging_data
                assert tracker._aging_data[rule_id]["validation_failures"] == 0

    def test_records_failure_for_multiple_rules(self, tmp_path):
        """Should record failure for all provided rule IDs."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            rule_ids = ["rule1", "rule2"]
            record_rule_validation_outcome("test-project", rule_ids, success=False)

            # Verify all rules have 1 failure
            tracker = RuleAgingTracker("test-project")
            for rule_id in rule_ids:
                assert tracker._aging_data[rule_id]["validation_failures"] == 1

    def test_empty_rule_list_no_op(self, tmp_path):
        """Empty rule list should be a no-op."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            record_rule_validation_outcome("test-project", [], success=True)
            # Should not create any files
            assert not aging_file.exists()


# ============================================================================
# get_active_rules_for_phase Deprecation Filtering Tests
# ============================================================================


class TestGetActiveRulesForPhaseDeprecation:
    """Tests for deprecation filtering in get_active_rules_for_phase."""

    def test_filters_out_deprecated_rules(self, tmp_path):
        """Deprecated rules should be filtered out."""
        rules_file = tmp_path / "docs" / "LEARNED_RULES.json"
        aging_file = tmp_path / "docs" / "RULE_AGING.json"
        rules_file.parent.mkdir(parents=True, exist_ok=True)

        # Create test rules
        rules = [
            {
                "rule_id": "active.rule",
                "task_category": "testing",
                "scope_pattern": None,
                "constraint": "Active rule",
                "source_hint_ids": [],
                "promotion_count": 5,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "stage": "rule",
            },
            {
                "rule_id": "deprecated.rule",
                "task_category": "testing",
                "scope_pattern": None,
                "constraint": "Deprecated rule",
                "source_hint_ids": [],
                "promotion_count": 3,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "stage": "rule",
            },
        ]
        with open(rules_file, "w") as f:
            json.dump({"rules": rules}, f)

        # Create aging data with high decay for deprecated rule
        aging_data = {
            "deprecated.rule": {
                "creation_date": datetime.now(timezone.utc).isoformat(),
                "last_validation_date": datetime.now(timezone.utc).isoformat(),
                "age_days": 0,
                "validation_failures": 8,  # 8 * 0.1 = 0.8 > 0.7
                "decay_score": 0.8,
            }
        }
        with open(aging_file, "w") as f:
            json.dump({"aging": aging_data}, f)

        phase = {"phase_id": "test-phase", "task_category": "testing"}

        with (
            patch(
                "autopack.learned_rules._get_project_rules_file",
                return_value=rules_file,
            ),
            patch(
                "autopack.learned_rules.RuleAgingTracker._get_aging_file",
                return_value=aging_file,
            ),
        ):
            result = get_active_rules_for_phase("test-project", phase)

            # Should only return the active rule, not the deprecated one
            assert len(result) == 1
            assert result[0].rule_id == "active.rule"

    def test_includes_rules_without_aging_data(self, tmp_path):
        """Rules without aging data should be included."""
        rules_file = tmp_path / "docs" / "LEARNED_RULES.json"
        aging_file = tmp_path / "docs" / "RULE_AGING.json"
        rules_file.parent.mkdir(parents=True, exist_ok=True)

        # Create test rule
        rules = [
            {
                "rule_id": "new.rule",
                "task_category": "testing",
                "scope_pattern": None,
                "constraint": "New rule without aging data",
                "source_hint_ids": [],
                "promotion_count": 1,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "stage": "rule",
            }
        ]
        with open(rules_file, "w") as f:
            json.dump({"rules": rules}, f)

        # No aging file - rule should still be included
        phase = {"phase_id": "test-phase", "task_category": "testing"}

        with (
            patch(
                "autopack.learned_rules._get_project_rules_file",
                return_value=rules_file,
            ),
            patch(
                "autopack.learned_rules.RuleAgingTracker._get_aging_file",
                return_value=aging_file,
            ),
        ):
            result = get_active_rules_for_phase("test-project", phase)

            assert len(result) == 1
            assert result[0].rule_id == "new.rule"


# ============================================================================
# LearningPipeline Integration Tests
# ============================================================================


class TestLearningPipelineRuleTracking:
    """Tests for LearningPipeline rule effectiveness tracking."""

    def test_register_applied_rules(self):
        """Should register applied rules for a phase."""
        from autopack.executor.learning_pipeline import LearningPipeline

        pipeline = LearningPipeline("test-run", project_id="test-project")
        rule_ids = ["rule1", "rule2"]

        pipeline.register_applied_rules("phase-1", rule_ids)

        assert pipeline.get_applied_rules_for_phase("phase-1") == rule_ids

    def test_record_phase_rule_effectiveness_success(self, tmp_path):
        """Should record success for applied rules when phase succeeds."""
        from autopack.executor.learning_pipeline import LearningPipeline

        aging_file = tmp_path / "RULE_AGING.json"

        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            pipeline = LearningPipeline("test-run", project_id="test-project")
            rule_ids = ["rule1", "rule2"]
            pipeline.register_applied_rules("phase-1", rule_ids)

            count = pipeline.record_phase_rule_effectiveness("phase-1", success=True)

            assert count == 2
            # Verify rules were recorded as success
            tracker = RuleAgingTracker("test-project")
            for rule_id in rule_ids:
                assert tracker._aging_data[rule_id]["validation_failures"] == 0

    def test_record_phase_rule_effectiveness_failure(self, tmp_path):
        """Should record failure for applied rules when phase fails."""
        from autopack.executor.learning_pipeline import LearningPipeline

        aging_file = tmp_path / "RULE_AGING.json"

        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            pipeline = LearningPipeline("test-run", project_id="test-project")
            rule_ids = ["rule1"]
            pipeline.register_applied_rules("phase-1", rule_ids)

            count = pipeline.record_phase_rule_effectiveness("phase-1", success=False)

            assert count == 1
            # Verify rule was recorded as failure
            tracker = RuleAgingTracker("test-project")
            assert tracker._aging_data["rule1"]["validation_failures"] == 1

    def test_record_clears_applied_rules_after_recording(self, tmp_path):
        """Applied rules should be cleared after recording effectiveness."""
        from autopack.executor.learning_pipeline import LearningPipeline

        aging_file = tmp_path / "RULE_AGING.json"

        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            pipeline = LearningPipeline("test-run", project_id="test-project")
            pipeline.register_applied_rules("phase-1", ["rule1"])
            pipeline.record_phase_rule_effectiveness("phase-1", success=True)

            # Should be empty after recording
            assert pipeline.get_applied_rules_for_phase("phase-1") == []

    def test_record_no_op_for_phase_without_rules(self, tmp_path):
        """Recording for phase without applied rules should return 0."""
        from autopack.executor.learning_pipeline import LearningPipeline

        pipeline = LearningPipeline("test-run", project_id="test-project")

        count = pipeline.record_phase_rule_effectiveness("unknown-phase", success=True)

        assert count == 0


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Edge case tests for rule effectiveness tracking."""

    def test_decay_score_calculation_consistency(self, tmp_path):
        """Decay score should be consistent between tracker and LearnedRuleAging."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")

            # Record 5 failures
            for _ in range(5):
                tracker.record_validation_failure("test.rule")

            # Get aging object and verify decay
            aging = tracker.get_aging("test.rule")
            assert aging is not None
            assert aging.validation_failures == 5
            assert aging.decay_score == 0.5  # 5 * 0.1 = 0.5

    def test_mixed_success_and_failure(self, tmp_path):
        """Mix of successes and failures should correctly update decay."""
        aging_file = tmp_path / "RULE_AGING.json"
        with patch(
            "autopack.learned_rules.RuleAgingTracker._get_aging_file",
            return_value=aging_file,
        ):
            tracker = RuleAgingTracker("test-project")

            # 3 successes, 2 failures
            tracker.record_validation_success("test.rule")
            tracker.record_validation_failure("test.rule")
            tracker.record_validation_success("test.rule")
            tracker.record_validation_failure("test.rule")
            tracker.record_validation_success("test.rule")

            aging = tracker.get_aging("test.rule")
            assert aging.validation_failures == 2
            assert aging.decay_score == 0.2  # 2 * 0.1 = 0.2

    def test_concurrent_project_isolation(self, tmp_path):
        """Different projects should have isolated aging data."""
        project1_aging = tmp_path / "project1" / "RULE_AGING.json"
        project2_aging = tmp_path / "project2" / "RULE_AGING.json"
        project1_aging.parent.mkdir(parents=True, exist_ok=True)
        project2_aging.parent.mkdir(parents=True, exist_ok=True)

        def get_aging_file(self):
            if self.project_id == "project1":
                return project1_aging
            return project2_aging

        with patch.object(RuleAgingTracker, "_get_aging_file", get_aging_file):
            tracker1 = RuleAgingTracker("project1")
            tracker2 = RuleAgingTracker("project2")

            tracker1.record_validation_failure("rule1")
            tracker2.record_validation_success("rule1")

            # Verify isolation
            assert tracker1._aging_data["rule1"]["validation_failures"] == 1
            assert tracker2._aging_data["rule1"]["validation_failures"] == 0
