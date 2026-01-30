# autopack/memory/deduplication.py
"""
Content-based deduplication for memory insights.

IMP-MAINT-003: Extracted from memory_service.py for improved maintainability.

This module provides content-hash deduplication and semantic similarity matching
to prevent memory bloat from duplicate failure patterns.

IMP-AUTO-003: Concurrent write safety with content-hash deduplication.
IMP-MEM-006: Content-based semantic deduplication using embedding similarity.
"""

import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Set

from .embeddings import sync_embed_text

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ContentDeduplicator:
    """Handles content-based deduplication for memory insights.

    IMP-MAINT-003: Extracted from MemoryService to improve maintainability.

    This class provides:
    - Content-hash deduplication for identical content (IMP-AUTO-003)
    - Semantic similarity matching for near-duplicate detection (IMP-MEM-006)
    - Thread-safe write operations for concurrent phase execution

    Attributes:
        _write_lock: Lock for thread-safe content hash tracking
        _content_hashes: Set of content hashes already written
    """

    def __init__(self) -> None:
        """Initialize the ContentDeduplicator."""
        # IMP-AUTO-003: Concurrent write safety for parallel phase execution
        # Lock protects against concurrent write_telemetry_insight calls
        self._write_lock = threading.Lock()
        # Track content hashes to deduplicate insights with identical content
        self._content_hashes: Set[str] = set()

    def compute_content_hash(self, insight_type: str, content: str) -> str:
        """Compute a content hash for deduplication.

        IMP-AUTO-003: Creates a deterministic hash from insight type and content
        to identify duplicate entries.

        Args:
            insight_type: Type of the insight (e.g., "failure_mode", "cost_sink")
            content: The content text to hash

        Returns:
            16-character hex hash of the content
        """
        return hashlib.sha256(f"{insight_type}:{content}".encode()).hexdigest()[:16]

    def check_and_track_hash(self, content_hash: str) -> bool:
        """Thread-safe check and track for a content hash.

        IMP-AUTO-003: Atomically checks if a hash exists and adds it if not,
        preventing race conditions during concurrent writes.

        Args:
            content_hash: The content hash to check and track

        Returns:
            True if this is a new hash (not a duplicate), False if already tracked
        """
        with self._write_lock:
            if content_hash in self._content_hashes:
                logger.debug(f"[IMP-AUTO-003] Duplicate insight skipped: {content_hash}")
                return False

            # Track the hash before writing to prevent race conditions
            self._content_hashes.add(content_hash)
            return True

    def clear_hashes(self) -> None:
        """Clear tracked content hashes.

        Useful for testing or when starting a new session.
        """
        with self._write_lock:
            self._content_hashes.clear()

    def find_similar_insights(
        self,
        insight: Dict[str, Any],
        enabled: bool,
        store: Any,
        safe_store_call: Callable[[str, Callable, Any], Any],
        collection_errors_ci: str,
        collection_doctor_hints: str,
        collection_run_summaries: str,
        threshold: float = 0.9,
    ) -> List[Dict[str, Any]]:
        """Find semantically similar insights using embedding similarity.

        IMP-MEM-006: Prevents memory bloat by detecting near-duplicate insights
        before storage. Uses vector similarity to find insights with similar
        content, even if not exact matches.

        Args:
            insight: The insight dict containing content/description to match.
            enabled: Whether memory is enabled.
            store: The vector store instance.
            safe_store_call: Function for safe store operations.
            collection_errors_ci: Name of errors/CI collection.
            collection_doctor_hints: Name of doctor hints collection.
            collection_run_summaries: Name of run summaries collection.
            threshold: Minimum similarity score (0-1) to consider as duplicate.
                       Default 0.9 requires very high similarity.

        Returns:
            List of similar insights with their payloads and scores, sorted
            by similarity score descending. Empty list if no matches found.
        """
        if not enabled:
            return []

        insight_type = insight.get("insight_type", "unknown")
        description = insight.get("description", "")
        content = insight.get("content", description)

        # Build search text same as used for storage
        search_text = f"{insight_type}:{content}"
        if not search_text.strip(":"):
            return []

        try:
            # Create embedding for similarity search
            query_vector = sync_embed_text(search_text)

            # Determine which collection to search based on insight type
            if insight_type == "failure_mode":
                collection = collection_errors_ci
            elif insight_type == "retry_cause":
                collection = collection_doctor_hints
            else:
                # cost_sink and generic insights go to run_summaries
                collection = collection_run_summaries

            # Search for similar insights with telemetry_insight task_type
            results = safe_store_call(
                f"_find_similar_insights/{collection}",
                lambda: store.search(
                    collection,
                    query_vector,
                    filter={"task_type": "telemetry_insight"},
                    limit=5,
                ),
                [],
            )

            # Filter by similarity threshold and return with metadata
            similar = []
            for result in results:
                score = result.get("score", 0)
                if score >= threshold:
                    similar.append(
                        {
                            "id": result.get("id"),
                            "payload": result.get("payload", {}),
                            "score": score,
                            "collection": collection,
                        }
                    )

            # Sort by score descending (highest similarity first)
            similar.sort(key=lambda x: x.get("score", 0), reverse=True)

            if similar:
                logger.debug(
                    f"[IMP-MEM-006] Found {len(similar)} similar insights "
                    f"(threshold={threshold}): top score={similar[0]['score']:.3f}"
                )

            return similar

        except Exception as e:
            logger.warning(f"[IMP-MEM-006] Error finding similar insights: {e}")
            return []

    def merge_insights(
        self,
        existing: Dict[str, Any],
        new_insight: Dict[str, Any],
        enabled: bool,
        store: Any,
        safe_store_call: Callable[[str, Callable, Any], Any],
        collection_run_summaries: str,
    ) -> str:
        """Merge a new insight into an existing similar insight.

        IMP-MEM-006: Instead of storing duplicate content, this method updates
        the existing insight with merged metadata: increments occurrence count,
        updates timestamp, and preserves the highest confidence value.

        Args:
            existing: Dict containing 'id', 'payload', and 'collection' of
                      the existing similar insight.
            new_insight: The new insight dict that would have been stored.
            enabled: Whether memory is enabled.
            store: The vector store instance.
            safe_store_call: Function for safe store operations.
            collection_run_summaries: Default collection name for fallback.

        Returns:
            The existing insight's ID (now updated with merged data), or empty
            string if merge failed.
        """
        if not enabled:
            return ""

        existing_id = existing.get("id", "")
        collection = existing.get("collection", collection_run_summaries)
        payload = existing.get("payload", {})

        if not existing_id:
            logger.warning("[IMP-MEM-006] Cannot merge: missing existing insight ID")
            return ""

        try:
            # Update occurrence count
            current_occurrences = payload.get("occurrence_count", 1)
            new_occurrences = current_occurrences + 1

            # Update timestamp to latest
            new_timestamp = datetime.now(timezone.utc).isoformat()

            # Merge metadata - keep highest confidence
            existing_confidence = payload.get("confidence", 0.5)
            new_confidence = new_insight.get("confidence", 0.5)
            merged_confidence = max(existing_confidence, new_confidence)

            # Prepare updated payload
            updated_payload = {
                "occurrence_count": new_occurrences,
                "last_occurrence": new_timestamp,
                "confidence": merged_confidence,
                # Track merge history
                "merge_count": payload.get("merge_count", 0) + 1,
                "last_merged_at": new_timestamp,
            }

            # Preserve suggested_action if new one is provided
            new_action = new_insight.get("suggested_action")
            if new_action and new_action != payload.get("suggested_action"):
                # Append to existing actions or set new one
                existing_actions = payload.get("suggested_actions", [])
                if payload.get("suggested_action"):
                    existing_actions = [payload["suggested_action"]] + existing_actions
                if new_action not in existing_actions:
                    existing_actions.append(new_action)
                updated_payload["suggested_actions"] = existing_actions[:5]  # Keep max 5

            # Update the existing record
            success = safe_store_call(
                f"_merge_insights/{collection}",
                lambda: store.update_payload(collection, existing_id, updated_payload),
                False,
            )

            if success:
                logger.info(
                    f"[IMP-MEM-006] Merged insight into existing (id={existing_id}, "
                    f"occurrences={new_occurrences}, confidence={merged_confidence:.2f})"
                )
                return existing_id
            else:
                logger.warning(
                    f"[IMP-MEM-006] Failed to update existing insight {existing_id}, "
                    "will store as new"
                )
                return ""

        except Exception as e:
            logger.warning(f"[IMP-MEM-006] Error merging insights: {e}")
            return ""
