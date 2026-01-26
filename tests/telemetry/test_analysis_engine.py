"""Tests for telemetry analysis engine, pattern detector, and metrics aggregator extensions."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from telemetry.analysis_engine import AnalysisEngine, AnalysisInsight
from telemetry.event_schema import TelemetryEvent
from telemetry.metrics_aggregator import AggregatedMetric, MetricsAggregator
from telemetry.pattern_detector import Pattern, PatternDetector
from telemetry.unified_event_log import UnifiedEventLog


@pytest.fixture
def temp_log_path():
    """Create a temporary file path for event log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "events.jsonl")


@pytest.fixture
def event_log(temp_log_path):
    """Create a UnifiedEventLog instance."""
    return UnifiedEventLog(temp_log_path)


@pytest.fixture
def analysis_engine(event_log):
    """Create an AnalysisEngine instance."""
    return AnalysisEngine(event_log)


@pytest.fixture
def pattern_detector():
    """Create a PatternDetector instance."""
    return PatternDetector()


class TestPattern:
    """Tests for Pattern dataclass."""

    def test_pattern_creation(self):
        """Test basic Pattern creation."""
        pattern = Pattern(
            pattern_id="abc123",
            occurrences=5,
            first_seen="2024-01-01T00:00:00",
            last_seen="2024-01-02T00:00:00",
            signature={"event_type": "error", "source": "ci_retry"},
        )

        assert pattern.pattern_id == "abc123"
        assert pattern.occurrences == 5
        assert pattern.signature["event_type"] == "error"

    def test_pattern_matches(self):
        """Test Pattern.matches method."""
        pattern = Pattern(
            pattern_id="test",
            occurrences=1,
            first_seen="2024-01-01",
            last_seen="2024-01-01",
            signature={"event_type": "error", "source": "ci_retry"},
        )

        assert pattern.matches({"event_type": "error", "source": "ci_retry"})
        assert pattern.matches({"event_type": "error", "source": "ci_retry", "extra": "field"})
        assert not pattern.matches({"event_type": "success", "source": "ci_retry"})
        assert not pattern.matches({"event_type": "error"})


class TestPatternDetector:
    """Tests for PatternDetector class."""

    def test_init(self, pattern_detector):
        """Test PatternDetector initialization."""
        assert pattern_detector.known_patterns == {}
        assert pattern_detector.get_pattern_count() == 0

    def test_register_pattern_empty_events(self, pattern_detector):
        """Test registering pattern with empty event list."""
        result = pattern_detector.register_pattern([])
        assert result is None

    def test_register_pattern_single_event(self, pattern_detector):
        """Test registering pattern from single event."""
        events = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]

        pattern = pattern_detector.register_pattern(events)

        assert pattern is not None
        assert pattern.occurrences == 1
        assert pattern.signature["event_type"] == "ci_failure"

    def test_register_pattern_increments_occurrences(self, pattern_detector):
        """Test that registering same pattern increments occurrences."""
        events = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]

        pattern1 = pattern_detector.register_pattern(events)
        pattern2 = pattern_detector.register_pattern(events)

        assert pattern1.pattern_id == pattern2.pattern_id
        assert pattern2.occurrences == 2
        assert pattern_detector.get_pattern_count() == 1

    def test_match_pattern(self, pattern_detector):
        """Test matching events against known patterns."""
        events = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]
        pattern_detector.register_pattern(events)

        match = pattern_detector.match_pattern(
            {"event_type": "ci_failure", "source": "ci_retry", "payload": {}}
        )

        assert match is not None
        assert match.signature["event_type"] == "ci_failure"

    def test_match_pattern_no_match(self, pattern_detector):
        """Test matching when no patterns exist."""
        match = pattern_detector.match_pattern({"event_type": "success", "source": "test"})
        assert match is None

    def test_get_frequent_patterns(self, pattern_detector):
        """Test getting patterns by frequency."""
        events1 = [{"event_type": "error_a", "source": "test", "payload": {}}]
        events2 = [{"event_type": "error_b", "source": "test", "payload": {}}]

        # Register error_a 3 times
        for _ in range(3):
            pattern_detector.register_pattern(events1)

        # Register error_b 1 time
        pattern_detector.register_pattern(events2)

        frequent = pattern_detector.get_frequent_patterns(min_occurrences=2)

        assert len(frequent) == 1
        assert frequent[0].occurrences == 3

    def test_clear_patterns(self, pattern_detector):
        """Test clearing all patterns."""
        events = [{"event_type": "test", "source": "test", "payload": {}}]
        pattern_detector.register_pattern(events)

        pattern_detector.clear_patterns()

        assert pattern_detector.get_pattern_count() == 0


