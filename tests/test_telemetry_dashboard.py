"""Tests for TelemetryDashboard."""

import json

import pytest
from pathlib import Path

from scripts.telemetry_dashboard import TelemetryDashboard


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for test files."""
    return tmp_path


@pytest.fixture
def sample_summary():
    """Sample telemetry summary data."""
    return {
        "version": "1.0.0",
        "generated_at": "2026-01-25T12:00:00",
        "metrics": {
            "timestamp": "2026-01-25T12:00:00",
            "success_rate": 85.5,
            "avg_completion_time": 150.25,
            "failure_categories": {
                "timeout": 3,
                "build_error": 2,
                "out_of_memory": 1,
            },
            "escalation_frequency": 25.0,
            "totals": {
                "total_operations": 20,
                "successful_operations": 17,
                "failed_operations": 6,
                "escalated_operations": 5,
            },
        },
        "sources_summary": {
            "nudge_state": {"loaded": True, "entry_count": 3},
            "ci_retry_state": {"loaded": True, "entry_count": 5},
            "slot_history": {"loaded": True, "entry_count": 10},
        },
    }


@pytest.fixture
def sample_summary_low_success():
    """Sample summary with low success rate for recommendation testing."""
    return {
        "version": "1.0.0",
        "generated_at": "2026-01-25T12:00:00",
        "metrics": {
            "success_rate": 55.0,
            "avg_completion_time": 450.0,
            "failure_categories": {
                "timeout": 10,
                "build_error": 2,
            },
            "escalation_frequency": 45.0,
            "totals": {
                "total_operations": 20,
                "successful_operations": 11,
                "failed_operations": 12,
                "escalated_operations": 9,
            },
        },
        "sources_summary": {},
    }


@pytest.fixture
def summary_file(temp_dir, sample_summary):
    """Create a summary file in the temp directory."""
    summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
    summary_path.write_text(json.dumps(sample_summary))
    return summary_path


@pytest.fixture
def summary_file_low_success(temp_dir, sample_summary_low_success):
    """Create a summary file with low success rate."""
    summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
    summary_path.write_text(json.dumps(sample_summary_low_success))
    return summary_path


class TestTelemetryDashboardInit:
    """Tests for TelemetryDashboard initialization."""

    def test_init_with_path(self, temp_dir):
        """Test dashboard initializes with summary path."""
        summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
        dashboard = TelemetryDashboard(summary_path)
        assert dashboard.summary_path == summary_path

    def test_init_with_string_path(self, temp_dir):
        """Test dashboard accepts string paths."""
        summary_path = str(temp_dir / "TELEMETRY_SUMMARY.json")
        dashboard = TelemetryDashboard(summary_path)
        assert dashboard.summary_path == Path(summary_path)


class TestLoadSummary:
    """Tests for _load_summary() method."""

    def test_load_summary_success(self, summary_file, sample_summary):
        """Test loading a valid summary file."""
        dashboard = TelemetryDashboard(summary_file)
        result = dashboard._load_summary()

        assert result["version"] == "1.0.0"
        assert result["metrics"]["success_rate"] == 85.5
        assert "totals" in result["metrics"]

    def test_load_summary_file_not_found(self, temp_dir):
        """Test loading a non-existent file raises error."""
        dashboard = TelemetryDashboard(temp_dir / "missing.json")

        with pytest.raises(FileNotFoundError):
            dashboard._load_summary()

    def test_load_summary_invalid_json(self, temp_dir):
        """Test loading invalid JSON raises error."""
        summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
        summary_path.write_text("{ invalid json }")

        dashboard = TelemetryDashboard(summary_path)

        with pytest.raises(json.JSONDecodeError):
            dashboard._load_summary()


class TestGenerateReport:
    """Tests for generate_report() method."""

    def test_generate_report_contains_header(self, summary_file):
        """Test report contains the main header."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "# Telemetry Report" in report

    def test_generate_report_contains_overview(self, summary_file):
        """Test report contains overview section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Overview" in report
        assert "**Generated**:" in report
        assert "**Total Operations**:" in report
        assert "**Overall Success Rate**:" in report

    def test_generate_report_contains_success_rates(self, summary_file):
        """Test report contains success rates section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Success Rates by Category" in report
        assert "| Category |" in report

    def test_generate_report_contains_completion_times(self, summary_file):
        """Test report contains completion times section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Completion Times" in report
        assert "Average Completion Time" in report

    def test_generate_report_contains_failure_categories(self, summary_file):
        """Test report contains failure categories section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Failure Categories" in report
        assert "timeout" in report
        assert "build_error" in report

    def test_generate_report_contains_escalation_trends(self, summary_file):
        """Test report contains escalation trends section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Escalation Trends" in report
        assert "Total Escalations" in report
        assert "Escalation Rate" in report

    def test_generate_report_contains_recommendations(self, summary_file):
        """Test report contains recommendations section."""
        dashboard = TelemetryDashboard(summary_file)
        report = dashboard.generate_report()

        assert "## Recommendations" in report

    def test_generate_report_low_success_recommendations(self, summary_file_low_success):
        """Test report generates appropriate recommendations for low success rate."""
        dashboard = TelemetryDashboard(summary_file_low_success)
        report = dashboard.generate_report()

        assert "Low Success Rate" in report
        assert "High Escalation Frequency" in report
        assert "Timeout Issues" in report
        assert "Long Completion Times" in report


class TestSaveReport:
    """Tests for save_report() method."""

    def test_save_report(self, summary_file, temp_dir):
        """Test saving report to file."""
        output_path = temp_dir / "TELEMETRY_REPORT.md"

        dashboard = TelemetryDashboard(summary_file)
        dashboard.save_report(output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "# Telemetry Report" in content

    def test_save_report_creates_file(self, summary_file, temp_dir):
        """Test save_report creates the output file."""
        output_path = temp_dir / "output" / "report.md"
        output_path.parent.mkdir(parents=True)

        dashboard = TelemetryDashboard(summary_file)
        dashboard.save_report(output_path)

        assert output_path.exists()

    def test_save_report_overwrites_existing(self, summary_file, temp_dir):
        """Test save_report overwrites existing file."""
        output_path = temp_dir / "TELEMETRY_REPORT.md"
        output_path.write_text("old content")

        dashboard = TelemetryDashboard(summary_file)
        dashboard.save_report(output_path)

        content = output_path.read_text()
        assert "old content" not in content
        assert "# Telemetry Report" in content


class TestFormatHelpers:
    """Tests for formatting helper methods."""

    def test_format_percentage(self, summary_file):
        """Test percentage formatting."""
        dashboard = TelemetryDashboard(summary_file)

        assert dashboard._format_percentage(85.5) == "85.5%"
        assert dashboard._format_percentage(0) == "0.0%"
        assert dashboard._format_percentage(100) == "100.0%"

    def test_format_time_seconds(self, summary_file):
        """Test time formatting for seconds."""
        dashboard = TelemetryDashboard(summary_file)

        assert dashboard._format_time(30) == "30.0s"
        assert dashboard._format_time(59.9) == "59.9s"

    def test_format_time_minutes(self, summary_file):
        """Test time formatting for minutes."""
        dashboard = TelemetryDashboard(summary_file)

        assert dashboard._format_time(60) == "1.0m"
        assert dashboard._format_time(150) == "2.5m"

    def test_format_time_hours(self, summary_file):
        """Test time formatting for hours."""
        dashboard = TelemetryDashboard(summary_file)

        assert dashboard._format_time(3600) == "1.0h"
        assert dashboard._format_time(7200) == "2.0h"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_failure_categories(self, temp_dir):
        """Test handling of empty failure categories."""
        summary = {
            "version": "1.0.0",
            "generated_at": "2026-01-25T12:00:00",
            "metrics": {
                "success_rate": 100.0,
                "avg_completion_time": 50.0,
                "failure_categories": {},
                "escalation_frequency": 0.0,
                "totals": {
                    "total_operations": 10,
                    "successful_operations": 10,
                    "failed_operations": 0,
                    "escalated_operations": 0,
                },
            },
            "sources_summary": {},
        }
        summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
        summary_path.write_text(json.dumps(summary))

        dashboard = TelemetryDashboard(summary_path)
        report = dashboard.generate_report()

        assert "No failures recorded" in report

    def test_missing_metrics(self, temp_dir):
        """Test handling of missing metrics gracefully."""
        summary = {
            "version": "1.0.0",
            "generated_at": "2026-01-25T12:00:00",
            "metrics": {},
            "sources_summary": {},
        }
        summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
        summary_path.write_text(json.dumps(summary))

        dashboard = TelemetryDashboard(summary_path)
        report = dashboard.generate_report()

        # Should not crash, should use defaults
        assert "# Telemetry Report" in report
        assert "0.0%" in report

    def test_moderate_success_rate_recommendation(self, temp_dir):
        """Test moderate success rate generates appropriate recommendation."""
        summary = {
            "version": "1.0.0",
            "generated_at": "2026-01-25T12:00:00",
            "metrics": {
                "success_rate": 75.0,
                "avg_completion_time": 50.0,
                "failure_categories": {},
                "escalation_frequency": 10.0,
                "totals": {
                    "total_operations": 20,
                    "successful_operations": 15,
                    "failed_operations": 5,
                    "escalated_operations": 2,
                },
            },
            "sources_summary": {},
        }
        summary_path = temp_dir / "TELEMETRY_SUMMARY.json"
        summary_path.write_text(json.dumps(summary))

        dashboard = TelemetryDashboard(summary_path)
        report = dashboard.generate_report()

        assert "Moderate Success Rate" in report
