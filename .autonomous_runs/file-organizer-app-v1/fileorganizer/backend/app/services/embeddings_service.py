"""
Embeddings Service - Generate and store document embeddings
"""
from openai import OpenAI
from app.core.config import settings
import json
import numpy as np


class EmbeddingsService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate embedding vector for text using OpenAI
        """
        if not text or not text.strip():
            raise ValueError("Text is required for embedding generation")

        try:
            # Truncate text if too long (max 8191 tokens for text-embedding-3-small)
            max_length = 8000  # Conservative limit
            truncated_text = text[:max_length]

            response = self.client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=truncated_text
            )

            embedding = response.data[0].embedding
            return embedding

        except Exception as e:
            raise Exception(f"Embedding generation failed: {str(e)}")

    def serialize_embedding(self, embedding: list[float]) -> str:
        """Serialize embedding to JSON string for database storage"""
        return json.dumps(embedding)

    def deserialize_embedding(self, embedding_str: str) -> list[float]:
        """Deserialize embedding from JSON string"""
        return json.loads(embedding_str)

    def cosine_similarity(
        self,
        embedding1: list[float],
        embedding2: list[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings"""
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))
