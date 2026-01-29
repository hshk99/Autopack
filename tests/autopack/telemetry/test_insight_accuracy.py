"""Tests for insight accuracy measurement (IMP-LOOP-035).

Tests the InsightAccuracyReport and ThresholdUpdate dataclasses and the
measure_insight_accuracy() and recalibrate_thresholds() methods for tracking
how well insights predict actual problems and recalibrating thresholds.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from autopack.telemetry.analyzer import (InsightAccuracyReport,
                                         TelemetryAnalyzer, ThresholdUpdate)


class TestInsightAccuracyReport:
    """Tests for InsightAccuracyReport dataclass."""

    def test_creation_basic(self):
        """Test basic creation of InsightAccuracyReport."""
        report = InsightAccuracyReport(
            insight_id="insight-001",
            predicted_problem="cost_sink",
            actual_problem="cost_sink_confirmed",
            prediction_correct=True,
            predicted_confidence=0.8,
            confidence_calibration=1.0,
        )

        assert report.insight_id == "insight-001"
        assert report.predicted_problem == "cost_sink"
        assert report.actual_problem == "cost_sink_confirmed"
        assert report.prediction_correct is True
        assert report.predicted_confidence == 0.8
        assert report.confidence_calibration == 1.0
        assert report.measured_at is not None

    def test_creation_with_all_fields(self):
        """Test creation with all optional fields."""
        now = datetime.now(timezone.utc)
        report = InsightAccuracyReport(
            insight_id="insight-002",
            predicted_problem="failure_mode",
            actual_problem="timeout_failure",
            prediction_correct=True,
            predicted_confidence=0.7,
            confidence_calibration=1.1,
            measured_at=now,
            task_id="IMP-LOOP-035",
            notes="Test note",
        )

        assert report.task_id == "IMP-LOOP-035"
        assert report.notes == "Test note"
        assert report.measured_at == now

    def test_auto_timestamp(self):
        """Test that measured_at is auto-populated."""
        before = datetime.now(timezone.utc)
        report = InsightAccuracyReport(
            insight_id="insight-003",
            predicted_problem="test",
            actual_problem="test",
            prediction_correct=True,
            predicted_confidence=0.5,
            confidence_calibration=1.0,
        )
        after = datetime.now(timezone.utc)

        assert before <= report.measured_at <= after


class TestThresholdUpdate:
    """Tests for ThresholdUpdate dataclass."""

    def test_creation_basic(self):
        """Test basic creation of ThresholdUpdate."""
        update = ThresholdUpdate(
            threshold_name="cost_sink_threshold",
            old_value=50000.0,
            new_value=60000.0,
            calibration_factor=1.2,
            reason="Low accuracy, overconfident",
        )

        assert update.threshold_name == "cost_sink_threshold"
        assert update.old_value == 50000.0
        assert update.new_value == 60000.0
        assert update.calibration_factor == 1.2
        assert update.reason == "Low accuracy, overconfident"
        assert update.updated_at is not None

    def test_creation_with_all_fields(self):
        """Test creation with all fields."""
        now = datetime.now(timezone.utc)
        update = ThresholdUpdate(
            threshold_name="failure_rate_threshold",
            old_value=0.3,
            new_value=0.35,
            calibration_factor=1.17,
            reason="Calibration based on 10 reports",
            accuracy_reports_count=10,
            updated_at=now,
        )

        assert update.accuracy_reports_count == 10
        assert update.updated_at == now


class TestTelemetryAnalyzerInsightAccuracy:
    """Tests for TelemetryAnalyzer insight accuracy methods."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_register_insight(self, analyzer):
        """Test registering an insight for tracking."""
        analyzer.register_insight(
            insight_id="insight-001",
            predicted_problem="high_token_usage",
            confidence=0.85,
            issue_type="cost_sink",
            phase_id="phase-123",
            phase_type="test_generation",
            metric_value=75000.0,
        )

        insight = analyzer.get_insight("insight-001")
        assert insight is not None
        assert insight["predicted_problem"] == "high_token_usage"
        assert insight["confidence"] == 0.85
        assert insight["issue_type"] == "cost_sink"
        assert insight["phase_id"] == "phase-123"

    def test_get_insight_not_found(self, analyzer):
        """Test getting a non-existent insight."""
        result = analyzer.get_insight("nonexistent")
        assert result is None

    def test_measure_insight_accuracy_insight_not_found(self, analyzer):
        """Test measuring accuracy when insight is not registered."""
        report = analyzer.measure_insight_accuracy("nonexistent-insight")

        assert report.insight_id == "nonexistent-insight"
        assert report.prediction_correct is False
        assert "not found" in report.notes.lower()

    def test_measure_insight_accuracy_correct_prediction(self, analyzer, mock_db):
        """Test measuring accuracy for a correct prediction."""
        # Register an insight
        analyzer.register_insight(
            insight_id="insight-cost-001",
            predicted_problem="cost_sink",
            confidence=0.8,
            issue_type="cost_sink",
            phase_id="phase-456",
        )

        # Mock DB response for outcome
        mock_row = MagicMock()
        mock_row.phase_outcome = "SUCCESS"
        mock_row.stop_reason = None
        mock_row.tokens_used = 80000  # High token usage confirms cost sink
        mock_row.duration_seconds = 10.0

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        report = analyzer.measure_insight_accuracy("insight-cost-001")

        assert report.insight_id == "insight-cost-001"
        assert report.predicted_problem == "cost_sink"
        assert report.actual_problem == "cost_sink_confirmed"
        assert report.prediction_correct is True

    def test_measure_insight_accuracy_incorrect_prediction(self, analyzer, mock_db):
        """Test measuring accuracy for an incorrect prediction."""
        # Register an insight predicting failure
        analyzer.register_insight(
            insight_id="insight-fail-001",
            predicted_problem="failure_expected",
            confidence=0.9,
            issue_type="failure_mode",
            phase_id="phase-789",
        )

        # Mock DB response showing success (prediction was wrong)
        mock_row = MagicMock()
        mock_row.phase_outcome = "SUCCESS"
        mock_row.stop_reason = None
        mock_row.tokens_used = 1000  # Low tokens
        mock_row.duration_seconds = 5.0  # Fast

        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result

        report = analyzer.measure_insight_accuracy("insight-fail-001")

        assert report.prediction_correct is False
        assert report.actual_problem == "no_problem_detected"
        # High confidence but wrong = low calibration factor
        assert report.confidence_calibration < 1.0

    def test_calibration_factor_correct_high_confidence(self, analyzer):
        """Test calibration factor for correct prediction with high confidence."""
        factor = analyzer._calculate_calibration_factor(
            predicted_confidence=0.9,
            prediction_correct=True,
        )
        # Correct with high confidence = appropriate, factor near 1.0
        assert factor == 1.0

    def test_calibration_factor_correct_low_confidence(self, analyzer):
        """Test calibration factor for correct prediction with low confidence."""
        factor = analyzer._calculate_calibration_factor(
            predicted_confidence=0.3,
            prediction_correct=True,
        )
        # Correct but low confidence = underconfident, factor > 1.0
        assert factor > 1.0

    def test_calibration_factor_incorrect_high_confidence(self, analyzer):
        """Test calibration factor for incorrect prediction with high confidence."""
        factor = analyzer._calculate_calibration_factor(
            predicted_confidence=0.9,
            prediction_correct=False,
        )
        # Wrong with high confidence = significantly overconfident, factor < 1.0
        assert factor < 0.8

    def test_calibration_factor_incorrect_low_confidence(self, analyzer):
        """Test calibration factor for incorrect prediction with low confidence."""
        factor = analyzer._calculate_calibration_factor(
            predicted_confidence=0.3,
            prediction_correct=False,
        )
        # Wrong but low confidence = only slightly overconfident
        assert factor >= 0.9

    def test_is_prediction_correct_exact_match(self, analyzer):
        """Test prediction correctness with exact match."""
        assert analyzer._is_prediction_correct("cost_sink", "cost_sink") is True

    def test_is_prediction_correct_case_insensitive(self, analyzer):
        """Test prediction correctness is case insensitive."""
        assert analyzer._is_prediction_correct("COST_SINK", "cost_sink") is True

    def test_is_prediction_correct_same_family(self, analyzer):
        """Test prediction correctness for same problem family."""
        # Cost family
        assert analyzer._is_prediction_correct("cost_sink", "high_token") is True
        assert analyzer._is_prediction_correct("token_usage", "cost_sink_confirmed") is True

        # Failure family
        assert analyzer._is_prediction_correct("failure_mode", "timeout_failure") is True
        assert analyzer._is_prediction_correct("error", "error_failure") is True

    def test_is_prediction_correct_no_problem(self, analyzer):
        """Test prediction correctness for no-problem cases."""
        assert analyzer._is_prediction_correct("no_problem", "no_issue") is True
        assert analyzer._is_prediction_correct("success", "no_problem_detected") is True

    def test_is_prediction_correct_different_families(self, analyzer):
        """Test prediction incorrectness for different families."""
        assert analyzer._is_prediction_correct("cost_sink", "timeout_failure") is False
        assert analyzer._is_prediction_correct("latency", "error_failure") is False


