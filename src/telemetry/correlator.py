"""Cross-artifact telemetry correlator."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from .event_schema import TelemetryEvent
from .unified_event_log import UnifiedEventLog


@dataclass
class CorrelatedEvent:
    """An event with its related events from other sources.

    Attributes:
        primary_event: The main event being correlated.
        related_events: Events from other sources related to the primary.
        correlation_confidence: Confidence score (0.0 to 1.0) for the correlation.
        inferred_root_cause: Optional description of the inferred root cause.
        correlation_type: Type of correlation ('temporal', 'causal', 'component', 'none').
    """

    primary_event: Optional[TelemetryEvent]
    related_events: List[TelemetryEvent]
    correlation_confidence: float
    inferred_root_cause: Optional[str]
    correlation_type: str


@dataclass
class CausationChain:
    """A chain of events showing cause-effect relationship.

    Attributes:
        chain_id: Unique identifier for this chain.
        events: Ordered list of events in the causation chain.
        root_cause_event: The first event that triggered the chain.
        final_effect_event: The last event in the chain (the observed effect).
        confidence: Confidence score for the entire chain.
    """

    chain_id: str
    events: List[TelemetryEvent]
    root_cause_event: TelemetryEvent
    final_effect_event: TelemetryEvent
    confidence: float


class TelemetryCorrelator:
    """Correlates events across different telemetry sources.

    Provides methods to find related events across slot_history, ci_retry,
    nudge_state, and escalation sources, enabling identification of hidden
    root causes that span multiple artifacts.
    """

    def __init__(self, event_log: UnifiedEventLog):
        """Initialize the correlator.

        Args:
            event_log: The unified event log to query for events.
        """
        self.event_log = event_log
        self.correlation_window = timedelta(minutes=5)

    def correlate_slot_with_pr(self, slot_id: int, pr_number: int) -> CorrelatedEvent:
        """Find all events related to a slot-PR combination.

        Args:
            slot_id: The slot ID to correlate.
            pr_number: The PR number to correlate.

        Returns:
            Correlated event with all related events from different sources.
        """
        # Query for events matching both slot_id and pr_number
        slot_events = self.event_log.query({"slot_id": slot_id})
        pr_events = self.event_log.query({"pr_number": pr_number})

        # Combine and deduplicate events
        all_events = []
        seen_keys = set()
        for event in slot_events + pr_events:
            key = (event.timestamp, event.source, event.event_type)
            if key not in seen_keys:
                seen_keys.add(key)
                all_events.append(event)

        # Sort by timestamp
        all_events.sort(key=lambda e: e.timestamp)

        if not all_events:
            return CorrelatedEvent(
                primary_event=None,
                related_events=[],
                correlation_confidence=0.0,
                inferred_root_cause=None,
                correlation_type="none",
            )

        primary = all_events[0]
        related = all_events[1:] if len(all_events) > 1 else []

        return CorrelatedEvent(
            primary_event=primary,
            related_events=related,
            correlation_confidence=self._calculate_confidence(all_events),
            inferred_root_cause=self._infer_root_cause(all_events),
            correlation_type="component",
        )

    def find_causation_chain(self, final_event: TelemetryEvent) -> CausationChain:
        """Trace back through events to find the causation chain.

        Args:
            final_event: The final effect event to trace back from.

        Returns:
            CausationChain showing the sequence of cause-effect events.
        """
        chain_events = [final_event]
        current = final_event

        # Look for events that could have caused this one
        while True:
            window_start = current.timestamp - self.correlation_window
            potential_causes = self.event_log.query(
                {"until": current.timestamp, "since": window_start}
            )

            # Filter to events before current and with same slot_id if available
            if current.slot_id is not None:
                potential_causes = [
                    e
                    for e in potential_causes
                    if e.slot_id == current.slot_id and e.timestamp < current.timestamp
                ]
            else:
                potential_causes = [e for e in potential_causes if e.timestamp < current.timestamp]

            if not potential_causes:
                break

            # Find most likely cause
            cause = self._find_likely_cause(current, potential_causes)
            if cause is None:
                break

            chain_events.insert(0, cause)
            current = cause

        return CausationChain(
            chain_id=f"chain_{final_event.timestamp.isoformat()}",
            events=chain_events,
            root_cause_event=chain_events[0],
            final_effect_event=final_event,
            confidence=self._chain_confidence(chain_events),
        )

    def correlate_by_timewindow(
        self,
        center_event: TelemetryEvent,
        window: Optional[timedelta] = None,
    ) -> List[CorrelatedEvent]:
        """Find all events within a time window of the center event.

        Args:
            center_event: The event to center the window on.
            window: Time window (defaults to self.correlation_window).

        Returns:
            List of correlated events within the window.
        """
        window = window or self.correlation_window
        start = center_event.timestamp - window
        end = center_event.timestamp + window

        events = self.event_log.query({"since": start, "until": end})

        # Build correlated events for each related event
        correlated = []
        for event in events:
            if event != center_event:
                correlated.append(
                    CorrelatedEvent(
                        primary_event=center_event,
                        related_events=[event],
                        correlation_confidence=self._temporal_confidence(center_event, event),
                        inferred_root_cause=None,
                        correlation_type="temporal",
                    )
                )

        return correlated

    def _calculate_confidence(self, events: List[TelemetryEvent]) -> float:
        """Calculate correlation confidence based on event overlap.

        Args:
            events: List of events to calculate confidence for.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        if len(events) < 2:
            return 0.0
        # More events = higher confidence, capped at 1.0
        return min(1.0, len(events) * 0.2)

    def _infer_root_cause(self, events: List[TelemetryEvent]) -> Optional[str]:
        """Infer potential root cause from correlated events.

        Args:
            events: List of correlated events.

        Returns:
            Description of the inferred root cause, or None if no events.
        """
        if not events:
            return None
        # Find earliest event - likely root cause
        earliest = min(events, key=lambda e: e.timestamp)
        return f"{earliest.source}: {earliest.event_type}"

    def _find_likely_cause(
        self,
        effect: TelemetryEvent,
        potential_causes: List[TelemetryEvent],
    ) -> Optional[TelemetryEvent]:
        """Find the most likely cause of an event.

        Args:
            effect: The effect event to find a cause for.
            potential_causes: List of potential cause events.

        Returns:
            The most likely cause event, or None if no suitable cause found.
        """
        # Filter to events within correlation window and before effect
        window_start = effect.timestamp - self.correlation_window
        candidates = [
            e
            for e in potential_causes
            if e.timestamp >= window_start and e.timestamp < effect.timestamp
        ]
        if not candidates:
            return None
        # Return most recent as likely cause
        return max(candidates, key=lambda e: e.timestamp)

    def _temporal_confidence(
        self,
        event1: TelemetryEvent,
        event2: TelemetryEvent,
    ) -> float:
        """Calculate confidence based on temporal proximity.

        Args:
            event1: First event.
            event2: Second event.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        delta = abs((event1.timestamp - event2.timestamp).total_seconds())
        max_seconds = self.correlation_window.total_seconds()
        return max(0.0, 1.0 - (delta / max_seconds))

    def _chain_confidence(self, chain: List[TelemetryEvent]) -> float:
        """Calculate confidence for a causation chain.

        Args:
            chain: List of events in the causation chain.

        Returns:
            Average confidence across all chain links.
        """
        if len(chain) < 2:
            return 0.0
        # Longer chains with tighter timing = higher confidence
        confidences = []
        for i in range(len(chain) - 1):
            conf = self._temporal_confidence(chain[i], chain[i + 1])
            confidences.append(conf)
        return sum(confidences) / len(confidences)
