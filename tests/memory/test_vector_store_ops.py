"""Tests for vector_store_ops module (IMP-MAINT-005).

Tests cover:
- VectorStoreOperations class
- safe_call error handling
- upsert_point and upsert_points methods
- search and search_by_project methods
- scroll and scroll_by_project methods
- delete, count, get_payload, update_payload methods
- build_point helper function
- build_project_filter helper function
"""

from unittest.mock import Mock

import pytest

from autopack.memory.vector_store_ops import (VectorStoreOperations,
                                              build_point,
                                              build_project_filter)


@pytest.fixture
def mock_store():
    """Create a mock store for testing."""
    store = Mock()
    store.upsert.return_value = 1
    store.search.return_value = [{"id": "test", "score": 0.9, "payload": {}}]
    store.scroll.return_value = [{"id": "test", "payload": {}}]
    store.delete.return_value = 1
    store.count.return_value = 10
    store.get_payload.return_value = {"key": "value"}
    store.update_payload.return_value = True
    store.ensure_collection.return_value = None
    return store


@pytest.fixture
def vector_ops(mock_store):
    """Create VectorStoreOperations with mock store."""
    return VectorStoreOperations(mock_store, enabled=True)


@pytest.fixture
def disabled_vector_ops(mock_store):
    """Create disabled VectorStoreOperations."""
    return VectorStoreOperations(mock_store, enabled=False)


class TestVectorStoreOperations:
    """Tests for VectorStoreOperations class."""

    def test_enabled_property(self, vector_ops):
        """Should return enabled status."""
        assert vector_ops.enabled is True

    def test_disabled_operations_return_defaults(self, disabled_vector_ops):
        """Disabled operations should return defaults without calling store."""
        assert disabled_vector_ops.upsert_point("col", "id", [0.1], {}) == 0
        assert disabled_vector_ops.upsert_points("col", []) == 0
        assert disabled_vector_ops.search("col", [0.1]) == []
        assert disabled_vector_ops.scroll("col") == []
        assert disabled_vector_ops.delete("col", ["id"]) == 0
        assert disabled_vector_ops.count("col") == 0
        assert disabled_vector_ops.get_payload("col", "id") is None
        assert disabled_vector_ops.update_payload("col", "id", {}) is False


class TestSafeCall:
    """Tests for safe_call error handling."""

    def test_safe_call_returns_result_on_success(self):
        """safe_call should return function result on success."""
        store = Mock()
        ops = VectorStoreOperations(store, enabled=True)
        result = ops.safe_call("test", lambda: "success", "default")
        assert result == "success"

    def test_safe_call_returns_default_on_exception(self):
        """safe_call should return default value on exception."""
        store = Mock()
        ops = VectorStoreOperations(store, enabled=True)

        def failing_fn():
            raise RuntimeError("Test error")

        result = ops.safe_call("test", failing_fn, "default_value")
        assert result == "default_value"


class TestUpsertOperations:
    """Tests for upsert operations."""

    def test_upsert_point(self, vector_ops, mock_store):
        """upsert_point should call store.upsert with correct args."""
        result = vector_ops.upsert_point(
            "test_collection",
            "point-1",
            [0.1, 0.2, 0.3],
            {"key": "value"},
        )
        assert result == 1
        mock_store.upsert.assert_called_once()
        call_args = mock_store.upsert.call_args
        assert call_args[0][0] == "test_collection"
        assert len(call_args[0][1]) == 1
        assert call_args[0][1][0]["id"] == "point-1"

    def test_upsert_points(self, vector_ops, mock_store):
        """upsert_points should call store.upsert with multiple points."""
        points = [
            {"id": "p1", "vector": [0.1], "payload": {}},
            {"id": "p2", "vector": [0.2], "payload": {}},
        ]
        mock_store.upsert.return_value = 2
        result = vector_ops.upsert_points("test_collection", points)
        assert result == 2
        mock_store.upsert.assert_called_once_with("test_collection", points)

    def test_upsert_points_empty_list(self, vector_ops, mock_store):
        """upsert_points with empty list should return 0 without calling store."""
        result = vector_ops.upsert_points("test_collection", [])
        assert result == 0
        mock_store.upsert.assert_not_called()


class TestSearchOperations:
    """Tests for search operations."""

    def test_search(self, vector_ops, mock_store):
        """search should call store.search with correct args."""
        result = vector_ops.search("test_collection", [0.1, 0.2], limit=5)
        assert len(result) == 1
        mock_store.search.assert_called_once_with(
            "test_collection",
            [0.1, 0.2],
            filter=None,
            limit=5,
        )

    def test_search_with_filter(self, vector_ops, mock_store):
        """search should pass filter to store."""
        filter_dict = {"type": "error"}
        vector_ops.search("col", [0.1], filter=filter_dict)
        mock_store.search.assert_called_once()
        call_kwargs = mock_store.search.call_args[1]
        assert call_kwargs["filter"] == filter_dict

    def test_search_by_project(self, vector_ops, mock_store):
        """search_by_project should include project_id in filter."""
        vector_ops.search_by_project("col", [0.1], "project-123", limit=10)
        mock_store.search.assert_called_once()
        call_kwargs = mock_store.search.call_args[1]
        assert call_kwargs["filter"]["project_id"] == "project-123"

    def test_search_by_project_with_additional_filters(self, vector_ops, mock_store):
        """search_by_project should merge additional filters."""
        vector_ops.search_by_project(
            "col",
            [0.1],
            "project-123",
            additional_filters={"type": "error"},
        )
        mock_store.search.assert_called_once()
        call_kwargs = mock_store.search.call_args[1]
        assert call_kwargs["filter"]["project_id"] == "project-123"
        assert call_kwargs["filter"]["type"] == "error"