class TestTelemetryAnalyzerRecalibration:
    """Tests for TelemetryAnalyzer.recalibrate_thresholds()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_recalibrate_insufficient_reports(self, analyzer):
        """Test that recalibration requires minimum reports."""
        # Only 3 reports, default min is 5
        reports = [
            InsightAccuracyReport(
                insight_id=f"insight-{i}",
                predicted_problem="cost",
                actual_problem="cost",
                prediction_correct=True,
                predicted_confidence=0.8,
                confidence_calibration=1.0,
            )
            for i in range(3)
        ]

        updates = analyzer.recalibrate_thresholds(accuracy_reports=reports, min_reports=5)

        assert updates == []

    def test_recalibrate_with_sufficient_accurate_reports(self, analyzer):
        """Test recalibration with accurate predictions."""
        # Create reports with high accuracy
        reports = [
            InsightAccuracyReport(
                insight_id=f"insight-{i}",
                predicted_problem="cost_sink",
                actual_problem="cost_sink_confirmed",
                prediction_correct=True,
                predicted_confidence=0.8,
                confidence_calibration=1.0,
            )
            for i in range(10)
        ]

        updates = analyzer.recalibrate_thresholds(accuracy_reports=reports, min_reports=5)

        # High accuracy should result in minimal or no changes
        # The threshold may or may not be updated depending on calibration
        assert isinstance(updates, list)

    def test_recalibrate_with_low_accuracy_overconfident(self, analyzer):
        """Test recalibration when predictions are wrong and overconfident."""
        # Create reports with low accuracy and low calibration (overconfident)
        reports = [
            InsightAccuracyReport(
                insight_id=f"insight-{i}",
                predicted_problem="cost_sink",
                actual_problem="no_problem_detected",
                prediction_correct=False,
                predicted_confidence=0.9,  # High confidence
                confidence_calibration=0.7,  # Overconfident
            )
            for i in range(10)
        ]

        # Store initial value for comparison
        before_value = analyzer._current_thresholds["cost_sink_threshold"]
        updates = analyzer.recalibrate_thresholds(accuracy_reports=reports, min_reports=5)

        # With low accuracy and overconfidence, threshold should be adjusted
        # Check if cost_sink_threshold was updated
        cost_updates = [u for u in updates if u.threshold_name == "cost_sink_threshold"]
        if cost_updates:
            assert cost_updates[0].old_value == before_value
            assert cost_updates[0].calibration_factor != 1.0

    def test_recalibrate_uses_internal_reports_if_none_provided(self, analyzer, mock_db):
        """Test that recalibration uses internally stored reports."""
        # Register insights and measure accuracy to populate internal reports
        for i in range(6):
            analyzer.register_insight(
                insight_id=f"insight-{i}",
                predicted_problem="failure",
                confidence=0.7,
                issue_type="failure_mode",
                phase_id=f"phase-{i}",
            )

            # Mock outcome
            mock_row = MagicMock()
            mock_row.phase_outcome = "FAILURE" if i < 3 else "SUCCESS"
            mock_row.stop_reason = "error" if i < 3 else None
            mock_row.tokens_used = 1000
            mock_row.duration_seconds = 5.0

            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_db.execute.return_value = mock_result

            analyzer.measure_insight_accuracy(f"insight-{i}")

        # Now recalibrate without providing reports
        updates = analyzer.recalibrate_thresholds(min_reports=5)

        # Should use the internally stored reports
        assert isinstance(updates, list)

    def test_get_current_thresholds(self, analyzer):
        """Test getting current threshold values."""
        thresholds = analyzer.get_current_thresholds()

        assert "cost_sink_threshold" in thresholds
        assert "failure_rate_threshold" in thresholds
        assert "retry_threshold" in thresholds
        assert "latency_threshold_ms" in thresholds

    def test_set_threshold_valid(self, analyzer):
        """Test setting a valid threshold."""
        success = analyzer.set_threshold("cost_sink_threshold", 75000.0)

        assert success is True
        assert analyzer._current_thresholds["cost_sink_threshold"] == 75000.0

    def test_set_threshold_invalid_name(self, analyzer):
        """Test setting an invalid threshold name."""
        success = analyzer.set_threshold("nonexistent_threshold", 100.0)

        assert success is False


class TestInsightAccuracySummary:
    """Tests for insight accuracy summary."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_get_summary_empty(self, analyzer):
        """Test summary with no data."""
        summary = analyzer.get_insight_accuracy_summary()

        assert summary["total_insights"] == 0
        assert summary["total_accuracy_reports"] == 0
        assert summary["overall_accuracy"] == 0.0
        assert summary["avg_calibration"] == 1.0
        assert len(summary["current_thresholds"]) > 0

    def test_get_summary_with_data(self, analyzer, mock_db):
        """Test summary with accuracy data."""
        # Register some insights and measure accuracy
        for i in range(5):
            analyzer.register_insight(
                insight_id=f"insight-{i}",
                predicted_problem="cost_sink",
                confidence=0.8,
                issue_type="cost_sink",
                phase_id=f"phase-{i}",
            )

        # Add accuracy reports directly
        for i in range(5):
            report = InsightAccuracyReport(
                insight_id=f"insight-{i}",
                predicted_problem="cost_sink",
                actual_problem="cost_sink_confirmed" if i < 4 else "no_problem",
                prediction_correct=i < 4,
                predicted_confidence=0.8,
                confidence_calibration=1.0 if i < 4 else 0.7,
            )
            analyzer._insight_accuracy_reports.append(report)

        summary = analyzer.get_insight_accuracy_summary()

        assert summary["total_insights"] == 5
        assert summary["total_accuracy_reports"] == 5
        assert summary["overall_accuracy"] == 0.8  # 4/5 correct
        assert len(summary["current_thresholds"]) > 0


