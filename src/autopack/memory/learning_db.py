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
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# Platform-specific file locking imports
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

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
            "successful_patterns": {},
            "project_history": [],
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
            # Add successful_patterns section for cross-project learning
            if "successful_patterns" not in self._data:
                self._data["successful_patterns"] = {}
            # Add project_history for tracking past projects
            if "project_history" not in self._data:
                self._data["project_history"] = []

            self._data["schema_version"] = self.SCHEMA_VERSION
            self._save()

    def _atomic_write_with_lock(self, data: dict[str, Any]) -> bool:
        """Write JSON atomically with file locking to prevent corruption.

        Uses a lock file and temp file pattern to ensure data durability:
        1. Acquire lock on lock file
        2. Write to temp file in same directory
        3. Sync data to disk
        4. Atomically replace original file
        5. Release lock

        This is cross-platform safe and prevents concurrent write corruption.

        Args:
            data: Dictionary to write as JSON.

        Returns:
            True if write was successful, False otherwise.
        """
        lock_file = self.db_path.with_suffix(".lock")

        # Acquire lock
        with open(lock_file, "w", encoding="utf-8") as lock_f:
            try:
                # Cross-platform locking
                if sys.platform == "win32":
                    msvcrt.locking(lock_f.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)

                # Write to temp file in same directory (ensures same filesystem)
                fd, temp_path = tempfile.mkstemp(
                    dir=self.db_path.parent,
                    prefix=f".{self.db_path.name}.",
                    suffix=".tmp",
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                        f.write("\n")
                        f.flush()
                        os.fsync(f.fileno())  # Ensure data is on disk
                    # Atomic replace (POSIX rename is atomic)
                    os.replace(temp_path, self.db_path)
                    return True
                except Exception:
                    # Clean up temp file on failure
                    if os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass
                    raise
            finally:
                # Release lock
                try:
                    if sys.platform == "win32":
                        msvcrt.locking(lock_f.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    def _save(self) -> bool:
        """Persist data to the database file with atomic writes and locking.

        Uses atomic write pattern with file locking to prevent corruption
        from concurrent writes or crashes during write operations.

        Returns:
            True if save was successful, False otherwise.
        """
        self._data["updated_at"] = datetime.now().isoformat()

        try:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Use atomic write with locking
            return self._atomic_write_with_lock(self._data)

        except (OSError, BlockingIOError) as e:
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

    # ========================================================================
    # Cross-Project Learning Pattern Methods
    # ========================================================================

    def store_pattern(
        self,
        pattern_id: str,
        pattern_data: dict[str, Any],
    ) -> bool:
        """Store an extracted pattern for cross-project learning.

        Args:
            pattern_id: Unique identifier for the pattern.
            pattern_data: Pattern data dictionary containing:
                - pattern_type: Type of pattern (tech_stack, architecture, etc.)
                - name: Human-readable name
                - description: Pattern description
                - success_rate: Success rate (0.0-1.0)
                - occurrence_count: Number of occurrences
                - confidence: Confidence level
                - components: List of pattern components
                - associated_project_types: Project types where pattern applies
                - success_factors: Factors contributing to success
                - risk_factors: Potential risk factors
                - recommended_for: Keywords for recommendation
                - avoid_for: Keywords to avoid

        Returns:
            True if storage was successful, False otherwise.
        """
        if not pattern_id:
            logger.warning("Cannot store pattern: empty pattern_id")
            return False

        timestamp = datetime.now().isoformat()

        # Initialize successful_patterns if needed
        if "successful_patterns" not in self._data:
            self._data["successful_patterns"] = {}

        # Store or update pattern
        self._data["successful_patterns"][pattern_id] = {
            "pattern_id": pattern_id,
            "stored_at": timestamp,
            "updated_at": timestamp,
            **pattern_data,
        }

        logger.info(
            "Stored pattern: %s (type=%s, success_rate=%.1f%%)",
            pattern_id,
            pattern_data.get("pattern_type", "unknown"),
            pattern_data.get("success_rate", 0) * 100,
        )

        return self._save()

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        """Get a specific pattern by ID.

        Args:
            pattern_id: Pattern identifier.

        Returns:
            The pattern data or None if not found.
        """
        return self._data.get("successful_patterns", {}).get(pattern_id)

    def list_patterns(
        self,
        pattern_type: str | None = None,
        min_success_rate: float | None = None,
        project_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List patterns with optional filtering.

        Args:
            pattern_type: Filter by pattern type if provided.
            min_success_rate: Filter by minimum success rate if provided.
            project_type: Filter by associated project type if provided.

        Returns:
            List of pattern records matching filters.
        """
        patterns = list(self._data.get("successful_patterns", {}).values())

        if pattern_type:
            patterns = [p for p in patterns if p.get("pattern_type") == pattern_type]

        if min_success_rate is not None:
            patterns = [p for p in patterns if p.get("success_rate", 0) >= min_success_rate]

        if project_type:
            patterns = [
                p
                for p in patterns
                if project_type.lower()
                in [t.lower() for t in p.get("associated_project_types", [])]
                or not p.get("associated_project_types")  # Include universal patterns
            ]

        return patterns

    def get_top_patterns(
        self,
        limit: int = 10,
        min_confidence: str = "medium",
    ) -> list[dict[str, Any]]:
        """Get top patterns by success rate and confidence.

        Args:
            limit: Maximum number of patterns to return.
            min_confidence: Minimum confidence level (low, medium, high).

        Returns:
            List of top patterns sorted by success rate.
        """
        confidence_order = {"experimental": 0, "low": 1, "medium": 2, "high": 3}
        min_conf_value = confidence_order.get(min_confidence.lower(), 1)

        patterns = [
            p
            for p in self._data.get("successful_patterns", {}).values()
            if confidence_order.get(p.get("confidence", "low"), 0) >= min_conf_value
        ]

        # Sort by success rate descending, then by occurrence count
        patterns.sort(
            key=lambda p: (p.get("success_rate", 0), p.get("occurrence_count", 0)),
            reverse=True,
        )

        return patterns[:limit]

    def get_patterns_for_context(
        self,
        context_keywords: list[str],
        project_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get patterns matching a project context.

        Args:
            context_keywords: Keywords describing the project context.
            project_type: Optional project type to filter by.

        Returns:
            List of relevant patterns with relevance scores.
        """
        patterns = self.list_patterns(project_type=project_type)
        scored_patterns: list[tuple[float, dict[str, Any]]] = []

        for pattern in patterns:
            score = 0.0

            # Score based on recommended_for matches
            recommended_for = pattern.get("recommended_for", [])
            for keyword in context_keywords:
                if keyword.lower() in [r.lower() for r in recommended_for]:
                    score += 0.3

            # Score based on avoid_for (negative)
            avoid_for = pattern.get("avoid_for", [])
            for keyword in context_keywords:
                if keyword.lower() in [a.lower() for a in avoid_for]:
                    score -= 0.4

            # Factor in success rate
            score += pattern.get("success_rate", 0) * 0.4

            # Only include patterns with positive relevance
            if score > 0:
                pattern_copy = dict(pattern)
                pattern_copy["relevance_score"] = round(score, 3)
                scored_patterns.append((score, pattern_copy))

        # Sort by score descending
        scored_patterns.sort(key=lambda x: x[0], reverse=True)

        return [p for _, p in scored_patterns]

    def update_pattern_metrics(
        self,
        pattern_id: str,
        new_occurrence: bool = False,
        was_successful: bool = True,
    ) -> bool:
        """Update pattern metrics based on new usage.

        Args:
            pattern_id: Pattern identifier to update.
            new_occurrence: Whether this is a new occurrence.
            was_successful: Whether the usage was successful.

        Returns:
            True if update was successful, False otherwise.
        """
        pattern = self._data.get("successful_patterns", {}).get(pattern_id)
        if not pattern:
            logger.warning("Pattern not found for metrics update: %s", pattern_id)
            return False

        if new_occurrence:
            old_count = pattern.get("occurrence_count", 0)
            old_success_rate = pattern.get("success_rate", 0)

            # Calculate new success rate
            old_successes = old_count * old_success_rate
            new_successes = old_successes + (1 if was_successful else 0)
            new_count = old_count + 1

            pattern["occurrence_count"] = new_count
            pattern["success_rate"] = round(new_successes / new_count, 3)
            pattern["updated_at"] = datetime.now().isoformat()
            pattern["last_seen"] = datetime.now().isoformat()

            # Update confidence based on new count
            if new_count >= 5:
                pattern["confidence"] = "high"
            elif new_count >= 3:
                pattern["confidence"] = "medium"
            else:
                pattern["confidence"] = "low"

            logger.info(
                "Updated pattern metrics: %s (count=%d, success_rate=%.1f%%)",
                pattern_id,
                new_count,
                pattern["success_rate"] * 100,
            )

        return self._save()

    def store_project_history(
        self,
        project_id: str,
        project_data: dict[str, Any],
    ) -> bool:
        """Store project data for historical analysis.

        Args:
            project_id: Unique project identifier.
            project_data: Project data dictionary containing:
                - project_type: Type of project
                - name: Project name
                - outcome: Project outcome
                - tech_stack: Technology stack used
                - architecture: Architecture decisions
                - monetization: Monetization strategy
                - deployment: Deployment configuration
                - lessons_learned: Key lessons

        Returns:
            True if storage was successful, False otherwise.
        """
        if not project_id:
            logger.warning("Cannot store project: empty project_id")
            return False

        timestamp = datetime.now().isoformat()

        # Initialize project_history if needed
        if "project_history" not in self._data:
            self._data["project_history"] = []

        # Remove existing entry for same project_id
        self._data["project_history"] = [
            p for p in self._data["project_history"] if p.get("project_id") != project_id
        ]

        # Add new entry
        project_record = {
            "project_id": project_id,
            "recorded_at": timestamp,
            "timestamp": timestamp,
            **project_data,
        }

        self._data["project_history"].append(project_record)

        logger.info(
            "Stored project history: %s (type=%s, outcome=%s)",
            project_id,
            project_data.get("project_type", "unknown"),
            project_data.get("outcome", "unknown"),
        )

        return self._save()

    def get_project_history(
        self,
        project_type: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get project history with optional filtering.

        Args:
            project_type: Filter by project type if provided.
            outcome: Filter by outcome if provided.
            limit: Maximum number of projects to return.

        Returns:
            List of project records matching filters.
        """
        projects = list(self._data.get("project_history", []))

        if project_type:
            projects = [p for p in projects if p.get("project_type") == project_type]

        if outcome:
            projects = [p for p in projects if p.get("outcome") == outcome]

        # Sort by timestamp descending (most recent first)
        projects.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        if limit is not None and limit > 0:
            projects = projects[:limit]

        return projects

    def get_cross_project_insights(self) -> dict[str, Any]:
        """Get cross-project learning insights.

        Returns:
            Dictionary containing:
            - total_patterns: Number of stored patterns
            - top_patterns: Highest success rate patterns
            - pattern_coverage: Patterns by type
            - project_history_summary: Summary of historical projects
            - recommended_approaches: Based on historical success
        """
        patterns = self._data.get("successful_patterns", {})
        history = self._data.get("project_history", [])

        # Calculate pattern coverage by type
        pattern_by_type: Counter[str] = Counter()
        for pattern in patterns.values():
            pattern_type = pattern.get("pattern_type", "unknown")
            pattern_by_type[pattern_type] += 1

        # Calculate project history summary
        outcome_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        for project in history:
            outcome_counts[project.get("outcome", "unknown")] += 1
            type_counts[project.get("project_type", "unknown")] += 1

        # Get top patterns
        top_patterns = self.get_top_patterns(limit=5, min_confidence="medium")

        # Generate recommended approaches based on successful patterns
        recommended = []
        for pattern in top_patterns:
            if pattern.get("success_rate", 0) >= 0.7:
                recommended.append(
                    {
                        "approach": pattern.get("name", "Unknown"),
                        "type": pattern.get("pattern_type", "unknown"),
                        "success_rate": pattern.get("success_rate", 0),
                        "basis": f"Based on {pattern.get('occurrence_count', 0)} occurrences",
                    }
                )

        return {
            "total_patterns": len(patterns),
            "top_patterns": top_patterns,
            "pattern_coverage": dict(pattern_by_type),
            "project_history_summary": {
                "total_projects": len(history),
                "by_outcome": dict(outcome_counts),
                "by_type": dict(type_counts),
            },
            "recommended_approaches": recommended,
        }
