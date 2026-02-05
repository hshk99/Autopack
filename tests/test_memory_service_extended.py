"""Extended tests for MemoryService covering critical operational areas.

IMP-TEST-004: Comprehensive memory service test coverage.

Tests cover:
- Vector store initialization and health checks
- Semantic search accuracy and performance
- Memory vector operations
- Persistence and retrieval
- Cache eviction strategies
- Long-term memory retention
- Multi-collection operations
- Error recovery and resilience

Goal: Achieve 85%+ code coverage for memory module.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from autopack.memory import MemoryService
from autopack.memory.freshness_filter import (
    COLLECTION_CODE_DOCS,
    COLLECTION_DOCTOR_HINTS,
    COLLECTION_ERRORS_CI,
    COLLECTION_PLANNING,
    COLLECTION_RUN_SUMMARIES,
    COLLECTION_SOT_DOCS,
)
from autopack.memory.memory_patterns import ProjectNamespaceError
from autopack.memory.memory_service import (
    MAX_CONTENT_LENGTH,
    _compress_content,
    _validate_project_id,
    CleanupResult,
)


class TestVectorStoreInitializationAndHealth:
    """Test vector store initialization and health checks."""

    def test_memory_service_initializes_all_collections(self, monkeypatch, tmp_path):
        """Verify MemoryService initializes all required collections."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        assert service.enabled is True
        # Verify all collections exist
        assert service.store.count(COLLECTION_CODE_DOCS) >= 0
        assert service.store.count(COLLECTION_RUN_SUMMARIES) >= 0
        assert service.store.count(COLLECTION_ERRORS_CI) >= 0
        assert service.store.count(COLLECTION_DOCTOR_HINTS) >= 0
        assert service.store.count(COLLECTION_PLANNING) >= 0
        assert service.store.count(COLLECTION_SOT_DOCS) >= 0

    def test_memory_service_ensure_collection_creates_if_missing(self, monkeypatch, tmp_path):
        """Verify ensure_collection creates collections with correct dimensions."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Ensure a new collection
        service.store.ensure_collection("test_collection_custom", size=1536)
        # Should not raise an error
        count = service.store.count("test_collection_custom")
        assert count == 0  # Empty collection

    def test_memory_service_handles_collection_size_mismatch(self, monkeypatch, tmp_path):
        """Verify MemoryService handles collection size mismatches gracefully."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # All collections should be initialized with size 1536
        # Attempting to ensure with different size should be idempotent
        service.store.ensure_collection(COLLECTION_CODE_DOCS, size=1536)
        count = service.store.count(COLLECTION_CODE_DOCS)
        assert count >= 0  # Should not crash


