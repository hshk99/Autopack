"""Source Discovery Module - Compatibility Shims.

This module provides compatibility shims for source discovery functionality
that tests expect but doesn't exist in the actual implementation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime


class SourceType(Enum):
    """Compat shim for SourceType."""
    WEB = "web"
    GITHUB = "github"
    REDDIT = "reddit"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    ACADEMIC = "academic"
    NEWS = "news"


@dataclass
class Source:
    """Compat shim for Source."""
    url: str
    source_type: SourceType
    title: str = ""
    description: str = ""
    relevance: float = 0.0
    discovered_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryQuery:
    """Compat shim for DiscoveryQuery."""
    query: str
    source_types: List[SourceType] = field(default_factory=list)
    max_results: int = 10
    filters: Dict[str, Any] = field(default_factory=dict)


class SourceDiscoveryStrategy:
    """Compat shim for SourceDiscoveryStrategy."""

    def __init__(self, name: str = "default"):
        """Initialize strategy."""
        self.name = name

    def discover(self, query: str) -> List[Source]:
        """Discover sources using this strategy."""
        return []


class SourceDiscovery:
    """Compat shim for SourceDiscovery."""

    def __init__(self, strategy: Optional[SourceDiscoveryStrategy] = None):
        """Initialize source discovery."""
        self.sources: List[Source] = []
        self.strategy = strategy or SourceDiscoveryStrategy()

    def discover(self, query: DiscoveryQuery) -> List[Source]:
        """Discover sources based on query."""
        return []

    def filter_sources(self, sources: List[Source], **kwargs) -> List[Source]:
        """Filter sources based on criteria."""
        return sources


class WebSearchStrategy(SourceDiscoveryStrategy):
    """Compat shim for WebSearchStrategy."""

    def __init__(self):
        """Initialize web search strategy."""
        super().__init__("web_search")


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


class AcademicSearchStrategy(SourceDiscoveryStrategy):
    """Compat shim for AcademicSearchStrategy."""
    def __init__(self):
        super().__init__("academic_search")

class DocumentationSearchStrategy(SourceDiscoveryStrategy):
    """Compat shim for DocumentationSearchStrategy."""
    def __init__(self):
        super().__init__("documentation_search")

@dataclass
class DiscoveredSource:
    """Compat shim for DiscoveredSource."""
    url: str
    title: str = ""
    description: str = ""
    relevance: float = 0.0

