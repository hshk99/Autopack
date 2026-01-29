"""Tests for performance optimization detector."""

from unittest.mock import MagicMock

import pytest

from feedback.optimization_detector import OptimizationDetector, OptimizationSuggestion


@pytest.fixture
def mock_metrics_db():
    """Create a mock MetricsDatabase instance."""
    return MagicMock()


@pytest.fixture
def detector(mock_metrics_db):
    """Create an OptimizationDetector instance with mock database."""
    return OptimizationDetector(mock_metrics_db)


class TestOptimizationSuggestion:
    """Tests for OptimizationSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test that suggestion can be created with all fields."""
        suggestion = OptimizationSuggestion(
            category="test_category",
            severity="high",
            description="Test description",
            current_value=0.5,
            threshold=0.7,
            estimated_impact="Test impact",
            implementation_hint="Test hint",
        )

        assert suggestion.category == "test_category"
        assert suggestion.severity == "high"
        assert suggestion.description == "Test description"
        assert suggestion.current_value == 0.5
        assert suggestion.threshold == 0.7
        assert suggestion.estimated_impact == "Test impact"
        assert suggestion.implementation_hint == "Test hint"


class TestOptimizationDetector:
    """Tests for OptimizationDetector class."""

    def test_init_stores_db(self, mock_metrics_db, detector):
        """Test that initialization stores database reference."""
        assert detector.db is mock_metrics_db

    def test_detect_all_no_metrics(self, mock_metrics_db, detector):
        """Test detect_all returns empty list when no metrics exist."""
        mock_metrics_db.get_daily_metrics.return_value = []

        suggestions = detector.detect_all()

        assert suggestions == []

    def test_detect_all_healthy_metrics(self, mock_metrics_db, detector):
        """Test detect_all returns empty list when metrics are healthy."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {
                "slot_utilization_avg": 0.85,
                "ci_failure_rate": 0.05,
                "tasks_completed": 10,
                "stagnation_count": 0,
                "pr_merge_time_avg": 3600,  # 1 hour
            },
        ]

        suggestions = detector.detect_all()

        assert suggestions == []

    def test_detect_all_sorted_by_severity(self, mock_metrics_db, detector):
        """Test that suggestions are sorted by severity (critical first)."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {
                "slot_utilization_avg": 0.3,  # Below 0.5 = high severity
                "ci_failure_rate": 0.30,  # Above 0.25 = high severity
                "tasks_completed": 10,
                "stagnation_count": 2,  # 20% rate > 10% threshold = medium
                "pr_merge_time_avg": 5 * 3600,  # 5 hours = medium
            },
        ]

        suggestions = detector.detect_all()

        # Should be sorted: high, high, medium, medium
        assert len(suggestions) == 4
        assert suggestions[0].severity == "high"
        assert suggestions[1].severity == "high"
        assert suggestions[2].severity == "medium"
        assert suggestions[3].severity == "medium"


class TestSlotUtilizationCheck:
    """Tests for slot utilization detection."""

    def test_low_slot_utilization_medium_severity(self, mock_metrics_db, detector):
        """Test that moderate under-utilization returns medium severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"slot_utilization_avg": 0.6},  # Above 0.5 but below 0.7
        ]

        suggestions = detector._check_slot_utilization()

        assert len(suggestions) == 1
        assert suggestions[0].category == "slot_utilization"
        assert suggestions[0].severity == "medium"
        assert suggestions[0].current_value == 0.6
        assert suggestions[0].threshold == 0.7

    def test_low_slot_utilization_high_severity(self, mock_metrics_db, detector):
        """Test that severe under-utilization returns high severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"slot_utilization_avg": 0.4},  # Below 0.5
        ]

        suggestions = detector._check_slot_utilization()

        assert len(suggestions) == 1
        assert suggestions[0].severity == "high"

    def test_healthy_slot_utilization(self, mock_metrics_db, detector):
        """Test that healthy utilization returns no suggestions."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"slot_utilization_avg": 0.8},
        ]

        suggestions = detector._check_slot_utilization()

        assert suggestions == []

    def test_slot_utilization_averages_multiple_days(self, mock_metrics_db, detector):
        """Test that utilization is averaged across multiple days."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"slot_utilization_avg": 0.6},
            {"slot_utilization_avg": 0.8},
        ]

        suggestions = detector._check_slot_utilization()

        # Average is 0.7, which equals threshold, so no suggestion
        assert suggestions == []


