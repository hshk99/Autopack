"""Tests for IMP-TEL-005: Correlator causation chain optimization.

Tests cycle detection and pre-fetching optimizations that achieve O(n) complexity
instead of O(n^2) worst case for deep causation chains.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.correlator import (DEFAULT_PREFETCH_WINDOW_HOURS,
                                  TelemetryCorrelator)
from telemetry.event_schema import TelemetryEvent
from telemetry.unified_event_log import UnifiedEventLog


@pytest.fixture
def temp_log_file():
    """Create a temporary file for the event log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "optimization_test_events.jsonl")


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


class TestCycleDetection:
    """Tests for cycle detection in causation chains (IMP-TEL-005)."""

    def test_get_event_key_creates_unique_key(self, correlator, base_time):
        """Test that _get_event_key creates unique identifiers."""
        event1 = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
        )
        event2 = TelemetryEvent(
            timestamp=base_time,
            source="slot_history",
            event_type="slot_filled",
            slot_id=2,  # Different slot_id
        )
        event3 = TelemetryEvent(
            timestamp=base_time + timedelta(seconds=1),
            source="slot_history",
            event_type="slot_filled",
            slot_id=1,
        )

        key1 = correlator._get_event_key(event1)
        key2 = correlator._get_event_key(event2)
        key3 = correlator._get_event_key(event3)

        # Same timestamp, source, event_type = same key (slot_id not in key)
        assert key1 == key2
        # Different timestamp = different key
        assert key1 != key3

    def test_cycle_detection_prevents_infinite_loop(self, correlator, event_log, base_time):
        """Test that cycle detection prevents revisiting same event."""
        # Create events where an obvious cause could be found multiple times
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
                event_type="ci_started",
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

        # Find chain - should not revisit events
        chain = correlator.find_causation_chain(events[-1])

        # Each event should only appear once
        event_keys = [correlator._get_event_key(e) for e in chain.events]
        assert len(event_keys) == len(set(event_keys))

    def test_chain_terminates_on_cycle(self, correlator, event_log, base_time):
        """Test that chain building terminates when cycle would occur."""
        # Create a long chain of events
        events = []
        for i in range(10):
            events.append(
                TelemetryEvent(
                    timestamp=base_time + timedelta(minutes=i),
                    source="slot_history",
                    event_type=f"event_{i}",
                    slot_id=1,
                )
            )
        for event in events:
            event_log.ingest(event)

        # Find chain from last event
        chain = correlator.find_causation_chain(events[-1])

        # Chain should contain unique events only
        event_keys = [correlator._get_event_key(e) for e in chain.events]
        assert len(event_keys) == len(set(event_keys))


class TestPrefetching:
    """Tests for event pre-fetching optimization (IMP-TEL-005)."""

    def test_prefetch_events_returns_events_in_window(self, correlator, event_log, base_time):
        """Test that _prefetch_events returns events within time window."""
        # Create events inside and outside window
        inside_event = TelemetryEvent(
            timestamp=base_time - timedelta(minutes=30),
            source="slot_history",
            event_type="inside",
            slot_id=1,
        )
        outside_event = TelemetryEvent(
            timestamp=base_time - timedelta(hours=2),
            source="slot_history",
            event_type="outside",
            slot_id=1,
        )
        event_log.ingest(inside_event)
        event_log.ingest(outside_event)

        # Pre-fetch with 1 hour window
        events = correlator._prefetch_events(
            end_time=base_time,
            time_window=timedelta(hours=1),
            slot_id=1,
        )

        # Should only find inside_event
        assert len(events) == 1
        assert events[0].event_type == "inside"

    def test_prefetch_events_filters_by_slot_id(self, correlator, event_log, base_time):
        """Test that _prefetch_events filters by slot_id when provided."""
        event_slot1 = TelemetryEvent(
            timestamp=base_time - timedelta(minutes=5),
            source="slot_history",
            event_type="slot1",
            slot_id=1,
        )
        event_slot2 = TelemetryEvent(
            timestamp=base_time - timedelta(minutes=5),
            source="slot_history",
            event_type="slot2",
            slot_id=2,
        )
        event_log.ingest(event_slot1)
        event_log.ingest(event_slot2)

        # Pre-fetch for slot 1 only
        events = correlator._prefetch_events(
            end_time=base_time,
            time_window=timedelta(hours=1),
            slot_id=1,
        )

        assert len(events) == 1
        assert events[0].slot_id == 1

    def test_build_time_index_groups_by_minute(self, correlator, base_time):
        """Test that _build_time_index groups events by minute buckets."""
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="a",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(seconds=30),
                source="slot_history",
                event_type="b",
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="slot_history",
                event_type="c",
            ),
        ]

        index = correlator._build_time_index(events)

        # Events a and b should be in same bucket (same minute)
        # Event c should be in different bucket
        assert len(index) == 2

    def test_get_potential_causes_filters_correctly(self, correlator, base_time):
        """Test that _get_potential_causes_from_index applies all filters."""
        effect = TelemetryEvent(
            timestamp=base_time + timedelta(minutes=5),
            source="escalation",
            event_type="effect",
            slot_id=1,
        )

        events = [
            # Valid cause: before effect, same slot, within window
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=3),
                source="ci_retry",
                event_type="valid_cause",
                slot_id=1,
            ),
            # Invalid: wrong slot
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=3),
                source="ci_retry",
                event_type="wrong_slot",
                slot_id=2,
            ),
            # Invalid: after effect
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=6),
                source="ci_retry",
                event_type="after_effect",
                slot_id=1,
            ),
        ]

        index = correlator._build_time_index(events)
        visited: set = set()

        causes = correlator._get_potential_causes_from_index(effect, index, visited)

        assert len(causes) == 1
        assert causes[0].event_type == "valid_cause"

    def test_prefetch_uses_default_window(self, correlator, event_log, base_time):
        """Test that prefetch uses DEFAULT_PREFETCH_WINDOW_HOURS."""
        # Create event just inside the default window
        event = TelemetryEvent(
            timestamp=base_time - timedelta(minutes=30),
            source="slot_history",
            event_type="inside_default",
            slot_id=1,
        )
        event_log.ingest(event)

        # Verify default window is 1 hour
        assert DEFAULT_PREFETCH_WINDOW_HOURS == 1

        events = correlator._prefetch_events(
            end_time=base_time,
            time_window=timedelta(hours=DEFAULT_PREFETCH_WINDOW_HOURS),
            slot_id=1,
        )

        assert len(events) == 1


