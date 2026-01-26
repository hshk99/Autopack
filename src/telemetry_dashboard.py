"""Telemetry Health Dashboard.

Generates operational health reports from telemetry data.
Provides metrics including failure rates, nudge averages, and escalation frequency.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryDashboard:
    """Generates health reports from telemetry files.

    Analyzes nudge_state.json, ci_retry_state.json, and slot_history.json
    to produce operational health metrics and markdown reports.
    """

    def __init__(self, base_path: str | Path) -> None:
        """Initialize the TelemetryDashboard.

        Args:
            base_path: Directory containing the telemetry JSON files.
        """
        self.base_path = Path(base_path)
        self.nudge_state_file = self.base_path / "nudge_state.json"
        self.ci_retry_file = self.base_path / "ci_retry_state.json"
        self.slot_history_file = self.base_path / "slot_history.json"

        # Cache for loaded data
        self._nudge_data: dict[str, Any] | None = None
        self._ci_retry_data: dict[str, Any] | None = None
        self._slot_history_data: dict[str, Any] | None = None

    def _load_json_file(self, file_path: Path) -> dict[str, Any]:
        """Load and parse a JSON file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            Parsed JSON data or empty dict if file doesn't exist or is invalid.
        """
        if not file_path.exists():
            logger.debug("Telemetry file not found: %s", file_path)
            return {}

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("Loaded %s with %d entries", file_path.name, len(data))
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse %s: %s", file_path.name, e)
            return {}
        except OSError as e:
            logger.warning("Failed to read %s: %s", file_path.name, e)
            return {}

    def _get_nudge_data(self) -> dict[str, Any]:
        """Get nudge state data, loading from file if not cached."""
        if self._nudge_data is None:
            self._nudge_data = self._load_json_file(self.nudge_state_file)
        return self._nudge_data

    def _get_ci_retry_data(self) -> dict[str, Any]:
        """Get CI retry state data, loading from file if not cached."""
        if self._ci_retry_data is None:
            self._ci_retry_data = self._load_json_file(self.ci_retry_file)
        return self._ci_retry_data

    def _get_slot_history_data(self) -> dict[str, Any]:
        """Get slot history data, loading from file if not cached."""
        if self._slot_history_data is None:
            self._slot_history_data = self._load_json_file(self.slot_history_file)
        return self._slot_history_data

    def _parse_timestamp(self, ts: str | None) -> datetime | None:
        """Parse an ISO timestamp string to datetime.

        Args:
            ts: ISO format timestamp string or None.

        Returns:
            Parsed datetime or None if parsing fails.
        """
        if not ts:
            return None
        try:
            # Handle various ISO formats
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None

    def _filter_by_time(
        self, items: list[dict[str, Any]], hours: int, timestamp_key: str = "timestamp"
    ) -> list[dict[str, Any]]:
        """Filter items to only those within the specified time window.

        Args:
            items: List of items with timestamp fields.
            hours: Number of hours to look back.
            timestamp_key: Key containing the timestamp field.

        Returns:
            Filtered list of items within the time window.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = []

        for item in items:
            # Skip non-dict entries
            if not isinstance(item, dict):
                continue

            ts = self._parse_timestamp(item.get(timestamp_key))
            if ts is None:
                # Include items without timestamps (legacy data)
                filtered.append(item)
            elif ts.tzinfo is None:
                # Assume UTC for naive timestamps
                ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    filtered.append(item)
            elif ts >= cutoff:
                filtered.append(item)

        return filtered

    def generate_summary(self, hours: int = 24) -> dict[str, Any]:
        """Generate summary for last N hours.

        Aggregates key metrics from all telemetry sources.

        Args:
            hours: Number of hours to include in the summary.

        Returns:
            Dictionary containing aggregated summary metrics.
        """
        nudge_data = self._get_nudge_data()
        ci_data = self._get_ci_retry_data()
        slot_data = self._get_slot_history_data()

        # Get raw lists
        nudges = nudge_data.get("nudges", [])
        if not isinstance(nudges, list):
            nudges = []

        retries = ci_data.get("retries", [])
        if not isinstance(retries, list):
            retries = []

        slots = slot_data.get("slots", [])
        if not isinstance(slots, list):
            slots = []

        events = slot_data.get("events", [])
        if not isinstance(events, list):
            events = []

        # Filter by time window
        nudges = self._filter_by_time(nudges, hours)
        retries = self._filter_by_time(retries, hours)
        slots = self._filter_by_time(slots, hours)
        events = self._filter_by_time(events, hours)

        # Calculate nudge metrics
        total_nudges = len(nudges)
        failed_nudges = sum(
            1 for n in nudges if n.get("status", "").lower() in ("failed", "error", "timeout")
        )
        escalated_nudges = sum(1 for n in nudges if n.get("escalated", False))

        # Calculate CI metrics
        total_ci_runs = len(retries)
        ci_failures = sum(1 for r in retries if r.get("outcome", "").lower() in ("failed", "error"))
        ci_successes = sum(
            1 for r in retries if r.get("outcome", "").lower() in ("success", "passed")
        )

        # Calculate slot metrics
        total_slot_events = len(slots) + len(events)
        slot_failures = sum(
            1 for s in slots if s.get("status", "").lower() in ("failed", "error", "timeout")
        )

        # Calculate rates
        nudge_failure_rate = failed_nudges / total_nudges if total_nudges > 0 else 0.0
        ci_success_rate = ci_successes / total_ci_runs if total_ci_runs > 0 else 0.0
        escalation_rate = escalated_nudges / total_nudges if total_nudges > 0 else 0.0

        return {
            "time_window_hours": hours,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "nudge_metrics": {
                "total": total_nudges,
                "failed": failed_nudges,
                "escalated": escalated_nudges,
                "failure_rate": round(nudge_failure_rate, 3),
                "escalation_rate": round(escalation_rate, 3),
            },
            "ci_metrics": {
                "total_runs": total_ci_runs,
                "successes": ci_successes,
                "failures": ci_failures,
                "success_rate": round(ci_success_rate, 3),
            },
            "slot_metrics": {
                "total_events": total_slot_events,
                "failures": slot_failures,
            },
            "failure_rates_by_type": self.failure_rates_by_type(hours),
            "avg_nudges_to_success": self.average_nudges_to_success(hours),
            "escalation_frequency": self.escalation_frequency(hours),
        }

    def failure_rates_by_type(self, hours: int = 24) -> dict[str, float]:
        """Calculate failure rates grouped by phase type.

        Args:
            hours: Number of hours to include in the calculation.

        Returns:
            Dictionary mapping phase type to failure rate (0.0 to 1.0).
        """
        nudge_data = self._get_nudge_data()
        nudges = nudge_data.get("nudges", [])

        if not isinstance(nudges, list):
            return {}

        nudges = self._filter_by_time(nudges, hours)

        # Group by phase type
        phase_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "failed": 0})

        for nudge in nudges:
            if not isinstance(nudge, dict):
                continue

            phase_type = nudge.get("phase_type") or nudge.get("phase") or "unknown"
            phase_stats[phase_type]["total"] += 1

            status = nudge.get("status", "").lower()
            if status in ("failed", "error", "timeout"):
                phase_stats[phase_type]["failed"] += 1

        # Calculate rates
        rates: dict[str, float] = {}
        for phase_type, stats in phase_stats.items():
            if stats["total"] > 0:
                rates[phase_type] = round(stats["failed"] / stats["total"], 3)

        return rates

    def average_nudges_to_success(self, hours: int = 24) -> float:
        """Calculate average nudges needed before phase completion.

        Counts consecutive nudges for the same phase until success.

        Args:
            hours: Number of hours to include in the calculation.

        Returns:
            Average number of nudges needed for successful completion.
        """
        nudge_data = self._get_nudge_data()
        nudges = nudge_data.get("nudges", [])

        if not isinstance(nudges, list) or not nudges:
            return 0.0

        nudges = self._filter_by_time(nudges, hours)

        if not nudges:
            return 0.0

        # Track nudge sequences by phase identifier
        phase_sequences: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for nudge in nudges:
            if not isinstance(nudge, dict):
                continue

            # Use phase_id or combination of phase_type and run_id
            phase_id = nudge.get(
                "phase_id",
                f"{nudge.get('phase_type', 'unknown')}_{nudge.get('run_id', 'unknown')}",
            )
            phase_sequences[phase_id].append(nudge)

        # Calculate nudges to success for completed phases
        nudge_counts: list[int] = []

        for phase_id, seq in phase_sequences.items():
            # Sort by timestamp if available
            seq_sorted = sorted(
                seq,
                key=lambda x: self._parse_timestamp(x.get("timestamp"))
                or datetime.min.replace(tzinfo=timezone.utc),
            )

            # Count nudges until success
            count = 0
            for nudge in seq_sorted:
                count += 1
                status = nudge.get("status", "").lower()
                if status in ("completed", "success", "passed"):
                    nudge_counts.append(count)
                    break

        if not nudge_counts:
            return 0.0

        return round(sum(nudge_counts) / len(nudge_counts), 2)

    def escalation_frequency(self, hours: int = 24) -> dict[int, int]:
        """Count escalations by level.

        Args:
            hours: Number of hours to include in the calculation.

        Returns:
            Dictionary mapping escalation level to count.
        """
        nudge_data = self._get_nudge_data()
        slot_data = self._get_slot_history_data()

        escalation_counts: Counter[int] = Counter()

        # Count from nudge data
        nudges = nudge_data.get("nudges", [])
        if isinstance(nudges, list):
            nudges = self._filter_by_time(nudges, hours)
            for nudge in nudges:
                if not isinstance(nudge, dict):
                    continue

                if nudge.get("escalated", False):
                    level = nudge.get("escalation_level", 1)
                    if isinstance(level, int):
                        escalation_counts[level] += 1

        # Count from slot history events
        events = slot_data.get("events", [])
        if isinstance(events, list):
            events = self._filter_by_time(events, hours)
            for event in events:
                if not isinstance(event, dict):
                    continue

                event_type = event.get("event_type", event.get("type", ""))
                if event_type == "escalation_level_change":
                    level = event.get("escalation_level", event.get("level", 1))
                    if isinstance(level, int):
                        escalation_counts[level] += 1

        # Convert to regular dict with sorted keys
        return dict(sorted(escalation_counts.items()))

    def render_markdown_report(self, hours: int = 24) -> str:
        """Render health report as markdown.

        Args:
            hours: Number of hours to include in the report.

        Returns:
            Markdown-formatted health report string.
        """
        summary = self.generate_summary(hours)

        lines = [
            "# Telemetry Health Report",
            "",
            f"**Generated**: {summary['generated_at']}",
            f"**Time Window**: Last {hours} hours",
            "",
            "---",
            "",
            "## Summary Metrics",
            "",
        ]

        # Nudge metrics section
        nudge = summary["nudge_metrics"]
        lines.extend(
            [
                "### Nudge Activity",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Total Nudges | {nudge['total']} |",
                f"| Failed Nudges | {nudge['failed']} |",
                f"| Escalated Nudges | {nudge['escalated']} |",
                f"| Failure Rate | {nudge['failure_rate']:.1%} |",
                f"| Escalation Rate | {nudge['escalation_rate']:.1%} |",
                "",
            ]
        )

        # CI metrics section
        ci = summary["ci_metrics"]
        lines.extend(
            [
                "### CI Pipeline",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Total Runs | {ci['total_runs']} |",
                f"| Successes | {ci['successes']} |",
                f"| Failures | {ci['failures']} |",
                f"| Success Rate | {ci['success_rate']:.1%} |",
                "",
            ]
        )

        # Slot metrics section
        slot = summary["slot_metrics"]
        lines.extend(
            [
                "### Slot Activity",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Total Events | {slot['total_events']} |",
                f"| Failures | {slot['failures']} |",
                "",
            ]
        )

        # Failure rates by type
        failure_rates = summary["failure_rates_by_type"]
        if failure_rates:
            lines.extend(
                [
                    "---",
                    "",
                    "## Failure Rates by Phase Type",
                    "",
                    "| Phase Type | Failure Rate |",
                    "|------------|--------------|",
                ]
            )
            for phase_type, rate in sorted(failure_rates.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| {phase_type} | {rate:.1%} |")
            lines.append("")

        # Average nudges to success
        avg_nudges = summary["avg_nudges_to_success"]
        lines.extend(
            [
                "---",
                "",
                "## Performance Indicators",
                "",
                f"**Average Nudges to Success**: {avg_nudges:.2f}",
                "",
            ]
        )

        # Escalation frequency
        escalations = summary["escalation_frequency"]
        if escalations:
            lines.extend(
                [
                    "### Escalation Distribution",
                    "",
                    "| Level | Count |",
                    "|-------|-------|",
                ]
            )
            for level, count in sorted(escalations.items()):
                lines.append(f"| {level} | {count} |")
            lines.append("")

        # Health status
        lines.extend(
            [
                "---",
                "",
                "## Health Status",
                "",
            ]
        )

        # Determine overall health
        health_issues = []
        if nudge["failure_rate"] > 0.3:
            health_issues.append(f"High nudge failure rate ({nudge['failure_rate']:.1%})")
        if nudge["escalation_rate"] > 0.2:
            health_issues.append(f"High escalation rate ({nudge['escalation_rate']:.1%})")
        if ci["total_runs"] > 0 and ci["success_rate"] < 0.7:
            health_issues.append(f"Low CI success rate ({ci['success_rate']:.1%})")
        if avg_nudges > 3:
            health_issues.append(f"High average nudges to success ({avg_nudges:.1f})")

        if not health_issues:
            lines.extend(
                [
                    "**Status**: HEALTHY",
                    "",
                    "All metrics are within acceptable thresholds.",
                ]
            )
        else:
            lines.extend(
                [
                    "**Status**: ATTENTION NEEDED",
                    "",
                    "Issues detected:",
                    "",
                ]
            )
            for issue in health_issues:
                lines.append(f"- {issue}")

        lines.append("")
        return "\n".join(lines)

    def clear_cache(self) -> None:
        """Clear cached telemetry data to force reload on next analysis."""
        self._nudge_data = None
        self._ci_retry_data = None
        self._slot_history_data = None
        logger.debug("Cleared telemetry data cache")
