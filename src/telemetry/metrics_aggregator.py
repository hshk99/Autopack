"""Metrics aggregation engine for Autopack telemetry."""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Batch size for streaming aggregation to prevent OOM on high-volume logs
BATCH_SIZE = 1000


@dataclass
class AggregatedMetric:
    """Represents an aggregated metric over a time period or grouping.

    Attributes:
        metric_name: Name identifying this metric.
        period: Time period or grouping identifier.
        count: Number of data points aggregated.
        sum_value: Sum of all values.
        avg_value: Average of all values.
        min_value: Minimum value observed.
        max_value: Maximum value observed.
    """

    metric_name: str
    period: str
    count: int
    sum_value: float
    avg_value: float
    min_value: float
    max_value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class StreamingAggregator:
    """Aggregates metrics incrementally without storing all events in memory.

    This class processes events one at a time, maintaining running statistics
    to avoid memory exhaustion when processing high-volume logs.
    """

    def __init__(self) -> None:
        """Initialize the streaming aggregator with empty statistics."""
        self.total_events: int = 0
        self.by_type: Dict[str, int] = defaultdict(int)
        self.by_slot: Dict[int, int] = defaultdict(int)
        self.error_count: int = 0
        self._events_with_duration: int = 0
        self._duration_sum: float = 0.0
        self._duration_min: float = float("inf")
        self._duration_max: float = 0.0

    def add(self, event: Dict[str, Any]) -> None:
        """Add a single event to the aggregation.

        Args:
            event: Event dictionary to aggregate.
        """
        self.total_events += 1

        event_type = event.get("type", "unknown")
        self.by_type[event_type] += 1

        slot = event.get("slot")
        if slot is not None:
            self.by_slot[slot] += 1

        if "error" in event_type.lower() or "failure" in event_type.lower():
            self.error_count += 1

        # Track duration statistics if present
        duration = event.get("duration")
        if duration is not None:
            self._events_with_duration += 1
            self._duration_sum += duration
            self._duration_min = min(self._duration_min, duration)
            self._duration_max = max(self._duration_max, duration)

    def finalize(self) -> Dict[str, Any]:
        """Finalize aggregation and return metrics dictionary.

        Returns:
            Dictionary containing aggregated metrics.
        """
        metrics: Dict[str, Any] = {
            "total_events": self.total_events,
            "by_type": dict(self.by_type),
            "by_slot": dict(self.by_slot),
            "success_rate": 0.0,
            "error_count": self.error_count,
        }

        if self.total_events > 0:
            metrics["success_rate"] = 1 - (self.error_count / self.total_events)

        # Add duration statistics if any events had duration
        if self._events_with_duration > 0:
            metrics["duration_stats"] = {
                "count": self._events_with_duration,
                "sum": self._duration_sum,
                "avg": self._duration_sum / self._events_with_duration,
                "min": self._duration_min,
                "max": self._duration_max,
            }

        return metrics


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

        Uses streaming aggregation to process events in batches of BATCH_SIZE
        to prevent memory exhaustion when processing high-volume logs.

        Args:
            since_hours: Number of hours to look back for events.

        Returns:
            Dictionary containing aggregated metrics.
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)

        # Use streaming aggregation to avoid loading all events into memory
        aggregator = StreamingAggregator()
        events_processed = 0

        for event in self._stream_events(cutoff):
            aggregator.add(event)
            events_processed += 1

            # Log progress for long operations
            if events_processed % 10000 == 0:
                logger.debug(f"Processed {events_processed} events")

        metrics = aggregator.finalize()

        self._metrics["metrics"] = metrics
        self._save_store()
        return metrics

    def _stream_events(self, since: datetime) -> Generator[Dict[str, Any], None, None]:
        """Stream events from log files since given datetime.

        This generator yields events one at a time without loading all events
        into memory, preventing OOM crashes for high-volume logs.

        Args:
            since: Only include events after this datetime.

        Yields:
            Event dictionaries matching the time filter.
        """
        if not self.log_dir.exists():
            return

        for log_file in sorted(self.log_dir.glob("events_*.jsonl")):
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            event = json.loads(line)
                            event_time = datetime.fromisoformat(event["timestamp"])
                            if event_time >= since:
                                yield event
                        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
                            # Log but continue - don't let one bad event crash aggregation
                            logger.warning(f"Skipping malformed event in {log_file}: {e}")
                            continue

    def _read_events(self, since: datetime) -> List[Dict[str, Any]]:
        """Read events from log files since given datetime.

        Note: This method loads all events into memory. For high-volume logs,
        prefer using _stream_events() or the aggregate() method which uses
        streaming aggregation.

        Args:
            since: Only include events after this datetime.

        Returns:
            List of event dictionaries.
        """
        return list(self._stream_events(since))

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

    def aggregate_by_period(
        self,
        metric_name: str,
        period: timedelta,
        since_hours: int = 24,
    ) -> List[AggregatedMetric]:
        """Aggregate metrics over time periods.

        Groups events into time buckets based on the period duration
        and computes aggregate statistics for each bucket.

        Args:
            metric_name: Name to identify this aggregation.
            period: Duration of each time bucket.
            since_hours: Number of hours to look back.

        Returns:
            List of AggregatedMetric objects, one per time period.
        """
        try:
            cutoff = datetime.now() - timedelta(hours=since_hours)
            events = self._read_events(cutoff)
        except Exception as e:
            logger.error(f"Failed to read events for period aggregation: {e}")
            return []

        if not events:
            return []

        # Group events by time period
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        skipped_count = 0

        for event in events:
            try:
                event_time = datetime.fromisoformat(event["timestamp"])
                # Calculate bucket start time
                bucket_start = cutoff + timedelta(
                    seconds=(
                        (event_time - cutoff).total_seconds()
                        // period.total_seconds()
                        * period.total_seconds()
                    )
                )
                bucket_key = bucket_start.isoformat()
                buckets[bucket_key].append(event)
            except (KeyError, TypeError, ValueError) as err:
                skipped_count += 1
                logger.warning(f"Skipping malformed event in period aggregation: {err}")
                continue

        if skipped_count > 0:
            logger.debug(f"Skipped {skipped_count} malformed events in period aggregation")

        # Convert buckets to AggregatedMetric objects
        results: List[AggregatedMetric] = []
        for period_key, bucket_events in sorted(buckets.items()):
            try:
                count = len(bucket_events)
                # For events, we aggregate counts (value=1 per event)
                results.append(
                    AggregatedMetric(
                        metric_name=metric_name,
                        period=period_key,
                        count=count,
                        sum_value=float(count),
                        avg_value=1.0,
                        min_value=1.0,
                        max_value=1.0,
                        metadata={"event_types": list({e.get("type") for e in bucket_events})},
                    )
                )
            except (TypeError, ValueError) as err:
                logger.warning(f"Error creating metric for period '{period_key}': {err}")
                continue

        return results

    def aggregate_by_component(
        self,
        metric_name: str,
        since_hours: int = 24,
    ) -> Dict[str, AggregatedMetric]:
        """Aggregate metrics by component/source.

        Groups events by their source or component field and computes
        aggregate statistics for each group.

        Args:
            metric_name: Name to identify this aggregation.
            since_hours: Number of hours to look back.

        Returns:
            Dictionary mapping component names to AggregatedMetric objects.
        """
        try:
            cutoff = datetime.now() - timedelta(hours=since_hours)
            events = self._read_events(cutoff)
        except Exception as e:
            logger.error(f"Failed to read events for component aggregation: {e}")
            return {}

        if not events:
            return {}

        # Group events by component (using 'type' as component proxy)
        components: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        skipped_count = 0

        for event in events:
            try:
                component = event.get("type", "unknown")
                components[component].append(event)
            except (AttributeError, TypeError) as err:
                skipped_count += 1
                logger.warning(f"Skipping malformed event in component aggregation: {err}")
                continue

        if skipped_count > 0:
            logger.debug(f"Skipped {skipped_count} malformed events in component aggregation")

        # Convert to AggregatedMetric objects
        results: Dict[str, AggregatedMetric] = {}
        for component, component_events in components.items():
            try:
                count = len(component_events)
                results[component] = AggregatedMetric(
                    metric_name=metric_name,
                    period=component,
                    count=count,
                    sum_value=float(count),
                    avg_value=1.0,
                    min_value=1.0,
                    max_value=1.0,
                    metadata={
                        "slots": list({e.get("slot") for e in component_events if e.get("slot")}),
                    },
                )
            except (TypeError, ValueError) as err:
                logger.warning(f"Error creating metric for component '{component}': {err}")
                continue

        return results
