"""Tests for calibration_reporter.py.

Tests cover:
- Report generation with coefficient diffs
- Confidence scoring based on sample size
- Markdown output formatting
- JSON serialization
- Edge cases (no changes, missing data)
"""

import json

import pytest

from autopack.calibration_reporter import (
    CalibrationReport,
    CalibrationReporter,
    CoefficientChange,
)


class TestCoefficientChange:
    """Test CoefficientChange dataclass."""

    def test_change_abs_positive(self):
        """Test absolute change calculation for increase."""
        change = CoefficientChange(
            key="test/key",
            old_value=1000.0,
            new_value=1200.0,
            change_pct=20.0,
            sample_count=10,
            confidence=0.8,
        )
        assert change.change_abs == 200.0

    def test_change_abs_negative(self):
        """Test absolute change calculation for decrease."""
        change = CoefficientChange(
            key="test/key",
            old_value=2000.0,
            new_value=1500.0,
            change_pct=-25.0,
            sample_count=15,
            confidence=0.9,
        )
        assert change.change_abs == -500.0


class TestCalibrationReport:
    """Test CalibrationReport dataclass."""

    def test_add_change(self):
        """Test adding changes to report."""
        report = CalibrationReport(version="v1", date="2025-01-01", sample_count=50)

        change = CoefficientChange(
            key="test/key",
            old_value=1000.0,
            new_value=1100.0,
            change_pct=10.0,
            sample_count=10,
            confidence=0.8,
        )

        report.add_change(change)
        assert len(report.changes) == 1
        assert report.changes[0].key == "test/key"

    def test_calculate_overall_confidence_empty(self):
        """Test overall confidence with no changes."""
        report = CalibrationReport(version="v1", date="2025-01-01", sample_count=0)

        report.calculate_overall_confidence()
        assert report.overall_confidence == 0.0

    def test_calculate_overall_confidence_weighted(self):
        """Test overall confidence weighted by sample count."""
        report = CalibrationReport(version="v1", date="2025-01-01", sample_count=30)

        # High confidence with many samples
        report.add_change(
            CoefficientChange(
                key="key1",
                old_value=1000.0,
                new_value=1100.0,
                change_pct=10.0,
                sample_count=20,
                confidence=0.9,
            )
        )

        # Low confidence with few samples
        report.add_change(
            CoefficientChange(
                key="key2",
                old_value=500.0,
                new_value=600.0,
                change_pct=20.0,
                sample_count=10,
                confidence=0.5,
            )
        )

        report.calculate_overall_confidence()

        # Should be weighted toward high confidence (more samples)
        # (0.9 * 20 + 0.5 * 10) / 30 = (18 + 5) / 30 = 0.767
        assert 0.76 < report.overall_confidence < 0.77