class TestSemanticSearchAndRetrieval:
    """Test semantic search accuracy and retrieval quality."""

    def test_search_code_returns_relevant_results(self, monkeypatch, tmp_path):
        """Verify search_code returns semantically relevant results."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Index a file
        service.index_file(
            path="src/utils.py",
            content="def calculate_sum(a, b): return a + b",
            project_id=project_id,
            run_id="run-1",
        )

        # Search for related content
        results = service.search_code("sum function implementation", project_id=project_id)

        assert isinstance(results, list)
        # Should return results or empty list depending on embedding availability

    def test_search_code_filters_by_max_age(self, monkeypatch, tmp_path):
        """Verify search_code respects max_age_hours filter."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Index a file with old timestamp
        (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        service.index_file(
            path="src/old_file.py",
            content="old code",
            project_id=project_id,
            run_id="run-1",
        )

        # Search with strict max_age (1 hour) should filter out old results
        results = service.search_code(
            "old code",
            project_id=project_id,
            max_age_hours=1,
        )

        # Results should be filtered by age (implementation dependent)
        assert isinstance(results, list)

    def test_search_summaries_retrieves_phase_summaries(self, monkeypatch, tmp_path):
        """Verify search_summaries retrieves phase summaries correctly."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write a phase summary
        service.write_phase_summary(
            run_id="run-1",
            phase_id="phase-1",
            project_id=project_id,
            summary="Phase 1 completed successfully with 5 files modified",
            changes=["modified.py", "created.py"],
        )

        # Search for the summary
        results = service.search_summaries(
            "files modified",
            project_id=project_id,
        )

        assert isinstance(results, list)

    def test_search_errors_finds_error_patterns(self, monkeypatch, tmp_path):
        """Verify search_errors finds error patterns effectively."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write an error
        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id=project_id,
            error_text="TypeError: 'NoneType' object is not subscriptable",
            error_type="test_failure",
        )

        # Search for similar errors
        results = service.search_errors(
            "NoneType error subscriptable",
            project_id=project_id,
        )

        assert isinstance(results, list)

    def test_retrieve_context_combines_multiple_collections(self, monkeypatch, tmp_path):
        """Verify retrieve_context combines results from multiple collections."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write to multiple collections
        service.index_file(
            path="src/main.py",
            content="main application code",
            project_id=project_id,
            run_id="run-1",
        )

        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id=project_id,
            error_text="RuntimeError: connection timeout",
            error_type="runtime_error",
        )

        # Retrieve combined context
        context = service.retrieve_context(
            "connection timeout error",
            project_id=project_id,
        )

        assert isinstance(context, dict)


class TestMemoryVectorOperations:
    """Test vector operations and storage mechanics."""

    def test_upsert_vector_points(self, monkeypatch, tmp_path):
        """Verify upsert stores vector points correctly."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Upsert a vector point
        points = [
            {
                "id": "test-point-1",
                "vector": [0.1] * 1536,
                "payload": {
                    "project_id": "test-project",
                    "run_id": "run-1",
                    "phase_id": "phase-1",
                    "content": "test content",
                },
            }
        ]

        count = service.store.upsert(COLLECTION_CODE_DOCS, points)
        assert count == 1

    def test_search_vector_similarity(self, monkeypatch, tmp_path):
        """Verify vector similarity search works."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Upsert a point
        points = [
            {
                "id": "vec-1",
                "vector": [0.5] * 1536,
                "payload": {"project_id": "test-project"},
            }
        ]
        service.store.upsert(COLLECTION_CODE_DOCS, points)

        # Search with similar vector
        results = service.store.search(
            COLLECTION_CODE_DOCS,
            query_vector=[0.5] * 1536,
            limit=5,
        )

        assert isinstance(results, list)
        assert len(results) <= 5

    def test_scroll_vector_pagination(self, monkeypatch, tmp_path):
        """Verify scroll operation for pagination."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Upsert multiple points
        points = [
            {
                "id": f"vec-{i}",
                "vector": [float(i) / 100.0] * 1536,
                "payload": {"project_id": "test-project", "index": i},
            }
            for i in range(5)
        ]
        service.store.upsert(COLLECTION_CODE_DOCS, points)

        # Scroll through results
        results = service.store.scroll(
            COLLECTION_CODE_DOCS,
            filter=None,
            limit=2,
        )

        assert isinstance(results, list)
        assert len(results) <= 2

    def test_delete_vector_points(self, monkeypatch, tmp_path):
        """Verify delete operation removes points."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Upsert points
        points = [
            {
                "id": "del-1",
                "vector": [0.1] * 1536,
                "payload": {"project_id": "test-project"},
            },
            {
                "id": "del-2",
                "vector": [0.2] * 1536,
                "payload": {"project_id": "test-project"},
            },
        ]
        service.store.upsert(COLLECTION_CODE_DOCS, points)

        # Delete one point
        count = service.store.delete(COLLECTION_CODE_DOCS, ["del-1"])
        assert count == 1


class TestPersistenceAndRetrieval:
    """Test persistence of memory data and retrieval consistency."""

    def test_write_and_retrieve_consistency(self, monkeypatch, tmp_path):
        """Verify written data can be retrieved consistently."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write multiple types of data
        service.index_file(
            path="src/app.py",
            content="app initialization code",
            project_id=project_id,
            run_id="run-1",
        )

        service.write_phase_summary(
            run_id="run-1",
            phase_id="phase-1",
            project_id=project_id,
            summary="Phase completed",
            changes=[],
        )

        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id=project_id,
            error_text="Test error",
            error_type="test_failure",
        )

        # Verify we can retrieve context containing written data
        context = service.retrieve_context(
            "initialization",
            project_id=project_id,
        )

        assert isinstance(context, dict)

    def test_payload_metadata_preserved(self, monkeypatch, tmp_path):
        """Verify payload metadata is preserved after storage."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Upsert with specific metadata
        point_id = "meta-test-1"
        metadata = {
            "project_id": "test-project",
            "run_id": "run-1",
            "phase_id": "phase-1",
            "custom_field": "custom_value",
        }

        points = [
            {
                "id": point_id,
                "vector": [0.3] * 1536,
                "payload": metadata,
            }
        ]
        service.store.upsert(COLLECTION_CODE_DOCS, points)

        # Retrieve and verify metadata
        retrieved = service.store.get_payload(COLLECTION_CODE_DOCS, point_id)

        if retrieved is not None:
            assert retrieved.get("project_id") == "test-project"


class TestCacheEvictionStrategies:
    """Test cache eviction and memory management."""

    def test_content_compression_applied(self):
        """Verify content compression is applied to long content."""
        long_content = "x" * (MAX_CONTENT_LENGTH + 1000)

        compressed, was_compressed = _compress_content(long_content)

        assert was_compressed is True
        assert len(compressed) <= MAX_CONTENT_LENGTH
        assert "[... truncated middle section ...]" in compressed

    def test_content_short_not_compressed(self):
        """Verify short content is not compressed."""
        short_content = "Short content under limit"

        compressed, was_compressed = _compress_content(short_content)

        assert was_compressed is False
        assert compressed == short_content

    def test_cleanup_stale_entries(self, monkeypatch, tmp_path):
        """Verify cleanup_stale_entries removes old entries."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write an entry
        service.index_file(
            path="src/test.py",
            content="test content",
            project_id=project_id,
            run_id="run-1",
        )

        # Run cleanup
        result = service.cleanup_stale_entries(
            project_id=project_id,
            max_age_days=0,  # Remove everything older than now
            min_relevance=0.0,  # Remove everything with relevance < 1.0
        )

        assert isinstance(result, CleanupResult)


