"""Cross-project reusable patterns for memory services.

This module extracts common patterns from MemoryService to enable reuse across
different projects. Patterns include:
- Collection CRUD operations with validation
- Project namespace isolation
- Safe operation execution
- Freshness filtering
- Payload construction

IMP-XPROJECT-001: No Cross-Project Pattern Reuse
These abstractions form the basis for a shared pattern library that can be
reused in other vector memory implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Project Namespace Isolation Pattern
# ---------------------------------------------------------------------------


class ProjectNamespaceError(ValueError):
    """Raised when project_id validation fails."""

    pass


class ProjectNamespaceMiddleware:
    """Validates and filters operations by project namespace.

    Ensures all memory operations are properly isolated by project_id
    to prevent cross-project contamination.
    """

    @staticmethod
    def validate_project_id(project_id: str, operation: str = "operation") -> None:
        """Validate that project_id is provided and non-empty.

        Args:
            project_id: The project identifier to validate
            operation: Description of the operation for error messages

        Raises:
            ProjectNamespaceError: If project_id is None, empty, or whitespace-only
        """
        if not project_id or not project_id.strip():
            raise ProjectNamespaceError(
                f"[IMP-MEM-015] project_id is required for {operation}. "
                "All memory operations must be namespaced by project to prevent "
                "cross-project contamination."
            )

    @staticmethod
    def build_project_filter(project_id: str) -> Dict[str, str]:
        """Build a filter dict for project-namespaced operations.

        Args:
            project_id: The project identifier

        Returns:
            Filter dict with project_id field
        """
        ProjectNamespaceMiddleware.validate_project_id(project_id, "filter building")
        return {"project_id": project_id}


# ---------------------------------------------------------------------------
# Safe Operation Execution Pattern
# ---------------------------------------------------------------------------


class SafeOperationExecutor:
    """Wraps operations with error handling and logging.

    Provides consistent error handling and recovery for store operations,
    returning sensible defaults on failure.
    """

    @staticmethod
    def execute(
        label: str,
        fn: Callable[[], T],
        default: T,
        logger: Optional[Any] = None,
    ) -> T:
        """Execute a function with error handling.

        Args:
            label: Label for the operation (used in logging)
            fn: The function to execute
            default: Default value to return on failure
            logger: Optional logger instance

        Returns:
            Result of fn() on success, default value on failure
        """
        try:
            return fn()
        except Exception as e:
            if logger:
                logger.debug(f"[SafeOperationExecutor] {label} failed: {e}", exc_info=True)
            return default


# ---------------------------------------------------------------------------
# Payload Construction Pattern
# ---------------------------------------------------------------------------


@dataclass
class PayloadMetadata:
    """Common metadata fields for collection payloads."""

    type: str
    project_id: str
    timestamp: Optional[str] = None
    run_id: Optional[str] = None
    phase_id: Optional[str] = None
    task_type: Optional[str] = None
    compressed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to payload dict, excluding None values."""
        result = {"type": self.type, "project_id": self.project_id}

        if self.timestamp is None:
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
        else:
            result["timestamp"] = self.timestamp

        if self.run_id is not None:
            result["run_id"] = self.run_id
        if self.phase_id is not None:
            result["phase_id"] = self.phase_id
        if self.task_type is not None:
            result["task_type"] = self.task_type
        if self.compressed:
            result["compressed"] = True

        return result


class PayloadBuilder:
    """Builds consistent payloads for collection operations.

    Ensures all payloads follow a consistent schema with required fields
    and proper timestamp handling.
    """

    @staticmethod
    def build(
        type_: str,
        project_id: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        task_type: Optional[str] = None,
        timestamp: Optional[str] = None,
        compressed: bool = False,
    ) -> Dict[str, Any]:
        """Build a complete payload dict.

        Args:
            type_: Collection type identifier
            project_id: Project identifier
            extra_fields: Additional fields to include in payload
            run_id: Optional run identifier
            phase_id: Optional phase identifier
            task_type: Optional task type
            timestamp: Optional custom timestamp (ISO format)
            compressed: Whether content was compressed

        Returns:
            Complete payload dict
        """
        metadata = PayloadMetadata(
            type=type_,
            project_id=project_id,
            run_id=run_id,
            phase_id=phase_id,
            task_type=task_type,
            timestamp=timestamp,
            compressed=compressed,
        )
        payload = metadata.to_dict()

        if extra_fields:
            payload.update(extra_fields)

        return payload


# ---------------------------------------------------------------------------
# Freshness Filtering Pattern
# ---------------------------------------------------------------------------


