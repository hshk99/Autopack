"""Historical Learning Database.

Persists learnings across discovery cycles:
- Improvement outcomes (implemented, blocked, abandoned)
- Cycle metrics (duration, success rate, blocking issues)
- Pattern correlations (which phases fail together)

This module bridges the insight->memory link in the self-improvement loop
by storing structured learning data that can inform future task prioritization
and improvement suggestions.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Valid improvement outcomes
VALID_OUTCOMES = frozenset(
    {"implemented", "blocked", "abandoned", "in_progress", "pending", "partial"}
)

# Valid priority levels
VALID_PRIORITIES = frozenset({"critical", "high", "medium", "low"})


class LearningDatabase:
    """Persistent database for cross-cycle learnings.

    This class stores and queries historical data about improvement outcomes,
    cycle metrics, and pattern correlations. Data is persisted to a JSON file
    and loaded on initialization.

    Attributes:
        db_path: Path to the JSON file storing learning data.
    """

    # Schema version for migration compatibility
    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str) -> None:
        """Initialize the LearningDatabase.

        Args:
            db_path: Path to the JSON file for storing learning data.
                Will be created if it doesn't exist.
        """
        self.db_path = Path(db_path)
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load data from the database file."""
        if not self.db_path.exists():
            logger.debug("Learning database not found, initializing empty: %s", self.db_path)
            self._data = self._create_empty_schema()
            return

        try:
            with open(self.db_path, encoding="utf-8") as f:
                self._data = json.load(f)

            # Validate and migrate schema if needed
            self._migrate_schema()

            logger.debug(
                "Loaded learning database with %d improvements, %d cycles",
                len(self._data.get("improvements", {})),
                len(self._data.get("cycles", {})),
            )
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse learning database %s: %s", self.db_path, e)
            self._data = self._create_empty_schema()
        except OSError as e:
            logger.warning("Failed to read learning database %s: %s", self.db_path, e)
            self._data = self._create_empty_schema()

    def _create_empty_schema(self) -> dict[str, Any]:
        """Create an empty database schema."""
        return {
            "schema_version": self.SCHEMA_VERSION,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "improvements": {},
            "cycles": {},
            "patterns": {
                "phase_correlations": {},
                "blocking_reasons": {},
                "category_success_rates": {},
            },
        }

    def _migrate_schema(self) -> None:
        """Migrate data to current schema version if needed."""
        current_version = self._data.get("schema_version", 0)

        if current_version < self.SCHEMA_VERSION:
            logger.info(
                "Migrating learning database from version %d to %d",
                current_version,
                self.SCHEMA_VERSION,
            )

            # Add missing top-level keys
            if "improvements" not in self._data:
                self._data["improvements"] = {}
            if "cycles" not in self._data:
                self._data["cycles"] = {}
            if "patterns" not in self._data:
                self._data["patterns"] = {
                    "phase_correlations": {},
                    "blocking_reasons": {},
                    "category_success_rates": {},
                }

            self._data["schema_version"] = self.SCHEMA_VERSION
            self._save()

    def _save(self) -> bool:
        """Persist data to the database file.

        Returns:
            True if save was successful, False otherwise.
        """
        self._data["updated_at"] = datetime.now().isoformat()

        try:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False, default=str)
                f.write("\n")

            logger.debug("Saved learning database to: %s", self.db_path)
            return True

        except OSError as e:
            logger.error("Failed to save learning database to %s: %s", self.db_path, e)
            return False

    def record_cycle_outcome(
        self,
        cycle_id: str,
        metrics: dict[str, Any],
    ) -> bool:
        """Store outcome of a discovery cycle.

        Args:
            cycle_id: Unique identifier for the cycle.
            metrics: Dictionary containing cycle metrics. Expected keys:
                - phases_completed: Number of phases completed
                - phases_blocked: Number of phases that were blocked
                - total_nudges: Total nudges during the cycle
                - total_escalations: Total escalations during the cycle
                - duration_hours: Duration of the cycle in hours
                - completion_rate: Ratio of completed phases (0.0-1.0)

        Returns:
            True if recording was successful, False otherwise.
        """
        if not cycle_id:
            logger.warning("Cannot record cycle outcome: empty cycle_id")
            return False

        timestamp = datetime.now().isoformat()

        cycle_record = {
            "cycle_id": cycle_id,
            "recorded_at": timestamp,
            "metrics": {
                "phases_completed": metrics.get("phases_completed", 0),
                "phases_blocked": metrics.get("phases_blocked", 0),
                "total_nudges": metrics.get("total_nudges", 0),
                "total_escalations": metrics.get("total_escalations", 0),
                "duration_hours": metrics.get("duration_hours", 0.0),
                "completion_rate": metrics.get("completion_rate", 0.0),
            },
            "blocking_reasons": metrics.get("blocking_reasons", []),
            "improvements_attempted": metrics.get("improvements_attempted", []),
        }

        self._data["cycles"][cycle_id] = cycle_record

        # Update pattern correlations
        self._update_pattern_correlations(cycle_record)

        logger.info(
            "Recorded cycle outcome: %s (completion_rate=%.1f%%)",
            cycle_id,
            cycle_record["metrics"]["completion_rate"] * 100,
        )

        return self._save()

    def record_improvement_outcome(
        self,
        imp_id: str,
        outcome: str,
        notes: str = "",
        category: str | None = None,
        priority: str | None = None,
        cycle_id: str | None = None,
    ) -> bool:
        """Track whether an improvement succeeded or why it failed.

        Args:
            imp_id: Improvement identifier (e.g., "IMP-MEM-001").
            outcome: One of: "implemented", "blocked", "abandoned",
                "in_progress", "pending", "partial".
            notes: Additional notes about the outcome.
            category: Category of the improvement (e.g., "memory", "telemetry").
            priority: Priority level (e.g., "critical", "high", "medium", "low").
            cycle_id: Optional cycle ID if this improvement was part of a cycle.

        Returns:
            True if recording was successful, False otherwise.
        """
        if not imp_id:
            logger.warning("Cannot record improvement outcome: empty imp_id")
            return False

        outcome_lower = outcome.lower()
        if outcome_lower not in VALID_OUTCOMES:
            logger.warning(
                "Invalid outcome '%s' for improvement %s. Valid: %s",
                outcome,
                imp_id,
                VALID_OUTCOMES,
            )
            return False

        timestamp = datetime.now().isoformat()

        # Get or create improvement record
        if imp_id not in self._data["improvements"]:
            self._data["improvements"][imp_id] = {
                "imp_id": imp_id,
                "category": category,
                "priority": priority,
                "first_seen": timestamp,
                "outcome_history": [],
            }

        imp_record = self._data["improvements"][imp_id]

        # Update category/priority if provided
        if category:
            imp_record["category"] = category
        if priority:
            imp_record["priority"] = priority

        # Add outcome to history
        outcome_entry = {
            "outcome": outcome_lower,
            "recorded_at": timestamp,
            "notes": notes,
            "cycle_id": cycle_id,
        }
        imp_record["outcome_history"].append(outcome_entry)

        # Update current outcome
        imp_record["current_outcome"] = outcome_lower
        imp_record["last_updated"] = timestamp

        # Update category success rates
        if category:
            self._update_category_success_rate(category, outcome_lower)

        logger.info(
            "Recorded improvement outcome: %s -> %s (category=%s)",
            imp_id,
            outcome_lower,
            category or "unknown",
        )

        return self._save()

    def _update_pattern_correlations(self, cycle_record: dict[str, Any]) -> None:
        """Update pattern correlation data from a cycle record."""
        patterns = self._data["patterns"]

        # Track blocking reasons
        for reason in cycle_record.get("blocking_reasons", []):
            if reason not in patterns["blocking_reasons"]:
                patterns["blocking_reasons"][reason] = {"count": 0, "cycles": []}
            patterns["blocking_reasons"][reason]["count"] += 1
            patterns["blocking_reasons"][reason]["cycles"].append(cycle_record["cycle_id"])

    def _update_category_success_rate(self, category: str, outcome: str) -> None:
        """Update success rate tracking for a category."""
        rates = self._data["patterns"]["category_success_rates"]

        if category not in rates:
            rates[category] = {"total": 0, "implemented": 0, "blocked": 0, "abandoned": 0}

        rates[category]["total"] += 1

        if outcome in ("implemented", "blocked", "abandoned"):
            rates[category][outcome] += 1

    def get_historical_patterns(self) -> dict[str, Any]:
        """Query past learnings for pattern matching.

        Returns:
            Dictionary containing:
            - blocking_reasons: Most common reasons for blocking
            - phase_correlations: Which phases tend to fail together
            - category_success_rates: Success rates by improvement category
            - recent_trends: Trends from recent cycles
        """
        patterns = self._data.get("patterns", {})
        cycles = self._data.get("cycles", {})
        improvements = self._data.get("improvements", {})

        # Sort blocking reasons by count
        blocking_sorted = sorted(
            patterns.get("blocking_reasons", {}).items(),
            key=lambda x: x[1].get("count", 0),
            reverse=True,
        )
        top_blocking_reasons = [
            {"reason": reason, "count": data["count"]} for reason, data in blocking_sorted[:10]
        ]

        # Calculate category success rates
        category_rates = {}
        for category, stats in patterns.get("category_success_rates", {}).items():
            total = stats.get("total", 0)
            if total > 0:
                implemented = stats.get("implemented", 0)
                category_rates[category] = {
                    "total": total,
                    "implemented": implemented,
                    "blocked": stats.get("blocked", 0),
                    "abandoned": stats.get("abandoned", 0),
                    "success_rate": round(implemented / total, 3),
                }

        # Calculate recent trends (last 10 cycles)
        sorted_cycles = sorted(
            cycles.values(),
            key=lambda x: x.get("recorded_at", ""),
            reverse=True,
        )
        recent_cycles = sorted_cycles[:10]

        if recent_cycles:
            avg_completion = sum(
                c.get("metrics", {}).get("completion_rate", 0) for c in recent_cycles
            ) / len(recent_cycles)
            avg_escalations = sum(
                c.get("metrics", {}).get("total_escalations", 0) for c in recent_cycles
            ) / len(recent_cycles)
            trend = {
                "sample_size": len(recent_cycles),
                "avg_completion_rate": round(avg_completion, 3),
                "avg_escalations": round(avg_escalations, 2),
            }
        else:
            trend = {"sample_size": 0}

        # Count improvement outcomes
        outcome_counts: Counter[str] = Counter()
        for imp in improvements.values():
            current = imp.get("current_outcome")
            if current:
                outcome_counts[current] += 1

        return {
            "top_blocking_reasons": top_blocking_reasons,
            "category_success_rates": category_rates,
            "recent_trends": trend,
            "improvement_outcome_summary": dict(outcome_counts),
            "total_improvements_tracked": len(improvements),
            "total_cycles_tracked": len(cycles),
        }

    def get_success_rate(self, category: str) -> float:
        """Calculate success rate for improvement category.

        Args:
            category: The improvement category to query.

        Returns:
            Success rate as a float between 0.0 and 1.0.
            Returns 0.0 if no data is available for the category.
        """
        rates = self._data.get("patterns", {}).get("category_success_rates", {})

        if category not in rates:
            logger.debug("No success rate data for category: %s", category)
            return 0.0

        stats = rates[category]
        total = stats.get("total", 0)

        if total == 0:
            return 0.0

        implemented = stats.get("implemented", 0)
        return round(implemented / total, 3)

    def get_improvement(self, imp_id: str) -> dict[str, Any] | None:
        """Get a specific improvement record.

        Args:
            imp_id: Improvement identifier.

        Returns:
            The improvement record or None if not found.
        """
        return self._data.get("improvements", {}).get(imp_id)

    def get_cycle(self, cycle_id: str) -> dict[str, Any] | None:
        """Get a specific cycle record.

        Args:
            cycle_id: Cycle identifier.

        Returns:
            The cycle record or None if not found.
        """
        return self._data.get("cycles", {}).get(cycle_id)

    def list_improvements(
        self,
        category: str | None = None,
        outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        """List improvements with optional filtering.

        Args:
            category: Filter by category if provided.
            outcome: Filter by current outcome if provided.

        Returns:
            List of improvement records matching filters.
        """
        improvements = list(self._data.get("improvements", {}).values())

        if category:
            improvements = [imp for imp in improvements if imp.get("category") == category]

        if outcome:
            improvements = [imp for imp in improvements if imp.get("current_outcome") == outcome]

        return improvements

    def list_cycles(self, limit: int | None = None) -> list[dict[str, Any]]:
        """List cycles ordered by recency.

        Args:
            limit: Maximum number of cycles to return.

        Returns:
            List of cycle records, most recent first.
        """
        cycles = sorted(
            self._data.get("cycles", {}).values(),
            key=lambda x: x.get("recorded_at", ""),
            reverse=True,
        )

        if limit is not None and limit > 0:
            cycles = cycles[:limit]

        return cycles

    def get_likely_blockers(self, category: str | None = None) -> list[dict[str, Any]]:
        """Predict what might block improvements in a category.

        Args:
            category: Optional category to filter by.

        Returns:
            List of likely blockers with their frequency.
        """
        patterns = self._data.get("patterns", {})
        blocking_reasons = patterns.get("blocking_reasons", {})

        # Get improvements that were blocked
        blocked_imps = self.list_improvements(category=category, outcome="blocked")

        # Aggregate blocking reasons
        reason_counts: Counter[str] = Counter()
        for imp in blocked_imps:
            for entry in imp.get("outcome_history", []):
                if entry.get("outcome") == "blocked" and entry.get("notes"):
                    reason_counts[entry["notes"]] += 1

        # Combine with global blocking reasons
        for reason, data in blocking_reasons.items():
            reason_counts[reason] += data.get("count", 0)

        # Convert to list of dicts
        blockers = [
            {"reason": reason, "frequency": count, "likelihood": "high" if count >= 3 else "medium"}
            for reason, count in reason_counts.most_common(10)
        ]

        return blockers

    def export_data(self) -> dict[str, Any]:
        """Export the full database for backup or analysis.

        Returns:
            Copy of the complete database content.
        """
        return dict(self._data)

    def clear_all(self) -> bool:
        """Clear all data from the database.

        Returns:
            True if clear was successful, False otherwise.
        """
        logger.warning("Clearing all data from learning database")
        self._data = self._create_empty_schema()
        return self._save()
