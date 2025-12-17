"""Tests for semantic search functionality.

Tests the EmbeddingService and SemanticSearchEngine classes.
"""

import pytest
import numpy as np

# Skip all tests if sentence-transformers not installed
pytorch_available = True
try:
    import torch
    from sentence_transformers import SentenceTransformer
except ImportError:
    pytorch_available = False

pytestmark = pytest.mark.skipif(
    not pytorch_available,
    reason="sentence-transformers not installed"
)


class TestEmbeddingService:
    """Tests for EmbeddingService."""
    
    @pytest.fixture
    def service(self):
        """Create embedding service fixture."""
        from src.backend.search.embedding_service import EmbeddingService
        return EmbeddingService()
    
    def test_embed_text_returns_array(self, service):
        """Test that embed_text returns numpy array."""
        embedding = service.embed_text("Hello world")
        assert isinstance(embedding, np.ndarray)
    
    def test_embed_text_dimension(self, service):
        """Test embedding dimension is 768 for all-mpnet-base-v2."""
        embedding = service.embed_text("Test text")
        assert embedding.shape == (768,)
    
    def test_embed_text_normalized(self, service):
        """Test that embeddings are L2 normalized."""
        embedding = service.embed_text("Test text", normalize=True)
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5
    
    def test_embed_texts_batch(self, service):
        """Test batch embedding."""
        texts = ["Hello", "World", "Test"]
        embeddings = service.embed_texts(texts)
        assert embeddings.shape == (3, 768)
    
    def test_embed_texts_empty(self, service):
        """Test empty input returns empty array."""
        embeddings = service.embed_texts([])
        assert len(embeddings) == 0
    
    def test_similarity_same_text(self, service):
        """Test similarity of identical texts is ~1.0."""
        sim = service.similarity("Hello world", "Hello world")
        assert sim > 0.99
    
    def test_similarity_different_texts(self, service):
        """Test similarity of different texts is lower."""
        sim = service.similarity(
            "Python programming language",
            "Cooking recipes for dinner"
        )
        assert sim < 0.5
    
    def test_similarity_semantic(self, service):
        """Test semantic similarity works."""
        # Similar meaning, different words
        sim_similar = service.similarity(
            "The cat sat on the mat",
            "A feline rested on the rug"
        )
        # Completely different topics
        sim_different = service.similarity(
            "The cat sat on the mat",
            "Stock market analysis report"
        )
        assert sim_similar > sim_different
    
    def test_batch_similarity(self, service):
        """Test batch similarity computation."""
        query = "Machine learning"
        candidates = [
            "Deep learning neural networks",
            "Cooking pasta recipes",
            "Artificial intelligence research"
        ]
        scores = service.batch_similarity(query, candidates)
        assert len(scores) == 3
        # ML should be more similar to AI/DL than cooking
        assert scores[0] > scores[1]
        assert scores[2] > scores[1]


