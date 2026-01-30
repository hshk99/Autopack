"""Tests for IMP-AUTO-002: Event-Driven Workflow Triggers.

This module tests the event trigger functionality including event creation,
handler registration, and event processing.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call

import pytest


class TestEventType:
    """Tests for EventType enum."""

    def test_event_type_values(self):
        """Test that EventType enum has expected values."""
        from autopack.autonomy.event_triggers import EventType

        assert EventType.API_VERSION_UPDATE.value == "api_version_update"
        assert EventType.DEPENDENCY_UPDATE.value == "dependency_update"
        assert EventType.MARKET_SIGNAL.value == "market_signal"
        assert EventType.COMPETITOR_CHANGE.value == "competitor_change"
        assert EventType.POLICY_UPDATE.value == "policy_update"

    def test_event_type_comparison(self):
        """Test EventType enum comparison."""
        from autopack.autonomy.event_triggers import EventType

        e1 = EventType.API_VERSION_UPDATE
        e2 = EventType.API_VERSION_UPDATE
        e3 = EventType.DEPENDENCY_UPDATE

        assert e1 == e2
        assert e1 != e3


class TestWorkflowEvent:
    """Tests for WorkflowEvent dataclass."""

    def test_create_event_minimal(self):
        """Test creating a WorkflowEvent with minimal data."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="external-api",
        )

        assert event.event_type == EventType.API_VERSION_UPDATE
        assert event.source == "external-api"
        assert event.payload == {}
        assert isinstance(event.timestamp, datetime)

    def test_create_event_with_payload(self):
        """Test creating a WorkflowEvent with payload."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        payload = {"version": "2.0", "breaking_changes": True}
        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="github-api",
            payload=payload,
        )

        assert event.payload == payload
        assert event.payload["version"] == "2.0"

    def test_event_validation_invalid_source(self):
        """Test that WorkflowEvent validates source."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        with pytest.raises(ValueError, match="source must be a non-empty string"):
            WorkflowEvent(
                event_type=EventType.API_VERSION_UPDATE,
                source="",
            )

    def test_event_validation_invalid_payload(self):
        """Test that WorkflowEvent validates payload type."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        with pytest.raises(ValueError, match="payload must be a dictionary"):
            WorkflowEvent(
                event_type=EventType.API_VERSION_UPDATE,
                source="test-source",
                payload="not a dict",
            )

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        payload = {"key": "value"}
        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
            payload=payload,
        )

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "api_version_update"
        assert event_dict["source"] == "test-source"
        assert event_dict["payload"] == payload
        assert "timestamp" in event_dict


class TestEventTriggerManager:
    """Tests for EventTriggerManager."""

    @pytest.fixture
    def manager(self):
        """Create an EventTriggerManager instance."""
        from autopack.autonomy.event_triggers import EventTriggerManager

        return EventTriggerManager()

    def test_initial_state(self, manager):
        """Test initial state of EventTriggerManager."""
        assert manager.get_handler_count() == 0
        assert len(manager.get_event_history()) == 0

    def test_register_handler(self, manager):
        """Test registering an event handler."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        manager.register_handler(EventType.API_VERSION_UPDATE, handler)

        assert manager.get_handler_count(EventType.API_VERSION_UPDATE) == 1
        assert manager.get_handler_count() == 1

    def test_register_multiple_handlers(self, manager):
        """Test registering multiple handlers for the same event type."""
        from autopack.autonomy.event_triggers import EventType

        handler1 = MagicMock()
        handler2 = MagicMock()

        manager.register_handler(EventType.API_VERSION_UPDATE, handler1)
        manager.register_handler(EventType.API_VERSION_UPDATE, handler2)

        assert manager.get_handler_count(EventType.API_VERSION_UPDATE) == 2
        assert manager.get_handler_count() == 2

    def test_register_handlers_different_types(self, manager):
        """Test registering handlers for different event types."""
        from autopack.autonomy.event_triggers import EventType

        handler1 = MagicMock()
        handler2 = MagicMock()

        manager.register_handler(EventType.API_VERSION_UPDATE, handler1)
        manager.register_handler(EventType.DEPENDENCY_UPDATE, handler2)

        assert manager.get_handler_count(EventType.API_VERSION_UPDATE) == 1
        assert manager.get_handler_count(EventType.DEPENDENCY_UPDATE) == 1
        assert manager.get_handler_count() == 2

    def test_register_invalid_handler(self, manager):
        """Test that registering a non-callable raises error."""
        from autopack.autonomy.event_triggers import EventType

        with pytest.raises(ValueError, match="Handler must be callable"):
            manager.register_handler(EventType.API_VERSION_UPDATE, "not callable")

    def test_unregister_handler(self, manager):
        """Test unregistering a handler."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        manager.register_handler(EventType.API_VERSION_UPDATE, handler)
        assert manager.get_handler_count() == 1

        result = manager.unregister_handler(EventType.API_VERSION_UPDATE, handler)

        assert result is True
        assert manager.get_handler_count() == 0

    def test_unregister_nonexistent_handler(self, manager):
        """Test unregistering a handler that was not registered."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        result = manager.unregister_handler(EventType.API_VERSION_UPDATE, handler)

        assert result is False

    @pytest.mark.asyncio
    async def test_process_event_calls_handler(self, manager):
        """Test that processing an event calls registered handler."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        handler = AsyncMock()
        manager.register_handler(EventType.API_VERSION_UPDATE, handler)

        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
        )

        await manager.process_event(event)

        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_process_event_multiple_handlers(self, manager):
        """Test that processing event calls multiple handlers."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        handler1 = AsyncMock()
        handler2 = AsyncMock()

        manager.register_handler(EventType.API_VERSION_UPDATE, handler1)
        manager.register_handler(EventType.API_VERSION_UPDATE, handler2)

        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
        )

        await manager.process_event(event)

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_process_event_no_handlers(self, manager):
        """Test processing event when no handlers are registered."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
        )

        # Should not raise
        await manager.process_event(event)

    @pytest.mark.asyncio
    async def test_process_event_handler_exception(self, manager):
        """Test that handler exception doesn't prevent other handlers."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        handler1 = MagicMock(side_effect=Exception("Handler error"))
        handler2 = AsyncMock()

        manager.register_handler(EventType.API_VERSION_UPDATE, handler1)
        manager.register_handler(EventType.API_VERSION_UPDATE, handler2)

        event = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
        )

        # Should not raise
        await manager.process_event(event)

        # Second handler should still be called
        handler2.assert_called_once_with(event)

    def test_event_history(self, manager):
        """Test event history recording."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        async def run_test():
            event1 = WorkflowEvent(
                event_type=EventType.API_VERSION_UPDATE,
                source="source1",
            )
            event2 = WorkflowEvent(
                event_type=EventType.DEPENDENCY_UPDATE,
                source="source2",
            )

            await manager.process_event(event1)
            await manager.process_event(event2)

            history = manager.get_event_history()
            assert len(history) == 2
            # Most recent first
            assert history[0].source == "source2"
            assert history[1].source == "source1"

        asyncio.run(run_test())

    def test_event_history_by_type(self, manager):
        """Test filtering event history by type."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        async def run_test():
            await manager.process_event(
                WorkflowEvent(
                    event_type=EventType.API_VERSION_UPDATE,
                    source="source1",
                )
            )
            await manager.process_event(
                WorkflowEvent(
                    event_type=EventType.DEPENDENCY_UPDATE,
                    source="source2",
                )
            )
            await manager.process_event(
                WorkflowEvent(
                    event_type=EventType.API_VERSION_UPDATE,
                    source="source3",
                )
            )

            api_history = manager.get_event_history(EventType.API_VERSION_UPDATE)
            assert len(api_history) == 2
            assert all(e.event_type == EventType.API_VERSION_UPDATE for e in api_history)

        asyncio.run(run_test())

    def test_event_history_limit(self, manager):
        """Test that event history respects max size."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        # Create manager with small history size
        manager = type(manager)(max_history=3)

        async def run_test():
            for i in range(5):
                await manager.process_event(
                    WorkflowEvent(
                        event_type=EventType.API_VERSION_UPDATE,
                        source=f"source{i}",
                    )
                )

            history = manager.get_event_history()
            # Should only keep last 3
            assert len(history) == 3
            assert history[2].source == "source2"  # oldest

        asyncio.run(run_test())

    def test_clear_history(self, manager):
        """Test clearing event history."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        async def run_test():
            await manager.process_event(
                WorkflowEvent(
                    event_type=EventType.API_VERSION_UPDATE,
                    source="source1",
                )
            )

            assert len(manager.get_event_history()) > 0

            manager.clear_history()

            assert len(manager.get_event_history()) == 0

        asyncio.run(run_test())

    def test_get_summary(self, manager):
        """Test getting EventTriggerManager summary."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        manager.register_handler(EventType.API_VERSION_UPDATE, handler)

        summary = manager.get_summary()

        assert summary["total_handlers"] == 1
        assert "handlers_by_type" in summary
        assert summary["history_size"] == 0
        assert "max_history" in summary


class TestAutopilotEventIntegration:
    """Tests for EventTriggerManager integration with AutopilotController."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        from autopack.autonomy.autopilot import AutopilotController

        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_register_event_handler(self, controller):
        """Test registering an event handler on autopilot controller."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        controller.register_event_handler(EventType.API_VERSION_UPDATE, handler)

        assert controller.get_event_handler_count(EventType.API_VERSION_UPDATE) == 1

    def test_unregister_event_handler(self, controller):
        """Test unregistering an event handler."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        controller.register_event_handler(EventType.API_VERSION_UPDATE, handler)
        assert controller.get_event_handler_count() == 1

        result = controller.unregister_event_handler(EventType.API_VERSION_UPDATE, handler)

        assert result is True
        assert controller.get_event_handler_count() == 0

    @pytest.mark.asyncio
    async def test_trigger_event(self, controller):
        """Test triggering an event."""
        from autopack.autonomy.event_triggers import EventType

        handler = AsyncMock()
        controller.register_event_handler(EventType.API_VERSION_UPDATE, handler)

        await controller.trigger_event(
            event_type=EventType.API_VERSION_UPDATE,
            source="test-source",
            payload={"version": "2.0"},
        )

        handler.assert_called_once()
        event = handler.call_args[0][0]
        assert event.event_type == EventType.API_VERSION_UPDATE
        assert event.source == "test-source"
        assert event.payload == {"version": "2.0"}

    @pytest.mark.asyncio
    async def test_process_pending_events(self, controller):
        """Test processing pending events."""
        from autopack.autonomy.event_triggers import EventType, WorkflowEvent

        handler = AsyncMock()
        controller.register_event_handler(EventType.API_VERSION_UPDATE, handler)

        # Manually add events to pending queue (simulating async-queued events)
        event1 = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="source1",
        )
        event2 = WorkflowEvent(
            event_type=EventType.API_VERSION_UPDATE,
            source="source2",
        )
        controller._pending_events.append(event1)
        controller._pending_events.append(event2)

        # Process pending events
        count = await controller.process_pending_events()
        assert count == 2
        assert len(controller._pending_events) == 0
        assert handler.call_count == 2

    def test_get_event_summary(self, controller):
        """Test getting event trigger summary."""
        from autopack.autonomy.event_triggers import EventType

        handler = MagicMock()
        controller.register_event_handler(EventType.API_VERSION_UPDATE, handler)

        summary = controller.get_event_summary()

        assert summary["total_handlers"] == 1
        assert "pending_events" in summary
