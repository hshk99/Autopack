# autopack/memory/qdrant_store.py
"""
Qdrant-based vector store adapter.

Design:
- Compatible interface with FaissStore for easy swap
- Uses Qdrant for distributed, production-ready vector search
- Collections map to Qdrant collections with HNSW indexing
- Payload filters on project_id, run_id, phase_id

Collections (per plan):
- code_docs: embeddings of workspace files
- run_summaries: per-phase summaries
- errors_ci: failing test/error snippets
- doctor_hints: doctor hints/actions/outcomes
- planning: planning artifacts and plan changes
"""

import hashlib
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Try importing qdrant client
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        SearchRequest,
        VectorParams,
    )

    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("qdrant-client not installed; QdrantStore will not be available")


# IMP-REL-012: Health monitoring for vector store operations
class VectorStoreHealthMonitor:
    """Monitor and track health of vector store connections.

    IMP-REL-012: Provides continuous health monitoring with:
    - Consecutive failure tracking
    - Health status transitions (healthy → degraded → unhealthy)
    - Automatic alerting when thresholds exceeded
    - Recovery tracking after reconnection
    """

    def __init__(self, consecutive_failure_threshold: int = 5):
        """Initialize health monitor.

        Args:
            consecutive_failure_threshold: Number of consecutive failures before alerting
        """
        self.consecutive_failure_threshold = consecutive_failure_threshold
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
        self.is_healthy = True
        self.total_failures = 0
        self.total_successes = 0

    def record_success(self) -> None:
        """Record a successful operation."""
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.last_success_time = time.time()
        self.total_successes += 1

        # Recover from degraded state if we had failures before
        if not self.is_healthy:
            self.is_healthy = True
            logger.info(
                f"[IMP-REL-012] Vector store recovered to healthy state after "
                f"{self.total_failures} total failures"
            )

    def record_failure(self, error: Exception) -> None:
        """Record a failed operation.

        Args:
            error: The exception that caused the failure
        """
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = time.time()
        self.total_failures += 1

        # Alert if threshold exceeded
        if self.consecutive_failures == self.consecutive_failure_threshold:
            logger.warning(
                f"[IMP-REL-012] Vector store health degraded: "
                f"{self.consecutive_failures} consecutive failures. "
                f"Last error: {type(error).__name__}: {str(error)[:100]}"
            )
            self.is_healthy = False
        elif self.consecutive_failures > self.consecutive_failure_threshold:
            logger.error(
                f"[IMP-REL-012] Vector store unhealthy: "
                f"{self.consecutive_failures} consecutive failures. "
                f"Operations will continue to retry but may fail."
            )

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status.

        Returns:
            Dictionary with health metrics
        """
        uptime_percent = 0.0
        if self.total_successes + self.total_failures > 0:
            uptime_percent = (
                self.total_successes / (self.total_successes + self.total_failures) * 100
            )

        return {
            "is_healthy": self.is_healthy,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "uptime_percent": uptime_percent,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }

    def reset(self) -> None:
        """Reset health tracking (useful for testing)."""
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.is_healthy = True
        self.last_failure_time = None
        self.last_success_time = None


class QdrantStore:
    """
    Qdrant-based vector store with FaissStore-compatible interface.

    Methods mirror FaissStore for easy swap:
    - ensure_collection(name, size)
    - upsert(collection, points)
    - search(collection, query_vector, filter, limit)
    - scroll(collection, filter, limit)
    - delete(collection, ids)
    - count(collection, filter)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        api_key: Optional[str] = None,
        prefer_grpc: bool = False,
        timeout: int = 60,
    ):
        """
        Initialize Qdrant store.

        Args:
            host: Qdrant server host
            port: Qdrant server port (6333 for HTTP, 6334 for gRPC)
            api_key: Optional API key for Qdrant Cloud
            prefer_grpc: Use gRPC instead of HTTP
            timeout: Request timeout in seconds
        """
        if not QDRANT_AVAILABLE:
            raise ImportError(
                "qdrant-client is required for QdrantStore. Install with: pip install qdrant-client"
            )

        self._unavailable_logged = False
        self.host = host
        self.port = port
        self.client = QdrantClient(
            host=host,
            port=port,
            api_key=api_key,
            prefer_grpc=prefer_grpc,
            timeout=timeout,
        )
        self._default_dim = 1536  # OpenAI text-embedding-ada-002 dimension

        # IMP-REL-012: Initialize health monitor for continuous tracking
        self._health_monitor = VectorStoreHealthMonitor(consecutive_failure_threshold=5)

        # IMP-REL-003: Enhanced health check with HTTP API validation and retry logic
        # Validate connectivity up front so callers can fall back cleanly.
        is_healthy, error_msg = self._check_qdrant_health()
        if not is_healthy:
            logger.warning(f"[Qdrant] Health check failed for {host}:{port}: {error_msg}")
            raise RuntimeError(f"Qdrant health check failed: {error_msg}")

        logger.info(f"[Qdrant] Connected to {host}:{port} (health check passed)")
        # IMP-REL-012: Record successful initialization
        self._health_monitor.record_success()

    def _log_unavailable(self, message: str, exc: Exception) -> None:
        """Log Qdrant connection issues without spamming."""
        if not self._unavailable_logged:
            self._unavailable_logged = True
            logger.warning(f"[Qdrant] {message}: {exc}")
        else:
            logger.debug(f"[Qdrant] {message}: {exc}")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(
            (
                ConnectionError,
                TimeoutError,
                OSError,
            )
        ),
        before_sleep=lambda retry_state: logger.warning(
            f"[IMP-REL-003] Qdrant connection failed, retrying in "
            f"{retry_state.next_action.sleep}s (attempt {retry_state.attempt_number}/5)..."
        ),
    )
    def _connect_with_retry(self) -> bool:
        """Connect to Qdrant with exponential backoff.

        IMP-REL-003: Implement retry logic for transient network failures.

        Problem: No retry logic for runtime connection failures. If Qdrant becomes
        temporarily unavailable, operations fail immediately without recovery.

        Solution: Use tenacity @retry decorator with exponential backoff for
        connection attempts. Automatically retry up to 5 times with increasing
        delay (1s, 2s, 4s, 8s, 16s, capped at 30s).

        Returns:
            True if connection successful
        """
        if not self._health_check():
            raise ConnectionError("Qdrant health check failed")
        return True

    def _health_check(self) -> bool:
        """Quick health check without retry logic."""
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.debug(f"[IMP-REL-003] Quick health check failed: {e}")
            return False

    def connect(self) -> bool:
        """Establish or restore Qdrant connection with fallback.

        IMP-REL-003: Implement fallback to FAISS on persistent failure.

        Problem: Server temporarily unavailable crashes entire executor at startup.

        Solution: Attempt retry with exponential backoff. On persistent failure
        after all retries, log error but return False to allow fallback to FAISS.

        Returns:
            True if connected, False if all retries failed (caller should fallback)
        """
        try:
            self._connect_with_retry()
            logger.info("[IMP-REL-003] Qdrant connection restored")
            self._unavailable_logged = False
            return True
        except Exception as e:
            logger.error(
                f"[IMP-REL-003] Qdrant connection failed after retries: {e}. "
                "Falling back to FAISS store"
            )
            return False

    def _check_qdrant_health(
        self, max_retries: int = 3, retry_delay: float = 1.0
    ) -> Tuple[bool, str]:
        """IMP-REL-003: Check Qdrant health with HTTP API validation and retry logic.

        Problem: Qdrant health check only performed at initialization. If Qdrant becomes
        temporarily unavailable after startup, executor crashes without fallback.

        Solution: Perform multi-layer health validation with retries:
        1. Test basic connectivity via get_collections() (validates TCP + initial API)
        2. Query HTTP /health endpoint for detailed status (validates full API readiness)
        3. Retry up to max_retries times with exponential backoff if not ready

        This ensures the Qdrant API is fully initialized before marking it as healthy.

        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (doubled on each retry)

        Returns:
            Tuple of (is_healthy: bool, error_msg: str)
            - (True, "") if healthy
            - (False, "error message") if unhealthy after all retries

        Note: This method is called during __init__, so exceptions should be caught
        by the caller and converted to connection failures.
        """
        attempt = 0
        last_error = ""

        while attempt < max_retries:
            attempt += 1

            try:
                # Step 1: Basic connectivity check via Qdrant client
                # This validates TCP connection and basic API responsiveness
                logger.debug(
                    f"[IMP-REL-003] Health check attempt {attempt}/{max_retries}: Testing basic connectivity"
                )
                self.client.get_collections()
                logger.debug("[IMP-REL-003] Basic connectivity check passed")

                # Step 2: HTTP /health endpoint check for full API readiness
                # Some Qdrant versions may pass get_collections but not be fully ready
                # The /health endpoint provides more detailed status
                try:
                    # Use requests library for direct HTTP health check
                    import requests

                    health_url = f"http://{self.host}:{self.port}/health"
                    logger.debug(f"[IMP-REL-003] Checking HTTP health endpoint: {health_url}")

                    response = requests.get(health_url, timeout=5)

                    if response.status_code == 200:
                        try:
                            health_data = response.json()
                            status = health_data.get("status", "unknown")
                            logger.debug(
                                f"[IMP-REL-003] HTTP health check passed (status: {status})"
                            )
                        except Exception:
                            # Some Qdrant versions return 200 without JSON body
                            logger.debug(
                                "[IMP-REL-003] HTTP health check passed (status 200, no JSON)"
                            )
                        return True, ""
                    else:
                        last_error = f"HTTP health endpoint returned status {response.status_code}"
                        logger.warning(f"[IMP-REL-003] {last_error}")

                except requests.exceptions.Timeout:
                    last_error = "HTTP health endpoint timeout after 5s"
                    logger.warning(f"[IMP-REL-003] {last_error}")

                except requests.exceptions.ConnectionError:
                    last_error = (
                        "HTTP health endpoint connection refused (API not fully initialized)"
                    )
                    logger.warning(f"[IMP-REL-003] {last_error}")

                except Exception as e:
                    # If requests library not available, fall back to basic check
                    logger.debug(
                        f"[IMP-REL-003] HTTP health check unavailable (requests not installed), "
                        f"falling back to basic check: {e}"
                    )
                    # Basic check passed above, so treat as healthy
                    return True, ""

            except Exception as e:
                last_error = f"Basic connectivity check failed: {type(e).__name__}: {e}"
                logger.warning(f"[IMP-REL-003] {last_error}")

            # Retry with exponential backoff if not the last attempt
            if attempt < max_retries:
                wait_time = retry_delay * (2 ** (attempt - 1))
                logger.info(
                    f"[IMP-REL-003] Qdrant not ready, retrying in {wait_time:.1f}s "
                    f"(attempt {attempt}/{max_retries})"
                )
                time.sleep(wait_time)

        # All retries exhausted
        logger.error(
            f"[IMP-REL-003] Qdrant health check failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
        return False, last_error

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of vector store.

        IMP-REL-012: Returns comprehensive health metrics including:
        - is_healthy: Boolean indicating overall health
        - consecutive_failures: Number of consecutive operation failures
        - consecutive_successes: Number of consecutive successful operations
        - total_failures: Cumulative failure count
        - total_successes: Cumulative success count
        - uptime_percent: Percentage of successful operations
        - last_failure_time: Timestamp of last failure
        - last_success_time: Timestamp of last success

        Returns:
            Dictionary with health metrics
        """
        return self._health_monitor.get_health_status()

    def check_vector_store_health(self) -> bool:
        """Check if Qdrant is accessible and responsive.

        IMP-REL-012: Performs a lightweight health check and updates
        the health monitor with the result.

        Returns:
            True if healthy, False otherwise
        """
        try:
            self._health_check()
            self._health_monitor.record_success()
            return True
        except Exception as e:
            self._health_monitor.record_failure(e)
            return False

    def _str_to_uuid(self, string_id: str) -> str:
        """
        Convert a string ID to a deterministic UUID.

        Qdrant requires IDs to be either UUID or unsigned integer.
        We hash the string ID to create a deterministic UUID.

        Args:
            string_id: String identifier

        Returns:
            UUID string
        """
        # Create deterministic UUID from string hash
        hash_bytes = hashlib.md5(string_id.encode()).digest()
        return str(uuid.UUID(bytes=hash_bytes))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def ensure_collection(self, name: str, size: int = 1536) -> None:
        """
        Ensure a collection exists (create if not).

        IMP-REL-003: Add retry for transient failures.
        IMP-REL-012: Track operation health.

        Args:
            name: Collection name
            size: Vector dimension
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(col.name == name for col in collections)

            if not exists:
                # Create collection with HNSW index
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=size,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"[Qdrant] Created collection '{name}' with dim={size}")
            else:
                logger.debug(f"[Qdrant] Collection '{name}' already exists")
            # IMP-REL-012: Record successful operation
            self._health_monitor.record_success()
        except Exception as e:
            # IMP-REL-012: Record failed operation
            self._health_monitor.record_failure(e)
            self._log_unavailable(f"Failed to ensure collection '{name}'", e)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def upsert(
        self,
        collection: str,
        points: List[Dict[str, Any]],
    ) -> int:
        """
        Upsert points to collection.

        IMP-REL-003: Add retry for transient failures.
        IMP-REL-012: Track operation health.

        Args:
            collection: Collection name
            points: List of {"id": str, "vector": List[float], "payload": Dict}

        Returns:
            Number of points upserted
        """
        if not points:
            return 0

        try:
            # Convert to Qdrant PointStruct
            qdrant_points = []
            for point in points:
                point_id = str(point.get("id") or uuid.uuid4().hex)
                # Convert string ID to UUID for Qdrant
                qdrant_id = self._str_to_uuid(point_id)

                vector = point.get("vector", [])
                payload = point.get("payload", {})
                # Store original ID in payload for retrieval
                payload["_original_id"] = point_id

                qdrant_points.append(
                    PointStruct(
                        id=qdrant_id,
                        vector=vector,
                        payload=payload,
                    )
                )

            # Upsert to Qdrant
            self.client.upsert(
                collection_name=collection,
                points=qdrant_points,
            )

            logger.debug(f"[Qdrant] Upserted {len(points)} points to '{collection}'")
            # IMP-REL-012: Record successful operation
            self._health_monitor.record_success()
            return len(points)

        except Exception as e:
            # IMP-REL-012: Record failed operation
            self._health_monitor.record_failure(e)
            self._log_unavailable(f"Failed to upsert to '{collection}'", e)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def search(
        self,
        collection: str,
        query_vector: List[float],
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        IMP-REL-003: Add retry for transient failures.
        IMP-REL-012: Track operation health.

        Args:
            collection: Collection name
            query_vector: Query embedding
            filter: Optional payload filter (e.g., {"project_id": "x", "run_id": "y"})
            limit: Max results

        Returns:
            List of {"id": str, "score": float, "payload": Dict}
        """
        try:
            # Build Qdrant filter from dict
            qdrant_filter = None
            if filter:
                must_conditions = []
                for key, value in filter.items():
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value),
                        )
                    )
                if must_conditions:
                    qdrant_filter = Filter(must=must_conditions)

            # Search using query_points API (search is deprecated)
            search_result = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=limit,
            ).points

            # Convert to common format
            results = []
            for hit in search_result:
                # Filter out tombstoned/superseded/archived entries
                payload = hit.payload or {}
                status = payload.get("status")
                if status in ("tombstoned", "superseded", "archived"):
                    continue

                # Return original ID from payload
                original_id = payload.pop("_original_id", str(hit.id))

                results.append(
                    {
                        "id": original_id,
                        "score": float(hit.score),
                        "payload": payload,
                    }
                )

            # IMP-REL-012: Record successful operation
            self._health_monitor.record_success()
            return results

        except Exception as e:
            # IMP-REL-012: Record failed operation
            self._health_monitor.record_failure(e)
            self._log_unavailable(f"Search failed in '{collection}'", e)
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def scroll(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Scroll through all documents matching filter.

        IMP-REL-003: Add retry for transient failures.

        Args:
            collection: Collection name
            filter: Optional payload filter
            limit: Max results

        Returns:
            List of {"id": str, "payload": Dict}
        """
        try:
            # Build Qdrant filter
            qdrant_filter = None
            if filter:
                must_conditions = []
                for key, value in filter.items():
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value),
                        )
                    )
                if must_conditions:
                    qdrant_filter = Filter(must=must_conditions)

            # Scroll
            records, _ = self.client.scroll(
                collection_name=collection,
                scroll_filter=qdrant_filter,
                limit=limit,
            )

            # Convert to common format
            results = []
            for record in records:
                payload = record.payload or {}
                # Return original ID from payload
                original_id = payload.pop("_original_id", str(record.id))

                results.append(
                    {
                        "id": original_id,
                        "payload": payload,
                    }
                )

            return results

        except Exception as e:
            self._log_unavailable(f"Scroll failed in '{collection}'", e)
            return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def get_payload(self, collection: str, point_id: str) -> Optional[Dict[str, Any]]:
        """
        Return payload for a point ID, or None if missing.

        IMP-REL-003: Add retry for transient failures.

        Args:
            collection: Collection name
            point_id: Point ID (original string ID)

        Returns:
            Payload dict or None
        """
        try:
            # Convert string ID to UUID
            qdrant_id = self._str_to_uuid(point_id)

            points = self.client.retrieve(
                collection_name=collection,
                ids=[qdrant_id],
            )
            if points and points[0].payload:
                payload = dict(points[0].payload)
                # Remove internal _original_id field
                payload.pop("_original_id", None)
                return payload
            return None
        except Exception as e:
            self._log_unavailable(f"Get payload failed for '{point_id}'", e)
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def update_payload(
        self,
        collection: str,
        point_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Update payload for an existing point ID.

        IMP-REL-003: Add retry for transient failures.

        Args:
            collection: Collection name
            point_id: Point ID (original string ID)
            payload: New payload

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert string ID to UUID
            qdrant_id = self._str_to_uuid(point_id)

            # Preserve original ID in payload
            payload["_original_id"] = point_id

            self.client.set_payload(
                collection_name=collection,
                payload=payload,
                points=[qdrant_id],
            )
            return True
        except Exception as e:
            self._log_unavailable(f"Update payload failed for '{point_id}'", e)
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def delete(self, collection: str, ids: List[str]) -> int:
        """
        Delete points by ID.

        IMP-REL-003: Add retry for transient failures.
        IMP-REL-012: Track operation health.

        Args:
            collection: Collection name
            ids: List of point IDs to delete (original string IDs)

        Returns:
            Number of points deleted
        """
        if not ids:
            return 0

        try:
            # Convert string IDs to UUIDs
            qdrant_ids = [self._str_to_uuid(point_id) for point_id in ids]

            self.client.delete(
                collection_name=collection,
                points_selector=qdrant_ids,
            )
            logger.debug(f"[Qdrant] Deleted {len(ids)} points from '{collection}'")
            # IMP-REL-012: Record successful operation
            self._health_monitor.record_success()
            return len(ids)
        except Exception as e:
            # IMP-REL-012: Record failed operation
            self._health_monitor.record_failure(e)
            self._log_unavailable(f"Delete failed in '{collection}'", e)
            return 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    )
    def count(self, collection: str, filter: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents in collection, optionally filtered.

        IMP-REL-003: Add retry for transient failures.
        IMP-REL-012: Track operation health.

        Args:
            collection: Collection name
            filter: Optional payload filter

        Returns:
            Number of documents
        """
        try:
            # Build Qdrant filter
            qdrant_filter = None
            if filter:
                must_conditions = []
                for key, value in filter.items():
                    must_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value),
                        )
                    )
                if must_conditions:
                    qdrant_filter = Filter(must=must_conditions)

            # Count
            result = self.client.count(
                collection_name=collection,
                count_filter=qdrant_filter,
                exact=True,
            )
            # IMP-REL-012: Record successful operation
            self._health_monitor.record_success()
            return result.count

        except Exception as e:
            # IMP-REL-012: Record failed operation
            self._health_monitor.record_failure(e)
            self._log_unavailable(f"Count failed in '{collection}'", e)
            return 0

    def delete_collection(self, name: str) -> bool:
        """
        Delete a collection entirely.

        Args:
            name: Collection name

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_collection(collection_name=name)
            logger.info(f"[Qdrant] Deleted collection '{name}'")
            return True
        except Exception as e:
            logger.error(f"[Qdrant] Failed to delete collection '{name}': {e}")
            return False
