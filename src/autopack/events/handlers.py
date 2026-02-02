"""Event Handlers for Cross-Cutting Concerns.

Provides base handler classes and common handler implementations for
processing events in the Autopack system.

Handler types:
- BaseEventHandler: Abstract base class for handlers
- LoggingHandler: Logs events for debugging/monitoring
- MetricsHandler: Collects event metrics
- PersistenceHandler: Persists events to storage
- AuditHandler: Records events for audit trail
- ChainHandler: Chains multiple handlers together
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .event_types import Event, EventType

logger = logging.getLogger(__name__)


class BaseEventHandler(ABC):
    """Abstract base class for event handlers.

    Provides a structured way to create event handlers with:
    - Initialization with optional configuration
    - Event filtering support
    - Error handling hooks
    - Lifecycle management

    Subclasses must implement the handle() method.

    Example:
        >>> class MyHandler(BaseEventHandler):
        ...     async def handle(self, event: Event) -> None:
        ...         print(f"Received: {event.type.value}")
        >>> handler = MyHandler(name="my-handler")
        >>> bus.subscribe(handler, EventFilter.for_type(EventType.PHASE_STARTED))
    """

    def __init__(
        self,
        name: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        """Initialize the handler.

        Args:
            name: Handler name for logging/debugging
            enabled: Whether the handler is active
        """
        self.name = name or self.__class__.__name__
        self.enabled = enabled
        self._event_count = 0
        self._error_count = 0
        self._last_event_time: Optional[datetime] = None

    @abstractmethod
    async def handle(self, event: Event) -> None:
        """Process an event.

        Args:
            event: The event to process

        Raises:
            Any exception will be caught by the event bus and logged
        """
        pass

    async def __call__(self, event: Event) -> None:
        """Make the handler callable for use with EventBus.subscribe().

        Args:
            event: The event to process
        """
        if not self.enabled:
            return

        try:
            self._event_count += 1
            self._last_event_time = datetime.utcnow()
            await self.handle(event)
        except Exception as e:
            self._error_count += 1
            self.on_error(event, e)
            raise

    def on_error(self, event: Event, error: Exception) -> None:
        """Called when handle() raises an exception.

        Override this method to implement custom error handling.

        Args:
            event: The event that caused the error
            error: The exception that was raised
        """
        logger.warning(f"[{self.name}] Error handling {event.type.value}: {error}")

    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics.

        Returns:
            Dictionary with event count, error count, and last event time
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "event_count": self._event_count,
            "error_count": self._error_count,
            "last_event_time": (
                self._last_event_time.isoformat() if self._last_event_time else None
            ),
        }


class LoggingHandler(BaseEventHandler):
    """Handler that logs events for debugging and monitoring.

    Logs event details at configurable log levels based on event type
    or priority.

    Example:
        >>> handler = LoggingHandler(log_level=logging.INFO)
        >>> bus.subscribe(handler, EventFilter.all_events())
    """

    def __init__(
        self,
        name: Optional[str] = None,
        log_level: int = logging.INFO,
        include_payload: bool = True,
        logger_name: Optional[str] = None,
    ) -> None:
        """Initialize the logging handler.

        Args:
            name: Handler name
            log_level: Default log level for events
            include_payload: Whether to include payload in logs
            logger_name: Custom logger name
        """
        super().__init__(name=name or "LoggingHandler")
        self.log_level = log_level
        self.include_payload = include_payload
        self._logger = logging.getLogger(logger_name or __name__)

        # Log level overrides by event type
        self._level_overrides: Dict[EventType, int] = {
            EventType.ERROR_OCCURRED: logging.ERROR,
            EventType.WARNING_RAISED: logging.WARNING,
            EventType.HEALTH_CHECK_FAILED: logging.ERROR,
            EventType.CIRCUIT_BREAKER_OPENED: logging.WARNING,
        }

    async def handle(self, event: Event) -> None:
        """Log the event.

        Args:
            event: Event to log
        """
        level = self._level_overrides.get(event.type, self.log_level)

        message = (
            f"[EVENT] {event.type.value} | "
            f"source={event.source} | "
            f"correlation_id={event.correlation_id[:8]}..."
        )

        if self.include_payload and event.payload:
            # Truncate large payloads
            payload_str = str(event.payload)
            if len(payload_str) > 200:
                payload_str = payload_str[:200] + "..."
            message += f" | payload={payload_str}"

        self._logger.log(level, message)

    def set_level_override(self, event_type: EventType, level: int) -> None:
        """Set a log level override for a specific event type.

        Args:
            event_type: Event type to override
            level: Log level to use (e.g., logging.DEBUG)
        """
        self._level_overrides[event_type] = level


class MetricsHandler(BaseEventHandler):
    """Handler that collects metrics about events.

    Tracks counts, rates, and distributions of events for monitoring
    and alerting.

    Example:
        >>> handler = MetricsHandler()
        >>> bus.subscribe(handler, EventFilter.all_events())
        >>> # Later...
        >>> metrics = handler.get_metrics()
    """

    def __init__(self, name: Optional[str] = None) -> None:
        """Initialize the metrics handler.

        Args:
            name: Handler name
        """
        super().__init__(name=name or "MetricsHandler")
        self._counts_by_type: Dict[str, int] = {}
        self._counts_by_source: Dict[str, int] = {}
        self._counts_by_category: Dict[str, int] = {}
        self._first_event_time: Optional[datetime] = None

    async def handle(self, event: Event) -> None:
        """Record metrics for the event.

        Args:
            event: Event to record
        """
        if self._first_event_time is None:
            self._first_event_time = datetime.utcnow()

        # Increment counters
        type_key = event.type.value
        self._counts_by_type[type_key] = self._counts_by_type.get(type_key, 0) + 1

        self._counts_by_source[event.source] = self._counts_by_source.get(event.source, 0) + 1

        category = event.category
        self._counts_by_category[category] = self._counts_by_category.get(category, 0) + 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics.

        Returns:
            Dictionary with event counts and rates
        """
        now = datetime.utcnow()
        duration_seconds = 0.0
        if self._first_event_time:
            duration_seconds = (now - self._first_event_time).total_seconds()

        total_events = self._event_count

        return {
            "total_events": total_events,
            "events_per_second": (total_events / duration_seconds if duration_seconds > 0 else 0),
            "counts_by_type": dict(self._counts_by_type),
            "counts_by_source": dict(self._counts_by_source),
            "counts_by_category": dict(self._counts_by_category),
            "first_event_time": (
                self._first_event_time.isoformat() if self._first_event_time else None
            ),
            "collection_duration_seconds": duration_seconds,
        }

    def reset_metrics(self) -> None:
        """Reset all collected metrics."""
        self._counts_by_type.clear()
        self._counts_by_source.clear()
        self._counts_by_category.clear()
        self._event_count = 0
        self._first_event_time = None


