"""Tests for TaskEffectivenessTracker in autopack.task_generation module."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from autopack.task_generation.task_effectiveness_tracker import (
    CORRECTIVE_TASK_FAILURE_THRESHOLD,
    EXCELLENT_EFFECTIVENESS,
    GOOD_EFFECTIVENESS,
    POOR_EFFECTIVENESS,
    CorrectiveTask,
    EffectivenessHistory,
    TaskEffectivenessTracker,
    TaskImpactReport,
)


class TestTaskImpactReport:
    """Tests for TaskImpactReport dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic TaskImpactReport."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
        )
        assert report.task_id == "IMP-TEST-001"
        assert report.effectiveness_score == 1.0

    def test_is_effective_true(self) -> None:
        """Test is_effective returns True for good effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.4,
            effectiveness_score=GOOD_EFFECTIVENESS,
            measured_at=datetime.now(),
        )
        assert report.is_effective() is True

    def test_is_effective_false(self) -> None:
        """Test is_effective returns False for poor effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.1,
            effectiveness_score=POOR_EFFECTIVENESS - 0.1,
            measured_at=datetime.now(),
        )
        assert report.is_effective() is False

    def test_get_effectiveness_grade_excellent(self) -> None:
        """Test excellent grade for high effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=EXCELLENT_EFFECTIVENESS,
            measured_at=datetime.now(),
        )
        assert report.get_effectiveness_grade() == "excellent"

    def test_get_effectiveness_grade_good(self) -> None:
        """Test good grade for moderate-high effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.4,
            effectiveness_score=0.8,
            measured_at=datetime.now(),
        )
        assert report.get_effectiveness_grade() == "good"

    def test_get_effectiveness_grade_moderate(self) -> None:
        """Test moderate grade for mid-range effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.25,
            effectiveness_score=0.5,
            measured_at=datetime.now(),
        )
        assert report.get_effectiveness_grade() == "moderate"

    def test_get_effectiveness_grade_poor(self) -> None:
        """Test poor grade for low effectiveness."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.05,
            effectiveness_score=0.1,
            measured_at=datetime.now(),
        )
        assert report.get_effectiveness_grade() == "poor"

    def test_optional_fields(self) -> None:
        """Test optional category and notes fields."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
            category="telemetry",
            notes="Test measurement",
        )
        assert report.category == "telemetry"
        assert report.notes == "Test measurement"


class TestEffectivenessHistory:
    """Tests for EffectivenessHistory dataclass."""

    def test_empty_history(self) -> None:
        """Test empty history initialization."""
        history = EffectivenessHistory()
        assert len(history.reports) == 0
        assert len(history.category_stats) == 0

    def test_add_report(self) -> None:
        """Test adding a report to history."""
        history = EffectivenessHistory()
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
            category="telemetry",
        )
        history.add_report(report)

        assert len(history.reports) == 1
        assert "telemetry" in history.category_stats

    def test_category_stats_aggregation(self) -> None:
        """Test category statistics are correctly aggregated."""
        history = EffectivenessHistory()

        report1 = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=0.8,
            measured_at=datetime.now(),
            category="telemetry",
        )
        report2 = TaskImpactReport(
            task_id="IMP-TEST-002",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.3,
            effectiveness_score=0.6,
            measured_at=datetime.now(),
            category="telemetry",
        )

        history.add_report(report1)
        history.add_report(report2)

        stats = history.category_stats["telemetry"]
        assert stats["total_tasks"] == 2
        assert stats["avg_effectiveness"] == pytest.approx(0.7)
        assert stats["effective_count"] == 1  # Only first is effective (0.8 >= 0.7)

    def test_get_category_effectiveness(self) -> None:
        """Test getting effectiveness for a category."""
        history = EffectivenessHistory()
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.4,
            effectiveness_score=0.8,
            measured_at=datetime.now(),
            category="memory",
        )
        history.add_report(report)

        assert history.get_category_effectiveness("memory") == 0.8
        assert history.get_category_effectiveness("unknown") == 0.5  # Default

    def test_general_category_fallback(self) -> None:
        """Test empty category falls back to general."""
        history = EffectivenessHistory()
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
            category="",
        )
        history.add_report(report)

        assert "general" in history.category_stats


class TestTaskEffectivenessTracker:
    """Tests for TaskEffectivenessTracker class."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker without priority engine."""
        return TaskEffectivenessTracker()

    @pytest.fixture
    def tracker_with_engine(self) -> TaskEffectivenessTracker:
        """Create a tracker with mock priority engine."""
        mock_engine = MagicMock()
        return TaskEffectivenessTracker(priority_engine=mock_engine)

    def test_init_without_engine(self) -> None:
        """Test tracker initializes without priority engine."""
        tracker = TaskEffectivenessTracker()
        assert tracker.priority_engine is None
        assert len(tracker.history.reports) == 0

    def test_init_with_engine(self) -> None:
        """Test tracker initializes with priority engine."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)
        assert tracker.priority_engine is mock_engine


class TestMeasureImpact:
    """Tests for measure_impact method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_basic_measurement(self, tracker: TaskEffectivenessTracker) -> None:
        """Test basic impact measurement."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )

        assert report.task_id == "IMP-TEST-001"
        assert report.target_improvement == 0.5
        # 50% reduction in error_rate: (0.2 - 0.1) / 0.2 = 0.5
        assert report.actual_improvement == pytest.approx(0.5)
        # Effectiveness: 0.5 / 0.5 = 1.0
        assert report.effectiveness_score == pytest.approx(1.0)

    def test_partial_improvement(self, tracker: TaskEffectivenessTracker) -> None:
        """Test partial improvement calculation."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target=0.5,
        )

        # 25% reduction: (0.2 - 0.15) / 0.2 = 0.25
        assert report.actual_improvement == pytest.approx(0.25)
        # Effectiveness: 0.25 / 0.5 = 0.5
        assert report.effectiveness_score == pytest.approx(0.5)

    def test_exceeded_target(self, tracker: TaskEffectivenessTracker) -> None:
        """Test effectiveness is capped at 1.0 when target exceeded."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
        )

        # 90% reduction: (0.2 - 0.02) / 0.2 = 0.9
        assert report.actual_improvement == pytest.approx(0.9)
        # Effectiveness capped at 1.0
        assert report.effectiveness_score == 1.0

    def test_higher_is_better_metric(self, tracker: TaskEffectivenessTracker) -> None:
        """Test metrics where higher values are better."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"success_rate": 0.6},
            after_metrics={"success_rate": 0.9},
            target=0.5,
        )

        # 50% increase: (0.9 - 0.6) / 0.6 = 0.5
        assert report.actual_improvement == pytest.approx(0.5)
        assert report.effectiveness_score == pytest.approx(1.0)

    def test_multiple_metrics(self, tracker: TaskEffectivenessTracker) -> None:
        """Test averaging across multiple metrics."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2, "latency": 100.0},
            after_metrics={"error_rate": 0.1, "latency": 80.0},
            target=0.3,
        )

        # error_rate: (0.2 - 0.1) / 0.2 = 0.5
        # latency: (100 - 80) / 100 = 0.2
        # average: (0.5 + 0.2) / 2 = 0.35
        assert report.actual_improvement == pytest.approx(0.35)

    def test_with_category(self, tracker: TaskEffectivenessTracker) -> None:
        """Test measurement with category."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
            category="telemetry",
        )

        assert report.category == "telemetry"
        assert "telemetry" in tracker.history.category_stats

    def test_with_notes(self, tracker: TaskEffectivenessTracker) -> None:
        """Test measurement with notes."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
            notes="Measured after 24-hour deployment",
        )

        assert report.notes == "Measured after 24-hour deployment"

    def test_report_stored_in_history(self, tracker: TaskEffectivenessTracker) -> None:
        """Test report is stored in history."""
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )

        assert len(tracker.history.reports) == 1
        assert tracker.history.reports[0].task_id == "IMP-TEST-001"

    def test_invalid_target_zero(self, tracker: TaskEffectivenessTracker) -> None:
        """Test error on zero target."""
        with pytest.raises(ValueError, match="Target improvement must be positive"):
            tracker.measure_impact(
                task_id="IMP-TEST-001",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.1},
                target=0,
            )

    def test_invalid_target_negative(self, tracker: TaskEffectivenessTracker) -> None:
        """Test error on negative target."""
        with pytest.raises(ValueError, match="Target improvement must be positive"):
            tracker.measure_impact(
                task_id="IMP-TEST-001",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.1},
                target=-0.1,
            )

    def test_no_common_keys(self, tracker: TaskEffectivenessTracker) -> None:
        """Test error when no common keys between before/after."""
        with pytest.raises(ValueError, match="must have common keys"):
            tracker.measure_impact(
                task_id="IMP-TEST-001",
                before_metrics={"error_rate": 0.2},
                after_metrics={"latency": 100.0},
                target=0.5,
            )

    def test_no_improvement(self, tracker: TaskEffectivenessTracker) -> None:
        """Test measurement when there's no improvement."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.2},
            target=0.5,
        )

        assert report.actual_improvement == pytest.approx(0.0)
        assert report.effectiveness_score == pytest.approx(0.0)

    def test_negative_improvement(self, tracker: TaskEffectivenessTracker) -> None:
        """Test measurement when metrics got worse."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.3},
            target=0.5,
        )

        # Got worse by 50%: (0.2 - 0.3) / 0.2 = -0.5
        assert report.actual_improvement == pytest.approx(-0.5)
        # Effectiveness is 0 since we didn't improve
        assert report.effectiveness_score == pytest.approx(0.0)


class TestFeedBackToPriorityEngine:
    """Tests for feed_back_to_priority_engine method."""

    def test_feedback_without_engine(self) -> None:
        """Test feedback is no-op without engine."""
        tracker = TaskEffectivenessTracker()
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
        )

        # Should not raise
        tracker.feed_back_to_priority_engine(report)

    def test_feedback_clears_cache(self) -> None:
        """Test feedback clears priority engine cache."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
            category="telemetry",
        )

        tracker.feed_back_to_priority_engine(report)

        mock_engine.clear_cache.assert_called_once()

    def test_feedback_for_excellent_grade(self) -> None:
        """Test feedback for excellent effectiveness."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=EXCELLENT_EFFECTIVENESS,
            measured_at=datetime.now(),
        )

        tracker.feed_back_to_priority_engine(report)
        mock_engine.clear_cache.assert_called_once()

    def test_feedback_for_poor_grade(self) -> None:
        """Test feedback for poor effectiveness."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.05,
            effectiveness_score=0.1,
            measured_at=datetime.now(),
        )

        tracker.feed_back_to_priority_engine(report)
        mock_engine.clear_cache.assert_called_once()


