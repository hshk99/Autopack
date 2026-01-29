"""Tests for streaming aggregation to prevent OOM on high-volume logs.

These tests verify that the MetricsAggregator can process events
using streaming aggregation without loading all events into memory.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.metrics_aggregator import BATCH_SIZE, MetricsAggregator, StreamingAggregator


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


def write_events_batch(log_dir: str, count: int, event_type: str = "test_event") -> None:
    """Helper to write a batch of events to a log file."""
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    log_file = Path(log_dir) / f"events_{date_str}.jsonl"

    with open(log_file, "a", encoding="utf-8") as f:
        for i in range(count):
            event = {
                "timestamp": now.isoformat(),
                "type": event_type,
                "slot": i % 5,  # Distribute across 5 slots
                "data": {"index": i},
            }
            f.write(json.dumps(event) + "\n")


def write_event(log_dir: str, event: dict, date_str: str = None) -> None:
    """Helper to write a single event to a log file."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    log_file = Path(log_dir) / f"events_{date_str}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


class TestStreamingAggregator:
    """Tests for the StreamingAggregator class."""

    def test_init_empty(self):
        """Test that initialization creates empty statistics."""
        agg = StreamingAggregator()
        assert agg.total_events == 0
        assert dict(agg.by_type) == {}
        assert dict(agg.by_slot) == {}
        assert agg.error_count == 0

    def test_add_single_event(self):
        """Test adding a single event."""
        agg = StreamingAggregator()
        event = {"type": "test_event", "slot": 1}

        agg.add(event)

        assert agg.total_events == 1
        assert agg.by_type["test_event"] == 1
        assert agg.by_slot[1] == 1
        assert agg.error_count == 0

    def test_add_multiple_events(self):
        """Test adding multiple events."""
        agg = StreamingAggregator()

        agg.add({"type": "pr_merged", "slot": 1})
        agg.add({"type": "pr_merged", "slot": 2})
        agg.add({"type": "ci_failure", "slot": 1})

        assert agg.total_events == 3
        assert agg.by_type["pr_merged"] == 2
        assert agg.by_type["ci_failure"] == 1
        assert agg.by_slot[1] == 2
        assert agg.by_slot[2] == 1
        assert agg.error_count == 1  # ci_failure

    def test_add_error_event(self):
        """Test that error events are counted."""
        agg = StreamingAggregator()

        agg.add({"type": "connection_error", "slot": None})
        agg.add({"type": "ci_failure", "slot": None})
        agg.add({"type": "pr_merged", "slot": None})

        assert agg.error_count == 2  # connection_error and ci_failure

    def test_add_event_with_duration(self):
        """Test adding events with duration statistics."""
        agg = StreamingAggregator()

        agg.add({"type": "api_call", "slot": None, "duration": 100})
        agg.add({"type": "api_call", "slot": None, "duration": 200})
        agg.add({"type": "api_call", "slot": None, "duration": 300})

        assert agg._events_with_duration == 3
        assert agg._duration_sum == 600
        assert agg._duration_min == 100
        assert agg._duration_max == 300

    def test_add_event_without_type(self):
        """Test that events without type are counted as unknown."""
        agg = StreamingAggregator()

        agg.add({"slot": 1})

        assert agg.by_type["unknown"] == 1

    def test_add_event_without_slot(self):
        """Test that events without slot don't add to by_slot."""
        agg = StreamingAggregator()

        agg.add({"type": "test", "slot": None})

        assert dict(agg.by_slot) == {}

    def test_finalize_returns_metrics(self):
        """Test that finalize returns proper metrics dictionary."""
        agg = StreamingAggregator()

        agg.add({"type": "pr_merged", "slot": 1})
        agg.add({"type": "ci_failure", "slot": 2})

        metrics = agg.finalize()

        assert metrics["total_events"] == 2
        assert metrics["by_type"] == {"pr_merged": 1, "ci_failure": 1}
        assert metrics["by_slot"] == {1: 1, 2: 1}
        assert metrics["error_count"] == 1
        assert metrics["success_rate"] == 0.5

    def test_finalize_empty_aggregator(self):
        """Test finalize with no events."""
        agg = StreamingAggregator()

        metrics = agg.finalize()

        assert metrics["total_events"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["error_count"] == 0

    def test_finalize_includes_duration_stats(self):
        """Test that finalize includes duration stats when present."""
        agg = StreamingAggregator()

        agg.add({"type": "api_call", "slot": None, "duration": 100})
        agg.add({"type": "api_call", "slot": None, "duration": 200})

        metrics = agg.finalize()

        assert "duration_stats" in metrics
        assert metrics["duration_stats"]["count"] == 2
        assert metrics["duration_stats"]["sum"] == 300
        assert metrics["duration_stats"]["avg"] == 150
        assert metrics["duration_stats"]["min"] == 100
        assert metrics["duration_stats"]["max"] == 200


class TestStreamingAggregation:
    """Tests for streaming aggregation in MetricsAggregator."""

    def test_batch_size_constant_exists(self):
        """Test that BATCH_SIZE constant is defined."""
        assert BATCH_SIZE == 1000

    def test_stream_events_generator(self, aggregator, temp_dirs):
        """Test that _stream_events returns a generator."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        cutoff = now - timedelta(hours=24)

        write_events_batch(log_dir, 5)

        events_gen = aggregator._stream_events(cutoff)

        # Should be a generator
        assert hasattr(events_gen, "__iter__")
        assert hasattr(events_gen, "__next__")

        # Should yield events
        events = list(events_gen)
        assert len(events) == 5

    def test_stream_events_empty_logs(self, aggregator):
        """Test streaming with no log files."""
        cutoff = datetime.now() - timedelta(hours=24)

        events = list(aggregator._stream_events(cutoff))

        assert events == []

    def test_stream_events_respects_time_filter(self, aggregator, temp_dirs):
        """Test that streaming respects time cutoff."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        old_time = now - timedelta(hours=48)

        # Write recent event
        write_event(log_dir, {"timestamp": now.isoformat(), "type": "recent"})

        # Write old event
        write_event(log_dir, {"timestamp": old_time.isoformat(), "type": "old"})

        cutoff = now - timedelta(hours=24)
        events = list(aggregator._stream_events(cutoff))

        assert len(events) == 1
        assert events[0]["type"] == "recent"

    def test_stream_events_handles_malformed_json(self, aggregator, temp_dirs):
        """Test that streaming skips malformed JSON lines."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        log_file = Path(log_dir) / f"events_{date_str}.jsonl"

        with open(log_file, "w", encoding="utf-8") as f:
            # Valid event
            f.write(json.dumps({"timestamp": now.isoformat(), "type": "valid"}) + "\n")
            # Malformed JSON
            f.write("not valid json\n")
            # Another valid event
            f.write(json.dumps({"timestamp": now.isoformat(), "type": "also_valid"}) + "\n")

        cutoff = now - timedelta(hours=1)
        events = list(aggregator._stream_events(cutoff))

        assert len(events) == 2
        assert events[0]["type"] == "valid"
        assert events[1]["type"] == "also_valid"

    def test_stream_events_handles_missing_timestamp(self, aggregator, temp_dirs):
        """Test that streaming skips events without timestamp."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        log_file = Path(log_dir) / f"events_{date_str}.jsonl"

        with open(log_file, "w", encoding="utf-8") as f:
            # Valid event
            f.write(json.dumps({"timestamp": now.isoformat(), "type": "valid"}) + "\n")
            # Missing timestamp
            f.write(json.dumps({"type": "no_timestamp"}) + "\n")
            # Another valid event
            f.write(json.dumps({"timestamp": now.isoformat(), "type": "also_valid"}) + "\n")

        cutoff = now - timedelta(hours=1)
        events = list(aggregator._stream_events(cutoff))

        assert len(events) == 2

    def test_aggregate_uses_streaming(self, aggregator, temp_dirs):
        """Test that aggregate() uses streaming aggregation."""
        log_dir, _ = temp_dirs

        write_events_batch(log_dir, 100)

        metrics = aggregator.aggregate()

        assert metrics["total_events"] == 100
        assert metrics["by_type"]["test_event"] == 100
        # Verify slots are distributed (0-4)
        for slot in range(5):
            assert slot in metrics["by_slot"]

    def test_aggregate_large_volume(self, aggregator, temp_dirs):
        """Test aggregation with volume larger than BATCH_SIZE."""
        log_dir, _ = temp_dirs
        event_count = BATCH_SIZE + 500  # More than one batch

        write_events_batch(log_dir, event_count)

        metrics = aggregator.aggregate()

        assert metrics["total_events"] == event_count
        assert metrics["by_type"]["test_event"] == event_count

    def test_aggregate_mixed_event_types(self, aggregator, temp_dirs):
        """Test streaming aggregation with mixed event types."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Write different event types
        for i in range(100):
            event = {
                "timestamp": now.isoformat(),
                "type": "pr_merged" if i % 2 == 0 else "ci_failure",
                "slot": i % 3,
            }
            write_event(log_dir, event)

        metrics = aggregator.aggregate()

        assert metrics["total_events"] == 100
        assert metrics["by_type"]["pr_merged"] == 50
        assert metrics["by_type"]["ci_failure"] == 50
        assert metrics["error_count"] == 50
        assert metrics["success_rate"] == 0.5

    def test_read_events_uses_stream_events(self, aggregator, temp_dirs):
        """Test that _read_events internally uses _stream_events."""
        log_dir, _ = temp_dirs
        now = datetime.now()
        cutoff = now - timedelta(hours=24)

        write_events_batch(log_dir, 10)

        events = aggregator._read_events(cutoff)

        # Should return a list (for backward compatibility)
        assert isinstance(events, list)
        assert len(events) == 10


class TestStreamingAggregationMemoryEfficiency:
    """Tests to verify memory efficiency of streaming aggregation."""

    def test_streaming_does_not_store_all_events(self, temp_dirs):
        """Test that streaming processes events without storing all in memory.

        This test verifies the design pattern - the StreamingAggregator
        should only maintain aggregate statistics, not individual events.
        """
        agg = StreamingAggregator()

        # Simulate processing many events
        for i in range(10000):
            agg.add({"type": f"event_{i % 10}", "slot": i % 5})

        # Verify aggregator doesn't store individual events
        # Only maintains counts
        assert agg.total_events == 10000
        assert len(agg.by_type) == 10  # Only 10 unique types
        assert len(agg.by_slot) == 5  # Only 5 slots

    def test_generator_yields_events_lazily(self, aggregator, temp_dirs):
        """Test that _stream_events yields events lazily."""
        log_dir, _ = temp_dirs

        write_events_batch(log_dir, 100)

        cutoff = datetime.now() - timedelta(hours=24)
        gen = aggregator._stream_events(cutoff)

        # Get first event without consuming entire generator
        first_event = next(gen)
        assert first_event is not None
        assert "type" in first_event

        # Generator should still have more events
        remaining = list(gen)
        assert len(remaining) == 99