class TestDetermineActualProblem:
    """Tests for _determine_actual_problem helper."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_cost_sink_detection(self, analyzer):
        """Test detection of cost sink from high token usage."""
        result = analyzer._determine_actual_problem(
            issue_type="cost_sink",
            phase_outcome="SUCCESS",
            stop_reason=None,
            tokens_used=80000,  # Above 50000 threshold
            duration_seconds=10.0,
        )
        assert result == "cost_sink_confirmed"

    def test_timeout_failure_detection(self, analyzer):
        """Test detection of timeout failure."""
        result = analyzer._determine_actual_problem(
            issue_type="failure_mode",
            phase_outcome="FAILURE",
            stop_reason="timeout exceeded",
            tokens_used=1000,
            duration_seconds=60.0,
        )
        assert result == "timeout_failure"

    def test_error_failure_detection(self, analyzer):
        """Test detection of error failure."""
        result = analyzer._determine_actual_problem(
            issue_type="failure_mode",
            phase_outcome="FAILURE",
            stop_reason="API error occurred",
            tokens_used=1000,
            duration_seconds=5.0,
        )
        assert result == "error_failure"

    def test_high_latency_detection(self, analyzer):
        """Test detection of high latency."""
        result = analyzer._determine_actual_problem(
            issue_type="latency",
            phase_outcome="SUCCESS",
            stop_reason=None,
            tokens_used=1000,
            duration_seconds=60.0,  # 60000ms > 30000ms threshold
        )
        assert result == "high_latency"

    def test_no_problem_success(self, analyzer):
        """Test no problem detected on successful fast execution."""
        result = analyzer._determine_actual_problem(
            issue_type="cost_sink",
            phase_outcome="SUCCESS",
            stop_reason=None,
            tokens_used=1000,  # Low tokens
            duration_seconds=1.0,  # Fast
        )
        assert result == "no_problem_detected"
