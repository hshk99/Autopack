"""Tests for cross-artifact telemetry correlator."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.correlator import CausationChain, CorrelatedEvent, TelemetryCorrelator
from telemetry.event_schema import TelemetryEvent
from telemetry.unified_event_log import UnifiedEventLog


@pytest.fixture
def temp_log_file():
    """Create a temporary file for the event log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "correlator_events.jsonl")


@pytest.fixture
def event_log(temp_log_file):
    """Create a UnifiedEventLog instance with temp file."""
    return UnifiedEventLog(log_path=temp_log_file)


@pytest.fixture
def correlator(event_log):
    """Create a TelemetryCorrelator instance."""
    return TelemetryCorrelator(event_log=event_log)


@pytest.fixture
def base_time():
    """Return a fixed base time for testing."""
    return datetime(2024, 1, 15, 10, 0, 0)


class TestCorrelatedEvent:
    """Tests for CorrelatedEvent dataclass."""

    def test_create_correlated_event(self):
        """Test creating a CorrelatedEvent with all fields."""
        primary = TelemetryEvent(
            timestamp=datetime.now(),
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
        )
        related = TelemetryEvent(
            timestamp=datetime.now(),
            source="ci_retry",
            event_type="retry_triggered",
            slot_id=1,
        )

        correlated = CorrelatedEvent(
            primary_event=primary,
            related_events=[related],
            correlation_confidence=0.8,
            inferred_root_cause="slot_history: slot_filled",
            correlation_type="component",
        )

        assert correlated.primary_event == primary
        assert len(correlated.related_events) == 1
        assert correlated.correlation_confidence == 0.8
        assert correlated.inferred_root_cause == "slot_history: slot_filled"
        assert correlated.correlation_type == "component"

    def test_correlated_event_with_no_primary(self):
        """Test creating CorrelatedEvent with no primary event."""
        correlated = CorrelatedEvent(
            primary_event=None,
            related_events=[],
            correlation_confidence=0.0,
            inferred_root_cause=None,
            correlation_type="none",
        )

        assert correlated.primary_event is None
        assert correlated.related_events == []
        assert correlated.correlation_confidence == 0.0


class TestCausationChain:
    """Tests for CausationChain dataclass."""

    def test_create_causation_chain(self, base_time):
        """Test creating a CausationChain with multiple events."""
        event1 = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
        )
        event2 = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=1),
            source="ci_retry",
            event_type="ci_started",
            slot_id=1,
        )
        event3 = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=2),
            source="escalation",
            event_type="escalation_created",
            slot_id=1,
        )

        chain = CausationChain(
            chain_id="chain_test",
            events=[event1, event2, event3],
            root_cause_event=event1,
            final_effect_event=event3,
            confidence=0.9,
        )

        assert chain.chain_id == "chain_test"
        assert len(chain.events) == 3
        assert chain.root_cause_event == event1
        assert chain.final_effect_event == event3
        assert chain.confidence == 0.9


