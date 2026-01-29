"""Tests for ROI prediction validation in ROIAnalyzer.

IMP-TASK-003: Tests for ROI prediction validation and effectiveness learning.
"""

from unittest.mock import MagicMock

import pytest

from autopack.task_generation.roi_analyzer import (MIN_SAMPLES_FOR_LEARNING,
                                                   ROIAnalyzer,
                                                   ROIPredictionRecord)


class TestROIPredictionRecord:
    """Tests for ROIPredictionRecord dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic ROIPredictionRecord."""
        record = ROIPredictionRecord(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            actual_roi=4.5,
            predicted_effectiveness=0.5,
            actual_effectiveness=0.45,
            error=0.5,
            category="telemetry",
        )
        assert record.task_id == "IMP-TEST-001"
        assert record.predicted_roi == 5.0
        assert record.actual_roi == 4.5
        assert record.error == 0.5

    def test_accuracy_grade_excellent(self) -> None:
        """Test excellent accuracy grade for low error."""
        record = ROIPredictionRecord(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            actual_roi=5.2,
            predicted_effectiveness=0.5,
            actual_effectiveness=0.52,
            error=0.2,
        )
        # Error 0.2 / predicted 5.0 = 4% relative error -> excellent
        assert record.get_accuracy_grade() == "excellent"

    def test_accuracy_grade_good(self) -> None:
        """Test good accuracy grade for moderate error."""
        record = ROIPredictionRecord(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            actual_roi=4.0,
            predicted_effectiveness=0.5,
            actual_effectiveness=0.4,
            error=1.0,
        )
        # Error 1.0 / predicted 5.0 = 20% relative error -> good
        assert record.get_accuracy_grade() == "good"

    def test_accuracy_grade_moderate(self) -> None:
        """Test moderate accuracy grade for higher error."""
        record = ROIPredictionRecord(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            actual_roi=3.0,
            predicted_effectiveness=0.5,
            actual_effectiveness=0.3,
            error=2.0,
        )
        # Error 2.0 / predicted 5.0 = 40% relative error -> moderate
        assert record.get_accuracy_grade() == "moderate"

    def test_accuracy_grade_poor(self) -> None:
        """Test poor accuracy grade for large error."""
        record = ROIPredictionRecord(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            actual_roi=1.0,
            predicted_effectiveness=0.5,
            actual_effectiveness=0.1,
            error=4.0,
        )
        # Error 4.0 / predicted 5.0 = 80% relative error -> poor
        assert record.get_accuracy_grade() == "poor"


class TestValidateROIPrediction:
    """Tests for validate_roi_prediction method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_validate_existing_prediction(self, analyzer: ROIAnalyzer) -> None:
        """Test validating a prediction that exists."""
        # First create a prediction by calculating payback
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        # Validate the prediction
        record = analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=6.5,
            actual_effectiveness=0.55,
        )

        assert record is not None
        assert record.task_id == "IMP-TEST-001"
        assert record.actual_roi == 6.5
        assert record.actual_effectiveness == 0.55
        assert record.error >= 0

    def test_validate_nonexistent_prediction(self, analyzer: ROIAnalyzer) -> None:
        """Test validating a prediction that doesn't exist."""
        record = analyzer.validate_roi_prediction(
            task_id="IMP-UNKNOWN-001",
            actual_roi=5.0,
            actual_effectiveness=0.5,
        )

        assert record is None

    def test_validation_removes_pending_prediction(self, analyzer: ROIAnalyzer) -> None:
        """Test that validation removes the pending prediction."""
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        assert "IMP-TEST-001" in analyzer._pending_predictions

        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=6.0,
            actual_effectiveness=0.5,
        )

        assert "IMP-TEST-001" not in analyzer._pending_predictions

    def test_validation_adds_to_history(self, analyzer: ROIAnalyzer) -> None:
        """Test that validation adds record to history."""
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=6.0,
            actual_effectiveness=0.5,
        )

        assert len(analyzer._roi_predictions) == 1
        assert analyzer._roi_predictions[0].task_id == "IMP-TEST-001"


