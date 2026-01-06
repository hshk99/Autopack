"""Usage accounting for intention-first stuck handling (BUILD-181 Phase 1).

Provides deterministic aggregation of usage events as the single source of truth
for stuck handling decisions. All aggregation is stable and sorted.

Key properties:
- Same usage events → same computed totals (deterministic)
- Order-independent aggregation
- No implicit globals; all inputs explicit
- Hashable results for caching/deduplication
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class UsageEvent(BaseModel):
    """Single usage event record.

    Represents one metered interaction (API call, context load, etc.).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., description="Unique event identifier")
    timestamp: datetime = Field(..., description="When the event occurred (UTC)")
    tokens_used: int = Field(default=0, ge=0, description="Tokens consumed")
    context_chars_used: int = Field(default=0, ge=0, description="Context characters loaded")
    sot_chars_used: int = Field(default=0, ge=0, description="SOT characters retrieved")

    def __hash__(self) -> int:
        """Hash for set membership and deduplication."""
        return hash((self.event_id, self.timestamp.isoformat()))


class UsageTotals(BaseModel):
    """Aggregated usage totals.

    Immutable, hashable result of usage aggregation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tokens_used: int = Field(default=0, ge=0)
    context_chars_used: int = Field(default=0, ge=0)
    sot_chars_used: int = Field(default=0, ge=0)

    def __hash__(self) -> int:
        """Hash for caching and deduplication."""
        return hash((self.tokens_used, self.context_chars_used, self.sot_chars_used))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tokens_used": self.tokens_used,
            "context_chars_used": self.context_chars_used,
            "sot_chars_used": self.sot_chars_used,
        }


def aggregate_usage(events: List[UsageEvent]) -> UsageTotals:
    """Aggregate usage events into totals.

    Deterministic aggregation:
    - Same events always produce identical totals
    - Order-independent (internally sorted by event_id for stability)
    - No side effects or implicit state

    Args:
        events: List of UsageEvent instances

    Returns:
        UsageTotals with summed metrics
    """
    if not events:
        return UsageTotals(tokens_used=0, context_chars_used=0, sot_chars_used=0)

    # Sort by event_id for deterministic processing (order-independence)
    sorted_events = sorted(events, key=lambda e: e.event_id)

    total_tokens = sum(e.tokens_used for e in sorted_events)
    total_context = sum(e.context_chars_used for e in sorted_events)
    total_sot = sum(e.sot_chars_used for e in sorted_events)

    return UsageTotals(
        tokens_used=total_tokens,
        context_chars_used=total_context,
        sot_chars_used=total_sot,
    )


def load_usage_events(run_id: str, artifact_path: Path) -> List[UsageEvent]:
    """Load usage events from run-local artifact file.

    Args:
        run_id: Run identifier (for logging)
        artifact_path: Path to usage_events.json artifact

    Returns:
        List of UsageEvent instances (empty if file missing or invalid)
    """
    if not artifact_path.exists():
        logger.debug(f"[UsageAccounting] No usage events file at {artifact_path}")
        return []

    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))

        if not isinstance(data, list):
            logger.warning(
                f"[UsageAccounting] Invalid format in {artifact_path}: expected list"
            )
            return []

        events = []
        for item in data:
            try:
                # Parse timestamp (deterministic): invalid/missing timestamps are skipped.
                timestamp_str = item.get("timestamp")
                if not timestamp_str:
                    logger.warning(
                        f"[UsageAccounting] Skipping event with missing timestamp (run={run_id})"
                    )
                    continue
                timestamp = datetime.fromisoformat(timestamp_str)

                event = UsageEvent(
                    event_id=item.get("event_id", "unknown"),
                    timestamp=timestamp,
                    tokens_used=item.get("tokens_used", 0),
                    context_chars_used=item.get("context_chars_used", 0),
                    sot_chars_used=item.get("sot_chars_used", 0),
                )
                events.append(event)
            except Exception as e:
                logger.warning(f"[UsageAccounting] Skipping invalid event: {e}")
                continue

        logger.debug(f"[UsageAccounting] Loaded {len(events)} events for run {run_id}")
        return events

    except json.JSONDecodeError as e:
        logger.warning(f"[UsageAccounting] JSON decode error in {artifact_path}: {e}")
        return []
    except Exception as e:
        logger.warning(f"[UsageAccounting] Error loading {artifact_path}: {e}")
        return []


def save_usage_events(events: List[UsageEvent], artifact_path: Path) -> None:
    """Save usage events to run-local artifact file.

    Args:
        events: List of UsageEvent instances
        artifact_path: Path to write usage_events.json
    """
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort for deterministic output
    sorted_events = sorted(events, key=lambda e: e.event_id)

    data = [
        {
            "event_id": e.event_id,
            "timestamp": e.timestamp.isoformat(),
            "tokens_used": e.tokens_used,
            "context_chars_used": e.context_chars_used,
            "sot_chars_used": e.sot_chars_used,
        }
        for e in sorted_events
    ]

    artifact_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.debug(f"[UsageAccounting] Saved {len(events)} events to {artifact_path}")


def compute_budget_remaining(
    totals: UsageTotals,
    token_cap: Optional[int] = None,
    context_cap: Optional[int] = None,
) -> float:
    """Compute remaining budget fraction.

    Args:
        totals: Current usage totals
        token_cap: Optional token budget cap
        context_cap: Optional context chars cap

    Returns:
        Fraction remaining (0.0 to 1.0), based on most constrained resource
    """
    if token_cap is None and context_cap is None:
        # No caps defined, return 1.0 (unlimited)
        return 1.0

    fractions = []

    if token_cap is not None and token_cap > 0:
        token_remaining = max(0, token_cap - totals.tokens_used) / token_cap
        fractions.append(token_remaining)

    if context_cap is not None and context_cap > 0:
        context_remaining = max(0, context_cap - totals.context_chars_used) / context_cap
        fractions.append(context_remaining)

    if not fractions:
        return 1.0

    # Return most constrained (minimum)
    return min(fractions)
