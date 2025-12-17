"""Embedding service using all-mpnet-base-v2 model.

Provides text embedding generation using the sentence-transformers library
with the all-mpnet-base-v2 model for high-quality semantic representations.
"""

import logging
from typing import List, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load sentence-transformers to avoid import overhead
_model = None
_model_name = "all-mpnet-base-v2"


def _get_model():
    """Lazy load the sentence-transformers model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {_model_name}")
            _model = SentenceTransformer(_model_name)
            logger.info(f"Embedding model loaded successfully. Dimension: {_model.get_sentence_embedding_dimension()}")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise
    return _model


class EmbeddingService:
    """Service for generating text embeddings using all-mpnet-base-v2.
    
    The all-mpnet-base-v2 model provides:
    - 768-dimensional embeddings
    - Strong performance on semantic similarity tasks
    - Good balance of speed and quality
    
    Example:
        >>> service = EmbeddingService()
        >>> embedding = service.embed_text("Hello world")
        >>> print(embedding.shape)  # (768,)
        >>> 
        >>> embeddings = service.embed_texts(["Hello", "World"])
        >>> print(embeddings.shape)  # (2, 768)
    """
    
    def __init__(self, model_name: str = "all-mpnet-base-v2"):
        """Initialize the embedding service.
        
        Args:
            model_name: Name of the sentence-transformers model to use.
                       Defaults to all-mpnet-base-v2.
        """
        global _model_name
        _model_name = model_name
        self._model_name = model_name
    
    @property
    def model(self):
        """Get the underlying sentence-transformers model."""
        return _get_model()
    
    @property
    def embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model."""
        return self.model.get_sentence_embedding_dimension()
    
    def embed_text(self, text: str, normalize: bool = True) -> np.ndarray:
        """Generate embedding for a single text.
        
        Args:
            text: Input text to embed.
            normalize: Whether to L2-normalize the embedding. Default True.
        
        Returns:
            Numpy array of shape (embedding_dimension,)
        """
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=normalize
        )
        return embedding
    
    def embed_texts(
        self,
        texts: List[str],
        normalize: bool = True,
        batch_size: int = 32,
        show_progress: bool = False
    ) -> np.ndarray:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of input texts to embed.
            normalize: Whether to L2-normalize embeddings. Default True.
            batch_size: Batch size for encoding. Default 32.
            show_progress: Whether to show progress bar. Default False.
        
        Returns:
            Numpy array of shape (len(texts), embedding_dimension)
        """
        if not texts:
            return np.array([])
        
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            batch_size=batch_size,
            show_progress_bar=show_progress
        )
        return embeddings
    
    def similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between two texts.
        
        Args:
            text1: First text.
            text2: Second text.
        
        Returns:
            Cosine similarity score between -1 and 1.
        """
        emb1 = self.embed_text(text1, normalize=True)
        emb2 = self.embed_text(text2, normalize=True)
        return float(np.dot(emb1, emb2))
    
    def batch_similarity(
        self,
        query: str,
        candidates: List[str]
    ) -> List[float]:
        """Compute similarity between a query and multiple candidates.
        
        Args:
            query: Query text.
            candidates: List of candidate texts to compare against.
        
        Returns:
            List of similarity scores for each candidate.
        """
        if not candidates:
            return []
        
        query_emb = self.embed_text(query, normalize=True)
        candidate_embs = self.embed_texts(candidates, normalize=True)
        
        # Compute dot products (equivalent to cosine similarity for normalized vectors)
        similarities = np.dot(candidate_embs, query_emb)
        return similarities.tolist()