class TestSemanticSearchEngine:
    """Tests for SemanticSearchEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create search engine fixture."""
        from src.backend.search.semantic_search import SemanticSearchEngine
        return SemanticSearchEngine()
    
    @pytest.fixture
    def populated_engine(self, engine):
        """Create engine with sample documents."""
        documents = [
            {"id": "1", "text": "Python programming tutorial for beginners"},
            {"id": "2", "text": "Machine learning and artificial intelligence"},
            {"id": "3", "text": "Web development with JavaScript and React"},
            {"id": "4", "text": "Data science with Python and pandas"},
            {"id": "5", "text": "Cooking recipes for Italian pasta dishes"},
        ]
        engine.add_documents(documents)
        return engine
    
    def test_add_document(self, engine):
        """Test adding a single document."""
        engine.add_document("test", "Test document")
        assert engine.document_count == 1
    
    def test_add_documents_batch(self, engine):
        """Test adding multiple documents."""
        docs = [
            {"id": "1", "text": "First document"},
            {"id": "2", "text": "Second document"},
        ]
        count = engine.add_documents(docs)
        assert count == 2
        assert engine.document_count == 2
    
    def test_remove_document(self, populated_engine):
        """Test removing a document."""
        initial_count = populated_engine.document_count
        removed = populated_engine.remove_document("1")
        assert removed is True
        assert populated_engine.document_count == initial_count - 1
    
    def test_remove_nonexistent(self, engine):
        """Test removing nonexistent document returns False."""
        removed = engine.remove_document("nonexistent")
        assert removed is False
    
    def test_clear(self, populated_engine):
        """Test clearing all documents."""
        populated_engine.clear()
        assert populated_engine.document_count == 0
    
    def test_search_returns_results(self, populated_engine):
        """Test search returns results."""
        results = populated_engine.search("Python programming")
        assert len(results) > 0
    
    def test_search_relevance(self, populated_engine):
        """Test search returns relevant results first."""
        results = populated_engine.search("Python programming", top_k=3)
        # Python-related docs should rank higher than cooking
        doc_ids = [r.document_id for r in results]
        assert "5" not in doc_ids[:2]  # Cooking should not be in top 2
    
    def test_search_top_k(self, populated_engine):
        """Test top_k limits results."""
        results = populated_engine.search("programming", top_k=2)
        assert len(results) <= 2
    
    def test_search_threshold(self, populated_engine):
        """Test threshold filters low-scoring results."""
        results = populated_engine.search(
            "quantum physics",
            threshold=0.9  # Very high threshold
        )
        # Should return few or no results for unrelated query
        assert len(results) == 0 or all(r.score >= 0.9 for r in results)
    
    def test_search_empty_index(self, engine):
        """Test search on empty index returns empty list."""
        results = engine.search("test query")
        assert results == []
    
    def test_search_result_structure(self, populated_engine):
        """Test search result has correct structure."""
        results = populated_engine.search("Python", top_k=1)
        assert len(results) == 1
        result = results[0]
        assert hasattr(result, "document_id")
        assert hasattr(result, "score")
        assert hasattr(result, "text")
        assert hasattr(result, "metadata")
    
    def test_search_with_metadata(self, engine):
        """Test search with metadata filter."""
        engine.add_document(
            "1", "Python tutorial",
            metadata={"category": "programming", "level": "beginner"}
        )
        engine.add_document(
            "2", "Python advanced",
            metadata={"category": "programming", "level": "advanced"}
        )
        engine.add_document(
            "3", "Cooking basics",
            metadata={"category": "cooking", "level": "beginner"}
        )
        
        # Filter by category
        results = engine.search(
            "tutorial",
            filter_metadata={"category": "programming"}
        )
        for r in results:
            assert r.metadata.get("category") == "programming"
    
    def test_get_document(self, populated_engine):
        """Test retrieving document by ID."""
        doc = populated_engine.get_document("1")
        assert doc is not None
        assert doc.id == "1"
    
    def test_get_document_not_found(self, engine):
        """Test retrieving nonexistent document returns None."""
        doc = engine.get_document("nonexistent")
        assert doc is None
    
    def test_get_similar_documents(self, populated_engine):
        """Test finding similar documents."""
        # Doc 1 is Python tutorial, should be similar to doc 4 (Python data science)
        results = populated_engine.get_similar_documents("1", top_k=2)
        assert len(results) > 0
        # Should not include the source document
        assert all(r.document_id != "1" for r in results)
    
    def test_search_result_to_dict(self, populated_engine):
        """Test SearchResult.to_dict() method."""
        results = populated_engine.search("Python", top_k=1)
        result_dict = results[0].to_dict()
        assert "document_id" in result_dict
        assert "score" in result_dict
        assert "text" in result_dict
        assert "metadata" in result_dict
    
    def test_embedding_dimension_property(self, engine):
        """Test embedding_service property access."""
        dim = engine.embedding_service.embedding_dimension
        assert dim == 768
