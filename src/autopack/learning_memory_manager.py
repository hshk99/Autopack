"""Cross-cycle learning memory manager for Discovery Cycles.

Persists learnings across Discovery Cycles to enable the system to learn from
past improvement outcomes. Tracks which improvement types succeed, common failure
patterns, and optimal wave sizes.

Features:
- Record improvement outcomes (success/failure with details)
- Analyze success patterns for Phase 1 prioritization
- Identify failure patterns to avoid
- Calculate optimal wave size based on historical completion rates

Example:
    >>> manager = LearningMemoryManager(Path("LEARNING_MEMORY.json"))
    >>> manager.record_improvement_outcome(
    ...     "IMP-001",
    ...     success=True,
    ...     details={"type": "refactor", "complexity": "low"}
    ... )
    >>> manager.save()
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_STRUCTURE: dict[str, Any] = {
    "version": "1.0.0",
    "improvement_outcomes": [],
    "success_patterns": [],
    "failure_patterns": [],
    "wave_history": [],
    "last_updated": None,
}


class LearningMemoryManager:
    """Manages cross-cycle learning memory for Discovery Cycles."""

    def __init__(self, memory_path: Path) -> None:
        """Initialize with memory file path.

        Args:
            memory_path: Path to the LEARNING_MEMORY.json file.
        """
        self.memory_path = memory_path
        self._memory = self._load_or_create()

    def _load_or_create(self) -> dict[str, Any]:
        """Load existing memory or create new structure.

        Returns:
            Memory dictionary with all required fields.
        """
        if self.memory_path.exists():
            try:
                content = self.memory_path.read_text(encoding="utf-8")
                data = json.loads(content)
                logger.info(f"[LearningMemory] Loaded memory from {self.memory_path}")

                # Ensure all required keys exist (forward compatibility)
                for key, default_value in DEFAULT_MEMORY_STRUCTURE.items():
                    if key not in data:
                        data[key] = (
                            default_value.copy()
                            if isinstance(default_value, (list, dict))
                            else default_value
                        )

                return data
            except json.JSONDecodeError as e:
                logger.warning(
                    f"[LearningMemory] Failed to parse {self.memory_path}: {e}\n"
                    f"  Creating fresh memory structure."
                )
            except Exception as e:
                logger.warning(
                    f"[LearningMemory] Failed to load {self.memory_path}: {e}\n"
                    f"  Creating fresh memory structure."
                )

        logger.info(f"[LearningMemory] Creating new memory at {self.memory_path}")
        return {
            key: (value.copy() if isinstance(value, (list, dict)) else value)
            for key, value in DEFAULT_MEMORY_STRUCTURE.items()
        }

    def record_improvement_outcome(
        self, imp_id: str, success: bool, details: dict[str, Any] | None = None
    ) -> None:
        """Record whether an improvement succeeded or failed.

        Args:
            imp_id: The improvement identifier (e.g., "IMP-MEM-001").
            success: True if improvement succeeded, False otherwise.
            details: Optional dictionary with additional context (type, complexity,
                     error_message, etc.).
        """
        outcome = {
            "imp_id": imp_id,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }

        self._memory["improvement_outcomes"].append(outcome)
        logger.debug(
            f"[LearningMemory] Recorded outcome for {imp_id}: "
            f"{'success' if success else 'failure'}"
        )

        # Update patterns based on new outcome
        self._update_patterns()

    def _update_patterns(self) -> None:
        """Update success and failure patterns based on all outcomes."""
        outcomes = self._memory["improvement_outcomes"]
        if not outcomes:
            return

        # Analyze by improvement type prefix (e.g., "IMP-MEM", "IMP-TEL")
        success_by_type: Counter[str] = Counter()
        failure_by_type: Counter[str] = Counter()
        details_by_success: list[dict[str, Any]] = []
        details_by_failure: list[dict[str, Any]] = []

        for outcome in outcomes:
            imp_id = outcome.get("imp_id", "")
            # Extract type prefix (e.g., "IMP-MEM" from "IMP-MEM-001")
            parts = imp_id.split("-")
            if len(parts) >= 2:
                imp_type = f"{parts[0]}-{parts[1]}"
            else:
                imp_type = imp_id

            if outcome.get("success"):
                success_by_type[imp_type] += 1
                if outcome.get("details"):
                    details_by_success.append(outcome["details"])
            else:
                failure_by_type[imp_type] += 1
                if outcome.get("details"):
                    details_by_failure.append(outcome["details"])

        # Build success patterns
        self._memory["success_patterns"] = [
            {"type": imp_type, "count": count, "pattern": "high_success_rate"}
            for imp_type, count in success_by_type.most_common(10)
        ]

        # Build failure patterns
        self._memory["failure_patterns"] = [
            {"type": imp_type, "count": count, "pattern": "recurring_failure"}
            for imp_type, count in failure_by_type.most_common(10)
        ]

        # Extract common failure reasons from details
        failure_reasons: Counter[str] = Counter()
        for details in details_by_failure:
            if "error_type" in details:
                failure_reasons[details["error_type"]] += 1
            if "error_message" in details:
                # Extract first 50 chars of error message as pattern
                msg = str(details["error_message"])[:50]
                failure_reasons[msg] += 1

        # Add common error patterns to failure patterns
        for reason, count in failure_reasons.most_common(5):
            if count >= 2:  # Only include if seen multiple times
                self._memory["failure_patterns"].append(
                    {"type": "error_pattern", "pattern": reason, "count": count}
                )

    def get_success_patterns(self) -> list[dict[str, Any]]:
        """Return patterns of successful improvements for Phase 1 prioritization.

        Returns:
            List of success pattern dictionaries with type, count, and pattern info.
        """
        return self._memory.get("success_patterns", [])

    def get_failure_patterns(self) -> list[dict[str, Any]]:
        """Return common failure patterns to avoid.

        Returns:
            List of failure pattern dictionaries with type, count, and pattern info.
        """
        return self._memory.get("failure_patterns", [])

    def record_wave_completion(self, wave_size: int, completed: int, failed: int) -> None:
        """Record wave completion statistics for optimal sizing analysis.

        Args:
            wave_size: Total number of improvements in the wave.
            completed: Number of improvements that completed successfully.
            failed: Number of improvements that failed.
        """
        wave_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wave_size": wave_size,
            "completed": completed,
            "failed": failed,
            "completion_rate": completed / wave_size if wave_size > 0 else 0.0,
        }
        self._memory["wave_history"].append(wave_record)
        logger.debug(
            f"[LearningMemory] Recorded wave completion: "
            f"{completed}/{wave_size} ({wave_record['completion_rate']:.1%})"
        )

    def get_optimal_wave_size(self) -> dict[str, Any]:
        """Calculate optimal wave size based on historical completion rates.

        Analyzes the last 5 waves from wave_history and adjusts size recommendations
        based on completion rate thresholds:
        - Below 70%: Recommend reducing wave size by 2
        - Above 90%: Recommend increasing wave size by 2
        - 70-90%: Maintain current average size

        Returns:
            Dictionary with:
            - recommended_size: The recommended wave size
            - completion_rate: The calculated completion rate (if available)
            - rationale: Human-readable explanation of the recommendation
        """
        wave_history = self._memory.get("wave_history", [])

        if not wave_history:
            logger.debug("[LearningMemory] No wave history - returning default size of 3")
            return {"recommended_size": 3, "rationale": "No history - using default"}

        # Calculate completion rate from last 5 waves
        recent_waves = wave_history[-5:]
        total_phases = sum(w.get("wave_size", 0) for w in recent_waves)
        completed_phases = sum(w.get("completed", 0) for w in recent_waves)

        if total_phases == 0:
            logger.debug("[LearningMemory] No phase data - returning default size of 3")
            return {"recommended_size": 3, "rationale": "No phase data - using default"}

        completion_rate = completed_phases / total_phases
        current_avg_size = total_phases / len(recent_waves)

        if completion_rate < 0.70:
            new_size = max(1, int(current_avg_size - 2))
            rationale = f"Low completion rate ({completion_rate:.0%}) - reducing size"
        elif completion_rate > 0.90:
            new_size = int(current_avg_size + 2)
            rationale = f"High completion rate ({completion_rate:.0%}) - increasing size"
        else:
            new_size = int(current_avg_size)
            rationale = f"Good completion rate ({completion_rate:.0%}) - maintaining size"

        logger.debug(
            f"[LearningMemory] Adaptive wave size: {new_size} "
            f"(completion_rate={completion_rate:.2%})"
        )

        return {
            "recommended_size": new_size,
            "completion_rate": completion_rate,
            "rationale": rationale,
        }

    def get_improvement_history(self, imp_id: str) -> list[dict[str, Any]]:
        """Get historical outcomes for a specific improvement ID.

        Args:
            imp_id: The improvement identifier to look up.

        Returns:
            List of outcome records for this improvement.
        """
        return [
            outcome
            for outcome in self._memory.get("improvement_outcomes", [])
            if outcome.get("imp_id") == imp_id
        ]

    def get_type_success_rate(self, imp_type_prefix: str) -> float | None:
        """Get success rate for a specific improvement type.

        Args:
            imp_type_prefix: Type prefix (e.g., "IMP-MEM", "IMP-TEL").

        Returns:
            Success rate as a float (0.0 to 1.0), or None if no history.
        """
        outcomes = self._memory.get("improvement_outcomes", [])

        matching = [o for o in outcomes if o.get("imp_id", "").startswith(imp_type_prefix)]

        if not matching:
            return None

        successes = sum(1 for o in matching if o.get("success"))
        return successes / len(matching)

    def get_effectiveness_stats(self, imp_category: str | None = None) -> dict[str, Any]:
        """Get effectiveness statistics for improvement outcomes.

        Calculates metrics including:
        - Average time from PR creation to merge
        - Average CI pass rate during review
        - Average number of review cycles
        - Success rate by category

        Args:
            imp_category: Optional category prefix to filter by (e.g., "IMP-TEL").
                          If None, returns stats for all improvements.

        Returns:
            Dictionary with effectiveness statistics:
            {
                "total_outcomes": int,
                "successful": int,
                "failed": int,
                "success_rate": float,
                "avg_merge_time_hours": float | None,
                "avg_ci_pass_rate": float | None,
                "avg_review_cycles": float | None,
                "by_category": dict[str, dict]  # Per-category breakdown
            }
        """
        outcomes = self._memory.get("improvement_outcomes", [])

        # Filter by category if specified
        if imp_category:
            outcomes = [o for o in outcomes if o.get("imp_id", "").startswith(imp_category)]

        if not outcomes:
            return {
                "total_outcomes": 0,
                "successful": 0,
                "failed": 0,
                "success_rate": 0.0,
                "avg_merge_time_hours": None,
                "avg_ci_pass_rate": None,
                "avg_review_cycles": None,
                "by_category": {},
            }

        # Calculate basic stats
        successful = sum(1 for o in outcomes if o.get("success"))
        failed = len(outcomes) - successful
        success_rate = successful / len(outcomes) if outcomes else 0.0

        # Extract merge times from details
        merge_times: list[float] = []
        ci_pass_rates: list[float] = []
        review_cycles_list: list[int] = []

        for outcome in outcomes:
            details = outcome.get("details", {})
            if details:
                if "merge_time_hours" in details:
                    merge_times.append(float(details["merge_time_hours"]))
                if "ci_pass_rate" in details:
                    ci_pass_rates.append(float(details["ci_pass_rate"]))
                if "review_cycles" in details:
                    review_cycles_list.append(int(details["review_cycles"]))

        # Calculate averages
        avg_merge_time = sum(merge_times) / len(merge_times) if merge_times else None
        avg_ci_pass_rate = sum(ci_pass_rates) / len(ci_pass_rates) if ci_pass_rates else None
        avg_review_cycles = (
            sum(review_cycles_list) / len(review_cycles_list) if review_cycles_list else None
        )

        # Build per-category breakdown
        by_category: dict[str, dict[str, Any]] = {}
        for outcome in outcomes:
            imp_id = outcome.get("imp_id", "")
            parts = imp_id.split("-")
            if len(parts) >= 2:
                category = f"{parts[0]}-{parts[1]}"
            else:
                category = imp_id or "UNKNOWN"

            if category not in by_category:
                by_category[category] = {
                    "total": 0,
                    "successful": 0,
                    "merge_times": [],
                    "ci_pass_rates": [],
                    "review_cycles": [],
                }

            by_category[category]["total"] += 1
            if outcome.get("success"):
                by_category[category]["successful"] += 1

            details = outcome.get("details", {})
            if details:
                if "merge_time_hours" in details:
                    by_category[category]["merge_times"].append(float(details["merge_time_hours"]))
                if "ci_pass_rate" in details:
                    by_category[category]["ci_pass_rates"].append(float(details["ci_pass_rate"]))
                if "review_cycles" in details:
                    by_category[category]["review_cycles"].append(int(details["review_cycles"]))

        # Finalize per-category stats
        for category, stats in by_category.items():
            stats["success_rate"] = (
                stats["successful"] / stats["total"] if stats["total"] > 0 else 0.0
            )
            stats["avg_merge_time_hours"] = (
                sum(stats["merge_times"]) / len(stats["merge_times"])
                if stats["merge_times"]
                else None
            )
            stats["avg_ci_pass_rate"] = (
                sum(stats["ci_pass_rates"]) / len(stats["ci_pass_rates"])
                if stats["ci_pass_rates"]
                else None
            )
            stats["avg_review_cycles"] = (
                sum(stats["review_cycles"]) / len(stats["review_cycles"])
                if stats["review_cycles"]
                else None
            )
            # Remove raw lists from output
            del stats["merge_times"]
            del stats["ci_pass_rates"]
            del stats["review_cycles"]

        return {
            "total_outcomes": len(outcomes),
            "successful": successful,
            "failed": failed,
            "success_rate": round(success_rate, 3),
            "avg_merge_time_hours": (
                round(avg_merge_time, 2) if avg_merge_time is not None else None
            ),
            "avg_ci_pass_rate": (
                round(avg_ci_pass_rate, 3) if avg_ci_pass_rate is not None else None
            ),
            "avg_review_cycles": (
                round(avg_review_cycles, 2) if avg_review_cycles is not None else None
            ),
            "by_category": by_category,
        }

    def save(self) -> None:
        """Persist memory to LEARNING_MEMORY.json."""
        self._memory["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Ensure parent directory exists
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(self._memory, indent=2, ensure_ascii=False)
        self.memory_path.write_text(content, encoding="utf-8")

        logger.info(f"[LearningMemory] Saved memory to {self.memory_path}")

    def clear(self) -> None:
        """Clear all memory (for testing or reset)."""
        self._memory = {
            key: (value.copy() if isinstance(value, (list, dict)) else value)
            for key, value in DEFAULT_MEMORY_STRUCTURE.items()
        }
        logger.info("[LearningMemory] Cleared all memory")

    @property
    def version(self) -> str:
        """Return the memory format version."""
        return self._memory.get("version", "1.0.0")

    @property
    def outcome_count(self) -> int:
        """Return the total number of recorded outcomes."""
        return len(self._memory.get("improvement_outcomes", []))

    @property
    def wave_count(self) -> int:
        """Return the total number of recorded wave completions."""
        return len(self._memory.get("wave_history", []))
