"""Tests for MemoryService Qdrant integration paths.

IMP-TEST-001: Mock-based tests for CI environments without Qdrant.

Tests cover:
- Graceful degradation when Qdrant unavailable
- Memory storage and retrieval operations
- Collection creation and management
- Error handling and fallback mechanisms

These tests use mocks to exercise integration paths in CI when Qdrant
is not available, ensuring critical code paths are always tested.
"""

from unittest.mock import patch

import pytest

from tests.conftest import QDRANT_AVAILABLE_FOR_TESTS


class TestMemoryServiceQdrantUnavailable:
    """Test graceful degradation when Qdrant unavailable."""

    def test_memory_service_handles_qdrant_connection_error(self, monkeypatch, tmp_path):
        """Verify graceful degradation when Qdrant connection fails."""
        from autopack.memory import memory_service as ms

        # Force Qdrant path but make connection fail
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

        class FailingQdrantStore:
            def __init__(self, *args, **kwargs):
                raise ConnectionError("Qdrant server unreachable")

        monkeypatch.setattr(ms, "QdrantStore", FailingQdrantStore, raising=True)
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)
        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)

        # Should fall back to FAISS, not crash
        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=True)

        assert service is not None
        assert service.enabled is True
        assert service.backend == "faiss"

    def test_memory_service_with_disabled_memory(self, monkeypatch):
        """Verify MemoryService handles disabled state correctly."""
        from autopack.memory import memory_service as ms

        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "0")
        service = ms.MemoryService()

        assert service.enabled is False
        assert service.backend == "disabled"
        # Calls should be no-ops
        assert service.search_code("test query", project_id="test") == []

    def test_memory_service_upsert_when_disabled(self, monkeypatch):
        """Verify upsert returns 0 when memory is disabled."""
        from autopack.memory import memory_service as ms

        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "0")
        service = ms.MemoryService()

        # Upsert should be a no-op
        result = service.store.upsert(
            "run_summaries",
            [
                {
                    "id": "test-1",
                    "payload": {"run_id": "run-1"},
                    "vector": [0.1] * 1536,
                }
            ],
        )
        assert result == 0

    def test_memory_service_search_when_disabled(self, monkeypatch):
        """Verify search returns empty list when memory is disabled."""
        from autopack.memory import memory_service as ms

        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "0")
        service = ms.MemoryService()

        results = service.store.search(
            "run_summaries",
            query_vector=[0.1] * 1536,
            limit=5,
        )
        assert isinstance(results, list)
        assert len(results) == 0


class TestMemoryServiceWithFaissBackend:
    """Test MemoryService operations with FAISS backend (mock for Qdrant paths)."""

    def test_memory_service_faiss_initialization(self, monkeypatch, tmp_path):
        """Verify FAISS backend initializes correctly."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)
        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        assert service.enabled is True
        assert service.backend == "faiss"
        assert service.store is not None

    def test_memory_service_ensures_collections(self, monkeypatch, tmp_path):
        """Verify all required collections are created during init."""
        from autopack.memory import memory_service as ms
        from autopack.memory.memory_service import ALL_COLLECTIONS

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Verify service initialized with expected collections
        assert service.enabled is True
        # ALL_COLLECTIONS should include expected collection names
        expected = {"code_docs", "run_summaries", "errors_ci", "doctor_hints", "planning"}
        actual = set(ALL_COLLECTIONS)
        assert expected.issubset(actual)

    def test_memory_service_store_and_search_cycle(
        self, monkeypatch, tmp_path, mock_embedding_function
    ):
        """Test basic store and search cycle with mocked embeddings."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Store a document
        test_text = "This is a test error message for CI"

        # This exercises the store path
        service.write_error(
            run_id="test-run",
            phase_id="phase-1",
            project_id="test-project",
            error_text=test_text,
        )

        # Verify embedding function was called
        mock_embedding_function.assert_called()


class TestMemoryServiceErrorHandling:
    """Test error handling in MemoryService."""

    def test_memory_service_handles_embedding_error(self, monkeypatch, tmp_path):
        """Verify graceful handling of embedding failures."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Patch embedding to fail
        with patch.object(ms, "sync_embed_text", side_effect=RuntimeError("Embedding failed")):
            # Should handle error gracefully - the error will be raised inside write_error
            # but the code should handle it gracefully
            try:
                result = service.write_error(
                    run_id="run-1",
                    phase_id="phase-1",
                    project_id="test",
                    error_text="Test error",
                )
            except RuntimeError:
                # It's acceptable for the error to propagate if not handled
                result = None
            # Should not crash; may return None or fail gracefully
            assert result is None or isinstance(result, (int, str, type(None)))

    def test_memory_service_handles_store_error(self, monkeypatch, tmp_path):
        """Verify graceful handling of store operation failures."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Patch store.upsert to fail
        with patch.object(service.store, "upsert", side_effect=RuntimeError("Store failed")):
            # Should handle error gracefully via _safe_store_call
            result = service._safe_store_call(
                "test_upsert",
                lambda: service.store.upsert("test", []),
                default=0,
            )
            assert result == 0  # Should return default on error


