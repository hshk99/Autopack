# autopack/memory/freshness_filter.py
"""
Freshness filtering for memory retrieval operations.

IMP-MAINT-005: Extracted from memory_service.py for improved maintainability.

This module provides freshness checking, staleness policies, and confidence
scoring for memory retrieval operations. It includes:

- Timestamp parsing and age calculation
- Per-collection freshness thresholds (IMP-MEM-004)
- Confidence scoring combining relevance and freshness (IMP-LOOP-019)
- Context metadata enrichment

IMP-LOOP-003: Freshness filtering for memory retrieval.
IMP-LOOP-014: Mandatory freshness filtering with positive thresholds.
IMP-LOOP-019: Context relevance/confidence metadata.
IMP-MEM-004: Per-collection staleness policies.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IMP-LOOP-023: Default freshness threshold (30 days)
# ---------------------------------------------------------------------------
DEFAULT_MEMORY_FRESHNESS_HOURS = 720  # 30 days


# ---------------------------------------------------------------------------
# IMP-MEM-004: Per-Collection Staleness Policies
# ---------------------------------------------------------------------------
# Different memory collections have different freshness requirements:
# - Error patterns need quick attention (24h)
# - Test/CI results need frequent refresh (48h)
# - Learning hints have moderate freshness (72h - default)
# - Code docs change less frequently (168h = 1 week)
# - Planning artifacts are more stable (168h)
# - SOT docs are reference material (336h = 2 weeks)

# Collection names (per plan)
COLLECTION_CODE_DOCS = "code_docs"
COLLECTION_RUN_SUMMARIES = "run_summaries"
COLLECTION_ERRORS_CI = "errors_ci"
COLLECTION_DOCTOR_HINTS = "doctor_hints"
COLLECTION_PLANNING = "planning"
COLLECTION_SOT_DOCS = "sot_docs"

COLLECTION_FRESHNESS_HOURS: Dict[str, int] = {
    COLLECTION_ERRORS_CI: 24,  # Errors should be addressed quickly
    COLLECTION_RUN_SUMMARIES: 48,  # Test/CI results need frequent refresh
    COLLECTION_DOCTOR_HINTS: 72,  # Hints have moderate freshness
    COLLECTION_CODE_DOCS: 168,  # Code docs change less frequently (1 week)
    COLLECTION_PLANNING: 168,  # Planning artifacts are more stable
    COLLECTION_SOT_DOCS: 336,  # SOT docs are reference material (2 weeks)
    "default": 720,  # Fallback to DEFAULT_MEMORY_FRESHNESS_HOURS (IMP-LOOP-023: 30 days)
}


def get_freshness_threshold(collection_name: str) -> int:
    """Get the freshness threshold in hours for a specific collection.

    IMP-MEM-004: Different collections have different staleness policies.
    Error patterns age differently than code docs, so each collection type
    has its own configurable freshness threshold.

    Args:
        collection_name: The name of the memory collection.

    Returns:
        Freshness threshold in hours for the collection.
    """
    return COLLECTION_FRESHNESS_HOURS.get(collection_name, COLLECTION_FRESHNESS_HOURS["default"])


# ---------------------------------------------------------------------------
# Timestamp Parsing and Freshness Checking
# ---------------------------------------------------------------------------


def parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string to datetime object.

    Args:
        timestamp_str: ISO format timestamp string (e.g., "2024-01-15T10:30:00+00:00")

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None
    try:
        # Handle ISO format with timezone
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return None


def is_fresh(
    timestamp_str: Optional[str],
    max_age_hours: float,
    now: Optional[datetime] = None,
) -> bool:
    """Check if a timestamp is within the freshness threshold.

    Args:
        timestamp_str: ISO format timestamp string
        max_age_hours: Maximum age in hours for data to be considered fresh.
                      IMP-LOOP-014: Must be positive; non-positive values
                      are treated as using the default freshness threshold.
        now: Current time (defaults to UTC now)

    Returns:
        True if timestamp is within max_age_hours, False otherwise
    """
    # IMP-LOOP-014: Freshness filtering is mandatory - non-positive values
    # should not bypass the check. Log warning and use default.
    if max_age_hours <= 0:
        logger.warning(
            "[IMP-LOOP-014] is_fresh called with max_age_hours=%s (must be positive). "
            "Using DEFAULT_MEMORY_FRESHNESS_HOURS=%s instead.",
            max_age_hours,
            DEFAULT_MEMORY_FRESHNESS_HOURS,
        )
        max_age_hours = DEFAULT_MEMORY_FRESHNESS_HOURS

    parsed_ts = parse_timestamp(timestamp_str)
    if parsed_ts is None:
        return False  # Can't determine freshness without valid timestamp

    now = now or datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware for comparison
    if parsed_ts.tzinfo is None:
        parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_hours = (now - parsed_ts).total_seconds() / 3600
    return age_hours <= max_age_hours


def calculate_age_hours(
    timestamp_str: Optional[str],
    now: Optional[datetime] = None,
) -> float:
    """Calculate age in hours from timestamp.

    Args:
        timestamp_str: ISO format timestamp string
        now: Current time (defaults to UTC now)

    Returns:
        Age in hours, or -1.0 if timestamp is invalid/missing
    """
    parsed_ts = parse_timestamp(timestamp_str)
    if parsed_ts is None:
        return -1.0  # Unknown age

    now = now or datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware
    if parsed_ts.tzinfo is None:
        parsed_ts = parsed_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    age_seconds = (now - parsed_ts).total_seconds()
    return max(0.0, age_seconds / 3600)


# ---------------------------------------------------------------------------
# IMP-LOOP-019: Context Relevance/Confidence Metadata
# ---------------------------------------------------------------------------

# Confidence thresholds for context quality assessment
LOW_CONFIDENCE_THRESHOLD = 0.3
MEDIUM_CONFIDENCE_THRESHOLD = 0.6

# Age thresholds for confidence decay (hours)
FRESH_AGE_HOURS = 24  # Context younger than this gets full score
STALE_AGE_HOURS = 168  # Context older than this (1 week) gets penalized


def calculate_confidence(
    relevance_score: float,
    age_hours: float,
) -> float:
    """Calculate confidence score combining relevance and freshness.

    IMP-LOOP-019: Confidence is based on:
    - Relevance score from vector search (primary factor)
    - Age decay: fresh context is more reliable than stale context

    Args:
        relevance_score: Similarity score from vector search (0.0-1.0)
        age_hours: Age of context in hours (-1 for unknown)

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Normalize relevance to 0-1 range (scores can sometimes exceed 1.0)
    relevance = max(0.0, min(1.0, relevance_score))

    # Unknown age gets a penalty but not complete rejection
    if age_hours < 0:
        age_factor = 0.5  # Unknown age = 50% confidence in freshness
    elif age_hours <= FRESH_AGE_HOURS:
        age_factor = 1.0  # Fresh content gets full score
    elif age_hours >= STALE_AGE_HOURS:
        age_factor = 0.5  # Stale content gets 50% score
    else:
        # Linear decay between fresh and stale thresholds
        decay_range = STALE_AGE_HOURS - FRESH_AGE_HOURS
        age_beyond_fresh = age_hours - FRESH_AGE_HOURS
        age_factor = 1.0 - (0.5 * age_beyond_fresh / decay_range)

    # Combine: relevance is weighted more heavily (70%) than freshness (30%)
    confidence = 0.7 * relevance + 0.3 * age_factor

    return max(0.0, min(1.0, confidence))


