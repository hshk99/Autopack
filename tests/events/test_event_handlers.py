"""Comprehensive tests for Event Handlers covering all event types.

This module provides extensive test coverage for all event handler implementations,
including tests for all event types (phase, research, build, artifact, model,
session, approval, system, etc.) and edge cases.

Tests cover:
- LoggingHandler with all event types and log level overrides
- MetricsHandler metrics collection and accuracy
- PersistenceHandler buffering and file I/O
- AuditHandler audit trail recording
- ChainHandler error handling and execution order
- ConditionalHandler conditional execution
- BaseEventHandler stats tracking and lifecycle
"""

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from autopack.events import Event, EventPriority, EventType
from autopack.events.handlers import (
    AuditHandler,
    BaseEventHandler,
    ChainHandler,
    ConditionalHandler,
    LoggingHandler,
    MetricsHandler,
    PersistenceHandler,
)


# Test utilities
class MockHandler(BaseEventHandler):
    """Mock handler for testing."""

    def __init__(self, name: str = "MockHandler", should_fail: bool = False):
        super().__init__(name=name)
        self.handled_events: List[Event] = []
        self.should_fail = should_fail

    async def handle(self, event: Event) -> None:
        """Handle event and optionally raise."""
        self.handled_events.append(event)
        if self.should_fail:
            raise ValueError(f"Mock handler failure for {event.type.value}")


# Test fixtures
@pytest.fixture
def phase_event():
    """Create a PHASE_STARTED event."""
    return Event.create(
        event_type=EventType.PHASE_STARTED,
        source="orchestrator",
        payload={"phase": "research", "step": 1},
    )


@pytest.fixture
def research_event():
    """Create a RESEARCH_GAP_DETECTED event."""
    return Event.create(
        event_type=EventType.RESEARCH_GAP_DETECTED,
        source="research-agent",
        payload={"gap": "market_analysis", "severity": "high"},
    )


@pytest.fixture
def build_event():
    """Create a BUILD_DECISION_MADE event."""
    return Event.create(
        event_type=EventType.BUILD_DECISION_MADE,
        source="build-engine",
        payload={"decision": "build", "tech_stack": "python"},
    )


@pytest.fixture
def model_event():
    """Create a MODEL_SELECTED event."""
    return Event.create(
        event_type=EventType.MODEL_SELECTED,
        source="model-router",
        payload={"model": "claude-opus-4.5", "temperature": 0.7},
    )


@pytest.fixture
def session_event():
    """Create a SESSION_STARTED event."""
    return Event.create(
        event_type=EventType.SESSION_STARTED,
        source="session-manager",
        payload={"session_id": "sess-123", "user": "test-user"},
    )


@pytest.fixture
def approval_event():
    """Create an APPROVAL_GRANTED event."""
    return Event.create(
        event_type=EventType.APPROVAL_GRANTED,
        source="approval-manager",
        payload={"approval_id": "apr-456", "reviewer": "admin"},
        priority=EventPriority.HIGH,
    )


@pytest.fixture
def error_event():
    """Create an ERROR_OCCURRED event."""
    return Event.create(
        event_type=EventType.ERROR_OCCURRED,
        source="executor",
        payload={"error": "Phase execution failed", "traceback": "..."},
        priority=EventPriority.CRITICAL,
    )


@pytest.fixture
def artifact_event():
    """Create an ARTIFACT_GENERATED event."""
    return Event.create(
        event_type=EventType.ARTIFACT_GENERATED,
        source="artifact-generator",
        payload={"artifact": "deployment-guide.md", "type": "document"},
    )


@pytest.fixture
def health_event():
    """Create a HEALTH_CHECK_FAILED event."""
    return Event.create(
        event_type=EventType.HEALTH_CHECK_FAILED,
        source="health-monitor",
        payload={"component": "database", "status": "unreachable"},
        priority=EventPriority.HIGH,
    )


@pytest.fixture
def circuit_breaker_event():
    """Create a CIRCUIT_BREAKER_OPENED event."""
    return Event.create(
        event_type=EventType.CIRCUIT_BREAKER_OPENED,
        source="circuit-breaker",
        payload={"service": "llm-api", "threshold": 5},
        priority=EventPriority.HIGH,
    )


