"""Tests for FAISS vector store operations.

Tests cover:
- Collection creation and management
- Thread-safe access (concurrent operations)
- LRU eviction policy
- Collection persistence (save/load)
- Search functionality (FAISS and fallback)
- Delete, scroll, and filter operations
- Edge cases (empty collections, null vectors, etc.)
"""

import json
import tempfile
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch

import pytest

from autopack.memory.faiss_store import FAISS_AVAILABLE, FaissStore


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


class TestFaissStoreThreadSafety:
    """Tests for thread safety in FAISS collection initialization.

    These tests verify that the race condition fix in ensure_collection
    properly prevents double-initialization of collections.
    """

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def _make_point(self, point_id: str, value: int):
        """Create a test point with a dummy vector."""
        return {
            "id": point_id,
            "vector": [0.1] * 1536,
            "payload": {"value": value},
        }

    def test_concurrent_ensure_collection_same_name(self, store):
        """Test that concurrent ensure_collection calls for same name don't race.

        This verifies the fix for the race condition where collection could be
        initialized twice if two threads check existence simultaneously.
        """
        collection_name = "concurrent_test"
        num_threads = 10
        results = []
        errors = []

        def ensure_and_record():
            try:
                store.ensure_collection(collection_name)
                results.append(True)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=ensure_and_record) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should succeed
        assert len(results) == num_threads
        assert len(errors) == 0

        # Collection should exist and be properly initialized
        assert collection_name in store._collections
        col = store._collections[collection_name]
        assert "payloads" in col
        assert "id_map" in col

    def test_concurrent_upsert_same_collection(self, store):
        """Test that concurrent upsert operations are thread-safe."""
        collection_name = "concurrent_upsert"
        num_threads = 10
        points_per_thread = 5
        errors = []

        def upsert_points(thread_id):
            try:
                points = [
                    self._make_point(f"thread{thread_id}_point{i}", thread_id * 100 + i)
                    for i in range(points_per_thread)
                ]
                store.upsert(collection_name, points)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(upsert_points, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        # All points should be inserted (though some may be evicted if over limit)
        # At minimum, we should have some points and no corruption
        assert store.count(collection_name) > 0

    def test_concurrent_search_and_upsert(self, store):
        """Test that search and upsert can run concurrently without corruption."""
        collection_name = "concurrent_search_upsert"
        errors = []
        search_results = []

        # Pre-populate with some data
        initial_points = [self._make_point(f"initial_{i}", i) for i in range(10)]
        store.upsert(collection_name, initial_points)

        def do_upsert(thread_id):
            try:
                points = [
                    self._make_point(f"upsert_{thread_id}_{i}", thread_id * 100 + i)
                    for i in range(5)
                ]
                store.upsert(collection_name, points)
            except Exception as e:
                errors.append(f"upsert error: {e}")

        def do_search(thread_id):
            try:
                query_vector = [0.1] * 1536
                results = store.search(collection_name, query_vector, limit=5)
                search_results.append(len(results))
            except Exception as e:
                errors.append(f"search error: {e}")

        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=do_upsert, args=(i,)))
            threads.append(threading.Thread(target=do_search, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All searches should return results
        assert all(r >= 0 for r in search_results)

    def test_concurrent_collection_creation_different_names(self, store):
        """Test that creating different collections concurrently is safe."""
        num_collections = 10
        errors = []

        def create_collection(collection_id):
            try:
                name = f"collection_{collection_id}"
                store.ensure_collection(name)
                points = [self._make_point(f"point_{collection_id}_{i}", i) for i in range(3)]
                store.upsert(name, points)
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=num_collections) as executor:
            futures = [executor.submit(create_collection, i) for i in range(num_collections)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        # All collections should exist
        for i in range(num_collections):
            assert f"collection_{i}" in store._collections
            assert store.count(f"collection_{i}") == 3

    def test_collection_not_double_initialized(self, store):
        """Test that a collection is only initialized once even with concurrent calls."""
        collection_name = "no_double_init"
        initialization_count = []
        original_ensure = store.ensure_collection.__func__

        def counting_ensure(self, name, size=1536):
            # Track when we actually create (not just return early)
            with self._lock:
                if name not in self._collections:
                    initialization_count.append(name)
            original_ensure(self, name, size)

        # Monkey-patch to count initializations
        import types

        store.ensure_collection = types.MethodType(counting_ensure, store)

        num_threads = 20
        threads = [
            threading.Thread(target=lambda: store.ensure_collection(collection_name))
            for _ in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Collection should only be initialized once
        assert initialization_count.count(collection_name) == 1

    def test_concurrent_delete_and_search(self, store):
        """Test that delete and search can run concurrently without errors."""
        collection_name = "concurrent_delete_search"
        errors = []

        # Pre-populate
        points = [self._make_point(f"point_{i}", i) for i in range(20)]
        store.upsert(collection_name, points)

        def do_delete(point_ids):
            try:
                store.delete(collection_name, point_ids)
            except Exception as e:
                errors.append(f"delete error: {e}")

        def do_search():
            try:
                query_vector = [0.1] * 1536
                store.search(collection_name, query_vector, limit=5)
            except Exception as e:
                errors.append(f"search error: {e}")

        threads = []
        # Delete some points while searching
        for i in range(5):
            threads.append(
                threading.Thread(target=do_delete, args=([f"point_{i * 2}", f"point_{i * 2 + 1}"],))
            )
            threads.append(threading.Thread(target=do_search))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_lock_is_initialized(self, store):
        """Test that the lock is properly initialized in __init__."""
        assert hasattr(store, "_lock")
        assert isinstance(store._lock, type(threading.Lock()))

    def test_concurrent_get_payload_updates_lru(self, store):
        """Test that concurrent get_payload calls properly update LRU ordering."""
        collection_name = "concurrent_lru"
        store.MAX_PAYLOAD_ENTRIES = 10
        errors = []

        # Insert points
        points = [self._make_point(f"point_{i}", i) for i in range(10)]
        store.upsert(collection_name, points)

        def get_payload(point_id):
            try:
                store.get_payload(collection_name, point_id)
            except Exception as e:
                errors.append(str(e))

        # Concurrently access various points
        threads = []
        for _ in range(5):
            for i in range(10):
                threads.append(threading.Thread(target=get_payload, args=(f"point_{i}",)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All points should still be accessible
        for i in range(10):
            assert store.get_payload(collection_name, f"point_{i}") is not None


class TestFaissStoreCollectionCreation:
    """Tests for collection creation and management."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def test_ensure_collection_creates_new_collection(self, store):
        """Test that ensure_collection creates a new collection."""
        store.ensure_collection("test_collection", size=1536)

        assert "test_collection" in store._collections
        assert store._collections["test_collection"]["dim"] == 1536

    def test_ensure_collection_idempotent(self, store):
        """Test that ensure_collection is idempotent."""
        store.ensure_collection("test_collection", size=1536)
        store.ensure_collection("test_collection", size=1536)

        assert "test_collection" in store._collections
        assert store.count("test_collection") == 0

    def test_ensure_collection_creates_empty_payloads(self, store):
        """Test that new collection has empty payloads OrderedDict."""
        store.ensure_collection("test_collection")

        col = store._collections["test_collection"]
        assert isinstance(col["payloads"], OrderedDict)
        assert len(col["payloads"]) == 0

    def test_ensure_collection_creates_empty_id_map(self, store):
        """Test that new collection has empty id_map."""
        store.ensure_collection("test_collection")

        col = store._collections["test_collection"]
        assert isinstance(col["id_map"], dict)
        assert len(col["id_map"]) == 0

    def test_ensure_collection_custom_dimension(self, store):
        """Test creating collection with custom vector dimension."""
        store.ensure_collection("custom_dim", size=384)

        assert store._collections["custom_dim"]["dim"] == 384

    def test_ensure_collection_default_dimension(self, store):
        """Test creating collection with default dimension."""
        store.ensure_collection("default_dim")

        # Default dimension is 1536
        assert store._collections["default_dim"]["dim"] == 1536

    def test_multiple_collections_independent(self, store):
        """Test that multiple collections are independent."""
        store.ensure_collection("collection_a")
        store.ensure_collection("collection_b")

        store.upsert(
            "collection_a", [{"id": "a1", "vector": [0.1] * 1536, "payload": {"name": "a1"}}]
        )
        store.upsert(
            "collection_b", [{"id": "b1", "vector": [0.2] * 1536, "payload": {"name": "b1"}}]
        )

        assert store.count("collection_a") == 1
        assert store.count("collection_b") == 1
        assert store.get_payload("collection_a", "a1")["name"] == "a1"
        assert store.get_payload("collection_b", "b1")["name"] == "b1"

    def test_index_dir_created_on_init(self, temp_dir):
        """Test that index directory is created on initialization."""
        new_dir = Path(temp_dir) / "nested" / "faiss"
        FaissStore(index_dir=str(new_dir))

        assert new_dir.exists()


class TestFaissStorePersistence:
    """Tests for collection persistence (save/load)."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_collection_persisted_to_disk(self, temp_dir):
        """Test that collections are persisted to disk after upsert."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"name": "test"}}],
        )

        # Check files exist
        payload_path = Path(temp_dir) / "test_collection.payloads.json"
        id_map_path = Path(temp_dir) / "test_collection.idmap.json"

        assert payload_path.exists()
        assert id_map_path.exists()

    @pytest.mark.skipif(
        not FAISS_AVAILABLE, reason="FAISS not installed - loading requires index file"
    )
    def test_collection_loaded_on_reopen(self, temp_dir):
        """Test that collections are loaded when reopening store."""
        store1 = FaissStore(index_dir=temp_dir)
        store1.upsert(
            "test_collection",
            [
                {"id": "point_1", "vector": [0.1] * 1536, "payload": {"name": "test1"}},
                {"id": "point_2", "vector": [0.2] * 1536, "payload": {"name": "test2"}},
            ],
        )

        store2 = FaissStore(index_dir=temp_dir)
        store2.ensure_collection("test_collection")

        assert store2.count("test_collection") == 2
        assert store2.get_payload("test_collection", "point_1")["name"] == "test1"
        assert store2.get_payload("test_collection", "point_2")["name"] == "test2"

    def test_payloads_json_format(self, temp_dir):
        """Test that payloads are stored in valid JSON format."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"key": "value"}}],
        )

        payload_path = Path(temp_dir) / "test_collection.payloads.json"
        with open(payload_path) as f:
            data = json.load(f)

        assert "point_1" in data
        assert data["point_1"]["key"] == "value"

    def test_id_map_json_format(self, temp_dir):
        """Test that id_map is stored in valid JSON format."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"key": "value"}}],
        )

        id_map_path = Path(temp_dir) / "test_collection.idmap.json"
        with open(id_map_path) as f:
            data = json.load(f)

        assert "point_1" in data

    @pytest.mark.skipif(
        not FAISS_AVAILABLE, reason="FAISS not installed - loading requires index file"
    )
    def test_persistence_after_delete(self, temp_dir):
        """Test that deletions are persisted."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [
                {"id": "keep", "vector": [0.1] * 1536, "payload": {"name": "keep"}},
                {"id": "delete", "vector": [0.2] * 1536, "payload": {"name": "delete"}},
            ],
        )

        store.delete("test_collection", ["delete"])

        store2 = FaissStore(index_dir=temp_dir)
        store2.ensure_collection("test_collection")

        assert store2.get_payload("test_collection", "keep") is not None
        assert store2.get_payload("test_collection", "delete") is None

    @pytest.mark.skipif(
        not FAISS_AVAILABLE, reason="FAISS not installed - loading requires index file"
    )
    def test_persistence_after_update(self, temp_dir):
        """Test that payload updates are persisted."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"version": 1}}],
        )

        store.update_payload("test_collection", "point_1", {"version": 2})

        store2 = FaissStore(index_dir=temp_dir)
        store2.ensure_collection("test_collection")

        assert store2.get_payload("test_collection", "point_1")["version"] == 2

    @pytest.mark.skipif(not FAISS_AVAILABLE, reason="FAISS not installed")
    def test_faiss_index_persisted(self, temp_dir):
        """Test that FAISS index is persisted to disk."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {}}],
        )

        index_path = Path(temp_dir) / "test_collection.index"
        assert index_path.exists()

    def test_payload_files_persisted_without_faiss(self, temp_dir):
        """Test that payload and id_map files are persisted even without FAISS."""
        store = FaissStore(index_dir=temp_dir)
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"name": "test"}}],
        )

        payload_path = Path(temp_dir) / "test_collection.payloads.json"
        id_map_path = Path(temp_dir) / "test_collection.idmap.json"

        assert payload_path.exists()
        assert id_map_path.exists()

        with open(payload_path) as f:
            payloads = json.load(f)
        assert payloads["point_1"]["name"] == "test"


