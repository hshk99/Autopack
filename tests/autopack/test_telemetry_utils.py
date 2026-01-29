"""Tests for telemetry_utils.py.

Covers:
- Sample filtering (success, category, complexity, token ranges)
- SMAPE calculation (edge cases, symmetry)
- Waste ratio calculation
- Underestimation detection
- Statistics calculation (mean, median, percentiles)
- Underestimation and truncation rates
- Sample validation
- Grouping by category and complexity

NOTE: Originally an extended/aspirational test suite, now graduated to core suite
as telemetry utility enhancements have been implemented (42/43 tests passing).
"""

import pytest

from autopack.telemetry_utils import (
    calculate_smape,
    calculate_statistics,
    calculate_truncation_rate,
    calculate_underestimation_rate,
    calculate_waste_ratio,
    detect_underestimation,
    filter_samples,
    group_by_category,
    group_by_complexity,
    validate_sample,
)

# GRADUATED: Removed xfail marker - enhancements have been implemented (BUILD-146 Phase A P15)


class TestFilterSamples:
    """Test sample filtering functionality."""

    @pytest.fixture
    def sample_data(self):
        """Create sample telemetry data."""
        return [
            {
                "predicted_output_tokens": 1000,
                "actual_output_tokens": 900,
                "success": True,
                "category": "implementation",
                "complexity": "low",
            },
            {
                "predicted_output_tokens": 2000,
                "actual_output_tokens": 1800,
                "success": True,
                "category": "implementation",
                "complexity": "medium",
            },
            {
                "predicted_output_tokens": 500,
                "actual_output_tokens": 120,
                "success": False,
                "category": "implementation",
                "complexity": "low",
            },
            {
                "predicted_output_tokens": 1500,
                "actual_output_tokens": 1400,
                "success": True,
                "category": "testing",
                "complexity": "low",
            },
            {
                "predicted_output_tokens": 3000,
                "actual_output_tokens": 2800,
                "success": True,
                "category": "implementation",
                "complexity": "high",
            },
        ]

    def test_filter_success_only(self, sample_data):
        """Test filtering for successful samples only."""
        filtered = filter_samples(sample_data, success_only=True)
        assert len(filtered) == 4
        assert all(s["success"] for s in filtered)

    def test_filter_by_category(self, sample_data):
        """Test filtering by category."""
        filtered = filter_samples(sample_data, category="implementation")
        assert len(filtered) == 4
        assert all(s["category"] == "implementation" for s in filtered)

    def test_filter_by_complexity(self, sample_data):
        """Test filtering by complexity."""
        filtered = filter_samples(sample_data, complexity="low")
        assert len(filtered) == 3
        assert all(s["complexity"] == "low" for s in filtered)

    def test_filter_min_tokens(self, sample_data):
        """Test filtering by minimum actual tokens."""
        filtered = filter_samples(sample_data, min_actual_tokens=500)
        assert len(filtered) == 4
        assert all(s["actual_output_tokens"] >= 500 for s in filtered)

    def test_filter_max_tokens(self, sample_data):
        """Test filtering by maximum actual tokens."""
        filtered = filter_samples(sample_data, max_actual_tokens=2000)
        assert len(filtered) == 4
        assert all(s["actual_output_tokens"] <= 2000 for s in filtered)

    def test_filter_combined(self, sample_data):
        """Test combining multiple filters."""
        filtered = filter_samples(
            sample_data, success_only=True, category="implementation", complexity="low"
        )
        assert len(filtered) == 1
        assert filtered[0]["success"]
        assert filtered[0]["category"] == "implementation"
        assert filtered[0]["complexity"] == "low"

    def test_filter_empty_result(self, sample_data):
        """Test filter that returns no results."""
        filtered = filter_samples(sample_data, category="nonexistent")
        assert len(filtered) == 0