@dataclass
class ContextMetadata:
    """Metadata about context relevance and quality.

    IMP-LOOP-019: Provides relevance scoring and confidence signals
    so callers know how fresh and relevant the retrieved context is.

    Attributes:
        content: The actual context content string
        relevance_score: Similarity/relevance score from vector search (0.0-1.0)
        age_hours: Age of the context in hours since creation
        confidence: Computed confidence score combining relevance and freshness (0.0-1.0)
        is_low_confidence: True if confidence is below the threshold for reliable use
        source_type: Type of context source (e.g., 'error', 'summary', 'hint', 'code')
        source_id: Original ID of the memory record
    """

    content: str
    relevance_score: float
    age_hours: float
    confidence: float
    is_low_confidence: bool
    source_type: str = ""
    source_id: str = ""

    @property
    def confidence_level(self) -> str:
        """Human-readable confidence level."""
        if self.confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
            return "high"
        elif self.confidence >= LOW_CONFIDENCE_THRESHOLD:
            return "medium"
        return "low"


def enrich_with_metadata(
    result: Dict[str, Any],
    source_type: str = "",
    content_key: str = "content",
    now: Optional[datetime] = None,
) -> ContextMetadata:
    """Enrich a search result with context metadata.

    IMP-LOOP-019: Converts a raw search result dict to ContextMetadata
    with relevance scoring and confidence signals.

    Args:
        result: Search result dict with 'id', 'score', and 'payload' keys
        source_type: Type of context source for identification
        content_key: Key in payload to use for content extraction
        now: Current time for age calculation

    Returns:
        ContextMetadata with all quality signals
    """
    # Extract fields from result
    score = result.get("score", 0.0)
    payload = result.get("payload", {})
    source_id = result.get("id", "")

    # Try to extract content from various common keys
    content = ""
    for key in [content_key, "content", "summary", "error_text", "hint", "description"]:
        if key in payload and payload[key]:
            content = str(payload[key])
            break

    # Get timestamp and calculate age
    timestamp = payload.get("timestamp")
    age_hours = calculate_age_hours(timestamp, now)

    # Calculate confidence
    confidence = calculate_confidence(score, age_hours)
    is_low_confidence = confidence < LOW_CONFIDENCE_THRESHOLD

    return ContextMetadata(
        content=content,
        relevance_score=score,
        age_hours=age_hours,
        confidence=confidence,
        is_low_confidence=is_low_confidence,
        source_type=source_type or payload.get("type", ""),
        source_id=source_id,
    )


