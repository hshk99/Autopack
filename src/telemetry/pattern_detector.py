"""Pattern detection algorithms for telemetry analysis."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Pattern:
    """Represents a detected pattern in telemetry events.

    Attributes:
        pattern_id: Unique identifier for the pattern.
        occurrences: Number of times the pattern has been observed.
        first_seen: ISO timestamp of first occurrence.
        last_seen: ISO timestamp of most recent occurrence.
        signature: Dictionary containing the pattern's identifying characteristics.
    """

    pattern_id: str
    occurrences: int
    first_seen: str
    last_seen: str
    signature: Dict[str, Any] = field(default_factory=dict)

    def matches(self, event_signature: Dict[str, Any]) -> bool:
        """Check if an event signature matches this pattern.

        Args:
            event_signature: Signature extracted from an event.

        Returns:
            True if the event matches this pattern's signature.
        """
        # Skip sequence-specific fields when matching single events
        sequence_fields = {"sequence_length", "event_type_sequence"}

        for key, value in self.signature.items():
            if key in sequence_fields:
                continue
            if key not in event_signature:
                return False
            if event_signature[key] != value:
                return False
        return True


class PatternDetector:
    """Detects and tracks patterns in telemetry event sequences.

    Maintains a registry of known patterns and provides methods to
    detect new patterns and match events against existing ones.
    """

    def __init__(self) -> None:
        """Initialize the pattern detector with empty pattern registry."""
        self.known_patterns: Dict[str, Pattern] = {}

    def _generate_pattern_id(self, signature: Dict[str, Any]) -> str:
        """Generate a unique ID for a pattern based on its signature.

        Args:
            signature: Pattern signature dictionary.

        Returns:
            Hash-based unique identifier.
        """
        sig_str = str(sorted(signature.items()))
        return hashlib.sha256(sig_str.encode()).hexdigest()[:12]

    def _extract_signature(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Extract identifying signature from an event.

        Args:
            event: Event dictionary.

        Returns:
            Signature dictionary with key identifying fields.
        """
        signature: Dict[str, Any] = {}

        # Extract core identifying fields
        if "event_type" in event:
            signature["event_type"] = event["event_type"]
        if "source" in event:
            signature["source"] = event["source"]

        # Extract error-related fields from payload
        payload = event.get("payload", {})
        if "error_type" in payload:
            signature["error_type"] = payload["error_type"]
        if "error_category" in payload:
            signature["error_category"] = payload["error_category"]
        if "failure_category" in payload:
            signature["failure_category"] = payload["failure_category"]
        if "component" in payload:
            signature["component"] = payload["component"]

        return signature

    def _extract_signature_from_sequence(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract a combined signature from a sequence of events.

        Args:
            events: List of event dictionaries.

        Returns:
            Combined signature dictionary.
        """
        if not events:
            return {}

        # Use the first event's core fields
        first_event = events[0]
        signature = self._extract_signature(first_event)

        # Add sequence-specific fields
        signature["sequence_length"] = len(events)

        # Track unique event types in sequence
        event_types = [e.get("event_type", "unknown") for e in events]
        signature["event_type_sequence"] = tuple(event_types)

        return signature

    def register_pattern(self, events: List[Dict[str, Any]]) -> Optional[Pattern]:
        """Detect and register a new pattern from event sequence.

        Args:
            events: List of event dictionaries to analyze.

        Returns:
            The detected Pattern if a valid pattern was found, None otherwise.
        """
        if not events:
            return None

        signature = self._extract_signature_from_sequence(events)
        if not signature:
            return None

        pattern_id = self._generate_pattern_id(signature)
        now = datetime.now().isoformat()

        if pattern_id in self.known_patterns:
            # Update existing pattern
            existing = self.known_patterns[pattern_id]
            existing.occurrences += 1
            existing.last_seen = now
            return existing

        # Create new pattern
        pattern = Pattern(
            pattern_id=pattern_id,
            occurrences=1,
            first_seen=now,
            last_seen=now,
            signature=signature,
        )
        self.known_patterns[pattern_id] = pattern
        return pattern

    def match_pattern(self, event: Dict[str, Any]) -> Optional[Pattern]:
        """Check if event matches any known pattern.

        Args:
            event: Event dictionary to check.

        Returns:
            Matching Pattern if found, None otherwise.
        """
        event_signature = self._extract_signature(event)
        if not event_signature:
            return None

        for pattern in self.known_patterns.values():
            if pattern.matches(event_signature):
                return pattern

        return None

    def get_frequent_patterns(self, min_occurrences: int = 2) -> List[Pattern]:
        """Get patterns that occur frequently.

        Args:
            min_occurrences: Minimum number of occurrences to include.

        Returns:
            List of patterns meeting the occurrence threshold.
        """
        return [p for p in self.known_patterns.values() if p.occurrences >= min_occurrences]

    def get_recent_patterns(self, since: str) -> List[Pattern]:
        """Get patterns seen since a given timestamp.

        Args:
            since: ISO timestamp to filter patterns.

        Returns:
            List of patterns last seen after the given timestamp.
        """
        return [p for p in self.known_patterns.values() if p.last_seen >= since]

    def clear_patterns(self) -> None:
        """Clear all registered patterns."""
        self.known_patterns.clear()

    def get_pattern_count(self) -> int:
        """Get the total number of registered patterns.

        Returns:
            Number of patterns in the registry.
        """
        return len(self.known_patterns)
