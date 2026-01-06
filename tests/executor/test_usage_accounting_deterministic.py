"""Contract-first tests for usage accounting determinism (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Same usage events → same computed totals
- Stable, sorted aggregation (no nondeterministic ordering)
- All inputs explicit and testable
"""

from __future__ import annotations

from datetime import datetime, timezone


def test_aggregate_usage_deterministic_same_events():
    """Same usage events always produce identical totals."""
    from autopack.executor.usage_accounting import UsageEvent, aggregate_usage

    events = [
        UsageEvent(
            event_id="evt-001",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tokens_used=1000,
            context_chars_used=5000,
            sot_chars_used=200,
        ),
        UsageEvent(
            event_id="evt-002",
            timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            tokens_used=500,
            context_chars_used=2500,
            sot_chars_used=100,
        ),
    ]

    # Run aggregation multiple times
    result1 = aggregate_usage(events)
    result2 = aggregate_usage(events)
    result3 = aggregate_usage(events)

    # All results must be identical
    assert result1 == result2 == result3
    assert result1.tokens_used == 1500
    assert result1.context_chars_used == 7500
    assert result1.sot_chars_used == 300


def test_aggregate_usage_order_independent():
    """Aggregation produces same result regardless of input event order."""
    from autopack.executor.usage_accounting import UsageEvent, aggregate_usage

    base_events = [
        UsageEvent(
            event_id="evt-001",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tokens_used=1000,
            context_chars_used=5000,
            sot_chars_used=200,
        ),
        UsageEvent(
            event_id="evt-002",
            timestamp=datetime(2025, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
            tokens_used=500,
            context_chars_used=2500,
            sot_chars_used=100,
        ),
        UsageEvent(
            event_id="evt-003",
            timestamp=datetime(2025, 1, 1, 11, 55, 0, tzinfo=timezone.utc),
            tokens_used=250,
            context_chars_used=1250,
            sot_chars_used=50,
        ),
    ]

    # Different orderings
    order1 = [base_events[0], base_events[1], base_events[2]]
    order2 = [base_events[2], base_events[0], base_events[1]]
    order3 = [base_events[1], base_events[2], base_events[0]]

    result1 = aggregate_usage(order1)
    result2 = aggregate_usage(order2)
    result3 = aggregate_usage(order3)

    # All must produce same totals
    assert result1 == result2 == result3


def test_aggregate_usage_empty_events():
    """Empty event list returns zero totals (valid state)."""
    from autopack.executor.usage_accounting import aggregate_usage

    result = aggregate_usage([])

    assert result.tokens_used == 0
    assert result.context_chars_used == 0
    assert result.sot_chars_used == 0


def test_load_usage_events_from_artifact():
    """Usage events can be loaded from run-local artifact path."""
    import json
    import tempfile
    from pathlib import Path

    from autopack.executor.usage_accounting import load_usage_events

    # Create test artifact
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_path = Path(tmpdir) / "usage_events.json"
        events_data = [
            {
                "event_id": "evt-001",
                "timestamp": "2025-01-01T12:00:00+00:00",
                "tokens_used": 1000,
                "context_chars_used": 5000,
                "sot_chars_used": 200,
            },
            {
                "event_id": "evt-002",
                "timestamp": "2025-01-01T12:05:00+00:00",
                "tokens_used": 500,
                "context_chars_used": 2500,
                "sot_chars_used": 100,
            },
        ]
        artifact_path.write_text(json.dumps(events_data), encoding="utf-8")

        # Load events
        events = load_usage_events("test-run", artifact_path)

        assert len(events) == 2
        assert events[0].event_id == "evt-001"
        assert events[0].tokens_used == 1000
        assert events[1].event_id == "evt-002"


def test_load_usage_events_missing_artifact():
    """Missing artifact returns empty list (not an error)."""
    from pathlib import Path

    from autopack.executor.usage_accounting import load_usage_events

    result = load_usage_events("test-run", Path("/nonexistent/path/events.json"))

    assert result == []


def test_usage_totals_is_hashable():
    """UsageTotals can be hashed for caching/deduplication."""
    from autopack.executor.usage_accounting import UsageTotals

    totals1 = UsageTotals(tokens_used=1000, context_chars_used=5000, sot_chars_used=200)
    totals2 = UsageTotals(tokens_used=1000, context_chars_used=5000, sot_chars_used=200)

    # Same values should hash to same value
    assert hash(totals1) == hash(totals2)

    # Can be used in sets
    totals_set = {totals1, totals2}
    assert len(totals_set) == 1


def test_no_implicit_globals():
    """Aggregation uses only explicit inputs, no implicit state."""
    from autopack.executor.usage_accounting import UsageEvent, aggregate_usage

    # First call
    events1 = [
        UsageEvent(
            event_id="evt-a",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tokens_used=100,
            context_chars_used=500,
            sot_chars_used=20,
        ),
    ]
    result1 = aggregate_usage(events1)

    # Second call with different events
    events2 = [
        UsageEvent(
            event_id="evt-b",
            timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            tokens_used=200,
            context_chars_used=1000,
            sot_chars_used=40,
        ),
    ]
    result2 = aggregate_usage(events2)

    # Results should be independent
    assert result1.tokens_used == 100
    assert result2.tokens_used == 200