class FreshnessPipeline:
    """Reusable pipeline for freshness filtering in search results.

    Applies configurable freshness thresholds to filter out stale results
    based on timestamp information in payloads.
    """

    def __init__(self, is_fresh_fn: Callable[[Optional[str], int], bool]):
        """Initialize with freshness check function.

        Args:
            is_fresh_fn: Function that takes (timestamp: str, max_age_hours: int) -> bool
        """
        self.is_fresh_fn = is_fresh_fn

    def filter_results(
        self,
        results: List[Dict[str, Any]],
        max_age_hours: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Filter results by freshness.

        Args:
            results: List of search results with payloads
            max_age_hours: Maximum age in hours
            limit: Optional limit on returned results

        Returns:
            Filtered results, optionally limited
        """
        if not results:
            return []

        filtered = [
            r
            for r in results
            if self.is_fresh_fn(r.get("payload", {}).get("timestamp"), max_age_hours)
        ]

        if limit is not None:
            filtered = filtered[:limit]

        return filtered


# ---------------------------------------------------------------------------
# Vector Search Builder Pattern
# ---------------------------------------------------------------------------


class VectorSearchBuilder:
    """Fluent builder for vector search operations.

    Simplifies construction of complex vector searches with multiple
    filters and parameters.
    """

    def __init__(self, query_text: str, embed_fn: Callable[[str], List[float]]):
        """Initialize builder with query text.

        Args:
            query_text: The text to embed and search for
            embed_fn: Function to embed text into vectors
        """
        self.query_text = query_text
        self.embed_fn = embed_fn
        self.query_vector = self.embed_fn(query_text)
        self.filters: Dict[str, Any] = {}
        self.limit: int = 10

    def with_project_filter(self, project_id: str) -> "VectorSearchBuilder":
        """Add project namespace filter.

        Args:
            project_id: Project to filter by

        Returns:
            Self for chaining
        """
        ProjectNamespaceMiddleware.validate_project_id(project_id)
        self.filters = ProjectNamespaceMiddleware.build_project_filter(project_id)
        return self

    def with_filters(self, filters: Dict[str, Any]) -> "VectorSearchBuilder":
        """Add custom filters.

        Args:
            filters: Filter dict to merge

        Returns:
            Self for chaining
        """
        self.filters.update(filters)
        return self

    def with_limit(self, limit: int) -> "VectorSearchBuilder":
        """Set result limit.

        Args:
            limit: Maximum results

        Returns:
            Self for chaining
        """
        self.limit = limit
        return self

    def build(self) -> Dict[str, Any]:
        """Build the search parameters dict.

        Returns:
            Dict with 'vector', 'filters', 'limit' keys
        """
        return {
            "vector": self.query_vector,
            "filters": self.filters,
            "limit": self.limit,
        }


# ---------------------------------------------------------------------------
# Base Collection Handler Pattern
# ---------------------------------------------------------------------------


class BaseCollectionHandler(ABC):
    """Abstract base for collection write/search operations.

    Defines the pattern for paired write/search operations on a collection,
    ensuring consistent behavior across different collection types.
    """

    @property
    @abstractmethod
    def collection_name(self) -> str:
        """Name of the collection."""
        pass

    @property
    @abstractmethod
    def type_identifier(self) -> str:
        """Type identifier for payloads in this collection."""
        pass

    @abstractmethod
    def validate_write_payload(self, payload: Dict[str, Any]) -> bool:
        """Validate payload before writing.

        Args:
            payload: Payload dict to validate

        Returns:
            True if valid, False otherwise

        Raises:
            ValueError: On validation errors
        """
        pass

    @abstractmethod
    def validate_search_query(self, query: str) -> bool:
        """Validate search query before execution.

        Args:
            query: Search query string

        Returns:
            True if valid, False otherwise

        Raises:
            ValueError: On validation errors
        """
        pass

    @abstractmethod
    def normalize_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw store result to standard format.

        Args:
            raw_result: Result from store

        Returns:
            Normalized result dict
        """
        pass

    def get_type(self) -> str:
        """Get the payload type identifier.

        Returns:
            Type string for this collection
        """
        return self.type_identifier


# ---------------------------------------------------------------------------
# Metadata Enrichment Pattern
# ---------------------------------------------------------------------------


class MetadataEnricher:
    """Adds quality signals and context to retrieval results.

    Consolidates metadata enrichment logic for consistent result formatting
    across different collection types.
    """

    @staticmethod
    def enrich_with_timestamp(result: Dict[str, Any]) -> Dict[str, Any]:
        """Add timestamp metadata.

        Args:
            result: Result dict

        Returns:
            Result with timestamp metadata added
        """
        payload = result.get("payload", {})
        timestamp = payload.get("timestamp")

        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
                result["metadata"] = result.get("metadata", {})
                result["metadata"]["age_hours"] = age_hours
                result["metadata"]["timestamp"] = timestamp
            except (ValueError, AttributeError):
                pass

        return result

    @staticmethod
    def enrich_with_confidence(
        result: Dict[str, Any],
        confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Add confidence metadata.

        Args:
            result: Result dict
            confidence: Optional confidence score

        Returns:
            Result with confidence metadata added
        """
        result["metadata"] = result.get("metadata", {})

        if confidence is not None:
            result["metadata"]["confidence"] = confidence
        elif "score" in result:
            # Use search score as confidence
            result["metadata"]["confidence"] = result["score"]

        return result

    @staticmethod
    def enrich_batch(
        results: List[Dict[str, Any]],
        enrichers: Optional[List[Callable[[Dict[str, Any]], Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Apply multiple enrichers to a batch of results.

        Args:
            results: List of results
            enrichers: Optional list of enricher functions

        Returns:
            Enriched results
        """
        enriched = results
        default_enrichers = [
            MetadataEnricher.enrich_with_timestamp,
            MetadataEnricher.enrich_with_confidence,
        ]

        all_enrichers = enrichers or default_enrichers

        for enricher in all_enrichers:
            enriched = [enricher(r) for r in enriched]

        return enriched