class TestLearnedEffectiveness:
    """Tests for learned effectiveness functionality."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_no_learned_effectiveness_initially(self, analyzer: ROIAnalyzer) -> None:
        """Test that no learned effectiveness exists initially."""
        result = analyzer._get_learned_effectiveness("telemetry")
        assert result is None

    def test_learned_effectiveness_after_validations(self, analyzer: ROIAnalyzer) -> None:
        """Test learned effectiveness is available after sufficient validations."""
        # Create and validate multiple predictions to build up learning data
        for i in range(MIN_SAMPLES_FOR_LEARNING):
            analyzer.calculate_payback_period(
                task_id=f"IMP-TEST-{i:03d}",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
                category="telemetry",
            )
            analyzer.validate_roi_prediction(
                task_id=f"IMP-TEST-{i:03d}",
                actual_roi=7.0,
                actual_effectiveness=0.7,
            )

        # Now learned effectiveness should be available
        learned = analyzer._get_learned_effectiveness("telemetry")
        assert learned is not None
        assert 0.0 <= learned <= 1.0

    def test_learned_effectiveness_used_in_calculation(self, analyzer: ROIAnalyzer) -> None:
        """Test that learned effectiveness is used in ROI calculation."""
        # Build up learning data
        for i in range(MIN_SAMPLES_FOR_LEARNING):
            analyzer.calculate_payback_period(
                task_id=f"IMP-TEST-{i:03d}",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
                category="telemetry",
            )
            analyzer.validate_roi_prediction(
                task_id=f"IMP-TEST-{i:03d}",
                actual_roi=7.0,
                actual_effectiveness=0.9,  # High effectiveness
            )

        # Now calculate a new payback - should use learned effectiveness
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-NEW-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        # Learned effectiveness should be close to 0.9
        # With 100 token reduction and 0.9 effectiveness = 90 savings
        # This is higher than default 0.5 * 100 = 50
        assert analysis.estimated_savings_per_phase > 50.0

    def test_insufficient_samples_uses_default(self, analyzer: ROIAnalyzer) -> None:
        """Test that insufficient samples falls back to default effectiveness."""
        # Add only 1 validation (less than MIN_SAMPLES_FOR_LEARNING)
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=7.0,
            actual_effectiveness=0.9,
        )

        # Should return None (not enough samples)
        learned = analyzer._get_learned_effectiveness("telemetry")
        assert learned is None


class TestUpdateEffectivenessModel:
    """Tests for _update_effectiveness_model method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_first_update_initializes_model(self, analyzer: ROIAnalyzer) -> None:
        """Test that first update initializes the model."""
        analyzer._update_effectiveness_model("telemetry", 0.8)

        assert "telemetry" in analyzer._category_effectiveness
        stats = analyzer._category_effectiveness["telemetry"]
        assert stats["learned_effectiveness"] == 0.8
        assert stats["sample_count"] == 1

    def test_subsequent_updates_smooth_learning(self, analyzer: ROIAnalyzer) -> None:
        """Test that subsequent updates use exponential moving average."""
        # Initialize
        analyzer._update_effectiveness_model("telemetry", 0.8)

        # Update with different value
        analyzer._update_effectiveness_model("telemetry", 0.4)

        stats = analyzer._category_effectiveness["telemetry"]
        # Should be somewhere between 0.4 and 0.8 due to EMA
        assert 0.4 < stats["learned_effectiveness"] < 0.8
        assert stats["sample_count"] == 2

    def test_general_category_fallback(self, analyzer: ROIAnalyzer) -> None:
        """Test that empty category falls back to 'general'."""
        analyzer._update_effectiveness_model("", 0.7)

        assert "general" in analyzer._category_effectiveness
        assert (
            "general" not in analyzer._category_effectiveness
            or "" not in analyzer._category_effectiveness
        )

    def test_multiple_categories_tracked_separately(self, analyzer: ROIAnalyzer) -> None:
        """Test that different categories are tracked independently."""
        analyzer._update_effectiveness_model("telemetry", 0.9)
        analyzer._update_effectiveness_model("memory", 0.5)

        assert analyzer._category_effectiveness["telemetry"]["learned_effectiveness"] == 0.9
        assert analyzer._category_effectiveness["memory"]["learned_effectiveness"] == 0.5


