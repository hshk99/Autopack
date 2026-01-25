"""Automated performance optimization detection."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from src.memory.metrics_db import MetricsDatabase


@dataclass
class OptimizationSuggestion:
    """Represents a detected optimization opportunity."""

    category: str  # 'slot_utilization', 'ci_efficiency', 'polling', 'stagnation'
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str
    current_value: float
    threshold: float
    estimated_impact: str
    implementation_hint: str


class OptimizationDetector:
    """Detects optimization opportunities from metrics."""

    THRESHOLDS: Dict[str, float] = {
        "slot_utilization_min": 0.7,  # Below = under-utilization
        "ci_failure_rate_max": 0.15,  # Above = too many failures
        "stagnation_rate_max": 0.1,  # Above = prompt issues
        "avg_task_time_max_seconds": 1800,  # 30 min before flagging
        "pr_merge_time_max_hours": 4,  # 4 hours max to merge
    }

    SEVERITY_ORDER: Dict[str, int] = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def __init__(self, metrics_db: "MetricsDatabase") -> None:
        """Initialize with MetricsDatabase instance."""
        self.db = metrics_db

    def detect_all(self) -> List[OptimizationSuggestion]:
        """Analyze metrics and return all optimization suggestions."""
        suggestions: List[OptimizationSuggestion] = []
        suggestions.extend(self._check_slot_utilization())
        suggestions.extend(self._check_ci_efficiency())
        suggestions.extend(self._check_stagnation_patterns())
        suggestions.extend(self._check_pr_merge_times())
        return sorted(suggestions, key=lambda s: self.SEVERITY_ORDER[s.severity])

    def _check_slot_utilization(self) -> List[OptimizationSuggestion]:
        """Check for slot under-utilization."""
        suggestions: List[OptimizationSuggestion] = []
        metrics = self.db.get_daily_metrics(days=7)

        if not metrics:
            return suggestions

        avg_utilization = sum(m.get("slot_utilization_avg", 0) for m in metrics) / len(metrics)

        if avg_utilization < self.THRESHOLDS["slot_utilization_min"]:
            threshold = self.THRESHOLDS["slot_utilization_min"]
            suggestions.append(
                OptimizationSuggestion(
                    category="slot_utilization",
                    severity="medium" if avg_utilization > 0.5 else "high",
                    description=(
                        f"Average slot utilization is {avg_utilization:.1%}, "
                        f"below {threshold:.0%} threshold"
                    ),
                    current_value=avg_utilization,
                    threshold=threshold,
                    estimated_impact=("Could increase throughput by running more parallel tasks"),
                    implementation_hint=(
                        "Consider increasing wave sizes or reducing task dependencies "
                        "to enable more parallelization"
                    ),
                )
            )

        return suggestions

    def _check_ci_efficiency(self) -> List[OptimizationSuggestion]:
        """Check for high CI failure rates."""
        suggestions: List[OptimizationSuggestion] = []
        metrics = self.db.get_daily_metrics(days=7)

        if not metrics:
            return suggestions

        avg_failure_rate = sum(m.get("ci_failure_rate", 0) for m in metrics) / len(metrics)

        if avg_failure_rate > self.THRESHOLDS["ci_failure_rate_max"]:
            threshold = self.THRESHOLDS["ci_failure_rate_max"]
            suggestions.append(
                OptimizationSuggestion(
                    category="ci_efficiency",
                    severity="high" if avg_failure_rate > 0.25 else "medium",
                    description=(
                        f"CI failure rate is {avg_failure_rate:.1%}, "
                        f"above {threshold:.0%} threshold"
                    ),
                    current_value=avg_failure_rate,
                    threshold=threshold,
                    estimated_impact=("Reducing failures would speed up overall completion time"),
                    implementation_hint=(
                        "Review common failure patterns, add pre-commit hooks, "
                        "improve test coverage"
                    ),
                )
            )

        return suggestions

    def _check_stagnation_patterns(self) -> List[OptimizationSuggestion]:
        """Check for high stagnation rates."""
        suggestions: List[OptimizationSuggestion] = []
        metrics = self.db.get_daily_metrics(days=7)

        if not metrics:
            return suggestions

        total_tasks = sum(m.get("tasks_completed", 0) for m in metrics)
        total_stagnations = sum(m.get("stagnation_count", 0) for m in metrics)

        if total_tasks > 0:
            stagnation_rate = total_stagnations / total_tasks
            if stagnation_rate > self.THRESHOLDS["stagnation_rate_max"]:
                threshold = self.THRESHOLDS["stagnation_rate_max"]
                suggestions.append(
                    OptimizationSuggestion(
                        category="stagnation",
                        severity="high" if stagnation_rate > 0.2 else "medium",
                        description=(
                            f"Stagnation rate is {stagnation_rate:.1%}, "
                            f"above {threshold:.0%} threshold"
                        ),
                        current_value=stagnation_rate,
                        threshold=threshold,
                        estimated_impact=(
                            "Reducing stagnation would improve task completion rates"
                        ),
                        implementation_hint=(
                            "Review prompts for clarity, add more specific instructions, "
                            "improve error handling"
                        ),
                    )
                )

        return suggestions

    def _check_pr_merge_times(self) -> List[OptimizationSuggestion]:
        """Check for slow PR merge times."""
        suggestions: List[OptimizationSuggestion] = []
        metrics = self.db.get_daily_metrics(days=7)

        if not metrics:
            return suggestions

        avg_merge_time = sum(m.get("pr_merge_time_avg", 0) for m in metrics) / len(metrics)
        max_hours = self.THRESHOLDS["pr_merge_time_max_hours"]

        if avg_merge_time > max_hours * 3600:  # Convert hours to seconds
            suggestions.append(
                OptimizationSuggestion(
                    category="pr_merge_time",
                    severity="medium",
                    description=(
                        f"Average PR merge time is {avg_merge_time / 3600:.1f} hours, "
                        f"above {max_hours} hour threshold"
                    ),
                    current_value=avg_merge_time / 3600,
                    threshold=max_hours,
                    estimated_impact=("Faster merges would enable quicker wave progression"),
                    implementation_hint=(
                        "Consider auto-merge for passing PRs, reduce required reviews, "
                        "optimize CI pipeline"
                    ),
                )
            )

        return suggestions

    def get_summary(self) -> str:
        """Get human-readable summary of optimization opportunities."""
        suggestions = self.detect_all()
        if not suggestions:
            return "No optimization opportunities detected. All metrics within thresholds."

        lines = [f"Found {len(suggestions)} optimization opportunities:\n"]
        for s in suggestions:
            lines.append(f"[{s.severity.upper()}] {s.category}: {s.description}")
            lines.append(f"  -> {s.implementation_hint}\n")

        return "\n".join(lines)
