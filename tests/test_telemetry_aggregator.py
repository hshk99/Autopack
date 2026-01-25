"""Tests for TelemetryAggregator."""

import json
import sys
import pytest
from pathlib import Path

# Add scripts/utility to path for importing telemetry_aggregator
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "utility"))

from telemetry_aggregator import TelemetryAggregator


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create a temporary directory for telemetry files."""
    return tmp_path


@pytest.fixture
def sample_nudge_state():
    """Sample nudge state data."""
    return {
        "nudges": [
            {"id": "nudge-1", "escalated": True, "timestamp": "2024-01-01T10:00:00"},
            {"id": "nudge-2", "escalated": False, "timestamp": "2024-01-01T11:00:00"},
            {"id": "nudge-3", "escalated": True, "timestamp": "2024-01-01T12:00:00"},
        ],
        "escalation_count": 2,
    }


@pytest.fixture
def sample_ci_retry_state():
    """Sample CI retry state data."""
    return {
        "retries": [
            {"run_id": "run-1", "outcome": "success", "attempt": 1},
            {"run_id": "run-2", "outcome": "failed", "failure_reason": "timeout", "attempt": 2},
            {"run_id": "run-3", "outcome": "success", "attempt": 1},
            {"run_id": "run-4", "outcome": "failed", "failure_reason": "build_error", "attempt": 3},
        ]
    }


@pytest.fixture
def sample_slot_history():
    """Sample slot history data."""
    return {
        "slots": [
            {"slot_id": "slot-1", "status": "completed", "completion_time": 120.5},
            {
                "slot_id": "slot-2",
                "status": "failed",
                "failure_category": "timeout",
                "completion_time": 300.0,
            },
            {"slot_id": "slot-3", "status": "completed", "completion_time": 85.2},
            {"slot_id": "slot-4", "status": "success", "duration": 95.0},
            {"slot_id": "slot-5", "status": "error", "reason": "out_of_memory"},
        ]
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


class TestTelemetryAggregatorInit:
    """Tests for TelemetryAggregator initialization."""

    def test_init_with_path(self, temp_telemetry_dir):
        """Test aggregator initializes with base path."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        assert aggregator.base_path == temp_telemetry_dir

    def test_init_with_string_path(self, temp_telemetry_dir):
        """Test aggregator accepts string paths."""
        aggregator = TelemetryAggregator(str(temp_telemetry_dir))
        assert aggregator.base_path == Path(str(temp_telemetry_dir))