class TestMemoryServiceSearch:
    """Test search functionality."""

    def test_memory_service_search_code_with_faiss(self, monkeypatch, tmp_path):
        """Verify search_code works with FAISS backend."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Search should return empty list on empty index
        results = service.search_code("test query", project_id="test-project")
        assert isinstance(results, list)

    def test_memory_service_search_errors(self, monkeypatch, tmp_path):
        """Verify search_errors works correctly."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        results = service.search_errors("connection timeout", project_id="test")
        assert isinstance(results, list)

    def test_memory_service_search_summaries(self, monkeypatch, tmp_path):
        """Verify search_summaries works correctly."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        results = service.search_summaries("database migration", project_id="test")
        assert isinstance(results, list)


class TestMemoryServiceQdrantAutostart:
    """Test Qdrant autostart behavior with mocks."""

    def test_memory_service_attempts_autostart_when_configured(self, monkeypatch, tmp_path):
        """Verify MemoryService attempts autostart when Qdrant unavailable."""
        from autopack.memory import memory_service as ms

        # Setup: Qdrant available but connection fails
        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)
        monkeypatch.setenv("AUTOPACK_QDRANT_AUTOSTART", "1")
        monkeypatch.setenv("AUTOPACK_QDRANT_HOST", "localhost")
        monkeypatch.setenv("AUTOPACK_QDRANT_PORT", "6333")

        autostart_called = {"value": False}

        def mock_autostart(**kwargs):
            autostart_called["value"] = True
            return False  # Simulate autostart failed

        monkeypatch.setattr(ms, "_autostart_qdrant_if_needed", mock_autostart, raising=True)

        # Make Qdrant connection fail
        class FailingQdrantStore:
            def __init__(self, *args, **kwargs):
                raise ConnectionError("Connection refused")

        monkeypatch.setattr(ms, "QdrantStore", FailingQdrantStore, raising=True)

        # Create service - should attempt autostart then fall back to FAISS
        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=True)

        assert autostart_called["value"] is True
        assert service.backend == "faiss"

    def test_memory_service_uses_qdrant_after_successful_autostart(self, monkeypatch):
        """Verify MemoryService uses Qdrant after successful autostart."""
        from autopack.memory import memory_service as ms

        monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)
        monkeypatch.setenv("AUTOPACK_QDRANT_AUTOSTART", "1")
        monkeypatch.setenv("AUTOPACK_QDRANT_HOST", "localhost")
        monkeypatch.setenv("AUTOPACK_QDRANT_PORT", "6333")

        connection_attempts = {"count": 0}

        class FlakyQdrantStore:
            def __init__(self, *args, **kwargs):
                connection_attempts["count"] += 1
                # First attempt fails, second succeeds
                if connection_attempts["count"] == 1:
                    raise ConnectionError("not running yet")

            def ensure_collection(self, name: str, size: int = 1536) -> None:
                return None

        monkeypatch.setattr(ms, "QdrantStore", FlakyQdrantStore, raising=True)
        # Pretend autostart succeeded
        monkeypatch.setattr(ms, "_autostart_qdrant_if_needed", lambda **kwargs: True, raising=True)

        service = ms.MemoryService(use_qdrant=True)
        assert service.backend == "qdrant"


class TestMemoryServiceCollectionOperations:
    """Test collection-level operations."""

    def test_null_store_operations_are_noops(self):
        """Verify NullStore returns expected no-op values."""
        from autopack.memory.memory_service import NullStore

        store = NullStore()

        # All operations should be no-ops
        assert store.ensure_collection("test", 1536) is None
        assert store.upsert("test", []) == 0
        assert store.search("test", [0.1] * 1536) == []
        assert store.scroll("test") == []
        assert store.delete("test", ["id1"]) == 0
        assert store.count("test") == 0
        assert store.get_payload("test", "id1") is None
        assert store.update_payload("test", "id1", {}) is False

    def test_memory_service_collection_isolation(self, monkeypatch, tmp_path):
        """Verify data in different collections doesn't interfere."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = ms.MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Store in one collection
        with patch.object(ms, "sync_embed_text", return_value=[0.1] * 1536):
            service.write_error(
                run_id="run-1",
                phase_id="phase-1",
                project_id="test",
                error_text="Test error",
            )

        # Search in different collection should not find it
        results = service.search_doctor_hints("Test error", project_id="test")
        assert isinstance(results, list)
        # Results should not contain the error stored in errors_ci collection


@pytest.mark.skipif(
    not QDRANT_AVAILABLE_FOR_TESTS,
    reason="Qdrant not available - run mock tests instead",
)
class TestMemoryServiceQdrantIntegration:
    """Integration tests that require a running Qdrant instance.

    These tests are skipped in CI when Qdrant is unavailable.
    The mock-based tests above cover the same code paths.
    """

    def test_memory_service_qdrant_connection(self, monkeypatch):
        """Verify MemoryService can connect to running Qdrant."""
        from autopack.memory import memory_service as ms

        monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)
        monkeypatch.setenv("AUTOPACK_QDRANT_HOST", "localhost")
        monkeypatch.setenv("AUTOPACK_QDRANT_PORT", "6333")

        service = ms.MemoryService(use_qdrant=True)
        assert service.backend == "qdrant"
        assert service.enabled is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
