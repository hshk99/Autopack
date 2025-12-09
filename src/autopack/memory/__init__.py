# autopack/memory - Vector memory for context retrieval
#
# This module provides:
# - embeddings.py: Text embedding (OpenAI + local fallback)
# - faiss_store.py: FAISS backend (Qdrant-ready adapter shape)
# - memory_service.py: High-level insert/search for collections
# - maintenance.py: TTL prune + optional compression
# - goal_drift.py: Goal drift detection for pre-apply gating

from .embeddings import sync_embed_text, async_embed_text, EMBEDDING_SIZE, MAX_EMBEDDING_CHARS
from .faiss_store import FaissStore
from .qdrant_store import QdrantStore, QDRANT_AVAILABLE
from .memory_service import MemoryService
from .goal_drift import check_goal_drift, should_block_on_drift, extract_goal_from_description

__all__ = [
    "sync_embed_text",
    "async_embed_text",
    "EMBEDDING_SIZE",
    "MAX_EMBEDDING_CHARS",
    "FaissStore",
    "QdrantStore",
    "QDRANT_AVAILABLE",
    "MemoryService",
    "check_goal_drift",
    "should_block_on_drift",
    "extract_goal_from_description",
]
