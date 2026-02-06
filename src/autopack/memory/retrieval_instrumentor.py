"""
IMP-MEM-025: Memory Retrieval Instrumentation

Instruments memory retrieval to detect potential missed results without
changing retrieval behavior. Logs metrics for analysis to determine if
hybrid search (vector + keyword) would be beneficial.

This is diagnostic only - it does NOT change retrieval behavior.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from autopack.memory.qdrant_store import QdrantStore
    from autopack.memory.faiss_store import FaissStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalMetrics:
    """Metrics captured for each retrieval operation."""

    # Query info
    query_text: str
    query_hash: str  # For deduplication
    collection: str
    timestamp: str

    # Vector search results
    vector_results_count: int
    vector_result_ids: List[str]
    vector_top_score: float
    vector_min_score: float

    # Keyword scan results (instrumentation only)
    keyword_matches_count: int
    keyword_match_ids: List[str]

    # Analysis
    keyword_only_count: int  # Found by keyword but NOT by vector
    vector_only_count: int  # Found by vector but NOT by keyword
    overlap_count: int  # Found by both

    # Exact match indicators
    exact_match_in_corpus: bool  # Query terms appear exactly in some memory
    exact_match_retrieved: bool  # That exact match was in vector results

    # Additional context
    top_k_requested: int
    query_terms: List[str]  # Extracted significant terms


@dataclass
class InstrumentorConfig:
    """Configuration for retrieval instrumentation."""

    enabled: bool = False
    sample_rate: float = 1.0  # 1.0 = all queries, 0.1 = 10%
    log_path: str = "data/retrieval_metrics.jsonl"
    keyword_scan_limit: int = 100  # Max entries to scan per query

    # Terms to extract from queries
    min_term_length: int = 3
    stop_words: Set[str] = field(
        default_factory=lambda: {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "are",
            "was",
            "were",
            "been",
            "have",
            "has",
            "had",
            "will",
            "would",
            "could",
            "should",
            "what",
            "when",
            "where",
            "which",
            "who",
            "how",
            "why",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "also",
            "now",
            "any",
            "both",
            "but",
            "not",
            "out",
            "over",
            "can",
            "did",
            "does",
            "doing",
            "being",
        }
    )


class RetrievalInstrumentor:
    """
    Instruments memory retrieval to detect potential missed results.

    IMP-MEM-025: This class runs keyword scans in parallel with vector
    search (for instrumentation only) and logs cases where keyword
    matching finds items that vector search missed.

    IMPORTANT: This does NOT change retrieval behavior. Vector search
    results are always returned unchanged. The keyword scan is purely
    for metrics collection.
    """

    def __init__(
        self,
        store: Any,  # QdrantStore or FaissStore
        config: Optional[InstrumentorConfig] = None,
    ):
        self.store = store
        self.config = config or InstrumentorConfig()
        self._ensure_log_dir()
        self._metrics_buffer: List[RetrievalMetrics] = []
        self._buffer_size = 10  # Flush every N metrics

    def _ensure_log_dir(self) -> None:
        """Ensure the log directory exists."""
        log_path = Path(self.config.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    def instrument_query(
        self,
        query: str,
        collection: str,
        vector_results: List[Any],  # List of ScoredPoint or similar
        top_k: int = 10,
    ) -> Optional[RetrievalMetrics]:
        """
        Run keyword scan and compare with vector results.

        This does NOT change retrieval behavior - only logs metrics.

        Args:
            query: The search query text
            collection: The collection being searched
            vector_results: Results from vector search
            top_k: Number of results requested

        Returns:
            RetrievalMetrics if instrumentation ran, None if skipped
        """
        if not self.config.enabled:
            return None

        # Sample rate check
        if self.config.sample_rate < 1.0:
            import random

            if random.random() > self.config.sample_rate:
                return None

        try:
            # 1. Extract significant terms from query
            terms = self._extract_query_terms(query)
            if not terms:
                logger.debug(f"[IMP-MEM-025] No significant terms in query: {query[:50]}")
                return None

            # 2. Run keyword scan against collection
            keyword_matches = self._keyword_scan(collection, terms)

            # 3. Extract IDs from results
            vector_ids = self._extract_ids(vector_results)
            keyword_ids = {m["id"] for m in keyword_matches}

            # 4. Calculate overlap/differences
            keyword_only = keyword_ids - vector_ids
            vector_only = vector_ids - keyword_ids
            overlap = vector_ids & keyword_ids

            # 5. Check for exact match scenarios
            exact_match_exists = self._check_exact_match_exists(keyword_matches, query)
            exact_match_retrieved = self._check_exact_match_retrieved(query, vector_results)

            # 6. Build metrics
            metrics = RetrievalMetrics(
                query_text=query[:500],  # Truncate for storage
                query_hash=hashlib.md5(query.encode()).hexdigest()[:12],
                collection=collection,
                timestamp=datetime.now(timezone.utc).isoformat(),
                vector_results_count=len(vector_results),
                vector_result_ids=list(vector_ids)[:20],  # Limit stored IDs
                vector_top_score=self._get_top_score(vector_results),
                vector_min_score=self._get_min_score(vector_results),
                keyword_matches_count=len(keyword_matches),
                keyword_match_ids=list(keyword_ids)[:20],
                keyword_only_count=len(keyword_only),
                vector_only_count=len(vector_only),
                overlap_count=len(overlap),
                exact_match_in_corpus=exact_match_exists,
                exact_match_retrieved=exact_match_retrieved,
                top_k_requested=top_k,
                query_terms=terms[:10],  # Limit stored terms
            )

            # 7. Log metrics
            self._log_metrics(metrics)

            # 8. Log warning if significant misses detected
            if keyword_only and len(keyword_only) > 0:
                logger.info(
                    f"[IMP-MEM-025] Potential missed results: "
                    f"{len(keyword_only)} items found by keyword but not vector "
                    f"(query: {query[:50]}...)"
                )

            if exact_match_exists and not exact_match_retrieved:
                logger.warning(
                    f"[IMP-MEM-025] Exact match exists but not retrieved: " f"{query[:50]}..."
                )

            return metrics

        except Exception as e:
            logger.warning(f"[IMP-MEM-025] Instrumentation error: {e}")
            return None

    def _extract_query_terms(self, query: str) -> List[str]:
        """
        Extract significant terms for keyword matching.

        Focuses on:
        - Technical terms (CamelCase, snake_case)
        - Error codes and identifiers
        - File paths
        - Non-stop words
        """
        terms = []

        # Extract words
        words = re.findall(r"\b\w+\b", query.lower())

        for word in words:
            # Skip short words and stop words
            if len(word) < self.config.min_term_length:
                continue
            if word in self.config.stop_words:
                continue

            terms.append(word)

        # Extract CamelCase terms (preserve case)
        camel_terms = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query)
        terms.extend([t.lower() for t in camel_terms])

        # Extract snake_case terms
        snake_terms = re.findall(r"\b\w+_\w+\b", query)
        terms.extend([t.lower() for t in snake_terms])

        # Extract potential error codes (e.g., ERR_001, E0001)
        error_codes = re.findall(r"\b[A-Z]+[_-]?\d+\b", query)
        terms.extend([e.lower() for e in error_codes])

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for t in terms:
            if t not in seen:
                seen.add(t)
                unique_terms.append(t)

        return unique_terms

    def _keyword_scan(
        self,
        collection: str,
        terms: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Scan collection for keyword matches.

        Returns list of matching entries with their IDs and content.
        """
        matches = []

        try:
            # Get entries from store (implementation depends on store type)
            entries = self._get_collection_entries(collection)

            for entry in entries[: self.config.keyword_scan_limit]:
                content = self._get_entry_content(entry)
                if not content:
                    continue

                content_lower = content.lower()

                # Check if any term matches
                for term in terms:
                    if term in content_lower:
                        matches.append(
                            {
                                "id": self._get_entry_id(entry),
                                "matched_term": term,
                                "content_preview": content[:200],
                            }
                        )
                        break  # Count each entry once

        except Exception as e:
            logger.debug(f"[IMP-MEM-025] Keyword scan error: {e}")

        return matches

    def _get_collection_entries(self, collection: str) -> List[Any]:
        """Get entries from the collection for scanning."""
        try:
            # Try Qdrant scroll
            if hasattr(self.store, "client") and hasattr(self.store.client, "scroll"):
                result = self.store.client.scroll(
                    collection_name=collection,
                    limit=self.config.keyword_scan_limit,
                    with_payload=True,
                )
                return result[0] if result else []

            # Try FAISS metadata access
            if hasattr(self.store, "metadata"):
                return list(self.store.metadata.get(collection, {}).values())

        except Exception as e:
            logger.debug(f"[IMP-MEM-025] Could not access collection: {e}")

        return []

    def _get_entry_content(self, entry: Any) -> Optional[str]:
        """Extract content string from an entry."""
        try:
            # Qdrant point
            if hasattr(entry, "payload"):
                payload = entry.payload
                return payload.get("content") or payload.get("summary") or str(payload)

            # Dict entry
            if isinstance(entry, dict):
                return entry.get("content") or entry.get("summary") or str(entry)

        except Exception:
            pass

        return None

    def _get_entry_id(self, entry: Any) -> str:
        """Extract ID from an entry."""
        try:
            if hasattr(entry, "id"):
                return str(entry.id)
            if isinstance(entry, dict) and "id" in entry:
                return str(entry["id"])
        except Exception:
            pass
        return "unknown"

    def _extract_ids(self, results: List[Any]) -> Set[str]:
        """Extract IDs from vector search results."""
        ids = set()
        for r in results:
            try:
                if hasattr(r, "id"):
                    ids.add(str(r.id))
                elif isinstance(r, dict) and "id" in r:
                    ids.add(str(r["id"]))
            except Exception:
                pass
        return ids

    def _get_top_score(self, results: List[Any]) -> float:
        """Get highest score from results."""
        if not results:
            return 0.0
        try:
            scores = [r.score if hasattr(r, "score") else r.get("score", 0) for r in results]
            return max(scores) if scores else 0.0
        except Exception:
            return 0.0

    def _get_min_score(self, results: List[Any]) -> float:
        """Get lowest score from results."""
        if not results:
            return 0.0
        try:
            scores = [r.score if hasattr(r, "score") else r.get("score", 0) for r in results]
            return min(scores) if scores else 0.0
        except Exception:
            return 0.0

    def _check_exact_match_exists(
        self,
        keyword_matches: List[Dict[str, Any]],
        query: str,
    ) -> bool:
        """Check if query text appears exactly in any matched entry."""
        query_lower = query.lower()

        for match in keyword_matches:
            content = match.get("content_preview", "").lower()
            if query_lower in content:
                return True

        return False

    def _check_exact_match_retrieved(
        self,
        query: str,
        vector_results: List[Any],
    ) -> bool:
        """Check if exact-match entry was in vector results."""
        query_lower = query.lower()

        for result in vector_results:
            content = self._get_entry_content(result)
            if content and query_lower in content.lower():
                return True

        return False

    def _log_metrics(self, metrics: RetrievalMetrics) -> None:
        """Append metrics to buffer and flush if needed."""
        self._metrics_buffer.append(metrics)

        if len(self._metrics_buffer) >= self._buffer_size:
            self._flush_metrics()

    def _flush_metrics(self) -> None:
        """Write buffered metrics to log file."""
        if not self._metrics_buffer:
            return

        try:
            with open(self.config.log_path, "a", encoding="utf-8") as f:
                for metrics in self._metrics_buffer:
                    f.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")

            logger.debug(f"[IMP-MEM-025] Flushed {len(self._metrics_buffer)} metrics to log")
            self._metrics_buffer.clear()

        except Exception as e:
            logger.warning(f"[IMP-MEM-025] Failed to flush metrics: {e}")

    def flush(self) -> None:
        """Force flush any buffered metrics."""
        self._flush_metrics()

    def get_metrics_count(self) -> int:
        """Get total number of logged metrics."""
        try:
            log_path = Path(self.config.log_path)
            if not log_path.exists():
                return 0

            with open(log_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0


def create_instrumentor_from_config(
    store: Any,
    config_dict: Optional[Dict[str, Any]] = None,
) -> RetrievalInstrumentor:
    """
    Create an instrumentor from configuration dictionary.

    Args:
        store: The vector store to instrument
        config_dict: Configuration from memory.yaml

    Returns:
        Configured RetrievalInstrumentor
    """
    if config_dict is None:
        config_dict = {}

    config = InstrumentorConfig(
        enabled=config_dict.get("enabled", False),
        sample_rate=config_dict.get("sample_rate", 1.0),
        log_path=config_dict.get("log_path", "data/retrieval_metrics.jsonl"),
        keyword_scan_limit=config_dict.get("keyword_scan_limit", 100),
    )

    return RetrievalInstrumentor(store, config)