class TestGetEffectiveness:
    """Tests for get_effectiveness method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_get_existing_task(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting effectiveness for existing task."""
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )

        effectiveness = tracker.get_effectiveness("IMP-TEST-001")
        assert effectiveness == pytest.approx(1.0)

    def test_get_nonexistent_task(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting effectiveness for non-existent task returns default."""
        effectiveness = tracker.get_effectiveness("IMP-NONEXISTENT")
        assert effectiveness == 0.5

    def test_get_multiple_tasks(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting effectiveness for multiple tasks."""
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )
        tracker.measure_impact(
            task_id="IMP-TEST-002",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target=0.5,
        )

        assert tracker.get_effectiveness("IMP-TEST-001") == pytest.approx(1.0)
        assert tracker.get_effectiveness("IMP-TEST-002") == pytest.approx(0.5)


class TestGetCategoryEffectiveness:
    """Tests for get_category_effectiveness method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_existing_category(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting effectiveness for existing category."""
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
            category="telemetry",
        )

        effectiveness = tracker.get_category_effectiveness("telemetry")
        assert effectiveness == pytest.approx(1.0)

    def test_nonexistent_category(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting effectiveness for non-existent category returns default."""
        effectiveness = tracker.get_category_effectiveness("unknown")
        assert effectiveness == 0.5


class TestGetSummary:
    """Tests for get_summary method."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_empty_summary(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary with no reports."""
        summary = tracker.get_summary()

        assert summary["total_tasks"] == 0
        assert summary["avg_effectiveness"] == 0.0
        assert summary["by_category"] == {}
        assert summary["effective_task_rate"] == 0.0
        assert summary["grade_distribution"] == {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }

    def test_summary_with_reports(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary with multiple reports."""
        # Add excellent task
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
            category="telemetry",
        )
        # Add moderate task
        tracker.measure_impact(
            task_id="IMP-TEST-002",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target=0.5,
            category="memory",
        )

        summary = tracker.get_summary()

        assert summary["total_tasks"] == 2
        assert "telemetry" in summary["by_category"]
        assert "memory" in summary["by_category"]
        assert summary["grade_distribution"]["excellent"] == 1
        assert summary["grade_distribution"]["moderate"] == 1

    def test_effective_task_rate(self, tracker: TaskEffectivenessTracker) -> None:
        """Test effective task rate calculation."""
        # Add effective task (effectiveness >= 0.7)
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )
        # Add ineffective task
        tracker.measure_impact(
            task_id="IMP-TEST-002",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.18},
            target=0.5,
        )

        summary = tracker.get_summary()

        # 1 effective out of 2 = 0.5
        assert summary["effective_task_rate"] == 0.5


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_zero_before_value(self, tracker: TaskEffectivenessTracker) -> None:
        """Test handling when before value is zero."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.0},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )

        # When before is 0 and after is positive, consider it a change
        assert report is not None

    def test_very_small_values(self, tracker: TaskEffectivenessTracker) -> None:
        """Test handling of very small metric values."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.0001},
            after_metrics={"error_rate": 0.00005},
            target=0.5,
        )

        assert report.actual_improvement == pytest.approx(0.5)
        assert report.effectiveness_score == pytest.approx(1.0)

    def test_empty_metrics_common_keys(self, tracker: TaskEffectivenessTracker) -> None:
        """Test error when metrics are empty."""
        with pytest.raises(ValueError, match="must have common keys"):
            tracker.measure_impact(
                task_id="IMP-TEST-001",
                before_metrics={},
                after_metrics={},
                target=0.5,
            )

    def test_mixed_metric_directions(self, tracker: TaskEffectivenessTracker) -> None:
        """Test metrics with different improvement directions."""
        report = tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2, "success_rate": 0.8},
            after_metrics={"error_rate": 0.1, "success_rate": 0.9},
            target=0.25,
        )

        # error_rate (lower better): (0.2 - 0.1) / 0.2 = 0.5
        # success_rate (higher better): (0.9 - 0.8) / 0.8 = 0.125
        # average: (0.5 + 0.125) / 2 = 0.3125
        assert report.actual_improvement == pytest.approx(0.3125)


class TestRecordTaskOutcome:
    """Tests for record_task_outcome method (IMP-FBK-001)."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_successful_task_basic(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording a successful task outcome."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=5000,
        )

        assert report.task_id == "phase-123"
        # Success with fast execution and low tokens: 0.8 + 0.1 + 0.1 = 1.0
        assert report.effectiveness_score == pytest.approx(1.0)
        assert report.get_effectiveness_grade() == "excellent"

    def test_successful_task_slow_execution(self, tracker: TaskEffectivenessTracker) -> None:
        """Test successful task with slow execution gets lower effectiveness."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=120.0,  # Slow (> 60s)
            tokens_used=5000,  # Low tokens
        )

        # Success with slow execution but low tokens: 0.8 + 0.0 + 0.1 = 0.9
        assert report.effectiveness_score == pytest.approx(0.9)
        assert report.get_effectiveness_grade() == "excellent"

    def test_successful_task_high_tokens(self, tracker: TaskEffectivenessTracker) -> None:
        """Test successful task with high token usage gets lower effectiveness."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=30.0,  # Fast
            tokens_used=15000,  # High tokens (> 10000)
        )

        # Success with fast execution but high tokens: 0.8 + 0.1 + 0.0 = 0.9
        assert report.effectiveness_score == pytest.approx(0.9)

    def test_successful_task_slow_and_high_tokens(self, tracker: TaskEffectivenessTracker) -> None:
        """Test successful task with slow execution and high tokens."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=120.0,  # Slow
            tokens_used=15000,  # High tokens
        )

        # Success with no bonuses: 0.8 + 0.0 + 0.0 = 0.8
        assert report.effectiveness_score == pytest.approx(0.8)
        assert report.get_effectiveness_grade() == "good"

    def test_failed_task(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording a failed task outcome."""
        report = tracker.record_task_outcome(
            task_id="phase-456",
            success=False,
            execution_time_seconds=10.0,
            tokens_used=1000,
        )

        assert report.task_id == "phase-456"
        assert report.effectiveness_score == pytest.approx(0.0)
        assert report.get_effectiveness_grade() == "poor"

    def test_with_category(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording task outcome with category."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            category="build",
        )

        assert report.category == "build"
        assert "build" in tracker.history.category_stats

    def test_with_notes(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording task outcome with custom notes."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            notes="Custom test notes",
        )

        assert report.notes == "Custom test notes"

    def test_default_notes_format(self, tracker: TaskEffectivenessTracker) -> None:
        """Test default notes include execution metrics."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=45.5,
            tokens_used=7500,
        )

        assert "execution_time=45.5s" in report.notes
        assert "tokens=7500" in report.notes

    def test_report_stored_in_history(self, tracker: TaskEffectivenessTracker) -> None:
        """Test report is stored in history."""
        tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
        )

        assert len(tracker.history.reports) == 1
        assert tracker.history.reports[0].task_id == "phase-123"

    def test_multiple_outcomes(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording multiple task outcomes."""
        tracker.record_task_outcome(task_id="phase-1", success=True)
        tracker.record_task_outcome(task_id="phase-2", success=False)
        tracker.record_task_outcome(task_id="phase-3", success=True)

        assert len(tracker.history.reports) == 3

        summary = tracker.get_summary()
        assert summary["total_tasks"] == 3
        # 2 effective (successful with base 0.8), 1 ineffective (failed with 0.0)
        assert summary["effective_task_rate"] == pytest.approx(2 / 3)

    def test_feed_back_to_priority_engine(self) -> None:
        """Test that record_task_outcome works with priority engine feedback."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            category="test",
        )

        # Feed back manually (record_task_outcome doesn't auto-feed)
        tracker.feed_back_to_priority_engine(report)
        mock_engine.clear_cache.assert_called_once()

    def test_zero_execution_time(self, tracker: TaskEffectivenessTracker) -> None:
        """Test handling of zero execution time."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=0.0,
            tokens_used=5000,
        )

        # Zero execution time doesn't get fast bonus (0.8 + 0.0 + 0.1 = 0.9)
        assert report.effectiveness_score == pytest.approx(0.9)

    def test_zero_tokens(self, tracker: TaskEffectivenessTracker) -> None:
        """Test handling of zero tokens."""
        report = tracker.record_task_outcome(
            task_id="phase-123",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=0,
        )

        # Zero tokens doesn't get low token bonus (0.8 + 0.1 + 0.0 = 0.9)
        assert report.effectiveness_score == pytest.approx(0.9)


