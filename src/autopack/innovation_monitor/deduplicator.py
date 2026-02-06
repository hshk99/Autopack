"""
Deduplication for AI innovations.

Hash and similarity-based deduplication - 0 tokens.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Set

from .models import ScoredInnovation

logger = logging.getLogger(__name__)


class Deduplicator:
    """
    Hash and similarity-based deduplication - 0 tokens.

    Tracks seen innovations across sessions via a persistent file.
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        seen_file: str = "data/innovation_monitor/seen.json",
    ):
        """
        Initialize deduplicator.

        Args:
            similarity_threshold: Title similarity threshold for duplicate detection
            seen_file: Path to file storing seen innovation IDs
        """
        self.similarity_threshold = similarity_threshold
        self.seen_file = Path(seen_file)
        self.seen_hashes: Set[str] = set()
        self.seen_titles: List[str] = []

        self._load_seen()

    def _load_seen(self) -> None:
        """Load previously seen innovations from file."""
        if not self.seen_file.exists():
            return

        try:
            with open(self.seen_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.seen_hashes = set(data.get("hashes", []))
                self.seen_titles = data.get("titles", [])[-1000:]  # Keep last 1000

            logger.info(f"[Deduplicator] Loaded {len(self.seen_hashes)} seen hashes")
        except Exception as e:
            logger.warning(f"[Deduplicator] Failed to load seen file: {e}")

    def _save_seen(self) -> None:
        """Save seen innovations to file."""
        try:
            self.seen_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.seen_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "hashes": list(self.seen_hashes)[-5000],  # Keep last 5000
                        "titles": self.seen_titles[-1000],  # Keep last 1000
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                )

        except Exception as e:
            logger.warning(f"[Deduplicator] Failed to save seen file: {e}")

    def deduplicate(
        self,
        innovations: List[ScoredInnovation],
    ) -> List[ScoredInnovation]:
        """
        Remove duplicates based on:
        1. URL hash (exact duplicate)
        2. Title similarity (near duplicate)

        Also filters out previously seen innovations.
        """
        unique = []
        new_hashes = []
        new_titles = []

        for item in innovations:
            # Check URL hash
            url_hash = hashlib.md5(item.raw.url.encode()).hexdigest()
            if url_hash in self.seen_hashes:
                continue

            # Check title similarity against seen titles
            if self._is_similar_to_seen(item.raw.title):
                continue

            # Check title similarity within current batch
            if self._is_similar_to_batch(item.raw.title, new_titles):
                continue

            # Unique - add to results
            unique.append(item)
            new_hashes.append(url_hash)
            new_titles.append(item.raw.title)

        # Update seen sets
        self.seen_hashes.update(new_hashes)
        self.seen_titles.extend(new_titles)

        # Persist
        self._save_seen()

        logger.info(
            f"[Deduplicator] {len(unique)} unique out of {len(innovations)} "
            f"({len(innovations) - len(unique)} duplicates removed)"
        )

        return unique

    def _is_similar_to_seen(self, title: str) -> bool:
        """Check if title is similar to any previously seen title."""
        title_lower = title.lower()

        for seen in self.seen_titles:
            ratio = SequenceMatcher(None, title_lower, seen.lower()).ratio()

            if ratio >= self.similarity_threshold:
                return True

        return False

    def _is_similar_to_batch(self, title: str, batch_titles: List[str]) -> bool:
        """Check if title is similar to any title in current batch."""
        title_lower = title.lower()

        for batch_title in batch_titles:
            ratio = SequenceMatcher(None, title_lower, batch_title.lower()).ratio()

            if ratio >= self.similarity_threshold:
                return True

        return False

    def filter_unseen(
        self,
        innovations: List[ScoredInnovation],
    ) -> List[ScoredInnovation]:
        """Filter to only innovations not previously seen (by URL)."""
        unseen = []

        for item in innovations:
            url_hash = hashlib.md5(item.raw.url.encode()).hexdigest()
            if url_hash not in self.seen_hashes:
                unseen.append(item)

        return unseen

    def mark_seen(self, innovations: List[ScoredInnovation]) -> None:
        """Mark innovations as seen without filtering."""
        for item in innovations:
            url_hash = hashlib.md5(item.raw.url.encode()).hexdigest()
            self.seen_hashes.add(url_hash)
            self.seen_titles.append(item.raw.title)

        self._save_seen()

    def reset(self) -> None:
        """Reset seen state (for testing)."""
        self.seen_hashes.clear()
        self.seen_titles.clear()
        if self.seen_file.exists():
            self.seen_file.unlink()
