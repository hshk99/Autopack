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
from typing import List

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


def sync_embed_text(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    Synchronous wrapper for OpenAI embedding with input truncation.

    Args:
        text: Text to embed
        model: OpenAI embedding model (default: text-embedding-3-small)

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
            return list(response.data[0].embedding)
        except Exception as e:
            logger.warning(f"OpenAI embedding failed ({e}); falling back to local embedding.")
            return _local_embed(text)
    else:
        logger.debug(f"Using local offline embedding for preview: '{preview}...'")
        return _local_embed(text)


def sync_embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    """
    Batch embedding helper.
    - Uses OpenAI embeddings in a single request when enabled.
    - Falls back to local hashing embeddings per item otherwise.
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
            return [list(item.embedding) for item in resp.data]
        except Exception as e:
            logger.warning(
                f"OpenAI batch embedding failed ({e}); falling back to local embeddings."
            )

    return [_local_embed(t) for t in cleaned]


async def async_embed_text(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """
    Asynchronous wrapper for embedding using asyncio.to_thread.

    Args:
        text: Text to embed
        model: OpenAI embedding model

    Returns:
        List of floats (embedding vector)
    """
    return await asyncio.to_thread(sync_embed_text, text, model)
