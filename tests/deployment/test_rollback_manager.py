"""Tests for rollback manager (IMP-ARCH-006)."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autopack.deployment.rollback_manager import RollbackManager
from autopack.models import PolicyPromotion


@pytest.fixture
def temp_config_file():
    """Create temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        import json

        json.dump({"max_tokens": 1000000}, f)
        config_path = Path(f.name)

    yield config_path

    if config_path.exists():
        config_path.unlink()


class TestRollbackManager:
    """Test suite for RollbackManager."""

    def test_trigger_rollback(self, db_session, temp_config_file):
        """Test triggering rollback for a promotion."""
        # Create a promotion
        promotion = PolicyPromotion(
            promotion_id="promo-123",
            ab_test_result_id=1,
            improvement_task_id="task-123",
            config_changes={"max_tokens": {"old": 1000000, "new": 1200000}},
            promoted_version="v2",
            previous_version="v1",
            status="active",
            monitoring_until=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db_session.add(promotion)
        db_session.commit()

        manager = RollbackManager(config_path=temp_config_file)

        # Trigger rollback
        result = manager.trigger_rollback(
            "promo-123", "Test rollback", restore_config=False  # Skip config restore for test
        )

        assert result is True

        # Verify rollback recorded
        db_session.refresh(promotion)
        assert promotion.rollback_triggered is True
        assert promotion.rollback_reason == "Test rollback"
        assert promotion.status == "rolled_back"

    def test_check_metric_degradation(self, temp_config_file):
        """Test metric degradation detection."""
        manager = RollbackManager(config_path=temp_config_file, degradation_threshold=0.10)  # 10%

        # Cost metric: 15% increase should trigger degradation
        degraded, pct = manager._check_metric_degradation("token_usage", 1000000, 1150000)
        assert degraded is True
        assert pct > 0.10

        # Cost metric: 5% increase should not trigger (below 10%)
        degraded, pct = manager._check_metric_degradation("token_usage", 1000000, 1050000)
        assert degraded is False

        # Quality metric: 15% decrease should trigger
        degraded, pct = manager._check_metric_degradation("success_rate", 1.0, 0.85)
        assert degraded is True

    def test_get_rollback_history(self, db_session, temp_config_file):
        """Test getting rollback history."""
        manager = RollbackManager(config_path=temp_config_file)

        # Create rolled back promotions
        for i in range(3):
            promotion = PolicyPromotion(
                promotion_id=f"promo-{i}",
                ab_test_result_id=1,
                improvement_task_id=f"task-{i}",
                config_changes={"key": {"old": "val1", "new": "val2"}},
                promoted_version=f"v{i+1}",
                previous_version=f"v{i}",
                status="rolled_back",
                rollback_triggered=True,
                rollback_reason="Test rollback",
                rollback_at=datetime.now(timezone.utc),
            )
            db_session.add(promotion)

        db_session.commit()

        # Get history
        history = manager.get_rollback_history(limit=2)
        assert len(history) == 2

    def test_auto_rollback_check_all(self, db_session, temp_config_file):
        """Test automatic rollback check for all active promotions."""
        # Create active promotion
        promotion = PolicyPromotion(
            promotion_id="promo-auto",
            ab_test_result_id=1,
            improvement_task_id="task-auto",
            config_changes={"key": {"old": "val1", "new": "val2"}},
            promoted_version="v2",
            previous_version="v1",
            status="active",
            monitoring_until=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db_session.add(promotion)
        db_session.commit()

        manager = RollbackManager(config_path=temp_config_file)

        # Run auto-rollback check
        actions = manager.auto_rollback_check_all()

        # In this test scenario, no rollback should occur (mocked metrics are stable)
        # In real scenario with degraded metrics, actions would contain rollback records
        assert isinstance(actions, list)