class TestFaissStoreSearch:
    """Tests for search functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    @pytest.fixture
    def populated_store(self, store):
        """Create a store with test data."""
        points = [
            {"id": "similar_1", "vector": [0.9] * 1536, "payload": {"group": "high"}},
            {"id": "similar_2", "vector": [0.85] * 1536, "payload": {"group": "high"}},
            {"id": "different_1", "vector": [0.1] * 1536, "payload": {"group": "low"}},
            {"id": "different_2", "vector": [0.15] * 1536, "payload": {"group": "low"}},
        ]
        store.upsert("test_collection", points)
        return store

    def test_search_returns_results(self, populated_store):
        """Test that search returns results."""
        query = [0.9] * 1536
        results = populated_store.search("test_collection", query, limit=2)

        assert len(results) > 0
        assert len(results) <= 2

    def test_search_returns_expected_fields(self, populated_store):
        """Test that search results have expected fields."""
        query = [0.9] * 1536
        results = populated_store.search("test_collection", query, limit=1)

        assert len(results) == 1
        result = results[0]
        assert "id" in result
        assert "score" in result
        assert "payload" in result

    def test_search_with_filter(self, populated_store):
        """Test search with payload filter."""
        query = [0.5] * 1536
        results = populated_store.search(
            "test_collection", query, filter={"group": "high"}, limit=10
        )

        assert all(r["payload"]["group"] == "high" for r in results)

    def test_search_empty_collection(self, store):
        """Test search on empty collection returns empty list."""
        store.ensure_collection("empty")
        results = store.search("empty", [0.1] * 1536, limit=5)

        assert results == []

    def test_search_limit_respected(self, populated_store):
        """Test that search respects limit parameter."""
        query = [0.5] * 1536
        results = populated_store.search("test_collection", query, limit=1)

        assert len(results) <= 1

    def test_search_skips_tombstoned_entries(self, store):
        """Test that search skips entries with tombstoned status."""
        store.upsert(
            "test_collection",
            [
                {"id": "active", "vector": [0.9] * 1536, "payload": {"status": "active"}},
                {
                    "id": "tombstoned",
                    "vector": [0.9] * 1536,
                    "payload": {"status": "tombstoned"},
                },
            ],
        )

        results = store.search("test_collection", [0.9] * 1536, limit=10)

        result_ids = [r["id"] for r in results]
        assert "active" in result_ids
        assert "tombstoned" not in result_ids

    def test_search_skips_superseded_entries(self, store):
        """Test that search skips entries with superseded status."""
        store.upsert(
            "test_collection",
            [
                {"id": "active", "vector": [0.9] * 1536, "payload": {"status": "active"}},
                {
                    "id": "superseded",
                    "vector": [0.9] * 1536,
                    "payload": {"status": "superseded"},
                },
            ],
        )

        results = store.search("test_collection", [0.9] * 1536, limit=10)

        result_ids = [r["id"] for r in results]
        assert "active" in result_ids
        assert "superseded" not in result_ids

    def test_search_skips_archived_entries(self, store):
        """Test that search skips entries with archived status."""
        store.upsert(
            "test_collection",
            [
                {"id": "active", "vector": [0.9] * 1536, "payload": {"status": "active"}},
                {"id": "archived", "vector": [0.9] * 1536, "payload": {"status": "archived"}},
            ],
        )

        results = store.search("test_collection", [0.9] * 1536, limit=10)

        result_ids = [r["id"] for r in results]
        assert "active" in result_ids
        assert "archived" not in result_ids


class TestFaissStoreDeleteScrollFilter:
    """Tests for delete, scroll, and filter operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def test_delete_removes_payload(self, store):
        """Test that delete removes payload."""
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"name": "test"}}],
        )

        deleted = store.delete("test_collection", ["point_1"])

        assert deleted == 1
        assert store.get_payload("test_collection", "point_1") is None

    def test_delete_removes_id_map_entry(self, store):
        """Test that delete removes id_map entry."""
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {}}],
        )

        store.delete("test_collection", ["point_1"])

        col = store._collections["test_collection"]
        assert "point_1" not in col["id_map"]

    def test_delete_nonexistent_id(self, store):
        """Test deleting nonexistent ID returns 0."""
        store.ensure_collection("test_collection")

        deleted = store.delete("test_collection", ["nonexistent"])

        assert deleted == 0

    def test_delete_multiple_ids(self, store):
        """Test deleting multiple IDs at once."""
        store.upsert(
            "test_collection",
            [
                {"id": "point_1", "vector": [0.1] * 1536, "payload": {}},
                {"id": "point_2", "vector": [0.2] * 1536, "payload": {}},
                {"id": "point_3", "vector": [0.3] * 1536, "payload": {}},
            ],
        )

        deleted = store.delete("test_collection", ["point_1", "point_2"])

        assert deleted == 2
        assert store.get_payload("test_collection", "point_1") is None
        assert store.get_payload("test_collection", "point_2") is None
        assert store.get_payload("test_collection", "point_3") is not None

    def test_scroll_returns_all_matching(self, store):
        """Test that scroll returns all matching entries."""
        store.upsert(
            "test_collection",
            [
                {"id": "a1", "vector": [0.1] * 1536, "payload": {"type": "a"}},
                {"id": "a2", "vector": [0.2] * 1536, "payload": {"type": "a"}},
                {"id": "b1", "vector": [0.3] * 1536, "payload": {"type": "b"}},
            ],
        )

        results = store.scroll("test_collection", filter={"type": "a"}, limit=100)

        assert len(results) == 2
        assert all(r["payload"]["type"] == "a" for r in results)

    def test_scroll_without_filter(self, store):
        """Test scroll without filter returns all entries."""
        store.upsert(
            "test_collection",
            [
                {"id": "point_1", "vector": [0.1] * 1536, "payload": {}},
                {"id": "point_2", "vector": [0.2] * 1536, "payload": {}},
            ],
        )

        results = store.scroll("test_collection", limit=100)

        assert len(results) == 2

    def test_scroll_respects_limit(self, store):
        """Test that scroll respects limit parameter."""
        store.upsert(
            "test_collection",
            [{"id": f"point_{i}", "vector": [0.1] * 1536, "payload": {}} for i in range(10)],
        )

        results = store.scroll("test_collection", limit=3)

        assert len(results) == 3

    def test_count_without_filter(self, store):
        """Test count without filter returns total count."""
        store.upsert(
            "test_collection",
            [{"id": f"point_{i}", "vector": [0.1] * 1536, "payload": {}} for i in range(5)],
        )

        assert store.count("test_collection") == 5

    def test_count_with_filter(self, store):
        """Test count with filter returns filtered count."""
        store.upsert(
            "test_collection",
            [
                {"id": "a1", "vector": [0.1] * 1536, "payload": {"type": "a"}},
                {"id": "a2", "vector": [0.2] * 1536, "payload": {"type": "a"}},
                {"id": "b1", "vector": [0.3] * 1536, "payload": {"type": "b"}},
            ],
        )

        assert store.count("test_collection", filter={"type": "a"}) == 2
        assert store.count("test_collection", filter={"type": "b"}) == 1

    def test_filter_matches_multiple_conditions(self, store):
        """Test filter matching multiple conditions."""
        store.upsert(
            "test_collection",
            [
                {
                    "id": "match",
                    "vector": [0.1] * 1536,
                    "payload": {"type": "a", "status": "active"},
                },
                {
                    "id": "partial1",
                    "vector": [0.2] * 1536,
                    "payload": {"type": "a", "status": "inactive"},
                },
                {
                    "id": "partial2",
                    "vector": [0.3] * 1536,
                    "payload": {"type": "b", "status": "active"},
                },
            ],
        )

        results = store.scroll(
            "test_collection", filter={"type": "a", "status": "active"}, limit=100
        )

        assert len(results) == 1
        assert results[0]["id"] == "match"


