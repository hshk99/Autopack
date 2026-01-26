"""Tests for unified telemetry event log."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.event_schema import TelemetryEvent
from telemetry.unified_event_log import UnifiedEventLog


@pytest.fixture
def temp_log_file():
    """Create a temporary file for the event log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "unified_events.jsonl")


@pytest.fixture
def event_log(temp_log_file):
    """Create a UnifiedEventLog instance with temp file."""
    return UnifiedEventLog(log_path=temp_log_file)


@pytest.fixture
def sample_event():
    """Create a sample TelemetryEvent."""
    return TelemetryEvent(
        timestamp=datetime.now(),
        source="slot_history",
        event_type="slot_filled",
        slot_id=1,
        phase_id="phase-001",
        pr_number=123,
        payload={"task_id": "IMP-TEL-001"},
    )


class TestTelemetryEvent:
    """Tests for TelemetryEvent dataclass."""

    def test_create_event(self):
        """Test creating a TelemetryEvent with all fields."""
        event = TelemetryEvent(
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            source="ci_retry",
            event_type="retry_triggered",
            slot_id=2,
            phase_id="phase-002",
            pr_number=456,
            payload={"attempt": 1},
        )

        assert event.source == "ci_retry"
        assert event.event_type == "retry_triggered"
        assert event.slot_id == 2
        assert event.phase_id == "phase-002"
        assert event.pr_number == 456
        assert event.payload == {"attempt": 1}

    def test_create_event_with_defaults(self):
        """Test creating event with optional fields defaulting to None."""
        event = TelemetryEvent(
            timestamp=datetime.now(),
            source="nudge_state",
            event_type="nudge_sent",
        )

        assert event.slot_id is None
        assert event.phase_id is None
        assert event.pr_number is None
        assert event.payload == {}

    def test_to_dict(self, sample_event):
        """Test converting event to dictionary."""
        data = sample_event.to_dict()

        assert data["source"] == "slot_history"
        assert data["event_type"] == "slot_filled"
        assert data["slot_id"] == 1
        assert data["phase_id"] == "phase-001"
        assert data["pr_number"] == 123
        assert data["payload"] == {"task_id": "IMP-TEL-001"}
        assert "timestamp" in data

    def test_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "timestamp": "2024-01-15T10:30:00",
            "source": "escalation",
            "event_type": "escalation_created",
            "slot_id": 3,
            "phase_id": "phase-003",
            "pr_number": 789,
            "payload": {"severity": "high"},
        }

        event = TelemetryEvent.from_dict(data)

        assert event.source == "escalation"
        assert event.event_type == "escalation_created"
        assert event.slot_id == 3
        assert event.phase_id == "phase-003"
        assert event.pr_number == 789
        assert event.payload == {"severity": "high"}
        assert event.timestamp == datetime(2024, 1, 15, 10, 30, 0)

    def test_from_dict_with_datetime_object(self):
        """Test from_dict handles datetime objects."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        data = {
            "timestamp": ts,
            "source": "ci_retry",
            "event_type": "test",
        }

        event = TelemetryEvent.from_dict(data)

        assert event.timestamp == ts

    def test_roundtrip_serialization(self, sample_event):
        """Test that to_dict and from_dict are inverse operations."""
        data = sample_event.to_dict()
        restored = TelemetryEvent.from_dict(data)

        assert restored.source == sample_event.source
        assert restored.event_type == sample_event.event_type
        assert restored.slot_id == sample_event.slot_id
        assert restored.phase_id == sample_event.phase_id
        assert restored.pr_number == sample_event.pr_number
        assert restored.payload == sample_event.payload


class TestUnifiedEventLog:
    """Tests for UnifiedEventLog class."""

    def test_init_creates_parent_directory(self, temp_log_file):
        """Test that initialization creates parent directories."""
        nested_path = str(Path(temp_log_file).parent / "nested" / "dir" / "log.jsonl")

        UnifiedEventLog(log_path=nested_path)

        assert Path(nested_path).parent.exists()

    def test_ingest_writes_event(self, event_log, sample_event, temp_log_file):
        """Test that ingest writes event to log file."""
        event_log.ingest(sample_event)

        with open(temp_log_file) as f:
            line = f.readline()
            data = json.loads(line)

        assert data["source"] == "slot_history"
        assert data["event_type"] == "slot_filled"
        assert data["slot_id"] == 1

    def test_ingest_appends_events(self, event_log, temp_log_file):
        """Test that multiple ingests append to log."""
        for i in range(3):
            event = TelemetryEvent(
                timestamp=datetime.now(),
                source="ci_retry",
                event_type=f"event_{i}",
            )
            event_log.ingest(event)

        with open(temp_log_file) as f:
            lines = f.readlines()

        assert len(lines) == 3

    def test_ingest_batch(self, event_log, temp_log_file):
        """Test batch ingestion of events."""
        events = [
            TelemetryEvent(
                timestamp=datetime.now(),
                source="slot_history",
                event_type=f"event_{i}",
                slot_id=i,
            )
            for i in range(5)
        ]

        count = event_log.ingest_batch(events)

        assert count == 5
        with open(temp_log_file) as f:
            lines = f.readlines()
        assert len(lines) == 5

    def test_query_returns_all_events_without_filters(self, event_log):
        """Test query returns all events when no filters provided."""
        for i in range(3):
            event = TelemetryEvent(
                timestamp=datetime.now(),
                source="nudge_state",
                event_type=f"event_{i}",
            )
            event_log.ingest(event)

        events = event_log.query()

        assert len(events) == 3

    def test_query_empty_log_returns_empty_list(self, event_log):
        """Test query on empty/nonexistent log returns empty list."""
        events = event_log.query()

        assert events == []

    def test_query_filter_by_source(self, event_log):
        """Test filtering events by source."""
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="slot_history", event_type="a")
        )
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="ci_retry", event_type="b")
        )
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="slot_history", event_type="c")
        )

        events = event_log.query({"source": "slot_history"})

        assert len(events) == 2
        assert all(e.source == "slot_history" for e in events)

    def test_query_filter_by_event_type(self, event_log):
        """Test filtering events by event_type."""
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="ci_retry", event_type="retry_start")
        )
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="ci_retry", event_type="retry_end")
        )

        events = event_log.query({"event_type": "retry_start"})

        assert len(events) == 1
        assert events[0].event_type == "retry_start"

    def test_query_filter_by_slot_id(self, event_log):
        """Test filtering events by slot_id."""
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="slot_history",
                event_type="a",
                slot_id=1,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="slot_history",
                event_type="b",
                slot_id=2,
            )
        )

        events = event_log.query({"slot_id": 1})

        assert len(events) == 1
        assert events[0].slot_id == 1

    def test_query_filter_by_phase_id(self, event_log):
        """Test filtering events by phase_id."""
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="escalation",
                event_type="a",
                phase_id="phase-001",
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="escalation",
                event_type="b",
                phase_id="phase-002",
            )
        )

        events = event_log.query({"phase_id": "phase-001"})

        assert len(events) == 1
        assert events[0].phase_id == "phase-001"

    def test_query_filter_by_pr_number(self, event_log):
        """Test filtering events by pr_number."""
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="ci_retry",
                event_type="a",
                pr_number=100,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="ci_retry",
                event_type="b",
                pr_number=200,
            )
        )

        events = event_log.query({"pr_number": 100})

        assert len(events) == 1
        assert events[0].pr_number == 100

    def test_query_filter_by_since(self, event_log):
        """Test filtering events after a datetime."""
        now = datetime.now()
        event_log.ingest(
            TelemetryEvent(
                timestamp=now - timedelta(hours=2),
                source="slot_history",
                event_type="old",
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="slot_history",
                event_type="new",
            )
        )

        events = event_log.query({"since": now - timedelta(hours=1)})

        assert len(events) == 1
        assert events[0].event_type == "new"

    def test_query_filter_by_until(self, event_log):
        """Test filtering events before a datetime."""
        now = datetime.now()
        event_log.ingest(
            TelemetryEvent(
                timestamp=now - timedelta(hours=2),
                source="slot_history",
                event_type="old",
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="slot_history",
                event_type="new",
            )
        )

        events = event_log.query({"until": now - timedelta(hours=1)})

        assert len(events) == 1
        assert events[0].event_type == "old"

    def test_query_multiple_filters(self, event_log):
        """Test combining multiple filters."""
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="ci_retry",
                event_type="retry_start",
                slot_id=1,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="ci_retry",
                event_type="retry_end",
                slot_id=1,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=datetime.now(),
                source="slot_history",
                event_type="retry_start",
                slot_id=1,
            )
        )

        events = event_log.query({"source": "ci_retry", "event_type": "retry_start"})

        assert len(events) == 1
        assert events[0].source == "ci_retry"
        assert events[0].event_type == "retry_start"

    def test_count(self, event_log):
        """Test counting events."""
        for i in range(5):
            event_log.ingest(
                TelemetryEvent(
                    timestamp=datetime.now(),
                    source="slot_history" if i % 2 == 0 else "ci_retry",
                    event_type="test",
                )
            )

        total = event_log.count()
        slot_history_count = event_log.count({"source": "slot_history"})

        assert total == 5
        assert slot_history_count == 3

    def test_get_sources(self, event_log):
        """Test getting unique sources."""
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="slot_history", event_type="a")
        )
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="ci_retry", event_type="b")
        )
        event_log.ingest(
            TelemetryEvent(timestamp=datetime.now(), source="slot_history", event_type="c")
        )

        sources = event_log.get_sources()

        assert sources == ["ci_retry", "slot_history"]

    def test_correlate_by_slot(self, event_log):
        """Test correlating events by slot_id."""
        now = datetime.now()
        event_log.ingest(
            TelemetryEvent(
                timestamp=now - timedelta(hours=1),
                source="slot_history",
                event_type="filled",
                slot_id=1,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="ci_retry",
                event_type="retry",
                slot_id=1,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="slot_history",
                event_type="other",
                slot_id=2,
            )
        )

        events = event_log.correlate_by_slot(1)

        assert len(events) == 2
        assert events[0].event_type == "filled"
        assert events[1].event_type == "retry"

    def test_correlate_by_pr(self, event_log):
        """Test correlating events by pr_number."""
        now = datetime.now()
        event_log.ingest(
            TelemetryEvent(
                timestamp=now - timedelta(hours=1),
                source="ci_retry",
                event_type="ci_start",
                pr_number=123,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="escalation",
                event_type="escalated",
                pr_number=123,
            )
        )
        event_log.ingest(
            TelemetryEvent(
                timestamp=now,
                source="ci_retry",
                event_type="ci_start",
                pr_number=456,
            )
        )

        events = event_log.correlate_by_pr(123)

        assert len(events) == 2
        assert events[0].event_type == "ci_start"
        assert events[1].event_type == "escalated"
