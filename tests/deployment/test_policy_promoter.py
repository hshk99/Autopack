"""Tests for policy promoter (IMP-ARCH-006)."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autopack.deployment.policy_promoter import PolicyPromoter
from autopack.models import ABTestResult, PolicyPromotion


@pytest.fixture
def temp_config_file():
    """Create temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        import json

        json.dump({"max_tokens": 1000000, "timeout": 3600}, f)
        config_path = Path(f.name)

    yield config_path

    # Cleanup
    if config_path.exists():
        config_path.unlink()


class TestPolicyPromoter:
    """Test suite for PolicyPromoter."""

    def test_promote_improvement(self, db_session, temp_config_file):
        """Test promotion of validated improvement."""
        # Create validated A-B test
        ab_test = ABTestResult(
            test_id="test-123",
            control_run_id="run-control",
            treatment_run_id="run-treatment",
            control_commit_sha="abc123",
            treatment_commit_sha="abc123",
            control_model_hash="hash1",
            treatment_model_hash="hash2",
            is_valid=True,
            token_delta=-200000,
            time_delta_seconds=-300,
            control_total_tokens=1000000,
            treatment_total_tokens=800000,
        )
        db_session.add(ab_test)
        db_session.flush()

        # Note: This test is a placeholder showing intended usage
        # For now, just verify the promoter can be instantiated
        promoter = PolicyPromoter(config_path=temp_config_file)
        assert promoter.config_path == temp_config_file

    def test_list_active_promotions(self, db_session, temp_config_file):
        """Test listing active promotions."""
        promoter = PolicyPromoter(config_path=temp_config_file)

        # Initially no active promotions
        active = promoter.list_active_promotions()
        assert len(active) == 0

    def test_mark_promotion_stable(self, db_session, temp_config_file):
        """Test marking promotion as stable."""
        promoter = PolicyPromoter(config_path=temp_config_file)

        # Create a promotion manually
        promotion = PolicyPromotion(
            promotion_id="promo-123",
            ab_test_result_id=1,
            improvement_task_id="task-123",
            config_changes={"key": {"old": "val1", "new": "val2"}},
            promoted_version="v2",
            previous_version="v1",
            status="active",
            monitoring_until=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db_session.add(promotion)
        db_session.commit()

        # Mark as stable
        result = promoter.mark_promotion_stable("promo-123")
        assert result is True

        # Verify status changed
        db_session.refresh(promotion)
        assert promotion.status == "stable"

    def test_get_promotion_history(self, db_session, temp_config_file):
        """Test getting promotion history."""
        promoter = PolicyPromoter(config_path=temp_config_file)

        # Create some promotions
        for i in range(3):
            promotion = PolicyPromotion(
                promotion_id=f"promo-{i}",
                ab_test_result_id=1,
                improvement_task_id=f"task-{i}",
                config_changes={"key": {"old": "val1", "new": "val2"}},
                promoted_version=f"v{i+1}",
                previous_version=f"v{i}",
                status="stable",
            )
            db_session.add(promotion)

        db_session.commit()

        # Get history
        history = promoter.get_promotion_history(limit=2)
        assert len(history) == 2
        assert history[0].promotion_id == "promo-2"  # Most recent first