class TestCalculateSMAPE:
    """Test SMAPE calculation."""

    def test_perfect_prediction(self):
        """Test SMAPE for perfect prediction."""
        smape = calculate_smape(100, 100)
        assert smape == 0.0

    def test_underestimation(self):
        """Test SMAPE for underestimation."""
        smape = calculate_smape(50, 100)
        assert 66.0 < smape < 67.0  # ~66.67%

    def test_overestimation(self):
        """Test SMAPE for overestimation."""
        smape = calculate_smape(100, 50)
        assert 66.0 < smape < 67.0  # ~66.67%

    def test_symmetry(self):
        """Test that SMAPE is symmetric."""
        smape1 = calculate_smape(100, 200)
        smape2 = calculate_smape(200, 100)
        assert abs(smape1 - smape2) < 0.01

    def test_zero_actual(self):
        """Test SMAPE with zero actual value."""
        smape = calculate_smape(100, 0)
        assert smape > 0  # Should use epsilon to avoid division by zero

    def test_negative_values(self):
        """Test SMAPE rejects negative values."""
        with pytest.raises(ValueError):
            calculate_smape(-100, 100)
        with pytest.raises(ValueError):
            calculate_smape(100, -100)


class TestCalculateWasteRatio:
    """Test waste ratio calculation."""

    def test_perfect_prediction(self):
        """Test waste ratio for perfect prediction."""
        ratio = calculate_waste_ratio(100, 100)
        assert ratio == 1.0

    def test_overestimation(self):
        """Test waste ratio for overestimation."""
        ratio = calculate_waste_ratio(200, 100)
        assert ratio == 2.0

    def test_underestimation(self):
        """Test waste ratio for underestimation."""
        ratio = calculate_waste_ratio(50, 100)
        assert ratio == 0.5

    def test_zero_actual(self):
        """Test waste ratio with zero actual value."""
        ratio = calculate_waste_ratio(100, 0)
        assert ratio > 0  # Should use epsilon

    def test_negative_values(self):
        """Test waste ratio rejects negative values."""
        with pytest.raises(ValueError):
            calculate_waste_ratio(-100, 100)
        with pytest.raises(ValueError):
            calculate_waste_ratio(100, -100)


class TestDetectUnderestimation:
    """Test underestimation detection."""

    def test_no_underestimation(self):
        """Test when prediction is accurate."""
        assert not detect_underestimation(100, 100)

    def test_underestimation(self):
        """Test when prediction underestimates."""
        assert detect_underestimation(90, 100)

    def test_overestimation(self):
        """Test when prediction overestimates."""
        assert not detect_underestimation(110, 100)

    def test_tolerance(self):
        """Test tolerance parameter."""
        # 10% underestimation
        assert detect_underestimation(90, 100, tolerance=1.0)
        assert not detect_underestimation(91, 100, tolerance=1.1)

    def test_invalid_tolerance(self):
        """Test invalid tolerance value."""
        with pytest.raises(ValueError):
            detect_underestimation(100, 100, tolerance=0.5)


class TestCalculateStatistics:
    """Test statistics calculation."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for statistics."""
        return [
            {"predicted_output_tokens": 1000, "actual_output_tokens": 900},
            {"predicted_output_tokens": 2000, "actual_output_tokens": 1800},
            {"predicted_output_tokens": 1500, "actual_output_tokens": 1400},
            {"predicted_output_tokens": 3000, "actual_output_tokens": 2800},
            {"predicted_output_tokens": 500, "actual_output_tokens": 450},
        ]

    def test_smape_statistics(self, sample_data):
        """Test SMAPE statistics calculation."""
        stats = calculate_statistics(sample_data, metric="smape")
        assert stats["count"] == 5
        assert stats["mean"] > 0
        assert stats["median"] > 0
        assert stats["min"] >= 0
        assert stats["max"] >= stats["mean"]

    def test_waste_ratio_statistics(self, sample_data):
        """Test waste ratio statistics calculation."""
        stats = calculate_statistics(sample_data, metric="waste_ratio")
        assert stats["count"] == 5
        assert stats["mean"] > 1.0  # All samples overestimate
        assert stats["median"] > 1.0

    def test_actual_tokens_statistics(self, sample_data):
        """Test actual tokens statistics."""
        stats = calculate_statistics(sample_data, metric="actual_tokens")
        assert stats["count"] == 5
        assert stats["min"] == 450
        assert stats["max"] == 2800

    def test_empty_samples(self):
        """Test statistics with empty sample list."""
        stats = calculate_statistics([], metric="smape")
        assert stats["count"] == 0
        assert stats["mean"] == 0.0

    def test_unknown_metric(self, sample_data):
        """Test unknown metric raises error."""
        with pytest.raises(ValueError):
            calculate_statistics(sample_data, metric="unknown")


