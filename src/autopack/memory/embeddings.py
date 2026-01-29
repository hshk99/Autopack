# autopack/memory/embeddings.py
# Adapted from chatbot_project/backend/embedding_utils.py
"""
Text embedding utilities with OpenAI + local fallback.

Provides:
- sync_embed_text: Synchronous embedding (OpenAI or local)
- async_embed_text: Async wrapper via asyncio.to_thread
- Local deterministic embedding (SHA256-based) when OpenAI unavailable

IMP-PERF-005: Caching added to prevent redundant embedding API calls.
"""

import asyncio
import functools
import hashlib
import logging
import os
import threading
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# OpenAI's context window for text-embedding-3-small is 8191 tokens.
# Safe character limit as heuristic to avoid errors.
MAX_EMBEDDING_CHARS = 30000
EMBEDDING_SIZE = 1536

# IMP-PERF-005: Embedding cache to prevent redundant API calls
# Cache stores (text_hash, model) -> embedding_result
_EMBEDDING_CACHE_MAXSIZE = 1000
_embedding_cache: dict[str, Tuple[float, ...]] = {}
_embedding_cache_lock = threading.Lock()
_embedding_cache_hits = 0
_embedding_cache_misses = 0

# Check for OpenAI availability
_USE_OPENAI = False
_openai_client = None

try:
    from openai import OpenAI

    _USE_OPENAI = os.getenv("USE_OPENAI_EMBEDDINGS", "0") in ("1", "true", "True") and bool(
        os.getenv("OPENAI_API_KEY")
    )
    if _USE_OPENAI:
        try:
            # Short default timeout so we never stall E2E
            _openai_client = OpenAI(timeout=3.0)
        except Exception as e:
            logger.warning(f"OpenAI client init failed, falling back to local embeddings: {e}")
            _USE_OPENAI = False
except ImportError:
    logger.info("openai library not installed; using local embeddings only")


def semantic_embeddings_enabled() -> bool:
    """True when embeddings are backed by OpenAI (semantically meaningful)."""
    return bool(_USE_OPENAI and _openai_client)


def _get_cache_key(text: str, model: str) -> str:
    """Generate a cache key from text and model.

    IMP-PERF-005: Uses SHA256 hash of text to keep cache keys manageable
    while avoiding collisions for different texts.
    """
    text_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return f"{model}:{text_hash}"


def _get_cached_embedding(cache_key: str) -> Optional[Tuple[float, ...]]:
    """Get embedding from cache if it exists.

    IMP-PERF-005: Thread-safe cache lookup.
    """
    global _embedding_cache_hits
    with _embedding_cache_lock:
        if cache_key in _embedding_cache:
            _embedding_cache_hits += 1
            return _embedding_cache[cache_key]
    return None


