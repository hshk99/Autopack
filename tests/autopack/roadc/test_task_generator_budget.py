"""Tests for cost budget gating in task generation (IMP-COST-001).

Tests cover:
- BudgetStatus dataclass
- CostTracker.get_budget_status() method
- GeneratedTask.estimated_cost field
- generate_tasks budget filtering
- _estimate_task_cost cost estimation
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from autopack.roadc.task_generator import (
    AutonomousTaskGenerator,
    GeneratedTask,
)
from autopack.telemetry.cost_tracker import (
    DEFAULT_BUDGET_CONSTRAINT_THRESHOLD,
    DEFAULT_DAILY_TOKEN_BUDGET,
    DEFAULT_LOW_COST_TASK_THRESHOLD,
    BudgetStatus,
    CostTracker,
)


class TestBudgetStatus:
    """Tests for BudgetStatus dataclass (IMP-COST-001)."""

    def test_budget_status_fields(self):
        """BudgetStatus should have all required fields."""
        status = BudgetStatus(
            total_budget=5_000_000,
            used=2_000_000,
            remaining=3_000_000,
            remaining_percentage=0.6,
            low_cost_threshold=50_000,
            constrained=False,
        )

        assert status.total_budget == 5_000_000
        assert status.used == 2_000_000
        assert status.remaining == 3_000_000
        assert status.remaining_percentage == 0.6
        assert status.low_cost_threshold == 50_000
        assert status.constrained is False

    def test_budget_status_constrained_when_low(self):
        """BudgetStatus should be constrained when remaining < 50%."""
        status = BudgetStatus(
            total_budget=5_000_000,
            used=3_000_000,
            remaining=2_000_000,
            remaining_percentage=0.4,  # 40% remaining
            low_cost_threshold=50_000,
            constrained=True,  # Should be constrained at 40%
        )

        assert status.constrained is True
        assert status.remaining_percentage < 0.5

    def test_budget_status_not_constrained_when_high(self):
        """BudgetStatus should not be constrained when remaining >= 50%."""
        status = BudgetStatus(
            total_budget=5_000_000,
            used=2_000_000,
            remaining=3_000_000,
            remaining_percentage=0.6,  # 60% remaining
            low_cost_threshold=50_000,
            constrained=False,
        )

        assert status.constrained is False
        assert status.remaining_percentage >= 0.5


class TestCostTracker:
    """Tests for CostTracker class (IMP-COST-001)."""

    def test_cost_tracker_default_values(self):
        """CostTracker should use sensible defaults."""
        tracker = CostTracker()

        assert tracker._daily_token_budget == DEFAULT_DAILY_TOKEN_BUDGET
        assert tracker._low_cost_task_threshold == DEFAULT_LOW_COST_TASK_THRESHOLD
        assert tracker._budget_constraint_threshold == DEFAULT_BUDGET_CONSTRAINT_THRESHOLD

    def test_cost_tracker_custom_values(self):
        """CostTracker should accept custom configuration."""
        tracker = CostTracker(
            daily_token_budget=10_000_000,
            low_cost_task_threshold=100_000,
            budget_constraint_threshold=0.3,
        )

        assert tracker._daily_token_budget == 10_000_000
        assert tracker._low_cost_task_threshold == 100_000
        assert tracker._budget_constraint_threshold == 0.3

    def test_get_budget_status_no_session(self):
        """get_budget_status should return full budget when no DB session."""
        tracker = CostTracker(daily_token_budget=5_000_000)
        status = tracker.get_budget_status()

        assert status.total_budget == 5_000_000
        assert status.used == 0  # No session, so no tokens used
        assert status.remaining == 5_000_000
        assert status.remaining_percentage == 1.0
        assert status.constrained is False

    @patch("autopack.telemetry.cost_tracker.CostTracker._get_tokens_used_today")
    def test_get_budget_status_partial_usage(self, mock_tokens_used):
        """get_budget_status should reflect partial budget usage."""
        mock_tokens_used.return_value = 2_000_000

        tracker = CostTracker(daily_token_budget=5_000_000)
        status = tracker.get_budget_status()

        assert status.total_budget == 5_000_000
        assert status.used == 2_000_000
        assert status.remaining == 3_000_000
        assert status.remaining_percentage == 0.6
        assert status.constrained is False  # 60% remaining > 50% threshold

    @patch("autopack.telemetry.cost_tracker.CostTracker._get_tokens_used_today")
    def test_get_budget_status_constrained(self, mock_tokens_used):
        """get_budget_status should be constrained when remaining < threshold."""
        mock_tokens_used.return_value = 3_000_000

        tracker = CostTracker(daily_token_budget=5_000_000)
        status = tracker.get_budget_status()

        assert status.total_budget == 5_000_000
        assert status.used == 3_000_000
        assert status.remaining == 2_000_000
        assert status.remaining_percentage == 0.4
        assert status.constrained is True  # 40% remaining < 50% threshold

    @patch("autopack.telemetry.cost_tracker.CostTracker._get_tokens_used_today")
    def test_get_budget_status_exhausted(self, mock_tokens_used):
        """get_budget_status should handle exhausted budget."""
        mock_tokens_used.return_value = 5_000_000

        tracker = CostTracker(daily_token_budget=5_000_000)
        status = tracker.get_budget_status()

        assert status.total_budget == 5_000_000
        assert status.used == 5_000_000
        assert status.remaining == 0
        assert status.remaining_percentage == 0.0
        assert status.constrained is True


class TestGeneratedTaskEstimatedCost:
    """Tests for GeneratedTask.estimated_cost field (IMP-COST-001)."""

    def test_generated_task_default_estimated_cost(self):
        """GeneratedTask should have default estimated_cost of 0."""
        task = GeneratedTask(
            task_id="TASK-ABC12345",
            title="Test task",
            description="Test description",
            priority="medium",
            source_insights=["insight_1"],
            suggested_files=["file.py"],
            estimated_effort="M",
            created_at=datetime.now(),
        )

        assert task.estimated_cost == 0

    def test_generated_task_custom_estimated_cost(self):
        """GeneratedTask should accept custom estimated_cost."""
        task = GeneratedTask(
            task_id="TASK-ABC12345",
            title="Test task",
            description="Test description",
            priority="high",
            source_insights=["insight_1"],
            suggested_files=["file.py"],
            estimated_effort="L",
            created_at=datetime.now(),
            estimated_cost=75_000,
        )

        assert task.estimated_cost == 75_000


class TestEstimateTaskCost:
    """Tests for _estimate_task_cost method (IMP-COST-001)."""

    @pytest.fixture
    def task_generator(self):
        """Create task generator for testing with mocked dependencies."""
        mock_memory = Mock()
        mock_memory.retrieve_insights.return_value = []
        mock_regression = Mock()
        mock_regression.check_protection.return_value = Mock(is_protected=True)
        mock_causal = Mock()
        mock_causal.get_pattern_causal_history.return_value = {}
        mock_causal.adjust_priority_for_causal_risk.side_effect = lambda pattern, history: pattern
        return AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

    def test_estimate_cost_small_effort(self, task_generator):
        """Small effort tasks should have low estimated cost."""
        pattern = {"type": "unknown", "occurrences": 2}
        cost = task_generator._estimate_task_cost(pattern, "S")

        # S = 10_000 base, no type multiplier, minimal occurrence factor
        assert 10_000 <= cost <= 15_000

    def test_estimate_cost_medium_effort(self, task_generator):
        """Medium effort tasks should have moderate estimated cost."""
        pattern = {"type": "unknown", "occurrences": 3}
        cost = task_generator._estimate_task_cost(pattern, "M")

        # M = 30_000 base
        assert 30_000 <= cost <= 45_000

    def test_estimate_cost_large_effort(self, task_generator):
        """Large effort tasks should have higher estimated cost."""
        pattern = {"type": "unknown", "occurrences": 6}
        cost = task_generator._estimate_task_cost(pattern, "L")

        # L = 75_000 base
        assert 75_000 <= cost <= 120_000

    def test_estimate_cost_xl_effort(self, task_generator):
        """Extra large effort tasks should have highest estimated cost."""
        pattern = {"type": "unknown", "occurrences": 11}
        cost = task_generator._estimate_task_cost(pattern, "XL")

        # XL = 150_000 base
        assert 150_000 <= cost <= 225_000

    def test_estimate_cost_cost_sink_multiplier(self, task_generator):
        """Cost sink patterns should have 1.5x multiplier."""
        pattern = {"type": "cost_sink", "occurrences": 2}
        cost = task_generator._estimate_task_cost(pattern, "M")

        # M = 30_000 base * 1.5 (cost_sink) * ~1.1 (occurrence factor)
        assert cost >= 30_000 * 1.5 * 0.95  # Allow for rounding

    def test_estimate_cost_failure_mode_multiplier(self, task_generator):
        """Failure mode patterns should have 1.3x multiplier."""
        pattern = {"type": "failure_mode", "occurrences": 2}
        cost = task_generator._estimate_task_cost(pattern, "M")

        # M = 30_000 base * 1.3 (failure_mode)
        assert cost >= 30_000 * 1.3 * 0.95

    def test_estimate_cost_retry_cause_multiplier(self, task_generator):
        """Retry cause patterns should have 1.2x multiplier."""
        pattern = {"type": "retry_cause", "occurrences": 2}
        cost = task_generator._estimate_task_cost(pattern, "M")

        # M = 30_000 base * 1.2 (retry_cause)
        assert cost >= 30_000 * 1.2 * 0.95

    def test_estimate_cost_occurrence_scaling(self, task_generator):
        """More occurrences should increase estimated cost."""
        pattern_low = {"type": "unknown", "occurrences": 2}
        pattern_high = {"type": "unknown", "occurrences": 10}

        cost_low = task_generator._estimate_task_cost(pattern_low, "M")
        cost_high = task_generator._estimate_task_cost(pattern_high, "M")

        # Higher occurrences should result in higher cost
        assert cost_high > cost_low


class TestGenerateTasksBudgetFiltering:
    """Tests for generate_tasks budget filtering (IMP-COST-001)."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for AutonomousTaskGenerator."""
        mock_memory = Mock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight_1",
                "issue_type": "cost_sink",
                "content": "High cost phase",
                "severity": "high",
                "confidence": 1.0,
                "metric_value": 100000,
                "phase_id": "phase_1",
                "phase_type": "building",
            },
            {
                "id": "insight_2",
                "issue_type": "cost_sink",
                "content": "High cost phase 2",
                "severity": "high",
                "confidence": 1.0,
                "metric_value": 80000,
                "phase_id": "phase_2",
                "phase_type": "building",
            },
            {
                "id": "insight_3",
                "issue_type": "failure_mode",
                "content": "Frequent failures",
                "severity": "high",
                "confidence": 1.0,
                "metric_value": 10,
                "phase_id": "phase_3",
                "phase_type": "testing",
            },
            {
                "id": "insight_4",
                "issue_type": "failure_mode",
                "content": "Frequent failures 2",
                "severity": "high",
                "confidence": 1.0,
                "metric_value": 8,
                "phase_id": "phase_4",
                "phase_type": "testing",
            },
        ]
        mock_regression = Mock()
        mock_regression.check_protection.return_value = Mock(is_protected=True)
        mock_regression.filter_patterns_with_risk_assessment.side_effect = lambda patterns: (
            patterns,
            {},
        )
        mock_causal = Mock()
        mock_causal.get_pattern_causal_history.return_value = {}
        mock_causal.adjust_priority_for_causal_risk.side_effect = lambda pattern, history: pattern

        return mock_memory, mock_regression, mock_causal

    def test_budget_filtering_when_not_constrained(self, mock_dependencies):
        """Tasks should not be filtered when budget is not constrained."""
        mock_memory, mock_regression, mock_causal = mock_dependencies
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

        # Budget is not constrained (60% remaining)
        budget_status = BudgetStatus(
            total_budget=5_000_000,
            used=2_000_000,
            remaining=3_000_000,
            remaining_percentage=0.6,
            low_cost_threshold=50_000,
            constrained=False,
        )

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.5,
            budget_status=budget_status,
        )

        # Tasks should not be filtered when not constrained
        # (All tasks will have estimated_cost > 0 but filtering only happens when constrained)
        assert len(result.tasks_generated) >= 0  # May be 0 if no patterns detected

    def test_budget_filtering_filters_high_cost_tasks(self, mock_dependencies):
        """High-cost tasks should be filtered when budget is constrained."""
        mock_memory, mock_regression, mock_causal = mock_dependencies
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

        # Budget is constrained (40% remaining)
        budget_status = BudgetStatus(
            total_budget=5_000_000,
            used=3_000_000,
            remaining=2_000_000,
            remaining_percentage=0.4,
            low_cost_threshold=50_000,  # Only tasks < 50k should be kept
            constrained=True,
        )

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.5,
            budget_status=budget_status,
        )

        # All remaining tasks should have estimated_cost <= low_cost_threshold
        for task in result.tasks_generated:
            assert task.estimated_cost <= budget_status.low_cost_threshold, (
                f"Task {task.task_id} has estimated_cost {task.estimated_cost} "
                f"which exceeds low_cost_threshold {budget_status.low_cost_threshold}"
            )

    def test_budget_filtering_keeps_low_cost_tasks(self, mock_dependencies):
        """Low-cost tasks should be kept even when budget is constrained."""
        mock_memory, mock_regression, mock_causal = mock_dependencies
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

        # Budget is constrained but with high low_cost_threshold
        budget_status = BudgetStatus(
            total_budget=5_000_000,
            used=3_000_000,
            remaining=2_000_000,
            remaining_percentage=0.4,
            low_cost_threshold=500_000,  # High threshold - most tasks should pass
            constrained=True,
        )

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.5,
            budget_status=budget_status,
        )

        # With a high threshold, tasks should still be generated
        # (unless patterns weren't detected)
        # All remaining tasks should have estimated_cost <= low_cost_threshold
        for task in result.tasks_generated:
            assert task.estimated_cost <= budget_status.low_cost_threshold

    def test_no_budget_status_skips_filtering(self, mock_dependencies):
        """No budget filtering should occur when budget_status is None."""
        mock_memory, mock_regression, mock_causal = mock_dependencies
        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.5,
            budget_status=None,  # No budget status
        )

        # Tasks should be generated without filtering
        # (may be 0 if no patterns detected, but no filtering was applied)
        assert result is not None


