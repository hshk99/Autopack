"""Tests for IMP-TRIGGER-002: Event-Driven Architecture.

This module tests the event bus, event types, filters, and handlers
for the Autopack event-driven architecture.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that EventType enum has expected values."""
        from autopack.events import EventType

        assert EventType.PHASE_STARTED.value == "phase.started"
        assert EventType.PHASE_COMPLETED.value == "phase.completed"
        assert EventType.RESEARCH_GAP_DETECTED.value == "research.gap_detected"
        assert EventType.BUILD_DECISION_MADE.value == "build.decision_made"
        assert EventType.MODEL_SELECTED.value == "model.selected"
        assert EventType.SESSION_STARTED.value == "session.started"
        assert EventType.ERROR_OCCURRED.value == "error.occurred"

    def test_event_type_from_string(self):
        """Test creating EventType from string value."""
        from autopack.events import EventType

        assert EventType.from_string("phase.started") == EventType.PHASE_STARTED
        assert EventType.from_string("research.completed") == EventType.RESEARCH_COMPLETED

    def test_event_type_from_string_invalid(self):
        """Test that invalid string raises ValueError."""
        from autopack.events import EventType

        with pytest.raises(ValueError, match="Unknown event type"):
            EventType.from_string("invalid.type")

    def test_event_type_category(self):
        """Test EventType category property."""
        from autopack.events import EventType

        assert EventType.PHASE_STARTED.category == "phase"
        assert EventType.RESEARCH_GAP_DETECTED.category == "research"
        assert EventType.BUILD_DECISION_MADE.category == "build"
        assert EventType.MODEL_SELECTED.category == "model"


class TestEventPriority:
    """Tests for EventPriority enum."""

    def test_priority_ordering(self):
        """Test that priorities are correctly ordered."""
        from autopack.events import EventPriority

        assert EventPriority.LOW.value < EventPriority.NORMAL.value
        assert EventPriority.NORMAL.value < EventPriority.HIGH.value
        assert EventPriority.HIGH.value < EventPriority.CRITICAL.value


class TestEvent:
    """Tests for Event dataclass."""

    def test_create_event_minimal(self):
        """Test creating an Event with minimal data."""
        from autopack.events import Event, EventType

        event = Event.create(
            event_type=EventType.PHASE_STARTED,
            source="test-source",
        )

        assert event.type == EventType.PHASE_STARTED
        assert event.source == "test-source"
        assert event.payload == {}
        assert isinstance(event.timestamp, datetime)
        assert len(event.event_id) > 0
        assert len(event.correlation_id) > 0

    def test_create_event_with_payload(self):
        """Test creating an Event with payload."""
        from autopack.events import Event, EventType

        payload = {"phase": "research", "step": 1}
        event = Event.create(
            event_type=EventType.PHASE_STARTED,
            source="orchestrator",
            payload=payload,
        )

        assert event.payload == payload
        assert event.payload["phase"] == "research"

    def test_create_event_with_correlation_id(self):
        """Test creating an Event with custom correlation ID."""
        from autopack.events import Event, EventType

        event = Event.create(
            event_type=EventType.PHASE_STARTED,
            source="test",
            correlation_id="my-session-123",
        )

        assert event.correlation_id == "my-session-123"

    def test_event_validation_invalid_source(self):
        """Test that Event validates source."""
        from autopack.events import Event, EventType

        with pytest.raises(ValueError, match="source must be a non-empty string"):
            Event(
                type=EventType.PHASE_STARTED,
                timestamp=datetime.utcnow(),
                payload={},
                source="",
                correlation_id="test-123",
            )

    def test_event_validation_invalid_payload(self):
        """Test that Event validates payload type."""
        from autopack.events import Event, EventType

        with pytest.raises(ValueError, match="payload must be a dictionary"):
            Event(
                type=EventType.PHASE_STARTED,
                timestamp=datetime.utcnow(),
                payload="not a dict",
                source="test-source",
                correlation_id="test-123",
            )

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        from autopack.events import Event, EventType

        event = Event.create(
            event_type=EventType.PHASE_STARTED,
            source="test-source",
            payload={"key": "value"},
        )

        event_dict = event.to_dict()

        assert event_dict["type"] == "phase.started"
        assert event_dict["source"] == "test-source"
        assert event_dict["payload"] == {"key": "value"}
        assert "timestamp" in event_dict
        assert "event_id" in event_dict
        assert "correlation_id" in event_dict

    def test_event_from_dict(self):
        """Test creating Event from dictionary."""
        from autopack.events import Event, EventType

        data = {
            "type": "phase.started",
            "timestamp": "2024-01-15T10:30:00",
            "payload": {"test": True},
            "source": "test",
            "correlation_id": "corr-123",
        }

        event = Event.from_dict(data)

        assert event.type == EventType.PHASE_STARTED
        assert event.payload == {"test": True}
        assert event.source == "test"

    def test_event_with_correlation_id(self):
        """Test creating event copy with new correlation ID."""
        from autopack.events import Event, EventType

        original = Event.create(
            event_type=EventType.PHASE_STARTED,
            source="test",
            payload={"data": "value"},
        )

        copy = original.with_correlation_id("new-corr-id")

        assert copy.correlation_id == "new-corr-id"
        assert copy.event_id != original.event_id
        assert copy.type == original.type
        assert copy.payload == original.payload

    def test_event_category_property(self):
        """Test Event category property."""
        from autopack.events import Event, EventType

        event = Event.create(EventType.RESEARCH_GAP_DETECTED, "test")
        assert event.category == "research"


