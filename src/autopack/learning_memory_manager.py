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

    def get_optimal_wave_size(self) -> int:
        """Calculate optimal wave size based on historical completion rates.

        Analyzes wave_history to find the wave size that maximizes throughput
        while maintaining acceptable completion rates.

        Returns:
            Recommended wave size (default: 3 if no history).
        """
        wave_history = self._memory.get("wave_history", [])

        if not wave_history:
            logger.debug("[LearningMemory] No wave history - returning default size of 3")
            return 3

        # Group by wave size and calculate average completion rate
        size_stats: dict[int, list[float]] = {}
        for wave in wave_history:
            size = wave.get("wave_size", 0)
            rate = wave.get("completion_rate", 0.0)
            if size > 0:
                if size not in size_stats:
                    size_stats[size] = []
                size_stats[size].append(rate)

        if not size_stats:
            return 3

        # Calculate average completion rate per size
        avg_rates = {size: sum(rates) / len(rates) for size, rates in size_stats.items()}

        # Find optimal size: maximize throughput (size * completion_rate)
        # with minimum completion rate threshold of 70%
        min_acceptable_rate = 0.70
        optimal_size = 3  # default
        best_throughput = 0.0

        for size, rate in avg_rates.items():
            if rate >= min_acceptable_rate:
                throughput = size * rate
                if throughput > best_throughput:
                    best_throughput = throughput
                    optimal_size = size

        # If no size meets the threshold, pick the one with highest completion rate
        if best_throughput == 0.0:
            optimal_size = max(avg_rates.keys(), key=lambda s: avg_rates[s])

        logger.debug(f"[LearningMemory] Calculated optimal wave size: {optimal_size}")
        return optimal_size

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
