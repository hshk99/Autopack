"""Unified telemetry event schema."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Literal, Optional


@dataclass
class TelemetryEvent:
    """Normalized telemetry event for cross-component correlation.

    Attributes:
        timestamp: When the event occurred.
        source: The telemetry source component.
        event_type: Type of event within the source.
        slot_id: Optional slot identifier.
        phase_id: Optional phase identifier.
        pr_number: Optional pull request number.
        payload: Additional event-specific data.
    """

    timestamp: datetime
    source: Literal["slot_history", "ci_retry", "nudge_state", "escalation"]
    event_type: str
    slot_id: Optional[int] = None
    phase_id: Optional[str] = None
    pr_number: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "event_type": self.event_type,
            "slot_id": self.slot_id,
            "phase_id": self.phase_id,
            "pr_number": self.pr_number,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryEvent":
        """Create event from dictionary.

        Args:
            data: Dictionary containing event data.

        Returns:
            TelemetryEvent instance.
        """
        timestamp = data["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        return cls(
            timestamp=timestamp,
            source=data["source"],
            event_type=data["event_type"],
            slot_id=data.get("slot_id"),
            phase_id=data.get("phase_id"),
            pr_number=data.get("pr_number"),
            payload=data.get("payload", {}),
        )
