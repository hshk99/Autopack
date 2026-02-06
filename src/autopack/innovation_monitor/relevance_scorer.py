"""
Relevance scorer for AI innovations.

Code-based weighted scoring - 0 tokens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .models import RawInnovation, ScoredInnovation, SourceType
from .keyword_filter import KeywordFilter

logger = logging.getLogger(__name__)


@dataclass
class ScoringWeights:
    """Weights for relevance scoring formula."""

    keyword_match: float = 0.30  # Keyword relevance
    engagement: float = 0.20  # Upvotes, comments
    recency: float = 0.15  # Newer = better
    source_quality: float = 0.20  # ArXiv > Reddit shitpost
    boost_keywords: float = 0.15  # Benchmark claims, etc.


class RelevanceScorer:
    """
    Code-based relevance scoring - 0 tokens.

    Computes a weighted score based on multiple signals.
    """

    # Source quality scores (higher = more credible)
    SOURCE_QUALITY_SCORES = {
        SourceType.ARXIV: 1.0,  # Peer review signal
        SourceType.HUGGINGFACE: 0.9,  # Curated
        SourceType.GITHUB: 0.7,  # Varies widely
        SourceType.HACKERNEWS: 0.6,  # Community filter
        SourceType.REDDIT: 0.5,  # High noise
        SourceType.BLOG: 0.4,  # Unknown quality
        SourceType.NEWS: 0.5,  # Varies
    }

    # Engagement thresholds by source (what counts as "high engagement")
    ENGAGEMENT_THRESHOLDS = {
        SourceType.ARXIV: 1,  # ArXiv doesn't have upvotes
        SourceType.HUGGINGFACE: 50,  # 50 upvotes is significant
        SourceType.GITHUB: 500,  # 500 stars is notable
        SourceType.HACKERNEWS: 50,  # 50 points is good
        SourceType.REDDIT: 100,  # 100 upvotes is good
        SourceType.BLOG: 1,  # No engagement data
        SourceType.NEWS: 1,  # No engagement data
    }

    def __init__(
        self,
        weights: ScoringWeights = None,
        keyword_filter: KeywordFilter = None,
    ):
        self.weights = weights or ScoringWeights()
        self.keyword_filter = keyword_filter or KeywordFilter()

    def score(self, innovations: List[RawInnovation]) -> List[ScoredInnovation]:
        """
        Score and rank innovations by relevance.

        Returns sorted list (highest score first).
        """
        scored = []

        for item in innovations:
            breakdown = self._compute_score_breakdown(item)
            total = sum(getattr(self.weights, k) * v for k, v in breakdown.items())

            scored.append(
                ScoredInnovation(
                    raw=item,
                    score=total,
                    score_breakdown=breakdown,
                )
            )

        # Sort by score descending
        return sorted(scored, key=lambda x: x.score, reverse=True)

    def _compute_score_breakdown(self, item: RawInnovation) -> dict:
        """Compute individual score components."""
        return {
            "keyword_match": self._keyword_score(item),
            "engagement": self._engagement_score(item),
            "recency": self._recency_score(item),
            "source_quality": self._source_quality_score(item),
            "boost_keywords": self._boost_score(item),
        }

    def _keyword_score(self, item: RawInnovation) -> float:
        """Score based on keyword match density."""
        matches = self.keyword_filter.count_required_matches(item)
        # Normalize: 3+ matches = 1.0
        return min(matches / 3.0, 1.0)

    def _engagement_score(self, item: RawInnovation) -> float:
        """Score based on community engagement."""
        threshold = self.ENGAGEMENT_THRESHOLDS.get(item.source, 100)

        # Normalize engagement relative to source-specific threshold
        if item.upvotes <= 0:
            # No engagement data
            return 0.5  # Neutral

        return min(item.upvotes / threshold, 1.0)

    def _recency_score(self, item: RawInnovation) -> float:
        """Score based on publication date."""
        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes
        pub_date = item.published_date
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        age_days = (now - pub_date).days

        if age_days <= 1:
            return 1.0
        elif age_days <= 3:
            return 0.9
        elif age_days <= 7:
            return 0.7
        elif age_days <= 14:
            return 0.5
        elif age_days <= 30:
            return 0.3
        else:
            return 0.1

    def _source_quality_score(self, item: RawInnovation) -> float:
        """Score based on source reputation."""
        return self.SOURCE_QUALITY_SCORES.get(item.source, 0.3)

    def _boost_score(self, item: RawInnovation) -> float:
        """Score based on boost keyword matches."""
        count = self.keyword_filter.count_boost_matches(item)
        return min(count / 3.0, 1.0)
