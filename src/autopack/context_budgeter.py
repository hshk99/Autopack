"""Context budgeter: select a subset of files for LLM context under a token/char budget.

Supports:
- Deliverables pinning (always include deliverable files when present)
- Semantic relevance ranking (OpenAI embeddings) when available
- Lexical relevance fallback (keywords + path signals) when embeddings are offline
- Local embedding cache with per-phase call cap
- Cross-phase cache persistence for cost optimization
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from autopack.config import settings
from autopack.file_hashing import compute_cache_key
from autopack.memory.embeddings import semantic_embeddings_enabled, sync_embed_texts

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from autopack.telemetry.cost_tracker import ContextPrepTracker

# Thread safety lock for embedding cache access
_CACHE_LOCK = threading.Lock()

# Local embedding cache: {cache_key: embedding_vector}
_EMBEDDING_CACHE: Dict[str, List[float]] = {}

# Per-phase call counter (reset via reset_embedding_cache)
_PHASE_CALL_COUNT: int = 0

# Cross-phase cache persistence (default True for cost optimization)
_PERSIST_CACHE: bool = True


def reset_embedding_cache() -> None:
    """Reset embedding cache and call counter.

    Should be called at the start of each phase to enforce per-phase limits.
    If cross-phase cache persistence is enabled, only the call counter is reset.
    """
    global _EMBEDDING_CACHE, _PHASE_CALL_COUNT
    with _CACHE_LOCK:
        if not _PERSIST_CACHE:
            cache_size = len(_EMBEDDING_CACHE)
            _EMBEDDING_CACHE.clear()
            logger.debug(f"Reset embedding cache (cleared {cache_size} entries)")
        else:
            cache_size = len(_EMBEDDING_CACHE)
            logger.debug(
                f"Phase start: preserving cache with {cache_size} entries (cross-phase persistence enabled)"
            )
        _PHASE_CALL_COUNT = 0


def get_embedding_stats() -> Dict[str, int]:
    """Get current embedding cache statistics.

    Returns:
        Dict with cache_size, call_count, and persist_cache
    """
    with _CACHE_LOCK:
        return {
            "cache_size": len(_EMBEDDING_CACHE),
            "call_count": _PHASE_CALL_COUNT,
            "persist_cache": _PERSIST_CACHE,
        }


def set_cache_persistence(persist: bool) -> None:
    """Configure whether embedding cache persists across phases.

    Args:
        persist: If True, cache persists across phases (default, cost-efficient).
                 If False, cache is reset at each phase start.
    """
    global _PERSIST_CACHE
    with _CACHE_LOCK:
        _PERSIST_CACHE = persist


def _get_embedding_call_cap() -> int:
    """Get per-phase embedding call cap from config/env.

    Returns:
        Maximum number of embedding calls per phase
        - 0 = embeddings disabled (fall back to lexical)
        - -1 = unlimited embeddings
        - > 0 = cap at that number
    """
    # Environment variable takes precedence
    env_cap = os.getenv("EMBEDDING_CACHE_MAX_CALLS_PER_PHASE")
    if env_cap is not None:
        try:
            return int(env_cap)
        except ValueError:
            pass

    return settings.embedding_cache_max_calls_per_phase


def _est_tokens_rough(text: str) -> int:
    # Conservative heuristic: 1 token ~= 4 chars for English-ish text.
    return max(1, int(len(text) / 4))


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    return float(dot / denom) if denom else 0.0


_WORD = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{2,}")


def _lexical_score(query: str, path: str, content: str) -> float:
    q = (query or "").lower()
    if not q:
        return 0.0
    q_terms = set(_WORD.findall(q))
    if not q_terms:
        return 0.0

    # Path gets a strong boost (it's a good proxy for relevance in codebases)
    p_terms = set(_WORD.findall((path or "").lower()))
    overlap_path = len(q_terms & p_terms)

    # Content: look at a limited prefix to stay cheap
    snippet = (content or "")[:6000].lower()
    c_terms = set(_WORD.findall(snippet))
    overlap_content = len(q_terms & c_terms)

    # Weighted overlap
    return overlap_path * 3.0 + overlap_content * 1.0


@dataclass
class BudgetSelection:
    kept: Dict[str, str]
    omitted: List[str]
    used_tokens_est: int
    budget_tokens: int
    mode: str  # "semantic" or "lexical"
    files_kept_count: int = 0
    files_omitted_count: int = 0


def select_files_for_context(
    *,
    files: Dict[str, str],
    scope_metadata: Optional[Dict[str, Any]],
    deliverables: Optional[List[str]],
    query: str,
    budget_tokens: int,
    semantic: bool = True,
    per_file_embed_chars: int = 4000,
    prep_tracker: Optional[ContextPrepTracker] = None,
) -> BudgetSelection:
    """Select files for context within a rough token budget.

    - Always includes deliverables if present in `files`.
    - Ranks remaining files by relevance, then by size.
    - Uses cached embeddings when available.
    - Falls back to lexical ranking if cache misses exceed per-phase cap.

    Args:
        files: Dict of file paths to contents
        scope_metadata: File categories and metadata
        deliverables: Files to always include
        query: Search query for relevance ranking
        budget_tokens: Token limit for context
        semantic: Whether to use semantic ranking with embeddings
        per_file_embed_chars: Characters to embed per file
        prep_tracker: Optional tracker for recording context prep costs
    """
    global _PHASE_CALL_COUNT

    scope_metadata = scope_metadata or {}
    deliverables_set = {d for d in (deliverables or []) if isinstance(d, str)}

    items: List[Tuple[int, int, str, str]] = []
    for path, content in (files or {}).items():
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        # Track file reads
        if prep_tracker:
            prep_tracker.record_file_read(path, len(content))
        meta = scope_metadata.get(path) or {}
        cat = meta.get("category") if isinstance(meta, dict) else None
        priority = 0 if path in deliverables_set else (1 if cat == "modifiable" else 2)
        items.append((priority, _est_tokens_rough(content), path, content))

    # Pin deliverables first
    kept: Dict[str, str] = {}
    used = 0
    omitted: List[str] = []

    for prio, tok, path, content in items:
        if prio != 0:
            continue
        kept[path] = content
        used += tok

    remaining = [
        (prio, tok, path, content) for prio, tok, path, content in items if path not in kept
    ]

    use_semantic = bool(semantic and semantic_embeddings_enabled())

    # Check if we've exceeded per-phase call cap (thread-safe read)
    call_cap = _get_embedding_call_cap()
    if call_cap == 0:
        # Cap of 0 means embeddings are disabled
        use_semantic = False
    elif call_cap > 0:
        with _CACHE_LOCK:
            if _PHASE_CALL_COUNT >= call_cap:
                # Positive cap exceeded
                use_semantic = False

    mode = "semantic" if use_semantic else "lexical"

    if use_semantic and remaining:
        try:
            # Build embeddings: 1 for query + N for file snippets
            texts_to_embed: List[str] = []
            cache_keys: List[Optional[str]] = [None]  # Query has no cache key

            # Query embedding (always fresh)
            texts_to_embed.append(query)

            # File embeddings (check cache - thread-safe)
            cache_hits = 0
            cache_misses = 0
            with _CACHE_LOCK:
                for _, _, path, content in remaining:
                    snippet = f"Path: {path}\n\n{content[:per_file_embed_chars]}"
                    cache_key = compute_cache_key(path, content)

                    if cache_key in _EMBEDDING_CACHE:
                        # Cache hit - no need to embed
                        cache_keys.append(cache_key)
                        cache_hits += 1
                    else:
                        # Cache miss - need to embed
                        texts_to_embed.append(snippet)
                        cache_keys.append(cache_key)
                        cache_misses += 1

            if cache_hits > 0 or cache_misses > 0:
                logger.info(
                    f"Embedding cache: {cache_hits} hits, {cache_misses} misses "
                    f"({(cache_hits / (cache_hits + cache_misses) * 100):.1f}% hit rate) "
                    f"out of {len(remaining)} files"
                )

            # Check if we need to make API call
            needs_api_call = len(texts_to_embed) > 1  # More than just query

            if needs_api_call:
                # Check cap before making call (thread-safe)
                with _CACHE_LOCK:
                    if call_cap > 0 and _PHASE_CALL_COUNT >= call_cap:
                        # Cap exceeded - fall back to lexical
                        use_semantic = False
                        mode = "lexical"

                if use_semantic:
                    # Make API call and update cache
                    vecs = sync_embed_texts(texts_to_embed)
                    # Track embedding call
                    if prep_tracker:
                        prep_tracker.record_embedding_call(
                            len(texts_to_embed) * 256
                        )  # Rough estimate
                    with _CACHE_LOCK:
                        _PHASE_CALL_COUNT += 1

                        # Store query vector
                        qv = vecs[0]

                        # Store file vectors in cache
                        vec_idx = 1
                        new_entries = 0
                        for i, (_, _, path, content) in enumerate(remaining):
                            cache_key = cache_keys[i + 1]  # +1 to skip query
                            if cache_key and cache_key not in _EMBEDDING_CACHE:
                                _EMBEDDING_CACHE[cache_key] = vecs[vec_idx]
                                vec_idx += 1
                                new_entries += 1

                    if new_entries > 0:
                        logger.info(
                            f"Added {new_entries} new embeddings to cache (cross-phase persistence)"
                        )
            else:
                # All cached - just get query embedding
                vecs = sync_embed_texts([query])
                with _CACHE_LOCK:
                    _PHASE_CALL_COUNT += 1
                qv = vecs[0]

            if use_semantic:
                # Build scores using cached or fresh embeddings (thread-safe)
                scores = []
                with _CACHE_LOCK:
                    for i, (prio, tok, path, content) in enumerate(remaining):
                        cache_key = cache_keys[i + 1]  # +1 to skip query
                        if cache_key and cache_key in _EMBEDDING_CACHE:
                            v = _EMBEDDING_CACHE[cache_key]
                        else:
                            # Should not happen if logic above is correct
                            v = [0.0] * 1536
                        scores.append((prio, -_cosine(qv, v), tok, path, content))

                # Sort by priority, then highest cosine (lowest negative), then smaller
                scores.sort(key=lambda t: (t[0], t[1], t[2]))
                ranked = [(prio, tok, path, content) for prio, _, tok, path, content in scores]
            else:
                # Fall back to lexical
                scored = []
                for prio, tok, path, content in remaining:
                    s = _lexical_score(query, path, content)
                    scored.append((prio, -s, tok, path, content))
                scored.sort(key=lambda t: (t[0], t[1], t[2]))
                ranked = [(prio, tok, path, content) for prio, _, tok, path, content in scored]

        except Exception:
            # API failure - fall back to lexical
            mode = "lexical"
            scored = []
            for prio, tok, path, content in remaining:
                s = _lexical_score(query, path, content)
                scored.append((prio, -s, tok, path, content))
            scored.sort(key=lambda t: (t[0], t[1], t[2]))
            ranked = [(prio, tok, path, content) for prio, _, tok, path, content in scored]
    else:
        # Lexical fallback
        scored = []
        for prio, tok, path, content in remaining:
            s = _lexical_score(query, path, content)
            scored.append((prio, -s, tok, path, content))
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        ranked = [(prio, tok, path, content) for prio, _, tok, path, content in scored]

    # Fill budget
    for prio, tok, path, content in ranked:
        if used + tok > budget_tokens:
            omitted.append(path)
            continue
        kept[path] = content
        used += tok

    return BudgetSelection(
        kept=kept,
        omitted=omitted,
        used_tokens_est=used,
        budget_tokens=budget_tokens,
        mode=mode,
        files_kept_count=len(kept),
        files_omitted_count=len(omitted),
    )
