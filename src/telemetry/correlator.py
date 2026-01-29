"""Cross-artifact telemetry correlator."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .event_schema import TelemetryEvent
from .unified_event_log import UnifiedEventLog

logger = logging.getLogger(__name__)

# IMP-REL-004: Max iteration limits for causation chain building
MAX_CAUSATION_CHAIN_DEPTH = 1000

# IMP-TEL-005: Default time window for pre-fetching events
DEFAULT_PREFETCH_WINDOW_HOURS = 1


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
        try:
            # Query for events matching both slot_id and pr_number
            slot_events = self.event_log.query({"slot_id": slot_id})
            pr_events = self.event_log.query({"pr_number": pr_number})
        except Exception as e:
            logger.error(f"Failed to query events for slot-PR correlation: {e}")
            return CorrelatedEvent(
                primary_event=None,
                related_events=[],
                correlation_confidence=0.0,
                inferred_root_cause=None,
                correlation_type="none",
            )

        # Combine and deduplicate events
        all_events = []
        seen_keys: set[Tuple[datetime, str, str]] = set()
        skipped_count = 0
        for event in slot_events + pr_events:
            try:
                key = (event.timestamp, event.source, event.event_type)
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_events.append(event)
            except (AttributeError, TypeError) as err:
                skipped_count += 1
                logger.warning(f"Skipping malformed event in slot-PR correlation: {err}")
                continue

        if skipped_count > 0:
            logger.debug(f"Skipped {skipped_count} malformed events in slot-PR correlation")

        # Sort by timestamp
        try:
            all_events.sort(key=lambda e: e.timestamp)
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error sorting events: {e}")

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

        IMP-TEL-005: Optimized with cycle detection and pre-fetching to achieve
        O(n) complexity instead of O(n^2) worst case.

        Args:
            final_event: The final effect event to trace back from.

        Returns:
            CausationChain showing the sequence of cause-effect events.
        """
        chain_events = [final_event]
        current = final_event

        try:
            # IMP-TEL-005: Cycle detection - track visited events
            visited: set[Tuple[datetime, str, str]] = {self._get_event_key(final_event)}
        except (AttributeError, TypeError) as e:
            logger.error(f"Failed to get event key for final event: {e}")
            # Return single-event chain on failure
            return CausationChain(
                chain_id=f"chain_error_{datetime.now().isoformat()}",
                events=chain_events,
                root_cause_event=final_event,
                final_effect_event=final_event,
                confidence=0.0,
            )

        # IMP-TEL-005: Pre-fetch events in one query instead of repeated queries
        # This reduces O(n^2) to O(n) for deep chains
        time_window = timedelta(hours=DEFAULT_PREFETCH_WINDOW_HOURS)
        try:
            prefetched_events = self._prefetch_events(
                end_time=final_event.timestamp,
                time_window=time_window,
                slot_id=final_event.slot_id,
            )
        except Exception as e:
            logger.error(f"Failed to pre-fetch events for causation chain: {e}")
            return CausationChain(
                chain_id=f"chain_{final_event.timestamp.isoformat()}",
                events=chain_events,
                root_cause_event=final_event,
                final_effect_event=final_event,
                confidence=0.0,
            )

        # Build index for efficient lookup: group events by timestamp range
        try:
            events_by_time = self._build_time_index(prefetched_events)
        except Exception as e:
            logger.error(f"Failed to build time index for causation chain: {e}")
            return CausationChain(
                chain_id=f"chain_{final_event.timestamp.isoformat()}",
                events=chain_events,
                root_cause_event=final_event,
                final_effect_event=final_event,
                confidence=0.0,
            )

        # IMP-REL-004: Add iteration counter to prevent unbounded loops
        depth = 0
        # Look for events that could have caused this one
        while depth < MAX_CAUSATION_CHAIN_DEPTH:
            depth += 1

            try:
                # Find potential causes from pre-fetched events
                potential_causes = self._get_potential_causes_from_index(
                    current, events_by_time, visited
                )

                if not potential_causes:
                    break

                # Find most likely cause
                cause = self._find_likely_cause(current, potential_causes)
                if cause is None:
                    break

                # IMP-TEL-005: Check for cycle before adding
                cause_key = self._get_event_key(cause)
                if cause_key in visited:
                    logger.warning(
                        f"Cycle detected in causation chain at event: "
                        f"{cause.source}:{cause.event_type}"
                    )
                    break

                visited.add(cause_key)
                chain_events.insert(0, cause)
                current = cause
            except (AttributeError, TypeError, KeyError) as err:
                logger.warning(f"Error processing causation chain at depth {depth}: {err}")
                break
        else:
            # IMP-REL-004: Max depth reached - log warning
            logger.warning(
                f"Causation chain exceeded max depth ({MAX_CAUSATION_CHAIN_DEPTH}), "
                "possible circular reference or extremely long chain"
            )

        return CausationChain(
            chain_id=f"chain_{final_event.timestamp.isoformat()}",
            events=chain_events,
            root_cause_event=chain_events[0],
            final_effect_event=final_event,
            confidence=self._chain_confidence(chain_events),
        )

    def _get_event_key(self, event: TelemetryEvent) -> Tuple[datetime, str, str]:
        """Create a unique key for an event for cycle detection.

        Args:
            event: The event to create a key for.

        Returns:
            Tuple of (timestamp, source, event_type) as unique identifier.
        """
        return (event.timestamp, event.source, event.event_type)

    def _prefetch_events(
        self,
        end_time: datetime,
        time_window: timedelta,
        slot_id: Optional[int] = None,
    ) -> List[TelemetryEvent]:
        """Pre-fetch events in time window for efficient chain traversal.

        IMP-TEL-005: Single query to fetch all potential cause events,
        avoiding repeated queries in the main loop.

        Args:
            end_time: The end of the time window (usually the final event's time).
            time_window: How far back to look for events.
            slot_id: Optional slot ID to filter events.

        Returns:
            List of events in the time window.
        """
        start_time = end_time - time_window
        filters: Dict[str, object] = {
            "since": start_time,
            "until": end_time,
        }
        if slot_id is not None:
            filters["slot_id"] = slot_id

        events = self.event_log.query(filters)
        logger.debug(f"Pre-fetched {len(events)} events in {time_window} window for chain analysis")
        return events

    def _build_time_index(self, events: List[TelemetryEvent]) -> Dict[int, List[TelemetryEvent]]:
        """Build time-based index for efficient event lookup.

        Groups events into minute-based buckets for faster filtering.

        Args:
            events: List of events to index.

        Returns:
            Dictionary mapping minute buckets to events.
        """
        index: Dict[int, List[TelemetryEvent]] = {}
        for event in events:
            # Use minute-granularity bucket (timestamp as minutes since epoch)
            bucket = int(event.timestamp.timestamp() // 60)
            if bucket not in index:
                index[bucket] = []
            index[bucket].append(event)
        return index

    def _get_potential_causes_from_index(
        self,
        effect: TelemetryEvent,
        events_by_time: Dict[int, List[TelemetryEvent]],
        visited: set[Tuple[datetime, str, str]],
    ) -> List[TelemetryEvent]:
        """Get potential cause events from the pre-built index.

        Args:
            effect: The effect event to find causes for.
            events_by_time: Time-indexed events from pre-fetch.
            visited: Set of already-visited event keys.

        Returns:
            List of potential cause events, filtered and sorted.
        """
        window_start = effect.timestamp - self.correlation_window
        window_end = effect.timestamp

        # Get relevant minute buckets
        start_bucket = int(window_start.timestamp() // 60)
        end_bucket = int(window_end.timestamp() // 60)

        potential_causes = []
        for bucket in range(start_bucket, end_bucket + 1):
            if bucket in events_by_time:
                for event in events_by_time[bucket]:
                    # Filter: must be before effect, not visited, same slot if applicable
                    if event.timestamp >= effect.timestamp:
                        continue
                    if event.timestamp < window_start:
                        continue
                    if self._get_event_key(event) in visited:
                        continue
                    if effect.slot_id is not None and event.slot_id != effect.slot_id:
                        continue
                    potential_causes.append(event)

        return potential_causes

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

        try:
            start = center_event.timestamp - window
            end = center_event.timestamp + window
        except (AttributeError, TypeError) as e:
            logger.error(f"Failed to calculate time window for correlation: {e}")
            return []

        try:
            events = self.event_log.query({"since": start, "until": end})
        except Exception as e:
            logger.error(f"Failed to query events for time window correlation: {e}")
            return []

        # Build correlated events for each related event
        correlated = []
        skipped_count = 0
        for event in events:
            try:
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
            except (AttributeError, TypeError) as err:
                skipped_count += 1
                logger.warning(f"Skipping malformed event in time window correlation: {err}")
                continue

        if skipped_count > 0:
            logger.debug(f"Skipped {skipped_count} malformed events in time window correlation")

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
        try:
            # Filter out events with invalid timestamps
            valid_events = [e for e in events if e.timestamp is not None]
            if not valid_events:
                return None
            # Find earliest event - likely root cause
            earliest = min(valid_events, key=lambda e: e.timestamp)
            return f"{earliest.source}: {earliest.event_type}"
        except (AttributeError, TypeError) as err:
            logger.warning(f"Error inferring root cause: {err}")
            return None

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
