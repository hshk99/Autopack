"""Event-Driven Architecture for Autopack.

This module provides a publish/subscribe event system for decoupled
communication between components. The event bus enables:

- Loose coupling between modules
- Easy extensibility via event listeners
- Audit trail of system activities
- External integration hooks

Quick Start:
    >>> from autopack.events import EventBus, Event, EventType, EventFilter
    >>> bus = EventBus()
    >>> def on_phase_started(event: Event):
    ...     print(f"Phase started: {event.payload}")
    >>> bus.subscribe(on_phase_started, EventFilter.for_type(EventType.PHASE_STARTED))
    >>> await bus.emit(EventType.PHASE_STARTED, "orchestrator", {"phase": "research"})

Using the Global Bus:
    >>> from autopack.events import get_event_bus
    >>> bus = get_event_bus()
    >>> bus.subscribe_to_type(EventType.PHASE_COMPLETED, my_handler)

Using Built-in Handlers:
    >>> from autopack.events import LoggingHandler, MetricsHandler
    >>> bus.subscribe(LoggingHandler(), EventFilter.all_events())
    >>> bus.subscribe(MetricsHandler(), EventFilter.for_category("phase"))
"""

from .event_bus import (
    DeadLetterEntry,
    EventBus,
    EventHandler,
    Subscription,
    get_event_bus,
    reset_event_bus,
)
from .event_types import Event, EventFilter, EventPriority, EventType
from .handlers import (
    AuditHandler,
    BaseEventHandler,
    ChainHandler,
    ConditionalHandler,
    LoggingHandler,
    MetricsHandler,
    PersistenceHandler,
)

__all__ = [
    # Event types and core classes
    "Event",
    "EventType",
    "EventPriority",
    "EventFilter",
    # Event bus
    "EventBus",
    "EventHandler",
    "Subscription",
    "DeadLetterEntry",
    "get_event_bus",
    "reset_event_bus",
    # Handlers
    "BaseEventHandler",
    "LoggingHandler",
    "MetricsHandler",
    "PersistenceHandler",
    "AuditHandler",
    "ChainHandler",
    "ConditionalHandler",
]
