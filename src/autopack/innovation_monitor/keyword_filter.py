"""
Keyword filter for AI innovations.

Rule-based filtering using regex patterns - 0 tokens.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Set

from .models import RawInnovation

logger = logging.getLogger(__name__)


@dataclass
class KeywordFilterConfig:
    """Configuration for keyword filtering."""

    # Must match at least one of these (case-insensitive regex patterns)
    required_keywords: List[str] = field(default_factory=list)

    # Boost score if these appear
    boost_keywords: List[str] = field(default_factory=list)

    # Skip if these appear (spam filter)
    exclude_keywords: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.required_keywords:
            self.required_keywords = [
                # Core RAG/Memory terms
                r"\bRAG\b",
                r"retrieval.augmented",
                r"vector.*(database|store|search|db)",
                r"embedding",
                r"semantic.search",
                r"memory.system",
                # Agent terms
                r"\bagent\b",
                r"agentic",
                r"autonomous",
                r"tool.use",
                r"function.call",
                # LLM efficiency
                r"token.efficien",
                r"context.window",
                r"context.length",
                r"long.context",
                r"context.compress",
                # Specific innovations
                r"PageIndex",
                r"tree.index",
                r"hierarchical.*(index|retrieval)",
                r"hybrid.search",
                r"ColBERT",
                r"RAPTOR",
                r"GraphRAG",
                r"HyDE",
                # LLM models
                r"\bClaude\b",
                r"\bGPT-?4",
                r"\bLlama",
                r"\bMistral\b",
                r"\bGemini\b",
            ]

        if not self.boost_keywords:
            self.boost_keywords = [
                r"benchmark",
                r"SOTA|state.of.the.art",
                r"outperform",
                r"\d+%.*improv",  # "30% improvement"
                r"open.source",
                r"github\.com",
                r"breakthrough",
                r"novel",
                r"efficient",
            ]

        if not self.exclude_keywords:
            self.exclude_keywords = [
                r"hiring|job.post|job.opening",
                r"looking.for.co-?founder",
                r"rate.my",
                r"roast.my",
                r"meme|joke|funny",
                r"salary|compensation|interview",
                r"beginner.question",
                r"ELI5",
            ]


class KeywordFilter:
    """
    Rule-based keyword filtering - 0 tokens.

    Filters raw innovations based on regex pattern matching.
    """

    def __init__(self, config: KeywordFilterConfig = None):
        self.config = config or KeywordFilterConfig()
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self.required_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config.required_keywords
        ]
        self.boost_patterns = [re.compile(p, re.IGNORECASE) for p in self.config.boost_keywords]
        self.exclude_patterns = [re.compile(p, re.IGNORECASE) for p in self.config.exclude_keywords]

    def filter(self, innovations: List[RawInnovation]) -> List[RawInnovation]:
        """
        Filter innovations based on keyword matching.

        Returns items that:
        - Match at least one required keyword
        - Don't match any exclude keywords
        """
        filtered = []
        excluded_count = 0
        no_match_count = 0

        for item in innovations:
            text = f"{item.title} {item.body_text}"

            # Check exclusions first (fast rejection)
            if self._matches_any(text, self.exclude_patterns):
                excluded_count += 1
                continue

            # Check required keywords
            if self._matches_any(text, self.required_patterns):
                filtered.append(item)
            else:
                no_match_count += 1

        logger.info(
            f"[KeywordFilter] {len(filtered)} passed, "
            f"{excluded_count} excluded, {no_match_count} no keyword match"
        )

        return filtered

    def _matches_any(self, text: str, patterns: List[re.Pattern]) -> bool:
        """Check if text matches any of the patterns."""
        return any(p.search(text) for p in patterns)

    def count_boost_matches(self, item: RawInnovation) -> int:
        """Count how many boost keywords match (for scoring)."""
        text = f"{item.title} {item.body_text}"
        return sum(1 for p in self.boost_patterns if p.search(text))

    def count_required_matches(self, item: RawInnovation) -> int:
        """Count how many required keywords match."""
        text = f"{item.title} {item.body_text}"
        return sum(1 for p in self.required_patterns if p.search(text))

    def get_matched_keywords(self, item: RawInnovation) -> List[str]:
        """Get list of matched required keywords."""
        text = f"{item.title} {item.body_text}"
        matched = []

        for pattern in self.required_patterns:
            match = pattern.search(text)
            if match:
                matched.append(match.group())

        return matched[:10]  # Limit to top 10
