"""File content hashing utilities for cache invalidation.

Provides deterministic content hashing for embedding cache keys.
"""

import hashlib


def compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of file content for cache keying.
    
    Args:
        content: File content string
        
    Returns:
        Hex digest of SHA256 hash
    """
    if not isinstance(content, str):
        content = str(content)
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def compute_cache_key(path: str, content: str, model: str = "text-embedding-3-small") -> str:
    """Compute cache key for embedding lookup.
    
    Args:
        path: File path
        content: File content
        model: Embedding model name
        
    Returns:
        Cache key string in format: path|hash|model
    """
    content_hash = compute_content_hash(content)
    return f"{path}|{content_hash}|{model}"
