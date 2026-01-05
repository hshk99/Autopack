"""Source Evaluation Agent.

This module provides the SourceEvaluator class for evaluating the relevance
and trustworthiness of research sources.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import re
from urllib.parse import urlparse


@dataclass
class SourceEvaluation:
    """Represents a source evaluation result."""

    source_url: str
    relevance_score: float
    trust_score: float
    overall_score: float
    factors: Dict[str, float]
    reasoning: str

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "source_url": self.source_url,
            "relevance_score": self.relevance_score,
            "trust_score": self.trust_score,
            "overall_score": self.overall_score,
            "factors": self.factors,
            "reasoning": self.reasoning,
        }


class SourceEvaluator:
    """Evaluates the quality and trustworthiness of research sources."""

    def __init__(self, trust_tiers: Optional[Dict] = None):
        """Initialize the source evaluator.

        Args:
            trust_tiers: Dictionary mapping domains to trust tiers
        """
        self.trust_tiers = trust_tiers or self._default_trust_tiers()

        # Domain patterns for different source types
        self.domain_patterns = {
            "official_docs": [r"docs?\..*", r".*\.readthedocs\.io"],
            "academic": [r".*\.edu", r"arxiv\.org", r"scholar\.google\.com"],
            "community": [r"stackoverflow\.com", r"reddit\.com", r"github\.com"],
            "blog": [r"medium\.com", r"dev\.to", r".*\.blog"],
            "news": [r".*news.*", r"techcrunch\.com", r"arstechnica\.com"],
        }

    def evaluate(
        self,
        source_url: str,
        content: Optional[str] = None,
        metadata: Optional[Dict] = None,
        query_keywords: Optional[List[str]] = None,
    ) -> SourceEvaluation:
        """Evaluate a source for relevance and trustworthiness.

        Args:
            source_url: URL of the source
            content: Optional content text for relevance analysis
            metadata: Optional metadata (title, description, etc.)
            query_keywords: Optional list of keywords from the research query

        Returns:
            SourceEvaluation with scores and reasoning
        """
        factors = {}
        reasoning_parts = []

        # Evaluate trust based on domain
        trust_score, trust_reasoning = self._evaluate_trust(source_url)
        factors["trust"] = trust_score
        reasoning_parts.append(trust_reasoning)

        # Evaluate relevance if content is provided
        if content and query_keywords:
            relevance_score, relevance_reasoning = self._evaluate_relevance(content, query_keywords)
            factors["relevance"] = relevance_score
            reasoning_parts.append(relevance_reasoning)
        else:
            relevance_score = 0.5  # Neutral if no content
            factors["relevance"] = relevance_score

        # Evaluate metadata quality
        if metadata:
            metadata_score, metadata_reasoning = self._evaluate_metadata(metadata)
            factors["metadata"] = metadata_score
            reasoning_parts.append(metadata_reasoning)
        else:
            factors["metadata"] = 0.5

        # Evaluate URL quality
        url_score, url_reasoning = self._evaluate_url(source_url)
        factors["url_quality"] = url_score
        reasoning_parts.append(url_reasoning)

        # Calculate overall score (weighted average)
        weights = {"trust": 0.4, "relevance": 0.3, "metadata": 0.15, "url_quality": 0.15}

        overall_score = sum(factors[k] * weights[k] for k in weights if k in factors)

        return SourceEvaluation(
            source_url=source_url,
            relevance_score=relevance_score,
            trust_score=trust_score,
            overall_score=overall_score,
            factors=factors,
            reasoning=" ".join(reasoning_parts),
        )

    def _evaluate_trust(self, url: str) -> tuple[float, str]:
        """Evaluate trustworthiness based on domain.

        Args:
            url: Source URL

        Returns:
            Tuple of (trust_score, reasoning)
        """
        domain = urlparse(url).netloc.lower()

        # Check against trust tiers
        for tier, domains in self.trust_tiers.items():
            if domain in domains:
                score = self._tier_to_score(tier)
                return score, f"Domain {domain} is in {tier} tier."

        # Check domain patterns
        for source_type, patterns in self.domain_patterns.items():
            for pattern in patterns:
                if re.match(pattern, domain):
                    score = self._source_type_to_score(source_type)
                    return score, f"Domain matches {source_type} pattern."

        # Default trust for unknown domains
        return 0.5, "Unknown domain, neutral trust."

    def _evaluate_relevance(self, content: str, keywords: List[str]) -> tuple[float, str]:
        """Evaluate content relevance to query keywords.

        Args:
            content: Content text
            keywords: List of query keywords

        Returns:
            Tuple of (relevance_score, reasoning)
        """
        if not content or not keywords:
            return 0.5, "Insufficient data for relevance analysis."

        content_lower = content.lower()
        keyword_matches = 0
        total_keywords = len(keywords)

        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Count occurrences
            count = content_lower.count(keyword_lower)
            if count > 0:
                keyword_matches += 1

        # Calculate relevance score
        if total_keywords > 0:
            match_ratio = keyword_matches / total_keywords
            score = min(match_ratio * 1.2, 1.0)  # Boost slightly, cap at 1.0
        else:
            score = 0.5

        reasoning = f"Matched {keyword_matches}/{total_keywords} keywords."
        return score, reasoning

    def _evaluate_metadata(self, metadata: Dict) -> tuple[float, str]:
        """Evaluate metadata quality.

        Args:
            metadata: Metadata dictionary

        Returns:
            Tuple of (metadata_score, reasoning)
        """
        score = 0.5
        factors = []

        # Check for title
        if metadata.get("title"):
            score += 0.15
            factors.append("has title")

        # Check for description
        if metadata.get("description"):
            score += 0.15
            factors.append("has description")

        # Check for author
        if metadata.get("author"):
            score += 0.1
            factors.append("has author")

        # Check for date
        if metadata.get("date") or metadata.get("published_date"):
            score += 0.1
            factors.append("has date")

        score = min(score, 1.0)
        reasoning = f"Metadata quality: {', '.join(factors) if factors else 'minimal'}."
        return score, reasoning

    def _evaluate_url(self, url: str) -> tuple[float, str]:
        """Evaluate URL quality and structure.

        Args:
            url: Source URL

        Returns:
            Tuple of (url_score, reasoning)
        """
        score = 0.5
        factors = []

        parsed = urlparse(url)

        # HTTPS is preferred
        if parsed.scheme == "https":
            score += 0.2
            factors.append("secure (HTTPS)")

        # Check for clean URL structure
        if not re.search(r"[?&].*=", parsed.path):  # No query params in path
            score += 0.15
            factors.append("clean path")

        # Check for readable path
        if re.search(r"/[a-z-]+/", parsed.path):  # Has readable segments
            score += 0.15
            factors.append("readable path")

        score = min(score, 1.0)
        reasoning = f"URL quality: {', '.join(factors) if factors else 'basic'}."
        return score, reasoning

    def _tier_to_score(self, tier: str) -> float:
        """Convert trust tier to numeric score.

        Args:
            tier: Trust tier name

        Returns:
            Numeric score (0.0-1.0)
        """
        tier_scores = {
            "tier1_official": 1.0,
            "tier2_verified": 0.85,
            "tier3_community": 0.7,
            "tier4_general": 0.5,
            "tier5_untrusted": 0.2,
        }
        return tier_scores.get(tier, 0.5)

    def _source_type_to_score(self, source_type: str) -> float:
        """Convert source type to trust score.

        Args:
            source_type: Type of source

        Returns:
            Numeric score (0.0-1.0)
        """
        type_scores = {
            "official_docs": 0.95,
            "academic": 0.9,
            "community": 0.7,
            "blog": 0.6,
            "news": 0.65,
        }
        return type_scores.get(source_type, 0.5)

    def _default_trust_tiers(self) -> Dict:
        """Get default trust tier configuration.

        Returns:
            Dictionary mapping tier names to domain lists
        """
        return {
            "tier1_official": [
                "docs.python.org",
                "developer.mozilla.org",
                "react.dev",
                "go.dev",
                "doc.rust-lang.org",
            ],
            "tier2_verified": ["github.com", "stackoverflow.com", "arxiv.org"],
            "tier3_community": ["reddit.com", "dev.to", "medium.com"],
            "tier4_general": [],
            "tier5_untrusted": [],
        }

    def batch_evaluate(self, sources: List[Dict]) -> List[SourceEvaluation]:
        """Evaluate multiple sources.

        Args:
            sources: List of source dictionaries with 'url', 'content', 'metadata'

        Returns:
            List of source evaluations
        """
        evaluations = []

        for source in sources:
            evaluation = self.evaluate(
                source_url=source.get("url", ""),
                content=source.get("content"),
                metadata=source.get("metadata"),
                query_keywords=source.get("keywords"),
            )
            evaluations.append(evaluation)

        return evaluations

    def rank_sources(self, evaluations: List[SourceEvaluation]) -> List[SourceEvaluation]:
        """Rank sources by overall score.

        Args:
            evaluations: List of source evaluations

        Returns:
            Sorted list of evaluations (highest score first)
        """
        return sorted(evaluations, key=lambda e: e.overall_score, reverse=True)