class TestOnTaskComplete:
    """Tests for on_task_complete method (IMP-LOOP-021)."""

    def test_on_task_complete_without_engine(self) -> None:
        """Test on_task_complete is no-op without priority engine."""
        tracker = TaskEffectivenessTracker()

        # Should not raise
        tracker.on_task_complete(
            task_id="IMP-TEST-001",
            success=False,
            metrics={"failure_count": 1},
        )

    def test_on_task_complete_calls_priority_engine(self) -> None:
        """Test on_task_complete forwards to priority engine."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        tracker.on_task_complete(
            task_id="IMP-TEST-001",
            success=False,
            metrics={"failure_count": 2},
        )

        mock_engine.update_from_effectiveness.assert_called_once_with(
            task_id="IMP-TEST-001",
            success=False,
            metrics={"failure_count": 2},
        )

    def test_on_task_complete_records_execution(self) -> None:
        """Test on_task_complete also records execution status."""
        tracker = TaskEffectivenessTracker()

        # Register task first
        tracker.register_task("IMP-TEST-001", priority="high", category="telemetry")

        tracker.on_task_complete(
            task_id="IMP-TEST-001",
            success=True,
        )

        # Verify execution was recorded
        registered = tracker._registered_tasks["IMP-TEST-001"]
        assert registered.executed is True
        assert registered.execution_success is True

    def test_on_task_complete_adds_category_from_registered_task(self) -> None:
        """Test on_task_complete includes category from registered task."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        # Register task with category
        tracker.register_task("IMP-TEST-001", priority="high", category="memory")

        tracker.on_task_complete(
            task_id="IMP-TEST-001",
            success=False,
        )

        # Verify category was added to metrics
        call_args = mock_engine.update_from_effectiveness.call_args
        assert call_args[1]["metrics"]["category"] == "memory"

    def test_on_task_complete_with_metrics(self) -> None:
        """Test on_task_complete passes all metrics."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        tracker.on_task_complete(
            task_id="IMP-TEST-001",
            success=False,
            metrics={
                "failure_count": 3,
                "error_type": "timeout",
                "category": "telemetry",
            },
        )

        call_args = mock_engine.update_from_effectiveness.call_args
        assert call_args[1]["metrics"]["failure_count"] == 3
        assert call_args[1]["metrics"]["error_type"] == "timeout"
        assert call_args[1]["metrics"]["category"] == "telemetry"


class TestNotifyTaskOutcome:
    """Tests for notify_task_outcome method (IMP-LOOP-021)."""

    def test_notify_task_outcome_returns_report(self) -> None:
        """Test notify_task_outcome returns TaskImpactReport."""
        tracker = TaskEffectivenessTracker()

        report = tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=True,
            execution_time_seconds=30.0,
            tokens_used=5000,
        )

        assert report.task_id == "IMP-TEST-001"
        assert report.effectiveness_score > 0

    def test_notify_task_outcome_records_history(self) -> None:
        """Test notify_task_outcome adds to history."""
        tracker = TaskEffectivenessTracker()

        tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=True,
        )

        assert len(tracker.history.reports) == 1

    def test_notify_task_outcome_calls_priority_engine(self) -> None:
        """Test notify_task_outcome forwards to priority engine."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=False,
            failure_count=2,
            error_type="build_error",
            category="build",
        )

        mock_engine.update_from_effectiveness.assert_called_once()
        call_args = mock_engine.update_from_effectiveness.call_args
        assert call_args[1]["task_id"] == "IMP-TEST-001"
        assert call_args[1]["success"] is False
        assert call_args[1]["metrics"]["failure_count"] == 2
        assert call_args[1]["metrics"]["error_type"] == "build_error"

    def test_notify_task_outcome_with_category(self) -> None:
        """Test notify_task_outcome records category."""
        tracker = TaskEffectivenessTracker()

        report = tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=True,
            category="testing",
        )

        assert report.category == "testing"
        assert "testing" in tracker.history.category_stats

    def test_notify_task_outcome_failed_task(self) -> None:
        """Test notify_task_outcome for failed task."""
        tracker = TaskEffectivenessTracker()

        report = tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=False,
            failure_count=1,
        )

        assert report.effectiveness_score == 0.0
        assert report.get_effectiveness_grade() == "poor"

    def test_notify_task_outcome_successful_efficient_task(self) -> None:
        """Test notify_task_outcome for efficient successful task."""
        tracker = TaskEffectivenessTracker()

        report = tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=True,
            execution_time_seconds=30.0,  # Fast
            tokens_used=5000,  # Low tokens
        )

        # Should get full bonus: 0.8 + 0.1 (fast) + 0.1 (low tokens) = 1.0
        assert report.effectiveness_score == pytest.approx(1.0)

    def test_notify_task_outcome_combined_flow(self) -> None:
        """Test notify_task_outcome combines recording and feedback."""
        mock_engine = MagicMock()
        tracker = TaskEffectivenessTracker(priority_engine=mock_engine)

        # Register task first
        tracker.register_task("IMP-TEST-001", priority="critical", category="memory")

        report = tracker.notify_task_outcome(
            task_id="IMP-TEST-001",
            success=False,
            failure_count=3,
        )

        # Verify report was created
        assert report.task_id == "IMP-TEST-001"
        assert report.effectiveness_score == 0.0

        # Verify history was updated
        assert len(tracker.history.reports) == 1

        # Verify priority engine was notified
        mock_engine.update_from_effectiveness.assert_called_once()

        # Verify execution was recorded
        assert tracker._registered_tasks["IMP-TEST-001"].executed is True