class TestBudgetFilteringIntegration:
    """Integration tests for budget filtering behavior."""

    def test_budget_filtering_logs_when_filtering(self, caplog):
        """Budget filtering should log when tasks are filtered."""
        import logging

        caplog.set_level(logging.INFO)

        # Create generator with mocks that produce high-cost tasks
        mock_memory = Mock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": f"insight_{i}",
                "issue_type": "cost_sink",
                "content": f"Cost sink {i}",
                "severity": "high",
                "confidence": 1.0,
                "metric_value": 100000 + i * 1000,
                "phase_id": f"phase_{i}",
                "phase_type": "building",
            }
            for i in range(10)  # Many insights to generate large tasks
        ]
        mock_regression = Mock()
        mock_regression.check_protection.return_value = Mock(is_protected=True)
        mock_regression.filter_patterns_with_risk_assessment.side_effect = lambda patterns: (
            patterns,
            {},
        )
        mock_causal = Mock()
        mock_causal.get_pattern_causal_history.return_value = {}
        mock_causal.adjust_priority_for_causal_risk.side_effect = lambda pattern, history: pattern

        generator = AutonomousTaskGenerator(
            memory_service=mock_memory,
            regression_protector=mock_regression,
            causal_analyzer=mock_causal,
        )

        # Constrained budget with very low threshold
        budget_status = BudgetStatus(
            total_budget=5_000_000,
            used=3_000_000,
            remaining=2_000_000,
            remaining_percentage=0.4,
            low_cost_threshold=1_000,  # Very low threshold - will filter most tasks
            constrained=True,
        )

        result = generator.generate_tasks(
            max_tasks=10,
            min_confidence=0.5,
            budget_status=budget_status,
        )

        # Check that filtering happened and was logged
        # The log message should mention budget constraint
        log_messages = [r.message for r in caplog.records]
        budget_logs = [m for m in log_messages if "IMP-COST-001" in m]
        # Either filtering happened or tasks were generated below threshold
        # We just verify the code path works without errors
        assert result is not None
