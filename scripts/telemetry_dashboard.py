"""Telemetry Dashboard for generating human-readable reports.

Reads TELEMETRY_SUMMARY.json and generates a markdown report
providing visibility into system health for operators.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryDashboard:
    """Generates human-readable reports from telemetry summary data."""

    def __init__(self, summary_path: Path) -> None:
        """Initialize the dashboard with path to TELEMETRY_SUMMARY.json.

        Args:
            summary_path: Path to the TELEMETRY_SUMMARY.json file
        """
        self.summary_path = Path(summary_path)
        self._summary: dict[str, Any] = {}

    def _load_summary(self) -> dict[str, Any]:
        """Load telemetry summary data from JSON file.

        Returns:
            Dictionary containing the telemetry summary data

        Raises:
            FileNotFoundError: If the summary file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        if not self.summary_path.exists():
            logger.error("Telemetry summary file not found: %s", self.summary_path)
            raise FileNotFoundError(f"Telemetry summary not found: {self.summary_path}")

        with open(self.summary_path, encoding="utf-8") as f:
            self._summary = json.load(f)
            logger.debug("Loaded telemetry summary from %s", self.summary_path)

        return self._summary

    def _format_percentage(self, value: float) -> str:
        """Format a percentage value for display.

        Args:
            value: Percentage value (0-100)

        Returns:
            Formatted string like "85.5%"
        """
        return f"{value:.1f}%"

    def _format_time(self, seconds: float) -> str:
        """Format time duration for display.

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable time string
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def _generate_overview_section(self) -> str:
        """Generate the Overview section of the report.

        Returns:
            Markdown string for the overview section
        """
        metrics = self._summary.get("metrics", {})
        totals = metrics.get("totals", {})
        generated_at = self._summary.get("generated_at", "Unknown")

        total_ops = totals.get("total_operations", 0)
        success_rate = metrics.get("success_rate", 0.0)

        lines = [
            "## Overview",
            "",
            f"**Generated**: {generated_at}",
            f"**Total Operations**: {total_ops}",
            f"**Overall Success Rate**: {self._format_percentage(success_rate)}",
            "",
        ]

        return "\n".join(lines)

    def _generate_success_rates_section(self) -> str:
        """Generate the Success Rates section of the report.

        Returns:
            Markdown string for success rates by category
        """
        metrics = self._summary.get("metrics", {})
        totals = metrics.get("totals", {})
        sources = self._summary.get("sources_summary", {})

        lines = [
            "## Success Rates by Category",
            "",
            "| Category | Success Rate | Total |",
            "|----------|--------------|-------|",
        ]

        # Calculate success rate per source
        successful = totals.get("successful_operations", 0)
        failed = totals.get("failed_operations", 0)
        total = totals.get("total_operations", 0)

        # Add overall rate
        overall_rate = metrics.get("success_rate", 0.0)
        lines.append(f"| Overall | {self._format_percentage(overall_rate)} | {total} |")

        # Add source-based categories if available
        for source_name, source_info in sources.items():
            if isinstance(source_info, dict) and source_info.get("loaded"):
                entry_count = source_info.get("entry_count", 0)
                # Map source names to category names
                category_map = {
                    "nudge_state": "automation",
                    "ci_retry_state": "reliability",
                    "slot_history": "performance",
                }
                category = category_map.get(source_name, source_name)
                # Estimate rate based on overall (simplified)
                lines.append(f"| {category} | - | {entry_count} |")

        lines.append("")
        return "\n".join(lines)

    def _generate_completion_times_section(self) -> str:
        """Generate the Completion Times section of the report.

        Returns:
            Markdown string for completion times
        """
        metrics = self._summary.get("metrics", {})
        avg_time = metrics.get("avg_completion_time", 0.0)

        lines = [
            "## Completion Times",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Average Completion Time | {self._format_time(avg_time)} |",
            "",
        ]

        return "\n".join(lines)

    def _generate_failure_categories_section(self) -> str:
        """Generate the Failure Categories section of the report.

        Returns:
            Markdown string for failure categories
        """
        metrics = self._summary.get("metrics", {})
        failure_cats = metrics.get("failure_categories", {})
        totals = metrics.get("totals", {})
        total_failed = totals.get("failed_operations", 0)

        lines = [
            "## Failure Categories",
            "",
        ]

        if not failure_cats:
            lines.append("No failures recorded.")
            lines.append("")
            return "\n".join(lines)

        lines.extend(
            [
                "| Category | Count | Percentage |",
                "|----------|-------|------------|",
            ]
        )

        # Sort by count descending
        sorted_cats = sorted(failure_cats.items(), key=lambda x: x[1], reverse=True)

        for category, count in sorted_cats:
            percentage = (count / total_failed * 100) if total_failed > 0 else 0
            lines.append(f"| {category} | {count} | {self._format_percentage(percentage)} |")

        lines.append("")
        return "\n".join(lines)

    def _generate_escalation_trends_section(self) -> str:
        """Generate the Escalation Trends section of the report.

        Returns:
            Markdown string for escalation trends
        """
        metrics = self._summary.get("metrics", {})
        escalation_freq = metrics.get("escalation_frequency", 0.0)
        totals = metrics.get("totals", {})
        escalated = totals.get("escalated_operations", 0)
        total = totals.get("total_operations", 0)

        lines = [
            "## Escalation Trends",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Escalations | {escalated} |",
            f"| Escalation Rate | {self._format_percentage(escalation_freq)} |",
            f"| Operations Without Escalation | {total - escalated} |",
            "",
        ]

        return "\n".join(lines)

    def _generate_recommendations_section(self) -> str:
        """Generate the Recommendations section based on patterns.

        Returns:
            Markdown string with actionable recommendations
        """
        metrics = self._summary.get("metrics", {})
        success_rate = metrics.get("success_rate", 0.0)
        escalation_freq = metrics.get("escalation_frequency", 0.0)
        avg_time = metrics.get("avg_completion_time", 0.0)
        failure_cats = metrics.get("failure_categories", {})

        lines = [
            "## Recommendations",
            "",
        ]

        recommendations = []

        # Success rate recommendations
        if success_rate < 70:
            recommendations.append(
                "- **Low Success Rate**: Consider reducing wave size or "
                "reviewing task complexity. Current rate is below 70%."
            )
        elif success_rate < 85:
            recommendations.append(
                "- **Moderate Success Rate**: Review failure patterns to "
                "identify improvement opportunities."
            )
        else:
            recommendations.append(
                "- **Healthy Success Rate**: System is performing well. "
                "Continue monitoring for any degradation."
            )

        # Escalation recommendations
        if escalation_freq > 30:
            recommendations.append(
                "- **High Escalation Frequency**: Consider adjusting escalation "
                "thresholds or improving automated resolution."
            )

        # Timeout recommendations
        if "timeout" in failure_cats:
            timeout_count = failure_cats.get("timeout", 0)
            total_failures = sum(failure_cats.values())
            if total_failures > 0 and timeout_count / total_failures > 0.3:
                recommendations.append(
                    "- **Timeout Issues**: Timeouts represent significant portion "
                    "of failures. Consider increasing timeout limits or optimizing "
                    "long-running operations."
                )

        # Completion time recommendations
        if avg_time > 300:  # More than 5 minutes
            recommendations.append(
                "- **Long Completion Times**: Average completion time exceeds "
                "5 minutes. Consider parallelization or optimization."
            )

        if not recommendations:
            recommendations.append("- No specific recommendations at this time.")

        lines.extend(recommendations)
        lines.append("")

        return "\n".join(lines)

    def generate_report(self) -> str:
        """Generate the complete markdown report from telemetry data.

        Returns:
            Complete markdown report as a string
        """
        if not self._summary:
            self._load_summary()

        lines = [
            "# Telemetry Report",
            "",
        ]

        # Generate each section
        lines.append(self._generate_overview_section())
        lines.append(self._generate_success_rates_section())
        lines.append(self._generate_completion_times_section())
        lines.append(self._generate_failure_categories_section())
        lines.append(self._generate_escalation_trends_section())
        lines.append(self._generate_recommendations_section())

        return "\n".join(lines)

    def save_report(self, output_path: Path) -> None:
        """Write the telemetry report to a markdown file.

        Args:
            output_path: Path where TELEMETRY_REPORT.md will be written

        Raises:
            OSError: If the file cannot be written
        """
        report = self.generate_report()
        output_path = Path(output_path)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info("Saved telemetry report to %s", output_path)
        except OSError as e:
            logger.error("Failed to save report to %s: %s", output_path, e)
            raise


def main() -> None:
    """CLI entry point for generating telemetry dashboard reports."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate human-readable telemetry reports")
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("TELEMETRY_SUMMARY.json"),
        help="Path to TELEMETRY_SUMMARY.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("TELEMETRY_REPORT.md"),
        help="Output path for the report file",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    dashboard = TelemetryDashboard(args.summary)
    dashboard.save_report(args.output)
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
