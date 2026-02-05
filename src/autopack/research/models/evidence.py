from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from autopack.research.models.enums import EvidenceType


class Evidence:
    def __init__(
        self,
        source: str = None,
        evidence_type: EvidenceType = None,
        relevance: float = None,
        publication_date: datetime = None,
        content: str = None,
        citation: "Citation" = None,
        metadata: Dict[str, Any] = None,
        tags: List[str] = None,
    ):
        # Support both old and new API
        self.source = source
        self.content = content
        self.evidence_type = evidence_type
        self.relevance = relevance
        self.publication_date = publication_date
        self.citation = citation
        self.metadata = metadata or {}
        self.tags = tags or []

    def is_recent(self) -> bool:
        """Check if the evidence is recent (within the last 5 years)."""
        if self.publication_date is None:
            return True
        return (datetime.now() - self.publication_date).days <= 5 * 365

    def is_valid(self) -> bool:
        """Validate the evidence based on type and relevance."""
        if self.relevance is None:
            return True
        return self.evidence_type in EvidenceType and self.relevance > 0.5

    def __repr__(self):
        return (
            f"Evidence(source={self.source}, type={self.evidence_type}, "
            f"relevance={self.relevance}, publication_date={self.publication_date})"
        )


# Example usage:
# evidence = Evidence(
#     source="https://example.com/research-paper",
#     evidence_type=EvidenceType.EMPIRICAL,
#     relevance=0.8,
#     publication_date=datetime(2023, 5, 17)
# )
# print(evidence.is_recent())  # True if within 5 years
# print(evidence.is_valid())   # True if relevance > 0.5

# This model ensures that all evidence used in research is both recent and valid,
# supporting the integrity and credibility of the research findings.


# Compat shim for Citation (missing from original implementation)
@dataclass
class Citation:
    """Citation model for research sources."""

    source: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    publication_date: Optional[datetime] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    publication: Optional[str] = None  # For social media/web sources
    year: Optional[int] = None  # For year-based citations