class TestEventFilter:
    """Tests for EventFilter."""

    def test_filter_all_events(self):
        """Test filter that matches all events."""
        from autopack.events import Event, EventFilter, EventType

        filter_ = EventFilter.all_events()
        event = Event.create(EventType.PHASE_STARTED, "test")

        assert filter_.matches(event) is True

    def test_filter_by_type(self):
        """Test filter by specific event type."""
        from autopack.events import Event, EventFilter, EventType

        filter_ = EventFilter.for_type(EventType.PHASE_STARTED)

        matching = Event.create(EventType.PHASE_STARTED, "test")
        non_matching = Event.create(EventType.PHASE_COMPLETED, "test")

        assert filter_.matches(matching) is True
        assert filter_.matches(non_matching) is False

    def test_filter_by_multiple_types(self):
        """Test filter by multiple event types."""
        from autopack.events import Event, EventFilter, EventType

        filter_ = EventFilter.for_types(
            EventType.PHASE_STARTED,
            EventType.PHASE_COMPLETED,
        )

        assert filter_.matches(Event.create(EventType.PHASE_STARTED, "test")) is True
        assert filter_.matches(Event.create(EventType.PHASE_COMPLETED, "test")) is True
        assert filter_.matches(Event.create(EventType.PHASE_FAILED, "test")) is False

    def test_filter_by_category(self):
        """Test filter by event category."""
        from autopack.events import Event, EventFilter, EventType

        filter_ = EventFilter.for_category("phase")

        assert filter_.matches(Event.create(EventType.PHASE_STARTED, "test")) is True
        assert filter_.matches(Event.create(EventType.PHASE_COMPLETED, "test")) is True
        assert filter_.matches(Event.create(EventType.RESEARCH_STARTED, "test")) is False

    def test_filter_by_priority(self):
        """Test filter by minimum priority."""
        from autopack.events import Event, EventFilter, EventPriority, EventType

        filter_ = EventFilter(min_priority=EventPriority.HIGH)

        low = Event.create(EventType.PHASE_STARTED, "test", priority=EventPriority.LOW)
        high = Event.create(EventType.PHASE_STARTED, "test", priority=EventPriority.HIGH)
        critical = Event.create(EventType.PHASE_STARTED, "test", priority=EventPriority.CRITICAL)

        assert filter_.matches(low) is False
        assert filter_.matches(high) is True
        assert filter_.matches(critical) is True