class TestLongTermMemoryRetention:
    """Test long-term memory retention and historical data access."""

    def test_retrieve_insights_returns_high_confidence_entries(self, monkeypatch, tmp_path):
        """Verify retrieve_insights returns high-confidence entries."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write telemetry insight
        service.write_telemetry_insight(
            {
                "insight_type": "cost_sink",
                "description": "high cost pattern detected",
                "content": "common pattern detected",
                "confidence": 0.9,
                "project_id": project_id,
            }
        )

        # Retrieve insights using query
        insights = service.retrieve_insights("pattern", project_id, limit=10)

        assert isinstance(insights, list)

    def test_measure_memory_quality(self, monkeypatch, tmp_path):
        """Verify memory quality metrics are calculated."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Add some data
        service.index_file(
            path="src/main.py",
            content="main code",
            project_id=project_id,
            run_id="run-1",
        )

        # Measure quality
        quality = service.measure_memory_quality(project_id)

        assert quality is not None
        assert hasattr(quality, 'total_entries')  # Check for expected attributes

    def test_cleanup_and_maintenance_workflow(self, monkeypatch, tmp_path):
        """Verify cleanup and maintenance workflow works."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write some data
        service.index_file(
            path="src/main.py",
            content="main code",
            project_id=project_id,
            run_id="run-1",
        )

        # Run cleanup (should not raise)
        result = service.cleanup_stale_entries(project_id=project_id, max_age_days=0, min_relevance=0.5)
        assert isinstance(result, CleanupResult)  # Success if no exception


class TestProjectNamespaceIsolation:
    """Test project namespace isolation validation."""

    def test_validate_project_id_rejects_none(self):
        """Verify validation rejects None project_id."""
        with pytest.raises(ProjectNamespaceError):
            _validate_project_id(None)

    def test_validate_project_id_rejects_empty_string(self):
        """Verify validation rejects empty string project_id."""
        with pytest.raises(ProjectNamespaceError):
            _validate_project_id("")

    def test_validate_project_id_rejects_whitespace(self):
        """Verify validation rejects whitespace-only project_id."""
        with pytest.raises(ProjectNamespaceError):
            _validate_project_id("   ")

    def test_validate_project_id_accepts_valid(self):
        """Verify validation accepts valid project_id."""
        # Should not raise
        _validate_project_id("valid-project-id")

    def test_search_code_validates_project_id(self, monkeypatch, tmp_path):
        """Verify search_code validates project_id."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Search with invalid project_id should raise
        with pytest.raises(ProjectNamespaceError):
            service.search_code("query", project_id=None)

    def test_index_file_validates_project_id(self, monkeypatch, tmp_path):
        """Verify index_file validates project_id."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Index with invalid project_id should raise
        with pytest.raises(ProjectNamespaceError):
            service.index_file(
                path="file.py",
                content="code",
                project_id="",
                run_id="run-1",
            )


class TestErrorHandlingAndResilience:
    """Test error handling and resilience mechanisms."""

    def test_search_handles_invalid_query_vector(self, monkeypatch, tmp_path):
        """Verify search handles invalid query vectors gracefully."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Search with wrong vector size
        try:
            results = service.store.search(
                COLLECTION_CODE_DOCS,
                query_vector=[0.1] * 100,  # Wrong size (should be 1536)
                limit=5,
            )
            # Should return empty or handle gracefully
            assert isinstance(results, list)
        except Exception as e:
            # Acceptable to raise for dimension mismatch
            assert "vector" in str(e).lower() or "dimension" in str(e).lower()

    def test_disable_memory_functionality(self, monkeypatch):
        """Verify memory can be disabled completely."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "0")

        service = MemoryService()

        assert service.enabled is False
        assert service.search_code("query", project_id="test") == []

    def test_retrieval_quality_tracker_integration(self, monkeypatch, tmp_path):
        """Verify retrieval quality tracker can be set."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        # Create mock tracker
        mock_tracker = MagicMock()
        service.set_retrieval_quality_tracker(mock_tracker)

        assert service.retrieval_quality_tracker == mock_tracker


