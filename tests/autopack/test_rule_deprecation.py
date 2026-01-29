"""Tests for learned rule deprecation system.

IMP-LOOP-034: Tests for rule effectiveness evaluation and automatic deprecation.

Tests cover:
- LearnedRule effectiveness fields (effectiveness_score, last_validated_at, deprecated)
- RuleEffectivenessReport dataclass
- RuleEffectivenessManager methods
- evaluate_rule_effectiveness() function
- deprecate_ineffective_rules() function
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from autopack.learned_rules import (
    DiscoveryStage,
    LearnedRule,
    RuleApplication,
    RuleEffectivenessManager,
    RuleEffectivenessReport,
    deprecate_ineffective_rules,
    evaluate_rule_effectiveness,
)


class TestLearnedRuleEffectivenessFields:
    """Tests for effectiveness fields added to LearnedRule."""

    def test_learned_rule_has_effectiveness_fields(self):
        """LearnedRule should have effectiveness tracking fields."""
        rule = LearnedRule(
            rule_id="test.rule_001",
            task_category="testing",
            scope_pattern="*.py",
            constraint="Always add type hints",
            source_hint_ids=["run_1:phase_1"],
            promotion_count=1,
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_seen=datetime.now(timezone.utc).isoformat(),
            status="active",
            stage=DiscoveryStage.RULE.value,
        )

        # Default values
        assert rule.effectiveness_score == 1.0
        assert rule.last_validated_at is None
        assert rule.deprecated is False

    def test_learned_rule_with_custom_effectiveness_values(self):
        """LearnedRule should accept custom effectiveness values."""
        now = datetime.now(timezone.utc).isoformat()
        rule = LearnedRule(
            rule_id="test.rule_002",
            task_category="testing",
            scope_pattern="*.py",
            constraint="Test constraint",
            source_hint_ids=[],
            promotion_count=1,
            first_seen=now,
            last_seen=now,
            status="active",
            stage=DiscoveryStage.RULE.value,
            effectiveness_score=0.75,
            last_validated_at=now,
            deprecated=True,
        )

        assert rule.effectiveness_score == 0.75
        assert rule.last_validated_at == now
        assert rule.deprecated is True

    def test_learned_rule_from_dict_handles_legacy_rules(self):
        """from_dict should handle legacy rules without effectiveness fields."""
        legacy_data = {
            "rule_id": "legacy.rule",
            "task_category": "testing",
            "scope_pattern": None,
            "constraint": "Legacy rule",
            "source_hint_ids": [],
            "promotion_count": 5,
            "first_seen": "2025-01-01T00:00:00+00:00",
            "last_seen": "2025-01-15T00:00:00+00:00",
            "status": "active",
            "stage": "rule",
        }

        rule = LearnedRule.from_dict(legacy_data)

        # Should use defaults for missing effectiveness fields
        assert rule.effectiveness_score == 1.0
        assert rule.last_validated_at is None
        assert rule.deprecated is False

    def test_learned_rule_to_dict_includes_effectiveness_fields(self):
        """to_dict should include effectiveness tracking fields."""
        now = datetime.now(timezone.utc).isoformat()
        rule = LearnedRule(
            rule_id="test.rule",
            task_category="testing",
            scope_pattern="*.py",
            constraint="Test",
            source_hint_ids=[],
            promotion_count=1,
            first_seen=now,
            last_seen=now,
            status="active",
            stage=DiscoveryStage.RULE.value,
            effectiveness_score=0.85,
            last_validated_at=now,
            deprecated=False,
        )

        data = rule.to_dict()

        assert "effectiveness_score" in data
        assert data["effectiveness_score"] == 0.85
        assert "last_validated_at" in data
        assert data["last_validated_at"] == now
        assert "deprecated" in data
        assert data["deprecated"] is False


class TestRuleEffectivenessReport:
    """Tests for RuleEffectivenessReport dataclass."""

    def test_effectiveness_report_creation(self):
        """RuleEffectivenessReport should store evaluation results."""
        report = RuleEffectivenessReport(
            rule_id="test.rule",
            effectiveness_score=0.8,
            total_applications=10,
            successful_applications=8,
            evaluation_period_days=30,
            recommendation="keep",
        )

        assert report.rule_id == "test.rule"
        assert report.effectiveness_score == 0.8
        assert report.total_applications == 10
        assert report.successful_applications == 8
        assert report.evaluation_period_days == 30
        assert report.recommendation == "keep"

    def test_effectiveness_report_to_dict(self):
        """RuleEffectivenessReport should serialize to dict."""
        report = RuleEffectivenessReport(
            rule_id="test.rule",
            effectiveness_score=0.5,
            total_applications=6,
            successful_applications=3,
            evaluation_period_days=30,
            recommendation="monitor",
        )

        data = report.to_dict()

        assert data["rule_id"] == "test.rule"
        assert data["effectiveness_score"] == 0.5
        assert data["recommendation"] == "monitor"


class TestRuleApplication:
    """Tests for RuleApplication dataclass."""

    def test_rule_application_creation(self):
        """RuleApplication should track individual rule applications."""
        now = datetime.now(timezone.utc).isoformat()
        app = RuleApplication(
            rule_id="test.rule",
            phase_id="phase_001",
            applied_at=now,
            successful=True,
            context={"task_type": "build"},
        )

        assert app.rule_id == "test.rule"
        assert app.phase_id == "phase_001"
        assert app.applied_at == now
        assert app.successful is True
        assert app.context == {"task_type": "build"}

    def test_rule_application_from_dict(self):
        """RuleApplication should deserialize from dict."""
        data = {
            "rule_id": "test.rule",
            "phase_id": "phase_002",
            "applied_at": "2025-01-20T10:00:00+00:00",
            "successful": False,
            "context": None,
        }

        app = RuleApplication.from_dict(data)

        assert app.rule_id == "test.rule"
        assert app.successful is False


class TestRuleEffectivenessManager:
    """Tests for RuleEffectivenessManager class."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create a RuleEffectivenessManager with temp storage."""
        with patch(
            "autopack.learned_rules.RuleEffectivenessManager._get_applications_file"
        ) as mock_path:
            apps_file = temp_dir / "RULE_APPLICATIONS.json"
            mock_path.return_value = apps_file

            manager = RuleEffectivenessManager(project_id="test_project")
            yield manager

    def test_record_application(self, manager):
        """record_application should store rule application."""
        app = manager.record_application(
            rule_id="test.rule",
            phase_id="phase_001",
            successful=True,
        )

        assert app.rule_id == "test.rule"
        assert app.successful is True
        assert len(manager._applications) == 1

    def test_get_recent_applications(self, manager):
        """get_recent_applications should filter by date range."""
        # Add applications at different times
        now = datetime.now(timezone.utc)

        # Recent application
        manager._applications.append(
            RuleApplication(
                rule_id="test.rule",
                phase_id="phase_001",
                applied_at=now.isoformat(),
                successful=True,
            )
        )

        # Old application (beyond 30 days)
        old_date = (now - timedelta(days=45)).isoformat()
        manager._applications.append(
            RuleApplication(
                rule_id="test.rule",
                phase_id="phase_002",
                applied_at=old_date,
                successful=False,
            )
        )

        recent = manager.get_recent_applications("test.rule", days=30)

        assert len(recent) == 1
        assert recent[0].phase_id == "phase_001"

    def test_evaluate_rule_effectiveness_high(self, manager):
        """evaluate_rule_effectiveness should return 'keep' for high effectiveness."""
        now = datetime.now(timezone.utc)

        # Add 10 applications, 8 successful
        for i in range(10):
            manager._applications.append(
                RuleApplication(
                    rule_id="test.rule",
                    phase_id=f"phase_{i}",
                    applied_at=now.isoformat(),
                    successful=i < 8,  # First 8 are successful
                )
            )

        report = manager.evaluate_rule_effectiveness("test.rule", days=30)

        assert report.effectiveness_score == 0.8
        assert report.total_applications == 10
        assert report.successful_applications == 8
        assert report.recommendation == "keep"

    def test_evaluate_rule_effectiveness_medium(self, manager):
        """evaluate_rule_effectiveness should return 'monitor' for medium effectiveness."""
        now = datetime.now(timezone.utc)

        # Add 10 applications, 5 successful (50% success rate)
        for i in range(10):
            manager._applications.append(
                RuleApplication(
                    rule_id="test.rule",
                    phase_id=f"phase_{i}",
                    applied_at=now.isoformat(),
                    successful=i < 5,
                )
            )

        report = manager.evaluate_rule_effectiveness("test.rule", days=30)

        assert report.effectiveness_score == 0.5
        assert report.recommendation == "monitor"

    def test_evaluate_rule_effectiveness_low(self, manager):
        """evaluate_rule_effectiveness should return 'deprecate' for low effectiveness."""
        now = datetime.now(timezone.utc)

        # Add 10 applications, 2 successful (20% success rate)
        for i in range(10):
            manager._applications.append(
                RuleApplication(
                    rule_id="test.rule",
                    phase_id=f"phase_{i}",
                    applied_at=now.isoformat(),
                    successful=i < 2,
                )
            )

        report = manager.evaluate_rule_effectiveness("test.rule", days=30)

        assert report.effectiveness_score == 0.2
        assert report.recommendation == "deprecate"

    def test_evaluate_rule_effectiveness_no_applications(self, manager):
        """evaluate_rule_effectiveness should handle rules with no applications."""
        report = manager.evaluate_rule_effectiveness("unknown.rule", days=30)

        assert report.effectiveness_score == 1.0  # Assume effective
        assert report.total_applications == 0
        assert report.recommendation == "monitor"

    def test_deprecate_ineffective_rules(self, temp_dir):
        """deprecate_ineffective_rules should mark low-effectiveness rules."""
        # Create test rules file
        rules_file = temp_dir / "LEARNED_RULES.json"
        now = datetime.now(timezone.utc).isoformat()

        rules_data = {
            "rules": [
                {
                    "rule_id": "good.rule",
                    "task_category": "testing",
                    "scope_pattern": "*.py",
                    "constraint": "Good rule",
                    "source_hint_ids": [],
                    "promotion_count": 10,
                    "first_seen": now,
                    "last_seen": now,
                    "status": "active",
                    "stage": "rule",
                    "effectiveness_score": 1.0,
                    "last_validated_at": None,
                    "deprecated": False,
                },
                {
                    "rule_id": "bad.rule",
                    "task_category": "testing",
                    "scope_pattern": "*.py",
                    "constraint": "Bad rule",
                    "source_hint_ids": [],
                    "promotion_count": 5,
                    "first_seen": now,
                    "last_seen": now,
                    "status": "active",
                    "stage": "rule",
                    "effectiveness_score": 1.0,
                    "last_validated_at": None,
                    "deprecated": False,
                },
            ]
        }

        rules_file.write_text(json.dumps(rules_data))

        # Create applications file with poor performance for bad.rule
        apps_file = temp_dir / "RULE_APPLICATIONS.json"
        applications = []

        for i in range(5):
            # Good rule - all successful
            applications.append(
                {
                    "rule_id": "good.rule",
                    "phase_id": f"phase_good_{i}",
                    "applied_at": now,
                    "successful": True,
                    "context": None,
                }
            )
            # Bad rule - all failed
            applications.append(
                {
                    "rule_id": "bad.rule",
                    "phase_id": f"phase_bad_{i}",
                    "applied_at": now,
                    "successful": False,
                    "context": None,
                }
            )

        apps_file.write_text(json.dumps({"applications": applications}))

        # Run deprecation
        with patch("autopack.learned_rules._get_project_rules_file") as mock_rules_path:
            mock_rules_path.return_value = rules_file

            with patch(
                "autopack.learned_rules.RuleEffectivenessManager._get_applications_file"
            ) as mock_apps_path:
                mock_apps_path.return_value = apps_file

                manager = RuleEffectivenessManager(project_id="test_project")
                deprecated = manager.deprecate_ineffective_rules(
                    min_effectiveness=0.3,
                    min_applications=3,
                )

        assert "bad.rule" in deprecated
        assert "good.rule" not in deprecated

        # Verify rule was updated
        updated_rules = json.loads(rules_file.read_text())
        bad_rule = next(r for r in updated_rules["rules"] if r["rule_id"] == "bad.rule")
        assert bad_rule["deprecated"] is True
        assert bad_rule["status"] == "deprecated"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_evaluate_rule_effectiveness_function(self):
        """evaluate_rule_effectiveness() should delegate to manager."""
        with patch("autopack.learned_rules.RuleEffectivenessManager") as MockManager:
            mock_manager = Mock()
            mock_manager.evaluate_rule_effectiveness.return_value = RuleEffectivenessReport(
                rule_id="test.rule",
                effectiveness_score=0.9,
                total_applications=10,
                successful_applications=9,
                evaluation_period_days=30,
                recommendation="keep",
            )
            MockManager.return_value = mock_manager

            report = evaluate_rule_effectiveness("test.rule", "test_project", days=30)

            assert report.effectiveness_score == 0.9
            mock_manager.evaluate_rule_effectiveness.assert_called_once_with("test.rule", 30)

    def test_deprecate_ineffective_rules_function(self):
        """deprecate_ineffective_rules() should delegate to manager."""
        with patch("autopack.learned_rules.RuleEffectivenessManager") as MockManager:
            mock_manager = Mock()
            mock_manager.deprecate_ineffective_rules.return_value = ["bad.rule_1", "bad.rule_2"]
            MockManager.return_value = mock_manager

            deprecated = deprecate_ineffective_rules(
                project_id="test_project",
                min_effectiveness=0.3,
                min_applications=3,
                days=30,
            )

            assert len(deprecated) == 2
            mock_manager.deprecate_ineffective_rules.assert_called_once_with(0.3, 3, 30)


class TestIntegrationWithExistingAging:
    """Tests for integration with existing RuleAgingTracker."""

    def test_effectiveness_and_aging_are_independent(self):
        """Effectiveness tracking should work alongside aging tracking."""
        now = datetime.now(timezone.utc).isoformat()

        # Rule with both effectiveness and aging data
        rule = LearnedRule(
            rule_id="combined.rule",
            task_category="testing",
            scope_pattern="*.py",
            constraint="Combined tracking rule",
            source_hint_ids=[],
            promotion_count=5,
            first_seen=now,
            last_seen=now,
            status="active",
            stage=DiscoveryStage.RULE.value,
            effectiveness_score=0.85,
            last_validated_at=now,
            deprecated=False,
        )

        # Both systems should be able to update the rule
        assert rule.effectiveness_score == 0.85
        assert rule.deprecated is False

        # Simulate effectiveness-based deprecation
        rule.effectiveness_score = 0.2
        rule.deprecated = True

        assert rule.deprecated is True
        assert rule.effectiveness_score == 0.2