class TestCalibrationReporter:
    """Test CalibrationReporter class."""

    @pytest.fixture
    def reporter(self, tmp_path):
        """Create reporter with temp output dir."""
        return CalibrationReporter(output_dir=tmp_path)

    @pytest.fixture
    def sample_data(self):
        """Sample calibration data."""
        return {
            "old_coefficients": {
                "implementation/low": 2000.0,
                "implementation/medium": 3000.0,
                "testing/low": 1500.0,
            },
            "new_coefficients": {
                "implementation/low": 1120.0,
                "implementation/medium": 1860.0,
                "testing/low": 915.0,
            },
            "sample_counts": {
                "implementation/low": 8,
                "implementation/medium": 12,
                "testing/low": 5,
            },
        }

    def test_generate_report(self, reporter, sample_data):
        """Test report generation."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
            notes=["Test calibration"],
        )

        assert report.version == "v5-step1"
        assert report.sample_count == 25  # 8 + 12 + 5
        assert len(report.changes) == 3
        assert len(report.notes) == 1

    def test_generate_report_calculates_changes(self, reporter, sample_data):
        """Test that changes are calculated correctly."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        # Find implementation/low change
        impl_low = next(c for c in report.changes if c.key == "implementation/low")

        assert impl_low.old_value == 2000.0
        assert impl_low.new_value == 1120.0
        assert impl_low.change_abs == -880.0
        assert impl_low.change_pct == pytest.approx(-44.0, rel=0.1)

    def test_calculate_confidence_high_samples(self, reporter):
        """Test confidence with high sample count."""
        confidence = reporter._calculate_confidence(sample_count=25, change_magnitude=20.0)
        assert confidence >= 0.8

    def test_calculate_confidence_low_samples(self, reporter):
        """Test confidence with low sample count."""
        confidence = reporter._calculate_confidence(sample_count=3, change_magnitude=20.0)
        assert confidence < 0.5

    def test_calculate_confidence_large_change(self, reporter):
        """Test confidence penalty for large changes."""
        # Same samples, different change magnitudes
        small_change = reporter._calculate_confidence(sample_count=15, change_magnitude=10.0)
        large_change = reporter._calculate_confidence(sample_count=15, change_magnitude=60.0)

        assert small_change > large_change

    def test_to_markdown_basic(self, reporter, sample_data):
        """Test markdown generation."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        markdown = reporter.to_markdown(report)

        # Check header
        assert "# Calibration Report: v5-step1" in markdown
        assert "**Total Samples:** 25" in markdown

        # Check table
        assert "| Coefficient | Old Value | New Value |" in markdown
        assert "implementation/low" in markdown
        assert "implementation/medium" in markdown
        assert "testing/low" in markdown

    def test_to_markdown_with_notes(self, reporter, sample_data):
        """Test markdown with notes section."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
            notes=["Note 1", "Note 2"],
        )

        markdown = reporter.to_markdown(report)

        assert "## Notes" in markdown
        assert "- Note 1" in markdown
        assert "- Note 2" in markdown

    def test_to_markdown_confidence_breakdown(self, reporter, sample_data):
        """Test markdown includes confidence breakdown."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        markdown = reporter.to_markdown(report)

        assert "## Confidence Breakdown" in markdown
        assert "High Confidence" in markdown
        assert "Medium Confidence" in markdown
        assert "Low Confidence" in markdown

    def test_save_report(self, reporter, sample_data, tmp_path):
        """Test saving report to file."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        output_path = reporter.save_report(report)

        assert output_path.exists()
        assert output_path.name == "calibration_v5-step1.md"

        content = output_path.read_text(encoding="utf-8")
        assert "# Calibration Report: v5-step1" in content

    def test_save_report_custom_filename(self, reporter, sample_data, tmp_path):
        """Test saving report with custom filename."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        output_path = reporter.save_report(report, filename="custom_report.md")

        assert output_path.exists()
        assert output_path.name == "custom_report.md"

    def test_save_json(self, reporter, sample_data, tmp_path):
        """Test saving report as JSON."""
        report = reporter.generate_report(
            version="v5-step1",
            old_coefficients=sample_data["old_coefficients"],
            new_coefficients=sample_data["new_coefficients"],
            sample_counts=sample_data["sample_counts"],
        )

        output_path = reporter.save_json(report)

        assert output_path.exists()
        assert output_path.name == "calibration_v5-step1.json"

        # Verify JSON structure
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["version"] == "v5-step1"
        assert data["sample_count"] == 25
        assert len(data["changes"]) == 3

    def test_no_changes(self, reporter):
        """Test report with no coefficient changes."""
        report = reporter.generate_report(
            version="v1",
            old_coefficients={"key1": 1000.0},
            new_coefficients={"key1": 1000.0},  # Same value
            sample_counts={"key1": 10},
        )

        assert len(report.changes) == 0
        assert report.overall_confidence == 0.0

    def test_new_coefficient(self, reporter):
        """Test report with new coefficient (not in old)."""
        report = reporter.generate_report(
            version="v1",
            old_coefficients={},
            new_coefficients={"new_key": 1000.0},
            sample_counts={"new_key": 10},
        )

        assert len(report.changes) == 1
        assert report.changes[0].old_value == 0.0
        assert report.changes[0].new_value == 1000.0

    def test_removed_coefficient(self, reporter):
        """Test report with removed coefficient (not in new)."""
        report = reporter.generate_report(
            version="v1",
            old_coefficients={"old_key": 1000.0},
            new_coefficients={},
            sample_counts={"old_key": 10},
        )

        assert len(report.changes) == 1
        assert report.changes[0].old_value == 1000.0
        assert report.changes[0].new_value == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
