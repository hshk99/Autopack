"""Research Models - Data models for research subsystem.

This module provides data models for the research subsystem including Evidence,
Citation, and ResearchReport. These models have validation logic to ensure data quality.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Import enums
from autopack.research.models.enums import (EvidenceType, ResearchStage,
                                            ValidationStatus)

# Import ResearchQuery from research_phase module
try:
    from autopack.phases.research_phase import ResearchQuery as _ResearchQuery

    ResearchQuery = _ResearchQuery
except ImportError:

    @dataclass
    class ResearchQuery:
        """Research query model."""

        query: str
        priority: int = 1
        required: bool = False
        context: Dict[str, Any] = field(default_factory=dict)


class EvidenceQuality(Enum):
    """Evidence quality levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class Citation:
    """Citation model for research sources.

    Args:
        source_url: URL of the source (required, must be valid URL)
        title: Title of the source
        author: Author name(s)
        accessed_at: When the source was accessed

    Raises:
        ValueError: If source_url is not a valid URL
    """

    source_url: str
    title: str = ""
    author: str = ""
    accessed_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate citation after initialization."""
        # Validate URL format
        try:
            result = urlparse(self.source_url)
            if not all([result.scheme, result.netloc]):
                raise ValueError(f"Invalid URL format: {self.source_url}")
        except Exception as e:
            raise ValueError(f"Invalid URL format: {self.source_url}") from e


@dataclass
class Evidence:
    """Evidence model for research claims.

    Args:
        content: The evidence text content (required)
        citations: List of citations supporting this evidence (required, non-empty)
        quality: Quality level of the evidence

    Raises:
        ValueError: If citations list is empty
    """

    content: str
    citations: List[Citation]
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN

    def __post_init__(self):
        """Validate evidence after initialization."""
        if not self.citations:
            raise ValueError("Evidence must have at least one citation")


@dataclass
class ResearchReport:
    """Research report model.

    Args:
        query: Original research query
        summary: Summary of findings
        evidence: List of evidence items
        conclusions: List of conclusion statements
    """

    query: str
    summary: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    conclusions: List[str] = field(default_factory=list)


# Export all symbols that tests might import
__all__ = [
    "Evidence",
    "Citation",
    "EvidenceQuality",
    "EvidenceType",
    "ResearchStage",
    "ValidationStatus",
    "ResearchQuery",
    "ResearchReport",
]
