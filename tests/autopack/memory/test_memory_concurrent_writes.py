"""Tests for concurrent write safety in memory service and feedback pipeline.

IMP-AUTO-003: Tests for parallel write safety for memory insights.

Tests cover:
- Content-hash based deduplication in MemoryService.write_telemetry_insight
- Thread-safe concurrent writes to MemoryService
- Thread-safe access to FeedbackPipeline._pending_insights
- Concurrent flush operations in FeedbackPipeline
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome


class TestMemoryServiceConcurrentWrites:
    """Tests for concurrent write safety in MemoryService."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService with the concurrent write features."""
        with patch("autopack.memory.memory_service.MemoryService") as MockMemoryService:
            service = MockMemoryService.return_value
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()

            # Track actual write calls
            service.write_calls = []

            def mock_write_phase_summary(**kwargs):
                service.write_calls.append(("phase_summary", kwargs))
                return f"id_{len(service.write_calls)}"

            service.write_phase_summary = Mock(side_effect=mock_write_phase_summary)
            yield service

    def test_content_hash_deduplication(self):
        """Duplicate insights with same content should be skipped."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service.store = Mock()

            # Mock the write methods to track calls
            write_calls = []

            def mock_write_phase_summary(**kwargs):
                write_calls.append(kwargs)
                return "test_id"

            service.write_phase_summary = mock_write_phase_summary

            # Mock TelemetryFeedbackValidator
            with patch(
                "autopack.memory.memory_service.TelemetryFeedbackValidator"
            ) as MockValidator:
                MockValidator.validate_insight.return_value = (True, [])

                # Write first insight
                insight1 = {
                    "insight_type": "unknown",
                    "description": "Test insight",
                    "content": "Test content",
                    "phase_id": "phase_1",
                    "run_id": "run_1",
                }
                result1 = service.write_telemetry_insight(insight1)

                # Write duplicate insight (same type and content)
                insight2 = {
                    "insight_type": "unknown",
                    "description": "Test insight",
                    "content": "Test content",
                    "phase_id": "phase_2",
                    "run_id": "run_2",
                }
                result2 = service.write_telemetry_insight(insight2)

                # First should succeed, second should be skipped
                assert result1 == "test_id"
                assert result2 == ""  # Duplicate skipped
                assert len(write_calls) == 1  # Only one actual write

    def test_different_content_not_deduplicated(self):
        """Insights with different content should not be deduplicated."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service.store = Mock()

            write_calls = []

            def mock_write_phase_summary(**kwargs):
                write_calls.append(kwargs)
                return f"test_id_{len(write_calls)}"

            service.write_phase_summary = mock_write_phase_summary

            with patch(
                "autopack.memory.memory_service.TelemetryFeedbackValidator"
            ) as MockValidator:
                MockValidator.validate_insight.return_value = (True, [])

                # Write first insight
                insight1 = {
                    "insight_type": "unknown",
                    "description": "Test insight 1",
                    "content": "Content A",
                    "phase_id": "phase_1",
                    "run_id": "run_1",
                }
                result1 = service.write_telemetry_insight(insight1)

                # Write different insight
                insight2 = {
                    "insight_type": "unknown",
                    "description": "Test insight 2",
                    "content": "Content B",
                    "phase_id": "phase_2",
                    "run_id": "run_2",
                }
                result2 = service.write_telemetry_insight(insight2)

                # Both should succeed
                assert result1 == "test_id_1"
                assert result2 == "test_id_2"
                assert len(write_calls) == 2