class TestFaissStoreUpsert:
    """Tests for upsert functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def test_upsert_returns_count(self, store):
        """Test that upsert returns number of points inserted."""
        points = [{"id": f"point_{i}", "vector": [0.1] * 1536, "payload": {}} for i in range(5)]

        count = store.upsert("test_collection", points)

        assert count == 5

    def test_upsert_auto_generates_id(self, store):
        """Test that upsert auto-generates ID if not provided."""
        points = [{"vector": [0.1] * 1536, "payload": {"name": "test"}}]

        store.upsert("test_collection", points)

        assert store.count("test_collection") == 1
        results = store.scroll("test_collection", limit=1)
        assert results[0]["id"] is not None

    def test_upsert_creates_collection_if_missing(self, store):
        """Test that upsert creates collection if it doesn't exist."""
        points = [{"id": "point_1", "vector": [0.1] * 1536, "payload": {}}]

        store.upsert("new_collection", points)

        assert "new_collection" in store._collections

    def test_upsert_stores_payload(self, store):
        """Test that upsert stores payload correctly."""
        payload = {"name": "test", "value": 42, "nested": {"key": "value"}}
        points = [{"id": "point_1", "vector": [0.1] * 1536, "payload": payload}]

        store.upsert("test_collection", points)

        retrieved = store.get_payload("test_collection", "point_1")
        assert retrieved == payload

    def test_upsert_empty_payload(self, store):
        """Test upserting with empty payload."""
        points = [{"id": "point_1", "vector": [0.1] * 1536, "payload": {}}]

        store.upsert("test_collection", points)

        assert store.get_payload("test_collection", "point_1") == {}

    def test_upsert_overwrites_payload(self, store):
        """Test that upserting same ID overwrites payload."""
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"version": 1}}],
        )
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.2] * 1536, "payload": {"version": 2}}],
        )

        payload = store.get_payload("test_collection", "point_1")
        assert payload["version"] == 2