class TestEventBus:
    """Tests for EventBus."""

    @pytest.fixture
    def bus(self):
        """Create an EventBus instance."""
        from autopack.events import EventBus

        return EventBus()

    def test_initial_state(self, bus):
        """Test initial state of EventBus."""
        assert bus.get_subscription_count() == 0
        assert len(bus.get_event_history()) == 0

    def test_subscribe(self, bus):
        """Test subscribing to events."""
        from autopack.events import EventFilter

        handler = MagicMock()
        sub_id = bus.subscribe(handler, EventFilter.all_events())

        assert sub_id is not None
        assert bus.get_subscription_count() == 1

    def test_subscribe_to_type(self, bus):
        """Test subscribing to a specific event type."""
        from autopack.events import EventType

        handler = MagicMock()
        sub_id = bus.subscribe_to_type(EventType.PHASE_STARTED, handler)

        assert sub_id is not None
        assert bus.get_subscription_count() == 1

    def test_subscribe_to_category(self, bus):
        """Test subscribing to an event category."""
        handler = MagicMock()
        sub_id = bus.subscribe_to_category("phase", handler)

        assert sub_id is not None
        assert bus.get_subscription_count() == 1

    def test_subscribe_invalid_handler(self, bus):
        """Test that subscribing with non-callable raises error."""
        from autopack.events import EventFilter

        with pytest.raises(ValueError, match="Handler must be callable"):
            bus.subscribe("not callable", EventFilter.all_events())

    def test_unsubscribe(self, bus):
        """Test unsubscribing from events."""
        from autopack.events import EventFilter

        handler = MagicMock()
        sub_id = bus.subscribe(handler, EventFilter.all_events())
        assert bus.get_subscription_count() == 1

        result = bus.unsubscribe(sub_id)

        assert result is True
        assert bus.get_subscription_count() == 0

    def test_unsubscribe_nonexistent(self, bus):
        """Test unsubscribing with invalid ID."""
        result = bus.unsubscribe("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_calls_handler(self, bus):
        """Test that publishing an event calls registered handler."""
        from autopack.events import Event, EventFilter, EventType

        handler = AsyncMock()
        bus.subscribe(handler, EventFilter.all_events())

        event = Event.create(EventType.PHASE_STARTED, "test")
        count = await bus.publish(event)

        assert count == 1
        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_publish_multiple_handlers(self, bus):
        """Test that publishing calls multiple handlers."""
        from autopack.events import Event, EventFilter, EventType

        handler1 = AsyncMock()
        handler2 = AsyncMock()

        bus.subscribe(handler1, EventFilter.all_events())
        bus.subscribe(handler2, EventFilter.all_events())

        event = Event.create(EventType.PHASE_STARTED, "test")
        count = await bus.publish(event)

        assert count == 2
        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_publish_filters_handlers(self, bus):
        """Test that publish only calls matching handlers."""
        from autopack.events import Event, EventFilter, EventType

        phase_handler = AsyncMock()
        research_handler = AsyncMock()

        bus.subscribe(phase_handler, EventFilter.for_category("phase"))
        bus.subscribe(research_handler, EventFilter.for_category("research"))

        event = Event.create(EventType.PHASE_STARTED, "test")
        count = await bus.publish(event)

        assert count == 1
        phase_handler.assert_called_once_with(event)
        research_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_no_handlers(self, bus):
        """Test publishing when no handlers are registered."""
        from autopack.events import Event, EventType

        event = Event.create(EventType.PHASE_STARTED, "test")
        count = await bus.publish(event)

        assert count == 0

    @pytest.mark.asyncio
    async def test_publish_handler_exception(self, bus):
        """Test that handler exception doesn't prevent other handlers."""
        from autopack.events import Event, EventFilter, EventType

        failing_handler = MagicMock(side_effect=Exception("Handler error"))
        working_handler = AsyncMock()

        bus.subscribe(failing_handler, EventFilter.all_events())
        bus.subscribe(working_handler, EventFilter.all_events())

        event = Event.create(EventType.PHASE_STARTED, "test")
        count = await bus.publish(event)

        assert count == 1  # Only the working handler succeeded
        working_handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_emit_convenience_method(self, bus):
        """Test emit() convenience method."""
        from autopack.events import EventFilter, EventType

        handler = AsyncMock()
        bus.subscribe(handler, EventFilter.all_events())

        count = await bus.emit(
            EventType.PHASE_STARTED,
            "orchestrator",
            payload={"phase": "research"},
        )

        assert count == 1
        handler.assert_called_once()
        event = handler.call_args[0][0]
        assert event.type == EventType.PHASE_STARTED
        assert event.payload == {"phase": "research"}

    def test_event_history(self, bus):
        """Test event history recording."""
        from autopack.events import Event, EventType

        async def run_test():
            event1 = Event.create(EventType.PHASE_STARTED, "source1")
            event2 = Event.create(EventType.PHASE_COMPLETED, "source2")

            await bus.publish(event1)
            await bus.publish(event2)

            history = bus.get_event_history()
            assert len(history) == 2
            # Most recent first
            assert history[0].source == "source2"
            assert history[1].source == "source1"

        import asyncio

        asyncio.run(run_test())

    def test_event_history_filtering(self, bus):
        """Test filtering event history."""
        from autopack.events import Event, EventType

        async def run_test():
            await bus.publish(Event.create(EventType.PHASE_STARTED, "source1"))
            await bus.publish(Event.create(EventType.RESEARCH_STARTED, "source2"))
            await bus.publish(Event.create(EventType.PHASE_COMPLETED, "source1"))

            phase_history = bus.get_event_history(event_type=EventType.PHASE_STARTED)
            assert len(phase_history) == 1

            source1_history = bus.get_event_history(source="source1")
            assert len(source1_history) == 2

        import asyncio

        asyncio.run(run_test())

    @pytest.mark.asyncio
    async def test_dead_letter_queue(self, bus):
        """Test that failed handlers add to dead letter queue."""
        from autopack.events import Event, EventFilter, EventType

        failing_handler = MagicMock(side_effect=Exception("Test error"))
        bus.subscribe(failing_handler, EventFilter.all_events())

        event = Event.create(EventType.PHASE_STARTED, "test")
        await bus.publish(event)

        dead_letters = bus.get_dead_letters()
        assert len(dead_letters) == 1
        assert dead_letters[0].event == event
        assert str(dead_letters[0].error) == "Test error"

    def test_clear_history(self, bus):
        """Test clearing event history."""
        from autopack.events import Event, EventType

        async def run_test():
            await bus.publish(Event.create(EventType.PHASE_STARTED, "test"))
            assert len(bus.get_event_history()) > 0

            bus.clear_history()

            assert len(bus.get_event_history()) == 0

        import asyncio

        asyncio.run(run_test())

    def test_get_summary(self, bus):
        """Test getting EventBus summary."""
        from autopack.events import EventFilter

        handler = MagicMock()
        bus.subscribe(handler, EventFilter.all_events())

        summary = bus.get_summary()

        assert summary["total_subscriptions"] == 1
        assert summary["history_size"] == 0
        assert "max_history" in summary
        assert "dead_letters" in summary


class TestGlobalEventBus:
    """Tests for global event bus functions."""

    def test_get_event_bus(self):
        """Test getting global event bus."""
        from autopack.events import get_event_bus, reset_event_bus

        reset_event_bus()  # Ensure clean state

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2  # Same instance

    def test_reset_event_bus(self):
        """Test resetting global event bus."""
        from autopack.events import get_event_bus, reset_event_bus

        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()

        assert bus1 is not bus2  # New instance


class TestLoggingHandler:
    """Tests for LoggingHandler."""

    @pytest.mark.asyncio
    async def test_logging_handler(self, caplog):
        """Test LoggingHandler logs events."""
        import logging

        from autopack.events import Event, EventType, LoggingHandler

        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.INFO):
            event = Event.create(EventType.PHASE_STARTED, "test-source")
            await handler(event)

        assert "phase.started" in caplog.text
        assert "test-source" in caplog.text

    @pytest.mark.asyncio
    async def test_logging_handler_error_level(self, caplog):
        """Test LoggingHandler uses ERROR level for error events."""
        import logging

        from autopack.events import Event, EventType, LoggingHandler

        handler = LoggingHandler()

        with caplog.at_level(logging.ERROR):
            event = Event.create(EventType.ERROR_OCCURRED, "test")
            await handler(event)

        assert "error.occurred" in caplog.text


