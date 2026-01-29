"""Tests for IMP-LOOP-031 ROI Feedback Loop Closure.

This module tests the actual ROI measurement and comparison functionality
that enables calibration of the prioritization engine by comparing estimated
ROI predictions against actual outcomes.
"""

from datetime import datetime

import pytest

from autopack.task_generation.roi_analyzer import ActualROIResult, ROIAccuracyReport, ROIAnalyzer
from autopack.task_generation.task_effectiveness_tracker import TaskEffectivenessTracker


class TestActualROIResult:
    """Tests for ActualROIResult dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic ActualROIResult."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=8.5,
            actual_cost=5000.0,
            actual_savings=600.0,
            actual_roi=2.5,
        )

        assert result.task_id == "IMP-LOOP-031"
        assert result.estimated_payback == 10
        assert result.actual_payback == 8.5
        assert result.actual_cost == 5000.0
        assert result.actual_savings == 600.0
        assert result.actual_roi == 2.5
        assert isinstance(result.measured_at, datetime)

    def test_achieved_payback_true(self) -> None:
        """Test achieved_payback returns True when actual <= 2x estimated."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=15.0,  # 1.5x estimated, within 2x threshold
            actual_cost=5000.0,
            actual_savings=333.0,
            actual_roi=1.5,
        )

        assert result.achieved_payback() is True

    def test_achieved_payback_false_too_slow(self) -> None:
        """Test achieved_payback returns False when actual > 2x estimated."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=25.0,  # 2.5x estimated, exceeds 2x threshold
            actual_cost=5000.0,
            actual_savings=200.0,
            actual_roi=0.5,
        )

        assert result.achieved_payback() is False

    def test_achieved_payback_false_infinite(self) -> None:
        """Test achieved_payback returns False when actual_payback is infinite."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=float("inf"),
            actual_cost=5000.0,
            actual_savings=0.0,
            actual_roi=0.0,
        )

        assert result.achieved_payback() is False

    def test_get_roi_grade_excellent(self) -> None:
        """Test ROI grade excellent for high actual ROI."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=5.0,
            actual_cost=1000.0,
            actual_savings=200.0,
            actual_roi=5.5,  # >= 5.0 is excellent
        )

        assert result.get_roi_grade() == "excellent"

    def test_get_roi_grade_good(self) -> None:
        """Test ROI grade good for moderate actual ROI."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=8.0,
            actual_cost=1000.0,
            actual_savings=125.0,
            actual_roi=3.0,  # >= 2.0 is good
        )

        assert result.get_roi_grade() == "good"

    def test_get_roi_grade_moderate(self) -> None:
        """Test ROI grade moderate for break-even ROI."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=12.0,
            actual_cost=1000.0,
            actual_savings=83.3,
            actual_roi=1.2,  # >= 1.0 is moderate
        )

        assert result.get_roi_grade() == "moderate"

    def test_get_roi_grade_poor(self) -> None:
        """Test ROI grade poor for negative/low ROI."""
        result = ActualROIResult(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=50.0,
            actual_cost=1000.0,
            actual_savings=20.0,
            actual_roi=0.3,  # < 0.5 is poor
        )

        assert result.get_roi_grade() == "poor"


class TestROIAccuracyReport:
    """Tests for ROIAccuracyReport dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic ROIAccuracyReport."""
        report = ROIAccuracyReport(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=12.0,
            prediction_error=2.0,
            calibration_factor=1.2,
            accuracy_grade="good",
            category="loop",
        )

        assert report.task_id == "IMP-LOOP-031"
        assert report.estimated_payback == 10
        assert report.actual_payback == 12.0
        assert report.prediction_error == 2.0
        assert report.calibration_factor == 1.2
        assert report.accuracy_grade == "good"
        assert report.category == "loop"
        assert isinstance(report.measured_at, datetime)

    def test_is_calibration_needed_true(self) -> None:
        """Test calibration is needed when factor deviates > 20%."""
        report = ROIAccuracyReport(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=15.0,
            prediction_error=5.0,
            calibration_factor=1.5,  # 50% deviation, > 20% threshold
            accuracy_grade="moderate",
        )

        assert report.is_calibration_needed() is True

    def test_is_calibration_needed_false(self) -> None:
        """Test calibration not needed when factor is close to 1.0."""
        report = ROIAccuracyReport(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=11.0,
            prediction_error=1.0,
            calibration_factor=1.1,  # 10% deviation, < 20% threshold
            accuracy_grade="good",
        )

        assert report.is_calibration_needed() is False

    def test_is_calibration_needed_under_estimate(self) -> None:
        """Test calibration needed when we over-estimated payback."""
        report = ROIAccuracyReport(
            task_id="IMP-LOOP-031",
            estimated_payback=10,
            actual_payback=5.0,
            prediction_error=5.0,
            calibration_factor=0.5,  # 50% deviation (under)
            accuracy_grade="moderate",
        )

        assert report.is_calibration_needed() is True


class TestROIAnalyzerActualMeasurement:
    """Tests for ROIAnalyzer actual ROI measurement methods."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an ROIAnalyzer for testing."""
        effectiveness_tracker = TaskEffectivenessTracker()
        return ROIAnalyzer(effectiveness_tracker=effectiveness_tracker)

    def test_record_task_cost(self, analyzer: ROIAnalyzer) -> None:
        """Test recording actual task cost."""
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)

        assert analyzer.get_task_cost("IMP-LOOP-031") == 5000.0

    def test_record_task_savings(self, analyzer: ROIAnalyzer) -> None:
        """Test recording actual task savings."""
        analyzer.record_task_savings("IMP-LOOP-031", 500.0)

        assert analyzer.get_task_savings("IMP-LOOP-031") == 500.0

    def test_get_task_cost_fallback_to_analysis(self, analyzer: ROIAnalyzer) -> None:
        """Test get_task_cost falls back to original analysis if no recorded cost."""
        # Create an original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
        )

        # Without recording actual cost, should fall back to execution_cost
        cost = analyzer.get_task_cost("IMP-LOOP-031")
        assert cost == 5000.0

    def test_get_task_cost_unknown_task(self, analyzer: ROIAnalyzer) -> None:
        """Test get_task_cost returns 0 for unknown task."""
        cost = analyzer.get_task_cost("UNKNOWN-TASK")
        assert cost == 0.0

    def test_get_task_savings_unknown_task(self, analyzer: ROIAnalyzer) -> None:
        """Test get_task_savings returns 0 for unknown task."""
        savings = analyzer.get_task_savings("UNKNOWN-TASK")
        assert savings == 0.0

    def test_measure_actual_roi_success(self, analyzer: ROIAnalyzer) -> None:
        """Test measuring actual ROI for a successful task."""
        # Create original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # Record actual cost and savings
        analyzer.record_task_cost("IMP-LOOP-031", 4500.0)  # Slightly less cost
        analyzer.record_task_savings("IMP-LOOP-031", 600.0)  # Better savings

        # Measure actual ROI
        result = analyzer.measure_actual_roi("IMP-LOOP-031")

        assert result is not None
        assert result.task_id == "IMP-LOOP-031"
        assert result.actual_cost == 4500.0
        assert result.actual_savings == 600.0
        assert result.actual_payback == pytest.approx(7.5)  # 4500 / 600
        # actual_roi = (600 * 100 - 4500) / 4500 = (60000 - 4500) / 4500 = 12.33
        assert result.actual_roi > 10.0  # High ROI

    def test_measure_actual_roi_no_savings(self, analyzer: ROIAnalyzer) -> None:
        """Test measuring actual ROI when no savings achieved."""
        # Create original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
        )

        # Record actual cost but no savings
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 0.0)

        result = analyzer.measure_actual_roi("IMP-LOOP-031")

        assert result is not None
        assert result.actual_payback == float("inf")
        assert result.actual_roi == 0.0

    def test_measure_actual_roi_unknown_task(self, analyzer: ROIAnalyzer) -> None:
        """Test measuring actual ROI for unknown task returns None."""
        result = analyzer.measure_actual_roi("UNKNOWN-TASK")
        assert result is None

    def test_measure_actual_roi_stores_result(self, analyzer: ROIAnalyzer) -> None:
        """Test that measure_actual_roi stores the result."""
        # Create original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
        )

        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 500.0)

        analyzer.measure_actual_roi("IMP-LOOP-031")

        # Check result was stored
        assert len(analyzer._actual_roi_results) == 1
        assert analyzer._actual_roi_results[0].task_id == "IMP-LOOP-031"


