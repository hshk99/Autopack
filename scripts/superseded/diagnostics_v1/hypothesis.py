"""
Lightweight hypothesis and evidence tracking for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Hypothesis:
    hypothesis: str
    confidence: float = 0.2
    evidence: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    outcome: Optional[str] = None

    def add_evidence(self, item: str) -> None:
        if item:
            self.evidence.append(item)

    def add_action(self, item: str) -> None:
        if item:
            self.actions.append(item)

    def set_outcome(self, outcome: str, confidence: Optional[float] = None) -> None:
        self.outcome = outcome
        if confidence is not None:
            self.confidence = confidence


class HypothesisLedger:
    """In-memory ledger of hypotheses for a diagnostic session."""

    def __init__(self) -> None:
        self.items: List[Hypothesis] = []

    def new(self, hypothesis: str, confidence: float = 0.2) -> Hypothesis:
        entry = Hypothesis(hypothesis=hypothesis, confidence=confidence)
        self.items.append(entry)
        return entry

    def summarize(self) -> str:
        if not self.items:
            return "No hypotheses recorded."
        parts = []
        for idx, item in enumerate(self.items, start=1):
            evidence = "; ".join(item.evidence[:3]) if item.evidence else "no evidence yet"
            actions = "; ".join(item.actions[:3]) if item.actions else "no actions yet"
            outcome = item.outcome or "pending"
            parts.append(
                f"{idx}) {item.hypothesis} (conf={item.confidence:.2f}) "
                f"evidence={evidence}; actions={actions}; outcome={outcome}"
            )
        return " | ".join(parts)
