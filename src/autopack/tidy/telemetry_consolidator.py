"""Consolidates telemetry insights into SOT ledgers."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..memory.memory_service import MemoryService


class TelemetryConsolidator:
    """Consolidates high-signal telemetry into SOT files."""

    def __init__(
        self,
        memory_service: Optional[MemoryService] = None,
        sot_root: Optional[Path] = None,
    ):
        self._memory = memory_service or MemoryService()
        self._sot_root = sot_root or Path("docs")

    def consolidate_learned_rules(
        self,
        min_occurrences: int = 3,
        min_confidence: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Extract recurring patterns into LEARNED_RULES.json.

        Args:
            min_occurrences: Minimum number of occurrences for a pattern
            min_confidence: Minimum confidence score (0.0-1.0)

        Returns:
            List of high-signal patterns extracted
        """
        # Ensure docs directory exists
        self._sot_root.mkdir(parents=True, exist_ok=True)

        # Query all telemetry insights - search for patterns across all insights
        all_insights = self._memory.store.scroll(
            collection="run_summaries",
            limit=1000,
        )

        # Also search error collection for failure patterns
        error_insights = self._memory.store.scroll(
            collection="errors_ci",
            limit=1000,
        )

        # Combine both sources
        all_insights.extend(error_insights)

        # Group by pattern
        patterns = self._extract_patterns(all_insights)

        # Filter by occurrence threshold
        high_signal_patterns = [
            p
            for p in patterns
            if p["occurrences"] >= min_occurrences and p["confidence"] >= min_confidence
        ]

        # Write to LEARNED_RULES.json
        learned_rules_path = self._sot_root / "LEARNED_RULES.json"
        existing_rules = self._load_existing_rules(learned_rules_path)

        new_rules = self._merge_rules(existing_rules, high_signal_patterns)

        with open(learned_rules_path, "w") as f:
            json.dump(new_rules, f, indent=2)

        return high_signal_patterns

    def append_to_debug_log(self, insights: List[Dict[str, Any]]) -> int:
        """Append significant insights to DEBUG_LOG.md.

        Args:
            insights: List of insights to append

        Returns:
            Number of insights appended
        """
        debug_log_path = self._sot_root / "DEBUG_LOG.md"

        # Ensure docs directory exists
        self._sot_root.mkdir(parents=True, exist_ok=True)

        # Filter for significant insights (high severity or high confidence)
        significant = [
            i for i in insights if i.get("severity") == "high" or i.get("confidence", 0) >= 0.8
        ]

        if not significant:
            return 0

        # Create or append to debug log
        mode = "a" if debug_log_path.exists() else "w"
        with open(debug_log_path, mode) as f:
            if mode == "w":
                f.write("# Debug Log\n\nTelemetry insights and high-priority issues.\n")
            f.write(f"\n\n## Telemetry Insights ({datetime.now().isoformat()})\n\n")
            for insight in significant:
                insight_type = insight.get("type", "unknown")
                content = insight.get("content", insight.get("summary", ""))
                f.write(f"- **{insight_type}**: {content}\n")

        return len(significant)

    def _extract_patterns(self, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract recurring patterns from insights.

        Args:
            insights: List of insight documents from memory

        Returns:
            List of pattern dictionaries with occurrence counts
        """
        # Group similar insights
        patterns: Dict[str, Dict[str, Any]] = {}
        for insight in insights:
            payload = insight.get("payload", insight)
            # Simple pattern extraction from payload
            key = self._get_pattern_key(payload)
            if key not in patterns:
                patterns[key] = {
                    "pattern": key,
                    "examples": [],
                    "occurrences": 0,
                    "confidence": 0.0,
                }
            patterns[key]["examples"].append(payload)
            patterns[key]["occurrences"] += 1

        # Calculate confidence based on occurrence frequency
        for pattern in patterns.values():
            # Confidence increases with occurrences (max 1.0)
            pattern["confidence"] = min(1.0, pattern["occurrences"] / 10.0)

        return list(patterns.values())

    def _get_pattern_key(self, insight: Dict[str, Any]) -> str:
        """Extract pattern key from insight.

        Args:
            insight: Single insight document

        Returns:
            Pattern key string
        """
        # Extract key from various insight types
        summary = insight.get("summary", "")
        error_type = insight.get("error_type", "")
        description = insight.get("description", "")
        hint = insight.get("hint", "")

        # Use the first non-empty field
        text = summary or error_type or description or hint or "unknown"

        # Simple implementation: use first 5 words as pattern
        words = text.lower().split()[:5]
        return " ".join(words) if words else "unknown"

    def _load_existing_rules(self, path: Path) -> Dict[str, Any]:
        """Load existing LEARNED_RULES.json.

        Args:
            path: Path to LEARNED_RULES.json

        Returns:
            Dictionary with existing rules structure
        """
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                # If file is corrupted, return default structure
                pass
        return {
            "version": "1.0",
            "description": "Patterns learned from telemetry analysis. Auto-generated by tidy_telemetry_to_sot.py",
            "rules": [],
            "last_updated": None,
        }

    def _merge_rules(
        self,
        existing: Dict[str, Any],
        new_patterns: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge new patterns into existing rules.

        Args:
            existing: Existing rules dictionary
            new_patterns: New patterns to merge

        Returns:
            Merged rules dictionary
        """
        existing["last_updated"] = datetime.now().isoformat()

        existing_patterns = {r["pattern"]: r for r in existing.get("rules", [])}

        for pattern in new_patterns:
            pattern_key = pattern["pattern"]
            if pattern_key not in existing_patterns:
                existing["rules"].append(
                    {
                        "pattern": pattern_key,
                        "occurrences": pattern["occurrences"],
                        "confidence": pattern["confidence"],
                        "added": datetime.now().isoformat(),
                    }
                )
            else:
                # Update existing pattern with new counts
                existing_patterns[pattern_key]["occurrences"] = pattern["occurrences"]
                existing_patterns[pattern_key]["confidence"] = pattern["confidence"]

        return existing