class TestROIAnalyzerComparison:
    """Tests for ROIAnalyzer comparison methods."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an ROIAnalyzer for testing."""
        return ROIAnalyzer()

    def test_compare_estimated_vs_actual_accurate(self, analyzer: ROIAnalyzer) -> None:
        """Test comparison when prediction was accurate."""
        # Create original analysis
        # With DEFAULT_EFFECTIVENESS=0.5 and token_reduction=500:
        # savings_per_phase = 500 * 0.5 = 250
        # payback_phases = int(5000 / 250) + 1 = 21
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # Record actual data matching the estimated payback (~21 phases)
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 250.0)  # Payback = 20, close to 21

        report = analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert report is not None
        assert report.task_id == "IMP-LOOP-031"
        assert report.prediction_error < 5.0  # Low error
        assert 0.8 < report.calibration_factor < 1.2  # Close to 1.0
        assert report.accuracy_grade in ["excellent", "good"]

    def test_compare_estimated_vs_actual_under_estimated(self, analyzer: ROIAnalyzer) -> None:
        """Test comparison when we under-estimated payback time."""
        # Create original analysis
        # estimated payback = 21 phases (with 250 savings/phase)
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # Actual payback takes longer (worse savings)
        # With 125 savings/phase, actual payback = 5000/125 = 40 phases
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 125.0)  # Actual payback = 40

        report = analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert report is not None
        # Calibration factor > 1 means actual takes longer than estimated
        # 40 / 21 = ~1.9
        assert report.calibration_factor > 1.0

    def test_compare_estimated_vs_actual_over_estimated(self, analyzer: ROIAnalyzer) -> None:
        """Test comparison when we over-estimated payback time."""
        # Create original analysis
        # estimated payback = 21 phases
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # Actual payback is faster (better savings)
        # With 1000 savings/phase, actual payback = 5000/1000 = 5 phases
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 1000.0)  # Actual payback = 5

        report = analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert report is not None
        # Calibration factor < 1 means actual is faster than estimated
        # 5 / 21 = ~0.24
        assert report.calibration_factor < 1.0

    def test_compare_estimated_vs_actual_no_savings(self, analyzer: ROIAnalyzer) -> None:
        """Test comparison when task achieved no savings."""
        # Create original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # No savings achieved
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 0.0)

        report = analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert report is not None
        assert report.accuracy_grade == "poor"
        # Calibration factor capped at 10.0 for infinite payback
        assert report.calibration_factor == 10.0

    def test_compare_estimated_vs_actual_stores_report(self, analyzer: ROIAnalyzer) -> None:
        """Test that comparison stores the accuracy report."""
        # Create original analysis
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
        )

        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 500.0)

        analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert len(analyzer._accuracy_reports) == 1
        assert analyzer._accuracy_reports[0].task_id == "IMP-LOOP-031"

    def test_compare_unknown_task(self, analyzer: ROIAnalyzer) -> None:
        """Test comparison for unknown task returns None."""
        report = analyzer.compare_estimated_vs_actual("UNKNOWN-TASK")
        assert report is None


