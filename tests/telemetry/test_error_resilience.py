"""Tests for error resilience in telemetry analysis pipeline.

IMP-TEL-002: Verifies that malformed events or corrupted JSON don't crash
the entire analysis pipeline.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from telemetry.analysis_engine import AnalysisEngine
from telemetry.correlator import TelemetryCorrelator
from telemetry.event_schema import TelemetryEvent
from telemetry.metrics_aggregator import MetricsAggregator
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
def correlator(event_log):
    """Create a TelemetryCorrelator instance."""
    return TelemetryCorrelator(event_log)


class TestAnalysisEngineErrorResilience:
    """Tests for AnalysisEngine error handling."""

    def test_detect_error_patterns_with_query_failure(self, analysis_engine):
        """Test that detect_error_patterns handles query failures gracefully."""
        with patch.object(
            analysis_engine.event_log, "query", side_effect=Exception("Query failed")
        ):
            result = analysis_engine.detect_error_patterns()
            assert result == []

    def test_detect_error_patterns_with_malformed_events(self, analysis_engine, event_log):
        """Test that detect_error_patterns skips malformed events."""
        now = datetime.now()

        # Add valid events
        for i in range(3):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="ci_failure",
                payload={"status": "error"},
            )
            event_log.ingest(event)

        # Mock a malformed event in the query result
        original_query = event_log.query

        def mock_query_with_malformed(*args, **kwargs):
            events = original_query(*args, **kwargs)
            malformed = MagicMock()
            malformed.event_type = None  # Will cause AttributeError on .lower()
            events.append(malformed)
            return events

        with patch.object(event_log, "query", mock_query_with_malformed):
            # Should not raise, should return valid insights
            result = analysis_engine.detect_error_patterns(since_hours=1, min_occurrences=2)
            # Verify some results are returned (malformed event was skipped)
            assert isinstance(result, list)

    def test_compute_success_rates_with_query_failure(self, analysis_engine):
        """Test that compute_success_rates handles query failures gracefully."""
        with patch.object(
            analysis_engine.event_log, "query", side_effect=Exception("Query failed")
        ):
            result = analysis_engine.compute_success_rates()
            assert result == {}

    def test_compute_success_rates_with_malformed_events(self, analysis_engine, event_log):
        """Test that compute_success_rates skips malformed events."""
        now = datetime.now()

        # Add valid events
        for i in range(3):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="pr_merged",
                payload={},
            )
            event_log.ingest(event)

        # Mock malformed event
        original_query = event_log.query

        def mock_query_with_malformed(*args, **kwargs):
            events = original_query(*args, **kwargs)
            malformed = MagicMock()
            malformed.source = None  # Will cause issues
            malformed.event_type = MagicMock()
            malformed.event_type.lower = MagicMock(side_effect=AttributeError())
            events.append(malformed)
            return events

        with patch.object(event_log, "query", mock_query_with_malformed):
            result = analysis_engine.compute_success_rates(since_hours=1)
            # Should return valid rates, malformed events skipped
            assert isinstance(result, dict)

    def test_identify_recurring_issues_with_query_failure(self, analysis_engine):
        """Test that identify_recurring_issues handles query failures gracefully."""
        with patch.object(
            analysis_engine.event_log, "query", side_effect=Exception("Query failed")
        ):
            result = analysis_engine.identify_recurring_issues()
            assert result == []

    def test_detect_bottlenecks_with_query_failure(self, analysis_engine):
        """Test that detect_bottlenecks handles query failures gracefully."""
        with patch.object(
            analysis_engine.event_log, "query", side_effect=Exception("Query failed")
        ):
            result = analysis_engine.detect_bottlenecks()
            assert result == []

    def test_detect_bottlenecks_with_invalid_duration(self, analysis_engine, event_log):
        """Test that detect_bottlenecks handles invalid duration values."""
        now = datetime.now()

        # Add event with valid duration
        event = TelemetryEvent(
            timestamp=now,
            source="ci_retry",
            event_type="build_process",
            payload={"duration_seconds": 120.0},
        )
        event_log.ingest(event)

        # Mock malformed event with invalid duration
        original_query = event_log.query

        def mock_query_with_invalid_duration(*args, **kwargs):
            events = original_query(*args, **kwargs)
            malformed = MagicMock()
            malformed.payload = {"duration_seconds": "not_a_number"}
            malformed.source = "test"
            malformed.event_type = "test"
            events.append(malformed)
            return events

        with patch.object(event_log, "query", mock_query_with_invalid_duration):
            result = analysis_engine.detect_bottlenecks(since_hours=1)
            # Should not crash, should return valid insights
            assert isinstance(result, list)

    def test_get_comprehensive_analysis_isolates_failures(self, analysis_engine):
        """Test that get_comprehensive_analysis continues despite individual failures."""
        # Make one analysis method fail
        with patch.object(
            analysis_engine,
            "detect_error_patterns",
            side_effect=Exception("Pattern detection failed"),
        ):
            result = analysis_engine.get_comprehensive_analysis()

            # Should still have other results
            assert "success_rates" in result
            assert "recurring_issues" in result
            assert "bottlenecks" in result
            # Should have error recorded
            assert "errors" in result
            assert len(result["errors"]) == 1
            assert result["errors"][0]["analysis"] == "error_patterns"


class TestCorrelatorErrorResilience:
    """Tests for TelemetryCorrelator error handling."""

    def test_correlate_slot_with_pr_query_failure(self, correlator):
        """Test that correlate_slot_with_pr handles query failures gracefully."""
        with patch.object(correlator.event_log, "query", side_effect=Exception("Query failed")):
            result = correlator.correlate_slot_with_pr(1, 123)
            assert result.primary_event is None
            assert result.related_events == []
            assert result.correlation_confidence == 0.0

    def test_correlate_slot_with_pr_malformed_events(self, correlator, event_log):
        """Test that correlate_slot_with_pr handles malformed events."""
        now = datetime.now()

        # Add valid event
        event = TelemetryEvent(
            timestamp=now,
            source="ci_retry",
            event_type="pr_opened",
            slot_id=1,
            payload={"pr_number": 123},
        )
        event_log.ingest(event)

        # Mock malformed event
        original_query = event_log.query

        def mock_query_with_malformed(*args, **kwargs):
            events = original_query(*args, **kwargs)
            malformed = MagicMock()
            malformed.timestamp = None  # Will cause issues in tuple creation
            events.append(malformed)
            return events

        with patch.object(event_log, "query", mock_query_with_malformed):
            result = correlator.correlate_slot_with_pr(1, 123)
            # Should not crash
            assert isinstance(result.correlation_confidence, float)

    def test_find_causation_chain_with_prefetch_failure(self, correlator, event_log):
        """Test that find_causation_chain handles prefetch failures."""
        now = datetime.now()
        event = TelemetryEvent(
            timestamp=now,
            source="ci_retry",
            event_type="test_event",
            slot_id=1,
            payload={},
        )
        event_log.ingest(event)

        with patch.object(correlator, "_prefetch_events", side_effect=Exception("Prefetch failed")):
            result = correlator.find_causation_chain(event)
            # Should return single-event chain
            assert len(result.events) == 1
            assert result.confidence == 0.0

    def test_correlate_by_timewindow_query_failure(self, correlator, event_log):
        """Test that correlate_by_timewindow handles query failures."""
        now = datetime.now()
        event = TelemetryEvent(
            timestamp=now,
            source="ci_retry",
            event_type="test_event",
            payload={},
        )

        with patch.object(correlator.event_log, "query", side_effect=Exception("Query failed")):
            result = correlator.correlate_by_timewindow(event)
            assert result == []


class TestMetricsAggregatorErrorResilience:
    """Tests for MetricsAggregator error handling."""

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
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = Path(log_dir) / f"events_{date_str}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _write_malformed_event(self, log_dir: str, malformed_line: str) -> None:
        """Helper to write malformed data to a log file."""
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = Path(log_dir) / f"events_{date_str}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(malformed_line + "\n")

    def test_stream_events_skips_malformed_json(self, aggregator, temp_dirs):
        """Test that _stream_events skips malformed JSON lines."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Write valid event
        valid_event = {
            "timestamp": now.isoformat(),
            "type": "test_event",
            "slot": 1,
        }
        self._write_event(log_dir, valid_event)

        # Write malformed JSON
        self._write_malformed_event(log_dir, "this is not valid json {{{")

        # Write another valid event
        valid_event2 = {
            "timestamp": now.isoformat(),
            "type": "test_event_2",
            "slot": 2,
        }
        self._write_event(log_dir, valid_event2)

        # Stream events - should get 2 valid events, skip malformed
        cutoff = now - timedelta(hours=1)
        events = list(aggregator._stream_events(cutoff))
        assert len(events) == 2

    def test_stream_events_skips_missing_timestamp(self, aggregator, temp_dirs):
        """Test that _stream_events skips events without timestamp."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Write valid event
        valid_event = {
            "timestamp": now.isoformat(),
            "type": "test_event",
        }
        self._write_event(log_dir, valid_event)

        # Write event without timestamp
        invalid_event = {"type": "missing_timestamp", "data": {}}
        self._write_event(log_dir, invalid_event)

        cutoff = now - timedelta(hours=1)
        events = list(aggregator._stream_events(cutoff))
        assert len(events) == 1

    def test_aggregate_by_period_with_read_failure(self, aggregator):
        """Test that aggregate_by_period handles read failures."""
        with patch.object(aggregator, "_read_events", side_effect=Exception("Read failed")):
            result = aggregator.aggregate_by_period("test", timedelta(hours=1))
            assert result == []

    def test_aggregate_by_period_with_malformed_events(self, aggregator, temp_dirs):
        """Test that aggregate_by_period skips events with invalid timestamps."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Write valid events
        for i in range(3):
            event = {
                "timestamp": (now - timedelta(minutes=i)).isoformat(),
                "type": "test_event",
            }
            self._write_event(log_dir, event)

        # Write event with invalid timestamp format
        invalid_event = {"timestamp": "not-a-valid-timestamp", "type": "invalid"}
        self._write_event(log_dir, invalid_event)

        result = aggregator.aggregate_by_period("test", timedelta(hours=1), since_hours=2)
        # Should process valid events only
        total_count = sum(m.count for m in result)
        assert total_count == 3

    def test_aggregate_by_component_with_read_failure(self, aggregator):
        """Test that aggregate_by_component handles read failures."""
        with patch.object(aggregator, "_read_events", side_effect=Exception("Read failed")):
            result = aggregator.aggregate_by_component("test")
            assert result == {}

    def test_aggregate_by_component_handles_malformed(self, aggregator, temp_dirs):
        """Test that aggregate_by_component handles various event formats."""
        log_dir, _ = temp_dirs
        now = datetime.now()

        # Write events with different structures
        events = [
            {"timestamp": now.isoformat(), "type": "valid_type", "slot": 1},
            {"timestamp": now.isoformat()},  # Missing type - should use "unknown"
            {"timestamp": now.isoformat(), "type": "another_type"},
        ]
        for event in events:
            self._write_event(log_dir, event)

        result = aggregator.aggregate_by_component("test", since_hours=1)
        # Should have results for valid types and "unknown"
        assert isinstance(result, dict)
        total_count = sum(m.count for m in result.values())
        assert total_count == 3


class TestCombinedPipelineResilience:
    """Integration tests for error resilience across the pipeline."""

    def test_analysis_continues_after_partial_failure(self, analysis_engine, event_log):
        """Test that analysis pipeline produces results despite some failures."""
        now = datetime.now()

        # Add some valid events
        for i in range(5):
            event = TelemetryEvent(
                timestamp=now - timedelta(minutes=i),
                source="ci_retry",
                event_type="pr_merged",
                payload={"duration_seconds": 30.0},
            )
            event_log.ingest(event)

        # Get comprehensive analysis - should succeed even if individual parts fail
        result = analysis_engine.get_comprehensive_analysis(since_hours=1)

        assert "analysis_timestamp" in result
        assert "success_rates" in result
        assert isinstance(result["success_rates"], dict)
