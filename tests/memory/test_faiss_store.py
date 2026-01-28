"""Tests for FAISS store LRU eviction policy."""

import tempfile

import pytest

from autopack.memory.faiss_store import FaissStore


class TestFaissStoreLRUEviction:
    """Tests for LRU eviction in FAISS payload cache."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore with a small max entries limit for testing."""
        store = FaissStore(index_dir=temp_dir)
        # Set small limit for testing eviction
        store.MAX_PAYLOAD_ENTRIES = 5
        return store

    def _make_point(self, point_id: str, value: int):
        """Create a test point with a dummy vector."""
        return {
            "id": point_id,
            "vector": [0.1] * 1536,  # Dummy 1536-dim vector
            "payload": {"value": value},
        }

    def test_eviction_removes_oldest_entries(self, store):
        """Test that oldest entries are evicted when limit is exceeded."""
        collection = "test_collection"

        # Insert 5 points (at the limit)
        points = [self._make_point(f"id_{i}", i) for i in range(5)]
        store.upsert(collection, points)

        # All 5 should be present
        assert store.count(collection) == 5
        for i in range(5):
            assert store.get_payload(collection, f"id_{i}") is not None

        # Insert 3 more points (should evict 3 oldest)
        more_points = [self._make_point(f"id_{i}", i) for i in range(5, 8)]
        store.upsert(collection, more_points)

        # Should still have 5 entries (limit enforced)
        assert store.count(collection) == 5

        # Oldest 3 (id_0, id_1, id_2) should be evicted
        for i in range(3):
            assert store.get_payload(collection, f"id_{i}") is None

        # Remaining entries (id_3, id_4, id_5, id_6, id_7) should exist
        for i in range(3, 8):
            assert store.get_payload(collection, f"id_{i}") is not None

    def test_lru_access_preserves_entries(self, store):
        """Test that accessing entries moves them to end and preserves them."""
        collection = "test_collection"

        # Insert 5 points
        points = [self._make_point(f"id_{i}", i) for i in range(5)]
        store.upsert(collection, points)

        # Access id_0 and id_1 to make them "recently used"
        store.get_payload(collection, "id_0")
        store.get_payload(collection, "id_1")

        # Now insert 3 more - should evict id_2, id_3, id_4 (not id_0, id_1)
        more_points = [self._make_point(f"id_{i}", i) for i in range(5, 8)]
        store.upsert(collection, more_points)

        # id_0 and id_1 should be preserved (were accessed)
        assert store.get_payload(collection, "id_0") is not None
        assert store.get_payload(collection, "id_1") is not None

        # id_2, id_3, id_4 should be evicted
        assert store.get_payload(collection, "id_2") is None
        assert store.get_payload(collection, "id_3") is None
        assert store.get_payload(collection, "id_4") is None

    def test_update_payload_preserves_entry(self, store):
        """Test that updating payload marks entry as recently used."""
        collection = "test_collection"

        # Insert 5 points
        points = [self._make_point(f"id_{i}", i) for i in range(5)]
        store.upsert(collection, points)

        # Update id_0 to make it "recently used"
        store.update_payload(collection, "id_0", {"value": 100})

        # Insert 4 more - should evict id_1, id_2, id_3, id_4 but not id_0
        more_points = [self._make_point(f"id_{i}", i) for i in range(5, 9)]
        store.upsert(collection, more_points)

        # id_0 should be preserved with updated value
        payload = store.get_payload(collection, "id_0")
        assert payload is not None
        assert payload["value"] == 100

        # Others should be evicted
        for i in range(1, 5):
            assert store.get_payload(collection, f"id_{i}") is None

    def test_eviction_logs_when_entries_removed(self, store, caplog):
        """Test that eviction is logged."""
        import logging

        caplog.set_level(logging.INFO)
        collection = "test_collection"

        # Insert more than limit
        points = [self._make_point(f"id_{i}", i) for i in range(10)]
        store.upsert(collection, points)

        # Check that eviction was logged
        assert any("Evicted" in record.message for record in caplog.records)

    def test_no_eviction_when_under_limit(self, store):
        """Test that no eviction occurs when under the limit."""
        collection = "test_collection"

        # Insert less than limit
        points = [self._make_point(f"id_{i}", i) for i in range(3)]
        store.upsert(collection, points)

        # All 3 should be present
        assert store.count(collection) == 3
        for i in range(3):
            assert store.get_payload(collection, f"id_{i}") is not None

    def test_eviction_syncs_id_map(self, store):
        """Test that id_map is kept in sync with payloads during eviction."""
        collection = "test_collection"

        # Insert more than limit
        points = [self._make_point(f"id_{i}", i) for i in range(10)]
        store.upsert(collection, points)

        # Check that payloads and id_map are in sync
        col = store._collections[collection]
        assert len(col["payloads"]) == 5
        # id_map entries for evicted points should also be removed
        for i in range(5):
            assert f"id_{i}" not in col["payloads"]
            assert f"id_{i}" not in col["id_map"]

    def test_max_payload_entries_default(self):
        """Test that MAX_PAYLOAD_ENTRIES has reasonable default."""
        assert FaissStore.MAX_PAYLOAD_ENTRIES == 10000

    def test_multiple_collections_independent_eviction(self, store):
        """Test that eviction is independent per collection."""
        # Insert 5 entries in collection_a
        points_a = [self._make_point(f"a_{i}", i) for i in range(5)]
        store.upsert("collection_a", points_a)

        # Insert 5 entries in collection_b
        points_b = [self._make_point(f"b_{i}", i) for i in range(5)]
        store.upsert("collection_b", points_b)

        # Both should have 5 entries
        assert store.count("collection_a") == 5
        assert store.count("collection_b") == 5

        # Add 3 more to collection_a (evicts 3 oldest in a, not b)
        more_a = [self._make_point(f"a_{i}", i) for i in range(5, 8)]
        store.upsert("collection_a", more_a)

        # collection_a should have 5 (evicted 3)
        assert store.count("collection_a") == 5
        # collection_b should still have all 5
        assert store.count("collection_b") == 5
        for i in range(5):
            assert store.get_payload("collection_b", f"b_{i}") is not None
