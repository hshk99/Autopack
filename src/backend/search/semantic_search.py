"""Semantic search engine using embeddings.

Provides semantic search capabilities over document collections
using the EmbeddingService for vector representations.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.backend.search.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result."""
    
    document_id: str
    score: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "document_id": self.document_id,
            "score": self.score,
            "text": self.text,
            "metadata": self.metadata
        }


@dataclass
class Document:
    """A document in the search index."""
    
    id: str
    text: str
    embedding: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticSearchEngine:
    """Semantic search engine using all-mpnet-base-v2 embeddings.
    
    Provides in-memory semantic search over a collection of documents.
    For production use with large collections, consider using a vector
    database like Qdrant, Pinecone, or Milvus.
    
    Example:
        >>> engine = SemanticSearchEngine()
        >>> engine.add_documents([
        ...     {"id": "1", "text": "Python programming tutorial"},
        ...     {"id": "2", "text": "Machine learning basics"},
        ...     {"id": "3", "text": "Web development with JavaScript"}
        ... ])
        >>> results = engine.search("AI and ML", top_k=2)
        >>> for r in results:
        ...     print(f"{r.document_id}: {r.score:.3f}")
    """
    
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        similarity_threshold: float = 0.0
    ):
        """Initialize the search engine.
        
        Args:
            embedding_service: EmbeddingService instance. Creates new one if None.
            similarity_threshold: Minimum similarity score for results. Default 0.0.
        """
        self._embedding_service = embedding_service or EmbeddingService()
        self._similarity_threshold = similarity_threshold
        self._documents: Dict[str, Document] = {}
        self._embeddings_matrix: Optional[np.ndarray] = None
        self._document_ids: List[str] = []
        self._index_dirty = True
    
    @property
    def embedding_service(self) -> EmbeddingService:
        """Get the embedding service."""
        return self._embedding_service
    
    @property
    def document_count(self) -> int:
        """Get the number of indexed documents."""
        return len(self._documents)
    
    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[np.ndarray] = None
    ) -> None:
        """Add a single document to the index.
        
        Args:
            doc_id: Unique document identifier.
            text: Document text content.
            metadata: Optional metadata dictionary.
            embedding: Pre-computed embedding. Computed if None.
        """
        if embedding is None:
            embedding = self._embedding_service.embed_text(text)
        
        self._documents[doc_id] = Document(
            id=doc_id,
            text=text,
            embedding=embedding,
            metadata=metadata or {}
        )
        self._index_dirty = True
    
    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 32,
        show_progress: bool = False
    ) -> int:
        """Add multiple documents to the index.
        
        Args:
            documents: List of document dicts with 'id', 'text', and optional 'metadata'.
            batch_size: Batch size for embedding computation.
            show_progress: Whether to show progress bar.
        
        Returns:
            Number of documents added.
        """
        if not documents:
            return 0
        
        # Extract texts for batch embedding
        texts = [doc["text"] for doc in documents]
        
        # Compute embeddings in batch
        embeddings = self._embedding_service.embed_texts(
            texts,
            batch_size=batch_size,
            show_progress=show_progress
        )
        
        # Add documents with embeddings
        for i, doc in enumerate(documents):
            self._documents[doc["id"]] = Document(
                id=doc["id"],
                text=doc["text"],
                embedding=embeddings[i],
                metadata=doc.get("metadata", {})
            )
        
        self._index_dirty = True
        return len(documents)
    
    def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index.
        
        Args:
            doc_id: Document ID to remove.
        
        Returns:
            True if document was removed, False if not found.
        """
        if doc_id in self._documents:
            del self._documents[doc_id]
            self._index_dirty = True
            return True
        return False
    
    def clear(self) -> None:
        """Clear all documents from the index."""
        self._documents.clear()
        self._embeddings_matrix = None
        self._document_ids = []
        self._index_dirty = True
    
    def _rebuild_index(self) -> None:
        """Rebuild the embeddings matrix for efficient search."""
        if not self._documents:
            self._embeddings_matrix = None
            self._document_ids = []
            self._index_dirty = False
            return
        
        self._document_ids = list(self._documents.keys())
        embeddings = [self._documents[doc_id].embedding for doc_id in self._document_ids]
        self._embeddings_matrix = np.vstack(embeddings)
        self._index_dirty = False
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        threshold: Optional[float] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Search for documents similar to the query.
        
        Args:
            query: Search query text.
            top_k: Maximum number of results to return.
            threshold: Minimum similarity threshold. Uses instance default if None.
            filter_metadata: Optional metadata filter (exact match on all keys).
        
        Returns:
            List of SearchResult objects sorted by descending similarity.
        """
        if not self._documents:
            return []
        
        # Rebuild index if needed
        if self._index_dirty:
            self._rebuild_index()
        
        # Compute query embedding
        query_embedding = self._embedding_service.embed_text(query)
        
        # Compute similarities
        similarities = np.dot(self._embeddings_matrix, query_embedding)
        
        # Apply threshold
        effective_threshold = threshold if threshold is not None else self._similarity_threshold
        
        # Get top-k indices
        if top_k >= len(similarities):
            top_indices = np.argsort(similarities)[::-1]
        else:
            # Use argpartition for efficiency with large collections
            partition_idx = len(similarities) - top_k
            top_indices = np.argpartition(similarities, partition_idx)[partition_idx:]
            top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        
        # Build results
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            
            # Apply threshold filter
            if score < effective_threshold:
                continue
            
            doc_id = self._document_ids[idx]
            doc = self._documents[doc_id]
            
            # Apply metadata filter
            if filter_metadata:
                if not all(
                    doc.metadata.get(k) == v
                    for k, v in filter_metadata.items()
                ):
                    continue
            
            results.append(SearchResult(
                document_id=doc_id,
                score=score,
                text=doc.text,
                metadata=doc.metadata
            ))
            
            if len(results) >= top_k:
                break
        
        return results
    
    def search_by_embedding(
        self,
        embedding: np.ndarray,
        top_k: int = 10,
        threshold: Optional[float] = None
    ) -> List[SearchResult]:
        """Search using a pre-computed embedding.
        
        Args:
            embedding: Query embedding vector.
            top_k: Maximum number of results.
            threshold: Minimum similarity threshold.
        
        Returns:
            List of SearchResult objects.
        """
        if not self._documents:
            return []
        
        if self._index_dirty:
            self._rebuild_index()
        
        # Normalize if needed
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        similarities = np.dot(self._embeddings_matrix, embedding)
        effective_threshold = threshold if threshold is not None else self._similarity_threshold
        
        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score < effective_threshold:
                continue
            
            doc_id = self._document_ids[idx]
            doc = self._documents[doc_id]
            
            results.append(SearchResult(
                document_id=doc_id,
                score=score,
                text=doc.text,
                metadata=doc.metadata
            ))
        
        return results
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID.
        
        Args:
            doc_id: Document ID.
        
        Returns:
            Document object or None if not found.
        """
        return self._documents.get(doc_id)
    
    def get_similar_documents(
        self,
        doc_id: str,
        top_k: int = 10,
        include_self: bool = False
    ) -> List[SearchResult]:
        """Find documents similar to a given document.
        
        Args:
            doc_id: Source document ID.
            top_k: Maximum number of results.
            include_self: Whether to include the source document in results.
        
        Returns:
            List of SearchResult objects.
        """
        doc = self._documents.get(doc_id)
        if doc is None or doc.embedding is None:
            return []
        
        results = self.search_by_embedding(
            doc.embedding,
            top_k=top_k + (0 if include_self else 1)
        )
        
        if not include_self:
            results = [r for r in results if r.document_id != doc_id]
        
        return results[:top_k]