class TestTelemetryCorrelator:
    """Tests for TelemetryCorrelator class."""

    def test_init(self, correlator, event_log):
        """Test correlator initialization."""
        assert correlator.event_log == event_log
        assert correlator.correlation_window == timedelta(minutes=5)

    def test_correlate_slot_with_pr_no_events(self, correlator):
        """Test correlation when no events exist."""
        result = correlator.correlate_slot_with_pr(slot_id=1, pr_number=100)

        assert result.primary_event is None
        assert result.related_events == []
        assert result.correlation_confidence == 0.0
        assert result.inferred_root_cause is None
        assert result.correlation_type == "none"

    def test_correlate_slot_with_pr_single_event(self, correlator, event_log, base_time):
        """Test correlation with a single matching event."""
        event = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
            pr_number=100,
        )
        event_log.ingest(event)

        result = correlator.correlate_slot_with_pr(slot_id=1, pr_number=100)

        assert result.primary_event is not None
        assert result.primary_event.event_type == "slot_filled"
        assert result.related_events == []
        assert result.correlation_type == "component"

    def test_correlate_slot_with_pr_multiple_events(self, correlator, event_log, base_time):
        """Test correlation with multiple matching events."""
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="slot_filled",
                slot_id=1,
                pr_number=100,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="ci_started",
                slot_id=1,
                pr_number=100,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="escalation",
                event_type="escalated",
                slot_id=1,
                pr_number=100,
            ),
        ]
        for event in events:
            event_log.ingest(event)

        result = correlator.correlate_slot_with_pr(slot_id=1, pr_number=100)

        assert result.primary_event is not None
        assert result.primary_event.event_type == "slot_filled"
        assert len(result.related_events) == 2
        assert result.correlation_confidence > 0.0
        assert result.inferred_root_cause == "slot_history: slot_filled"

    def test_correlate_slot_with_pr_mixed_sources(self, correlator, event_log, base_time):
        """Test correlation combining slot and PR events from different sources."""
        # Event with only slot_id
        event_log.ingest(
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="slot_filled",
                slot_id=1,
            )
        )
        # Event with only pr_number
        event_log.ingest(
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="ci_started",
                pr_number=100,
            )
        )
        # Event with both
        event_log.ingest(
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="nudge_state",
                event_type="nudge_sent",
                slot_id=1,
                pr_number=100,
            )
        )

        result = correlator.correlate_slot_with_pr(slot_id=1, pr_number=100)

        assert result.primary_event is not None
        # Should have found 3 unique events
        total_events = 1 + len(result.related_events)
        assert total_events == 3

    def test_find_causation_chain_single_event(self, correlator, event_log, base_time):
        """Test causation chain with single event."""
        event = TelemetryEvent(
            timestamp=base_time,
            source="escalation",
            event_type="escalation_created",
            slot_id=1,
        )
        event_log.ingest(event)

        chain = correlator.find_causation_chain(event)

        assert chain.chain_id.startswith("chain_")
        assert len(chain.events) == 1
        assert chain.root_cause_event == event
        assert chain.final_effect_event == event
        assert chain.confidence == 0.0  # Single event has no chain confidence

    def test_find_causation_chain_multiple_events(self, correlator, event_log, base_time):
        """Test causation chain traces back through related events."""
        # Create a series of related events
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="slot_filled",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="ci_failed",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="escalation",
                event_type="escalation_created",
                slot_id=1,
            ),
        ]
        for event in events:
            event_log.ingest(event)

        # Start from the final event and trace back
        chain = correlator.find_causation_chain(events[-1])

        assert len(chain.events) >= 1
        assert chain.final_effect_event == events[-1]
        # Root cause should be an earlier event
        assert chain.root_cause_event.timestamp <= events[-1].timestamp

    def test_find_causation_chain_respects_slot_id(self, correlator, event_log, base_time):
        """Test that causation chain only considers events with same slot_id."""
        # Events for slot 1
        event_slot1 = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
        )
        # Events for slot 2 (should not be included)
        event_slot2 = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=1),
            source="ci_retry",
            event_type="ci_failed",
            slot_id=2,
        )
        # Final event for slot 1
        final_event = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=2),
            source="escalation",
            event_type="escalation_created",
            slot_id=1,
        )

        event_log.ingest(event_slot1)
        event_log.ingest(event_slot2)
        event_log.ingest(final_event)

        chain = correlator.find_causation_chain(final_event)

        # Should not include event from slot 2
        for event in chain.events:
            assert event.slot_id == 1 or event.slot_id is None

    def test_correlate_by_timewindow_no_related_events(self, correlator, event_log, base_time):
        """Test time window correlation with no related events."""
        event = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
        )
        event_log.ingest(event)

        results = correlator.correlate_by_timewindow(event)

        assert results == []

    def test_correlate_by_timewindow_finds_related_events(self, correlator, event_log, base_time):
        """Test time window correlation finds events within window."""
        center_event = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
        )
        related_event = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=2),
            source="ci_retry",
            event_type="ci_started",
        )
        event_log.ingest(center_event)
        event_log.ingest(related_event)

        results = correlator.correlate_by_timewindow(center_event)

        assert len(results) == 1
        assert results[0].primary_event == center_event
        assert results[0].related_events[0].event_type == "ci_started"
        assert results[0].correlation_type == "temporal"

    def test_correlate_by_timewindow_excludes_events_outside_window(
        self, correlator, event_log, base_time
    ):
        """Test time window correlation excludes events outside window."""
        center_event = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
        )
        # Event outside default 5-minute window
        outside_event = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=10),
            source="ci_retry",
            event_type="ci_started",
        )
        event_log.ingest(center_event)
        event_log.ingest(outside_event)

        results = correlator.correlate_by_timewindow(center_event)

        assert results == []

    def test_correlate_by_timewindow_custom_window(self, correlator, event_log, base_time):
        """Test time window correlation with custom window size."""
        center_event = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
        )
        event_log.ingest(center_event)
        event_log.ingest(
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=8),
                source="ci_retry",
                event_type="ci_started",
            )
        )

        # Default window (5 min) should not find it
        results_default = correlator.correlate_by_timewindow(center_event)
        assert results_default == []

        # Custom 10-minute window should find it
        results_custom = correlator.correlate_by_timewindow(
            center_event, window=timedelta(minutes=10)
        )
        assert len(results_custom) == 1

    def test_temporal_confidence_closer_events_higher_confidence(self, correlator, base_time):
        """Test that closer events have higher temporal confidence."""
        event1 = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="a",
        )
        event_close = TelemetryEvent(
            timestamp=base_time + timedelta(seconds=30),
            source="ci_retry",
            event_type="b",
        )
        event_far = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=4),
            source="ci_retry",
            event_type="c",
        )

        conf_close = correlator._temporal_confidence(event1, event_close)
        conf_far = correlator._temporal_confidence(event1, event_far)

        assert conf_close > conf_far
        assert conf_close >= 0.9  # Very close events
        assert conf_far < 0.3  # Events 4 minutes apart in 5 min window

    def test_calculate_confidence_based_on_event_count(self, correlator, base_time):
        """Test that more events lead to higher confidence."""
        events_few = [
            TelemetryEvent(timestamp=base_time, source="slot_history", event_type="a"),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="b",
            ),
        ]
        events_many = events_few + [
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="escalation",
                event_type="c",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=3),
                source="nudge_state",
                event_type="d",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=4),
                source="slot_history",
                event_type="e",
            ),
        ]

        conf_few = correlator._calculate_confidence(events_few)
        conf_many = correlator._calculate_confidence(events_many)

        assert conf_few < conf_many
        assert conf_many == 1.0  # 5+ events should hit max confidence

    def test_infer_root_cause_finds_earliest_event(self, correlator, base_time):
        """Test that inferred root cause is the earliest event."""
        events = [
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="escalation",
                event_type="escalated",
            ),
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="slot_filled",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="ci_failed",
            ),
        ]

        root_cause = correlator._infer_root_cause(events)

        assert root_cause == "slot_history: slot_filled"

    def test_infer_root_cause_empty_list(self, correlator):
        """Test that empty event list returns None for root cause."""
        root_cause = correlator._infer_root_cause([])

        assert root_cause is None

    def test_chain_confidence_higher_for_tight_timing(self, correlator, base_time):
        """Test that chains with tighter timing have higher confidence."""
        tight_chain = [
            TelemetryEvent(timestamp=base_time, source="slot_history", event_type="a"),
            TelemetryEvent(
                timestamp=base_time + timedelta(seconds=10),
                source="ci_retry",
                event_type="b",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(seconds=20),
                source="escalation",
                event_type="c",
            ),
        ]
        loose_chain = [
            TelemetryEvent(timestamp=base_time, source="slot_history", event_type="a"),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=3),
                source="ci_retry",
                event_type="b",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=4, seconds=30),
                source="escalation",
                event_type="c",
            ),
        ]

        tight_conf = correlator._chain_confidence(tight_chain)
        loose_conf = correlator._chain_confidence(loose_chain)

        assert tight_conf > loose_conf
        assert tight_conf > 0.9
