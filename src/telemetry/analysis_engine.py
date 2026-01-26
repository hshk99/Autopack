"""Telemetry analysis engine for pattern detection and insights."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .pattern_detector import PatternDetector
from .unified_event_log import UnifiedEventLog


@dataclass
class AnalysisInsight:
    """Represents an actionable insight derived from telemetry analysis.

    Attributes:
        pattern_type: Category of the detected pattern.
        confidence: Confidence score from 0.0 to 1.0.
        description: Human-readable description of the insight.
        affected_components: List of components affected by this pattern.
        recommended_action: Suggested action to address the insight.
    """

    pattern_type: str
    confidence: float
    description: str
    affected_components: List[str]
    recommended_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnalysisEngine:
    """Analyzes telemetry data to extract actionable insights.

    Provides pattern detection, success rate computation, recurring
    issue identification, and bottleneck detection capabilities.
    """

    def __init__(self, event_log: UnifiedEventLog) -> None:
        """Initialize the analysis engine.

        Args:
            event_log: UnifiedEventLog instance to analyze.
        """
        self.event_log = event_log
        self.pattern_detector = PatternDetector()

    def detect_error_patterns(
        self,
        since_hours: int = 24,
        min_occurrences: int = 2,
    ) -> List[AnalysisInsight]:
        """Analyze events to detect recurring error patterns.

        Identifies patterns in error events that occur multiple times,
        indicating systematic issues that need attention.

        Args:
            since_hours: Number of hours to look back for events.
            min_occurrences: Minimum pattern occurrences to report.

        Returns:
            List of AnalysisInsight objects describing detected patterns.
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = self.event_log.query({"since": cutoff.isoformat()})

        # Filter for error-related events
        error_events = [
            e
            for e in events
            if "error" in e.event_type.lower()
            or "failure" in e.event_type.lower()
            or e.payload.get("status") == "error"
        ]

        if not error_events:
            return []

        # Group error events by characteristics
        error_groups: Dict[str, List[Any]] = defaultdict(list)
        for event in error_events:
            key = f"{event.source}:{event.event_type}"
            error_groups[key].append(event)

        # Detect patterns and create insights
        insights: List[AnalysisInsight] = []
        for group_key, group_events in error_groups.items():
            if len(group_events) < min_occurrences:
                continue

            # Register pattern with detector
            event_dicts = [e.to_dict() for e in group_events]
            pattern = self.pattern_detector.register_pattern(event_dicts)

            if pattern:
                source, event_type = group_key.split(":", 1)
                affected = list({e.phase_id for e in group_events if e.phase_id})

                confidence = min(1.0, len(group_events) / 10.0)

                insights.append(
                    AnalysisInsight(
                        pattern_type="error_pattern",
                        confidence=confidence,
                        description=(
                            f"Detected {len(group_events)} occurrences of "
                            f"{event_type} errors from {source}"
                        ),
                        affected_components=affected or [source],
                        recommended_action=(
                            f"Investigate {event_type} errors in {source} component"
                        ),
                        metadata={
                            "pattern_id": pattern.pattern_id,
                            "occurrence_count": len(group_events),
                            "first_seen": pattern.first_seen,
                            "last_seen": pattern.last_seen,
                        },
                    )
                )

        return sorted(insights, key=lambda i: i.confidence, reverse=True)

    def compute_success_rates(
        self,
        since_hours: int = 24,
    ) -> Dict[str, float]:
        """Calculate success rates by improvement category.

        Computes the ratio of successful to total events for each
        source/category in the telemetry data.

        Args:
            since_hours: Number of hours to look back for events.

        Returns:
            Dictionary mapping category names to success rates (0.0-1.0).
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = self.event_log.query({"since": cutoff.isoformat()})

        if not events:
            return {}

        # Group by source and count success/failure
        stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "total": 0})

        for event in events:
            category: str = event.source
            stats[category]["total"] += 1

            # Determine if event represents success
            is_error = (
                "error" in event.event_type.lower()
                or "failure" in event.event_type.lower()
                or event.payload.get("status") == "error"
                or event.payload.get("success") is False
            )

            if not is_error:
                stats[category]["success"] += 1

        # Calculate rates
        rates: Dict[str, float] = {}
        for category, counts in stats.items():
            if counts["total"] > 0:
                rates[category] = counts["success"] / counts["total"]
            else:
                rates[category] = 0.0

        return rates

    def identify_recurring_issues(
        self,
        since_hours: int = 72,
        min_recurrences: int = 3,
    ) -> List[AnalysisInsight]:
        """Find issues that occur repeatedly across phases.

        Identifies problems that persist or recur over time, indicating
        underlying issues that haven't been fully resolved.

        Args:
            since_hours: Number of hours to look back.
            min_recurrences: Minimum recurrences to flag as recurring.

        Returns:
            List of AnalysisInsight objects for recurring issues.
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = self.event_log.query({"since": cutoff.isoformat()})

        # Track issue occurrences by signature
        issue_tracker: Dict[str, List[Any]] = defaultdict(list)

        for event in events:
            if (
                "error" in event.event_type.lower()
                or "failure" in event.event_type.lower()
                or "retry" in event.event_type.lower()
            ):
                # Create issue signature
                error_type = event.payload.get("error_type", event.event_type)
                signature = f"{event.source}:{error_type}"
                issue_tracker[signature].append(event)

        insights: List[AnalysisInsight] = []

        for signature, occurrences in issue_tracker.items():
            if len(occurrences) < min_recurrences:
                continue

            source, error_type = signature.split(":", 1)
            phases = list({e.phase_id for e in occurrences if e.phase_id})
            slots = list({e.slot_id for e in occurrences if e.slot_id})

            # Calculate time span
            timestamps = sorted(e.timestamp for e in occurrences)
            time_span = timestamps[-1] - timestamps[0]
            hours_span = time_span.total_seconds() / 3600

            confidence = min(1.0, len(occurrences) / 5.0 * (hours_span / since_hours + 0.5))

            insights.append(
                AnalysisInsight(
                    pattern_type="recurring_issue",
                    confidence=confidence,
                    description=(
                        f"Issue '{error_type}' has occurred {len(occurrences)} times "
                        f"over {hours_span:.1f} hours in {source}"
                    ),
                    affected_components=phases or [source],
                    recommended_action=(f"Review root cause of recurring {error_type} in {source}"),
                    metadata={
                        "occurrence_count": len(occurrences),
                        "affected_slots": slots,
                        "time_span_hours": hours_span,
                        "first_occurrence": timestamps[0].isoformat(),
                        "last_occurrence": timestamps[-1].isoformat(),
                    },
                )
            )

        return sorted(insights, key=lambda i: i.confidence, reverse=True)

    def detect_bottlenecks(
        self,
        since_hours: int = 24,
        duration_threshold_seconds: float = 60.0,
    ) -> List[AnalysisInsight]:
        """Identify execution bottlenecks from telemetry.

        Analyzes event timing to find operations that take unusually
        long or cause delays in the system.

        Args:
            since_hours: Number of hours to look back.
            duration_threshold_seconds: Minimum duration to flag as bottleneck.

        Returns:
            List of AnalysisInsight objects for detected bottlenecks.
        """
        cutoff = datetime.now() - timedelta(hours=since_hours)
        events = self.event_log.query({"since": cutoff.isoformat()})

        if not events:
            return []

        insights: List[AnalysisInsight] = []

        # Analyze events with duration information
        duration_stats: Dict[str, List[float]] = defaultdict(list)

        for event in events:
            duration = event.payload.get("duration_seconds")
            if duration is not None:
                key = f"{event.source}:{event.event_type}"
                duration_stats[key].append(float(duration))

        # Identify bottlenecks
        for operation, durations in duration_stats.items():
            if not durations:
                continue

            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            if avg_duration >= duration_threshold_seconds:
                source, event_type = operation.split(":", 1)
                confidence = min(1.0, avg_duration / (duration_threshold_seconds * 5))

                insights.append(
                    AnalysisInsight(
                        pattern_type="bottleneck",
                        confidence=confidence,
                        description=(
                            f"Operation '{event_type}' in {source} averages "
                            f"{avg_duration:.1f}s (max: {max_duration:.1f}s)"
                        ),
                        affected_components=[source],
                        recommended_action=(
                            f"Optimize {event_type} operation in {source} to reduce execution time"
                        ),
                        metadata={
                            "avg_duration_seconds": avg_duration,
                            "max_duration_seconds": max_duration,
                            "sample_count": len(durations),
                        },
                    )
                )

        # Also check for retry patterns indicating bottlenecks
        retry_counts: Dict[str, int] = defaultdict(int)
        for event in events:
            if "retry" in event.event_type.lower():
                key = f"{event.source}:retry"
                retry_counts[key] += 1

        for operation, count in retry_counts.items():
            if count >= 3:  # Multiple retries indicate potential bottleneck
                source = operation.split(":")[0]
                confidence = min(1.0, count / 10.0)

                insights.append(
                    AnalysisInsight(
                        pattern_type="bottleneck",
                        confidence=confidence,
                        description=(
                            f"High retry count ({count}) detected in {source}, "
                            f"indicating potential resource contention"
                        ),
                        affected_components=[source],
                        recommended_action=(
                            f"Investigate retry causes in {source} - "
                            f"may indicate capacity or reliability issues"
                        ),
                        metadata={
                            "retry_count": count,
                            "bottleneck_type": "retry_pattern",
                        },
                    )
                )

        return sorted(insights, key=lambda i: i.confidence, reverse=True)

    def get_comprehensive_analysis(
        self,
        since_hours: int = 24,
    ) -> Dict[str, Any]:
        """Run all analysis methods and return combined results.

        Convenience method that executes all analysis types and
        combines them into a single report.

        Args:
            since_hours: Number of hours to look back.

        Returns:
            Dictionary containing all analysis results.
        """
        return {
            "error_patterns": [
                {
                    "pattern_type": i.pattern_type,
                    "confidence": i.confidence,
                    "description": i.description,
                    "affected_components": i.affected_components,
                    "recommended_action": i.recommended_action,
                    "metadata": i.metadata,
                }
                for i in self.detect_error_patterns(since_hours)
            ],
            "success_rates": self.compute_success_rates(since_hours),
            "recurring_issues": [
                {
                    "pattern_type": i.pattern_type,
                    "confidence": i.confidence,
                    "description": i.description,
                    "affected_components": i.affected_components,
                    "recommended_action": i.recommended_action,
                    "metadata": i.metadata,
                }
                for i in self.identify_recurring_issues(since_hours * 3)
            ],
            "bottlenecks": [
                {
                    "pattern_type": i.pattern_type,
                    "confidence": i.confidence,
                    "description": i.description,
                    "affected_components": i.affected_components,
                    "recommended_action": i.recommended_action,
                    "metadata": i.metadata,
                }
                for i in self.detect_bottlenecks(since_hours)
            ],
            "analysis_timestamp": datetime.now().isoformat(),
            "analysis_window_hours": since_hours,
        }