# ---------------------------------------------------------------------------
# FreshnessFilter Class
# ---------------------------------------------------------------------------


class FreshnessFilter:
    """Handles freshness filtering for memory retrieval.

    IMP-MAINT-005: Provides a class-based interface for freshness filtering
    operations, wrapping the module-level functions for easier composition.

    IMP-MEM-004: Supports per-collection staleness policies.
    IMP-LOOP-019: Provides confidence scoring and metadata enrichment.

    Attributes:
        default_max_age_hours: Default freshness threshold when not specified
    """

    def __init__(self, default_max_age_hours: int = DEFAULT_MEMORY_FRESHNESS_HOURS):
        """Initialize the FreshnessFilter.

        Args:
            default_max_age_hours: Default freshness threshold in hours
        """
        self.default_max_age_hours = default_max_age_hours

    def is_fresh(
        self,
        timestamp_str: Optional[str],
        max_age_hours: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Check if a timestamp is within the freshness threshold.

        Args:
            timestamp_str: ISO format timestamp string
            max_age_hours: Maximum age in hours (uses default if None)
            now: Current time (defaults to UTC now)

        Returns:
            True if timestamp is within max_age_hours, False otherwise
        """
        effective_max_age = (
            max_age_hours if max_age_hours is not None else self.default_max_age_hours
        )
        return is_fresh(timestamp_str, effective_max_age, now)

    def filter_by_freshness(
        self,
        items: List[Dict[str, Any]],
        max_age_hours: Optional[float] = None,
        timestamp_field: str = "timestamp",
    ) -> List[Dict[str, Any]]:
        """Filter items by freshness threshold.

        Args:
            items: List of items to filter
            max_age_hours: Maximum age in hours (uses default if None)
            timestamp_field: Field name containing the timestamp

        Returns:
            List of items within the freshness threshold
        """
        effective_max_age = (
            max_age_hours if max_age_hours is not None else self.default_max_age_hours
        )
        return [
            item
            for item in items
            if is_fresh(
                (
                    item.get("payload", {}).get(timestamp_field)
                    if isinstance(item.get("payload"), dict)
                    else item.get(timestamp_field)
                ),
                effective_max_age,
            )
        ]

    def get_freshness_for_collection(self, collection_name: str) -> int:
        """Get the freshness threshold for a specific collection.

        IMP-MEM-004: Uses per-collection staleness policies.

        Args:
            collection_name: The name of the memory collection

        Returns:
            Freshness threshold in hours for the collection
        """
        return get_freshness_threshold(collection_name)

    def enrich_with_metadata(
        self,
        result: Dict[str, Any],
        source_type: str = "",
        content_key: str = "content",
        now: Optional[datetime] = None,
    ) -> ContextMetadata:
        """Enrich a search result with context metadata.

        Args:
            result: Search result dict with 'id', 'score', and 'payload' keys
            source_type: Type of context source for identification
            content_key: Key in payload to use for content extraction
            now: Current time for age calculation

        Returns:
            ContextMetadata with all quality signals
        """
        return enrich_with_metadata(result, source_type, content_key, now)

    def calculate_confidence(
        self,
        relevance_score: float,
        age_hours: float,
    ) -> float:
        """Calculate confidence score combining relevance and freshness.

        Args:
            relevance_score: Similarity score from vector search (0.0-1.0)
            age_hours: Age of context in hours (-1 for unknown)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        return calculate_confidence(relevance_score, age_hours)
