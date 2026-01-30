"""Event-Driven Workflow Triggers.

Handles external events that trigger automated workflows.

Events can originate from various sources:
- API version updates detected
- Dependency updates in package registries
- Market signals from research
- Competitor changes
- Policy updates

The EventTriggerManager processes events and dispatches them to registered
handlers, enabling autonomous response to external changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of events that can trigger workflows."""

    API_VERSION_UPDATE = "api_version_update"
    DEPENDENCY_UPDATE = "dependency_update"
    MARKET_SIGNAL = "market_signal"
    COMPETITOR_CHANGE = "competitor_change"
    POLICY_UPDATE = "policy_update"


@dataclass
class WorkflowEvent:
    """An event that can trigger a workflow.

    Attributes:
        event_type: Type of event (from EventType enum)
        source: Source system/service that generated the event
        payload: Event-specific data (structure depends on event type)
        timestamp: When the event occurred
    """

    event_type: EventType
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not self.source or not isinstance(self.source, str):
            raise ValueError("Event source must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise ValueError("Event payload must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            Dictionary representation of the event
        """
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


class EventTriggerManager:
    """Manages event-driven workflow triggers.

    Handles registration of event handlers and processing of incoming events.
    Multiple handlers can be registered for the same event type and will
    be invoked in registration order.

    Attributes:
        _handlers: Mapping of EventType to list of handler functions
        _event_history: Historical record of processed events
    """

    def __init__(self, max_history: int = 1000) -> None:
        """Initialize event trigger manager.

        Args:
            max_history: Maximum number of events to keep in history
        """
        self._handlers: Dict[EventType, List[Callable[[WorkflowEvent], None]]] = {}
        self._event_history: List[WorkflowEvent] = []
        self._max_history = max_history

    def register_handler(
        self, event_type: EventType, handler: Callable[[WorkflowEvent], None]
    ) -> None:
        """Register a handler for an event type.

        Handlers are invoked in registration order when events of the
        specified type are processed.

        Args:
            event_type: Type of event to handle
            handler: Callable that receives WorkflowEvent

        Raises:
            ValueError: If handler is not callable
        """
        if not callable(handler):
            raise ValueError("Handler must be callable")

        if event_type not in self._handlers:
            self._handlers[event_type] = []

        self._handlers[event_type].append(handler)
        logger.debug(
            f"[EventTriggerManager] Registered handler for {event_type.value} "
            f"(total: {len(self._handlers[event_type])})"
        )

    def unregister_handler(
        self, event_type: EventType, handler: Callable[[WorkflowEvent], None]
    ) -> bool:
        """Unregister a handler for an event type.

        Args:
            event_type: Type of event
            handler: Handler function to unregister

        Returns:
            True if handler was found and removed, False otherwise
        """
        if event_type not in self._handlers:
            return False

        try:
            self._handlers[event_type].remove(handler)
            logger.debug(
                f"[EventTriggerManager] Unregistered handler for {event_type.value} "
                f"(remaining: {len(self._handlers[event_type])})"
            )
            return True
        except ValueError:
            return False

    async def process_event(self, event: WorkflowEvent) -> None:
        """Process an incoming event.

        Dispatches the event to all registered handlers for its type.
        Handles exceptions from handlers gracefully to prevent one failure
        from blocking other handlers.

        Args:
            event: WorkflowEvent to process
        """
        # Validate event
        if not isinstance(event, WorkflowEvent):
            logger.error("[EventTriggerManager] Invalid event type received")
            return

        # Record in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        logger.info(
            f"[EventTriggerManager] Processing event: {event.event_type.value} "
            f"from {event.source}"
        )

        # Get handlers for this event type
        handlers = self._handlers.get(event.event_type, [])

        if not handlers:
            logger.debug(f"[EventTriggerManager] No handlers for {event.event_type.value}")
            return

        # Invoke all handlers
        invoked = 0
        failed = 0

        for handler in handlers:
            try:
                # Support both sync and async handlers
                result = handler(event)
                if hasattr(result, "__await__"):
                    # Handler is async, await it
                    await result
                invoked += 1
            except Exception as e:
                failed += 1
                logger.warning(
                    f"[EventTriggerManager] Handler failed for {event.event_type.value}: {e}"
                )

        logger.info(
            f"[EventTriggerManager] Event processed: {invoked} handlers invoked, "
            f"{failed} failed"
        )

    def get_handler_count(self, event_type: Optional[EventType] = None) -> int:
        """Get count of registered handlers.

        Args:
            event_type: Specific event type, or None for total count

        Returns:
            Number of registered handlers
        """
        if event_type is None:
            return sum(len(handlers) for handlers in self._handlers.values())
        return len(self._handlers.get(event_type, []))

    def get_event_history(
        self, event_type: Optional[EventType] = None, limit: int = 100
    ) -> List[WorkflowEvent]:
        """Get historical events.

        Args:
            event_type: Filter by specific event type, or None for all
            limit: Maximum number of events to return

        Returns:
            List of WorkflowEvent instances (most recent first)
        """
        events = self._event_history

        if event_type is not None:
            events = [e for e in events if e.event_type == event_type]

        # Return in reverse order (most recent first)
        return list(reversed(events[-limit:]))

    def clear_history(self) -> None:
        """Clear event history.

        Useful for testing or memory management.
        """
        self._event_history.clear()
        logger.debug("[EventTriggerManager] Event history cleared")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of event trigger state.

        Returns:
            Dictionary with handler and history information
        """
        return {
            "total_handlers": self.get_handler_count(),
            "handlers_by_type": {
                event_type.value: len(handlers)
                for event_type, handlers in self._handlers.items()
                if handlers
            },
            "history_size": len(self._event_history),
            "max_history": self._max_history,
        }