class TestMetricsHandler:
    """Tests for MetricsHandler."""

    @pytest.mark.asyncio
    async def test_metrics_collection(self):
        """Test MetricsHandler collects metrics."""
        from autopack.events import Event, EventType, MetricsHandler

        handler = MetricsHandler()

        await handler(Event.create(EventType.PHASE_STARTED, "source1"))
        await handler(Event.create(EventType.PHASE_COMPLETED, "source1"))
        await handler(Event.create(EventType.RESEARCH_STARTED, "source2"))

        metrics = handler.get_metrics()

        assert metrics["total_events"] == 3
        assert metrics["counts_by_type"]["phase.started"] == 1
        assert metrics["counts_by_type"]["phase.completed"] == 1
        assert metrics["counts_by_category"]["phase"] == 2
        assert metrics["counts_by_category"]["research"] == 1

    @pytest.mark.asyncio
    async def test_metrics_reset(self):
        """Test MetricsHandler reset."""
        from autopack.events import Event, EventType, MetricsHandler

        handler = MetricsHandler()

        await handler(Event.create(EventType.PHASE_STARTED, "test"))
        assert handler.get_metrics()["total_events"] == 1

        handler.reset_metrics()
        assert handler.get_metrics()["total_events"] == 0


class TestAuditHandler:
    """Tests for AuditHandler."""

    @pytest.mark.asyncio
    async def test_audit_logging(self):
        """Test AuditHandler records events."""
        from autopack.events import AuditHandler, Event, EventType

        handler = AuditHandler()

        event = Event.create(EventType.APPROVAL_GRANTED, "approvals", {"user": "admin"})
        await handler(event)

        log = handler.get_audit_log()
        assert len(log) == 1
        assert log[0]["event_type"] == "approval.granted"
        assert log[0]["payload"] == {"user": "admin"}

    @pytest.mark.asyncio
    async def test_audit_filtering(self):
        """Test AuditHandler filters by event type."""
        from autopack.events import AuditHandler, Event, EventType

        handler = AuditHandler(audit_types={EventType.APPROVAL_GRANTED})

        await handler(Event.create(EventType.APPROVAL_GRANTED, "test"))
        await handler(Event.create(EventType.PHASE_STARTED, "test"))

        log = handler.get_audit_log()
        assert len(log) == 1
        assert log[0]["event_type"] == "approval.granted"


