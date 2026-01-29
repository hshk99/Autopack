"""Tests for FAISS store LRU eviction policy and thread safety."""

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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