class TestFaissStoreGetUpdatePayload:
    """Tests for get_payload and update_payload methods."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def test_get_payload_existing(self, store):
        """Test getting payload for existing point."""
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"key": "value"}}],
        )

        payload = store.get_payload("test_collection", "point_1")

        assert payload == {"key": "value"}

    def test_get_payload_nonexistent(self, store):
        """Test getting payload for nonexistent point returns None."""
        store.ensure_collection("test_collection")

        payload = store.get_payload("test_collection", "nonexistent")

        assert payload is None

    def test_update_payload_success(self, store):
        """Test updating payload for existing point."""
        store.upsert(
            "test_collection",
            [{"id": "point_1", "vector": [0.1] * 1536, "payload": {"version": 1}}],
        )

        result = store.update_payload("test_collection", "point_1", {"version": 2})

        assert result is True
        assert store.get_payload("test_collection", "point_1") == {"version": 2}

    def test_update_payload_nonexistent(self, store):
        """Test updating payload for nonexistent point returns False."""
        store.ensure_collection("test_collection")

        result = store.update_payload("test_collection", "nonexistent", {"key": "value"})

        assert result is False

    def test_get_payload_marks_as_recently_used(self, store):
        """Test that get_payload marks entry as recently used."""
        store.MAX_PAYLOAD_ENTRIES = 3
        store.upsert(
            "test_collection",
            [
                {"id": "point_1", "vector": [0.1] * 1536, "payload": {}},
                {"id": "point_2", "vector": [0.2] * 1536, "payload": {}},
                {"id": "point_3", "vector": [0.3] * 1536, "payload": {}},
            ],
        )

        # Access point_1 to make it recently used
        store.get_payload("test_collection", "point_1")

        # Add more points to trigger eviction
        store.upsert(
            "test_collection",
            [{"id": "point_4", "vector": [0.4] * 1536, "payload": {}}],
        )

        # point_1 should still exist (was recently used)
        assert store.get_payload("test_collection", "point_1") is not None


class TestFaissStoreFallbackMode:
    """Tests for fallback mode when FAISS is not available."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_fallback_search_works(self, temp_dir):
        """Test that fallback search works without FAISS."""
        with patch("autopack.memory.faiss_store.FAISS_AVAILABLE", False):
            store = FaissStore(index_dir=temp_dir)

            store._collections["test"] = {
                "index": None,
                "payloads": OrderedDict(
                    [
                        ("p1", {"group": "a"}),
                        ("p2", {"group": "b"}),
                    ]
                ),
                "id_map": {"p1": 0, "p2": 1},
                "dim": 4,
                "vectors": [
                    {"id": "p1", "vector": [0.9, 0.1, 0.0, 0.0]},
                    {"id": "p2", "vector": [0.1, 0.9, 0.0, 0.0]},
                ],
            }

            results = store._fallback_search(
                store._collections["test"], [0.9, 0.1, 0.0, 0.0], None, 10
            )

            assert len(results) > 0
            assert results[0]["id"] == "p1"

    def test_fallback_search_with_filter(self, temp_dir):
        """Test fallback search with filter."""
        store = FaissStore(index_dir=temp_dir)

        store._collections["test"] = {
            "index": None,
            "payloads": OrderedDict(
                [
                    ("p1", {"group": "a"}),
                    ("p2", {"group": "b"}),
                    ("p3", {"group": "a"}),
                ]
            ),
            "id_map": {"p1": 0, "p2": 1, "p3": 2},
            "dim": 4,
            "vectors": [
                {"id": "p1", "vector": [0.9, 0.1, 0.0, 0.0]},
                {"id": "p2", "vector": [0.1, 0.9, 0.0, 0.0]},
                {"id": "p3", "vector": [0.8, 0.2, 0.0, 0.0]},
            ],
        }

        results = store._fallback_search(
            store._collections["test"], [0.9, 0.1, 0.0, 0.0], {"group": "a"}, 10
        )

        assert all(r["payload"]["group"] == "a" for r in results)

    def test_fallback_search_empty_collection(self, temp_dir):
        """Test fallback search on empty collection."""
        store = FaissStore(index_dir=temp_dir)

        store._collections["test"] = {
            "index": None,
            "payloads": OrderedDict(),
            "id_map": {},
            "dim": 4,
            "vectors": [],
        }

        results = store._fallback_search(store._collections["test"], [0.5, 0.5, 0.0, 0.0], None, 10)

        assert results == []

    def test_fallback_cosine_similarity_calculation(self, temp_dir):
        """Test cosine similarity calculation in fallback mode."""
        store = FaissStore(index_dir=temp_dir)

        store._collections["test"] = {
            "index": None,
            "payloads": OrderedDict(
                [
                    ("identical", {}),
                    ("orthogonal", {}),
                    ("opposite", {}),
                ]
            ),
            "id_map": {"identical": 0, "orthogonal": 1, "opposite": 2},
            "dim": 4,
            "vectors": [
                {"id": "identical", "vector": [1.0, 0.0, 0.0, 0.0]},
                {"id": "orthogonal", "vector": [0.0, 1.0, 0.0, 0.0]},
                {"id": "opposite", "vector": [-1.0, 0.0, 0.0, 0.0]},
            ],
        }

        results = store._fallback_search(store._collections["test"], [1.0, 0.0, 0.0, 0.0], None, 10)

        assert results[0]["id"] == "identical"
        assert results[0]["score"] == pytest.approx(1.0)


class TestFaissStoreEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for FAISS indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def store(self, temp_dir):
        """Create a FaissStore instance."""
        return FaissStore(index_dir=temp_dir)

    def test_empty_points_list_upsert(self, store):
        """Test upserting empty list of points."""
        count = store.upsert("test_collection", [])

        assert count == 0
        assert store.count("test_collection") == 0

    def test_empty_ids_list_delete(self, store):
        """Test deleting empty list of IDs."""
        store.ensure_collection("test_collection")

        deleted = store.delete("test_collection", [])

        assert deleted == 0

    def test_special_characters_in_id(self, store):
        """Test handling of special characters in point ID."""
        special_id = "point:with/special\\chars?#&=+"
        store.upsert(
            "test_collection",
            [{"id": special_id, "vector": [0.1] * 1536, "payload": {"name": "special"}}],
        )

        payload = store.get_payload("test_collection", special_id)
        assert payload["name"] == "special"

    def test_unicode_in_payload(self, store):
        """Test handling of unicode characters in payload."""
        payload = {"name": "テスト", "emoji": "🚀", "chinese": "测试"}
        store.upsert(
            "test_collection",
            [{"id": "unicode_point", "vector": [0.1] * 1536, "payload": payload}],
        )

        retrieved = store.get_payload("test_collection", "unicode_point")
        assert retrieved == payload

    def test_large_payload(self, store):
        """Test handling of large payload."""
        large_data = "x" * 100000
        payload = {"large_field": large_data}
        store.upsert(
            "test_collection",
            [{"id": "large_point", "vector": [0.1] * 1536, "payload": payload}],
        )

        retrieved = store.get_payload("test_collection", "large_point")
        assert len(retrieved["large_field"]) == 100000

    def test_nested_payload(self, store):
        """Test handling of deeply nested payload."""
        payload = {"level1": {"level2": {"level3": {"level4": {"level5": {"value": "deep"}}}}}}
        store.upsert(
            "test_collection",
            [{"id": "nested_point", "vector": [0.1] * 1536, "payload": payload}],
        )

        retrieved = store.get_payload("test_collection", "nested_point")
        assert retrieved["level1"]["level2"]["level3"]["level4"]["level5"]["value"] == "deep"

    def test_null_values_in_payload(self, store):
        """Test handling of null values in payload."""
        payload = {"null_field": None, "valid_field": "value"}
        store.upsert(
            "test_collection",
            [{"id": "null_point", "vector": [0.1] * 1536, "payload": payload}],
        )

        retrieved = store.get_payload("test_collection", "null_point")
        assert retrieved["null_field"] is None
        assert retrieved["valid_field"] == "value"

    def test_path_methods(self, store, temp_dir):
        """Test path generation methods."""
        assert store._index_path("test") == Path(temp_dir) / "test.index"
        assert store._payload_path("test") == Path(temp_dir) / "test.payloads.json"
        assert store._id_map_path("test") == Path(temp_dir) / "test.idmap.json"

    def test_matches_filter_empty_filter(self, store):
        """Test _matches_filter with empty filter returns True."""
        assert store._matches_filter({"key": "value"}, {}) is True

    def test_matches_filter_missing_key(self, store):
        """Test _matches_filter with missing key returns False."""
        assert store._matches_filter({"key": "value"}, {"other": "value"}) is False

    def test_matches_filter_wrong_value(self, store):
        """Test _matches_filter with wrong value returns False."""
        assert store._matches_filter({"key": "value"}, {"key": "other"}) is False

    def test_matches_filter_matching(self, store):
        """Test _matches_filter with matching filter returns True."""
        assert store._matches_filter({"key": "value"}, {"key": "value"}) is True
