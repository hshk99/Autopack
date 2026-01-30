# autopack/memory/vector_store_ops.py
"""
Vector store operations for memory service.

IMP-MAINT-005: Extracted from memory_service.py for improved maintainability.

This module provides common vector store operation patterns used by MemoryService,
including batch upsert, filtered search, scroll, and delete operations.

The VectorStoreOperations class wraps store operations with:
- Error handling and safe fallbacks
- Consistent logging
- Common filter construction patterns
- Batch operations with point formatting
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

# Type for store (could be NullStore, FaissStore, or QdrantStore)
StoreType = Any
T = TypeVar("T")


class VectorStoreOperations:
    """Handles vector store CRUD operations.

    IMP-MAINT-005: Provides a unified interface for vector store operations
    with consistent error handling and logging.

    This class wraps the underlying store (NullStore, FaissStore, or QdrantStore)
    and provides higher-level operations for:
    - Upserting points with automatic point formatting
    - Searching with filter construction
    - Scrolling through collections
    - Batch delete operations

    Attributes:
        store: The underlying vector store instance
        _enabled: Whether memory operations are enabled
    """

    def __init__(
        self,
        store: StoreType,
        enabled: bool = True,
    ):
        """Initialize VectorStoreOperations.

        Args:
            store: The underlying vector store (NullStore, FaissStore, or QdrantStore)
            enabled: Whether memory operations are enabled
        """
        self.store = store
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Check if vector store operations are enabled."""
        return self._enabled

    def safe_call(
        self,
        label: str,
        fn: Callable[[], T],
        default: T,
    ) -> T:
        """Execute a store operation with error handling.

        Wraps store calls with try/except to ensure failures don't break
        the calling code. Logs warnings for failed operations.

        Args:
            label: Description of the operation for logging
            fn: Callable that performs the store operation
            default: Value to return if operation fails

        Returns:
            Result of fn() or default if an error occurs
        """
        try:
            return fn()
        except Exception as exc:
            logger.warning(f"[VectorStoreOps] {label} failed; continuing without memory op: {exc}")
            return default

    def upsert_point(
        self,
        collection: str,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> int:
        """Upsert a single point to a collection.

        Args:
            collection: Name of the collection
            point_id: Unique identifier for the point
            vector: Embedding vector
            payload: Metadata payload

        Returns:
            Number of points upserted (0 or 1)
        """
        if not self._enabled:
            return 0

        return self.safe_call(
            f"upsert_point/{collection}",
            lambda: self.store.upsert(
                collection,
                [{"id": point_id, "vector": vector, "payload": payload}],
            ),
            0,
        )

    def upsert_points(
        self,
        collection: str,
        points: List[Dict[str, Any]],
    ) -> int:
        """Upsert multiple points to a collection.

        Args:
            collection: Name of the collection
            points: List of point dicts with 'id', 'vector', and 'payload' keys

        Returns:
            Number of points upserted
        """
        if not self._enabled:
            return 0

        if not points:
            return 0

        return self.safe_call(
            f"upsert_points/{collection}",
            lambda: self.store.upsert(collection, points),
            0,
        )

    def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search a collection for similar vectors.

        Args:
            collection: Name of the collection
            query_vector: Query embedding vector
            limit: Maximum number of results
            filter: Optional filter dict

        Returns:
            List of result dicts with 'id', 'score', and 'payload' keys
        """
        if not self._enabled:
            return []

        return self.safe_call(
            f"search/{collection}",
            lambda: self.store.search(
                collection,
                query_vector,
                filter=filter,
                limit=limit,
            ),
            [],
        )

    def search_by_project(
        self,
        collection: str,
        query_vector: List[float],
        project_id: str,
        limit: int = 5,
        additional_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search a collection filtered by project_id.

        IMP-MEM-015: Project namespace isolation is critical for multi-project usage.

        Args:
            collection: Name of the collection
            query_vector: Query embedding vector
            project_id: Project ID to filter by
            limit: Maximum number of results
            additional_filters: Additional filter criteria to merge

        Returns:
            List of result dicts with 'id', 'score', and 'payload' keys
        """
        if not self._enabled:
            return []

        filter_dict: Dict[str, Any] = {"project_id": project_id}
        if additional_filters:
            filter_dict.update(additional_filters)

        return self.search(collection, query_vector, limit, filter_dict)

    def scroll(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Scroll through a collection to retrieve all matching entries.

        Args:
            collection: Name of the collection
            filter: Optional filter dict
            limit: Maximum number of results

        Returns:
            List of entry dicts with 'id', 'payload' keys
        """
        if not self._enabled:
            return []

        return self.safe_call(
            f"scroll/{collection}",
            lambda: self.store.scroll(collection, filter=filter, limit=limit),
            [],
        )

    def scroll_by_project(
        self,
        collection: str,
        project_id: str,
        limit: int = 100,
        additional_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Scroll through a collection filtered by project_id.

        IMP-MEM-015: Project namespace isolation.

        Args:
            collection: Name of the collection
            project_id: Project ID to filter by
            limit: Maximum number of results
            additional_filters: Additional filter criteria to merge

        Returns:
            List of entry dicts with 'id', 'payload' keys
        """
        if not self._enabled:
            return []

        filter_dict: Dict[str, Any] = {"project_id": project_id}
        if additional_filters:
            filter_dict.update(additional_filters)

        return self.scroll(collection, filter_dict, limit)

    def delete(
        self,
        collection: str,
        ids: List[str],
    ) -> int:
        """Delete points from a collection by IDs.

        Args:
            collection: Name of the collection
            ids: List of point IDs to delete

        Returns:
            Number of points deleted
        """
        if not self._enabled:
            return 0

        if not ids:
            return 0

        return self.safe_call(
            f"delete/{collection}",
            lambda: self.store.delete(collection, ids),
            0,
        )

    def count(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count entries in a collection.

        Args:
            collection: Name of the collection
            filter: Optional filter dict

        Returns:
            Number of matching entries
        """
        if not self._enabled:
            return 0

        return self.safe_call(
            f"count/{collection}",
            lambda: self.store.count(collection, filter=filter),
            0,
        )

    def get_payload(
        self,
        collection: str,
        point_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the payload for a specific point.

        Args:
            collection: Name of the collection
            point_id: ID of the point

        Returns:
            Payload dict or None if not found
        """
        if not self._enabled:
            return None

        return self.safe_call(
            f"get_payload/{collection}",
            lambda: self.store.get_payload(collection, point_id),
            None,
        )

    def update_payload(
        self,
        collection: str,
        point_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Update the payload for a specific point.

        Args:
            collection: Name of the collection
            point_id: ID of the point
            payload: New payload dict

        Returns:
            True if update succeeded, False otherwise
        """
        if not self._enabled:
            return False

        return self.safe_call(
            f"update_payload/{collection}",
            lambda: self.store.update_payload(collection, point_id, payload),
            False,
        )

    def ensure_collection(
        self,
        collection: str,
        vector_size: int = 1536,
    ) -> None:
        """Ensure a collection exists with the specified vector size.

        Args:
            collection: Name of the collection
            vector_size: Dimension of vectors in the collection
        """
        if not self._enabled:
            return

        self.safe_call(
            f"ensure_collection/{collection}",
            lambda: self.store.ensure_collection(collection, vector_size),
            None,
        )


def build_point(
    point_id: str,
    vector: List[float],
    payload: Dict[str, Any],
    project_id: Optional[str] = None,
    run_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a properly formatted point for upsert.

    Helper function to create point dicts with consistent structure.

    Args:
        point_id: Unique identifier for the point
        vector: Embedding vector
        payload: Base payload dict
        project_id: Optional project ID to add to payload
        run_id: Optional run ID to add to payload
        timestamp: Optional timestamp (defaults to current UTC time)

    Returns:
        Point dict with 'id', 'vector', and 'payload' keys
    """
    full_payload = dict(payload)

    if project_id:
        full_payload["project_id"] = project_id

    if run_id:
        full_payload["run_id"] = run_id

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    full_payload["timestamp"] = timestamp

    return {
        "id": point_id,
        "vector": vector,
        "payload": full_payload,
    }


def build_project_filter(
    project_id: str,
    additional_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a filter dict with project_id.

    IMP-MEM-015: Ensures project namespace isolation in queries.

    Args:
        project_id: Project ID to filter by
        additional_filters: Optional additional filter criteria

    Returns:
        Filter dict for use in search/scroll operations
    """
    filter_dict: Dict[str, Any] = {"project_id": project_id}
    if additional_filters:
        filter_dict.update(additional_filters)
    return filter_dict