class TestDeepChainPerformance:
    """Tests for performance with deep causation chains (IMP-TEL-005)."""

    def test_deep_chain_completes_efficiently(self, correlator, event_log, base_time):
        """Test that deep chains complete without excessive queries."""
        # Create a deep chain of 50 events
        events = []
        for i in range(50):
            events.append(
                TelemetryEvent(
                    timestamp=base_time + timedelta(seconds=i * 10),
                    source="slot_history",
                    event_type=f"event_{i}",
                    slot_id=1,
                )
            )
        for event in events:
            event_log.ingest(event)

        # Track query count
        original_query = event_log.query
        query_count = [0]

        def counting_query(*args, **kwargs):
            query_count[0] += 1
            return original_query(*args, **kwargs)

        event_log.query = counting_query

        # Find chain - should use pre-fetching (minimal queries)
        chain = correlator.find_causation_chain(events[-1])

        # With pre-fetching, should only need 1 query for the entire chain
        # (vs 50 queries without optimization)
        assert query_count[0] == 1

        # Chain should still work correctly
        assert len(chain.events) >= 1
        assert chain.final_effect_event == events[-1]

    def test_chain_handles_many_events_same_timestamp(self, correlator, event_log, base_time):
        """Test handling multiple events with same timestamp."""
        # Create events with same timestamp but different types
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="first",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time,
                source="ci_retry",
                event_type="second",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="escalation",
                event_type="third",
                slot_id=1,
            ),
        ]
        for event in events:
            event_log.ingest(event)

        chain = correlator.find_causation_chain(events[-1])

        # Should handle same-timestamp events correctly
        assert chain.final_effect_event == events[-1]
        # Chain should not have duplicates
        event_keys = [correlator._get_event_key(e) for e in chain.events]
        assert len(event_keys) == len(set(event_keys))


class TestBackwardCompatibility:
    """Tests ensuring optimization doesn't break existing functionality."""

    def test_find_causation_chain_returns_same_structure(self, correlator, event_log, base_time):
        """Test that chain structure is preserved after optimization."""
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="root",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="ci_retry",
                event_type="middle",
                slot_id=1,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=2),
                source="escalation",
                event_type="final",
                slot_id=1,
            ),
        ]
        for event in events:
            event_log.ingest(event)

        chain = correlator.find_causation_chain(events[-1])

        # Verify chain structure
        assert chain.chain_id.startswith("chain_")
        assert chain.final_effect_event == events[-1]
        assert chain.root_cause_event.timestamp <= chain.final_effect_event.timestamp
        assert 0.0 <= chain.confidence <= 1.0
        assert len(chain.events) >= 1

    def test_empty_event_log_still_works(self, correlator, base_time):
        """Test that empty log returns single-event chain."""
        event = TelemetryEvent(
            timestamp=base_time,
            source="escalation",
            event_type="orphan",
            slot_id=1,
        )

        chain = correlator.find_causation_chain(event)

        assert len(chain.events) == 1
        assert chain.events[0] == event
        assert chain.root_cause_event == event
        assert chain.final_effect_event == event

    def test_slot_id_none_still_works(self, correlator, event_log, base_time):
        """Test that events without slot_id are handled correctly."""
        events = [
            TelemetryEvent(
                timestamp=base_time,
                source="slot_history",
                event_type="no_slot_root",
                slot_id=None,
            ),
            TelemetryEvent(
                timestamp=base_time + timedelta(minutes=1),
                source="escalation",
                event_type="no_slot_final",
                slot_id=None,
            ),
        ]
        for event in events:
            event_log.ingest(event)

        chain = correlator.find_causation_chain(events[-1])

        # Should still build chain without slot_id filtering
        assert chain.final_effect_event == events[-1]
