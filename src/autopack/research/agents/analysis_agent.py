"""
Analysis agent for Chunk 2B.

Responsibilities:
- aggregate findings by type/category
- deduplicate content
- identify gaps (technical, UX, market, competition)
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


class AnalysisAgent:
    def __init__(self):
        pass

    # === API used by existing tests ===
    def aggregate_findings(self, findings: Sequence[Mapping[str, Any]]) -> Dict[str, List[Mapping[str, Any]]]:
        aggregated: Dict[str, List[Mapping[str, Any]]] = {}
        for f in findings:
            t = str(f.get("type", "unknown"))
            aggregated.setdefault(t, []).append(f)
        return aggregated

    def deduplicate_content(self, contents: Sequence[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for c in contents:
            if c not in seen:
                out.append(c)
                seen.add(c)
        return out

    def identify_gaps(self, findings: Sequence[Mapping[str, Any]], required_types: Sequence[str]) -> List[str]:
        present = {str(f.get("type", "unknown")) for f in findings}
        gaps = [t for t in required_types if t not in present]
        return gaps

    # === Higher-level API ===
    def analyze(self, categorized: Mapping[str, Iterable[Mapping[str, Any]]]) -> Dict[str, Any]:
        required = ["technical", "ux", "market", "competition"]
        present = [k for k, v in categorized.items() if list(v)]
        gaps = [k for k in required if k not in present]
        confidence = self._confidence_score(categorized)
        return {"gaps": gaps, "confidence": confidence}

    def _confidence_score(self, categorized: Mapping[str, Iterable[Mapping[str, Any]]]) -> float:
        # Simple deterministic proxy: more categories with data => higher confidence
        non_empty = 0
        for v in categorized.values():
            if list(v):
                non_empty += 1
        return min(1.0, non_empty / 4.0)