class TestAnalysisInsight:
    """Tests for AnalysisInsight dataclass."""

    def test_insight_creation(self):
        """Test basic AnalysisInsight creation."""
        insight = AnalysisInsight(
            pattern_type="error_pattern",
            confidence=0.85,
            description="Test insight",
            affected_components=["component_a", "component_b"],
            recommended_action="Fix the issue",
        )

        assert insight.pattern_type == "error_pattern"
        assert insight.confidence == 0.85
        assert len(insight.affected_components) == 2
        assert insight.metadata == {}

    def test_insight_with_metadata(self):
        """Test AnalysisInsight with metadata."""
        insight = AnalysisInsight(
            pattern_type="bottleneck",
            confidence=0.9,
            description="Slow operation",
            affected_components=["api"],
            recommended_action="Optimize",
            metadata={"duration": 120, "samples": 10},
        )

        assert insight.metadata["duration"] == 120
        assert insight.metadata["samples"] == 10


class TestAnalysisEngine:
    """Tests for AnalysisEngine class."""

    def test_init(self, analysis_engine, event_log):
        """Test AnalysisEngine initialization."""
        assert analysis_engine.event_log is event_log
        assert analysis_engine.pattern_detector is not None

    def test_detect_error_patterns_empty(self, analysis_engine):
        """Test error pattern detection with no events."""
        insights = analysis_engine.detect_error_patterns()
        assert insights == []

    def test_detect_error_patterns_with_errors(self, analysis_engine, event_log):
        """Test error pattern detection with error events."""
        now = datetime.now()

        # Add error events
        for i in range(3):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="ci_failure",
                slot_id=1,
                phase_id="phase-1",
                payload={"error_type": "test_failure"},
            )
            event_log.ingest(event)

        insights = analysis_engine.detect_error_patterns(since_hours=1, min_occurrences=2)

        assert len(insights) >= 1
        assert insights[0].pattern_type == "error_pattern"
        assert "ci_failure" in insights[0].description

    def test_compute_success_rates_empty(self, analysis_engine):
        """Test success rate computation with no events."""
        rates = analysis_engine.compute_success_rates()
        assert rates == {}

    def test_compute_success_rates(self, analysis_engine, event_log):
        """Test success rate computation."""
        now = datetime.now()

        # Add 8 success events
        for i in range(8):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="pr_merged",
                payload={},
            )
            event_log.ingest(event)

        # Add 2 error events
        for i in range(2):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i + 10),
                source="ci_retry",
                event_type="ci_failure",
                payload={},
            )
            event_log.ingest(event)

        rates = analysis_engine.compute_success_rates(since_hours=1)

        assert "ci_retry" in rates
        assert rates["ci_retry"] == 0.8  # 8 success out of 10

    def test_identify_recurring_issues_empty(self, analysis_engine):
        """Test recurring issue identification with no events."""
        insights = analysis_engine.identify_recurring_issues()
        assert insights == []

    def test_identify_recurring_issues(self, analysis_engine, event_log):
        """Test recurring issue identification."""
        now = datetime.now()

        # Add recurring error events over time
        for i in range(5):
            event = TelemetryEvent(
                timestamp=now - timedelta(hours=i),
                source="slot_history",
                event_type="connection_error",
                slot_id=1,
                phase_id=f"phase-{i}",
                payload={"error_type": "timeout"},
            )
            event_log.ingest(event)

        insights = analysis_engine.identify_recurring_issues(since_hours=24, min_recurrences=3)

        assert len(insights) >= 1
        assert insights[0].pattern_type == "recurring_issue"
        assert insights[0].metadata["occurrence_count"] >= 3

    def test_detect_bottlenecks_empty(self, analysis_engine):
        """Test bottleneck detection with no events."""
        insights = analysis_engine.detect_bottlenecks()
        assert insights == []

    def test_detect_bottlenecks_with_duration(self, analysis_engine, event_log):
        """Test bottleneck detection with duration data."""
        now = datetime.now()

        # Add events with long duration
        for i in range(3):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="build_process",
                payload={"duration_seconds": 120.0},
            )
            event_log.ingest(event)

        insights = analysis_engine.detect_bottlenecks(
            since_hours=1, duration_threshold_seconds=60.0
        )

        assert len(insights) >= 1
        assert insights[0].pattern_type == "bottleneck"
        assert insights[0].metadata["avg_duration_seconds"] >= 60.0

    def test_detect_bottlenecks_retry_pattern(self, analysis_engine, event_log):
        """Test bottleneck detection with retry patterns."""
        now = datetime.now()

        # Add multiple retry events
        for i in range(5):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="ci_retry_attempt",
                payload={},
            )
            event_log.ingest(event)

        insights = analysis_engine.detect_bottlenecks(since_hours=1)

        retry_insights = [
            i for i in insights if i.metadata.get("bottleneck_type") == "retry_pattern"
        ]
        assert len(retry_insights) >= 1

    def test_get_comprehensive_analysis(self, analysis_engine, event_log):
        """Test comprehensive analysis output."""
        now = datetime.now()

        # Add some events
        event = TelemetryEvent(
            timestamp=now,
            source="ci_retry",
            event_type="test_event",
            payload={},
        )
        event_log.ingest(event)

        result = analysis_engine.get_comprehensive_analysis(since_hours=1)

        assert "error_patterns" in result
        assert "success_rates" in result
        assert "recurring_issues" in result
        assert "bottlenecks" in result
        assert "analysis_timestamp" in result
        assert result["analysis_window_hours"] == 1


