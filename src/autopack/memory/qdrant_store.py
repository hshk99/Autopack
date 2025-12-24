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
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try importing qdrant client
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        SearchRequest,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    logger.warning("qdrant-client not installed; QdrantStore will not be available")


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
                "qdrant-client is required for QdrantStore. "
                "Install with: pip install qdrant-client"
            )

        self._unavailable_logged = False
        self.client = QdrantClient(
            host=host,
            port=port,
            api_key=api_key,
            prefer_grpc=prefer_grpc,
            timeout=timeout,
        )
        self._default_dim = 1536  # OpenAI text-embedding-ada-002 dimension
        # Validate connectivity up front so callers can fall back cleanly.
        try:
            self.client.get_collections()
        except Exception as e:
            logger.warning(f"[Qdrant] Connection check failed for {host}:{port}: {e}")
            raise

        logger.info(f"[Qdrant] Connected to {host}:{port}")

    def _log_unavailable(self, message: str, exc: Exception) -> None:
        """Log Qdrant connection issues without spamming."""
        if not self._unavailable_logged:
            self._unavailable_logged = True
            logger.warning(f"[Qdrant] {message}: {exc}")
        else:
            logger.debug(f"[Qdrant] {message}: {exc}")

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

    def ensure_collection(self, name: str, size: int = 1536) -> None:
        """
        Ensure a collection exists (create if not).

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
        except Exception as e:
            self._log_unavailable(f"Failed to ensure collection '{name}'", e)
            raise

    def upsert(
        self,
        collection: str,
        points: List[Dict[str, Any]],
    ) -> int:
        """
        Upsert points to collection.

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
            return len(points)

        except Exception as e:
            self._log_unavailable(f"Failed to upsert to '{collection}'", e)
            raise

    def search(
        self,
        collection: str,
        query_vector: List[float],
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

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

                results.append({
                    "id": original_id,
                    "score": float(hit.score),
                    "payload": payload,
                })

            return results

        except Exception as e:
            self._log_unavailable(f"Search failed in '{collection}'", e)
            return []

    def scroll(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Scroll through all documents matching filter.

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

                results.append({
                    "id": original_id,
                    "payload": payload,
                })

            return results

        except Exception as e:
            self._log_unavailable(f"Scroll failed in '{collection}'", e)
            return []

    def get_payload(self, collection: str, point_id: str) -> Optional[Dict[str, Any]]:
        """
        Return payload for a point ID, or None if missing.

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

    def update_payload(
        self,
        collection: str,
        point_id: str,
        payload: Dict[str, Any],
    ) -> bool:
        """
        Update payload for an existing point ID.

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

    def delete(self, collection: str, ids: List[str]) -> int:
        """
        Delete points by ID.

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
            return len(ids)
        except Exception as e:
            self._log_unavailable(f"Delete failed in '{collection}'", e)
            return 0

    def count(self, collection: str, filter: Optional[Dict[str, Any]] = None) -> int:
        """
        Count documents in collection, optionally filtered.

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
            return result.count

        except Exception as e:
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