class TestScrollOperations:
    """Tests for scroll operations."""

    def test_scroll(self, vector_ops, mock_store):
        """scroll should call store.scroll with correct args."""
        result = vector_ops.scroll("test_collection", limit=50)
        assert len(result) == 1
        mock_store.scroll.assert_called_once_with(
            "test_collection",
            filter=None,
            limit=50,
        )

    def test_scroll_by_project(self, vector_ops, mock_store):
        """scroll_by_project should include project_id in filter."""
        vector_ops.scroll_by_project("col", "project-123", limit=100)
        mock_store.scroll.assert_called_once()
        call_kwargs = mock_store.scroll.call_args[1]
        assert call_kwargs["filter"]["project_id"] == "project-123"


class TestDeleteOperations:
    """Tests for delete operations."""

    def test_delete(self, vector_ops, mock_store):
        """delete should call store.delete with correct args."""
        result = vector_ops.delete("test_collection", ["id1", "id2"])
        assert result == 1
        mock_store.delete.assert_called_once_with("test_collection", ["id1", "id2"])

    def test_delete_empty_list(self, vector_ops, mock_store):
        """delete with empty list should return 0 without calling store."""
        result = vector_ops.delete("test_collection", [])
        assert result == 0
        mock_store.delete.assert_not_called()


class TestCountOperation:
    """Tests for count operation."""

    def test_count(self, vector_ops, mock_store):
        """count should call store.count with correct args."""
        result = vector_ops.count("test_collection")
        assert result == 10
        mock_store.count.assert_called_once_with("test_collection", filter=None)

    def test_count_with_filter(self, vector_ops, mock_store):
        """count should pass filter to store."""
        filter_dict = {"type": "error"}
        vector_ops.count("col", filter=filter_dict)
        mock_store.count.assert_called_once()
        call_kwargs = mock_store.count.call_args[1]
        assert call_kwargs["filter"] == filter_dict


class TestPayloadOperations:
    """Tests for payload operations."""

    def test_get_payload(self, vector_ops, mock_store):
        """get_payload should call store.get_payload with correct args."""
        result = vector_ops.get_payload("test_collection", "point-1")
        assert result == {"key": "value"}
        mock_store.get_payload.assert_called_once_with("test_collection", "point-1")

    def test_update_payload(self, vector_ops, mock_store):
        """update_payload should call store.update_payload with correct args."""
        result = vector_ops.update_payload("test_collection", "point-1", {"new": "value"})
        assert result is True
        mock_store.update_payload.assert_called_once_with(
            "test_collection",
            "point-1",
            {"new": "value"},
        )


class TestEnsureCollection:
    """Tests for ensure_collection operation."""

    def test_ensure_collection(self, vector_ops, mock_store):
        """ensure_collection should call store.ensure_collection."""
        vector_ops.ensure_collection("test_collection", vector_size=1536)
        mock_store.ensure_collection.assert_called_once_with("test_collection", 1536)

    def test_ensure_collection_default_size(self, vector_ops, mock_store):
        """ensure_collection should use default vector size."""
        vector_ops.ensure_collection("test_collection")
        mock_store.ensure_collection.assert_called_once_with("test_collection", 1536)


class TestBuildPoint:
    """Tests for build_point helper function."""

    def test_build_point_basic(self):
        """build_point should create point with basic fields."""
        point = build_point(
            point_id="test-1",
            vector=[0.1, 0.2, 0.3],
            payload={"content": "test"},
        )
        assert point["id"] == "test-1"
        assert point["vector"] == [0.1, 0.2, 0.3]
        assert point["payload"]["content"] == "test"
        assert "timestamp" in point["payload"]

    def test_build_point_with_project_id(self):
        """build_point should include project_id in payload."""
        point = build_point(
            point_id="test-1",
            vector=[0.1],
            payload={},
            project_id="project-123",
        )
        assert point["payload"]["project_id"] == "project-123"

    def test_build_point_with_run_id(self):
        """build_point should include run_id in payload."""
        point = build_point(
            point_id="test-1",
            vector=[0.1],
            payload={},
            run_id="run-456",
        )
        assert point["payload"]["run_id"] == "run-456"

    def test_build_point_with_custom_timestamp(self):
        """build_point should use custom timestamp if provided."""
        custom_ts = "2024-01-15T10:30:00+00:00"
        point = build_point(
            point_id="test-1",
            vector=[0.1],
            payload={},
            timestamp=custom_ts,
        )
        assert point["payload"]["timestamp"] == custom_ts

    def test_build_point_preserves_existing_payload(self):
        """build_point should preserve existing payload fields."""
        point = build_point(
            point_id="test-1",
            vector=[0.1],
            payload={"type": "error", "content": "test"},
            project_id="project-123",
        )
        assert point["payload"]["type"] == "error"
        assert point["payload"]["content"] == "test"
        assert point["payload"]["project_id"] == "project-123"


class TestBuildProjectFilter:
    """Tests for build_project_filter helper function."""

    def test_build_filter_with_project_only(self):
        """build_project_filter should create filter with project_id."""
        filter_dict = build_project_filter("project-123")
        assert filter_dict == {"project_id": "project-123"}

    def test_build_filter_with_additional_filters(self):
        """build_project_filter should merge additional filters."""
        filter_dict = build_project_filter(
            "project-123",
            additional_filters={"type": "error", "status": "active"},
        )
        assert filter_dict["project_id"] == "project-123"
        assert filter_dict["type"] == "error"
        assert filter_dict["status"] == "active"

    def test_additional_filters_none(self):
        """build_project_filter should handle None additional_filters."""
        filter_dict = build_project_filter("project-123", additional_filters=None)
        assert filter_dict == {"project_id": "project-123"}