class TestAggregatedMetric:
    """Tests for AggregatedMetric dataclass."""

    def test_aggregated_metric_creation(self):
        """Test basic AggregatedMetric creation."""
        metric = AggregatedMetric(
            metric_name="event_count",
            period="2024-01-01T00:00:00",
            count=10,
            sum_value=10.0,
            avg_value=1.0,
            min_value=1.0,
            max_value=1.0,
        )

        assert metric.metric_name == "event_count"
        assert metric.count == 10
        assert metric.metadata == {}

    def test_aggregated_metric_with_metadata(self):
        """Test AggregatedMetric with metadata."""
        metric = AggregatedMetric(
            metric_name="duration",
            period="hourly",
            count=5,
            sum_value=500.0,
            avg_value=100.0,
            min_value=50.0,
            max_value=150.0,
            metadata={"unit": "seconds"},
        )

        assert metric.metadata["unit"] == "seconds"


class TestMetricsAggregatorExtensions:
    """Tests for MetricsAggregator extension methods."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for log and store files."""
        with tempfile.TemporaryDirectory() as log_dir:
            with tempfile.TemporaryDirectory() as store_dir:
                yield log_dir, store_dir

    @pytest.fixture
    def aggregator(self, temp_dirs):
        """Create a MetricsAggregator instance."""
        log_dir, store_dir = temp_dirs
        store_path = Path(store_dir) / "metrics_store.json"
        return MetricsAggregator(log_dir=log_dir, store_path=str(store_path))

    def _write_event(self, log_dir: str, event: dict) -> None:
        """Helper to write an event to a log file."""
        import json

        date_str = datetime.now().strftime("%Y%m%d")
        log_file = Path(log_dir) / f"events_{date_str}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def test_aggregate_by_period_empty(self, aggregator):
        """Test aggregate_by_period with no events."""
        result = aggregator.aggregate_by_period("events", timedelta(hours=1))
        assert result == []

    def test_aggregate_by_period(self, aggregator, temp_dirs):
        """Test aggregate_by_period groups events correctly."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Add events at different times
        for i in range(5):
            event = {
                "timestamp": (now - timedelta(minutes=i * 10)).isoformat(),
                "type": "test_event",
                "slot": None,
                "data": {},
            }
            self._write_event(log_dir, event)

        result = aggregator.aggregate_by_period("test_metric", timedelta(hours=1), since_hours=2)

        assert len(result) >= 1
        assert all(isinstance(m, AggregatedMetric) for m in result)
        total_count = sum(m.count for m in result)
        assert total_count == 5

    def test_aggregate_by_component_empty(self, aggregator):
        """Test aggregate_by_component with no events."""
        result = aggregator.aggregate_by_component("events")
        assert result == {}

    def test_aggregate_by_component(self, aggregator, temp_dirs):
        """Test aggregate_by_component groups by type."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Add events of different types
        events = [
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": 1, "data": {}},
            {"timestamp": now.isoformat(), "type": "pr_merged", "slot": 2, "data": {}},
            {"timestamp": now.isoformat(), "type": "ci_failure", "slot": 1, "data": {}},
        ]
        for event in events:
            self._write_event(log_dir, event)

        result = aggregator.aggregate_by_component("test_metric", since_hours=1)

        assert "pr_merged" in result
        assert "ci_failure" in result
        assert result["pr_merged"].count == 2
        assert result["ci_failure"].count == 1
        assert isinstance(result["pr_merged"], AggregatedMetric)


class TestPatternDetectorEdgeCases:
    """Edge case tests for PatternDetector."""

    def test_extract_signature_with_error_fields(self):
        """Test signature extraction includes error-related fields."""
        detector = PatternDetector()

        event = {
            "event_type": "ci_failure",
            "source": "ci_retry",
            "payload": {
                "error_type": "timeout",
                "error_category": "network",
                "component": "api",
            },
        }

        signature = detector._extract_signature(event)

        assert signature["event_type"] == "ci_failure"
        assert signature["source"] == "ci_retry"
        assert signature["error_type"] == "timeout"
        assert signature["error_category"] == "network"
        assert signature["component"] == "api"

    def test_get_recent_patterns(self):
        """Test getting patterns by recency."""
        detector = PatternDetector()
        now = datetime.now()

        events = [{"event_type": "test", "source": "test", "payload": {}}]
        detector.register_pattern(events)

        # All patterns should be recent
        recent = detector.get_recent_patterns((now - timedelta(hours=1)).isoformat())
        assert len(recent) == 1

        # No patterns before registration
        old = detector.get_recent_patterns((now + timedelta(hours=1)).isoformat())
        assert len(old) == 0
