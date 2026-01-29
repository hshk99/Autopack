"""Tests for IMP-MEM-004: Circuit Breaker to Memory Integration.

Tests cover:
- record_circuit_breaker_event() method in FeedbackPipeline
- Circuit breaker event recording when circuit trips
- Insight persistence with proper metadata
- Error handling for memory service failures
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from autopack.feedback_pipeline import FeedbackPipeline


class TestRecordCircuitBreakerEvent:
    """Tests for FeedbackPipeline.record_circuit_breaker_event() method."""

    def test_record_event_disabled_pipeline(self):
        """record_circuit_breaker_event should return early when pipeline is disabled."""
        pipeline = FeedbackPipeline(enabled=False)

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test failure",
        )

        assert result["success"] is True
        assert result["insight_id"] is None

    def test_record_event_with_memory_service(self):
        """record_circuit_breaker_event should persist insight to memory service."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            project_id="test_project",
            run_id="run_001",
        )

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Phase build_001 failed with status: error",
        )

        assert result["success"] is True
        mock_memory.write_telemetry_insight.assert_called_once()

        # Verify the insight structure
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]

        assert insight["insight_type"] == "circuit_breaker_open"
        assert "5 consecutive failures" in insight["description"]
        assert insight["metadata"]["failure_count"] == 5
        assert "build_001" in insight["metadata"]["last_failure_reason"]
        assert insight["severity"] == "critical"
        assert insight["confidence"] == 1.0
        assert insight["run_id"] == "run_001"

    def test_record_event_with_custom_timestamp(self):
        """record_circuit_breaker_event should use provided timestamp."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        custom_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = pipeline.record_circuit_breaker_event(
            failure_count=3,
            last_failure_reason="Network timeout",
            timestamp=custom_time,
        )

        assert result["success"] is True

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]

        assert insight["metadata"]["timestamp"] == custom_time.isoformat()

    def test_record_event_without_memory_service(self):
        """record_circuit_breaker_event should queue insight when memory service unavailable."""
        pipeline = FeedbackPipeline(memory_service=None)

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="API error",
        )

        assert result["success"] is True
        # Should be queued in pending insights
        assert len(pipeline._pending_insights) == 1
        assert pipeline._pending_insights[0]["insight_type"] == "circuit_breaker_open"

    def test_record_event_with_disabled_memory_service(self):
        """record_circuit_breaker_event should queue when memory service is disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Build failure",
        )

        assert result["success"] is True
        assert len(pipeline._pending_insights) == 1

    def test_record_event_updates_stats(self):
        """record_circuit_breaker_event should update insights_persisted stat."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        initial_stats = pipeline.get_stats()
        initial_persisted = initial_stats["insights_persisted"]

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test failure",
        )

        final_stats = pipeline.get_stats()
        assert final_stats["insights_persisted"] == initial_persisted + 1

    def test_record_event_handles_memory_error(self):
        """record_circuit_breaker_event should handle memory service errors gracefully."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("Storage unavailable"))

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        result = pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test failure",
        )

        assert result["success"] is False
        assert "Storage unavailable" in result["error"]

    def test_record_event_insight_content(self):
        """record_circuit_breaker_event should create insight with proper content."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        pipeline.record_circuit_breaker_event(
            failure_count=7,
            last_failure_reason="Connection refused",
        )

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]

        # Verify content includes both failure count and reason
        assert "7 failures" in insight["content"]
        assert "Connection refused" in insight["content"]

        # Verify suggested action is present
        assert insight["suggested_action"] is not None
        assert "investigate" in insight["suggested_action"].lower()

    def test_record_event_project_id_passed(self):
        """record_circuit_breaker_event should pass project_id to memory service."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            project_id="my_custom_project",
        )

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test",
        )

        call_args = mock_memory.write_telemetry_insight.call_args
        assert call_args.kwargs["project_id"] == "my_custom_project"


