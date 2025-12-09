# tests/test_qdrant_store.py
"""
Tests for QdrantStore adapter.

These tests require Qdrant running locally:
    docker run -p 6333:6333 qdrant/qdrant

Tests will be skipped if Qdrant is not available.
"""

import os
import pytest
from typing import List

# Check if Qdrant should be tested
QDRANT_TEST_ENABLED = os.getenv("QDRANT_TEST_ENABLED", "false").lower() in ("true", "1", "yes")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

try:
    from autopack.memory import QdrantStore, QDRANT_AVAILABLE
    if QDRANT_AVAILABLE and QDRANT_TEST_ENABLED:
        # Try connecting to Qdrant
        test_client = QdrantStore(host=QDRANT_HOST, port=QDRANT_PORT)
        test_client.client.get_collections()  # Simple connection test
        QDRANT_TESTABLE = True
    else:
        QDRANT_TESTABLE = False
except Exception:
    QDRANT_TESTABLE = False


skip_if_no_qdrant = pytest.mark.skipif(
    not QDRANT_TESTABLE,
    reason="Qdrant not available or QDRANT_TEST_ENABLED not set. "
           "Set QDRANT_TEST_ENABLED=true and ensure Qdrant is running on localhost:6333"
)


@skip_if_no_qdrant
class TestQdrantStore:
    """Test suite for QdrantStore."""

    @pytest.fixture
    def store(self):
        """Create a QdrantStore instance for testing."""
        store = QdrantStore(host=QDRANT_HOST, port=QDRANT_PORT)
        yield store
        # Cleanup: delete test collections
        try:
            store.delete_collection("test_collection")
            store.delete_collection("test_search")
            store.delete_collection("test_filter")
        except Exception:
            pass

    def test_ensure_collection(self, store: QdrantStore):
        """Test collection creation."""
        collection_name = "test_collection"

        # Create collection
        store.ensure_collection(collection_name, size=128)

        # Verify collection exists
        collections = store.client.get_collections().collections
        assert any(col.name == collection_name for col in collections)

        # Ensure idempotency (calling again should not error)
        store.ensure_collection(collection_name, size=128)

    def test_upsert_and_search(self, store: QdrantStore):
        """Test upserting points and searching."""
        collection_name = "test_search"
        store.ensure_collection(collection_name, size=128)

        # Create test vectors (128-dim)
        points = [
            {
                "id": "point1",
                "vector": [0.1] * 128,
                "payload": {
                    "project_id": "test-project",
                    "type": "code",
                    "text": "Hello world",
                },
            },
            {
                "id": "point2",
                "vector": [0.2] * 128,
                "payload": {
                    "project_id": "test-project",
                    "type": "summary",
                    "text": "Goodbye world",
                },
            },
            {
                "id": "point3",
                "vector": [0.3] * 128,
                "payload": {
                    "project_id": "other-project",
                    "type": "code",
                    "text": "Different project",
                },
            },
        ]

        # Upsert points
        count = store.upsert(collection_name, points)
        assert count == 3

        # Search (should find point1 as closest to query [0.1, 0.1, ...])
        query_vector = [0.1] * 128
        results = store.search(collection_name, query_vector, limit=2)

        assert len(results) <= 2
        assert all("id" in r and "score" in r and "payload" in r for r in results)
        # First result should be point1 (exact match)
        assert results[0]["id"] == "point1"

    def test_search_with_filter(self, store: QdrantStore):
        """Test searching with payload filters."""
        collection_name = "test_filter"
        store.ensure_collection(collection_name, size=128)

        # Create test points
        points = [
            {
                "id": "point1",
                "vector": [0.1] * 128,
                "payload": {"project_id": "proj-a", "run_id": "run-1"},
            },
            {
                "id": "point2",
                "vector": [0.2] * 128,
                "payload": {"project_id": "proj-a", "run_id": "run-2"},
            },
            {
                "id": "point3",
                "vector": [0.3] * 128,
                "payload": {"project_id": "proj-b", "run_id": "run-1"},
            },
        ]
        store.upsert(collection_name, points)

        # Search with project_id filter
        query_vector = [0.15] * 128
        results = store.search(
            collection_name,
            query_vector,
            filter={"project_id": "proj-a"},
            limit=5,
        )

        # Should only return proj-a points
        assert len(results) == 2
        assert all(r["payload"]["project_id"] == "proj-a" for r in results)

        # Search with multiple filters
        results = store.search(
            collection_name,
            query_vector,
            filter={"project_id": "proj-a", "run_id": "run-1"},
            limit=5,
        )

        # Should only return point1
        assert len(results) == 1
        assert results[0]["id"] == "point1"

    def test_scroll(self, store: QdrantStore):
        """Test scrolling through collection."""
        collection_name = "test_collection"
        store.ensure_collection(collection_name, size=128)

        # Create test points
        points = [
            {
                "id": f"point{i}",
                "vector": [float(i) / 10] * 128,
                "payload": {"project_id": "test", "index": i},
            }
            for i in range(10)
        ]
        store.upsert(collection_name, points)

        # Scroll all
        results = store.scroll(collection_name, limit=100)
        assert len(results) == 10

        # Scroll with filter
        results = store.scroll(
            collection_name,
            filter={"project_id": "test"},
            limit=5,
        )
        assert len(results) == 5

    def test_get_and_update_payload(self, store: QdrantStore):
        """Test getting and updating payloads."""
        collection_name = "test_collection"
        store.ensure_collection(collection_name, size=128)

        # Upsert a point
        store.upsert(
            collection_name,
            [
                {
                    "id": "test-point",
                    "vector": [0.1] * 128,
                    "payload": {"status": "active", "count": 1},
                }
            ],
        )

        # Get payload
        payload = store.get_payload(collection_name, "test-point")
        assert payload is not None
        assert payload["status"] == "active"
        assert payload["count"] == 1

        # Update payload
        success = store.update_payload(
            collection_name,
            "test-point",
            {"status": "updated", "count": 2},
        )
        assert success is True

        # Verify update
        payload = store.get_payload(collection_name, "test-point")
        assert payload["status"] == "updated"
        assert payload["count"] == 2

    def test_delete(self, store: QdrantStore):
        """Test deleting points."""
        collection_name = "test_collection"
        store.ensure_collection(collection_name, size=128)

        # Upsert points
        points = [
            {"id": f"point{i}", "vector": [float(i)] * 128, "payload": {}}
            for i in range(5)
        ]
        store.upsert(collection_name, points)

        # Delete some points
        deleted = store.delete(collection_name, ["point0", "point1"])
        assert deleted == 2

        # Verify deletion
        all_points = store.scroll(collection_name, limit=100)
        assert len(all_points) == 3
        assert not any(p["id"] in ("point0", "point1") for p in all_points)

    def test_count(self, store: QdrantStore):
        """Test counting documents."""
        collection_name = "test_collection"
        store.ensure_collection(collection_name, size=128)

        # Upsert points
        points = [
            {
                "id": f"point{i}",
                "vector": [float(i)] * 128,
                "payload": {"project_id": "proj-a" if i < 3 else "proj-b"},
            }
            for i in range(5)
        ]
        store.upsert(collection_name, points)

        # Count all
        total = store.count(collection_name)
        assert total == 5

        # Count with filter
        proj_a_count = store.count(collection_name, filter={"project_id": "proj-a"})
        assert proj_a_count == 3

        proj_b_count = store.count(collection_name, filter={"project_id": "proj-b"})
        assert proj_b_count == 2

    def test_tombstoned_filtering(self, store: QdrantStore):
        """Test that tombstoned/superseded/archived entries are filtered out."""
        collection_name = "test_collection"
        store.ensure_collection(collection_name, size=128)

        # Upsert points with different statuses
        points = [
            {
                "id": "active",
                "vector": [0.1] * 128,
                "payload": {"status": "active"},
            },
            {
                "id": "tombstoned",
                "vector": [0.1] * 128,
                "payload": {"status": "tombstoned"},
            },
            {
                "id": "superseded",
                "vector": [0.1] * 128,
                "payload": {"status": "superseded"},
            },
            {
                "id": "archived",
                "vector": [0.1] * 128,
                "payload": {"status": "archived"},
            },
        ]
        store.upsert(collection_name, points)

        # Search should filter out tombstoned/superseded/archived
        query_vector = [0.1] * 128
        results = store.search(collection_name, query_vector, limit=10)

        # Should only return active point
        assert len(results) == 1
        assert results[0]["id"] == "active"


@skip_if_no_qdrant
def test_qdrant_memory_service_integration():
    """Test MemoryService with Qdrant backend."""
    from autopack.memory import MemoryService

    # Create MemoryService with Qdrant
    service = MemoryService(use_qdrant=True)

    # Verify Qdrant backend is used
    assert service.backend == "qdrant"
    assert isinstance(service.store, QdrantStore)

    # Test basic operation
    point_id = service.index_file(
        path="test.py",
        content="def hello(): print('world')",
        project_id="test-project",
    )

    assert point_id != ""
