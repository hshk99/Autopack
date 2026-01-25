"""Tests for model switch telemetry functionality.

Tests both the recording of model switch events (select_llm_model_ocr.py)
and the aggregation of model switch metrics (telemetry_aggregator.py).
"""

import json
import sys
from pathlib import Path

import pytest

# Add scripts/utility to path for importing telemetry_aggregator
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "utility"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from select_llm_model_ocr import MODEL_SWITCH_LOG_FILE, record_model_switch
from telemetry_aggregator import TelemetryAggregator


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create a temporary directory for telemetry files."""
    return tmp_path


@pytest.fixture
def sample_model_switch_log():
    """Sample model switch log data."""
    return {
        "events": [
            {
                "timestamp": "2024-01-01T10:00:00",
                "from_model": "gpt-5.2",
                "to_model": "glm-4.7",
                "trigger_reason": "token_limit",
                "phase_id": "phase-1",
            },
            {
                "timestamp": "2024-01-01T11:00:00",
                "from_model": "glm-4.7",
                "to_model": "claude",
                "trigger_reason": "user_request",
            },
            {
                "timestamp": "2024-01-01T12:00:00",
                "from_model": "claude",
                "to_model": "glm-4.7",
                "trigger_reason": "fallback",
                "phase_id": "phase-2",
            },
            {
                "timestamp": "2024-01-01T13:00:00",
                "from_model": "glm-4.7",
                "to_model": "gpt-5.2",
                "trigger_reason": "token_limit",
                "phase_id": "phase-1",
            },
        ],
        "last_updated": "2024-01-01T13:00:00",
    }


class TestRecordModelSwitch:
    """Tests for record_model_switch function."""

    def test_record_creates_new_file(self, temp_telemetry_dir):
        """Test recording creates a new log file if none exists."""
        record_model_switch(
            from_model="gpt-5.2",
            to_model="glm-4.7",
            trigger_reason="user_request",
            log_dir=temp_telemetry_dir,
        )

        log_path = temp_telemetry_dir / MODEL_SWITCH_LOG_FILE
        assert log_path.exists()

        with open(log_path) as f:
            data = json.load(f)

        assert "events" in data
        assert len(data["events"]) == 1
        assert data["events"][0]["from_model"] == "gpt-5.2"
        assert data["events"][0]["to_model"] == "glm-4.7"
        assert data["events"][0]["trigger_reason"] == "user_request"
        assert "timestamp" in data["events"][0]

    def test_record_appends_to_existing(self, temp_telemetry_dir):
        """Test recording appends to existing log file."""
        # Create initial event
        record_model_switch(
            from_model="gpt-5.2",
            to_model="glm-4.7",
            trigger_reason="user_request",
            log_dir=temp_telemetry_dir,
        )

        # Add second event
        record_model_switch(
            from_model="glm-4.7",
            to_model="claude",
            trigger_reason="token_limit",
            phase_id="phase-1",
            log_dir=temp_telemetry_dir,
        )

        log_path = temp_telemetry_dir / MODEL_SWITCH_LOG_FILE
        with open(log_path) as f:
            data = json.load(f)

        assert len(data["events"]) == 2
        assert data["events"][1]["phase_id"] == "phase-1"

    def test_record_returns_event_dict(self, temp_telemetry_dir):
        """Test record_model_switch returns the event dictionary."""
        event = record_model_switch(
            from_model="gpt-5.2",
            to_model="glm-4.7",
            trigger_reason="fallback",
            phase_id="phase-3",
            log_dir=temp_telemetry_dir,
        )

        assert event["from_model"] == "gpt-5.2"
        assert event["to_model"] == "glm-4.7"
        assert event["trigger_reason"] == "fallback"
        assert event["phase_id"] == "phase-3"
        assert "timestamp" in event

    def test_record_without_phase_id(self, temp_telemetry_dir):
        """Test recording without phase_id omits the field."""
        event = record_model_switch(
            from_model="gpt-5.2",
            to_model="glm-4.7",
            trigger_reason="user_request",
            log_dir=temp_telemetry_dir,
        )

        assert "phase_id" not in event

    def test_record_handles_corrupted_file(self, temp_telemetry_dir):
        """Test recording handles corrupted existing file."""
        log_path = temp_telemetry_dir / MODEL_SWITCH_LOG_FILE
        log_path.write_text("{ corrupted json")

        # Should not raise, should create new log
        event = record_model_switch(
            from_model="gpt-5.2",
            to_model="glm-4.7",
            trigger_reason="user_request",
            log_dir=temp_telemetry_dir,
        )

        assert event["from_model"] == "gpt-5.2"

        with open(log_path) as f:
            data = json.load(f)
        assert len(data["events"]) == 1


class TestModelSwitchMetricsAggregation:
    """Tests for model switch metrics in TelemetryAggregator."""

    def test_aggregate_includes_model_switch_source(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test aggregation includes model switch log source."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        result = aggregator.aggregate()

        assert result["sources"]["model_switch_log"]["loaded"] is True
        assert result["sources"]["model_switch_log"]["entry_count"] == 4
        assert "model_switch_log" in result

    def test_aggregate_empty_model_switch(self, temp_telemetry_dir):
        """Test aggregation with no model switch log."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        result = aggregator.aggregate()

        assert result["sources"]["model_switch_log"]["loaded"] is False
        assert result["sources"]["model_switch_log"]["entry_count"] == 0

    def test_get_model_switch_metrics_total_switches(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test total_switches metric."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        assert metrics["total_switches"] == 4

    def test_get_model_switch_metrics_switches_by_reason(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test switches_by_reason metric."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        assert metrics["switches_by_reason"]["token_limit"] == 2
        assert metrics["switches_by_reason"]["user_request"] == 1
        assert metrics["switches_by_reason"]["fallback"] == 1

    def test_get_model_switch_metrics_model_usage_distribution(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test model_usage_distribution metric."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        assert metrics["model_usage_distribution"]["glm-4.7"] == 2
        assert metrics["model_usage_distribution"]["claude"] == 1
        assert metrics["model_usage_distribution"]["gpt-5.2"] == 1

    def test_get_model_switch_metrics_switches_by_phase(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test switches_by_phase metric."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        # phase-1 appears twice, phase-2 once, one event has no phase_id
        assert metrics["switches_by_phase"]["phase-1"] == 2
        assert metrics["switches_by_phase"]["phase-2"] == 1
        assert len(metrics["switches_by_phase"]) == 2  # No unknown for missing

    def test_get_model_switch_metrics_empty(self, temp_telemetry_dir):
        """Test model switch metrics with no data."""
        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        assert metrics["total_switches"] == 0
        assert metrics["switches_by_reason"] == {}
        assert metrics["model_usage_distribution"] == {}
        assert metrics["switches_by_phase"] == {}

    def test_compute_metrics_includes_model_switch(
        self, temp_telemetry_dir, sample_model_switch_log
    ):
        """Test compute_metrics includes model switch metrics."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        metrics = aggregator.compute_metrics()

        assert "model_switch_metrics" in metrics
        assert metrics["model_switch_metrics"]["total_switches"] == 4

    def test_save_summary_includes_model_switch(self, temp_telemetry_dir, sample_model_switch_log):
        """Test save_summary includes model switch in sources."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(
            json.dumps(sample_model_switch_log)
        )
        output_path = temp_telemetry_dir / "TELEMETRY_SUMMARY.json"

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.save_summary(output_path)

        with open(output_path) as f:
            summary = json.load(f)

        assert "model_switch_log" in summary["sources_summary"]
        assert summary["sources_summary"]["model_switch_log"]["loaded"] is True


class TestEdgeCases:
    """Tests for edge cases in model switch telemetry."""

    def test_malformed_events(self, temp_telemetry_dir):
        """Test handling of malformed event entries."""
        malformed_data = {
            "events": [
                "not a dict",
                123,
                None,
                {"from_model": "gpt-5.2", "to_model": "glm-4.7"},  # missing trigger_reason
            ]
        }
        (temp_telemetry_dir / "model_switch_log.json").write_text(json.dumps(malformed_data))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        # Should count valid entries only
        assert metrics["total_switches"] == 4  # All items in list
        # But only the last valid dict should contribute to reason counts
        assert metrics["switches_by_reason"].get("unknown", 0) == 1

    def test_empty_events_list(self, temp_telemetry_dir):
        """Test handling of empty events list."""
        (temp_telemetry_dir / "model_switch_log.json").write_text(json.dumps({"events": []}))

        aggregator = TelemetryAggregator(temp_telemetry_dir)
        aggregator.aggregate()
        metrics = aggregator.get_model_switch_metrics()

        assert metrics["total_switches"] == 0

    def test_legacy_list_format(self, temp_telemetry_dir):
        """Test handling of legacy list format (events as root array)."""
        # record_model_switch should handle this format when reading
        legacy_data = [
            {"from_model": "gpt-5.2", "to_model": "glm-4.7", "trigger_reason": "user_request"}
        ]
        log_path = temp_telemetry_dir / MODEL_SWITCH_LOG_FILE
        log_path.write_text(json.dumps(legacy_data))

        # Add a new event - should work with legacy format
        record_model_switch(
            from_model="glm-4.7",
            to_model="claude",
            trigger_reason="fallback",
            log_dir=temp_telemetry_dir,
        )

        with open(log_path) as f:
            data = json.load(f)

        # Should have converted to new format
        assert "events" in data
        assert len(data["events"]) == 2