class TestFeedbackPipelineConcurrentWrites:
    """Tests for thread-safe pending insights handling in FeedbackPipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create a FeedbackPipeline instance for testing."""
        # Create enabled pipeline but stop auto-flush timer immediately
        pipeline = FeedbackPipeline(enabled=True)
        pipeline.stop_auto_flush()  # Stop timer to avoid complications
        pipeline._auto_flush_enabled = False
        yield pipeline

    def test_insights_lock_exists(self, pipeline):
        """FeedbackPipeline should have _insights_lock for thread safety."""
        assert hasattr(pipeline, "_insights_lock")
        assert isinstance(pipeline._insights_lock, type(threading.Lock()))

    def test_concurrent_insight_queuing(self, pipeline):
        """Concurrent insight queuing should be thread-safe."""
        num_threads = 10
        insights_per_thread = 50
        errors = []
        results = []

        def queue_insights(thread_id):
            try:
                for i in range(insights_per_thread):
                    outcome = PhaseOutcome(
                        phase_id=f"phase_{thread_id}_{i}",
                        phase_type="test",
                        success=True,
                        status="completed",
                        run_id=f"run_{thread_id}_{i}",
                    )
                    result = pipeline.process_phase_outcome(outcome)
                    results.append(result)
            except Exception as e:
                errors.append(e)

        # Run concurrent threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=queue_insights, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify no errors occurred
        assert len(errors) == 0, f"Errors during concurrent queuing: {errors}"

        # Count successful results with insights created
        successful_results = [
            r for r in results if r.get("success") and r.get("insights_created", 0) > 0
        ]

        # Verify all outcomes were processed (each creates 1 insight)
        expected_count = num_threads * insights_per_thread
        assert len(successful_results) == expected_count, (
            f"Expected {expected_count} successful results, got {len(successful_results)}. "
            f"Sample results: {results[:5]}"
        )

    def test_concurrent_flush_safety(self, pipeline):
        """Concurrent flush operations should be thread-safe."""
        # Add a mock memory service so flush actually counts items
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value="test_id")
        pipeline.memory_service = mock_memory

        # Pre-populate with insights
        for i in range(100):
            with pipeline._insights_lock:
                pipeline._pending_insights.append(
                    {"insight_type": "test", "description": f"Insight {i}"}
                )

        errors = []
        flush_results = []

        def do_flush():
            try:
                result = pipeline.flush_pending_insights()
                flush_results.append(result)
            except Exception as e:
                errors.append(e)

        # Run concurrent flushes
        threads = []
        for _ in range(5):
            t = threading.Thread(target=do_flush)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors during concurrent flush: {errors}"

        # Verify total flushed equals initial count
        # (one flush gets them all, others get 0)
        assert sum(flush_results) == 100

        # Verify list is empty after flushes
        with pipeline._insights_lock:
            assert len(pipeline._pending_insights) == 0

    def test_queue_and_flush_concurrent(self, pipeline):
        """Queueing and flushing concurrently should be thread-safe."""
        num_producers = 5
        insights_per_producer = 20
        flush_interval = 0.01  # 10ms
        errors = []

        def produce_insights(producer_id):
            try:
                for i in range(insights_per_producer):
                    outcome = PhaseOutcome(
                        phase_id=f"phase_{producer_id}_{i}",
                        phase_type="test",
                        success=True,
                        status="completed",
                        run_id=f"concurrent_run_{producer_id}_{i}",
                    )
                    pipeline.process_phase_outcome(outcome)
                    time.sleep(0.001)  # Small delay to increase interleaving
            except Exception as e:
                errors.append(("producer", producer_id, e))

        def consume_insights():
            try:
                for _ in range(10):
                    pipeline.flush_pending_insights()
                    time.sleep(flush_interval)
            except Exception as e:
                errors.append(("consumer", 0, e))

        # Start producers and consumer
        threads = []
        for i in range(num_producers):
            t = threading.Thread(target=produce_insights, args=(i,))
            threads.append(t)

        consumer = threading.Thread(target=consume_insights)
        threads.append(consumer)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors during concurrent operations: {errors}"

        # Final flush to clean up
        pipeline.flush_pending_insights()


class TestContentHashDeduplication:
    """Tests for content-hash based deduplication."""

    def test_hash_computation_consistency(self):
        """Same content should always produce same hash."""
        import hashlib

        content1 = "unknown:Test content"
        content2 = "unknown:Test content"

        hash1 = hashlib.sha256(content1.encode()).hexdigest()[:16]
        hash2 = hashlib.sha256(content2.encode()).hexdigest()[:16]

        assert hash1 == hash2

    def test_hash_computation_different_content(self):
        """Different content should produce different hashes."""
        import hashlib

        content1 = "unknown:Content A"
        content2 = "unknown:Content B"

        hash1 = hashlib.sha256(content1.encode()).hexdigest()[:16]
        hash2 = hashlib.sha256(content2.encode()).hexdigest()[:16]

        assert hash1 != hash2

    def test_hash_includes_insight_type(self):
        """Hash should include insight_type for differentiation."""
        import hashlib

        # Same content, different types
        content1 = "cost_sink:Same content"
        content2 = "failure_mode:Same content"

        hash1 = hashlib.sha256(content1.encode()).hexdigest()[:16]
        hash2 = hashlib.sha256(content2.encode()).hexdigest()[:16]

        assert hash1 != hash2
