"""Tests for metrics aggregation engine."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.metrics_aggregator import MetricsAggregator


@pytest.fixture
def temp_dirs():
    """Create temporary directories for log and store files."""
    with tempfile.TemporaryDirectory() as log_dir:
        with tempfile.TemporaryDirectory() as store_dir:
            yield log_dir, store_dir


@pytest.fixture
def aggregator(temp_dirs):
    """Create a MetricsAggregator instance with temp directories."""
    log_dir, store_dir = temp_dirs
    store_path = Path(store_dir) / "metrics_store.json"
    return MetricsAggregator(log_dir=log_dir, store_path=str(store_path))


def write_event(log_dir: str, event: dict, date_str: str = None) -> None:
    """Helper to write an event to a log file."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    log_file = Path(log_dir) / f"events_{date_str}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


class TestMetricsAggregator:
    """Tests for MetricsAggregator class."""

    def test_init_loads_empty_store(self, aggregator):
        """Test that initialization loads empty metrics when no store exists."""
        metrics = aggregator.get_metrics()
        assert metrics == {}

    def test_init_loads_existing_store(self, temp_dirs):
        """Test that initialization loads existing metrics store."""
        log_dir, store_dir = temp_dirs
        store_path = Path(store_dir) / "metrics_store.json"

        # Create existing store
        existing_metrics = {
            "aggregated_at": "2024-01-01T00:00:00",
            "metrics": {"total_events": 10},
        }
        with open(store_path, "w", encoding="utf-8") as f:
            json.dump(existing_metrics, f)

        aggregator = MetricsAggregator(log_dir=log_dir, store_path=str(store_path))
        assert aggregator.get_metrics() == {"total_events": 10}

    def test_aggregate_empty_logs(self, aggregator):
        """Test aggregation with no log files."""
        metrics = aggregator.aggregate()

        assert metrics["total_events"] == 0
        assert metrics["by_type"] == {}
        assert metrics["by_slot"] == {}
        assert metrics["success_rate"] == 0.0
        assert metrics["error_count"] == 0

    def test_aggregate_counts_events(self, aggregator, temp_dirs):
        """Test that aggregation counts total events."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        for i in range(5):
            event = {
                "timestamp": now.isoformat(),
                "type": "test_event",
                "slot": None,
                "data": {},
            }
            write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["total_events"] == 5

    def test_aggregate_groups_by_type(self, aggregator, temp_dirs):
        """Test that aggregation groups events by type."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        events = [
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "ci_failure", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "slot_filled", "slot": None, "data": {}},
        ]
        for event in events:
            write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["by_type"]["pr_merged"] == 2
        assert metrics["by_type"]["ci_failure"] == 1
        assert metrics["by_type"]["slot_filled"] == 1

    def test_aggregate_groups_by_slot(self, aggregator, temp_dirs):
        """Test that aggregation groups events by slot."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        events = [
            {"timestamp": now.isoformat(), "type": "event", "slot": 1, "data": {}},
            {"timestamp": now.isoformat(), "type": "event", "slot": 1, "data": {}},
            {"timestamp": now.isoformat(), "type": "event", "slot": 2, "data": {}},
            {"timestamp": now.isoformat(), "type": "event", "slot": None, "data": {}},
        ]
        for event in events:
            write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["by_slot"][1] == 2
        assert metrics["by_slot"][2] == 1
        assert None not in metrics["by_slot"]

    def test_aggregate_counts_errors(self, aggregator, temp_dirs):
        """Test that aggregation counts error events."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        events = [
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "connection_error", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "ci_failure", "slot": None, "data": {}},
            {"timestamp": now.isoformat(), "type": "slot_filled", "slot": None, "data": {}},
        ]
        for event in events:
            write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["error_count"] == 2  # connection_error and ci_failure

    def test_aggregate_calculates_success_rate(self, aggregator, temp_dirs):
        """Test that aggregation calculates success rate correctly."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # 8 success events, 2 error events = 80% success rate
        for _ in range(8):
            event = {"timestamp": now.isoformat(), "type": "pr_merged", "slot": None, "data": {}}
            write_event(log_dir, event)
        for _ in range(2):
            event = {"timestamp": now.isoformat(), "type": "ci_failure", "slot": None, "data": {}}
            write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["success_rate"] == 0.8
        assert metrics["error_count"] == 2

    def test_aggregate_respects_time_cutoff(self, aggregator, temp_dirs):
        """Test that aggregation only includes events within time window."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        old_time = now - timedelta(hours=48)

        # Write recent event
        recent_event = {
            "timestamp": now.isoformat(),
            "type": "recent_event",
            "slot": None,
            "data": {},
        }
        write_event(log_dir, recent_event)

        # Write old event (outside 24h window)
        old_event = {
            "timestamp": old_time.isoformat(),
            "type": "old_event",
            "slot": None,
            "data": {},
        }
        write_event(log_dir, old_event)

        metrics = aggregator.aggregate(since_hours=24)
        assert metrics["total_events"] == 1
        assert "recent_event" in metrics["by_type"]
        assert "old_event" not in metrics["by_type"]

    def test_aggregate_saves_to_store(self, aggregator, temp_dirs):
        """Test that aggregation persists metrics to store."""
        log_dir, store_dir = temp_dirs
        now = datetime.now()

        event = {"timestamp": now.isoformat(), "type": "test", "slot": None, "data": {}}
        write_event(log_dir, event)

        aggregator.aggregate()

        # Read the store file directly
        store_path = Path(store_dir) / "metrics_store.json"
        with open(store_path, "r", encoding="utf-8") as f:
            stored = json.load(f)

        assert stored["aggregated_at"] is not None
        assert stored["metrics"]["total_events"] == 1

    def test_get_summary_formats_metrics(self, aggregator, temp_dirs):
        """Test that get_summary returns formatted string."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        events = [
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": 1, "data": {}},
            {"timestamp": now.isoformat(), "type": "ci_failure", "slot": 2, "data": {}},
        ]
        for event in events:
            write_event(log_dir, event)

        aggregator.aggregate()
        summary = aggregator.get_summary()

        assert "Total Events: 2" in summary
        assert "Success Rate: 50.0%" in summary
        assert "Errors: 1" in summary

    def test_get_summary_empty_metrics(self, aggregator):
        """Test get_summary with no metrics."""
        summary = aggregator.get_summary()

        assert "Total Events: 0" in summary
        assert "Success Rate: 0.0%" in summary

    def test_aggregate_handles_unknown_event_type(self, aggregator, temp_dirs):
        """Test that events without type are counted as unknown."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        event = {"timestamp": now.isoformat(), "slot": None, "data": {}}
        write_event(log_dir, event)

        metrics = aggregator.aggregate()
        assert metrics["by_type"]["unknown"] == 1


