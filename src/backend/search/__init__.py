"""Semantic search module.

Provides semantic search capabilities with confidence scoring.
"""
from src.backend.search.semantic_search import (
    SemanticSearchEngine,
    SearchResult,
)

__all__ = [
    "SemanticSearchEngine",
    "SearchResult",
]
