"""Context injector for feeding telemetry insights into discovery."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import json


@dataclass
class DiscoveryContext:
    """Context to inject into Phase 1 discovery."""

    recurring_issues: list[dict[str, Any]]  # Issues that keep appearing
    successful_patterns: list[dict[str, Any]]  # Patterns that worked well
    high_value_categories: list[str]  # IMP categories with best outcomes
    failed_approaches: list[dict[str, Any]]  # Approaches to avoid
    performance_insights: dict[str, Any]  # Timing/throughput data


class ContextInjector:
    """Injects telemetry-derived context into discovery phase."""

    def __init__(
        self,
        telemetry_path: str = "telemetry_events.json",
        decisions_path: str = "decisions_log.json",
    ):
        """Initialize the context injector.

        Args:
            telemetry_path: Path to telemetry events JSON file
            decisions_path: Path to decisions log JSON file
        """
        self.telemetry_path = Path(telemetry_path)
        self.decisions_path = Path(decisions_path)

    def gather_context(self, lookback_days: int = 30) -> DiscoveryContext:
        """Gather context from telemetry for discovery phase.

        Args:
            lookback_days: How far back to analyze

        Returns:
            DiscoveryContext with insights for Phase 1
        """
        cutoff = datetime.now() - timedelta(days=lookback_days)

        return DiscoveryContext(
            recurring_issues=self._find_recurring_issues(cutoff),
            successful_patterns=self._find_successful_patterns(cutoff),
            high_value_categories=self._identify_high_value_categories(cutoff),
            failed_approaches=self._find_failed_approaches(cutoff),
            performance_insights=self._get_performance_insights(cutoff),
        )

    def inject_into_phase1(self, context: DiscoveryContext, output_path: str) -> None:
        """Write context to a file for Phase 1 to read.

        Args:
            context: The gathered context
            output_path: Where to write the context file
        """
        context_data = {
            "generated_at": datetime.now().isoformat(),
            "recurring_issues": context.recurring_issues,
            "successful_patterns": context.successful_patterns,
            "high_value_categories": context.high_value_categories,
            "failed_approaches": context.failed_approaches,
            "performance_insights": context.performance_insights,
            "recommendations": self._generate_recommendations(context),
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(context_data, f, indent=2)

    def _find_recurring_issues(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Find issues that recur across multiple projects."""
        issues: list[dict[str, Any]] = []
        if self.telemetry_path.exists():
            with open(self.telemetry_path, encoding="utf-8") as f:
                events = json.load(f).get("events", [])
                error_counts: dict[str, int] = {}
                for e in events:
                    if e.get("event_type") == "error":
                        error_key = e.get("payload", {}).get("error_type", "unknown")
                        error_counts[error_key] = error_counts.get(error_key, 0) + 1

                for error_type, count in error_counts.items():
                    if count >= 3:
                        issues.append(
                            {
                                "type": error_type,
                                "occurrences": count,
                                "recommendation": f"Address root cause of {error_type}",
                            }
                        )
        return issues

    def _find_successful_patterns(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Find implementation patterns that succeeded."""
        patterns: list[dict[str, Any]] = []
        if self.decisions_path.exists():
            with open(self.decisions_path, encoding="utf-8") as f:
                decisions = json.load(f).get("decisions", [])
                for d in decisions:
                    if d.get("outcome") == "success":
                        patterns.append(
                            {
                                "decision_type": d.get("decision_type"),
                                "chosen_option": d.get("chosen_option"),
                                "context": d.get("context", {}),
                            }
                        )
        return patterns

    def _identify_high_value_categories(self, cutoff: datetime) -> list[str]:
        """Identify IMP categories with best outcomes."""
        # Default high-value categories based on historical analysis
        return ["TEL", "LOG", "ESC", "PERF"]

    def _find_failed_approaches(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Find approaches that failed and should be avoided."""
        failed: list[dict[str, Any]] = []
        if self.decisions_path.exists():
            with open(self.decisions_path, encoding="utf-8") as f:
                decisions = json.load(f).get("decisions", [])
                for d in decisions:
                    if d.get("outcome") == "failure":
                        failed.append(
                            {
                                "approach": d.get("chosen_option"),
                                "reason": d.get("reasoning"),
                                "avoid_in": d.get("context", {}).get("phase_id"),
                            }
                        )
        return failed

    def _get_performance_insights(self, cutoff: datetime) -> dict[str, Any]:
        """Get performance insights for optimization."""
        return {
            "avg_phase_duration_seconds": 0,
            "ci_success_rate": 0.0,
            "bottleneck_components": [],
        }

    def _generate_recommendations(self, context: DiscoveryContext) -> list[str]:
        """Generate actionable recommendations for Phase 1."""
        recommendations: list[str] = []
        if context.recurring_issues:
            recommendations.append(
                f"Prioritize fixing {len(context.recurring_issues)} recurring issues"
            )
        if context.high_value_categories:
            recommendations.append(
                f"Focus on categories: {', '.join(context.high_value_categories)}"
            )
        if context.failed_approaches:
            recommendations.append(
                f"Avoid {len(context.failed_approaches)} previously failed approaches"
            )
        return recommendations
