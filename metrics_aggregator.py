"""Metrics aggregation for autonomous improvement cycles.

Tracks:
- Cycle success/failure rates
- PR merge rates
- Average time to completion
- Escalation frequency
"""

import json
import os
from datetime import datetime
from typing import Dict

METRICS_FILE = "cycle_metrics.json"


class MetricsAggregator:
    """Collect and aggregate metrics across discovery cycles."""

    def __init__(self, metrics_path: str = METRICS_FILE):
        self.metrics_path = metrics_path
        self.metrics = self._load_metrics()

    def _load_metrics(self) -> Dict:
        """Load existing metrics or create empty structure."""
        if os.path.exists(self.metrics_path):
            with open(self.metrics_path, "r") as f:
                return json.load(f)
        return {
            "cycles": [],
            "summary": {
                "total_cycles": 0,
                "successful_cycles": 0,
                "failed_cycles": 0,
                "total_prs_created": 0,
                "total_prs_merged": 0,
            },
        }

    def record_cycle_start(self, cycle_id: str) -> None:
        """Record the start of a new discovery cycle."""
        self.metrics["cycles"].append(
            {
                "cycle_id": cycle_id,
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "status": "in_progress",
                "prs_created": 0,
                "prs_merged": 0,
                "escalations": 0,
            }
        )
        self._save_metrics()

    def record_cycle_complete(
        self, cycle_id: str, success: bool, prs_created: int = 0, prs_merged: int = 0
    ) -> None:
        """Record cycle completion with outcome."""
        for cycle in self.metrics["cycles"]:
            if cycle["cycle_id"] == cycle_id:
                cycle["completed_at"] = datetime.now().isoformat()
                cycle["status"] = "success" if success else "failed"
                cycle["prs_created"] = prs_created
                cycle["prs_merged"] = prs_merged
                break

        self.metrics["summary"]["total_cycles"] += 1
        if success:
            self.metrics["summary"]["successful_cycles"] += 1
        else:
            self.metrics["summary"]["failed_cycles"] += 1
        self.metrics["summary"]["total_prs_created"] += prs_created
        self.metrics["summary"]["total_prs_merged"] += prs_merged
        self._save_metrics()

    def get_success_rate(self) -> float:
        """Calculate overall cycle success rate."""
        total = self.metrics["summary"]["total_cycles"]
        if total == 0:
            return 0.0
        return self.metrics["summary"]["successful_cycles"] / total

    def _save_metrics(self) -> None:
        """Persist metrics to file."""
        with open(self.metrics_path, "w") as f:
            json.dump(self.metrics, f, indent=2)