class PersistenceHandler(BaseEventHandler):
    """Handler that persists events to storage.

    Writes events to a JSON Lines file for later analysis or replay.

    Example:
        >>> handler = PersistenceHandler(Path("/var/log/autopack/events.jsonl"))
        >>> bus.subscribe(handler, EventFilter.all_events())
    """

    def __init__(
        self,
        output_path: Path,
        name: Optional[str] = None,
        flush_interval: int = 10,
    ) -> None:
        """Initialize the persistence handler.

        Args:
            output_path: Path to output file (JSON Lines format)
            name: Handler name
            flush_interval: Flush after this many events
        """
        super().__init__(name=name or "PersistenceHandler")
        self.output_path = output_path
        self.flush_interval = flush_interval
        self._buffer: List[str] = []

        # Ensure parent directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    async def handle(self, event: Event) -> None:
        """Persist the event.

        Args:
            event: Event to persist
        """
        event_json = json.dumps(event.to_dict(), default=str)
        self._buffer.append(event_json)

        if len(self._buffer) >= self.flush_interval:
            await self.flush()

    async def flush(self) -> None:
        """Flush buffered events to disk."""
        if not self._buffer:
            return

        with open(self.output_path, "a", encoding="utf-8") as f:
            for line in self._buffer:
                f.write(line + "\n")

        logger.debug(f"[{self.name}] Flushed {len(self._buffer)} events to {self.output_path}")
        self._buffer.clear()

    def __del__(self) -> None:
        """Flush remaining events on cleanup."""
        if self._buffer:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.flush())
                else:
                    asyncio.run(self.flush())
            except Exception:
                # Fallback to sync write
                with open(self.output_path, "a", encoding="utf-8") as f:
                    for line in self._buffer:
                        f.write(line + "\n")


