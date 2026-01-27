"""Regression guard for autonomous improvement protection (IMP-ARCH-008)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.autopack.telemetry.meta_metrics import MetaMetricsTracker


class RegressionTest:
    """A regression test case for validating improvements."""

    def __init__(
        self,
        test_id: str,
        test_name: str,
        baseline_metrics: Dict[str, float],
        max_degradation: float = 0.05,  # 5%
        critical_metrics: Optional[List[str]] = None,
    ):
        self.test_id = test_id
        self.test_name = test_name
        self.baseline_metrics = baseline_metrics
        self.max_degradation = max_degradation
        self.critical_metrics = critical_metrics or ["token_usage", "error_rate", "duration"]
        self.created_at = datetime.now(timezone.utc)

    def validate(self, current_metrics: Dict[str, float]) -> tuple[bool, List[str]]:
        """
        Validate current metrics against baseline.

        Returns:
            (passed, violations): True if no regression detected, list of violation messages
        """
        violations = []

        for metric in self.critical_metrics:
            if metric not in self.baseline_metrics or metric not in current_metrics:
                continue

            baseline = self.baseline_metrics[metric]
            current = current_metrics[metric]

            # For cost/error metrics: current should be ≤ baseline (lower is better)
            # For quality metrics: current should be ≥ baseline (higher is better)
            if metric in ["token_usage", "duration", "error_rate", "retry_count"]:
                # Lower is better
                if baseline > 0:
                    pct_change = (current - baseline) / baseline
                    if pct_change > self.max_degradation:
                        violations.append(
                            f"{metric}: {pct_change * 100:.1f}% increase "
                            f"(baseline={baseline:.2f}, current={current:.2f})"
                        )
            elif metric in ["success_rate", "quality_score"]:
                # Higher is better
                if baseline > 0:
                    pct_change = (baseline - current) / baseline
                    if pct_change > self.max_degradation:
                        violations.append(
                            f"{metric}: {pct_change * 100:.1f}% decrease "
                            f"(baseline={baseline:.2f}, current={current:.2f})"
                        )

        return len(violations) == 0, violations


class RegressionGuard:
    """
    Regression protection for autonomous improvements.

    Generates and validates regression tests to ensure improvements
    don't degrade system performance on critical metrics.
    """

    def __init__(
        self,
        test_storage_path: Optional[Path] = None,
        meta_metrics_tracker: Optional[MetaMetricsTracker] = None,
    ):
        self.test_storage_path = test_storage_path or Path("tests/regression")
        self.test_storage_path.mkdir(parents=True, exist_ok=True)
        self.meta_metrics_tracker = meta_metrics_tracker
        self._test_registry: Dict[str, RegressionTest] = {}
        self._load_tests()

    def generate_test(
        self,
        improvement_task_id: str,
        baseline_metrics: Dict[str, float],
        max_degradation: float = 0.05,
    ) -> RegressionTest:
        """
        Generate a regression test for an improvement.

        Args:
            improvement_task_id: ID of the improvement task
            baseline_metrics: Current baseline metrics to protect
            max_degradation: Maximum allowed degradation percentage (default 5%)

        Returns:
            RegressionTest instance
        """
        test_id = self._generate_test_id(improvement_task_id)
        test_name = f"regression_test_{improvement_task_id}"

        test = RegressionTest(
            test_id=test_id,
            test_name=test_name,
            baseline_metrics=baseline_metrics,
            max_degradation=max_degradation,
        )

        # Save test
        self._save_test(test)
        self._test_registry[test_id] = test

        return test

    def validate_improvement(
        self, improvement_task_id: str, current_metrics: Dict[str, float]
    ) -> tuple[bool, List[str]]:
        """
        Validate an improvement against its regression test.

        Args:
            improvement_task_id: ID of the improvement task
            current_metrics: Current metrics after improvement

        Returns:
            (passed, violations): True if no regression, list of violations
        """
        test_id = self._generate_test_id(improvement_task_id)

        if test_id not in self._test_registry:
            # No test exists - allow by default but log warning
            return True, [f"Warning: No regression test found for {improvement_task_id}"]

        test = self._test_registry[test_id]
        passed, violations = test.validate(current_metrics)

        # Track regression detection in meta-metrics
        if self.meta_metrics_tracker and not passed:
            self.meta_metrics_tracker.track_validation_failure(
                task_id=improvement_task_id, reason="regression_detected", details=violations
            )

        return passed, violations

    def get_critical_baselines(
        self, project_id: Optional[str] = None, lookback_days: int = 7
    ) -> Dict[str, float]:
        """
        Get current baseline metrics for critical KPIs.

        Used to establish regression test baselines before improvement.

        Args:
            project_id: Optional project scope
            lookback_days: Number of days to look back for baseline

        Returns:
            Dict of metric baselines
        """
        # If meta_metrics_tracker available, use it to compute baselines
        if self.meta_metrics_tracker:
            return self._compute_baselines_from_meta_metrics(project_id, lookback_days)

        # Otherwise return conservative defaults
        return {
            "token_usage": 1_000_000,  # 1M tokens per run
            "duration": 3600,  # 1 hour
            "error_rate": 0.05,  # 5% error rate
            "success_rate": 0.90,  # 90% success rate
        }

    def _compute_baselines_from_meta_metrics(
        self, project_id: Optional[str], lookback_days: int
    ) -> Dict[str, float]:
        """Compute baselines from historical meta-metrics."""
        # Placeholder - would integrate with MetaMetricsTracker
        # to compute percentile baselines from historical data
        return {
            "token_usage": 1_000_000,
            "duration": 3600,
            "error_rate": 0.05,
            "success_rate": 0.90,
        }

    def _generate_test_id(self, improvement_task_id: str) -> str:
        """Generate deterministic test ID from task ID."""
        return hashlib.sha256(improvement_task_id.encode()).hexdigest()[:16]

    def _save_test(self, test: RegressionTest) -> None:
        """Save regression test to storage."""
        test_file = self.test_storage_path / f"{test.test_id}.json"

        test_data = {
            "test_id": test.test_id,
            "test_name": test.test_name,
            "baseline_metrics": test.baseline_metrics,
            "max_degradation": test.max_degradation,
            "critical_metrics": test.critical_metrics,
            "created_at": test.created_at.isoformat(),
        }

        with open(test_file, "w") as f:
            json.dump(test_data, f, indent=2)

    def _load_tests(self) -> None:
        """Load all regression tests from storage."""
        if not self.test_storage_path.exists():
            return

        for test_file in self.test_storage_path.glob("*.json"):
            try:
                with open(test_file) as f:
                    data = json.load(f)

                test = RegressionTest(
                    test_id=data["test_id"],
                    test_name=data["test_name"],
                    baseline_metrics=data["baseline_metrics"],
                    max_degradation=data.get("max_degradation", 0.05),
                    critical_metrics=data.get("critical_metrics"),
                )
                test.created_at = datetime.fromisoformat(data["created_at"])

                self._test_registry[test.test_id] = test
            except Exception:
                # Skip invalid test files
                pass

    def list_tests(self) -> List[RegressionTest]:
        """List all registered regression tests."""
        return list(self._test_registry.values())

    def delete_test(self, test_id: str) -> bool:
        """Delete a regression test."""
        if test_id not in self._test_registry:
            return False

        # Remove from registry
        del self._test_registry[test_id]

        # Remove from storage
        test_file = self.test_storage_path / f"{test_id}.json"
        if test_file.exists():
            test_file.unlink()

        return True

    def auto_rollback_check(
        self, improvement_task_id: str, post_deployment_metrics: Dict[str, float]
    ) -> tuple[bool, Optional[str]]:
        """
        Check if automatic rollback should be triggered.

        Args:
            improvement_task_id: ID of deployed improvement
            post_deployment_metrics: Metrics after deployment

        Returns:
            (should_rollback, reason): True if rollback needed, reason string
        """
        passed, violations = self.validate_improvement(improvement_task_id, post_deployment_metrics)

        if not passed:
            reason = f"Regression detected: {'; '.join(violations)}"
            return True, reason

        return False, None
