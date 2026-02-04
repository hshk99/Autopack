"""
Compilation agent for Chunk 2B.

Responsibilities:
- deduplicate findings (best-effort similarity)
- categorize by type (technical, UX, market, competition)
- preserve citations/attribution (pass-through)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping

from autopack.research.gatherers.web_scraper import WebScraper
from autopack.research.security.prompt_sanitizer import PromptSanitizer, RiskLevel


@dataclass(frozen=True)
class Finding:
    type: str
    content: str
    source_url: str | None = None
    trust_tier: int | None = None
    extracted_at: str | None = None


class CompilationAgent:
    def __init__(self):
        self.scraper = WebScraper()
        # Initialize prompt sanitizer for injection prevention (BUILD-SECURITY)
        self.prompt_sanitizer = PromptSanitizer()

    # === API used by existing tests ===
    def compile_report(self, findings: List[Mapping[str, Any]]) -> str:
        return "\n".join([str(f.get("content", "")) for f in findings if f.get("content")])

    def categorize_by_type(
        self, findings: List[Mapping[str, Any]]
    ) -> Dict[str, List[Mapping[str, Any]]]:
        categorized: Dict[str, List[Mapping[str, Any]]] = {}
        for f in findings:
            t = str(f.get("type", "unknown"))
            categorized.setdefault(t, []).append(f)
        return categorized

    def generate_summary(self, findings: List[Mapping[str, Any]]) -> str:
        return f"Summary of findings: {len(findings)} items"

    # === More structured helpers (used for coverage/quality targets) ===
    def compile_content(self, urls: List[str]) -> Dict[str, Any]:
        texts: List[Dict[str, Any]] = []
        for u in urls:
            text = self.scraper.fetch_content(u)
            # Sanitize web-scraped content (BUILD-SECURITY: prevent prompt injection via scraped data)
            if text:
                text = self.prompt_sanitizer.sanitize_for_prompt(text, RiskLevel.MEDIUM)
            texts.append({"type": "web", "content": text, "source_url": u})
        return {"findings": texts}

    def deduplicate_findings(
        self, findings: Iterable[Mapping[str, Any]], *, threshold: int = 80
    ) -> List[Mapping[str, Any]]:
        """
        Best-effort fuzzy deduplication. If fuzzywuzzy isn't available, falls back to exact match.
        Keeps the first occurrence.
        """
        items = [dict(f) for f in findings]
        kept: List[Dict[str, Any]] = []

        def norm(s: str) -> str:
            return " ".join((s or "").lower().split())

        try:
            from fuzzywuzzy import fuzz  # type: ignore
        except Exception:  # pragma: no cover
            seen = set()
            for f in items:
                key = norm(str(f.get("content", "")))
                if key and key not in seen:
                    kept.append(f)
                    seen.add(key)
            return kept

        for f in items:
            c = norm(str(f.get("content", "")))
            if not c:
                continue
            is_dup = False
            for existing in kept:
                e = norm(str(existing.get("content", "")))
                if fuzz.ratio(c, e) >= threshold:
                    is_dup = True
                    # preserve citations if present
                    if existing.get("source_url") is None and f.get("source_url") is not None:
                        existing["source_url"] = f["source_url"]
                    break
            if not is_dup:
                kept.append(f)
        return kept

    def categorize(
        self, findings: Iterable[Mapping[str, Any]]
    ) -> Dict[str, List[Mapping[str, Any]]]:
        """
        Categorize into the 4 required buckets via keyword heuristics.
        """
        buckets = {"technical": [], "ux": [], "market": [], "competition": []}
        for f in findings:
            content = str(f.get("content", "")).lower()
            if any(
                k in content for k in ["latency", "architecture", "api", "database", "scalability"]
            ):
                buckets["technical"].append(f)
            elif any(
                k in content for k in ["ux", "user experience", "onboarding", "ui", "workflow"]
            ):
                buckets["ux"].append(f)
            elif any(
                k in content for k in ["market", "pricing", "tamagotchi", "demand", "segment"]
            ):
                buckets["market"].append(f)
            else:
                buckets["competition"].append(f)
        return buckets