@pytest.fixture
def warning_event():
    """Create a WARNING_RAISED event."""
    return Event.create(
        event_type=EventType.WARNING_RAISED,
        source="system",
        payload={"warning": "High memory usage", "value": 85},
    )


@pytest.fixture
def all_event_types():
    """Fixture providing events for all major event types."""
    return [
        Event.create(EventType.PHASE_STARTED, "orchestrator"),
        Event.create(EventType.PHASE_COMPLETED, "orchestrator"),
        Event.create(EventType.PHASE_FAILED, "orchestrator"),
        Event.create(EventType.RESEARCH_STARTED, "research-agent"),
        Event.create(EventType.RESEARCH_GAP_DETECTED, "research-agent"),
        Event.create(EventType.RESEARCH_COMPLETED, "research-agent"),
        Event.create(EventType.BUILD_STARTED, "build-engine"),
        Event.create(EventType.BUILD_DECISION_MADE, "build-engine"),
        Event.create(EventType.BUILD_COMPLETED, "build-engine"),
        Event.create(EventType.ARTIFACT_GENERATED, "artifact-generator"),
        Event.create(EventType.ARTIFACT_VALIDATED, "artifact-generator"),
        Event.create(EventType.MODEL_SELECTED, "model-router"),
        Event.create(EventType.MODEL_FALLBACK_TRIGGERED, "model-router"),
        Event.create(EventType.SESSION_STARTED, "session-manager"),
        Event.create(EventType.SESSION_ENDED, "session-manager"),
        Event.create(EventType.APPROVAL_REQUESTED, "approval-manager"),
        Event.create(EventType.APPROVAL_GRANTED, "approval-manager"),
        Event.create(EventType.ERROR_OCCURRED, "executor"),
        Event.create(EventType.WARNING_RAISED, "system"),
        Event.create(EventType.HEALTH_CHECK_FAILED, "health-monitor"),
        Event.create(EventType.CIRCUIT_BREAKER_OPENED, "circuit-breaker"),
    ]


# ============================================================================
# Tests for LoggingHandler
# ============================================================================


class TestLoggingHandler:
    """Comprehensive tests for LoggingHandler."""

    def test_logging_handler_logs_phase_event(self, phase_event, caplog):
        """Test LoggingHandler logs PHASE_STARTED event."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(phase_event))

        assert "[EVENT]" in caplog.text
        assert "phase.started" in caplog.text
        assert "orchestrator" in caplog.text

    def test_logging_handler_logs_research_event(self, research_event, caplog):
        """Test LoggingHandler logs RESEARCH_GAP_DETECTED event."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(research_event))

        assert "research.gap_detected" in caplog.text

    def test_logging_handler_logs_build_event(self, build_event, caplog):
        """Test LoggingHandler logs BUILD_DECISION_MADE event."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(build_event))

        assert "build.decision_made" in caplog.text

    def test_logging_handler_logs_error_event_at_error_level(self, error_event, caplog):
        """Test LoggingHandler logs ERROR_OCCURRED at ERROR level."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.ERROR):
            import asyncio

            asyncio.run(handler(error_event))

        assert "error.occurred" in caplog.text

    def test_logging_handler_logs_warning_event_at_warning_level(self, warning_event, caplog):
        """Test LoggingHandler logs WARNING_RAISED at WARNING level."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.WARNING):
            import asyncio

            asyncio.run(handler(warning_event))

        assert "warning.raised" in caplog.text

    def test_logging_handler_logs_health_check_at_error_level(self, health_event, caplog):
        """Test LoggingHandler logs HEALTH_CHECK_FAILED at ERROR level."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.ERROR):
            import asyncio

            asyncio.run(handler(health_event))

        assert "health.check_failed" in caplog.text

    def test_logging_handler_logs_circuit_breaker_at_warning_level(
        self, circuit_breaker_event, caplog
    ):
        """Test LoggingHandler logs CIRCUIT_BREAKER_OPENED at WARNING level."""
        handler = LoggingHandler(log_level=logging.INFO)

        with caplog.at_level(logging.WARNING):
            import asyncio

            asyncio.run(handler(circuit_breaker_event))

        assert "circuit_breaker.opened" in caplog.text

    def test_logging_handler_includes_payload(self, phase_event, caplog):
        """Test LoggingHandler includes event payload."""
        handler = LoggingHandler(include_payload=True)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(phase_event))

        assert "payload=" in caplog.text

    def test_logging_handler_excludes_payload_when_disabled(self, phase_event, caplog):
        """Test LoggingHandler excludes payload when disabled."""
        handler = LoggingHandler(include_payload=False)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(phase_event))

        assert "payload=" not in caplog.text

    def test_logging_handler_truncates_large_payload(self, caplog):
        """Test LoggingHandler truncates large payloads."""
        large_payload = {"data": "x" * 500}
        event = Event.create(
            event_type=EventType.PHASE_STARTED, source="test", payload=large_payload
        )
        handler = LoggingHandler(include_payload=True)

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(event))

        assert "..." in caplog.text

    def test_logging_handler_set_level_override(self, research_event, caplog):
        """Test LoggingHandler can override log level per event type."""
        handler = LoggingHandler(log_level=logging.INFO)
        handler.set_level_override(EventType.RESEARCH_GAP_DETECTED, logging.DEBUG)

        with caplog.at_level(logging.DEBUG):
            import asyncio

            asyncio.run(handler(research_event))

        assert "research.gap_detected" in caplog.text

    def test_logging_handler_tracks_stats(self, all_event_types):
        """Test LoggingHandler tracks event and error statistics."""
        handler = LoggingHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        stats = handler.get_stats()
        assert stats["event_count"] == len(all_event_types)
        assert stats["error_count"] == 0
        assert stats["enabled"] is True

    def test_logging_handler_disabled(self, phase_event, caplog):
        """Test disabled LoggingHandler doesn't log."""
        handler = LoggingHandler()
        handler.enabled = False

        with caplog.at_level(logging.INFO):
            import asyncio

            asyncio.run(handler(phase_event))

        assert "[EVENT]" not in caplog.text

    def test_logging_handler_custom_logger(self):
        """Test LoggingHandler uses custom logger."""
        handler = LoggingHandler(logger_name="custom.logger")
        assert handler._logger.name == "custom.logger"


