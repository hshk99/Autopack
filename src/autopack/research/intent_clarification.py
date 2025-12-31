"""Intent Clarification Module - Compatibility Shims.

This module provides compatibility shims for intent clarification functionality
that tests expect but doesn't exist in the actual implementation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClarifiedIntent:
    """Compat shim for ClarifiedIntent."""
    original_query: str
    clarified_query: str
    keywords: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    suggestions: List[str] = field(default_factory=list)


class IntentClarificationAgent:
    """Compat shim for IntentClarificationAgent."""

    def __init__(self):
        """Initialize intent clarification agent."""
        pass

    def clarify(self, query: str, context: Optional[Dict[str, Any]] = None) -> ClarifiedIntent:
        """Clarify user intent from query."""
        return ClarifiedIntent(
            original_query=query,
            clarified_query=query,
            context=context or {},
        )


__all__ = [
    "ClarifiedIntent",
    "IntentClarificationAgent",
]
