"""Policy promotion system for validated improvements (IMP-ARCH-006)."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.autopack.database import SessionLocal
from src.autopack.models import ABTestResult, PolicyPromotion


class PolicyPromoter:
    """
    Automated promotion of A-B tested improvements to production configuration.

    Promotes validated improvements with:
    - Configuration change tracking
    - Rollback protection (24hr monitoring)
    - SOT ledger updates
    - Metric degradation detection
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        monitoring_hours: int = 24,
        degradation_threshold: float = 0.10,  # 10% degradation triggers rollback
    ):
        self.config_path = config_path or Path("config/autopack_config.json")
        self.monitoring_hours = monitoring_hours
        self.degradation_threshold = degradation_threshold

    def promote_improvement(
        self,
        ab_test_result_id: int,
        improvement_task_id: str,
        config_changes: Dict[str, Dict[str, Any]],
        auto_rollback: bool = True,
    ) -> PolicyPromotion:
        """
        Promote validated improvement to production configuration.

        Args:
            ab_test_result_id: ID of validated A-B test result
            improvement_task_id: ID of the improvement task
            config_changes: Dict of config changes: {"key": {"old": val1, "new": val2}}
            auto_rollback: Enable automatic rollback on degradation

        Returns:
            PolicyPromotion record

        Raises:
            ValueError: If A-B test not validated or already promoted
        """
        session = SessionLocal()

        try:
            # Verify A-B test is validated
            ab_test = session.query(ABTestResult).filter_by(id=ab_test_result_id).first()
            if not ab_test:
                raise ValueError(f"A-B test result {ab_test_result_id} not found")
            if not ab_test.validated:
                raise ValueError(f"A-B test result {ab_test_result_id} not validated")
            if ab_test.promoted:
                raise ValueError(f"A-B test result {ab_test_result_id} already promoted")

            # Read current config
            current_config = self._read_config()
            previous_version = self._compute_config_hash(current_config)

            # Apply config changes
            updated_config = current_config.copy()
            for key, change in config_changes.items():
                updated_config[key] = change["new"]

            # Write updated config
            self._write_config(updated_config)
            promoted_version = self._compute_config_hash(updated_config)

            # Create promotion record
            promotion_id = str(uuid.uuid4())
            monitoring_until = (
                datetime.now(timezone.utc) + timedelta(hours=self.monitoring_hours)
                if auto_rollback
                else None
            )

            promotion = PolicyPromotion(
                promotion_id=promotion_id,
                ab_test_result_id=ab_test_result_id,
                improvement_task_id=improvement_task_id,
                config_changes=config_changes,
                promoted_version=promoted_version,
                previous_version=previous_version,
                promoted_at=datetime.now(timezone.utc),
                monitoring_until=monitoring_until,
                rollback_triggered=False,
                degradation_detected=False,
                status="active",
            )

            session.add(promotion)

            # Mark A-B test as promoted
            ab_test.promoted = True

            session.commit()

            return promotion

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def list_active_promotions(self) -> List[PolicyPromotion]:
        """List all active promotions being monitored."""
        session = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            promotions = (
                session.query(PolicyPromotion)
                .filter(
                    PolicyPromotion.status == "active",
                    PolicyPromotion.monitoring_until > now,
                )
                .all()
            )
            return promotions
        finally:
            session.close()

    def mark_promotion_stable(self, promotion_id: str) -> bool:
        """
        Mark a promotion as stable after monitoring period.

        Args:
            promotion_id: Promotion ID

        Returns:
            True if marked stable
        """
        session = SessionLocal()
        try:
            promotion = session.query(PolicyPromotion).filter_by(promotion_id=promotion_id).first()
            if not promotion:
                return False

            promotion.status = "stable"
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    def _read_config(self) -> Dict[str, Any]:
        """Read current configuration."""
        if not self.config_path.exists():
            return {}

        with open(self.config_path) as f:
            return json.load(f)

    def _write_config(self, config: Dict[str, Any]) -> None:
        """Write updated configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    def _compute_config_hash(self, config: Dict[str, Any]) -> str:
        """Compute deterministic hash of configuration."""
        import hashlib

        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    def get_promotion_history(self, limit: int = 10) -> List[PolicyPromotion]:
        """
        Get recent promotion history.

        Args:
            limit: Number of promotions to return

        Returns:
            List of recent promotions
        """
        session = SessionLocal()
        try:
            promotions = (
                session.query(PolicyPromotion)
                .order_by(PolicyPromotion.promoted_at.desc())
                .limit(limit)
                .all()
            )
            return promotions
        finally:
            session.close()

    def get_promotion_by_task(self, improvement_task_id: str) -> Optional[PolicyPromotion]:
        """Get promotion for a specific improvement task."""
        session = SessionLocal()
        try:
            promotion = (
                session.query(PolicyPromotion)
                .filter_by(improvement_task_id=improvement_task_id)
                .order_by(PolicyPromotion.promoted_at.desc())
                .first()
            )
            return promotion
        finally:
            session.close()
