"""Performance metrics collector for execution optimization."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class PerformanceMetric:
    """A single performance measurement."""

    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    context: dict = field(default_factory=dict)


@dataclass
class SlotUtilization:
    """Slot utilization metrics."""

    slot_id: int
    total_time: timedelta
    busy_time: timedelta
    idle_time: timedelta
    utilization_percent: float


class PerformanceCollector:
    """Collects and aggregates performance metrics.

    Tracks phase durations, slot utilization, CI wait times, and wave
    throughput for optimization analysis.
    """

    def __init__(self, metrics_path: Optional[str] = None):
        """Initialize the performance collector.

        Args:
            metrics_path: Path to metrics JSON file. Defaults to
                         performance_metrics.json in current directory.
        """
        self.metrics_path = Path(metrics_path or "performance_metrics.json")
        self.metrics: list[PerformanceMetric] = []
        self._load_metrics()

    def _load_metrics(self) -> None:
        """Load existing metrics from file."""
        if self.metrics_path.exists():
            with open(self.metrics_path, encoding="utf-8") as f:
                data = json.load(f)
                for m in data.get("metrics", []):
                    self.metrics.append(
                        PerformanceMetric(
                            metric_name=m["metric_name"],
                            value=m["value"],
                            unit=m["unit"],
                            timestamp=datetime.fromisoformat(m["timestamp"]),
                            context=m.get("context", {}),
                        )
                    )

    def _save_metrics(self) -> None:
        """Save metrics to file."""
        data = {
            "metrics": [
                {
                    "metric_name": m.metric_name,
                    "value": m.value,
                    "unit": m.unit,
                    "timestamp": m.timestamp.isoformat(),
                    "context": m.context,
                }
                for m in self.metrics
            ]
        }
        with open(self.metrics_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record_phase_duration(
        self,
        phase_id: str,
        start: datetime,
        end: datetime,
        imp_id: Optional[str] = None,
    ) -> PerformanceMetric:
        """Record duration of a phase execution.

        Args:
            phase_id: The phase identifier
            start: Start time
            end: End time
            imp_id: Optional improvement ID

        Returns:
            The recorded metric
        """
        duration = (end - start).total_seconds()
        metric = PerformanceMetric(
            metric_name="phase_duration",
            value=duration,
            unit="seconds",
            timestamp=end,
            context={
                "phase_id": phase_id,
                "imp_id": imp_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        self.metrics.append(metric)
        self._save_metrics()
        return metric

    def record_slot_utilization(
        self,
        slot_id: int,
        busy_time: timedelta,
        idle_time: timedelta,
    ) -> SlotUtilization:
        """Record slot utilization metrics.

        Args:
            slot_id: The slot ID
            busy_time: Time slot was actively processing
            idle_time: Time slot was idle

        Returns:
            SlotUtilization summary
        """
        total = busy_time + idle_time
        utilization = (
            busy_time.total_seconds() / total.total_seconds() * 100
            if total.total_seconds() > 0
            else 0.0
        )

        metric = PerformanceMetric(
            metric_name="slot_utilization",
            value=utilization,
            unit="percent",
            timestamp=datetime.now(),
            context={
                "slot_id": slot_id,
                "busy_seconds": busy_time.total_seconds(),
                "idle_seconds": idle_time.total_seconds(),
            },
        )
        self.metrics.append(metric)
        self._save_metrics()

        return SlotUtilization(
            slot_id=slot_id,
            total_time=total,
            busy_time=busy_time,
            idle_time=idle_time,
            utilization_percent=utilization,
        )

    def record_ci_wait_time(
        self,
        pr_number: int,
        wait_seconds: float,
        outcome: str,
    ) -> PerformanceMetric:
        """Record CI wait time for a PR.

        Args:
            pr_number: The PR number
            wait_seconds: How long CI took
            outcome: 'success', 'failure', 'timeout'

        Returns:
            The recorded metric
        """
        metric = PerformanceMetric(
            metric_name="ci_wait_time",
            value=wait_seconds,
            unit="seconds",
            timestamp=datetime.now(),
            context={"pr_number": pr_number, "outcome": outcome},
        )
        self.metrics.append(metric)
        self._save_metrics()
        return metric

    def record_wave_throughput(
        self,
        wave_number: int,
        phases_completed: int,
        duration: timedelta,
    ) -> PerformanceMetric:
        """Record wave throughput.

        Args:
            wave_number: Wave identifier
            phases_completed: Number of phases completed
            duration: Total wave duration

        Returns:
            The recorded metric
        """
        hours = duration.total_seconds() / 3600
        throughput = phases_completed / hours if hours > 0 else 0.0

        metric = PerformanceMetric(
            metric_name="wave_throughput",
            value=throughput,
            unit="phases_per_hour",
            timestamp=datetime.now(),
            context={
                "wave_number": wave_number,
                "phases_completed": phases_completed,
                "duration_seconds": duration.total_seconds(),
            },
        )
        self.metrics.append(metric)
        self._save_metrics()
        return metric

    def get_efficiency_report(self) -> dict:
        """Generate efficiency report from collected metrics.

        Returns:
            Dict with aggregated efficiency metrics
        """
        if not self.metrics:
            return {"error": "No metrics collected yet"}

        phase_durations = [m.value for m in self.metrics if m.metric_name == "phase_duration"]
        ci_waits = [m.value for m in self.metrics if m.metric_name == "ci_wait_time"]
        utilizations = [m.value for m in self.metrics if m.metric_name == "slot_utilization"]

        return {
            "phase_completion": {
                "count": len(phase_durations),
                "avg_seconds": (
                    sum(phase_durations) / len(phase_durations) if phase_durations else 0
                ),
                "min_seconds": min(phase_durations) if phase_durations else 0,
                "max_seconds": max(phase_durations) if phase_durations else 0,
            },
            "ci_performance": {
                "count": len(ci_waits),
                "avg_wait_seconds": (sum(ci_waits) / len(ci_waits) if ci_waits else 0),
            },
            "slot_efficiency": {
                "avg_utilization_percent": (
                    sum(utilizations) / len(utilizations) if utilizations else 0
                ),
            },
            "generated_at": datetime.now().isoformat(),
        }


# Global collector instance
_default_collector: Optional[PerformanceCollector] = None


def get_collector(metrics_path: Optional[str] = None) -> PerformanceCollector:
    """Get or create the default PerformanceCollector instance.

    Args:
        metrics_path: Optional path override for metrics file.

    Returns:
        The PerformanceCollector instance.
    """
    global _default_collector
    if _default_collector is None or metrics_path is not None:
        _default_collector = PerformanceCollector(metrics_path)
    return _default_collector


def record_metric_from_ps(metric_type: str, **kwargs) -> None:
    """Helper for recording metrics from PowerShell scripts.

    Args:
        metric_type: One of 'phase', 'slot', 'ci', 'wave'
        **kwargs: Arguments for the specific metric type
    """
    collector = get_collector()

    if metric_type == "phase":
        collector.record_phase_duration(
            phase_id=kwargs["phase_id"],
            start=datetime.fromisoformat(kwargs["start"]),
            end=datetime.fromisoformat(kwargs["end"]),
            imp_id=kwargs.get("imp_id"),
        )
    elif metric_type == "ci":
        collector.record_ci_wait_time(
            pr_number=kwargs["pr_number"],
            wait_seconds=kwargs["wait_seconds"],
            outcome=kwargs["outcome"],
        )
    elif metric_type == "slot":
        collector.record_slot_utilization(
            slot_id=kwargs["slot_id"],
            busy_time=timedelta(seconds=kwargs["busy_seconds"]),
            idle_time=timedelta(seconds=kwargs["idle_seconds"]),
        )
    elif metric_type == "wave":
        collector.record_wave_throughput(
            wave_number=kwargs["wave_number"],
            phases_completed=kwargs["phases_completed"],
            duration=timedelta(seconds=kwargs["duration_seconds"]),
        )
