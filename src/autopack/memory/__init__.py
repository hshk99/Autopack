# autopack/memory - Vector memory for context retrieval
#
# This module provides:
# - embeddings.py: Text embedding (OpenAI + local fallback)
# - faiss_store.py: FAISS backend (Qdrant-ready adapter shape)
# - memory_service.py: High-level insert/search for collections
# - maintenance.py: TTL prune + optional compression
# - goal_drift.py: Goal drift detection for pre-apply gating
# - learning_db.py: Historical learning database for cross-cycle memory

from .embeddings import (
    EMBEDDING_SIZE,
    MAX_EMBEDDING_CHARS,
    async_embed_text,
    clear_embedding_cache,
    get_embedding_cache_stats,
    sync_embed_text,
)
from .faiss_store import FaissStore
from .goal_drift import check_goal_drift, extract_goal_from_description, should_block_on_drift
from .learning_db import LearningDatabase
from .memory_service import MemoryService
from .qdrant_store import QDRANT_AVAILABLE, QdrantStore

__all__ = [
    "sync_embed_text",
    "async_embed_text",
    "EMBEDDING_SIZE",
    "MAX_EMBEDDING_CHARS",
    "clear_embedding_cache",
    "get_embedding_cache_stats",
    "FaissStore",
    "QdrantStore",
    "QDRANT_AVAILABLE",
    "MemoryService",
    "check_goal_drift",
    "should_block_on_drift",
    "extract_goal_from_description",
    "LearningDatabase",
]
