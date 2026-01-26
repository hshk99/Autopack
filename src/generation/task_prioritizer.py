"""Adaptive task prioritization for slot assignment."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Type hints for optional dependencies (avoid circular imports)
try:
    from memory.failure_analyzer import FailureAnalyzer
    from memory.metrics_db import MetricsDatabase
except ImportError:
    FailureAnalyzer = None  # type: ignore[misc, assignment]
    MetricsDatabase = None  # type: ignore[misc, assignment]


@dataclass
class PrioritizedTask:
    """A task with computed priority score."""

    phase_id: str
    imp_id: str
    title: str
    wave: int
    priority: str  # original priority
    score: float  # computed priority score (higher = more urgent)
    factors: Dict[str, float]  # breakdown of score factors
    blocked_by: List[str]  # list of blocking dependencies
    estimated_success_rate: float


class TaskPrioritizer:
    """Adaptively prioritizes tasks for slot assignment."""

    PRIORITY_WEIGHTS = {"critical": 100, "high": 75, "medium": 50, "low": 25}

    FACTOR_WEIGHTS = {
        "base_priority": 0.30,  # Original priority weight
        "wave_urgency": 0.20,  # Earlier waves get priority
        "success_likelihood": 0.20,  # Higher success rate = higher priority
        "dependency_chain": 0.15,  # Blocking more tasks = higher priority
        "age": 0.15,  # Older tasks get slight boost
    }

    def __init__(
        self,
        metrics_db: Optional["MetricsDatabase"] = None,
        failure_analyzer: Optional["FailureAnalyzer"] = None,
    ):
        """Initialize with optional dependencies."""
        self.metrics_db = metrics_db
        self.failure_analyzer = failure_analyzer
        self._task_history: Dict[str, List[Dict[str, Any]]] = {}

    def prioritize(
        self, tasks: List[Dict[str, Any]], available_slots: int = 4
    ) -> List[PrioritizedTask]:
        """
        Prioritize tasks and return top N for available slots.

        Args:
            tasks: List of task dicts with keys: phase_id, imp_id, title, wave,
                   priority, dependencies, files
            available_slots: Number of slots to fill

        Returns:
            List of PrioritizedTask sorted by score (highest first)
        """
        prioritized = []
        completed_phases = self._get_completed_phases()

        for task in tasks:
            # Check if task is blocked
            blocked_by = self._check_blocked(task, completed_phases)
            if blocked_by:
                continue  # Skip blocked tasks

            # Calculate priority score
            score, factors = self._calculate_score(task, tasks)
            success_rate = self._estimate_success_rate(task)

            prioritized.append(
                PrioritizedTask(
                    phase_id=task.get("phase_id", task.get("id", "")),
                    imp_id=task.get("imp_id", ""),
                    title=task.get("title", ""),
                    wave=task.get("wave", 0),
                    priority=task.get("priority", "medium"),
                    score=score,
                    factors=factors,
                    blocked_by=blocked_by,
                    estimated_success_rate=success_rate,
                )
            )

        # Sort by score (descending) and return top N
        prioritized.sort(key=lambda t: t.score, reverse=True)
        return prioritized[:available_slots]

    def _calculate_score(
        self, task: Dict[str, Any], all_tasks: List[Dict[str, Any]]
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate composite priority score."""
        factors: Dict[str, float] = {}

        # Base priority factor
        priority = task.get("priority", "medium")
        factors["base_priority"] = self.PRIORITY_WEIGHTS.get(priority, 50) / 100

        # Wave urgency factor (wave 1 = 1.0, wave 7 = 0.3)
        wave = task.get("wave", 1)
        factors["wave_urgency"] = max(0.3, 1.0 - (wave - 1) * 0.1)

        # Success likelihood factor
        factors["success_likelihood"] = self._estimate_success_rate(task)

        # Dependency chain factor (how many tasks depend on this one)
        imp_id = task.get("imp_id", "")
        dependents = sum(1 for t in all_tasks if imp_id in t.get("dependencies", []))
        factors["dependency_chain"] = min(1.0, dependents * 0.2)

        # Age factor (placeholder - would need created_at timestamp)
        factors["age"] = 0.5  # Default middle value

        # Compute weighted score
        score = sum(factors[k] * self.FACTOR_WEIGHTS[k] for k in self.FACTOR_WEIGHTS) * 100

        return score, factors

    def _check_blocked(self, task: Dict[str, Any], completed: set[str]) -> List[str]:
        """Check if task is blocked by unfinished dependencies."""
        dependencies = task.get("dependencies", [])
        blocked_by = []

        for dep in dependencies:
            if dep not in completed:
                blocked_by.append(dep)

        return blocked_by

    def _get_completed_phases(self) -> set[str]:
        """Get set of completed phase/IMP IDs."""
        # In production, this would query the metrics DB
        if self.metrics_db:
            outcomes = self.metrics_db.get_phase_outcomes()
            return {o["phase_id"] for o in outcomes if o.get("outcome") == "success"}
        return set()

    def _estimate_success_rate(self, task: Dict[str, Any]) -> float:
        """Estimate success rate based on historical data."""
        if not self.failure_analyzer:
            return 0.7  # Default 70% success assumption

        # Get failure statistics for similar tasks
        stats = self.failure_analyzer.get_failure_statistics()
        category = task.get("category", "unknown")

        # Base success rate on category failure history
        by_category = stats.get("by_category", {})
        total_failures = sum(by_category.values())

        if total_failures == 0:
            return 0.8  # No failure history = optimistic

        # Lower success estimate if similar failures exist
        category_failures = by_category.get(f"ci_{category}_failure", 0)
        failure_ratio = category_failures / total_failures if total_failures > 0 else 0

        return max(0.3, 0.9 - failure_ratio * 0.4)

    def get_recommendation(self, tasks: List[Dict[str, Any]], slots: int = 4) -> str:
        """Get human-readable recommendation."""
        prioritized = self.prioritize(tasks, slots)

        if not prioritized:
            return "No unblocked tasks available for assignment."

        lines = [f"Recommended tasks for {slots} slots:\n"]

        for i, task in enumerate(prioritized, 1):
            lines.append(f"{i}. [{task.imp_id}] {task.title}")
            lines.append(f"   Score: {task.score:.1f} | Wave {task.wave} | {task.priority}")
            lines.append(f"   Success estimate: {task.estimated_success_rate:.0%}")
            lines.append(
                f"   Factors: {', '.join(f'{k}={v:.2f}' for k, v in task.factors.items())}"
            )
            lines.append("")

        return "\n".join(lines)

    def export_recommendations(
        self, tasks: List[Dict[str, Any]], output_path: str, slots: int = 4
    ) -> None:
        """Export prioritization recommendations to JSON."""
        import json
        from pathlib import Path

        prioritized = self.prioritize(tasks, slots)

        output = {
            "generated_at": datetime.now().isoformat(),
            "available_slots": slots,
            "recommended_tasks": [
                {
                    "phase_id": t.phase_id,
                    "imp_id": t.imp_id,
                    "title": t.title,
                    "wave": t.wave,
                    "score": t.score,
                    "factors": t.factors,
                    "estimated_success_rate": t.estimated_success_rate,
                }
                for t in prioritized
            ],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