class TestCorrectiveTask:
    """Tests for CorrectiveTask dataclass (IMP-LOOP-022)."""

    def test_basic_creation(self) -> None:
        """Test creating a basic CorrectiveTask."""
        task = CorrectiveTask(
            corrective_id="CORR-001",
            original_task_id="IMP-TEST-001",
            failure_count=3,
        )
        assert task.corrective_id == "CORR-001"
        assert task.original_task_id == "IMP-TEST-001"
        assert task.failure_count == 3
        assert task.priority == "high"

    def test_to_dict(self) -> None:
        """Test converting CorrectiveTask to dict."""
        task = CorrectiveTask(
            corrective_id="CORR-001",
            original_task_id="IMP-TEST-001",
            failure_count=3,
            error_patterns=["timeout", "connection_error"],
            category="telemetry",
        )
        data = task.to_dict()

        assert data["corrective_id"] == "CORR-001"
        assert data["original_task_id"] == "IMP-TEST-001"
        assert data["failure_count"] == 3
        assert data["error_patterns"] == ["timeout", "connection_error"]
        assert data["type"] == "corrective"
        assert data["priority"] == "high"

    def test_error_patterns_default_empty(self) -> None:
        """Test error_patterns defaults to empty list."""
        task = CorrectiveTask(
            corrective_id="CORR-001",
            original_task_id="IMP-TEST-001",
            failure_count=3,
        )
        assert task.error_patterns == []


