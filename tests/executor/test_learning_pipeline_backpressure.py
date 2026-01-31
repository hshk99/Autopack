"""Tests for IMP-REL-010: Learning Pipeline Backpressure.

Tests verify that learning memory writes have backpressure and overflow
protection to prevent OOM crashes and data loss.
"""

import errno
import time
from unittest.mock import MagicMock, patch

import pytest

from autopack.executor.learning_pipeline import (MAX_BATCH_SIZE, MAX_MEMORY_MB,
                                                 LearningHint,
                                                 LearningPipeline)


class TestLearningPipelineBackpressure:
    """Test backpressure mechanisms in learning pipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create a LearningPipeline instance for testing."""
        return LearningPipeline(run_id="test_run")

    def test_chunked_splits_items_correctly(self, pipeline):
        """Test that _chunked helper properly splits items into chunks."""
        items = list(range(250))  # 250 items

        chunks = list(pipeline._chunked(items, MAX_BATCH_SIZE))

        # With MAX_BATCH_SIZE=100, should have 3 chunks: 100, 100, 50
        assert len(chunks) == 3
        assert len(chunks[0]) == 100
        assert len(chunks[1]) == 100
        assert len(chunks[2]) == 50

    def test_chunked_empty_list(self, pipeline):
        """Test that _chunked handles empty list."""
        items = []
        chunks = list(pipeline._chunked(items, MAX_BATCH_SIZE))
        assert len(chunks) == 0

    def test_chunked_single_batch(self, pipeline):
        """Test that _chunked returns single chunk when items fit."""
        items = list(range(50))  # Less than MAX_BATCH_SIZE
        chunks = list(pipeline._chunked(items, MAX_BATCH_SIZE))
        assert len(chunks) == 1
        assert chunks[0] == items

    def test_check_memory_pressure_detects_high_usage(self, pipeline):
        """Test that memory pressure is detected when usage exceeds limit."""
        # Mock memory usage above threshold
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB + 100) * 1024 * 1024

        with patch("psutil.Process", return_value=mock_process):
            assert pipeline._check_memory_pressure() is True

    def test_check_memory_pressure_allows_low_usage(self, pipeline):
        """Test that memory pressure is not detected when usage is low."""
        # Mock memory usage below threshold
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB - 100) * 1024 * 1024

        with patch("psutil.Process", return_value=mock_process):
            assert pipeline._check_memory_pressure() is False

    def test_check_memory_pressure_handles_error(self, pipeline):
        """Test that memory check gracefully handles errors."""
        with patch("psutil.Process", side_effect=Exception("psutil error")):
            # Should return False without raising
            assert pipeline._check_memory_pressure() is False

    def test_persist_hints_batch_with_memory_pressure(self, pipeline):
        """Test that batch persistence throttles under memory pressure."""
        # Mock high memory usage
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB + 100) * 1024 * 1024

        # Create some hints
        for i in range(5):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.return_value = True

        # Time the operation to verify throttling
        with patch("psutil.Process", return_value=mock_process):
            start = time.time()
            persisted = pipeline._persist_hints_batch(memory_service, "test_project")
            elapsed = time.time() - start

            # Should have slept for backpressure (at least 1 second)
            assert elapsed >= 1.0
            assert persisted == 5

    def test_persist_hints_batch_chunks_large_batches(self, pipeline):
        """Test that large batches are chunked properly."""
        # Create many hints (more than MAX_BATCH_SIZE)
        for i in range(MAX_BATCH_SIZE + 50):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.return_value = True

        # Track calls to verify chunking
        with patch.object(pipeline, "_chunked", wraps=pipeline._chunked) as mock_chunked:
            persisted = pipeline._persist_hints_batch(memory_service, "test_project")

            # Verify _chunked was called
            mock_chunked.assert_called_once()
            # All hints should be persisted
            assert persisted == MAX_BATCH_SIZE + 50

    def test_persist_hints_batch_handles_memory_error(self, pipeline):
        """Test that MemoryError is properly handled during persistence."""
        # Mock normal memory usage (so no backpressure)
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB - 100) * 1024 * 1024

        # Create some hints
        for i in range(3):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service that raises MemoryError on second write
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.side_effect = [
            True,
            MemoryError("Out of memory"),
            True,
        ]

        # Should raise MemoryError without swallowing it
        with patch("psutil.Process", return_value=mock_process):
            with pytest.raises(MemoryError):
                pipeline._persist_hints_batch(memory_service, "test_project")

    def test_persist_hints_batch_handles_disk_full(self, pipeline):
        """Test that disk full (ENOSPC) is properly handled."""
        # Mock normal memory usage
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB - 100) * 1024 * 1024

        # Create some hints
        for i in range(3):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service that raises OSError with ENOSPC
        memory_service = MagicMock()
        os_error = OSError("No space left on device")
        os_error.errno = errno.ENOSPC
        memory_service.write_telemetry_insight.side_effect = [True, os_error, True]

        # Should raise OSError with ENOSPC
        with patch("psutil.Process", return_value=mock_process):
            with pytest.raises(OSError) as exc_info:
                pipeline._persist_hints_batch(memory_service, "test_project")

            assert exc_info.value.errno == errno.ENOSPC

    def test_persist_hints_batch_partial_success(self, pipeline):
        """Test that partial persistence returns count of successful hints."""
        # Create some hints
        for i in range(5):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service that succeeds for some calls
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.side_effect = [True, True, False, True, False]

        persisted = pipeline._persist_hints_batch(memory_service, "test_project")

        # Should have persisted 3 hints (others failed silently in normal operation)
        assert persisted == 3

    def test_persist_hints_batch_all_failures_raises(self, pipeline):
        """Test that all failures result in exception being raised."""
        # Create one hint
        pipeline._hints.append(
            LearningHint(
                phase_id="phase_0",
                hint_type="ci_fail",
                hint_text="Test hint",
                source_issue_keys=["issue_0"],
                recorded_at=time.time(),
            )
        )

        # Mock memory service that fails
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.side_effect = RuntimeError("Service unavailable")

        # Should raise the exception
        with pytest.raises(RuntimeError):
            pipeline._persist_hints_batch(memory_service, "test_project")

    def test_empty_hints_batch_returns_zero(self, pipeline):
        """Test that empty hints batch returns 0."""
        pipeline._hints = []

        memory_service = MagicMock()
        persisted = pipeline._persist_hints_batch(memory_service, "test_project")

        assert persisted == 0
        memory_service.write_telemetry_insight.assert_not_called()

    def test_persist_hints_guaranteed_respects_backpressure(self, pipeline):
        """Test that guaranteed persistence respects backpressure throttling."""
        # Mock high memory usage
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = (MAX_MEMORY_MB + 50) * 1024 * 1024

        # Create hints
        for i in range(3):
            pipeline._hints.append(
                LearningHint(
                    phase_id=f"phase_{i}",
                    hint_type="ci_fail",
                    hint_text=f"Test hint {i}",
                    source_issue_keys=[f"issue_{i}"],
                    recorded_at=time.time(),
                )
            )

        # Mock memory service
        memory_service = MagicMock()
        memory_service.write_telemetry_insight.return_value = True
        memory_service.retrieve_insights.return_value = [{"hint_id": "test"}]

        with patch("psutil.Process", return_value=mock_process):
            start = time.time()
            persisted = pipeline.persist_hints_guaranteed(
                memory_service=memory_service,
                project_id="test_project",
                max_retries=1,
                verify=False,
            )
            elapsed = time.time() - start

            # Should apply backpressure (sleep for 1 second)
            assert elapsed >= 1.0
            assert persisted == 3

    def test_batch_size_constant_matches_workflow(self):
        """Verify that MAX_BATCH_SIZE matches workflow specification."""
        # IMP-REL-010 workflow specifies MAX_BATCH_SIZE = 100
        assert MAX_BATCH_SIZE == 100

    def test_memory_threshold_constant_matches_workflow(self):
        """Verify that MAX_MEMORY_MB matches workflow specification."""
        # IMP-REL-010 workflow specifies MAX_MEMORY_MB = 512
        assert MAX_MEMORY_MB == 512
