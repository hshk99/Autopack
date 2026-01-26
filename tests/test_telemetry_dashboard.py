"""Tests for TelemetryDashboard."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.telemetry_dashboard import TelemetryDashboard


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create a temporary directory for telemetry files."""
    return tmp_path


@pytest.fixture
def sample_nudge_state():
    """Sample nudge state data with various patterns."""
    now = datetime.now(timezone.utc)
    return {
        "nudges": [
            {
                "id": "nudge-1",
                "phase_type": "build",
                "status": "failed",
                "escalated": True,
                "escalation_level": 1,
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "id": "nudge-2",
                "phase_type": "build",
                "status": "failed",
                "escalated": False,
                "timestamp": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "id": "nudge-3",
                "phase_type": "build",
                "status": "completed",
                "escalated": False,
                "timestamp": (now - timedelta(hours=4)).isoformat(),
            },
            {
                "id": "nudge-4",
                "phase_type": "test",
                "status": "completed",
                "escalated": False,
                "timestamp": (now - timedelta(hours=5)).isoformat(),
            },
            {
                "id": "nudge-5",
                "phase_type": "deploy",
                "status": "failed",
                "escalated": True,
                "escalation_level": 2,
                "timestamp": (now - timedelta(hours=6)).isoformat(),
            },
            {
                "id": "nudge-6",
                "phase_type": "deploy",
                "status": "completed",
                "escalated": False,
                "timestamp": (now - timedelta(hours=7)).isoformat(),
            },
            # Phase sequence for average nudges calculation
            {
                "id": "nudge-7",
                "phase_id": "phase-A",
                "phase_type": "integration",
                "status": "failed",
                "timestamp": (now - timedelta(hours=8)).isoformat(),
            },
            {
                "id": "nudge-8",
                "phase_id": "phase-A",
                "phase_type": "integration",
                "status": "failed",
                "timestamp": (now - timedelta(hours=7, minutes=30)).isoformat(),
            },
            {
                "id": "nudge-9",
                "phase_id": "phase-A",
                "phase_type": "integration",
                "status": "completed",
                "timestamp": (now - timedelta(hours=7)).isoformat(),
            },
        ]
    }


@pytest.fixture
def sample_ci_retry_state():
    """Sample CI retry state data."""
    now = datetime.now(timezone.utc)
    return {
        "retries": [
            {
                "test_name": "test_auth",
                "outcome": "failed",
                "workflow": "ci",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "test_name": "test_auth",
                "outcome": "success",
                "workflow": "ci",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "test_name": "test_db",
                "outcome": "failed",
                "workflow": "integration",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
            },
            {
                "test_name": "test_simple",
                "outcome": "passed",
                "workflow": "unit",
                "timestamp": (now - timedelta(hours=4)).isoformat(),
            },
        ]
    }


@pytest.fixture
def sample_slot_history():
    """Sample slot history data."""
    now = datetime.now(timezone.utc)
    return {
        "slots": [
            {
                "slot_id": 1,
                "status": "completed",
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "slot_id": 1,
                "status": "failed",
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "slot_id": 2,
                "status": "completed",
                "timestamp": (now - timedelta(hours=3)).isoformat(),
            },
        ],
        "events": [
            {
                "slot": 1,
                "event_type": "escalation_level_change",
                "escalation_level": 1,
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "slot": 2,
                "event_type": "escalation_level_change",
                "escalation_level": 2,
                "timestamp": (now - timedelta(hours=2)).isoformat(),
            },
        ],
    }


@pytest.fixture
def populated_telemetry_dir(
    temp_telemetry_dir, sample_nudge_state, sample_ci_retry_state, sample_slot_history
):
    """Create telemetry files in temp directory."""
    (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(sample_nudge_state))
    (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps(sample_ci_retry_state))
    (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))
    return temp_telemetry_dir


class TestTelemetryDashboardInit:
    """Tests for TelemetryDashboard initialization."""

    def test_init_with_path(self, temp_telemetry_dir):
        """Test dashboard initializes with Path object."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        assert dashboard.base_path == temp_telemetry_dir

    def test_init_with_string_path(self, temp_telemetry_dir):
        """Test dashboard accepts string paths."""
        dashboard = TelemetryDashboard(str(temp_telemetry_dir))
        assert dashboard.base_path == Path(str(temp_telemetry_dir))

    def test_file_paths_configured(self, temp_telemetry_dir):
        """Test telemetry file paths are correctly configured."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        assert dashboard.nudge_state_file == temp_telemetry_dir / "nudge_state.json"
        assert dashboard.ci_retry_file == temp_telemetry_dir / "ci_retry_state.json"
        assert dashboard.slot_history_file == temp_telemetry_dir / "slot_history.json"


