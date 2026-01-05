# autopack/memory/faiss_store.py
"""
FAISS-based vector store with Qdrant-ready adapter interface.

Design:
- Thin adapter shape so Qdrant can be swapped later
- FAISS index stored on disk (no external infra)
- Collections map to separate index files
- Payload stored in companion JSON sidecar

Collections (per plan):
- code_docs: embeddings of workspace files
- run_summaries: per-phase summaries
- errors_ci: failing test/error snippets
- doctor_hints: doctor hints/actions/outcomes
"""

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Try importing faiss (optional dependency)
try:
    import faiss
    import numpy as np

    FAISS_AVAILABLE = True
except ImportError:
    faiss = None  # type: ignore
    np = None  # type: ignore
    FAISS_AVAILABLE = False
    logger.warning("faiss library not installed; FaissStore will use in-memory fallback")


class FaissStore:
    """
    FAISS-based vector store with Qdrant-compatible interface.

    Keeps the same method signatures as Qdrant utils for easy swap:
    - ensure_collection(name, size)
    - upsert(collection, points)
    - search(collection, query_vector, filter, limit)
    - scroll(collection, filter, limit)
    - delete(collection, ids)
    """

    def __init__(self, index_dir: str = ".autonomous_runs/file-organizer-app-v1/.faiss"):
        """
        Initialize FAISS store.

        Args:
            index_dir: Directory to store index files
        """
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # In-memory caches: {collection_name: {"index": faiss.Index, "payloads": {id: payload}}}
        self._collections: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

        # Default dimension
        self._default_dim = 1536

    def _index_path(self, name: str) -> Path:
        return self.index_dir / f"{name}.index"

    def _payload_path(self, name: str) -> Path:
        return self.index_dir / f"{name}.payloads.json"

    def _id_map_path(self, name: str) -> Path:
        return self.index_dir / f"{name}.idmap.json"

    def ensure_collection(self, name: str, size: int = 1536) -> None:
        """
        Ensure a collection exists (create if not).

        Args:
            name: Collection name
            size: Vector dimension
        """
        with self._lock:
            if name in self._collections:
                return

            index_path = self._index_path(name)
            payload_path = self._payload_path(name)
            id_map_path = self._id_map_path(name)

            if FAISS_AVAILABLE and index_path.exists():
                # Load existing index
                try:
                    index = faiss.read_index(str(index_path))
                    with open(payload_path, "r", encoding="utf-8") as f:
                        payloads = json.load(f)
                    with open(id_map_path, "r", encoding="utf-8") as f:
                        id_map = json.load(f)
                    self._collections[name] = {
                        "index": index,
                        "payloads": payloads,
                        "id_map": id_map,  # {str_id: faiss_idx}
                        "dim": size,
                    }
                    logger.info(f"[FAISS] Loaded collection '{name}' with {index.ntotal} vectors")
                    return
                except Exception as e:
                    logger.warning(f"[FAISS] Failed to load index '{name}': {e}, creating new")

            # Create new collection
            if FAISS_AVAILABLE:
                index = faiss.IndexFlatIP(size)  # Inner product (cosine after normalization)
            else:
                index = None  # Fallback to in-memory list
            self._collections[name] = {
                "index": index,
                "payloads": {},
                "id_map": {},
                "dim": size,
                "vectors": [] if not FAISS_AVAILABLE else None,  # Fallback storage
            }
            logger.info(f"[FAISS] Created collection '{name}' with dim={size}")

    def _save_collection(self, name: str) -> None:
        """Persist collection to disk."""
        if name not in self._collections:
            return
        col = self._collections[name]
        try:
            if FAISS_AVAILABLE and col["index"] is not None:
                faiss.write_index(col["index"], str(self._index_path(name)))
            with open(self._payload_path(name), "w", encoding="utf-8") as f:
                json.dump(col["payloads"], f)
            with open(self._id_map_path(name), "w", encoding="utf-8") as f:
                json.dump(col["id_map"], f)
        except Exception as e:
            logger.error(f"[FAISS] Failed to save collection '{name}': {e}")

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
        self.ensure_collection(collection)

        with self._lock:
            col = self._collections[collection]
            count = 0

            for point in points:
                point_id = str(point.get("id") or uuid.uuid4().hex)
                vector = point.get("vector", [])
                payload = point.get("payload", {})

                # Normalize vector for cosine similarity
                if FAISS_AVAILABLE:
                    vec_np = np.array(vector, dtype=np.float32).reshape(1, -1)
                    faiss.normalize_L2(vec_np)

                    # If point exists, we can't update in place with IndexFlatIP
                    # For simplicity, we just add (duplicates handled by ID dedup at search time)
                    # A production system would use IndexIDMap
                    col["index"].add(vec_np)
                    faiss_idx = col["index"].ntotal - 1
                    col["id_map"][point_id] = faiss_idx
                else:
                    # Fallback: store in list
                    col["vectors"].append({"id": point_id, "vector": vector})
                    col["id_map"][point_id] = len(col["vectors"]) - 1

                col["payloads"][point_id] = payload
                count += 1

            self._save_collection(collection)
            return count

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
        self.ensure_collection(collection)

        with self._lock:
            col = self._collections[collection]

            if FAISS_AVAILABLE and col["index"] is not None:
                if col["index"].ntotal == 0:
                    return []

                # Normalize query
                query_np = np.array(query_vector, dtype=np.float32).reshape(1, -1)
                faiss.normalize_L2(query_np)

                # Search more than limit to allow for filtering
                k = min(limit * 3, col["index"].ntotal)
                scores, indices = col["index"].search(query_np, k)

                # Reverse map faiss_idx -> point_id
                idx_to_id = {v: k for k, v in col["id_map"].items()}

                results = []
                for i, (score, faiss_idx) in enumerate(zip(scores[0], indices[0])):
                    if faiss_idx < 0:
                        continue
                    point_id = idx_to_id.get(faiss_idx)
                    if not point_id:
                        continue
                    payload = col["payloads"].get(point_id, {})

                    status = payload.get("status")
                    if status in ("tombstoned", "superseded", "archived"):
                        continue

                    # Apply filter
                    if filter and not self._matches_filter(payload, filter):
                        continue

                    results.append(
                        {
                            "id": point_id,
                            "score": float(score),
                            "payload": payload,
                        }
                    )
                    if len(results) >= limit:
                        break

                return results
            else:
                # Fallback: brute-force cosine similarity
                return self._fallback_search(col, query_vector, filter, limit)

    def _fallback_search(
        self,
        col: Dict,
        query_vector: List[float],
        filter: Optional[Dict],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Brute-force search without FAISS."""
        if not col.get("vectors"):
            return []

        def cosine_sim(a: List[float], b: List[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        scored = []
        for item in col["vectors"]:
            point_id = item["id"]
            vector = item["vector"]
            payload = col["payloads"].get(point_id, {})

            status = payload.get("status")
            if status in ("tombstoned", "superseded", "archived"):
                continue

            if filter and not self._matches_filter(payload, filter):
                continue

            score = cosine_sim(query_vector, vector)
            scored.append({"id": point_id, "score": score, "payload": payload})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _matches_filter(self, payload: Dict, filter: Dict) -> bool:
        """Check if payload matches all filter conditions."""
        for key, value in filter.items():
            if payload.get(key) != value:
                return False
        return True

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
        self.ensure_collection(collection)

        with self._lock:
            col = self._collections[collection]
            results = []

            for point_id, payload in col["payloads"].items():
                if filter and not self._matches_filter(payload, filter):
                    continue
                results.append({"id": point_id, "payload": payload})
                if len(results) >= limit:
                    break

            return results

    def get_payload(self, collection: str, point_id: str) -> Optional[Dict[str, Any]]:
        """Return payload for a point ID, or None if missing."""
        self.ensure_collection(collection)
        with self._lock:
            col = self._collections[collection]
            return col["payloads"].get(point_id)

    def update_payload(self, collection: str, point_id: str, payload: Dict[str, Any]) -> bool:
        """Update payload for an existing point ID."""
        self.ensure_collection(collection)
        with self._lock:
            col = self._collections[collection]
            if point_id not in col["payloads"]:
                return False
            col["payloads"][point_id] = payload
            self._save_collection(collection)
            return True

    def delete(self, collection: str, ids: List[str]) -> int:
        """
        Delete points by ID.

        Note: With IndexFlatIP, we can't truly delete. We mark payloads as deleted
        and filter them out in search. A production system would rebuild the index.

        Args:
            collection: Collection name
            ids: List of point IDs to delete

        Returns:
            Number of points deleted
        """
        self.ensure_collection(collection)

        with self._lock:
            col = self._collections[collection]
            count = 0

            for point_id in ids:
                if point_id in col["payloads"]:
                    del col["payloads"][point_id]
                    if point_id in col["id_map"]:
                        del col["id_map"][point_id]
                    count += 1

            self._save_collection(collection)
            return count

    def count(self, collection: str, filter: Optional[Dict[str, Any]] = None) -> int:
        """Count documents in collection, optionally filtered."""
        self.ensure_collection(collection)

        with self._lock:
            col = self._collections[collection]
            if not filter:
                return len(col["payloads"])

            count = 0
            for payload in col["payloads"].values():
                if self._matches_filter(payload, filter):
                    count += 1
            return count