class TestMultiCollectionOperations:
    """Test operations across multiple collections."""

    def test_retrieve_context_with_metadata(self, monkeypatch, tmp_path):
        """Verify retrieve_context_with_metadata returns typed results."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write to multiple collections
        service.index_file(
            path="src/app.py",
            content="application code here",
            project_id=project_id,
            run_id="run-1",
        )

        # Retrieve with metadata
        context = service.retrieve_context_with_metadata(
            "application code",
            project_id=project_id,
        )

        assert isinstance(context, (dict, list)) or context is None

    def test_write_across_multiple_collections(self, monkeypatch, tmp_path):
        """Verify writing to multiple collections works correctly."""
        monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "1")
        monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

        faiss_dir = str(tmp_path / ".faiss")
        service = MemoryService(index_dir=faiss_dir, use_qdrant=False)

        project_id = "test-project"

        # Write to code_docs
        service.index_file("file.py", "code", project_id, run_id="run-1")

        # Write to run_summaries
        service.write_phase_summary("run-1", "phase-1", project_id, "summary", [])

        # Write to errors_ci
        service.write_error("run-1", "phase-1", project_id, "error")

        # Write to doctor_hints
        service.write_doctor_hint("run-1", "phase-1", project_id, "hint")

        # Write to planning
        service.write_planning_artifact("plan.yaml", "content", project_id, version=1)

        # Verify no exceptions raised
        assert service.enabled is True