# ============================================================================
# Tests for MetricsHandler
# ============================================================================


class TestMetricsHandler:
    """Comprehensive tests for MetricsHandler."""

    def test_metrics_handler_collects_phase_events(self, phase_event):
        """Test MetricsHandler collects PHASE_STARTED metrics."""
        handler = MetricsHandler()
        import asyncio

        asyncio.run(handler(phase_event))

        metrics = handler.get_metrics()
        assert metrics["counts_by_type"]["phase.started"] == 1
        assert metrics["counts_by_source"]["orchestrator"] == 1
        assert metrics["counts_by_category"]["phase"] == 1

    def test_metrics_handler_collects_multiple_event_types(self, all_event_types):
        """Test MetricsHandler aggregates metrics for multiple event types."""
        handler = MetricsHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        metrics = handler.get_metrics()
        assert metrics["total_events"] == len(all_event_types)
        assert len(metrics["counts_by_type"]) > 0
        assert len(metrics["counts_by_source"]) > 0
        assert len(metrics["counts_by_category"]) > 0

    def test_metrics_handler_tracks_events_per_second(self, all_event_types):
        """Test MetricsHandler calculates events per second."""
        handler = MetricsHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        metrics = handler.get_metrics()
        assert metrics["events_per_second"] >= 0
        assert metrics["collection_duration_seconds"] >= 0

    def test_metrics_handler_category_counting(self):
        """Test MetricsHandler correctly counts events by category."""
        handler = MetricsHandler()
        import asyncio

        # Create events from different categories
        phase_event = Event.create(EventType.PHASE_STARTED, "orchestrator")
        research_event = Event.create(EventType.RESEARCH_STARTED, "research-agent")
        build_event = Event.create(EventType.BUILD_STARTED, "build-engine")

        asyncio.run(handler(phase_event))
        asyncio.run(handler(research_event))
        asyncio.run(handler(build_event))

        metrics = handler.get_metrics()
        assert metrics["counts_by_category"]["phase"] == 1
        assert metrics["counts_by_category"]["research"] == 1
        assert metrics["counts_by_category"]["build"] == 1

    def test_metrics_handler_source_counting(self):
        """Test MetricsHandler correctly counts events by source."""
        handler = MetricsHandler()
        import asyncio

        event1 = Event.create(EventType.PHASE_STARTED, "source-a")
        event2 = Event.create(EventType.PHASE_STARTED, "source-a")
        event3 = Event.create(EventType.PHASE_STARTED, "source-b")

        asyncio.run(handler(event1))
        asyncio.run(handler(event2))
        asyncio.run(handler(event3))

        metrics = handler.get_metrics()
        assert metrics["counts_by_source"]["source-a"] == 2
        assert metrics["counts_by_source"]["source-b"] == 1

    def test_metrics_handler_reset_metrics(self, all_event_types):
        """Test MetricsHandler can reset metrics."""
        handler = MetricsHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        metrics_before = handler.get_metrics()
        assert metrics_before["total_events"] > 0

        handler.reset_metrics()
        metrics_after = handler.get_metrics()
        assert metrics_after["total_events"] == 0
        assert len(metrics_after["counts_by_type"]) == 0

    def test_metrics_handler_tracks_handler_stats(self, all_event_types):
        """Test MetricsHandler tracks its own statistics."""
        handler = MetricsHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        stats = handler.get_stats()
        assert stats["event_count"] == len(all_event_types)
        assert stats["error_count"] == 0

    def test_metrics_handler_tracks_error_events(self):
        """Test MetricsHandler tracks ERROR_OCCURRED events."""
        handler = MetricsHandler()
        import asyncio

        error_event = Event.create(EventType.ERROR_OCCURRED, "system")
        asyncio.run(handler(error_event))

        metrics = handler.get_metrics()
        assert metrics["counts_by_type"]["error.occurred"] == 1


