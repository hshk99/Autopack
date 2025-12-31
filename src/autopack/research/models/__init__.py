"""Research Models - Compatibility Shims for Test Collection.

This module provides minimal exports to allow research tests to collect cleanly.
The research subsystem has API drift and is quarantined (see RESEARCH_QUARANTINE.md).

These are compatibility shims to prevent collection errors when tests try to import
missing symbols. Tests are marked with @pytest.mark.research and deselected by default.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

# Import real models where they exist
try:
    from autopack.research.models.evidence import Evidence as _Evidence
    from autopack.research.models.enums import EvidenceType, ResearchStage, ValidationStatus

    # Re-export real Evidence
    Evidence = _Evidence
except ImportError:
    # Fallback shim if evidence.py has issues
    @dataclass
    class Evidence:
        """Compat shim for Evidence model."""
        source: str
        evidence_type: str
        relevance: float
        publication_date: datetime

    class EvidenceType(Enum):
        """Compat shim for EvidenceType enum."""
        EMPIRICAL = "empirical"
        THEORETICAL = "theoretical"
        STATISTICAL = "statistical"
        ANECDOTAL = "anecdotal"


# Import ResearchQuery from research_phase module
try:
    from autopack.phases.research_phase import ResearchQuery as _ResearchQuery
    ResearchQuery = _ResearchQuery
except ImportError:
    # Fallback shim if research_phase has issues
    @dataclass
    class ResearchQuery:
        """Compat shim for ResearchQuery."""
        query: str
        priority: int = 1
        required: bool = False
        context: Dict[str, Any] = field(default_factory=dict)


# Compat shims for missing symbols expected by tests
@dataclass
class Citation:
    """Compat shim for Citation model (missing from original implementation)."""
    source: str
    title: str = ""
    authors: List[str] = field(default_factory=list)
    publication_date: Optional[datetime] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceQuality(Enum):
    """Compat shim for EvidenceQuality enum (missing from original implementation)."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


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


@dataclass
class ResearchReport:
    """Compat shim for ResearchReport."""
    title: str
    content: str = ""
    evidence: List[Any] = field(default_factory=list)
    citations: List[Any] = field(default_factory=list)

