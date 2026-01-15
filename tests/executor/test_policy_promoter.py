"""Tests for ROAD-F: Policy Promotion"""

import pytest
import tempfile
from pathlib import Path
from src.autopack.executor.policy_promoter import PolicyPromoter


class TestPolicyPromoter:
    """Test policy promotion system."""

    def test_create_promoter(self):
        """Test promoter creation."""
        promoter = PolicyPromoter()
        assert promoter.SUCCESS_THRESHOLD == 0.9

    def test_promote_rule_above_threshold(self):
        """Test promoting rule with sufficient success rate."""
        promoter = PolicyPromoter()

        rule = promoter.promote_rule(
            rule_id="rule-001",
            mitigation="Add timeout wrapper",
            success_rate=0.95,
            applicable_phases=["auth", "database"],
        )

        assert rule is not None
        assert rule.rule_id == "rule-001"
        assert rule.success_rate == 0.95
        assert len(rule.applicable_phases) == 2

    def test_dont_promote_below_threshold(self):
        """Test not promoting rule below threshold."""
        promoter = PolicyPromoter()

        rule = promoter.promote_rule(
            rule_id="rule-002",
            mitigation="Some mitigation",
            success_rate=0.85,
            applicable_phases=["auth"],
        )

        assert rule is None

    def test_save_promoted_rules(self):
        """Test saving promoted rules to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            promoter = PolicyPromoter()

            promoter.promote_rule("rule-001", "Fix timeout", 0.92, ["auth", "db"])
            promoter.promote_rule("rule-002", "Add retry", 0.91, ["api"])

            output_path = Path(tmpdir) / "rules.json"
            promoter.save_promoted_rules(output_path)

            assert output_path.exists()
            import json

            with open(output_path) as f:
                data = json.load(f)
            assert data["count"] == 2
            assert "rule-001" in data["rules"]

    def test_get_rules_for_phase(self):
        """Test retrieving rules for phase."""
        promoter = PolicyPromoter()

        promoter.promote_rule("r1", "Fix A", 0.95, ["auth", "general"])
        promoter.promote_rule("r2", "Fix B", 0.92, ["database"])
        promoter.promote_rule("r3", "Fix C", 0.91, ["auth"])

        auth_rules = promoter.get_rules_for_phase("auth")
        assert len(auth_rules) == 2

        db_rules = promoter.get_rules_for_phase("database")
        assert len(db_rules) == 1

    def test_generate_prevention_prompts(self):
        """Test generating prevention prompts."""
        promoter = PolicyPromoter()

        promoter.promote_rule("r1", "Use connection pool", 0.95, ["database"])
        promoter.promote_rule("r2", "Add exponential backoff", 0.92, ["api"])

        prompts = promoter.generate_prevention_prompts()

        assert "database" in prompts
        assert "api" in prompts
        assert "connection pool" in prompts["database"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
