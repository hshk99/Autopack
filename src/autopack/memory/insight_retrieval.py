# autopack/memory/insight_retrieval.py
"""
Insight retrieval for ROAD-C task generation.

IMP-MAINT-003: Extracted from memory_service.py for improved maintainability.

This module provides insight retrieval, confidence management, and decay
lifecycle handling for the self-improvement loop.

IMP-ARCH-010/016: Retrieve insights from memory for task generation.
IMP-LOOP-003: Freshness filtering for memory retrieval.
IMP-LOOP-016: Confidence filtering for insights.
IMP-LOOP-034: Confidence decay lifecycle management.
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .embeddings import sync_embed_text

if TYPE_CHECKING:
    from .confidence_manager import ConfidenceManager

logger = logging.getLogger(__name__)


class InsightRetriever:
    """Handles insight retrieval and confidence management.

    IMP-MAINT-003: Extracted from MemoryService to improve maintainability.

    This class provides:
    - Insight retrieval with freshness filtering (IMP-LOOP-003)
    - Confidence filtering and decay (IMP-LOOP-016, IMP-LOOP-034)
    - High-occurrence insight detection (IMP-LOOP-032)
    - Confidence update persistence (IMP-LOOP-031)

    Attributes:
        _confidence_manager: Optional manager for confidence decay lifecycle
    """

    def __init__(self) -> None:
        """Initialize the InsightRetriever."""
        # IMP-LOOP-034: Initialize confidence manager for decay lifecycle
        self._confidence_manager: Optional["ConfidenceManager"] = None

    def set_confidence_manager(self, confidence_manager: "ConfidenceManager") -> None:
        """Set the confidence manager for decay lifecycle management.

        IMP-LOOP-034: The ConfidenceManager handles confidence decay over time
        and updates based on task outcomes. Setting it here enables automatic
        decay application when retrieving insights.

        Args:
            confidence_manager: ConfidenceManager instance for decay calculations.
        """
        self._confidence_manager = confidence_manager
        # Connect memory service to confidence manager for persistence
        # Note: The MemoryService calls confidence_manager.set_memory_service()
        logger.debug("[IMP-LOOP-034] Confidence manager connected to InsightRetriever")

    def get_confidence_manager(self) -> Optional["ConfidenceManager"]:
        """Get the confidence manager instance.

        Returns:
            ConfidenceManager if set, None otherwise.
        """
        return self._confidence_manager

    def get_decayed_confidence(
        self,
        insight_id: str,
        original_confidence: float = 1.0,
        created_at: Optional[datetime] = None,
    ) -> float:
        """Get confidence with decay applied for an insight.

        IMP-LOOP-034: Uses the ConfidenceManager to calculate decayed confidence
        based on age and task outcomes. Falls back to original confidence if
        no confidence manager is configured.

        Args:
            insight_id: Unique identifier for the insight.
            original_confidence: Original confidence score if not tracked.
            created_at: Creation timestamp if not tracked.

        Returns:
            Decayed confidence score (0.0-1.0).
        """
        if self._confidence_manager is None:
            logger.debug(
                "[IMP-LOOP-034] No confidence manager configured, returning original confidence"
            )
            return original_confidence

        return self._confidence_manager.get_effective_confidence(
            insight_id=insight_id,
            original_confidence=original_confidence,
            created_at=created_at,
        )

    def apply_confidence_decay(
        self,
        insights: List[Dict[str, Any]],
        confidence_field: str = "confidence",
        timestamp_field: str = "timestamp",
    ) -> List[Dict[str, Any]]:
        """Apply confidence decay to a list of insights.

        IMP-LOOP-034: Applies time-based decay to insights using the
        ConfidenceManager. Modifies the confidence field in-place.

        Args:
            insights: List of insight dictionaries.
            confidence_field: Name of the confidence field in each insight.
            timestamp_field: Name of the timestamp field for age calculation.

        Returns:
            The same list with decayed confidence values applied.
        """
        if self._confidence_manager is None:
            logger.debug(
                "[IMP-LOOP-034] No confidence manager configured, skipping decay application"
            )
            return insights

        return self._confidence_manager.apply_decay_to_insights(
            insights=insights,
            confidence_field=confidence_field,
            created_at_field=timestamp_field,
        )

    def retrieve_insights(
        self,
        query: str,
        project_id: str,
        enabled: bool,
        store: Any,
        safe_store_call: Callable[[str, Callable, Any], Any],
        validate_project_id: Callable[[str, str], None],
        is_fresh: Callable[[Optional[str], float], bool],
        get_freshness_threshold: Callable[[str], int],
        collection_run_summaries: str,
        collection_errors_ci: str,
        collection_doctor_hints: str,
        default_freshness_hours: float,
        limit: int = 10,
        max_age_hours: Optional[float] = None,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve insights from memory for task generation (IMP-ARCH-010/016).

        This method is called by the ROAD-C AutonomousTaskGenerator to retrieve
        telemetry insights that can be converted into improvement tasks.

        IMP-ARCH-016: Fixed to query across collections where telemetry insights
        are actually written (run_summaries, errors_ci, doctor_hints) and filter
        for task_type="telemetry_insight".

        IMP-LOOP-003: Added freshness check to filter out stale insights based on
        timestamp. Stale data can lead to outdated context being used for task creation.

        IMP-LOOP-014: Freshness filtering is MANDATORY. Attempts to disable via
        0/negative values are ignored with a warning. Audit logging added.

        IMP-LOOP-016: Added confidence filtering to exclude low-confidence insights
        from task generation, improving decision quality.

        IMP-MEM-015: project_id is now REQUIRED to prevent cross-project contamination.

        Args:
            query: Search query to find relevant insights
            project_id: Project ID to filter by (REQUIRED - IMP-MEM-015)
            enabled: Whether memory is enabled.
            store: The vector store instance.
            safe_store_call: Function for safe store operations.
            validate_project_id: Function to validate project namespace.
            is_fresh: Function to check if timestamp is fresh.
            get_freshness_threshold: Function to get collection freshness threshold.
            collection_run_summaries: Name of run summaries collection.
            collection_errors_ci: Name of errors/CI collection.
            collection_doctor_hints: Name of doctor hints collection.
            default_freshness_hours: Default freshness threshold in hours.
            limit: Maximum number of results to return
            max_age_hours: Maximum age in hours for insights to be considered fresh.
                          Defaults to DEFAULT_MEMORY_FRESHNESS_HOURS (720 hours / 30 days).
                          Must be positive; attempts to disable are ignored.
            min_confidence: Optional minimum confidence threshold (0.0-1.0).
                           If provided, insights with confidence below this are filtered.

        Returns:
            List of insight dictionaries with content, metadata, and score

        Raises:
            ProjectNamespaceError: If project_id is empty or None (IMP-MEM-015)
        """
        if not enabled:
            logger.debug("[MemoryService] Memory disabled, returning empty insights")
            return []

        # IMP-MEM-015: Validate project namespace isolation
        validate_project_id(project_id, "retrieve_insights")

        # IMP-LOOP-014: Enforce mandatory freshness filtering with validation
        # IMP-MEM-004: When max_age_hours is None, use per-collection thresholds
        use_per_collection_freshness = max_age_hours is None
        if max_age_hours is not None and max_age_hours <= 0:
            logger.warning(
                "[IMP-LOOP-014] max_age_hours=%s is invalid (must be positive). "
                "Freshness filtering is mandatory for the self-improvement loop. "
                "Override ignored - using per-collection thresholds.",
                max_age_hours,
            )
            use_per_collection_freshness = True

        # IMP-LOOP-014/IMP-MEM-004: Audit log for freshness filter applied
        # IMP-MEM-015: project_id is now required - no fallback to "all"
        if use_per_collection_freshness:
            logger.info(
                "[IMP-MEM-004] Retrieving insights with per-collection freshness thresholds, "
                "project_id=%s, limit=%s",
                project_id,
                limit,
            )
        else:
            logger.info(
                "[IMP-LOOP-014] Retrieving insights with freshness_filter=%sh, project_id=%s, limit=%s",
                max_age_hours,
                project_id,
                limit,
            )

        try:
            # Embed the query text
            query_vector = sync_embed_text(query)

            # Collections where write_telemetry_insight routes data
            insight_collections = [
                collection_run_summaries,  # cost_sink and generic insights
                collection_errors_ci,  # failure_mode insights
                collection_doctor_hints,  # retry_cause insights
            ]

            all_insights = []
            stale_count = 0
            # Fetch more results to account for freshness filtering
            per_collection_limit = max((limit * 2) // len(insight_collections), 5)

            for collection in insight_collections:
                # IMP-MEM-004: Get collection-specific freshness threshold
                if use_per_collection_freshness:
                    collection_max_age = get_freshness_threshold(collection)
                else:
                    collection_max_age = max_age_hours

                # Build filter for telemetry insights
                # IMP-MEM-015: project_id is now required - always include in filter
                search_filter = {
                    "task_type": "telemetry_insight",
                    "project_id": project_id,
                }

                results = safe_store_call(
                    f"retrieve_insights/{collection}",
                    lambda col=collection, flt=search_filter: store.search(
                        collection=col,
                        query_vector=query_vector,
                        filter=flt,
                        limit=per_collection_limit,
                    ),
                    [],
                )

                for result in results:
                    payload = getattr(result, "payload", {}) or {}
                    # Only include telemetry insights
                    if payload.get("task_type") != "telemetry_insight":
                        continue

                    # IMP-LOOP-003/IMP-LOOP-014/IMP-MEM-004: Apply freshness check
                    # Uses per-collection threshold when max_age_hours is not specified
                    timestamp = payload.get("timestamp")
                    if not is_fresh(timestamp, collection_max_age):
                        stale_count += 1
                        logger.debug(
                            "[IMP-MEM-004] Skipping stale insight (age > %sh for %s): "
                            "id=%s, timestamp=%s",
                            collection_max_age,
                            collection,
                            getattr(result, "id", "unknown"),
                            timestamp,
                        )
                        continue

                    # IMP-LOOP-016: Extract confidence from payload, default to 1.0
                    confidence = payload.get("confidence", 1.0)
                    insight = {
                        "id": getattr(result, "id", None),
                        "content": payload.get("content", payload.get("summary", "")),
                        "metadata": payload,
                        "score": getattr(result, "score", 0.0),
                        "issue_type": payload.get("issue_type", "unknown"),
                        "severity": payload.get("severity", "medium"),
                        "file_path": payload.get("file_path"),
                        "collection": collection,
                        "timestamp": timestamp,  # IMP-LOOP-003: Include timestamp in result
                        "freshness_threshold": collection_max_age,  # IMP-MEM-004: Include threshold
                        "confidence": confidence,  # IMP-LOOP-016: Include confidence for filtering
                    }
                    all_insights.append(insight)

            # Sort by score and limit
            all_insights.sort(key=lambda x: x.get("score", 0), reverse=True)
            insights = all_insights[:limit]

            # IMP-LOOP-003/IMP-MEM-004: Log freshness filtering stats
            if stale_count > 0:
                logger.info(
                    "[IMP-MEM-004] Filtered %d stale insights using per-collection thresholds",
                    stale_count,
                )

            # IMP-LOOP-034: Apply confidence decay based on age
            # This must happen before confidence filtering to use decayed values
            if self._confidence_manager is not None:
                insights = self.apply_confidence_decay(insights)
                logger.debug(
                    "[IMP-LOOP-034] Applied confidence decay to %d insights",
                    len(insights),
                )

            # IMP-LOOP-016: Apply confidence filtering if threshold is specified
            # Uses decayed confidence values after IMP-LOOP-034 decay application
            if min_confidence is not None:
                pre_filter_count = len(insights)
                insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]
                filtered_count = pre_filter_count - len(insights)
                if filtered_count > 0:
                    logger.info(
                        "[IMP-LOOP-016] Filtered %d low-confidence insights (threshold: %.2f)",
                        filtered_count,
                        min_confidence,
                    )

            logger.debug(
                f"[MemoryService] Retrieved {len(insights)} fresh insights for query: {query[:50]}..."
            )
            return insights

        except Exception as e:
            logger.warning(f"[MemoryService] Failed to retrieve insights: {e}")
            return []

    def update_insight_confidence(
        self,
        insight_id: str,
        confidence: float,
        enabled: bool,
        store: Any,
        safe_store_call: Callable[[str, Callable, Any], Any],
        collection_run_summaries: str,
        collection_errors_ci: str,
        collection_doctor_hints: str,
        project_id: Optional[str] = None,
    ) -> bool:
        """Update the confidence score for a stored insight.

        IMP-LOOP-031: This method is called by the InsightCorrelationEngine to
        persist updated confidence scores back to stored insights. When tasks
        generated from an insight succeed or fail, the confidence is adjusted
        and persisted here to influence future task generation.

        The method searches across all insight collections to find and update
        the insight with the given ID.

        Args:
            insight_id: The unique identifier of the insight to update.
            confidence: New confidence score (0.0-1.0). Will be clamped to
                       valid range.
            enabled: Whether memory is enabled.
            store: The vector store instance.
            safe_store_call: Function for safe store operations.
            collection_run_summaries: Name of run summaries collection.
            collection_errors_ci: Name of errors/CI collection.
            collection_doctor_hints: Name of doctor hints collection.
            project_id: Optional project ID for namespace filtering.

        Returns:
            True if the insight was found and updated, False otherwise.
        """
        if not enabled:
            logger.debug(
                "[IMP-LOOP-031] Memory disabled, skipping confidence update for %s",
                insight_id,
            )
            return False

        # Clamp confidence to valid range
        confidence = max(0.0, min(1.0, confidence))

        # Collections where insights may be stored
        insight_collections = [
            collection_run_summaries,
            collection_errors_ci,
            collection_doctor_hints,
        ]

        for collection in insight_collections:
            try:
                # Try to get the payload for this insight
                payload = safe_store_call(
                    f"update_insight_confidence/{collection}/get_payload",
                    lambda col=collection: store.get_payload(col, insight_id),
                    None,
                )

                if payload is None:
                    continue

                # Verify this is a telemetry insight
                if payload.get("task_type") != "telemetry_insight":
                    continue

                # Verify project ID if specified
                if project_id and payload.get("project_id") != project_id:
                    continue

                # Record previous confidence for logging
                old_confidence = payload.get("confidence", 1.0)

                # Update the confidence in the payload
                payload["confidence"] = confidence
                payload["confidence_updated_at"] = datetime.now(timezone.utc).isoformat()

                # Persist the update
                success = safe_store_call(
                    f"update_insight_confidence/{collection}/update_payload",
                    lambda col=collection, pid=insight_id, pl=payload: store.update_payload(
                        col, pid, pl
                    ),
                    False,
                )

                if success:
                    logger.info(
                        "[IMP-LOOP-031] Updated insight confidence: id=%s, "
                        "collection=%s, confidence=%.2f -> %.2f",
                        insight_id,
                        collection,
                        old_confidence,
                        confidence,
                    )
                    return True
                else:
                    logger.warning(
                        "[IMP-LOOP-031] Failed to persist confidence update for %s in %s",
                        insight_id,
                        collection,
                    )

            except Exception as e:
                logger.warning(
                    "[IMP-LOOP-031] Error updating confidence for %s in %s: %s",
                    insight_id,
                    collection,
                    e,
                )

        logger.debug(
            "[IMP-LOOP-031] Insight %s not found in any collection, confidence not updated",
            insight_id,
        )
        return False

    def get_high_occurrence_insights(
        self,
        project_id: str,
        enabled: bool,
        store: Any,
        safe_store_call: Callable[[str, Callable, Any], Any],
        validate_project_id: Callable[[str, str], None],
        collection_run_summaries: str,
        collection_errors_ci: str,
        collection_doctor_hints: str,
        min_occurrences: int = 3,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get insights that have occurred multiple times.

        IMP-LOOP-032: This method supports the MemoryTaskPromoter by querying
        for insights with high occurrence counts, indicating recurring patterns
        that should be automatically promoted to tasks.

        Args:
            project_id: Project ID for namespace isolation (required).
            enabled: Whether memory is enabled.
            store: The vector store instance.
            safe_store_call: Function for safe store operations.
            validate_project_id: Function to validate project namespace.
            collection_run_summaries: Name of run summaries collection.
            collection_errors_ci: Name of errors/CI collection.
            collection_doctor_hints: Name of doctor hints collection.
            min_occurrences: Minimum occurrence count for inclusion.
            min_confidence: Minimum confidence score for inclusion.
            limit: Maximum number of insights to return.

        Returns:
            List of insight dictionaries with occurrence_count field,
            sorted by occurrence count descending.

        Raises:
            ProjectNamespaceError: If project_id is empty or None.
        """
        if not enabled:
            logger.debug("[IMP-LOOP-032] Memory disabled, returning empty high-occurrence insights")
            return []

        # IMP-MEM-015: Validate project namespace isolation
        validate_project_id(project_id, "get_high_occurrence_insights")

        logger.debug(
            "[IMP-LOOP-032] Querying for high-occurrence insights "
            "(min_occurrences=%d, min_confidence=%.2f, limit=%d)",
            min_occurrences,
            min_confidence,
            limit,
        )

        try:
            # Query using a broad search vector for failure patterns
            query = "failure error recurring pattern problem issue retry"
            query_vector = sync_embed_text(query)

            # Collections where insights may be stored
            insight_collections = [
                collection_run_summaries,
                collection_errors_ci,
                collection_doctor_hints,
            ]

            high_occurrence_insights: List[Dict[str, Any]] = []

            for collection in insight_collections:
                # Build filter for telemetry insights
                search_filter = {
                    "task_type": "telemetry_insight",
                    "project_id": project_id,
                }

                results = safe_store_call(
                    f"get_high_occurrence_insights/{collection}",
                    lambda col=collection, flt=search_filter: store.search(
                        collection=col,
                        query_vector=query_vector,
                        filter=flt,
                        limit=limit * 2,  # Fetch extra for filtering
                    ),
                    [],
                )

                for result in results:
                    payload = getattr(result, "payload", {}) or {}

                    # Only include telemetry insights
                    if payload.get("task_type") != "telemetry_insight":
                        continue

                    # Check occurrence count
                    occurrence_count = payload.get("occurrence_count", 1)
                    if occurrence_count < min_occurrences:
                        continue

                    # Check confidence
                    conf = payload.get("confidence", 1.0)
                    if conf < min_confidence:
                        continue

                    insight = {
                        "id": getattr(result, "id", None),
                        "content": payload.get("content", payload.get("summary", "")),
                        "payload": payload,
                        "score": getattr(result, "score", 0.0),
                        "issue_type": payload.get("issue_type", "unknown"),
                        "severity": payload.get("severity", "medium"),
                        "occurrence_count": occurrence_count,
                        "confidence": conf,
                        "last_occurrence": payload.get("last_occurrence"),
                        "collection": collection,
                    }
                    high_occurrence_insights.append(insight)

            # Sort by occurrence count descending
            high_occurrence_insights.sort(key=lambda x: x.get("occurrence_count", 0), reverse=True)

            # Apply limit
            insights = high_occurrence_insights[:limit]

            logger.info(
                "[IMP-LOOP-032] Found %d high-occurrence insights (min_occurrences=%d, project=%s)",
                len(insights),
                min_occurrences,
                project_id,
            )

            return insights

        except Exception as e:
            logger.warning("[IMP-LOOP-032] Failed to get high-occurrence insights: %s", e)
            return []
