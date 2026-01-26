"""Unified telemetry event log aggregator."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_schema import TelemetryEvent


class UnifiedEventLog:
    """Aggregates telemetry events from multiple sources into a unified log.

    Provides a centralized store for events from slot_history, ci_retry,
    nudge_state, and escalation sources with filtering and query capabilities.
    """

    def __init__(self, log_path: str):
        """Initialize the unified event log.

        Args:
            log_path: Path to the JSONL file for storing events.
        """
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def ingest(self, event: TelemetryEvent) -> None:
        """Add event to unified log.

        Args:
            event: TelemetryEvent to append to the log.
        """
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    def ingest_batch(self, events: List[TelemetryEvent]) -> int:
        """Add multiple events to the unified log.

        Args:
            events: List of TelemetryEvents to append.

        Returns:
            Number of events ingested.
        """
        with open(self.log_path, "a", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event.to_dict()) + "\n")
        return len(events)

    def query(
        self,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[TelemetryEvent]:
        """Query events with filters.

        Args:
            filters: Dictionary of filter criteria. Supported keys:
                - source: Filter by event source
                - event_type: Filter by event type
                - slot_id: Filter by slot ID
                - phase_id: Filter by phase ID
                - pr_number: Filter by PR number
                - since: Filter events after this datetime
                - until: Filter events before this datetime

        Returns:
            List of TelemetryEvents matching the filters.
        """
        filters = filters or {}
        events: List[TelemetryEvent] = []

        if not self.log_path.exists():
            return events

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                event = TelemetryEvent.from_dict(data)

                if self._matches_filters(event, filters):
                    events.append(event)

        return events

    def _matches_filters(self, event: TelemetryEvent, filters: Dict[str, Any]) -> bool:
        """Check if event matches all filter criteria.

        Args:
            event: Event to check.
            filters: Filter criteria dictionary.

        Returns:
            True if event matches all filters.
        """
        if "source" in filters and event.source != filters["source"]:
            return False
        if "event_type" in filters and event.event_type != filters["event_type"]:
            return False
        if "slot_id" in filters and event.slot_id != filters["slot_id"]:
            return False
        if "phase_id" in filters and event.phase_id != filters["phase_id"]:
            return False
        if "pr_number" in filters and event.pr_number != filters["pr_number"]:
            return False
        if "since" in filters:
            since = filters["since"]
            if isinstance(since, str):
                since = datetime.fromisoformat(since)
            if event.timestamp < since:
                return False
        if "until" in filters:
            until = filters["until"]
            if isinstance(until, str):
                until = datetime.fromisoformat(until)
            if event.timestamp > until:
                return False

        return True

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count events matching filters.

        Args:
            filters: Optional filter criteria.

        Returns:
            Number of matching events.
        """
        return len(self.query(filters))

    def get_sources(self) -> List[str]:
        """Get list of unique sources in the log.

        Returns:
            List of source names.
        """
        sources = set()
        events = self.query()
        for event in events:
            sources.add(event.source)
        return sorted(sources)

    def correlate_by_slot(self, slot_id: int) -> List[TelemetryEvent]:
        """Get all events for a specific slot across all sources.

        Args:
            slot_id: Slot identifier.

        Returns:
            List of events for the slot, sorted by timestamp.
        """
        events = self.query({"slot_id": slot_id})
        return sorted(events, key=lambda e: e.timestamp)

    def correlate_by_pr(self, pr_number: int) -> List[TelemetryEvent]:
        """Get all events for a specific PR across all sources.

        Args:
            pr_number: Pull request number.

        Returns:
            List of events for the PR, sorted by timestamp.
        """
        events = self.query({"pr_number": pr_number})
        return sorted(events, key=lambda e: e.timestamp)