class TestCircuitBreakerMemoryIntegration:
    """Integration tests for circuit breaker and memory service interaction."""

    def test_circuit_breaker_trip_records_event(self):
        """When circuit breaker trips, event should be recorded via feedback pipeline."""
        from autopack.executor.autonomous_loop import CircuitBreaker

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        # Create a feedback pipeline
        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            run_id="test_run",
        )

        # Create a circuit breaker
        cb = CircuitBreaker(failure_threshold=3)

        # Simulate failures until trip
        for i in range(3):
            cb.record_failure()

        assert cb.is_open is True

        # Simulate what autonomous_loop does on trip
        pipeline.record_circuit_breaker_event(
            failure_count=cb.consecutive_failures,
            last_failure_reason="Phase test_phase failed with status: error",
            timestamp=datetime.now(timezone.utc),
        )

        # Verify the event was recorded
        mock_memory.write_telemetry_insight.assert_called_once()

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]

        assert insight["insight_type"] == "circuit_breaker_open"
        assert insight["metadata"]["failure_count"] == 3

    def test_multiple_trips_record_separate_events(self):
        """Each circuit breaker trip should record a separate event."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        # Record multiple trip events
        for i in range(3):
            pipeline.record_circuit_breaker_event(
                failure_count=5 + i,
                last_failure_reason=f"Failure set {i}",
            )

        assert mock_memory.write_telemetry_insight.call_count == 3

    def test_insight_metadata_for_root_cause_analysis(self):
        """Insight should contain metadata useful for root cause analysis."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            run_id="analysis_run",
            project_id="analysis_project",
        )

        test_time = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Database connection pool exhausted",
            timestamp=test_time,
        )

        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]

        # Verify all required metadata for root cause analysis
        assert insight["metadata"]["failure_count"] == 5
        assert "Database connection pool" in insight["metadata"]["last_failure_reason"]
        assert insight["metadata"]["timestamp"] == test_time.isoformat()
        assert insight["metadata"]["event_type"] == "circuit_breaker_trip"
        assert insight["run_id"] == "analysis_run"

        # Verify it's marked as critical
        assert insight["severity"] == "critical"

        # Verify actionable guidance
        assert "root cause" in insight["suggested_action"].lower()


class TestCircuitBreakerEventPersistence:
    """Tests for circuit breaker event persistence behavior."""

    def test_event_persisted_with_validate_flag(self):
        """Circuit breaker events should be persisted with validate=True."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test",
        )

        call_args = mock_memory.write_telemetry_insight.call_args
        assert call_args.kwargs["validate"] is True

    def test_event_persisted_with_strict_false(self):
        """Circuit breaker events should be persisted with strict=False."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Test",
        )

        call_args = mock_memory.write_telemetry_insight.call_args
        assert call_args.kwargs["strict"] is False

    def test_queued_events_flushed_later(self):
        """Events queued when memory unavailable should be flushed later."""
        # Start with no memory service
        pipeline = FeedbackPipeline(memory_service=None)

        pipeline.record_circuit_breaker_event(
            failure_count=5,
            last_failure_reason="Initial failure",
        )

        assert len(pipeline._pending_insights) == 1

        # Now add memory service and flush
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline.memory_service = mock_memory

        flushed = pipeline.flush_pending_insights()

        assert flushed == 1
        assert len(pipeline._pending_insights) == 0
        mock_memory.write_telemetry_insight.assert_called_once()


class TestCircuitBreakerEventLogging:
    """Tests for circuit breaker event logging."""

    def test_successful_recording_logged(self):
        """Successful event recording should be logged."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock()

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        with patch("autopack.feedback_pipeline.logger") as mock_logger:
            pipeline.record_circuit_breaker_event(
                failure_count=5,
                last_failure_reason="Test failure",
            )

            # Verify info log was called
            mock_logger.info.assert_called()
            log_message = mock_logger.info.call_args[0][0]
            assert "[IMP-MEM-004]" in log_message
            assert "5 failures" in log_message

    def test_failed_recording_logged_as_warning(self):
        """Failed event recording should be logged as warning."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(side_effect=Exception("Test error"))

        pipeline = FeedbackPipeline(memory_service=mock_memory)

        with patch("autopack.feedback_pipeline.logger") as mock_logger:
            pipeline.record_circuit_breaker_event(
                failure_count=5,
                last_failure_reason="Test failure",
            )

            # Verify warning log was called
            mock_logger.warning.assert_called()
            log_message = mock_logger.warning.call_args[0][0]
            assert "[IMP-MEM-004]" in log_message
