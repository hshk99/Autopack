"""Metrics aggregation engine for Autopack telemetry."""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetricsAggregator:
    """Aggregates events from EventLogger into actionable metrics."""

    def __init__(self, log_dir: Optional[str] = None, store_path: Optional[str] = None):
        """Initialize the metrics aggregator.

        Args:
            log_dir: Directory containing event log files.
                    Defaults to ./logs.
            store_path: Path to persist aggregated metrics.
                       Defaults to ./src/telemetry/metrics_store.json.
        """
        self.log_dir = Path(log_dir or "./logs")
        self.store_path = Path(store_path or "./src/telemetry/metrics_store.json")
        self._metrics: Dict[str, Any] = self._load_store()

    def _load_store(self) -> Dict[str, Any]:
        """Load existing metrics store or initialize empty."""
        if self.store_path.exists():
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"aggregated_at": None, "metrics": {}}

    def _save_store(self) -> None:
        """Persist metrics to store."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._metrics["aggregated_at"] = datetime.now().isoformat()
        with open(self.store_path, "w", encoding="utf-8") as f:
            json.dump(self._metrics, f, indent=2)

    def aggregate(self, since_hours: int = 24) -> Dict[str, Any]:
        """Aggregate events from last N hours into metrics.

        Args:
            since_hours: Number of hours to look back for events.

        Returns:
            Dictionary containing aggregated metrics.
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = self._read_events(cutoff)

        metrics: Dict[str, Any] = {
            "total_events": len(events),
            "by_type": defaultdict(int),
            "by_slot": defaultdict(int),
            "success_rate": 0.0,
            "error_count": 0,
        }

        for event in events:
            event_type = event.get("type", "unknown")
            metrics["by_type"][event_type] += 1
            slot = event.get("slot")
            if slot is not None:
                metrics["by_slot"][slot] += 1
            if "error" in event_type.lower() or "failure" in event_type.lower():
                metrics["error_count"] += 1

        if metrics["total_events"] > 0:
            metrics["success_rate"] = 1 - (metrics["error_count"] / metrics["total_events"])

        # Convert defaultdicts to regular dicts for JSON serialization
        metrics["by_type"] = dict(metrics["by_type"])
        metrics["by_slot"] = dict(metrics["by_slot"])

        self._metrics["metrics"] = metrics
        self._save_store()
        return metrics

    def _read_events(self, since: datetime) -> List[Dict[str, Any]]:
        """Read events from log files since given datetime.

        Args:
            since: Only include events after this datetime.

        Returns:
            List of event dictionaries.
        """
        events: List[Dict[str, Any]] = []
        if not self.log_dir.exists():
            return events

        for log_file in sorted(self.log_dir.glob("events_*.jsonl")):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        event = json.loads(line)
                        event_time = datetime.fromisoformat(event["timestamp"])
                        if event_time >= since:
                            events.append(event)
        return events

    def get_summary(self) -> str:
        """Get human-readable metrics summary.

        Returns:
            Formatted string with metrics summary.
        """
        m = self._metrics.get("metrics", {})
        return (
            f"Total Events: {m.get('total_events', 0)}\n"
            f"Success Rate: {m.get('success_rate', 0):.1%}\n"
            f"Errors: {m.get('error_count', 0)}\n"
            f"By Type: {m.get('by_type', {})}\n"
            f"By Slot: {m.get('by_slot', {})}"
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Get the current metrics.

        Returns:
            Dictionary containing the metrics data.
        """
        return self._metrics.get("metrics", {})