class AuditHandler(BaseEventHandler):
    """Handler that records events for audit trail.

    Captures important events with additional context for compliance
    and security auditing.

    Example:
        >>> handler = AuditHandler(audit_types={EventType.APPROVAL_GRANTED})
        >>> bus.subscribe(handler, EventFilter.all_events())
    """

    def __init__(
        self,
        name: Optional[str] = None,
        audit_types: Optional[Set[EventType]] = None,
        max_entries: int = 10000,
    ) -> None:
        """Initialize the audit handler.

        Args:
            name: Handler name
            audit_types: Event types to audit (None = all events)
            max_entries: Maximum audit entries to keep
        """
        super().__init__(name=name or "AuditHandler")
        self.audit_types = audit_types
        self.max_entries = max_entries
        self._audit_log: List[Dict[str, Any]] = []

    async def handle(self, event: Event) -> None:
        """Record the event in the audit log.

        Args:
            event: Event to audit
        """
        # Filter by audit types if specified
        if self.audit_types and event.type not in self.audit_types:
            return

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_id": event.event_id,
            "event_type": event.type.value,
            "source": event.source,
            "correlation_id": event.correlation_id,
            "payload": event.payload,
            "priority": event.priority.value,
        }

        self._audit_log.append(entry)

        # Trim if over limit
        if len(self._audit_log) > self.max_entries:
            self._audit_log = self._audit_log[-self.max_entries :]

    def get_audit_log(
        self,
        event_type: Optional[EventType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries.

        Args:
            event_type: Filter by event type
            since: Filter by timestamp
            limit: Maximum entries to return

        Returns:
            List of audit log entries (most recent first)
        """
        entries = list(self._audit_log)

        if event_type is not None:
            entries = [e for e in entries if e["event_type"] == event_type.value]

        if since is not None:
            since_iso = since.isoformat()
            entries = [e for e in entries if e["timestamp"] >= since_iso]

        return list(reversed(entries[-limit:]))

    def clear_audit_log(self) -> None:
        """Clear the audit log."""
        self._audit_log.clear()


class ChainHandler(BaseEventHandler):
    """Handler that chains multiple handlers together.

    Invokes a sequence of handlers for each event, stopping if any
    handler raises an exception (unless continue_on_error is True).

    Example:
        >>> chain = ChainHandler([
        ...     LoggingHandler(),
        ...     MetricsHandler(),
        ...     AuditHandler(),
        ... ])
        >>> bus.subscribe(chain, EventFilter.all_events())
    """

    def __init__(
        self,
        handlers: List[BaseEventHandler],
        name: Optional[str] = None,
        continue_on_error: bool = False,
    ) -> None:
        """Initialize the chain handler.

        Args:
            handlers: List of handlers to chain
            name: Handler name
            continue_on_error: Whether to continue if a handler fails
        """
        super().__init__(name=name or "ChainHandler")
        self.handlers = handlers
        self.continue_on_error = continue_on_error

    async def handle(self, event: Event) -> None:
        """Invoke all handlers in the chain.

        Args:
            event: Event to process
        """
        for handler in self.handlers:
            try:
                await handler(event)
            except Exception as e:
                if not self.continue_on_error:
                    raise
                logger.warning(f"[{self.name}] Handler {handler.name} failed, continuing: {e}")


class ConditionalHandler(BaseEventHandler):
    """Handler that only processes events matching a condition.

    Wraps another handler and only invokes it when the condition
    function returns True.

    Example:
        >>> def is_high_priority(event: Event) -> bool:
        ...     return event.priority == EventPriority.HIGH
        >>> handler = ConditionalHandler(
        ...     inner=AlertHandler(),
        ...     condition=is_high_priority,
        ... )
        >>> bus.subscribe(handler, EventFilter.all_events())
    """

    def __init__(
        self,
        inner: BaseEventHandler,
        condition: Callable[[Event], bool],
        name: Optional[str] = None,
    ) -> None:
        """Initialize the conditional handler.

        Args:
            inner: Handler to invoke when condition is met
            condition: Function that returns True if handler should be invoked
            name: Handler name
        """
        super().__init__(name=name or f"Conditional({inner.name})")
        self.inner = inner
        self.condition = condition
        self._skipped_count = 0

    async def handle(self, event: Event) -> None:
        """Conditionally invoke the inner handler.

        Args:
            event: Event to process
        """
        if self.condition(event):
            await self.inner(event)
        else:
            self._skipped_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics including skip count.

        Returns:
            Statistics dictionary
        """
        stats = super().get_stats()
        stats["skipped_count"] = self._skipped_count
        stats["inner_stats"] = self.inner.get_stats()
        return stats