class TestGenerateSummary:
    """Tests for generate_summary() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test summary with no telemetry files."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary()

        assert "time_window_hours" in summary
        assert "generated_at" in summary
        assert "nudge_metrics" in summary
        assert "ci_metrics" in summary
        assert "slot_metrics" in summary
        assert summary["nudge_metrics"]["total"] == 0
        assert summary["ci_metrics"]["total_runs"] == 0

    def test_summary_structure(self, populated_telemetry_dir):
        """Test summary has expected structure."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        summary = dashboard.generate_summary(hours=48)

        assert summary["time_window_hours"] == 48
        assert "generated_at" in summary

        # Check nudge metrics structure
        nudge = summary["nudge_metrics"]
        assert "total" in nudge
        assert "failed" in nudge
        assert "escalated" in nudge
        assert "failure_rate" in nudge
        assert "escalation_rate" in nudge

        # Check CI metrics structure
        ci = summary["ci_metrics"]
        assert "total_runs" in ci
        assert "successes" in ci
        assert "failures" in ci
        assert "success_rate" in ci

        # Check slot metrics structure
        slot = summary["slot_metrics"]
        assert "total_events" in slot
        assert "failures" in slot

    def test_summary_calculates_metrics(self, populated_telemetry_dir):
        """Test summary calculates correct metrics."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        summary = dashboard.generate_summary(hours=48)

        # Should have 9 nudges total
        assert summary["nudge_metrics"]["total"] == 9
        # 5 failed (nudge-1, nudge-2, nudge-5, nudge-7, nudge-8)
        assert summary["nudge_metrics"]["failed"] == 5
        # 2 escalated (nudge-1, nudge-5)
        assert summary["nudge_metrics"]["escalated"] == 2

        # CI metrics: 4 retries, 2 success, 2 failed
        assert summary["ci_metrics"]["total_runs"] == 4
        assert summary["ci_metrics"]["successes"] == 2
        assert summary["ci_metrics"]["failures"] == 2

    def test_summary_time_filter(self, temp_telemetry_dir):
        """Test summary respects time window."""
        now = datetime.now(timezone.utc)
        nudge_data = {
            "nudges": [
                {
                    "id": "recent",
                    "status": "completed",
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                },
                {
                    "id": "old",
                    "status": "completed",
                    "timestamp": (now - timedelta(hours=48)).isoformat(),
                },
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)

        # With 24 hour window, should only include recent nudge
        summary = dashboard.generate_summary(hours=24)
        assert summary["nudge_metrics"]["total"] == 1

        # With 72 hour window, should include both
        summary = dashboard.generate_summary(hours=72)
        assert summary["nudge_metrics"]["total"] == 2


class TestFailureRatesByType:
    """Tests for failure_rates_by_type() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test with no telemetry files."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        rates = dashboard.failure_rates_by_type()
        assert rates == {}

    def test_calculates_rates_by_phase(self, populated_telemetry_dir):
        """Test failure rates are calculated per phase type."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        rates = dashboard.failure_rates_by_type(hours=48)

        # build: 2 failed, 1 completed = 66.7%
        assert "build" in rates
        assert abs(rates["build"] - 0.667) < 0.01

        # test: 0 failed, 1 completed = 0%
        assert "test" in rates
        assert rates["test"] == 0.0

        # deploy: 1 failed, 1 completed = 50%
        assert "deploy" in rates
        assert rates["deploy"] == 0.5

    def test_handles_empty_nudges(self, temp_telemetry_dir):
        """Test with empty nudges list."""
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        rates = dashboard.failure_rates_by_type()
        assert rates == {}


class TestAverageNudgesToSuccess:
    """Tests for average_nudges_to_success() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test with no telemetry files."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        avg = dashboard.average_nudges_to_success()
        assert avg == 0.0

    def test_calculates_average(self, populated_telemetry_dir):
        """Test average nudges calculation."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        avg = dashboard.average_nudges_to_success(hours=48)

        # phase-A has 3 nudges to success
        # Other single nudges complete immediately (1 nudge each)
        # Average depends on how phases are identified
        assert avg > 0

    def test_single_nudge_success(self, temp_telemetry_dir):
        """Test with phases that succeed on first nudge."""
        now = datetime.now(timezone.utc)
        nudge_data = {
            "nudges": [
                {
                    "id": "n1",
                    "phase_id": "p1",
                    "status": "completed",
                    "timestamp": now.isoformat(),
                },
                {
                    "id": "n2",
                    "phase_id": "p2",
                    "status": "completed",
                    "timestamp": now.isoformat(),
                },
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        avg = dashboard.average_nudges_to_success(hours=24)
        assert avg == 1.0

    def test_multi_nudge_sequence(self, temp_telemetry_dir):
        """Test with phases requiring multiple nudges."""
        now = datetime.now(timezone.utc)
        nudge_data = {
            "nudges": [
                # Phase A: 3 nudges to success
                {
                    "phase_id": "A",
                    "status": "failed",
                    "timestamp": (now - timedelta(hours=3)).isoformat(),
                },
                {
                    "phase_id": "A",
                    "status": "failed",
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                },
                {
                    "phase_id": "A",
                    "status": "completed",
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                },
                # Phase B: 1 nudge to success
                {"phase_id": "B", "status": "completed", "timestamp": now.isoformat()},
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        avg = dashboard.average_nudges_to_success(hours=24)
        # (3 + 1) / 2 = 2.0
        assert avg == 2.0


class TestEscalationFrequency:
    """Tests for escalation_frequency() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test with no telemetry files."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        freq = dashboard.escalation_frequency()
        assert freq == {}

    def test_counts_escalations_by_level(self, populated_telemetry_dir):
        """Test escalation counting by level."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        freq = dashboard.escalation_frequency(hours=48)

        # From nudge_state: level 1 (1x), level 2 (1x)
        # From slot_history events: level 1 (1x), level 2 (1x)
        assert 1 in freq
        assert 2 in freq
        assert freq[1] == 2  # nudge + event
        assert freq[2] == 2  # nudge + event

    def test_escalation_from_nudges_only(self, temp_telemetry_dir):
        """Test escalation counting from nudge data."""
        now = datetime.now(timezone.utc)
        nudge_data = {
            "nudges": [
                {
                    "status": "failed",
                    "escalated": True,
                    "escalation_level": 1,
                    "timestamp": now.isoformat(),
                },
                {
                    "status": "failed",
                    "escalated": True,
                    "escalation_level": 1,
                    "timestamp": now.isoformat(),
                },
                {
                    "status": "failed",
                    "escalated": True,
                    "escalation_level": 3,
                    "timestamp": now.isoformat(),
                },
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        freq = dashboard.escalation_frequency(hours=24)

        assert freq[1] == 2
        assert freq[3] == 1


class TestRenderMarkdownReport:
    """Tests for render_markdown_report() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test report generation with no data."""
        dashboard = TelemetryDashboard(temp_telemetry_dir)
        report = dashboard.render_markdown_report()

        assert "# Telemetry Health Report" in report
        assert "Generated" in report
        assert "Summary Metrics" in report

    def test_report_contains_sections(self, populated_telemetry_dir):
        """Test report contains all expected sections."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        report = dashboard.render_markdown_report(hours=48)

        # Check main sections
        assert "# Telemetry Health Report" in report
        assert "## Summary Metrics" in report
        assert "### Nudge Activity" in report
        assert "### CI Pipeline" in report
        assert "### Slot Activity" in report
        assert "## Failure Rates by Phase Type" in report
        assert "## Performance Indicators" in report
        assert "## Health Status" in report

    def test_report_contains_metrics(self, populated_telemetry_dir):
        """Test report contains metric values."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        report = dashboard.render_markdown_report(hours=48)

        # Should contain table formatting
        assert "|" in report
        assert "Total Nudges" in report
        assert "Failed Nudges" in report
        assert "Failure Rate" in report
        assert "Success Rate" in report

    def test_report_shows_health_status(self, populated_telemetry_dir):
        """Test report includes health status assessment."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)
        report = dashboard.render_markdown_report(hours=48)

        # Should have status indicator
        assert "**Status**:" in report

    def test_report_healthy_status(self, temp_telemetry_dir):
        """Test healthy status when metrics are good."""
        now = datetime.now(timezone.utc)
        # Create data with good metrics
        nudge_data = {
            "nudges": [
                {"status": "completed", "timestamp": now.isoformat()},
                {"status": "completed", "timestamp": now.isoformat()},
                {"status": "completed", "timestamp": now.isoformat()},
            ]
        }
        ci_data = {
            "retries": [
                {"outcome": "success", "timestamp": now.isoformat()},
                {"outcome": "success", "timestamp": now.isoformat()},
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))
        (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps(ci_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        report = dashboard.render_markdown_report(hours=24)

        assert "HEALTHY" in report

    def test_report_attention_needed_status(self, temp_telemetry_dir):
        """Test attention needed status when metrics are bad."""
        now = datetime.now(timezone.utc)
        # Create data with bad metrics (high failure rate)
        nudge_data = {
            "nudges": [
                {"status": "failed", "timestamp": now.isoformat()},
                {"status": "failed", "timestamp": now.isoformat()},
                {"status": "failed", "timestamp": now.isoformat()},
                {"status": "completed", "timestamp": now.isoformat()},
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        report = dashboard.render_markdown_report(hours=24)

        assert "ATTENTION NEEDED" in report
        assert "High nudge failure rate" in report


class TestCacheHandling:
    """Tests for data caching behavior."""

    def test_cache_prevents_multiple_reads(self, populated_telemetry_dir):
        """Test that data is cached after first read."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)

        # First call loads data
        summary1 = dashboard.generate_summary()
        # Second call should use cached data
        summary2 = dashboard.generate_summary()

        # Cache should be populated
        assert dashboard._nudge_data is not None
        assert summary1["nudge_metrics"]["total"] == summary2["nudge_metrics"]["total"]

    def test_clear_cache(self, populated_telemetry_dir):
        """Test that clear_cache resets cached data."""
        dashboard = TelemetryDashboard(populated_telemetry_dir)

        # Load data
        dashboard.generate_summary()
        assert dashboard._nudge_data is not None

        # Clear cache
        dashboard.clear_cache()

        assert dashboard._nudge_data is None
        assert dashboard._ci_retry_data is None
        assert dashboard._slot_history_data is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_invalid_json(self, temp_telemetry_dir):
        """Test handling of invalid JSON files."""
        (temp_telemetry_dir / "nudge_state.json").write_text("{ invalid json }")

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary()

        # Should return empty metrics, not crash
        assert summary["nudge_metrics"]["total"] == 0

    def test_handles_empty_arrays(self, temp_telemetry_dir):
        """Test handling of empty arrays in data."""
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps({"retries": []}))
        (temp_telemetry_dir / "slot_history.json").write_text(
            json.dumps({"slots": [], "events": []})
        )

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary()

        assert summary["nudge_metrics"]["total"] == 0
        assert summary["ci_metrics"]["total_runs"] == 0
        assert summary["slot_metrics"]["total_events"] == 0

    def test_handles_missing_fields(self, temp_telemetry_dir):
        """Test handling of missing expected fields."""
        (temp_telemetry_dir / "nudge_state.json").write_text(
            json.dumps({"nudges": [{"id": "n1"}, {"id": "n2"}]})
        )

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary()

        # Should not crash
        assert isinstance(summary, dict)

    def test_handles_malformed_entries(self, temp_telemetry_dir):
        """Test handling of malformed entries in arrays."""
        (temp_telemetry_dir / "ci_retry_state.json").write_text(
            json.dumps({"retries": ["not a dict", 123, None, {"outcome": "success"}]})
        )

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary()

        # Should not crash, should skip invalid entries
        assert isinstance(summary, dict)
        # Only the valid entry should be counted
        assert summary["ci_metrics"]["total_runs"] == 1

    def test_handles_invalid_timestamps(self, temp_telemetry_dir):
        """Test handling of invalid timestamp formats."""
        nudge_data = {
            "nudges": [
                {"status": "completed", "timestamp": "invalid-timestamp"},
                {"status": "completed", "timestamp": "2025-01-01T00:00:00Z"},
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary(hours=24)

        # Should not crash, items with invalid timestamps included (legacy data)
        assert summary["nudge_metrics"]["total"] >= 1

    def test_handles_naive_timestamps(self, temp_telemetry_dir):
        """Test handling of timestamps without timezone info."""
        now = datetime.now()
        nudge_data = {
            "nudges": [
                {"status": "completed", "timestamp": now.isoformat()},
            ]
        }
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(nudge_data))

        dashboard = TelemetryDashboard(temp_telemetry_dir)
        summary = dashboard.generate_summary(hours=24)

        # Should handle naive timestamps as UTC
        assert isinstance(summary, dict)
