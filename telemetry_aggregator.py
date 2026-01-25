"""Centralized Telemetry Aggregator for unified runtime telemetry analysis.

Consolidates telemetry from multiple sources:
- nudge_state.json: Nudge tracking and escalation data
- ci_retry_state.json: CI retry patterns and outcomes
- slot_history.json: Slot allocation and completion history

Provides unified metrics including success rates, completion times,
failure categories, and escalation frequencies.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryAggregator:
    """Aggregates telemetry from multiple JSON state files into unified metrics."""

    # Default telemetry file names
    NUDGE_STATE_FILE = "nudge_state.json"
    CI_RETRY_STATE_FILE = "ci_retry_state.json"
    SLOT_HISTORY_FILE = "slot_history.json"

    def __init__(self, base_path: Path) -> None:
        """Initialize the aggregator with a base path for telemetry files.

        Args:
            base_path: Directory containing telemetry state files
        """
        self.base_path = Path(base_path)
        self._nudge_data: dict[str, Any] = {}
        self._ci_retry_data: dict[str, Any] = {}
        self._slot_history_data: dict[str, Any] = {}
        self._aggregated: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}

    def _load_json_file(self, filename: str) -> dict[str, Any]:
        """Load a JSON file from the base path.

        Args:
            filename: Name of the JSON file to load

        Returns:
            Parsed JSON data or empty dict if file doesn't exist
        """
        file_path = self.base_path / filename
        if not file_path.exists():
            logger.debug("Telemetry file not found: %s", file_path)
            return {}

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("Loaded telemetry from %s: %d entries", filename, len(data))
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse %s: %s", filename, e)
            return {}
        except OSError as e:
            logger.warning("Failed to read %s: %s", filename, e)
            return {}

    def aggregate(self) -> dict[str, Any]:
        """Consolidate all telemetry sources into a unified structure.

        Reads nudge_state, ci_retry_state, and slot_history files,
        merging them into a single aggregated view.

        Returns:
            Dictionary containing consolidated telemetry data
        """
        # Load all telemetry sources
        self._nudge_data = self._load_json_file(self.NUDGE_STATE_FILE)
        self._ci_retry_data = self._load_json_file(self.CI_RETRY_STATE_FILE)
        self._slot_history_data = self._load_json_file(self.SLOT_HISTORY_FILE)

        # Build aggregated view
        self._aggregated = {
            "timestamp": datetime.now().isoformat(),
            "sources": {
                "nudge_state": {
                    "loaded": bool(self._nudge_data),
                    "entry_count": len(self._nudge_data),
                },
                "ci_retry_state": {
                    "loaded": bool(self._ci_retry_data),
                    "entry_count": len(self._ci_retry_data),
                },
                "slot_history": {
                    "loaded": bool(self._slot_history_data),
                    "entry_count": len(self._slot_history_data),
                },
            },
            "nudge_state": self._nudge_data,
            "ci_retry_state": self._ci_retry_data,
            "slot_history": self._slot_history_data,
        }

        logger.info(
            "Aggregated telemetry: nudge=%d, ci_retry=%d, slot_history=%d",
            len(self._nudge_data),
            len(self._ci_retry_data),
            len(self._slot_history_data),
        )

        return self._aggregated

    def compute_metrics(self) -> dict[str, Any]:
        """Compute key metrics from aggregated telemetry data.

        Calculates:
        - success_rate: Overall success rate across all operations
        - avg_completion_time: Average time to complete operations
        - failure_categories: Breakdown of failure types
        - escalation_frequency: How often escalations occur

        Returns:
            Dictionary containing computed metrics
        """
        if not self._aggregated:
            self.aggregate()

        # Initialize metrics
        self._metrics = {
            "timestamp": datetime.now().isoformat(),
            "success_rate": 0.0,
            "avg_completion_time": 0.0,
            "failure_categories": {},
            "escalation_frequency": 0.0,
            "totals": {
                "total_operations": 0,
                "successful_operations": 0,
                "failed_operations": 0,
                "escalated_operations": 0,
            },
        }

        total_ops = 0
        successful_ops = 0
        failed_ops = 0
        escalated_ops = 0
        completion_times: list[float] = []
        failure_cats: dict[str, int] = {}

        # Process slot history for success/failure metrics
        if isinstance(self._slot_history_data, dict):
            slots = self._slot_history_data.get("slots", [])
            if isinstance(slots, list):
                for slot in slots:
                    if not isinstance(slot, dict):
                        continue
                    total_ops += 1
                    status = slot.get("status", "").lower()
                    if status in ("completed", "success", "passed"):
                        successful_ops += 1
                    elif status in ("failed", "error", "timeout"):
                        failed_ops += 1
                        # Track failure category
                        category = slot.get("failure_category", slot.get("reason", "unknown"))
                        failure_cats[category] = failure_cats.get(category, 0) + 1

                    # Track completion time if available
                    completion_time = slot.get("completion_time", slot.get("duration"))
                    if completion_time is not None:
                        try:
                            completion_times.append(float(completion_time))
                        except (ValueError, TypeError):
                            pass

        # Process CI retry state for retry/failure patterns
        if isinstance(self._ci_retry_data, dict):
            retries = self._ci_retry_data.get("retries", [])
            if isinstance(retries, list):
                for retry in retries:
                    if not isinstance(retry, dict):
                        continue
                    total_ops += 1
                    outcome = retry.get("outcome", "").lower()
                    if outcome in ("success", "passed"):
                        successful_ops += 1
                    else:
                        failed_ops += 1
                        reason = retry.get("failure_reason", "ci_retry_failure")
                        failure_cats[reason] = failure_cats.get(reason, 0) + 1

        # Process nudge state for escalation metrics
        if isinstance(self._nudge_data, dict):
            nudges = self._nudge_data.get("nudges", [])
            if isinstance(nudges, list):
                for nudge in nudges:
                    if not isinstance(nudge, dict):
                        continue
                    if nudge.get("escalated", False):
                        escalated_ops += 1
            # Also check for flat structure
            if self._nudge_data.get("escalated", False):
                escalated_ops += 1
            # Check escalation_count field
            escalation_count = self._nudge_data.get("escalation_count", 0)
            if isinstance(escalation_count, int):
                escalated_ops += escalation_count

        # Calculate final metrics
        if total_ops > 0:
            self._metrics["success_rate"] = round((successful_ops / total_ops) * 100, 2)
            self._metrics["escalation_frequency"] = round((escalated_ops / total_ops) * 100, 2)

        if completion_times:
            self._metrics["avg_completion_time"] = round(
                sum(completion_times) / len(completion_times), 2
            )

        self._metrics["failure_categories"] = failure_cats
        self._metrics["totals"] = {
            "total_operations": total_ops,
            "successful_operations": successful_ops,
            "failed_operations": failed_ops,
            "escalated_operations": escalated_ops,
        }

        logger.info(
            "Computed metrics: success_rate=%.2f%%, avg_time=%.2fs, escalations=%d",
            self._metrics["success_rate"],
            self._metrics["avg_completion_time"],
            escalated_ops,
        )

        return self._metrics

    def save_summary(self, output_path: Path) -> None:
        """Write the telemetry summary to a JSON file.

        Saves both aggregated data and computed metrics to the specified path.

        Args:
            output_path: Path where TELEMETRY_SUMMARY.json will be written
        """
        if not self._metrics:
            self.compute_metrics()

        summary = {
            "version": "1.0.0",
            "generated_at": datetime.now().isoformat(),
            "metrics": self._metrics,
            "sources_summary": self._aggregated.get("sources", {}),
        }

        output_path = Path(output_path)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
            logger.info("Saved telemetry summary to %s", output_path)
        except OSError as e:
            logger.error("Failed to save summary to %s: %s", output_path, e)
            raise


def main() -> None:
    """CLI entry point for running the telemetry aggregator."""
    import argparse

    parser = argparse.ArgumentParser(description="Aggregate telemetry from multiple sources")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path("."),
        help="Base directory containing telemetry files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("TELEMETRY_SUMMARY.json"),
        help="Output path for the summary file",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    aggregator = TelemetryAggregator(args.base_path)
    aggregator.aggregate()
    aggregator.compute_metrics()
    aggregator.save_summary(args.output)


if __name__ == "__main__":
    main()