def _put_cached_embedding(cache_key: str, embedding: List[float]) -> None:
    """Store embedding in cache with LRU-like eviction.

    IMP-PERF-005: Thread-safe cache storage with size limit.
    When cache is full, removes oldest entries (FIFO eviction).
    """
    global _embedding_cache_misses
    with _embedding_cache_lock:
        _embedding_cache_misses += 1

        # Evict oldest entries if cache is full
        if len(_embedding_cache) >= _EMBEDDING_CACHE_MAXSIZE:
            # Remove oldest 10% of entries
            to_remove = max(1, _EMBEDDING_CACHE_MAXSIZE // 10)
            keys_to_remove = list(_embedding_cache.keys())[:to_remove]
            for key in keys_to_remove:
                del _embedding_cache[key]

        # Store as tuple for immutability
        _embedding_cache[cache_key] = tuple(embedding)


def clear_embedding_cache() -> None:
    """Clear the embedding cache.

    IMP-PERF-005: Useful for testing and memory management.
    """
    global _embedding_cache_hits, _embedding_cache_misses
    with _embedding_cache_lock:
        _embedding_cache.clear()
        _embedding_cache_hits = 0
        _embedding_cache_misses = 0


def get_embedding_cache_stats() -> dict:
    """Get embedding cache statistics.

    IMP-PERF-005: Returns cache hit rate and size for monitoring.
    """
    with _embedding_cache_lock:
        total = _embedding_cache_hits + _embedding_cache_misses
        hit_rate = _embedding_cache_hits / total if total > 0 else 0.0
        return {
            "size": len(_embedding_cache),
            "maxsize": _EMBEDDING_CACHE_MAXSIZE,
            "hits": _embedding_cache_hits,
            "misses": _embedding_cache_misses,
            "hit_rate": hit_rate,
        }


def _local_embed(text: str, size: int = EMBEDDING_SIZE) -> List[float]:
    """
    Deterministic, offline-safe embedding using SHA256 hashing.
    Not semantically meaningful; only for tests & indexing structure.
    """
    text = text or ""
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    # Expand deterministically
    vec = []
    seed = int.from_bytes(digest[:8], "big", signed=False)
    for i in range(size):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        vec.append((seed / 0x7FFFFFFF) - 0.5)
    return vec


def _record_embedding_usage(
    response,
    model: str,
    db: Optional[Session],
    run_id: Optional[str],
    phase_id: Optional[str],
) -> None:
    """
    Record embedding API usage to telemetry.

    IMP-TEL-003: Track embedding costs for complete cost attribution.

    Args:
        response: OpenAI embeddings response object
        model: Model name used for embedding
        db: Database session (if None, usage is not recorded)
        run_id: Optional run identifier
        phase_id: Optional phase identifier
    """
    if db is None:
        return

    # Extract total_tokens from response usage
    usage = getattr(response, "usage", None)
    if usage is None:
        logger.debug("No usage data in embedding response; skipping usage recording")
        return

    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None or total_tokens == 0:
        logger.debug("No total_tokens in embedding usage; skipping usage recording")
        return

    try:
        from autopack.service.usage_recording import record_usage_total_only
        from autopack.usage_recorder import EMBEDDING_ROLE

        record_usage_total_only(
            db=db,
            provider="openai",
            model=model,
            role=EMBEDDING_ROLE,
            total_tokens=total_tokens,
            run_id=run_id,
            phase_id=phase_id,
        )
        logger.debug(
            f"[EMBEDDING-USAGE] Recorded {total_tokens} tokens for model={model}, "
            f"run_id={run_id}, phase_id={phase_id}"
        )
    except Exception as e:
        # Don't fail embedding call if usage recording fails
        logger.warning(f"Failed to record embedding usage: {e}")


def sync_embed_text(
    text: str,
    model: str = "text-embedding-3-small",
    db: Optional[Session] = None,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> List[float]:
    """
    Synchronous wrapper for OpenAI embedding with input truncation.

    IMP-PERF-005: Results are cached to prevent redundant embedding API calls.
    Cache lookup is based on (text, model). Usage recording only occurs on
    cache misses when an actual API call is made.

    Args:
        text: Text to embed
        model: OpenAI embedding model (default: text-embedding-3-small)
        db: Optional database session for usage recording
        run_id: Optional run identifier for usage tracking
        phase_id: Optional phase identifier for usage tracking

    Returns:
        List of floats (embedding vector of size EMBEDDING_SIZE)
    """
    if len(text) > MAX_EMBEDDING_CHARS:
        logger.warning(
            f"Input text truncated from {len(text)} to {MAX_EMBEDDING_CHARS} characters for embedding."
        )
        text = text[:MAX_EMBEDDING_CHARS]

    # IMP-PERF-005: Check cache first
    cache_key = _get_cache_key(text, model)
    cached_result = _get_cached_embedding(cache_key)
    if cached_result is not None:
        logger.debug(f"Embedding cache hit for key {cache_key[:20]}...")
        return list(cached_result)

    # Cache miss - compute embedding
    preview = text[:50].replace("\n", " ")
    result: List[float]

    if _USE_OPENAI and _openai_client:
        logger.debug(f"Calling OpenAI embedding for preview: '{preview}...'")
        try:
            response = _openai_client.embeddings.create(
                input=text,
                model=model,
            )
            # Record embedding usage if db session provided (only on API calls)
            _record_embedding_usage(response, model, db, run_id, phase_id)
            result = list(response.data[0].embedding)
        except Exception as e:
            logger.warning(f"OpenAI embedding failed ({e}); falling back to local embedding.")
            result = _local_embed(text)
    else:
        logger.debug(f"Using local offline embedding for preview: '{preview}...'")
        result = _local_embed(text)

    # IMP-PERF-005: Store in cache
    _put_cached_embedding(cache_key, result)

    return result


def sync_embed_texts(
    texts: List[str],
    model: str = "text-embedding-3-small",
    db: Optional[Session] = None,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> List[List[float]]:
    """
    Batch embedding helper.
    - Uses OpenAI embeddings in a single request when enabled.
    - Falls back to local hashing embeddings per item otherwise.

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model (default: text-embedding-3-small)
        db: Optional database session for usage recording
        run_id: Optional run identifier for usage tracking
        phase_id: Optional phase identifier for usage tracking

    Returns:
        List of embedding vectors
    """
    cleaned: List[str] = []
    for t in texts:
        t = t or ""
        if len(t) > MAX_EMBEDDING_CHARS:
            t = t[:MAX_EMBEDDING_CHARS]
        cleaned.append(t)

    if _USE_OPENAI and _openai_client:
        try:
            resp = _openai_client.embeddings.create(input=cleaned, model=model)
            # Record embedding usage if db session provided
            _record_embedding_usage(resp, model, db, run_id, phase_id)
            return [list(item.embedding) for item in resp.data]
        except Exception as e:
            logger.warning(
                f"OpenAI batch embedding failed ({e}); falling back to local embeddings."
            )

    return [_local_embed(t) for t in cleaned]


async def async_embed_text(
    text: str,
    model: str = "text-embedding-3-small",
    db: Optional[Session] = None,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
) -> List[float]:
    """
    Asynchronous wrapper for embedding using asyncio.to_thread.

    Args:
        text: Text to embed
        model: OpenAI embedding model
        db: Optional database session for usage recording
        run_id: Optional run identifier for usage tracking
        phase_id: Optional phase identifier for usage tracking

    Returns:
        List of floats (embedding vector)
    """
    return await asyncio.to_thread(sync_embed_text, text, model, db, run_id, phase_id)
