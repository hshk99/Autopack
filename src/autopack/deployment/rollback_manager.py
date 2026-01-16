"""Rollback manager for automatic policy rollback (IMP-ARCH-006)."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from autopack.database import SessionLocal
from autopack.models import PolicyPromotion
from autopack.telemetry.meta_metrics import MetaMetricsTracker


class RollbackManager:
    """
    Automatic rollback protection for promoted improvements.

    Monitors post-promotion metrics and triggers rollback if:
    - Error rate increases >10%
    - Token usage increases >10%
    - Duration increases >10%
    - Success rate decreases >10%
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        degradation_threshold: float = 0.10,
        meta_metrics_tracker: Optional[MetaMetricsTracker] = None,
    ):
        self.config_path = config_path or Path("config/autopack_config.json")
        self.degradation_threshold = degradation_threshold
        self.meta_metrics_tracker = meta_metrics_tracker

    def monitor_promotion(
        self,
        promotion_id: str,
        metrics_to_watch: Optional[List[str]] = None,
        monitoring_period_hours: int = 24,
    ) -> Tuple[bool, Optional[str]]:
        """
        Monitor a promotion for degradation.

        Args:
            promotion_id: Promotion ID to monitor
            metrics_to_watch: List of metrics to monitor (default: all critical metrics)
            monitoring_period_hours: How long to monitor (hours)

        Returns:
            (should_rollback, reason): True if rollback needed, reason string
        """
        session = SessionLocal()

        try:
            promotion = session.query(PolicyPromotion).filter_by(promotion_id=promotion_id).first()
            if not promotion:
                return False, f"Promotion {promotion_id} not found"

            if promotion.status == "rolled_back":
                return False, "Already rolled back"

            # Get current metrics
            current_metrics = self._get_current_metrics()
            if not current_metrics:
                return False, "No metrics available for comparison"

            # Get baseline metrics from A-B test
            baseline_metrics = self._get_baseline_metrics(promotion.ab_test_result_id)
            if not baseline_metrics:
                return False, "No baseline metrics available"

            # Check for degradation
            metrics_to_check = metrics_to_watch or [
                "token_usage",
                "error_rate",
                "duration",
                "success_rate",
            ]

            degradations = []
            for metric in metrics_to_check:
                if metric not in baseline_metrics or metric not in current_metrics:
                    continue

                baseline = baseline_metrics[metric]
                current = current_metrics[metric]

                degraded, pct_change = self._check_metric_degradation(metric, baseline, current)

                if degraded:
                    degradations.append(
                        f"{metric}: {pct_change*100:.1f}% degradation "
                        f"(baseline={baseline:.2f}, current={current:.2f})"
                    )

            if degradations:
                reason = f"Degradation detected: {'; '.join(degradations)}"
                return True, reason

            return False, None

        finally:
            session.close()

    def trigger_rollback(self, promotion_id: str, reason: str, restore_config: bool = True) -> bool:
        """
        Trigger rollback for a promotion.

        Args:
            promotion_id: Promotion ID to rollback
            reason: Reason for rollback
            restore_config: Whether to restore previous configuration

        Returns:
            True if rollback successful
        """
        session = SessionLocal()

        try:
            promotion = session.query(PolicyPromotion).filter_by(promotion_id=promotion_id).first()
            if not promotion:
                return False

            # Restore previous configuration
            if restore_config:
                self._restore_config(promotion)

            # Update promotion record
            promotion.rollback_triggered = True
            promotion.rollback_reason = reason
            promotion.rollback_at = datetime.now(timezone.utc)
            promotion.status = "rolled_back"

            session.commit()

            return True

        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def auto_rollback_check_all(self) -> List[Dict[str, Any]]:
        """
        Check all active promotions for auto-rollback triggers.

        Returns:
            List of rollback actions taken: [{"promotion_id": ..., "reason": ..., "rolled_back": bool}]
        """
        session = SessionLocal()
        actions = []

        try:
            now = datetime.now(timezone.utc)

            # Get all active promotions in monitoring period
            active_promotions = (
                session.query(PolicyPromotion)
                .filter(
                    PolicyPromotion.status == "active",
                    PolicyPromotion.monitoring_until > now,
                )
                .all()
            )

            for promotion in active_promotions:
                should_rollback, reason = self.monitor_promotion(
                    promotion.promotion_id, monitoring_period_hours=24
                )

                if should_rollback and reason:
                    rolled_back = self.trigger_rollback(promotion.promotion_id, reason)
                    actions.append(
                        {
                            "promotion_id": promotion.promotion_id,
                            "improvement_task_id": promotion.improvement_task_id,
                            "reason": reason,
                            "rolled_back": rolled_back,
                        }
                    )

            return actions

        finally:
            session.close()

    def _check_metric_degradation(
        self, metric: str, baseline: float, current: float
    ) -> Tuple[bool, float]:
        """
        Check if metric has degraded beyond threshold.

        Returns:
            (is_degraded, pct_change)
        """
        if baseline == 0:
            return False, 0.0

        # Cost metrics: higher is worse
        if metric in ["token_usage", "duration", "error_rate"]:
            pct_change = (current - baseline) / baseline
            return pct_change > self.degradation_threshold, pct_change

        # Quality metrics: lower is worse
        elif metric in ["success_rate", "quality_score"]:
            pct_change = (baseline - current) / baseline
            return pct_change > self.degradation_threshold, pct_change

        return False, 0.0

    def _get_current_metrics(self) -> Optional[Dict[str, float]]:
        """Get current system metrics from meta-metrics tracker."""
        if not self.meta_metrics_tracker:
            # Fallback: return mock metrics for testing
            return {
                "token_usage": 1_000_000,
                "error_rate": 0.05,
                "duration": 3600,
                "success_rate": 0.90,
            }

        # Get recent metrics from meta-metrics tracker
        # This would integrate with MetaMetricsTracker.get_recent_summary()
        return self.meta_metrics_tracker.get_recent_summary()

    def _get_baseline_metrics(self, ab_test_result_id: int) -> Optional[Dict[str, float]]:
        """Get baseline metrics from A-B test result."""
        session = SessionLocal()
        try:
            from src.autopack.models import ABTestResult

            ab_test = session.query(ABTestResult).filter_by(id=ab_test_result_id).first()
            if not ab_test or not ab_test.metrics:
                return None

            # Extract control (baseline) metrics
            metrics = ab_test.metrics
            baseline = {}

            for metric_name, values in metrics.items():
                if isinstance(values, dict) and "control" in values:
                    # Format: {"control": [...], "treatment": [...]}
                    import statistics

                    baseline[metric_name] = statistics.mean(values["control"])
                elif isinstance(values, list):
                    # Assume first half is control
                    import statistics

                    mid = len(values) // 2
                    baseline[metric_name] = statistics.mean(values[:mid])

            return baseline if baseline else None

        finally:
            session.close()

    def _restore_config(self, promotion: PolicyPromotion) -> None:
        """Restore configuration to pre-promotion state."""
        # Read current config
        if not self.config_path.exists():
            return

        with open(self.config_path) as f:
            config = json.load(f)

        # Revert config changes
        for key, change in promotion.config_changes.items():
            config[key] = change["old"]

        # Write restored config
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    def get_rollback_history(self, limit: int = 10) -> List[PolicyPromotion]:
        """
        Get recent rollback history.

        Args:
            limit: Number of rollbacks to return

        Returns:
            List of rolled back promotions
        """
        session = SessionLocal()
        try:
            rollbacks = (
                session.query(PolicyPromotion)
                .filter(PolicyPromotion.rollback_triggered == True)  # noqa: E712
                .order_by(PolicyPromotion.rollback_at.desc())
                .limit(limit)
                .all()
            )
            return rollbacks
        finally:
            session.close()