class TestChainHandler:
    """Tests for ChainHandler."""

    @pytest.mark.asyncio
    async def test_chain_invokes_all(self):
        """Test ChainHandler invokes all handlers."""
        from autopack.events import (
            ChainHandler,
            Event,
            EventType,
            LoggingHandler,
            MetricsHandler,
        )

        metrics = MetricsHandler()
        logging_handler = LoggingHandler()
        chain = ChainHandler([logging_handler, metrics])

        event = Event.create(EventType.PHASE_STARTED, "test")
        await chain(event)

        assert metrics.get_metrics()["total_events"] == 1

    @pytest.mark.asyncio
    async def test_chain_stops_on_error(self):
        """Test ChainHandler stops on error (continue_on_error=False)."""
        from autopack.events import (
            BaseEventHandler,
            ChainHandler,
            Event,
            EventType,
            MetricsHandler,
        )

        class FailingHandler(BaseEventHandler):
            async def handle(self, event):
                raise Exception("Intentional failure")

        failing = FailingHandler()
        metrics = MetricsHandler()
        chain = ChainHandler([failing, metrics], continue_on_error=False)

        with pytest.raises(Exception, match="Intentional failure"):
            await chain(Event.create(EventType.PHASE_STARTED, "test"))

        # Metrics handler should not have been called
        assert metrics.get_metrics()["total_events"] == 0

    @pytest.mark.asyncio
    async def test_chain_continues_on_error(self):
        """Test ChainHandler continues on error when configured."""
        from autopack.events import (
            BaseEventHandler,
            ChainHandler,
            Event,
            EventType,
            MetricsHandler,
        )

        class FailingHandler(BaseEventHandler):
            async def handle(self, event):
                raise Exception("Intentional failure")

        failing = FailingHandler()
        metrics = MetricsHandler()
        chain = ChainHandler([failing, metrics], continue_on_error=True)

        # Should not raise
        await chain(Event.create(EventType.PHASE_STARTED, "test"))

        # Metrics handler should still have been called
        assert metrics.get_metrics()["total_events"] == 1


class TestPersistenceHandler:
    """Tests for PersistenceHandler."""

    @pytest.mark.asyncio
    async def test_persistence_writes_events(self, tmp_path):
        """Test PersistenceHandler writes events to file."""
        import json

        from autopack.events import Event, EventType, PersistenceHandler

        output_path = tmp_path / "events.jsonl"
        handler = PersistenceHandler(output_path, flush_interval=1)

        event = Event.create(EventType.PHASE_STARTED, "test", {"key": "value"})
        await handler(event)

        # Read the file
        with open(output_path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["type"] == "phase.started"
        assert data["payload"] == {"key": "value"}


class TestConditionalHandler:
    """Tests for ConditionalHandler."""

    @pytest.mark.asyncio
    async def test_conditional_invokes_when_true(self):
        """Test ConditionalHandler invokes inner when condition is true."""
        from autopack.events import (
            ConditionalHandler,
            Event,
            EventPriority,
            EventType,
            MetricsHandler,
        )

        metrics = MetricsHandler()
        handler = ConditionalHandler(
            inner=metrics,
            condition=lambda e: e.priority == EventPriority.HIGH,
        )

        high = Event.create(EventType.PHASE_STARTED, "test", priority=EventPriority.HIGH)
        await handler(high)

        assert metrics.get_metrics()["total_events"] == 1

    @pytest.mark.asyncio
    async def test_conditional_skips_when_false(self):
        """Test ConditionalHandler skips when condition is false."""
        from autopack.events import (
            ConditionalHandler,
            Event,
            EventPriority,
            EventType,
            MetricsHandler,
        )

        metrics = MetricsHandler()
        handler = ConditionalHandler(
            inner=metrics,
            condition=lambda e: e.priority == EventPriority.HIGH,
        )

        low = Event.create(EventType.PHASE_STARTED, "test", priority=EventPriority.LOW)
        await handler(low)

        assert metrics.get_metrics()["total_events"] == 0
        assert handler.get_stats()["skipped_count"] == 1
