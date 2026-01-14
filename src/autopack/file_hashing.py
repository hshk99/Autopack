"""File content hashing utilities for cache invalidation.

Provides deterministic content hashing for embedding cache keys.
Includes LRU cache for file hashing to reduce disk I/O.
"""

import hashlib
import os
from functools import lru_cache


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


@lru_cache(maxsize=512)
def compute_file_hash_cached(file_path: str, mtime: float) -> str:
    """Compute file hash with LRU caching.

    Cache uses (path, mtime) as key to auto-invalidate when file is modified.

    Args:
        file_path: Absolute path to file
        mtime: File modification timestamp (from os.path.getmtime)

    Returns:
        SHA256 hex digest of file content

    Note:
        The mtime parameter ensures cache invalidation when file changes.
        When mtime changes, it's a new cache key, so we read from disk.
    """
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def compute_file_hash_with_cache(file_path: str) -> str:
    """Compute file hash with LRU caching.

    Automatically invalidates cache when file modification time changes.
    Expects 60%+ cache hit rate for typical build phases.

    Args:
        file_path: Absolute path to file

    Returns:
        SHA256 hex digest of file content, empty string if file cannot be read

    Raises:
        OSError: If file modification time cannot be obtained
    """
    mtime = os.path.getmtime(file_path)
    return compute_file_hash_cached(file_path, mtime)


def clear_file_hash_cache() -> None:
    """Clear the LRU cache for file hashing.

    Useful for testing or forcing re-computation of file hashes.
    """
    compute_file_hash_cached.cache_clear()
