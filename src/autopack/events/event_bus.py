"""Event Bus for Publish/Subscribe Pattern.

Implements a central event bus for decoupled communication between
components in the Autopack system. The event bus supports:

- Multiple handlers per event type
- Event filtering by type, source, or category
- Async and sync handler support
- Event persistence for audit trails
- Dead letter queue for failed handlers
- Event replay capability

Architecture:
- Publishers call bus.publish() to emit events
- Subscribers call bus.subscribe() to receive events
- Handlers are invoked in order of registration
- Failed handlers don't block other handlers
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from .event_types import Event, EventFilter, EventPriority, EventType

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[Event], Union[None, Coroutine[Any, Any, None]]]


@dataclass
class Subscription:
    """A subscription to events on the event bus.

    Tracks a handler and its filter criteria for matching events.

    Attributes:
        handler: Callable to invoke when matching events occur
        filter: Criteria for which events to receive
        subscription_id: Unique identifier for this subscription
        created_at: When the subscription was created
        invocation_count: Number of times this handler has been invoked
    """

    handler: EventHandler
    filter: EventFilter
    subscription_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    invocation_count: int = 0

    def matches(self, event: Event) -> bool:
        """Check if an event matches this subscription's filter.

        Args:
            event: Event to check

        Returns:
            True if the event should be delivered to this subscriber
        """
        return self.filter.matches(event)


@dataclass
class DeadLetterEntry:
    """Entry in the dead letter queue for failed event processing.

    Tracks events that could not be processed by a handler for
    debugging and retry purposes.

    Attributes:
        event: The event that failed to process
        subscription_id: ID of the subscription that failed
        error: The exception that occurred
        timestamp: When the failure occurred
        retry_count: Number of times this event has been retried
    """

    event: Event
    subscription_id: str
    error: Exception
    timestamp: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0


class EventBus:
    """Central event bus for publish/subscribe communication.

    The event bus provides a decoupled way for components to communicate
    via events. Publishers emit events without knowing who will receive them,
    and subscribers receive events without knowing who sent them.

    Features:
    - Async and sync handler support
    - Event filtering and routing
    - Event persistence for audit trail
    - Dead letter queue for failed handlers
    - Event replay capability

    Example:
        >>> bus = EventBus()
        >>> def on_phase_started(event: Event):
        ...     print(f"Phase started: {event.payload}")
        >>> bus.subscribe(on_phase_started, EventFilter.for_type(EventType.PHASE_STARTED))
        >>> await bus.publish(Event.create(EventType.PHASE_STARTED, "orchestrator", {"phase": "research"}))

    Attributes:
        _subscriptions: Map of subscription ID to Subscription
        _event_history: Historical record of published events
        _dead_letter_queue: Events that failed to process
        _max_history: Maximum number of events to keep in history
        _max_dead_letters: Maximum dead letter queue size
    """

    def __init__(
        self,
        max_history: int = 10000,
        max_dead_letters: int = 1000,
        persist_events: bool = False,
    ) -> None:
        """Initialize the event bus.

        Args:
            max_history: Maximum number of events to keep in history
            max_dead_letters: Maximum dead letter queue size
            persist_events: Whether to persist events (for future implementation)
        """
        self._subscriptions: Dict[str, Subscription] = {}
        self._event_history: deque[Event] = deque(maxlen=max_history)
        self._dead_letter_queue: deque[DeadLetterEntry] = deque(maxlen=max_dead_letters)
        self._max_history = max_history
        self._max_dead_letters = max_dead_letters
        self._persist_events = persist_events
        self._subscription_counter = 0
        self._lock = asyncio.Lock()

    def subscribe(
        self,
        handler: EventHandler,
        event_filter: Optional[EventFilter] = None,
    ) -> str:
        """Subscribe a handler to receive events.

        Args:
            handler: Callable to invoke when matching events occur.
                    Can be sync or async.
            event_filter: Criteria for which events to receive.
                         If None, receives all events.

        Returns:
            Subscription ID for unsubscribing later

        Raises:
            ValueError: If handler is not callable
        """
        if not callable(handler):
            raise ValueError("Handler must be callable")

        self._subscription_counter += 1
        subscription_id = f"sub_{self._subscription_counter}"

        subscription = Subscription(
            handler=handler,
            filter=event_filter or EventFilter.all_events(),
            subscription_id=subscription_id,
        )

        self._subscriptions[subscription_id] = subscription

        logger.debug(
            f"[EventBus] Subscription {subscription_id} registered "
            f"(total: {len(self._subscriptions)})"
        )

        return subscription_id

    def subscribe_to_type(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> str:
        """Convenience method to subscribe to a specific event type.

        Args:
            event_type: Event type to subscribe to
            handler: Handler for events of this type

        Returns:
            Subscription ID
        """
        return self.subscribe(handler, EventFilter.for_type(event_type))

    def subscribe_to_category(
        self,
        category: str,
        handler: EventHandler,
    ) -> str:
        """Convenience method to subscribe to an event category.

        Args:
            category: Category to subscribe to (e.g., "phase", "research")
            handler: Handler for events in this category

        Returns:
            Subscription ID
        """
        return self.subscribe(handler, EventFilter.for_category(category))

    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe a handler.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            True if subscription was found and removed, False otherwise
        """
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]
            logger.debug(
                f"[EventBus] Subscription {subscription_id} removed "
                f"(remaining: {len(self._subscriptions)})"
            )
            return True
        return False

    async def publish(self, event: Event) -> int:
        """Publish an event to all matching subscribers.

        The event is delivered to all subscribers whose filters match.
        Each subscriber's handler is invoked, with exceptions caught
        and logged to prevent one handler from blocking others.

        Args:
            event: Event to publish

        Returns:
            Number of handlers successfully invoked

        Raises:
            ValueError: If event is not a valid Event instance
        """
        if not isinstance(event, Event):
            raise ValueError("publish() requires an Event instance")

        async with self._lock:
            # Record in history
            self._event_history.append(event)

        logger.debug(
            f"[EventBus] Publishing event: {event.type.value} "
            f"from {event.source} (id: {event.event_id[:8]}...)"
        )

        # Find matching subscriptions
        matching_subs = [sub for sub in self._subscriptions.values() if sub.matches(event)]

        if not matching_subs:
            logger.debug(f"[EventBus] No subscribers for {event.type.value}")
            return 0

        # Invoke handlers
        invoked = 0
        failed = 0

        for subscription in matching_subs:
            try:
                result = subscription.handler(event)
                if asyncio.iscoroutine(result):
                    await result
                subscription.invocation_count += 1
                invoked += 1
            except Exception as e:
                failed += 1
                logger.warning(
                    f"[EventBus] Handler {subscription.subscription_id} failed "
                    f"for {event.type.value}: {e}"
                )
                # Add to dead letter queue
                self._dead_letter_queue.append(
                    DeadLetterEntry(
                        event=event,
                        subscription_id=subscription.subscription_id,
                        error=e,
                    )
                )

        logger.info(
            f"[EventBus] Event {event.type.value} delivered: "
            f"{invoked} successful, {failed} failed"
        )

        return invoked

    def publish_sync(self, event: Event) -> int:
        """Synchronous wrapper for publish().

        Useful when calling from non-async code.

        Args:
            event: Event to publish

        Returns:
            Number of handlers successfully invoked
        """
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create a new event loop for this call
            future = asyncio.run_coroutine_threadsafe(self.publish(event), loop)
            return future.result()
        else:
            return asyncio.run(self.publish(event))

    async def emit(
        self,
        event_type: EventType,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Convenience method to create and publish an event in one call.

        Args:
            event_type: Type of event to emit
            source: Component emitting the event
            payload: Event data
            correlation_id: ID for linking related events
            priority: Event priority
            metadata: Additional context

        Returns:
            Number of handlers successfully invoked
        """
        event = Event.create(
            event_type=event_type,
            source=source,
            payload=payload,
            correlation_id=correlation_id,
            priority=priority,
            metadata=metadata,
        )
        return await self.publish(event)

    def get_subscription_count(self, event_type: Optional[EventType] = None) -> int:
        """Get count of active subscriptions.

        Args:
            event_type: Specific event type, or None for total count

        Returns:
            Number of active subscriptions
        """
        if event_type is None:
            return len(self._subscriptions)

        count = 0
        for sub in self._subscriptions.values():
            if sub.filter.event_types is None or event_type in sub.filter.event_types:
                count += 1
        return count

    def get_event_history(
        self,
        event_type: Optional[EventType] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Get historical events with optional filtering.

        Args:
            event_type: Filter by specific event type
            source: Filter by source
            correlation_id: Filter by correlation ID
            limit: Maximum number of events to return

        Returns:
            List of events (most recent first)
        """
        events = list(self._event_history)

        if event_type is not None:
            events = [e for e in events if e.type == event_type]

        if source is not None:
            events = [e for e in events if e.source == source]

        if correlation_id is not None:
            events = [e for e in events if e.correlation_id == correlation_id]

        # Return in reverse order (most recent first)
        return list(reversed(events[-limit:]))

    def get_dead_letters(self, limit: int = 100) -> List[DeadLetterEntry]:
        """Get entries from the dead letter queue.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of dead letter entries (most recent first)
        """
        entries = list(self._dead_letter_queue)
        return list(reversed(entries[-limit:]))

    async def retry_dead_letter(self, entry: DeadLetterEntry) -> bool:
        """Retry processing a dead letter entry.

        Args:
            entry: Dead letter entry to retry

        Returns:
            True if retry succeeded, False otherwise
        """
        if entry.subscription_id not in self._subscriptions:
            logger.warning(
                f"[EventBus] Cannot retry dead letter: "
                f"subscription {entry.subscription_id} no longer exists"
            )
            return False

        subscription = self._subscriptions[entry.subscription_id]
        entry.retry_count += 1

        try:
            result = subscription.handler(entry.event)
            if asyncio.iscoroutine(result):
                await result
            subscription.invocation_count += 1

            # Remove from dead letter queue on success
            try:
                self._dead_letter_queue.remove(entry)
            except ValueError:
                pass  # Already removed

            logger.info(
                f"[EventBus] Dead letter retry succeeded for "
                f"{entry.event.type.value} (attempt {entry.retry_count})"
            )
            return True
        except Exception as e:
            entry.error = e
            entry.timestamp = datetime.utcnow()
            logger.warning(
                f"[EventBus] Dead letter retry failed for "
                f"{entry.event.type.value}: {e} (attempt {entry.retry_count})"
            )
            return False

    def clear_history(self) -> None:
        """Clear event history.

        Useful for testing or memory management.
        """
        self._event_history.clear()
        logger.debug("[EventBus] Event history cleared")

    def clear_dead_letters(self) -> None:
        """Clear dead letter queue.

        Useful for testing or after manual investigation.
        """
        self._dead_letter_queue.clear()
        logger.debug("[EventBus] Dead letter queue cleared")

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of event bus state.

        Returns:
            Dictionary with subscription, history, and dead letter information
        """
        # Count subscriptions by category
        category_counts: Dict[str, int] = {}
        for sub in self._subscriptions.values():
            if sub.filter.categories:
                for cat in sub.filter.categories:
                    category_counts[cat] = category_counts.get(cat, 0) + 1
            elif sub.filter.event_types:
                for et in sub.filter.event_types:
                    cat = et.category
                    category_counts[cat] = category_counts.get(cat, 0) + 1
            else:
                category_counts["all"] = category_counts.get("all", 0) + 1

        return {
            "total_subscriptions": len(self._subscriptions),
            "subscriptions_by_category": category_counts,
            "history_size": len(self._event_history),
            "max_history": self._max_history,
            "dead_letters": len(self._dead_letter_queue),
            "max_dead_letters": self._max_dead_letters,
        }

    def get_subscription_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all subscriptions.

        Returns:
            List of subscription statistics
        """
        return [
            {
                "subscription_id": sub.subscription_id,
                "created_at": sub.created_at.isoformat(),
                "invocation_count": sub.invocation_count,
                "filter_types": (
                    [t.value for t in sub.filter.event_types] if sub.filter.event_types else None
                ),
                "filter_categories": (
                    list(sub.filter.categories) if sub.filter.categories else None
                ),
            }
            for sub in self._subscriptions.values()
        ]


# Global event bus instance for convenience
_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Creates the instance on first call (lazy initialization).

    Returns:
        Global EventBus instance
    """
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def reset_event_bus() -> None:
    """Reset the global event bus instance.

    Primarily for testing purposes.
    """
    global _global_bus
    _global_bus = None