class TestRecordOutcome:
    """Tests for record_outcome method (IMP-LOOP-022)."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_record_failure_increments_count(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording a failure increments the count."""
        tracker.record_outcome(task_id="IMP-TEST-001", success=False, error="test error")

        assert tracker.get_failure_count("IMP-TEST-001") == 1

    def test_record_multiple_failures(self, tracker: TaskEffectivenessTracker) -> None:
        """Test recording multiple failures."""
        tracker.record_outcome(task_id="IMP-TEST-001", success=False, error="error 1")
        tracker.record_outcome(task_id="IMP-TEST-001", success=False, error="error 2")

        assert tracker.get_failure_count("IMP-TEST-001") == 2

    def test_success_resets_failure_count(self, tracker: TaskEffectivenessTracker) -> None:
        """Test success resets the failure count."""
        tracker.record_outcome(task_id="IMP-TEST-001", success=False)
        tracker.record_outcome(task_id="IMP-TEST-001", success=False)
        tracker.record_outcome(task_id="IMP-TEST-001", success=True)

        assert tracker.get_failure_count("IMP-TEST-001") == 0

    def test_errors_are_tracked(self, tracker: TaskEffectivenessTracker) -> None:
        """Test error messages are tracked."""
        tracker.record_outcome(task_id="IMP-TEST-001", success=False, error="error 1")
        tracker.record_outcome(task_id="IMP-TEST-001", success=False, error="error 2")

        assert len(tracker._failure_errors["IMP-TEST-001"]) == 2
        assert "error 1" in tracker._failure_errors["IMP-TEST-001"]
        assert "error 2" in tracker._failure_errors["IMP-TEST-001"]

    def test_corrective_task_generated_at_threshold(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test corrective task is generated at failure threshold."""
        # Record failures up to threshold
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(
                task_id="IMP-TEST-001",
                success=False,
                error=f"error {i}",
            )

        corrective_tasks = tracker.get_corrective_tasks()
        assert len(corrective_tasks) == 1
        assert corrective_tasks[0].original_task_id == "IMP-TEST-001"
        assert corrective_tasks[0].failure_count == CORRECTIVE_TASK_FAILURE_THRESHOLD

    def test_corrective_task_not_generated_below_threshold(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test no corrective task is generated below threshold."""
        # Record failures below threshold
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD - 1):
            tracker.record_outcome(
                task_id="IMP-TEST-001",
                success=False,
                error=f"error {i}",
            )

        corrective_tasks = tracker.get_corrective_tasks()
        assert len(corrective_tasks) == 0

    def test_only_one_corrective_task_per_threshold(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test only one corrective task is generated at threshold crossing."""
        # Record failures beyond threshold
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD + 2):
            tracker.record_outcome(
                task_id="IMP-TEST-001",
                success=False,
                error=f"error {i}",
            )

        corrective_tasks = tracker.get_corrective_tasks()
        # Should still only have 1 corrective task
        assert len(corrective_tasks) == 1

    def test_multiple_tasks_can_trigger_corrective_tasks(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test multiple different tasks can each trigger corrective tasks."""
        # Trigger corrective task for task 1
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(task_id="IMP-TEST-001", success=False)

        # Trigger corrective task for task 2
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(task_id="IMP-TEST-002", success=False)

        corrective_tasks = tracker.get_corrective_tasks()
        assert len(corrective_tasks) == 2
        task_ids = [ct.original_task_id for ct in corrective_tasks]
        assert "IMP-TEST-001" in task_ids
        assert "IMP-TEST-002" in task_ids


class TestCorrectiveTaskGeneration:
    """Tests for corrective task generation and forwarding (IMP-LOOP-022)."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_corrective_task_includes_error_pattern(
        self, tracker: TaskEffectivenessTracker
    ) -> None:
        """Test corrective task includes error pattern analysis."""
        errors = ["timeout error", "timeout occurred", "connection timeout"]
        for error in errors:
            tracker.record_outcome(task_id="IMP-TEST-001", success=False, error=error)

        corrective_tasks = tracker.get_corrective_tasks()
        assert len(corrective_tasks) == 1
        # Should detect "timeout" as common pattern
        assert len(corrective_tasks[0].error_patterns) > 0

    def test_corrective_task_has_high_priority(self, tracker: TaskEffectivenessTracker) -> None:
        """Test corrective tasks always have high priority."""
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(task_id="IMP-TEST-001", success=False)

        corrective_tasks = tracker.get_corrective_tasks()
        assert corrective_tasks[0].priority == "high"

    def test_corrective_task_preserves_category(self, tracker: TaskEffectivenessTracker) -> None:
        """Test corrective task preserves original task category."""
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(
                task_id="IMP-TEST-001",
                success=False,
                category="telemetry",
            )

        corrective_tasks = tracker.get_corrective_tasks()
        assert corrective_tasks[0].category == "telemetry"


class TestCorrectiveTaskSummary:
    """Tests for get_corrective_task_summary method (IMP-LOOP-022)."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_empty_summary(self, tracker: TaskEffectivenessTracker) -> None:
        """Test summary with no failures."""
        summary = tracker.get_corrective_task_summary()

        assert summary["total_corrective_tasks"] == 0
        assert summary["failure_threshold"] == CORRECTIVE_TASK_FAILURE_THRESHOLD
        assert summary["tasks_at_risk"] == []
        assert summary["tasks_exceeded_threshold"] == []
        assert summary["corrective_tasks"] == []

    def test_tasks_at_risk(self, tracker: TaskEffectivenessTracker) -> None:
        """Test tracking tasks at risk of triggering corrective action."""
        # Record failures below threshold
        tracker.record_outcome(task_id="IMP-TEST-001", success=False)
        tracker.record_outcome(task_id="IMP-TEST-001", success=False)

        summary = tracker.get_corrective_task_summary()

        assert len(summary["tasks_at_risk"]) == 1
        assert summary["tasks_at_risk"][0]["task_id"] == "IMP-TEST-001"
        assert summary["tasks_at_risk"][0]["failure_count"] == 2

    def test_tasks_exceeded_threshold(self, tracker: TaskEffectivenessTracker) -> None:
        """Test tracking tasks that exceeded threshold."""
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(task_id="IMP-TEST-001", success=False)

        summary = tracker.get_corrective_task_summary()

        assert len(summary["tasks_exceeded_threshold"]) == 1
        assert summary["tasks_exceeded_threshold"][0]["task_id"] == "IMP-TEST-001"
        assert (
            summary["tasks_exceeded_threshold"][0]["failure_count"]
            == CORRECTIVE_TASK_FAILURE_THRESHOLD
        )

    def test_corrective_tasks_in_summary(self, tracker: TaskEffectivenessTracker) -> None:
        """Test corrective tasks are included in summary."""
        for i in range(CORRECTIVE_TASK_FAILURE_THRESHOLD):
            tracker.record_outcome(task_id="IMP-TEST-001", success=False)

        summary = tracker.get_corrective_task_summary()

        assert summary["total_corrective_tasks"] == 1
        assert len(summary["corrective_tasks"]) == 1
        assert summary["corrective_tasks"][0]["original_task_id"] == "IMP-TEST-001"


class TestFindCommonErrorPattern:
    """Tests for _find_common_error_pattern method (IMP-LOOP-022)."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_single_error(self, tracker: TaskEffectivenessTracker) -> None:
        """Test pattern detection with single error."""
        pattern = tracker._find_common_error_pattern(["Connection timeout"])
        assert "Connection timeout" in pattern

    def test_common_words(self, tracker: TaskEffectivenessTracker) -> None:
        """Test detection of common words across errors."""
        errors = [
            "Connection timeout in database",
            "Connection reset by peer",
            "Connection refused",
        ]
        pattern = tracker._find_common_error_pattern(errors)
        assert "connection" in pattern.lower()

    def test_empty_errors(self, tracker: TaskEffectivenessTracker) -> None:
        """Test pattern detection with empty error list."""
        pattern = tracker._find_common_error_pattern([])
        assert pattern == "Unknown error pattern"

    def test_long_error_truncation(self, tracker: TaskEffectivenessTracker) -> None:
        """Test long error messages are truncated."""
        long_error = "x" * 300
        pattern = tracker._find_common_error_pattern([long_error])
        assert len(pattern) <= 200