class TestRecordPrediction:
    """Tests for record_prediction method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_record_prediction_stores_data(self, analyzer: ROIAnalyzer) -> None:
        """Test that recording a prediction stores the data."""
        analyzer.record_prediction(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            predicted_effectiveness=0.6,
            category="telemetry",
        )

        assert "IMP-TEST-001" in analyzer._pending_predictions
        prediction = analyzer._pending_predictions["IMP-TEST-001"]
        assert prediction["predicted_roi"] == 5.0
        assert prediction["predicted_effectiveness"] == 0.6
        assert prediction["category"] == "telemetry"

    def test_record_prediction_includes_timestamp(self, analyzer: ROIAnalyzer) -> None:
        """Test that recorded prediction includes timestamp."""
        analyzer.record_prediction(
            task_id="IMP-TEST-001",
            predicted_roi=5.0,
            predicted_effectiveness=0.6,
        )

        prediction = analyzer._pending_predictions["IMP-TEST-001"]
        assert "recorded_at" in prediction


class TestGetValidationSummary:
    """Tests for get_validation_summary method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_empty_summary(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with no validations."""
        summary = analyzer.get_validation_summary()

        assert summary["total_validations"] == 0
        assert summary["avg_error"] == 0.0
        assert summary["avg_effectiveness_error"] == 0.0
        assert summary["learned_effectiveness"] == {}
        assert summary["pending_predictions"] == 0

    def test_summary_with_validations(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with validated predictions."""
        # Create and validate predictions
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=7.0,
            actual_effectiveness=0.55,
        )

        summary = analyzer.get_validation_summary()

        assert summary["total_validations"] == 1
        assert "telemetry" in summary["learned_effectiveness"]

    def test_summary_counts_pending_predictions(self, analyzer: ROIAnalyzer) -> None:
        """Test that summary counts pending predictions."""
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-002",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        summary = analyzer.get_validation_summary()
        assert summary["pending_predictions"] == 2

    def test_summary_accuracy_distribution(self, analyzer: ROIAnalyzer) -> None:
        """Test accuracy distribution in summary."""
        # Create predictions with different accuracy levels
        for i in range(4):
            analyzer.calculate_payback_period(
                task_id=f"IMP-TEST-{i:03d}",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
            )

        # Validate with different actual values to get various accuracy grades
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-000",
            actual_roi=7.2,  # Close to predicted -> excellent
            actual_effectiveness=0.5,
        )
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-001",
            actual_roi=6.0,  # Moderate difference -> good
            actual_effectiveness=0.5,
        )
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-002",
            actual_roi=4.0,  # Larger difference -> moderate
            actual_effectiveness=0.5,
        )
        analyzer.validate_roi_prediction(
            task_id="IMP-TEST-003",
            actual_roi=1.0,  # Very different -> poor
            actual_effectiveness=0.5,
        )

        summary = analyzer.get_validation_summary()

        # Should have distribution across grades
        total_grades = sum(summary["accuracy_distribution"].values())
        assert total_grades == 4


class TestIntegrationWithEffectivenessTracker:
    """Integration tests with TaskEffectivenessTracker."""

    def test_learned_effectiveness_takes_priority(self) -> None:
        """Test that learned effectiveness takes priority over tracker."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.3  # Low tracker value
        mock_tracker.get_category_effectiveness.return_value = 0.3

        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        # Build up learning data with high effectiveness
        for i in range(MIN_SAMPLES_FOR_LEARNING):
            analyzer.calculate_payback_period(
                task_id=f"IMP-TEST-{i:03d}",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
                category="telemetry",
            )
            analyzer.validate_roi_prediction(
                task_id=f"IMP-TEST-{i:03d}",
                actual_roi=9.0,
                actual_effectiveness=0.9,
            )

        # New calculation should use learned effectiveness (0.9) not tracker (0.3)
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-NEW-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        # With 0.9 effectiveness: 100 * 0.9 = 90 savings
        # With 0.3 effectiveness: 100 * 0.3 = 30 savings
        assert analysis.estimated_savings_per_phase > 50.0

    def test_falls_back_to_tracker_when_no_learning_data(self) -> None:
        """Test fallback to tracker when no learned data exists."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.8
        mock_tracker.get_category_effectiveness.return_value = 0.8

        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        # Should use tracker's 0.8 effectiveness
        assert analysis.estimated_savings_per_phase == pytest.approx(80.0)
        mock_tracker.get_effectiveness.assert_called_once()
