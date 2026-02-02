"""Event Types for Event-Driven Architecture.

Defines all event types used across the Autopack system for decoupled
communication between components. Events enable:
- Loose coupling between modules
- Easy extensibility via event listeners
- Audit trail of system activities
- External integration hooks

Event categories:
- Phase lifecycle events (start, complete, fail)
- Research events (start, gap detection, completion)
- Build events (decision making, artifact generation)
- Model events (selection, fallback triggers)
- Session events (start, end)
- System events (errors, warnings)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class EventType(Enum):
    """Types of events in the Autopack system.

    Organized by domain for clarity and extensibility.
    """

    # Phase lifecycle events
    PHASE_STARTED = "phase.started"
    PHASE_COMPLETED = "phase.completed"
    PHASE_FAILED = "phase.failed"
    PHASE_SKIPPED = "phase.skipped"
    PHASE_ROLLED_BACK = "phase.rolled_back"

    # Research events
    RESEARCH_STARTED = "research.started"
    RESEARCH_GAP_DETECTED = "research.gap_detected"
    RESEARCH_GAP_RESOLVED = "research.gap_resolved"
    RESEARCH_COMPLETED = "research.completed"
    RESEARCH_FAILED = "research.failed"

    # Build events
    BUILD_DECISION_MADE = "build.decision_made"
    BUILD_STARTED = "build.started"
    BUILD_COMPLETED = "build.completed"
    BUILD_FAILED = "build.failed"

    # Artifact events
    ARTIFACT_GENERATED = "artifact.generated"
    ARTIFACT_VALIDATED = "artifact.validated"
    ARTIFACT_VALIDATION_FAILED = "artifact.validation_failed"

    # Model events
    MODEL_SELECTED = "model.selected"
    MODEL_FALLBACK_TRIGGERED = "model.fallback_triggered"
    MODEL_VALIDATION_COMPLETED = "model.validation_completed"
    MODEL_VALIDATION_FAILED = "model.validation_failed"

    # Session events
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SESSION_PAUSED = "session.paused"
    SESSION_RESUMED = "session.resumed"

    # Approval events
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"
    APPROVAL_TIMEOUT = "approval.timeout"

    # System events
    ERROR_OCCURRED = "error.occurred"
    WARNING_RAISED = "warning.raised"
    HEALTH_CHECK_FAILED = "health.check_failed"
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"
    CIRCUIT_BREAKER_CLOSED = "circuit_breaker.closed"

    @classmethod
    def from_string(cls, value: str) -> "EventType":
        """Create EventType from string value.

        Args:
            value: String representation of the event type (e.g., "phase.started")

        Returns:
            EventType enum member

        Raises:
            ValueError: If value doesn't match any event type
        """
        for event_type in cls:
            if event_type.value == value:
                return event_type
        raise ValueError(f"Unknown event type: {value}")

    @property
    def category(self) -> str:
        """Get the category of this event type.

        Returns:
            Category name (e.g., "phase", "research", "build")
        """
        return self.value.split(".")[0]


class EventPriority(Enum):
    """Priority levels for events.

    Higher priority events are processed before lower priority ones
    when multiple events are queued.
    """

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Event:
    """An event in the Autopack event bus system.

    Events are the fundamental unit of communication in the event-driven
    architecture. Each event has:
    - A type indicating what happened
    - A timestamp of when it occurred
    - A payload with event-specific data
    - A source indicating the originating component
    - A correlation_id linking related events
    - Optional metadata for additional context

    Attributes:
        type: Type of event (from EventType enum)
        timestamp: When the event occurred (UTC)
        payload: Event-specific data (structure depends on event type)
        source: Component/module that generated the event
        correlation_id: UUID linking related events (e.g., same session)
        event_id: Unique identifier for this specific event
        priority: Event priority for processing order
        metadata: Optional additional context
    """

    type: EventType
    timestamp: datetime
    payload: Dict[str, Any]
    source: str
    correlation_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: EventPriority = EventPriority.NORMAL
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Validate event after initialization."""
        if not self.source or not isinstance(self.source, str):
            raise ValueError("Event source must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise ValueError("Event payload must be a dictionary")
        if not self.correlation_id or not isinstance(self.correlation_id, str):
            raise ValueError("Event correlation_id must be a non-empty string")
        if self.metadata is not None and not isinstance(self.metadata, dict):
            raise ValueError("Event metadata must be a dictionary or None")

    @classmethod
    def create(
        cls,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Event":
        """Factory method to create an Event with sensible defaults.

        Args:
            event_type: Type of event
            source: Component generating the event
            payload: Event-specific data (defaults to empty dict)
            correlation_id: ID for linking events (generates new UUID if not provided)
            priority: Event priority (defaults to NORMAL)
            metadata: Optional additional context

        Returns:
            New Event instance
        """
        return cls(
            type=event_type,
            timestamp=datetime.utcnow(),
            payload=payload or {},
            source=source,
            correlation_id=correlation_id or str(uuid.uuid4()),
            priority=priority,
            metadata=metadata,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            Dictionary representation of the event
        """
        result = {
            "event_id": self.event_id,
            "type": self.type.value,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "priority": self.priority.value,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create Event from dictionary representation.

        Args:
            data: Dictionary with event data

        Returns:
            Event instance

        Raises:
            ValueError: If data is missing required fields or has invalid values
        """
        required_fields = ["type", "timestamp", "payload", "source", "correlation_id"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(f"Missing required field: {field_name}")

        return cls(
            type=EventType.from_string(data["type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data["payload"],
            source=data["source"],
            correlation_id=data["correlation_id"],
            event_id=data.get("event_id", str(uuid.uuid4())),
            priority=EventPriority(data.get("priority", EventPriority.NORMAL.value)),
            metadata=data.get("metadata"),
        )

    def with_correlation_id(self, correlation_id: str) -> "Event":
        """Create a copy of this event with a different correlation ID.

        Useful for creating related events that share the same correlation.

        Args:
            correlation_id: New correlation ID

        Returns:
            New Event instance with updated correlation_id
        """
        return Event(
            type=self.type,
            timestamp=self.timestamp,
            payload=self.payload.copy(),
            source=self.source,
            correlation_id=correlation_id,
            event_id=str(uuid.uuid4()),  # New event gets new ID
            priority=self.priority,
            metadata=self.metadata.copy() if self.metadata else None,
        )

    @property
    def category(self) -> str:
        """Get the category of this event.

        Returns:
            Category name from the event type
        """
        return self.type.category

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"Event(type={self.type.value}, source={self.source}, "
            f"event_id={self.event_id[:8]}..., correlation_id={self.correlation_id[:8]}...)"
        )


@dataclass
class EventFilter:
    """Filter criteria for event subscriptions.

    Allows handlers to specify which events they want to receive based on:
    - Event types (exact match or pattern)
    - Event sources
    - Event categories
    - Custom predicate functions

    Attributes:
        event_types: Set of specific event types to match (empty = all)
        sources: Set of source patterns to match (empty = all)
        categories: Set of categories to match (empty = all)
        min_priority: Minimum priority level to receive
    """

    event_types: Optional[set[EventType]] = None
    sources: Optional[set[str]] = None
    categories: Optional[set[str]] = None
    min_priority: EventPriority = EventPriority.LOW

    def matches(self, event: Event) -> bool:
        """Check if an event matches this filter.

        Args:
            event: Event to check

        Returns:
            True if the event matches all filter criteria
        """
        # Check priority
        if event.priority.value < self.min_priority.value:
            return False

        # Check event type
        if self.event_types and event.type not in self.event_types:
            return False

        # Check source
        if self.sources and event.source not in self.sources:
            return False

        # Check category
        if self.categories and event.category not in self.categories:
            return False

        return True

    @classmethod
    def for_type(cls, event_type: EventType) -> "EventFilter":
        """Create a filter for a specific event type.

        Args:
            event_type: Event type to filter for

        Returns:
            EventFilter matching only that type
        """
        return cls(event_types={event_type})

    @classmethod
    def for_types(cls, *event_types: EventType) -> "EventFilter":
        """Create a filter for multiple event types.

        Args:
            event_types: Event types to filter for

        Returns:
            EventFilter matching any of the types
        """
        return cls(event_types=set(event_types))

    @classmethod
    def for_category(cls, category: str) -> "EventFilter":
        """Create a filter for an event category.

        Args:
            category: Category name (e.g., "phase", "research")

        Returns:
            EventFilter matching events in that category
        """
        return cls(categories={category})

    @classmethod
    def all_events(cls) -> "EventFilter":
        """Create a filter that matches all events.

        Returns:
            EventFilter with no restrictions
        """
        return cls()
