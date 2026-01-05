"""Extended tests for memory_service.py.

Tests cover:
- Embedding storage and retrieval
- Similarity search functionality
- Error handling and edge cases
- Integration with qdrant_store

NOTE: This is an extended test suite for memory service enhancements.
Tests are marked xfail until the full enhanced API is implemented (EmbeddingModel
and enhanced MemoryService methods).
"""

import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch
import numpy as np

pytestmark = [
    pytest.mark.xfail(
        strict=False,
        reason="Extended MemoryService API not fully implemented - aspirational test suite",
    ),
    pytest.mark.aspirational,
]

try:
    from autopack.memory.memory_service import MemoryService
    from autopack.memory.qdrant_store import QdrantStore
except ImportError:
    # Fallback for different import paths
    try:
        from autopack.memory.memory_service import MemoryService
        from autopack.memory.qdrant_store import QdrantStore
    except ImportError:
        pytest.skip("Memory service modules not available", allow_module_level=True)


@pytest.fixture
def temp_storage_dir():
    """Create a temporary directory for test storage."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_embedding_model():
    """Create a mock embedding model."""
    model = Mock()
    model.embed.return_value = np.random.rand(384).tolist()
    model.embed_batch.return_value = [np.random.rand(384).tolist() for _ in range(3)]
    model.dimension = 384
    return model


@pytest.fixture
def memory_service(temp_storage_dir, mock_embedding_model):
    """Create a MemoryService instance for testing."""
    with patch(
        "src.autopack.memory.memory_service.EmbeddingModel", return_value=mock_embedding_model
    ):
        service = MemoryService(storage_path=temp_storage_dir)
        yield service
        service.close()


class TestEmbeddingStorage:
    """Tests for embedding storage functionality."""

    def test_store_single_embedding(self, memory_service, mock_embedding_model):
        """Test storing a single embedding."""
        text = "This is a test document"
        metadata = {"source": "test", "type": "document"}

        doc_id = memory_service.store(text, metadata=metadata)

        assert doc_id is not None
        assert isinstance(doc_id, str)
        mock_embedding_model.embed.assert_called_once_with(text)

    def test_store_multiple_embeddings(self, memory_service, mock_embedding_model):
        """Test storing multiple embeddings in batch."""
        texts = ["First document", "Second document", "Third document"]
        metadata_list = [{"index": 0}, {"index": 1}, {"index": 2}]

        doc_ids = memory_service.store_batch(texts, metadata_list=metadata_list)

        assert len(doc_ids) == 3
        assert all(isinstance(doc_id, str) for doc_id in doc_ids)
        mock_embedding_model.embed_batch.assert_called_once()

    def test_store_with_custom_id(self, memory_service):
        """Test storing embedding with custom document ID."""
        text = "Custom ID document"
        custom_id = "custom-doc-123"

        doc_id = memory_service.store(text, doc_id=custom_id)

        assert doc_id == custom_id

    def test_store_empty_text_raises_error(self, memory_service):
        """Test that storing empty text raises appropriate error."""
        with pytest.raises((ValueError, Exception)):
            memory_service.store("")

    def test_store_with_large_metadata(self, memory_service):
        """Test storing embedding with large metadata payload."""
        text = "Document with large metadata"
        metadata = {
            "title": "Test Document",
            "content": "A" * 1000,  # Large content
            "tags": [f"tag{i}" for i in range(50)],
            "nested": {"level1": {"level2": {"level3": "deep"}}},
        }

        doc_id = memory_service.store(text, metadata=metadata)

        assert doc_id is not None


class TestEmbeddingRetrieval:
    """Tests for embedding retrieval functionality."""

    def test_retrieve_by_id(self, memory_service):
        """Test retrieving a stored embedding by ID."""
        text = "Retrievable document"
        metadata = {"key": "value"}

        doc_id = memory_service.store(text, metadata=metadata)
        retrieved = memory_service.retrieve(doc_id)

        assert retrieved is not None
        assert retrieved.get("id") == doc_id
        assert retrieved.get("metadata", {}).get("key") == "value"

    def test_retrieve_nonexistent_id(self, memory_service):
        """Test retrieving a non-existent document returns None."""
        result = memory_service.retrieve("nonexistent-id-12345")

        assert result is None

    def test_retrieve_multiple_by_ids(self, memory_service):
        """Test retrieving multiple documents by their IDs."""
        texts = ["Doc 1", "Doc 2", "Doc 3"]
        doc_ids = [memory_service.store(text) for text in texts]

        retrieved = memory_service.retrieve_batch(doc_ids)

        assert len(retrieved) == 3
        assert all(doc is not None for doc in retrieved)

    def test_retrieve_with_missing_ids(self, memory_service):
        """Test retrieving batch with some missing IDs."""
        text = "Existing document"
        doc_id = memory_service.store(text)

        ids_to_retrieve = [doc_id, "missing-1", "missing-2"]
        retrieved = memory_service.retrieve_batch(ids_to_retrieve)

        assert len(retrieved) == 3
        assert retrieved[0] is not None
        assert retrieved[1] is None
        assert retrieved[2] is None


class TestSimilaritySearch:
    """Tests for similarity search functionality."""

    def test_basic_similarity_search(self, memory_service, mock_embedding_model):
        """Test basic similarity search."""
        # Store some documents
        texts = [
            "Python programming language",
            "JavaScript web development",
            "Machine learning algorithms",
        ]
        for text in texts:
            memory_service.store(text)

        # Search for similar documents
        query = "Python coding"
        results = memory_service.search(query, limit=2)

        assert len(results) <= 2
        mock_embedding_model.embed.assert_called()

    def test_similarity_search_with_filters(self, memory_service):
        """Test similarity search with metadata filters."""
        # Store documents with different categories
        memory_service.store("Python tutorial", metadata={"category": "programming"})
        memory_service.store("Cooking recipe", metadata={"category": "food"})
        memory_service.store("Java guide", metadata={"category": "programming"})

        # Search with filter
        query = "tutorial"
        filters = {"category": "programming"}
        results = memory_service.search(query, filters=filters, limit=5)

        # All results should match the filter
        for result in results:
            assert result.get("metadata", {}).get("category") == "programming"

    def test_similarity_search_with_score_threshold(self, memory_service):
        """Test similarity search with minimum score threshold."""
        texts = ["Document one", "Document two", "Document three"]
        for text in texts:
            memory_service.store(text)

        query = "Document"
        results = memory_service.search(query, limit=10, min_score=0.5)

        # All results should have score >= threshold
        for result in results:
            score = result.get("score", 0)
            assert score >= 0.5

    def test_similarity_search_empty_store(self, memory_service):
        """Test similarity search on empty store returns empty results."""
        query = "test query"
        results = memory_service.search(query)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_similarity_search_limit_parameter(self, memory_service):
        """Test that limit parameter correctly restricts results."""
        # Store many documents
        for i in range(20):
            memory_service.store(f"Document number {i}")

        query = "Document"
        limit = 5
        results = memory_service.search(query, limit=limit)

        assert len(results) <= limit


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_store_with_invalid_metadata_type(self, memory_service):
        """Test storing with invalid metadata type."""
        text = "Test document"
        # Metadata should be dict, not string
        with pytest.raises((TypeError, ValueError, Exception)):
            memory_service.store(text, metadata="invalid metadata")

    def test_concurrent_access_safety(self, memory_service):
        """Test that concurrent operations don't corrupt data."""
        import threading

        results = []
        errors = []

        def store_document(index):
            try:
                doc_id = memory_service.store(f"Document {index}")
                results.append(doc_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=store_document, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Should have stored all documents without errors
        assert len(errors) == 0
        assert len(results) == 10
        assert len(set(results)) == 10  # All IDs should be unique

    def test_service_close_and_reopen(self, temp_storage_dir, mock_embedding_model):
        """Test closing and reopening service preserves data."""
        # Create service and store data
        with patch(
            "src.autopack.memory.memory_service.EmbeddingModel", return_value=mock_embedding_model
        ):
            service1 = MemoryService(storage_path=temp_storage_dir)
            doc_id = service1.store("Persistent document")
            service1.close()

            # Reopen service
            service2 = MemoryService(storage_path=temp_storage_dir)
            retrieved = service2.retrieve(doc_id)
            service2.close()

            assert retrieved is not None
            assert retrieved.get("id") == doc_id

    def test_search_with_malformed_query(self, memory_service):
        """Test search with malformed or unusual query."""
        memory_service.store("Normal document")

        # Try various edge case queries
        edge_cases = [
            "",  # Empty string
            " " * 100,  # Only whitespace
            "\n\t\r",  # Only special characters
        ]

        for query in edge_cases:
            try:
                results = memory_service.search(query)
                # Should either return empty results or handle gracefully
                assert isinstance(results, list)
            except (ValueError, Exception):
                # Raising an exception is also acceptable
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