class TestCIEfficiencyCheck:
    """Tests for CI efficiency detection."""

    def test_high_ci_failure_rate_medium_severity(self, mock_metrics_db, detector):
        """Test that moderate failure rate returns medium severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"ci_failure_rate": 0.20},  # Above 0.15 but below 0.25
        ]

        suggestions = detector._check_ci_efficiency()

        assert len(suggestions) == 1
        assert suggestions[0].category == "ci_efficiency"
        assert suggestions[0].severity == "medium"
        assert suggestions[0].current_value == 0.20
        assert suggestions[0].threshold == 0.15

    def test_high_ci_failure_rate_high_severity(self, mock_metrics_db, detector):
        """Test that severe failure rate returns high severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"ci_failure_rate": 0.30},  # Above 0.25
        ]

        suggestions = detector._check_ci_efficiency()

        assert len(suggestions) == 1
        assert suggestions[0].severity == "high"

    def test_healthy_ci_failure_rate(self, mock_metrics_db, detector):
        """Test that healthy failure rate returns no suggestions."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"ci_failure_rate": 0.10},
        ]

        suggestions = detector._check_ci_efficiency()

        assert suggestions == []


class TestStagnationPatternCheck:
    """Tests for stagnation pattern detection."""

    def test_high_stagnation_rate_medium_severity(self, mock_metrics_db, detector):
        """Test that moderate stagnation returns medium severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 10, "stagnation_count": 2},  # 20% but above 10%
        ]

        suggestions = detector._check_stagnation_patterns()

        assert len(suggestions) == 1
        assert suggestions[0].category == "stagnation"
        assert suggestions[0].severity == "medium"
        assert suggestions[0].current_value == 0.2
        assert suggestions[0].threshold == 0.1

    def test_high_stagnation_rate_high_severity(self, mock_metrics_db, detector):
        """Test that severe stagnation returns high severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 10, "stagnation_count": 3},  # 30% > 20%
        ]

        suggestions = detector._check_stagnation_patterns()

        assert len(suggestions) == 1
        assert suggestions[0].severity == "high"

    def test_healthy_stagnation_rate(self, mock_metrics_db, detector):
        """Test that healthy stagnation rate returns no suggestions."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 100, "stagnation_count": 5},  # 5% < 10%
        ]

        suggestions = detector._check_stagnation_patterns()

        assert suggestions == []

    def test_zero_tasks_no_suggestion(self, mock_metrics_db, detector):
        """Test that zero tasks returns no suggestions (avoids division by zero)."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 0, "stagnation_count": 0},
        ]

        suggestions = detector._check_stagnation_patterns()

        assert suggestions == []


class TestPRMergeTimeCheck:
    """Tests for PR merge time detection."""

    def test_slow_merge_time(self, mock_metrics_db, detector):
        """Test that slow merge times return medium severity."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"pr_merge_time_avg": 6 * 3600},  # 6 hours > 4 hours
        ]

        suggestions = detector._check_pr_merge_times()

        assert len(suggestions) == 1
        assert suggestions[0].category == "pr_merge_time"
        assert suggestions[0].severity == "medium"
        assert suggestions[0].current_value == 6.0
        assert suggestions[0].threshold == 4

    def test_healthy_merge_time(self, mock_metrics_db, detector):
        """Test that healthy merge time returns no suggestions."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"pr_merge_time_avg": 2 * 3600},  # 2 hours < 4 hours
        ]

        suggestions = detector._check_pr_merge_times()

        assert suggestions == []


class TestGetSummary:
    """Tests for summary generation."""

    def test_summary_no_suggestions(self, mock_metrics_db, detector):
        """Test summary when no optimization opportunities exist."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {
                "slot_utilization_avg": 0.9,
                "ci_failure_rate": 0.05,
                "tasks_completed": 100,
                "stagnation_count": 5,
                "pr_merge_time_avg": 3600,
            },
        ]

        summary = detector.get_summary()

        assert "No optimization opportunities detected" in summary

    def test_summary_with_suggestions(self, mock_metrics_db, detector):
        """Test summary when optimization opportunities exist."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {
                "slot_utilization_avg": 0.4,
                "ci_failure_rate": 0.30,
                "tasks_completed": 10,
                "stagnation_count": 3,
                "pr_merge_time_avg": 6 * 3600,
            },
        ]

        summary = detector.get_summary()

        assert "Found" in summary
        assert "optimization opportunities" in summary
        assert "[HIGH]" in summary
        assert "[MEDIUM]" in summary
        assert "slot_utilization" in summary
        assert "ci_efficiency" in summary
        assert "stagnation" in summary
        assert "pr_merge_time" in summary


class TestDefaultsForMissingMetricFields:
    """Tests for handling missing metric fields."""

    def test_missing_slot_utilization_defaults_to_zero(self, mock_metrics_db, detector):
        """Test that missing slot_utilization_avg defaults to zero."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {},  # No fields
        ]

        suggestions = detector._check_slot_utilization()

        # 0 < 0.7 threshold, so should return a suggestion
        assert len(suggestions) == 1
        assert suggestions[0].current_value == 0.0

    def test_missing_ci_failure_rate_defaults_to_zero(self, mock_metrics_db, detector):
        """Test that missing ci_failure_rate defaults to zero."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {},  # No fields
        ]

        suggestions = detector._check_ci_efficiency()

        # 0 < 0.15 threshold, so no suggestion
        assert suggestions == []

    def test_missing_stagnation_fields_defaults_to_zero(self, mock_metrics_db, detector):
        """Test that missing stagnation fields default to zero."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {},  # No fields
        ]

        suggestions = detector._check_stagnation_patterns()

        # No tasks = no suggestion
        assert suggestions == []

    def test_missing_pr_merge_time_defaults_to_zero(self, mock_metrics_db, detector):
        """Test that missing pr_merge_time_avg defaults to zero."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {},  # No fields
        ]

        suggestions = detector._check_pr_merge_times()

        # 0 < threshold, so no suggestion
        assert suggestions == []