# ============================================================================
# Tests for AuditHandler
# ============================================================================


class TestAuditHandler:
    """Comprehensive tests for AuditHandler."""

    def test_audit_handler_records_approval_event(self, approval_event):
        """Test AuditHandler records APPROVAL_GRANTED event."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))

        audit_log = handler.get_audit_log()
        assert len(audit_log) == 1
        assert audit_log[0]["event_type"] == "approval.granted"

    def test_audit_handler_filters_by_event_type(self, all_event_types):
        """Test AuditHandler filters audit log by event type."""
        handler = AuditHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        # Query for specific event type
        audit_log = handler.get_audit_log(event_type=EventType.PHASE_STARTED)
        assert all(e["event_type"] == "phase.started" for e in audit_log)

    def test_audit_handler_audit_specific_types(self, all_event_types):
        """Test AuditHandler filters to specific event types."""
        audit_types = {EventType.APPROVAL_GRANTED, EventType.APPROVAL_DENIED}
        handler = AuditHandler(audit_types=audit_types)
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        audit_log = handler.get_audit_log()
        # Should only have approval events
        assert all(e["event_type"].startswith("approval.") for e in audit_log)

    def test_audit_handler_timestamps_entries(self, approval_event):
        """Test AuditHandler timestamps audit entries."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))

        audit_log = handler.get_audit_log()
        assert "timestamp" in audit_log[0]

    def test_audit_handler_includes_event_id(self, approval_event):
        """Test AuditHandler includes event ID."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))

        audit_log = handler.get_audit_log()
        assert audit_log[0]["event_id"] == approval_event.event_id

    def test_audit_handler_includes_correlation_id(self, approval_event):
        """Test AuditHandler includes correlation ID."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))

        audit_log = handler.get_audit_log()
        assert audit_log[0]["correlation_id"] == approval_event.correlation_id

    def test_audit_handler_respects_limit(self):
        """Test AuditHandler respects audit log limit."""
        handler = AuditHandler(max_entries=5)
        import asyncio

        for i in range(10):
            event = Event.create(EventType.APPROVAL_GRANTED, f"source-{i}")
            asyncio.run(handler(event))

        audit_log = handler.get_audit_log()
        assert len(audit_log) == 5

    def test_audit_handler_clear_audit_log(self, approval_event):
        """Test AuditHandler can clear audit log."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))
        assert len(handler.get_audit_log()) > 0

        handler.clear_audit_log()
        assert len(handler.get_audit_log()) == 0

    def test_audit_handler_filter_by_timestamp(self, approval_event):
        """Test AuditHandler filters by timestamp."""
        handler = AuditHandler()
        import asyncio

        asyncio.run(handler(approval_event))

        # Query with a future timestamp
        future_time = datetime.utcnow()
        audit_log = handler.get_audit_log(since=future_time)
        assert len(audit_log) == 0


# ============================================================================
# Tests for PersistenceHandler
# ============================================================================


class TestPersistenceHandler:
    """Comprehensive tests for PersistenceHandler."""

    def test_persistence_handler_writes_event_to_file(self, phase_event):
        """Test PersistenceHandler writes events to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "events.jsonl"
            handler = PersistenceHandler(output_path, flush_interval=1)
            import asyncio

            asyncio.run(handler(phase_event))
            asyncio.run(handler.flush())

            assert output_path.exists()
            with open(output_path) as f:
                lines = f.readlines()
                assert len(lines) == 1
                data = json.loads(lines[0])
                assert data["type"] == "phase.started"

    def test_persistence_handler_buffers_events(self, phase_event, research_event):
        """Test PersistenceHandler buffers events before flush."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "events.jsonl"
            handler = PersistenceHandler(output_path, flush_interval=10)
            import asyncio

            asyncio.run(handler(phase_event))
            asyncio.run(handler(research_event))

            # File should not exist yet (buffer not flushed)
            assert not output_path.exists()

            # Flush manually
            asyncio.run(handler.flush())
            assert output_path.exists()

    def test_persistence_handler_auto_flushes_on_interval(self):
        """Test PersistenceHandler auto-flushes after event count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "events.jsonl"
            handler = PersistenceHandler(output_path, flush_interval=2)
            import asyncio

            # Add events up to flush interval
            for i in range(3):
                event = Event.create(EventType.PHASE_STARTED, f"source-{i}")
                asyncio.run(handler(event))

            # File should exist after exceeding flush_interval
            assert output_path.exists()

    def test_persistence_handler_creates_parent_directories(self):
        """Test PersistenceHandler creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "deep" / "events.jsonl"
            PersistenceHandler(output_path)
            assert output_path.parent.exists()

    def test_persistence_handler_preserves_event_data(self, approval_event):
        """Test PersistenceHandler preserves all event data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "events.jsonl"
            handler = PersistenceHandler(output_path, flush_interval=1)
            import asyncio

            asyncio.run(handler(approval_event))
            asyncio.run(handler.flush())

            with open(output_path) as f:
                data = json.loads(f.readline())
                assert data["type"] == "approval.granted"
                assert data["source"] == "approval-manager"
                # Priority is stored as numeric value in JSON
                assert data["priority"] == 3

    def test_persistence_handler_handles_multiple_events(self, all_event_types):
        """Test PersistenceHandler handles multiple event types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "events.jsonl"
            handler = PersistenceHandler(output_path, flush_interval=100)
            import asyncio

            for event in all_event_types:
                asyncio.run(handler(event))

            asyncio.run(handler.flush())

            with open(output_path) as f:
                lines = f.readlines()
                assert len(lines) == len(all_event_types)


# ============================================================================
# Tests for ChainHandler
# ============================================================================


class TestChainHandler:
    """Comprehensive tests for ChainHandler."""

    def test_chain_handler_invokes_all_handlers(self, phase_event):
        """Test ChainHandler invokes all handlers in sequence."""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2")
        handler3 = MockHandler("handler3")
        chain = ChainHandler([handler1, handler2, handler3])
        import asyncio

        asyncio.run(chain(phase_event))

        assert len(handler1.handled_events) == 1
        assert len(handler2.handled_events) == 1
        assert len(handler3.handled_events) == 1

    def test_chain_handler_stops_on_error(self, phase_event):
        """Test ChainHandler stops on error by default."""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2", should_fail=True)
        handler3 = MockHandler("handler3")
        chain = ChainHandler([handler1, handler2, handler3], continue_on_error=False)
        import asyncio

        with pytest.raises(ValueError):
            asyncio.run(chain(phase_event))

        assert len(handler1.handled_events) == 1
        assert len(handler2.handled_events) == 1
        assert len(handler3.handled_events) == 0

    def test_chain_handler_continues_on_error(self, phase_event):
        """Test ChainHandler continues on error when configured."""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2", should_fail=True)
        handler3 = MockHandler("handler3")
        chain = ChainHandler([handler1, handler2, handler3], continue_on_error=True)
        import asyncio

        asyncio.run(chain(phase_event))

        assert len(handler1.handled_events) == 1
        assert len(handler2.handled_events) == 1
        assert len(handler3.handled_events) == 1

    def test_chain_handler_with_multiple_event_types(self, all_event_types):
        """Test ChainHandler processes multiple event types."""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2")
        chain = ChainHandler([handler1, handler2])
        import asyncio

        for event in all_event_types:
            asyncio.run(chain(event))

        assert len(handler1.handled_events) == len(all_event_types)
        assert len(handler2.handled_events) == len(all_event_types)

    def test_chain_handler_tracks_stats(self, phase_event):
        """Test ChainHandler tracks statistics."""
        handler1 = MockHandler("handler1")
        handler2 = MockHandler("handler2")
        chain = ChainHandler([handler1, handler2])
        import asyncio

        asyncio.run(chain(phase_event))

        stats = chain.get_stats()
        assert stats["event_count"] == 1
        assert stats["error_count"] == 0


# ============================================================================
# Tests for ConditionalHandler
# ============================================================================


class TestConditionalHandler:
    """Comprehensive tests for ConditionalHandler."""

    def test_conditional_handler_invokes_when_true(self, approval_event):
        """Test ConditionalHandler invokes when condition is true."""
        inner = MockHandler("inner")

        def is_approval(event: Event) -> bool:
            return "approval" in event.type.value

        handler = ConditionalHandler(inner, condition=is_approval)
        import asyncio

        asyncio.run(handler(approval_event))

        assert len(inner.handled_events) == 1

    def test_conditional_handler_skips_when_false(self, phase_event):
        """Test ConditionalHandler skips when condition is false."""
        inner = MockHandler("inner")

        def is_approval(event: Event) -> bool:
            return "approval" in event.type.value

        handler = ConditionalHandler(inner, condition=is_approval)
        import asyncio

        asyncio.run(handler(phase_event))

        assert len(inner.handled_events) == 0

    def test_conditional_handler_filters_by_priority(self):
        """Test ConditionalHandler filters by event priority."""
        inner = MockHandler("inner")

        def is_high_priority(event: Event) -> bool:
            return event.priority == EventPriority.HIGH

        handler = ConditionalHandler(inner, condition=is_high_priority)
        import asyncio

        # High priority event
        high_event = Event.create(EventType.APPROVAL_GRANTED, "source", priority=EventPriority.HIGH)
        asyncio.run(handler(high_event))
        assert len(inner.handled_events) == 1

        # Normal priority event
        normal_event = Event.create(
            EventType.PHASE_STARTED, "source", priority=EventPriority.NORMAL
        )
        asyncio.run(handler(normal_event))
        assert len(inner.handled_events) == 1  # Still 1, not incremented

    def test_conditional_handler_tracks_skipped_count(self):
        """Test ConditionalHandler tracks skipped event count."""
        inner = MockHandler("inner")

        def is_approval(event: Event) -> bool:
            return "approval" in event.type.value

        handler = ConditionalHandler(inner, condition=is_approval)
        import asyncio

        # Invoke with approval event (will be handled)
        approval_event = Event.create(EventType.APPROVAL_GRANTED, "source")
        asyncio.run(handler(approval_event))

        # Invoke with non-approval event (will be skipped)
        phase_event = Event.create(EventType.PHASE_STARTED, "source")
        asyncio.run(handler(phase_event))

        stats = handler.get_stats()
        assert stats["skipped_count"] == 1
        assert stats["event_count"] == 2  # Both calls counted

    def test_conditional_handler_filters_multiple_event_types(self, all_event_types):
        """Test ConditionalHandler filters multiple event types."""
        inner = MockHandler("inner")

        def is_error_or_warning(event: Event) -> bool:
            return event.category in ["error", "warning"]

        handler = ConditionalHandler(inner, condition=is_error_or_warning)
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        # Count how many were actually errors/warnings
        error_warning_count = sum(1 for e in all_event_types if e.category in ["error", "warning"])
        assert len(inner.handled_events) == error_warning_count

    def test_conditional_handler_inner_stats(self):
        """Test ConditionalHandler includes inner handler stats."""
        inner = MockHandler("inner")

        def always_true(event: Event) -> bool:
            return True

        handler = ConditionalHandler(inner, condition=always_true)
        import asyncio

        event = Event.create(EventType.PHASE_STARTED, "source")
        asyncio.run(handler(event))

        stats = handler.get_stats()
        assert "inner_stats" in stats
        assert stats["inner_stats"]["event_count"] == 1


# ============================================================================
# Tests for BaseEventHandler
# ============================================================================


class TestBaseEventHandler:
    """Comprehensive tests for BaseEventHandler."""

    def test_handler_tracks_event_count(self, all_event_types):
        """Test handler tracks event count."""
        handler = MockHandler()
        import asyncio

        for event in all_event_types:
            asyncio.run(handler(event))

        stats = handler.get_stats()
        assert stats["event_count"] == len(all_event_types)

    def test_handler_tracks_error_count(self):
        """Test handler tracks error count."""
        handler = MockHandler(should_fail=True)
        import asyncio

        event = Event.create(EventType.PHASE_STARTED, "source")

        with pytest.raises(ValueError):
            asyncio.run(handler(event))

        stats = handler.get_stats()
        assert stats["error_count"] == 1

    def test_handler_tracks_last_event_time(self, phase_event):
        """Test handler tracks last event time."""
        handler = MockHandler()
        import asyncio

        asyncio.run(handler(phase_event))

        stats = handler.get_stats()
        assert stats["last_event_time"] is not None

    def test_handler_disabled_flag(self, phase_event):
        """Test handler disabled flag prevents processing."""
        handler = MockHandler(name="disabled-handler")
        handler.enabled = False
        import asyncio

        asyncio.run(handler(phase_event))

        # Handler should not have processed the event
        assert len(handler.handled_events) == 0

    def test_handler_on_error_callback(self):
        """Test handler on_error callback is called."""
        handler = MockHandler(should_fail=True)
        import asyncio

        # Mock the on_error method
        handler.on_error = MagicMock()

        event = Event.create(EventType.PHASE_STARTED, "source")

        with pytest.raises(ValueError):
            asyncio.run(handler(event))

        handler.on_error.assert_called_once()

    def test_handler_get_stats_complete(self):
        """Test handler get_stats returns all expected fields."""
        handler = MockHandler(name="test-handler")
        import asyncio

        event = Event.create(EventType.PHASE_STARTED, "source")
        asyncio.run(handler(event))

        stats = handler.get_stats()
        assert "name" in stats
        assert "enabled" in stats
        assert "event_count" in stats
        assert "error_count" in stats
        assert "last_event_time" in stats
        assert stats["name"] == "test-handler"


# ============================================================================
# Integration Tests
# ============================================================================


class TestHandlerIntegration:
    """Integration tests combining multiple handlers."""

    def test_logging_and_metrics_together(self, all_event_types, caplog):
        """Test LoggingHandler and MetricsHandler together."""
        logging_handler = LoggingHandler()
        metrics_handler = MetricsHandler()
        chain = ChainHandler([logging_handler, metrics_handler])
        import asyncio

        for event in all_event_types:
            with caplog.at_level(logging.INFO):
                asyncio.run(chain(event))

        metrics = metrics_handler.get_metrics()
        assert metrics["total_events"] == len(all_event_types)

    def test_audit_and_persistence_together(self, all_event_types):
        """Test AuditHandler and PersistenceHandler together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_handler = AuditHandler()
            persistence_handler = PersistenceHandler(
                Path(tmpdir) / "events.jsonl", flush_interval=100
            )
            chain = ChainHandler([audit_handler, persistence_handler])
            import asyncio

            for event in all_event_types:
                asyncio.run(chain(event))

            asyncio.run(persistence_handler.flush())

            audit_log = audit_handler.get_audit_log()
            assert len(audit_log) == len(all_event_types)

    def test_all_handlers_with_all_event_types(self, all_event_types):
        """Test all handlers working together with all event types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handlers = ChainHandler(
                [
                    LoggingHandler(name="logger"),
                    MetricsHandler(name="metrics"),
                    AuditHandler(name="audit"),
                    PersistenceHandler(
                        Path(tmpdir) / "events.jsonl", flush_interval=100, name="persistence"
                    ),
                ]
            )
            import asyncio

            for event in all_event_types:
                asyncio.run(handlers(event))

            # Verify all handlers processed events
            metrics = [h for h in handlers.handlers if isinstance(h, MetricsHandler)][0]
            metrics_data = metrics.get_metrics()
            assert metrics_data["total_events"] == len(all_event_types)
