"""Tests for regression guard (IMP-ARCH-008)."""

import tempfile
from pathlib import Path

import pytest

from src.autopack.validation.regression_guard import RegressionGuard, RegressionTest


class TestRegressionGuard:
    """Test suite for RegressionGuard."""

    @pytest.fixture
    def temp_test_storage(self):
        """Create temporary test storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_generate_test(self, temp_test_storage):
        """Test regression test generation."""
        guard = RegressionGuard(test_storage_path=temp_test_storage)

        baseline_metrics = {
            "token_usage": 1_000_000,
            "duration": 3600,
            "error_rate": 0.05,
        }

        test = guard.generate_test(
            improvement_task_id="task-123", baseline_metrics=baseline_metrics, max_degradation=0.05
        )

        assert isinstance(test, RegressionTest)
        assert test.test_id is not None
        assert test.baseline_metrics == baseline_metrics
        assert test.max_degradation == 0.05

        # Test should be saved
        assert len(guard.list_tests()) == 1

    def test_validate_improvement_pass(self, temp_test_storage):
        """Test validation passes when metrics improve."""
        guard = RegressionGuard(test_storage_path=temp_test_storage)

        baseline_metrics = {"token_usage": 1_000_000, "error_rate": 0.05}

        guard.generate_test(improvement_task_id="task-123", baseline_metrics=baseline_metrics)

        # Current metrics are better (lower token usage, lower error rate)
        current_metrics = {"token_usage": 900_000, "error_rate": 0.03}

        passed, violations = guard.validate_improvement("task-123", current_metrics)

        assert passed is True
        assert len(violations) == 0

    def test_validate_improvement_fail_regression(self, temp_test_storage):
        """Test validation fails when regression detected."""
        guard = RegressionGuard(test_storage_path=temp_test_storage)

        baseline_metrics = {"token_usage": 1_000_000, "error_rate": 0.05}

        guard.generate_test(
            improvement_task_id="task-123",
            baseline_metrics=baseline_metrics,
            max_degradation=0.05,  # 5% max
        )

        # Current metrics show >5% regression
        current_metrics = {"token_usage": 1_200_000, "error_rate": 0.12}

        passed, violations = guard.validate_improvement("task-123", current_metrics)

        assert passed is False
        assert len(violations) > 0
        assert "token_usage" in violations[0] or "error_rate" in violations[0]

    def test_auto_rollback_check(self, temp_test_storage):
        """Test automatic rollback detection."""
        guard = RegressionGuard(test_storage_path=temp_test_storage)

        baseline_metrics = {"token_usage": 1_000_000}

        guard.generate_test(improvement_task_id="task-123", baseline_metrics=baseline_metrics)

        # Post-deployment metrics show regression
        post_deployment_metrics = {"token_usage": 1_150_000}

        should_rollback, reason = guard.auto_rollback_check("task-123", post_deployment_metrics)

        assert should_rollback is True
        assert reason is not None
        assert "Regression detected" in reason