class TestAggregate:
    """Tests for aggregate() method."""

    def test_aggregate_empty_directory(self, temp_telemetry_dir):
        """Test aggregation with no telemetry files."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        result = aggregator.aggregate()

        assert "timestamp" in result
        assert result["sources"]["nudge_state"]["loaded"] is False
        assert result["sources"]["ci_retry_state"]["loaded"] is False
        assert result["sources"]["slot_history"]["loaded"] is False

    def test_aggregate_all_files(self, populated_telemetry_dir):
        """Test aggregation with all telemetry files present."""
        aggregator = TelemetryAggregator(populated_telemetry_dir)
        result = aggregator.aggregate()

        assert result["sources"]["nudge_state"]["loaded"] is True
        assert result["sources"]["ci_retry_state"]["loaded"] is True
        assert result["sources"]["slot_history"]["loaded"] is True
        assert "nudges" in result["nudge_state"]
        assert "retries" in result["ci_retry_state"]
        assert "slots" in result["slot_history"]

    def test_aggregate_partial_files(self, temp_telemetry_dir, sample_slot_history):
        """Test aggregation with only some files present."""
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        result = aggregator.aggregate()

        assert result["sources"]["nudge_state"]["loaded"] is False
        assert result["sources"]["ci_retry_state"]["loaded"] is False
        assert result["sources"]["slot_history"]["loaded"] is True

    def test_aggregate_invalid_json(self, temp_telemetry_dir):
        """Test aggregation handles invalid JSON gracefully."""
        (temp_telemetry_dir / "nudge_state.json").write_text("{ invalid json }")

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        result = aggregator.aggregate()

        assert result["sources"]["nudge_state"]["loaded"] is False
        assert result["nudge_state"] == {}


class TestComputeMetrics:
    """Tests for compute_metrics() method."""

    def test_compute_metrics_empty(self, temp_telemetry_dir):
        """Test metrics computation with no data."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert metrics["success_rate"] == 0.0
        assert metrics["avg_completion_time"] == 0.0
        assert metrics["failure_categories"] == {}
        assert metrics["escalation_frequency"] == 0.0
        assert metrics["totals"]["total_operations"] == 0

    def test_compute_metrics_with_data(self, populated_telemetry_dir):
        """Test metrics computation with full data."""
        aggregator = TelemetryAggregator(populated_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # Should have totals from slot_history (5) + ci_retry (4) = 9 operations
        assert metrics["totals"]["total_operations"] == 9
        # Successful: slot 1,3,4 (3) + ci_retry run-1,3 (2) = 5
        assert metrics["totals"]["successful_operations"] == 5
        # Failed: slot 2,5 (2) + ci_retry run-2,4 (2) = 4
        assert metrics["totals"]["failed_operations"] == 4
        # Escalated: nudges with escalated=True (2) + escalation_count (2) = 4
        assert metrics["totals"]["escalated_operations"] == 4

        # Success rate: 5/9 = 55.56%
        assert metrics["success_rate"] == pytest.approx(55.56, rel=0.1)

        # Completion times from slot_history: 120.5, 300.0, 85.2, 95.0
        expected_avg = (120.5 + 300.0 + 85.2 + 95.0) / 4
        assert metrics["avg_completion_time"] == pytest.approx(expected_avg, rel=0.01)

        # Failure categories
        assert "timeout" in metrics["failure_categories"]
        assert "build_error" in metrics["failure_categories"]
        assert "out_of_memory" in metrics["failure_categories"]

    def test_compute_metrics_auto_aggregates(self, populated_telemetry_dir):
        """Test that compute_metrics calls aggregate if not done."""
        aggregator = TelemetryAggregator(populated_telemetry_dir)
        # Directly call compute_metrics without aggregate
        metrics = aggregator.compute_metrics()

        assert metrics["totals"]["total_operations"] > 0

    def test_escalation_frequency(self, populated_telemetry_dir):
        """Test escalation frequency calculation."""
        aggregator = TelemetryAggregator(populated_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # Escalated: 4, Total: 9, Frequency: 4/9 = 44.44%
        assert metrics["escalation_frequency"] == pytest.approx(44.44, rel=0.1)


class TestSaveSummary:
    """Tests for save_summary() method."""

    def test_save_summary(self, populated_telemetry_dir):
        """Test saving summary to file."""
        output_path = populated_telemetry_dir / "TELEMETRY_SUMMARY.json"

        aggregator = TelemetryAggregator(populated_telemetry_dir)
        aggregator.save_summary(output_path)

        assert output_path.exists()

        with open(output_path) as f:
            summary = json.load(f)

        assert summary["version"] == "1.0.0"
        assert "generated_at" in summary
        assert "metrics" in summary
        assert "sources_summary" in summary

    def test_save_summary_auto_computes(self, populated_telemetry_dir):
        """Test that save_summary computes metrics if not done."""
        output_path = populated_telemetry_dir / "TELEMETRY_SUMMARY.json"

        aggregator = TelemetryAggregator(populated_telemetry_dir)
        # Directly call save_summary without compute_metrics
        aggregator.save_summary(output_path)

        with open(output_path) as f:
            summary = json.load(f)

        assert summary["metrics"]["totals"]["total_operations"] > 0

    def test_save_summary_creates_parent_dirs(self, populated_telemetry_dir):
        """Test saving summary creates parent directories if needed."""
        output_path = populated_telemetry_dir / "subdir" / "TELEMETRY_SUMMARY.json"
        output_path.parent.mkdir(parents=True)

        aggregator = TelemetryAggregator(populated_telemetry_dir)
        aggregator.save_summary(output_path)

        assert output_path.exists()


class TestCompletionTimeMetrics:
    """Tests for completion time metrics per category."""

    def test_completion_time_metrics_empty(self, temp_telemetry_dir):
        """Test completion time metrics with no phase data."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert metrics["completion_time_metrics"] == {}

    def test_completion_time_metrics_with_phases(self, temp_telemetry_dir):
        """Test completion time metrics with phase timestamps."""
        slot_history = {
            "slots": [],
            "phases": [
                {
                    "name": "research",
                    "category": "performance",
                    "started_at": "2024-01-01 10:00:00",
                    "completed_at": "2024-01-01 10:30:00",
                },
                {
                    "name": "implementation",
                    "category": "performance",
                    "started_at": "2024-01-01 11:00:00",
                    "completed_at": "2024-01-01 12:00:00",
                },
                {
                    "name": "testing",
                    "category": "reliability",
                    "started_at": "2024-01-01 13:00:00",
                    "completed_at": "2024-01-01 13:15:00",
                },
            ],
        }
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(slot_history))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # Performance category: 30 min + 60 min = avg 45 min
        assert "performance" in metrics["completion_time_metrics"]
        assert (
            metrics["completion_time_metrics"]["performance"]["avg_completion_time_minutes"] == 45.0
        )
        assert metrics["completion_time_metrics"]["performance"]["count"] == 2
        assert (
            metrics["completion_time_metrics"]["performance"]["min_completion_time_minutes"] == 30.0
        )
        assert (
            metrics["completion_time_metrics"]["performance"]["max_completion_time_minutes"] == 60.0
        )

        # Reliability category: 15 min
        assert "reliability" in metrics["completion_time_metrics"]
        assert (
            metrics["completion_time_metrics"]["reliability"]["avg_completion_time_minutes"] == 15.0
        )
        assert metrics["completion_time_metrics"]["reliability"]["count"] == 1

    def test_completion_time_metrics_missing_timestamps(self, temp_telemetry_dir):
        """Test completion time metrics ignores phases without timestamps."""
        slot_history = {
            "slots": [],
            "phases": [
                {"name": "phase1", "category": "test", "started_at": "2024-01-01 10:00:00"},
                {"name": "phase2", "category": "test", "completed_at": "2024-01-01 11:00:00"},
                {"name": "phase3", "category": "test"},
            ],
        }
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(slot_history))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # No valid phases, so no metrics
        assert metrics["completion_time_metrics"] == {}

    def test_completion_time_metrics_default_category(self, temp_telemetry_dir):
        """Test phases without category default to 'uncategorized'."""
        slot_history = {
            "slots": [],
            "phases": [
                {
                    "name": "unnamed",
                    "started_at": "2024-01-01 10:00:00",
                    "completed_at": "2024-01-01 10:20:00",
                },
            ],
        }
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(slot_history))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert "uncategorized" in metrics["completion_time_metrics"]
        assert (
            metrics["completion_time_metrics"]["uncategorized"]["avg_completion_time_minutes"]
            == 20.0
        )

    def test_completion_time_metrics_iso_format(self, temp_telemetry_dir):
        """Test completion time metrics with ISO format timestamps."""
        slot_history = {
            "slots": [],
            "phases": [
                {
                    "name": "iso-phase",
                    "category": "features",
                    "started_at": "2024-01-01T10:00:00",
                    "completed_at": "2024-01-01T10:45:00",
                },
            ],
        }
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(slot_history))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert "features" in metrics["completion_time_metrics"]
        assert metrics["completion_time_metrics"]["features"]["avg_completion_time_minutes"] == 45.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_slot_list(self, temp_telemetry_dir):
        """Test handling of empty slots list."""
        (temp_telemetry_dir / "slot_history.json").write_text(json.dumps({"slots": []}))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert metrics["totals"]["total_operations"] == 0

    def test_malformed_slot_entries(self, temp_telemetry_dir):
        """Test handling of malformed slot entries."""
        (temp_telemetry_dir / "slot_history.json").write_text(
            json.dumps({"slots": ["not a dict", 123, None, {"status": "completed"}]})
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # Only the last valid entry should be counted
        assert metrics["totals"]["total_operations"] == 1
        assert metrics["totals"]["successful_operations"] == 1

    def test_invalid_completion_time(self, temp_telemetry_dir):
        """Test handling of invalid completion times."""
        (temp_telemetry_dir / "slot_history.json").write_text(
            json.dumps({"slots": [{"status": "completed", "completion_time": "not a number"}]})
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        # Should not crash, just skip invalid time
        assert metrics["avg_completion_time"] == 0.0

    def test_nudge_flat_structure(self, temp_telemetry_dir):
        """Test handling of flat nudge structure with escalated flag."""
        (temp_telemetry_dir / "nudge_state.json").write_text(
            json.dumps({"escalated": True, "nudge_id": "n1"})
        )
        (temp_telemetry_dir / "slot_history.json").write_text(
            json.dumps({"slots": [{"status": "completed"}]})
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert metrics["totals"]["escalated_operations"] == 1
