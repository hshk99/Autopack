"""
Test embeddings service
"""
import pytest
from app.services.embeddings_service import EmbeddingsService


def test_embeddings_service_initialization():
    """Test embeddings service can be initialized"""
    service = EmbeddingsService()
    assert service is not None


def test_serialize_deserialize_embedding():
    """Test embedding serialization"""
    service = EmbeddingsService()

    original_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    serialized = service.serialize_embedding(original_embedding)
    deserialized = service.deserialize_embedding(serialized)

    assert deserialized == original_embedding


def test_cosine_similarity():
    """Test cosine similarity calculation"""
    service = EmbeddingsService()

    embedding1 = [1.0, 0.0, 0.0]
    embedding2 = [1.0, 0.0, 0.0]
    embedding3 = [0.0, 1.0, 0.0]

    # Identical vectors should have similarity 1.0
    similarity1 = service.cosine_similarity(embedding1, embedding2)
    assert abs(similarity1 - 1.0) < 0.001

    # Orthogonal vectors should have similarity 0.0
    similarity2 = service.cosine_similarity(embedding1, embedding3)
    assert abs(similarity2 - 0.0) < 0.001