class TestMetricsAggregatorIntegration:
    """Integration tests for MetricsAggregator with EventLogger."""

    def test_aggregate_events_from_event_logger(self, temp_dirs):
        """Test aggregating events written by EventLogger."""
        from telemetry.event_logger import EventLogger

        log_dir, store_dir = temp_dirs
        store_path = Path(store_dir) / "metrics_store.json"

        # Use EventLogger to create events
        logger = EventLogger(log_dir=log_dir)
        logger.log_pr_event("merged", 1, {"branch": "main"}, slot=1)
        logger.log_pr_event("merged", 2, {"branch": "main"}, slot=2)
        logger.log_ci_failure("run-123", "flaky_test", {"job": "lint"}, slot=1)
        logger.log_slot_operation("filled", 3, {"task_id": "IMP-001"})
        logger.log_connection_error("timeout", {"operation": "fetch"})

        # Aggregate with MetricsAggregator
        aggregator = MetricsAggregator(log_dir=log_dir, store_path=str(store_path))
        metrics = aggregator.aggregate()

        assert metrics["total_events"] == 5
        assert metrics["by_type"]["pr_merged"] == 2
        assert metrics["by_type"]["ci_failure"] == 1
        assert metrics["by_type"]["slot_filled"] == 1
        assert metrics["by_type"]["connection_error"] == 1
        assert metrics["by_slot"][1] == 2
        assert metrics["by_slot"][2] == 1
        assert metrics["by_slot"][3] == 1
        assert metrics["error_count"] == 2  # ci_failure + connection_error
        assert metrics["success_rate"] == 0.6  # 3/5 = 60%
