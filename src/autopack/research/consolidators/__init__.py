"""Research data consolidation module.

This module provides utilities for consolidating research findings through
sanitization, deduplication, and categorization.
"""

from .research_data_consolidator import (
    ResearchDataConsolidator,
    ConsolidatedFinding,
    ConsolidationResult,
)

__all__ = [
    "ResearchDataConsolidator",
    "ConsolidatedFinding",
    "ConsolidationResult",
]
