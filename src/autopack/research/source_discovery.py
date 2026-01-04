"""Source Discovery Module - Discovery strategies for research sources.

This module provides async discovery strategies for finding relevant sources
from different platforms (web, academic, documentation).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from datetime import datetime


class SourceType(Enum):
    """Source type enumeration."""
    WEB = "web"
    GITHUB = "github"
    REDDIT = "reddit"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    ACADEMIC = "academic"
    NEWS = "news"
    DOCUMENTATION = "documentation"


@dataclass
class DiscoveredSource:
    """Discovered source with relevance scoring.

    Attributes:
        url: Source URL
        title: Source title
        description: Source description/snippet
        relevance_score: Relevance score (0.0-1.0)
        source_type: Type of source
        metadata: Additional metadata
    """
    url: str
    title: str = ""
    description: str = ""
    relevance_score: float = 0.0
    source_type: SourceType = SourceType.WEB
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Source:
    """Legacy Source model for backward compatibility."""
    url: str
    source_type: SourceType
    title: str = ""
    description: str = ""
    relevance: float = 0.0
    discovered_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryQuery:
    """Discovery query configuration."""
    query: str
    source_types: List[SourceType] = field(default_factory=list)
    max_results: int = 10
    filters: Dict[str, Any] = field(default_factory=dict)


class SourceDiscoveryStrategy:
    """Base class for source discovery strategies."""

    def __init__(self, name: str = "default"):
        """Initialize strategy."""
        self.name = name

    async def discover(self, intent) -> List[DiscoveredSource]:
        """Discover sources using this strategy.

        Args:
            intent: ClarifiedIntent object with research query details

        Returns:
            List of DiscoveredSource objects
        """
        return []

    async def _execute_search(self, query: str) -> List[Dict[str, Any]]:
        """Execute search and return raw results.

        Args:
            query: Search query string

        Returns:
            List of search results as dicts with url, title, snippet
        """
        # Mock implementation - real implementation would call external APIs
        return []

    def _calculate_relevance(self, source: Dict[str, Any], intent) -> float:
        """Calculate relevance score for a source.

        Args:
            source: Source dict with title and snippet
            intent: ClarifiedIntent object

        Returns:
            Relevance score (0.0-1.0)
        """
        # Simple keyword-based relevance
        score = 0.0
        text = (source.get("title", "") + " " + source.get("snippet", "")).lower()

        # Check for key concepts
        if hasattr(intent, "key_concepts"):
            matches = sum(1 for concept in intent.key_concepts if concept.lower() in text)
            score += min(matches / max(len(intent.key_concepts), 1) * 0.5, 0.5)

        # Check for clarified aspects
        if hasattr(intent, "clarified_aspects"):
            matches = sum(1 for aspect in intent.clarified_aspects if aspect.lower() in text)
            score += min(matches / max(len(intent.clarified_aspects), 1) * 0.5, 0.5)

        return min(score, 1.0)

    def _deduplicate(self, sources: List[DiscoveredSource]) -> List[DiscoveredSource]:
        """Remove duplicate sources based on URL.

        Args:
            sources: List of sources

        Returns:
            Deduplicated list of sources
        """
        seen_urls: Set[str] = set()
        unique_sources = []
        for source in sources:
            if source.url not in seen_urls:
                seen_urls.add(source.url)
                unique_sources.append(source)
        return unique_sources

    def _rank_by_relevance(self, sources: List[DiscoveredSource]) -> List[DiscoveredSource]:
        """Sort sources by relevance score (descending).

        Args:
            sources: List of sources

        Returns:
            Sorted list of sources
        """
        return sorted(sources, key=lambda s: s.relevance_score, reverse=True)


class WebSearchStrategy(SourceDiscoveryStrategy):
    """Web search discovery strategy."""

    def __init__(self):
        """Initialize web search strategy."""
        super().__init__("web_search")

    async def discover(self, intent) -> List[DiscoveredSource]:
        """Discover sources via web search.

        Args:
            intent: ClarifiedIntent object

        Returns:
            Ranked and deduplicated list of DiscoveredSource objects
        """
        # Build search query from intent
        query = getattr(intent, "original_query", "")

        # Execute search
        raw_results = await self._execute_search(query)

        # Convert to DiscoveredSource objects with relevance scores
        sources = []
        for result in raw_results:
            relevance = self._calculate_relevance(result, intent)
            source = DiscoveredSource(
                url=result.get("url", ""),
                title=result.get("title", ""),
                description=result.get("snippet", ""),
                relevance_score=relevance,
                source_type=SourceType.WEB
            )
            sources.append(source)

        # Deduplicate and rank
        sources = self._deduplicate(sources)
        sources = self._rank_by_relevance(sources)

        return sources


class AcademicSearchStrategy(SourceDiscoveryStrategy):
    """Academic search discovery strategy."""

    def __init__(self):
        """Initialize academic search strategy."""
        super().__init__("academic_search")

    async def discover(self, intent) -> List[DiscoveredSource]:
        """Discover academic sources.

        Args:
            intent: ClarifiedIntent object

        Returns:
            List of academic DiscoveredSource objects
        """
        query = getattr(intent, "original_query", "")
        raw_results = await self._execute_search(query)

        sources = []
        for result in raw_results:
            relevance = self._calculate_relevance(result, intent)
            source = DiscoveredSource(
                url=result.get("url", ""),
                title=result.get("title", ""),
                description=result.get("snippet", ""),
                relevance_score=relevance,
                source_type=SourceType.ACADEMIC
            )
            sources.append(source)

        sources = self._deduplicate(sources)
        sources = self._rank_by_relevance(sources)
        return sources


class DocumentationSearchStrategy(SourceDiscoveryStrategy):
    """Documentation search discovery strategy."""

    def __init__(self):
        """Initialize documentation search strategy."""
        super().__init__("documentation_search")

    async def discover(self, intent) -> List[DiscoveredSource]:
        """Discover documentation sources.

        Args:
            intent: ClarifiedIntent object

        Returns:
            List of documentation DiscoveredSource objects
        """
        query = getattr(intent, "original_query", "")
        raw_results = await self._execute_search(query)

        sources = []
        for result in raw_results:
            relevance = self._calculate_relevance(result, intent)
            source = DiscoveredSource(
                url=result.get("url", ""),
                title=result.get("title", ""),
                description=result.get("snippet", ""),
                relevance_score=relevance,
                source_type=SourceType.DOCUMENTATION
            )
            sources.append(source)

        sources = self._deduplicate(sources)
        sources = self._rank_by_relevance(sources)
        return sources


class SourceDiscovery:
    """Main source discovery coordinator."""

    def __init__(self, strategy: Optional[SourceDiscoveryStrategy] = None):
        """Initialize source discovery.

        Args:
            strategy: Discovery strategy to use
        """
        self.sources: List[Source] = []
        self.strategy = strategy or SourceDiscoveryStrategy()

    def discover(self, query: DiscoveryQuery) -> List[Source]:
        """Discover sources based on query (legacy sync method)."""
        return []

    def filter_sources(self, sources: List[Source], **kwargs) -> List[Source]:
        """Filter sources based on criteria."""
        return sources


__all__ = [
    "AcademicSearchStrategy",
    "DocumentationSearchStrategy",
    "DiscoveredSource",
    "SourceType",
    "Source",
    "DiscoveryQuery",
    "SourceDiscovery",
    "SourceDiscoveryStrategy",
    "WebSearchStrategy",
]

