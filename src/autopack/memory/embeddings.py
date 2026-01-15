# autopack/memory/embeddings.py
# Adapted from chatbot_project/backend/embedding_utils.py
"""
Text embedding utilities with OpenAI + local fallback.

Provides:
- sync_embed_text: Synchronous embedding (OpenAI or local)
- async_embed_text: Async wrapper via asyncio.to_thread
- Local deterministic embedding (SHA256-based) when OpenAI unavailable
"""

import os
import asyncio
import hashlib
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# OpenAI's context window for text-embedding-3-small is 8191 tokens.
# Safe character limit as heuristic to avoid errors.
MAX_EMBEDDING_CHARS = 30000
EMBEDDING_SIZE = 1536

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
        from autopack.usage_recorder import EMBEDDING_ROLE
        from autopack.service.usage_recording import record_usage_total_only

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

    preview = text[:50].replace("\n", " ")
    if _USE_OPENAI and _openai_client:
        logger.debug(f"Calling OpenAI embedding for preview: '{preview}...'")
        try:
            response = _openai_client.embeddings.create(
                input=text,
                model=model,
            )
            # Record embedding usage if db session provided
            _record_embedding_usage(response, model, db, run_id, phase_id)
            return list(response.data[0].embedding)
        except Exception as e:
            logger.warning(f"OpenAI embedding failed ({e}); falling back to local embedding.")
            return _local_embed(text)
    else:
        logger.debug(f"Using local offline embedding for preview: '{preview}...'")
        return _local_embed(text)


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