class TestCalculateUnderestimationRate:
    """Test underestimation rate calculation."""

    def test_no_underestimation(self):
        """Test when no samples underestimate."""
        samples = [
            {"predicted_output_tokens": 1000, "actual_output_tokens": 900},
            {"predicted_output_tokens": 2000, "actual_output_tokens": 1800},
        ]
        rate = calculate_underestimation_rate(samples)
        assert rate == 0.0

    def test_all_underestimation(self):
        """Test when all samples underestimate."""
        samples = [
            {"predicted_output_tokens": 900, "actual_output_tokens": 1000},
            {"predicted_output_tokens": 1800, "actual_output_tokens": 2000},
        ]
        rate = calculate_underestimation_rate(samples)
        assert rate == 100.0

    def test_partial_underestimation(self):
        """Test when some samples underestimate."""
        samples = [
            {"predicted_output_tokens": 900, "actual_output_tokens": 1000},
            {"predicted_output_tokens": 2000, "actual_output_tokens": 1800},
        ]
        rate = calculate_underestimation_rate(samples)
        assert rate == 50.0

    def test_empty_samples(self):
        """Test with empty sample list."""
        rate = calculate_underestimation_rate([])
        assert rate == 0.0


class TestCalculateTruncationRate:
    """Test truncation rate calculation."""

    def test_no_truncation(self):
        """Test when no samples are truncated."""
        samples = [{"truncated": False}, {"truncated": False}]
        rate = calculate_truncation_rate(samples)
        assert rate == 0.0

    def test_all_truncated(self):
        """Test when all samples are truncated."""
        samples = [{"truncated": True}, {"truncated": True}]
        rate = calculate_truncation_rate(samples)
        assert rate == 100.0

    def test_partial_truncation(self):
        """Test when some samples are truncated."""
        samples = [{"truncated": True}, {"truncated": False}]
        rate = calculate_truncation_rate(samples)
        assert rate == 50.0

    def test_empty_samples(self):
        """Test with empty sample list."""
        rate = calculate_truncation_rate([])
        assert rate == 0.0


class TestValidateSample:
    """Test sample validation."""

    def test_valid_sample(self):
        """Test validation of valid sample."""
        sample = {
            "predicted_output_tokens": 1000,
            "actual_output_tokens": 900,
            "category": "implementation",
            "complexity": "low",
        }
        is_valid, error = validate_sample(sample)
        assert is_valid
        assert error is None

    def test_missing_field(self):
        """Test validation with missing field."""
        sample = {
            "predicted_output_tokens": 1000,
            "category": "implementation",
            "complexity": "low",
        }
        is_valid, error = validate_sample(sample)
        assert not is_valid
        assert "actual_output_tokens" in error

    def test_invalid_tokens(self):
        """Test validation with invalid token values."""
        sample = {
            "predicted_output_tokens": -100,
            "actual_output_tokens": 900,
            "category": "implementation",
            "complexity": "low",
        }
        is_valid, error = validate_sample(sample)
        assert not is_valid
        assert "predicted_output_tokens" in error

    def test_invalid_category(self):
        """Test validation with invalid category."""
        sample = {
            "predicted_output_tokens": 1000,
            "actual_output_tokens": 900,
            "category": "",
            "complexity": "low",
        }
        is_valid, error = validate_sample(sample)
        assert not is_valid
        assert "category" in error


class TestGrouping:
    """Test grouping functions."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for grouping."""
        return [
            {"category": "implementation", "complexity": "low"},
            {"category": "implementation", "complexity": "medium"},
            {"category": "testing", "complexity": "low"},
            {"category": "testing", "complexity": "high"},
        ]

    def test_group_by_category(self, sample_data):
        """Test grouping by category."""
        groups = group_by_category(sample_data)
        assert len(groups) == 2
        assert len(groups["implementation"]) == 2
        assert len(groups["testing"]) == 2

    def test_group_by_complexity(self, sample_data):
        """Test grouping by complexity."""
        groups = group_by_complexity(sample_data)
        assert len(groups) == 3
        assert len(groups["low"]) == 2
        assert len(groups["medium"]) == 1
        assert len(groups["high"]) == 1

    def test_empty_samples(self):
        """Test grouping with empty sample list."""
        groups = group_by_category([])
        assert len(groups) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