class TestROIAnalyzerCalibration:
    """Tests for ROIAnalyzer calibration methods."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an ROIAnalyzer for testing."""
        return ROIAnalyzer()

    def test_get_category_calibration_factor_default(self, analyzer: ROIAnalyzer) -> None:
        """Test default calibration factor is 1.0."""
        factor = analyzer.get_category_calibration_factor("unknown-category")
        assert factor == 1.0

    def test_category_calibration_updates(self, analyzer: ROIAnalyzer) -> None:
        """Test that calibration factor updates after comparison."""
        # Create and compare task
        # Estimated: 500 * 0.5 = 250 savings/phase, payback = 21 phases
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            category="loop",
        )

        # Actual: 125 savings/phase, payback = 40 phases (worse than estimated)
        analyzer.record_task_cost("IMP-LOOP-031", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-031", 125.0)  # Payback = 40

        analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        # Calibration factor should be updated for "loop" category
        # 40 / 21 = ~1.9, so factor > 1
        factor = analyzer.get_category_calibration_factor("loop")
        assert factor > 1.0  # Under-estimated, so factor > 1

    def test_calibration_learns_over_time(self, analyzer: ROIAnalyzer) -> None:
        """Test that calibration improves with multiple comparisons."""
        # Create multiple tasks in same category
        # Estimated payback = 21 phases (with 250 savings/phase)
        for i in range(5):
            task_id = f"IMP-LOOP-{i:03d}"
            analyzer.calculate_payback_period(
                task_id=task_id,
                estimated_token_reduction=500.0,
                execution_cost=5000.0,
                category="loop",
            )

            # All tasks take 1.5x longer than estimated
            # Estimated payback = 21, target actual = 21 * 1.5 = 31.5
            # To get payback = 31.5, need savings = 5000 / 31.5 = 158.7
            analyzer.record_task_cost(task_id, 5000.0)
            analyzer.record_task_savings(task_id, 159.0)  # Payback ~31.4

            analyzer.compare_estimated_vs_actual(task_id)

        # After multiple samples, calibration should reflect the 1.5x pattern
        factor = analyzer.get_category_calibration_factor("loop")
        assert 1.3 < factor < 1.7  # Should be close to 1.5


class TestROIFeedbackSummary:
    """Tests for ROI feedback summary method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an ROIAnalyzer for testing."""
        return ROIAnalyzer()

    def test_empty_summary(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with no measurements."""
        summary = analyzer.get_roi_feedback_summary()

        assert summary["total_measurements"] == 0
        assert summary["total_accuracy_reports"] == 0
        assert summary["avg_prediction_error"] == 0.0
        assert summary["avg_calibration_factor"] == 1.0
        assert summary["tasks_achieving_payback"] == 0
        assert summary["tasks_total"] == 0

    def test_summary_with_measurements(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with actual measurements."""
        # Create tasks and measure ROI
        for i in range(3):
            task_id = f"IMP-LOOP-{i:03d}"
            analyzer.calculate_payback_period(
                task_id=task_id,
                estimated_token_reduction=500.0,
                execution_cost=5000.0,
                category="loop",
            )

            analyzer.record_task_cost(task_id, 5000.0)
            # Varying savings
            savings = [500.0, 250.0, 0.0][i]
            analyzer.record_task_savings(task_id, savings)

            analyzer.measure_actual_roi(task_id)
            analyzer.compare_estimated_vs_actual(task_id)

        summary = analyzer.get_roi_feedback_summary()

        assert summary["total_measurements"] == 3
        assert summary["total_accuracy_reports"] == 3
        # First task achieves payback (savings > 0, reasonable ROI)
        assert summary["tasks_achieving_payback"] >= 1
        assert "loop" in summary["category_calibration"]

    def test_summary_accuracy_distribution(self, analyzer: ROIAnalyzer) -> None:
        """Test that summary includes accuracy distribution."""
        # Create task with accurate prediction
        analyzer.calculate_payback_period(
            task_id="IMP-LOOP-001",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
        )
        analyzer.record_task_cost("IMP-LOOP-001", 5000.0)
        analyzer.record_task_savings("IMP-LOOP-001", 500.0)  # Matches estimate
        analyzer.compare_estimated_vs_actual("IMP-LOOP-001")

        summary = analyzer.get_roi_feedback_summary()

        assert "accuracy_distribution" in summary
        total_grades = sum(summary["accuracy_distribution"].values())
        assert total_grades == 1


class TestROIFeedbackIntegration:
    """Integration tests for ROI feedback loop."""

    def test_full_feedback_loop(self) -> None:
        """Test complete ROI feedback loop from estimation to calibration."""
        # Setup
        effectiveness_tracker = TaskEffectivenessTracker()
        analyzer = ROIAnalyzer(effectiveness_tracker=effectiveness_tracker)

        # Step 1: Generate task with ROI estimate
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-LOOP-031",
            estimated_token_reduction=500.0,
            execution_cost=5000.0,
            confidence=0.8,
            category="loop",
        )

        estimated_payback = analysis.payback_phases
        assert estimated_payback > 0

        # Step 2: Simulate task execution with outcome
        # Record actual cost (task ran more efficiently)
        analyzer.record_task_cost("IMP-LOOP-031", 4000.0)
        # Record actual savings (better than expected)
        analyzer.record_task_savings("IMP-LOOP-031", 600.0)

        # Step 3: Measure actual ROI
        actual_result = analyzer.measure_actual_roi("IMP-LOOP-031")

        assert actual_result is not None
        assert actual_result.actual_cost == 4000.0
        assert actual_result.actual_savings == 600.0

        # Step 4: Compare for calibration
        accuracy_report = analyzer.compare_estimated_vs_actual("IMP-LOOP-031")

        assert accuracy_report is not None
        assert accuracy_report.category == "loop"

        # Step 5: Verify calibration is available
        calibration = analyzer.get_category_calibration_factor("loop")
        assert calibration != 1.0  # Should have been adjusted

        # Step 6: Check summary
        summary = analyzer.get_roi_feedback_summary()
        assert summary["total_measurements"] == 1
        assert summary["total_accuracy_reports"] == 1

    def test_feedback_loop_multiple_categories(self) -> None:
        """Test feedback loop tracks multiple categories independently."""
        analyzer = ROIAnalyzer()

        # Create tasks in different categories
        categories = ["loop", "memory", "telemetry"]

        for i, category in enumerate(categories):
            task_id = f"IMP-{category.upper()}-001"
            analyzer.calculate_payback_period(
                task_id=task_id,
                estimated_token_reduction=500.0,
                execution_cost=5000.0,
                category=category,
            )

            # Different performance per category
            savings_multiplier = [1.0, 0.5, 1.5][i]
            analyzer.record_task_cost(task_id, 5000.0)
            analyzer.record_task_savings(task_id, 500.0 * savings_multiplier)

            analyzer.compare_estimated_vs_actual(task_id)

        # Each category should have independent calibration
        summary = analyzer.get_roi_feedback_summary()
        category_calibration = summary["category_calibration"]

        assert "loop" in category_calibration
        assert "memory" in category_calibration
        assert "telemetry" in category_calibration

        # Memory category should have higher calibration (under-performed)
        # Telemetry should have lower calibration (over-performed)
        assert category_calibration["memory"] > category_calibration["telemetry"]


class TestTaskEffectivenessTrackerSavings:
    """Tests for get_savings method in TaskEffectivenessTracker."""

    @pytest.fixture
    def tracker(self) -> TaskEffectivenessTracker:
        """Create a tracker for testing."""
        return TaskEffectivenessTracker()

    def test_get_savings_from_impact_report(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting savings from task impact report."""
        # Record a task outcome with improvement
        tracker.measure_impact(
            task_id="IMP-LOOP-031",
            before_metrics={"error_rate": 0.1},
            after_metrics={"error_rate": 0.05},
            target=0.5,  # 50% improvement target
            category="loop",
        )

        savings = tracker.get_savings("IMP-LOOP-031")

        # Should compute savings based on actual improvement
        assert savings > 0.0

    def test_get_savings_unknown_task(self, tracker: TaskEffectivenessTracker) -> None:
        """Test get_savings returns 0 for unknown task."""
        savings = tracker.get_savings("UNKNOWN-TASK")
        assert savings == 0.0

    def test_get_task_cost_estimate(self, tracker: TaskEffectivenessTracker) -> None:
        """Test getting task cost estimate from attribution outcomes."""
        # Record attribution outcome with token usage
        tracker.record_task_attribution_outcome(
            task_id="IMP-LOOP-031",
            phase_id="phase-123",
            success=True,
            tokens_used=8000,
        )

        cost = tracker.get_task_cost_estimate("IMP-LOOP-031")
        assert cost == 8000.0

    def test_get_task_cost_estimate_unknown(self, tracker: TaskEffectivenessTracker) -> None:
        """Test get_task_cost_estimate returns 0 for unknown task."""
        cost = tracker.get_task_cost_estimate("UNKNOWN-TASK")
        assert cost == 0.0
