"""
Context budgeter: select a subset of files for LLM context under a token/char budget.

Supports:
- Deliverables pinning (always include deliverable files when present)
- Semantic relevance ranking (OpenAI embeddings) when available
- Lexical relevance fallback (keywords + path signals) when embeddings are offline
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from autopack.memory.embeddings import sync_embed_texts, semantic_embeddings_enabled


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

    # Path gets a strong boost (it’s a good proxy for relevance in codebases)
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


def select_files_for_context(
    *,
    files: Dict[str, str],
    scope_metadata: Optional[Dict[str, Any]],
    deliverables: Optional[List[str]],
    query: str,
    budget_tokens: int,
    semantic: bool = True,
    per_file_embed_chars: int = 4000,
) -> BudgetSelection:
    """
    Select files for context within a rough token budget.

    - Always includes deliverables if present in `files`.
    - Ranks remaining files by relevance, then by size.
    """
    scope_metadata = scope_metadata or {}
    deliverables_set = {d for d in (deliverables or []) if isinstance(d, str)}

    items: List[Tuple[int, int, str, str]] = []
    for path, content in (files or {}).items():
        if not isinstance(path, str) or not isinstance(content, str):
            continue
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

    remaining = [(prio, tok, path, content) for prio, tok, path, content in items if path not in kept]

    use_semantic = bool(semantic and semantic_embeddings_enabled())
    mode = "semantic" if use_semantic else "lexical"

    if use_semantic and remaining:
        # Build embeddings: 1 for query + N for file snippets
        texts = [query]
        for _, _, path, content in remaining:
            snippet = f"Path: {path}\n\n{content[:per_file_embed_chars]}"
            texts.append(snippet)
        vecs = sync_embed_texts(texts)
        qv = vecs[0]
        scores = []
        for (prio, tok, path, content), v in zip(remaining, vecs[1:]):
            scores.append((prio, -_cosine(qv, v), tok, path, content))
        # Sort by priority, then highest cosine (lowest negative), then smaller
        scores.sort(key=lambda t: (t[0], t[1], t[2]))
        ranked = [(prio, tok, path, content) for prio, _, tok, path, content in scores]
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
    )


