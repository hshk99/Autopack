"""Tests for memory quality control and cleanup functionality.

IMP-MEM-020: Tests for memory quality measurement and stale entry cleanup.

Tests cover:
- cleanup_stale_entries: Removing stale and low-relevance memory entries
- measure_memory_quality: Calculating signal-to-noise ratio and staleness metrics
- CleanupResult and MemoryQualityReport dataclass behavior
"""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from autopack.memory.memory_service import CleanupResult, MemoryQualityReport, MemoryService


class TestCleanupResult:
    """Tests for CleanupResult dataclass."""

    def test_cleanup_result_creation(self):
        """Should create CleanupResult with all required fields."""
        result = CleanupResult(
            total_scanned=100,
            stale_removed=20,
            low_relevance_removed=10,
            total_removed=30,
            retained=70,
            collections_processed=["run_summaries", "errors_ci"],
        )

        assert result.total_scanned == 100
        assert result.stale_removed == 20
        assert result.low_relevance_removed == 10
        assert result.total_removed == 30
        assert result.retained == 70
        assert result.collections_processed == ["run_summaries", "errors_ci"]
        assert result.errors == []  # Default empty list

    def test_cleanup_result_with_errors(self):
        """Should create CleanupResult with error messages."""
        result = CleanupResult(
            total_scanned=50,
            stale_removed=5,
            low_relevance_removed=0,
            total_removed=5,
            retained=45,
            collections_processed=["run_summaries"],
            errors=["Failed to access collection"],
        )

        assert result.errors == ["Failed to access collection"]


class TestMemoryQualityReport:
    """Tests for MemoryQualityReport dataclass."""

    def test_memory_quality_report_creation(self):
        """Should create MemoryQualityReport with all required fields."""
        report = MemoryQualityReport(
            total_entries=1000,
            fresh_entries=200,
            stale_entries=100,
            high_relevance_entries=600,
            low_relevance_entries=150,
            avg_relevance_score=0.65,
            avg_age_hours=48.5,
            signal_to_noise_ratio=4.0,
            staleness_ratio=0.1,
            quality_score=0.75,
        )

        assert report.total_entries == 1000
        assert report.fresh_entries == 200
        assert report.stale_entries == 100
        assert report.high_relevance_entries == 600
        assert report.low_relevance_entries == 150
        assert report.avg_relevance_score == 0.65
        assert report.avg_age_hours == 48.5
        assert report.signal_to_noise_ratio == 4.0
        assert report.staleness_ratio == 0.1
        assert report.quality_score == 0.75
        assert report.collection_stats == {}  # Default empty dict

    def test_memory_quality_report_with_collection_stats(self):
        """Should create MemoryQualityReport with per-collection statistics."""
        report = MemoryQualityReport(
            total_entries=500,
            fresh_entries=100,
            stale_entries=50,
            high_relevance_entries=300,
            low_relevance_entries=75,
            avg_relevance_score=0.7,
            avg_age_hours=72.0,
            signal_to_noise_ratio=4.0,
            staleness_ratio=0.1,
            quality_score=0.8,
            collection_stats={
                "run_summaries": {"total": 250, "fresh": 50, "stale": 25},
                "errors_ci": {"total": 250, "fresh": 50, "stale": 25},
            },
        )

        assert "run_summaries" in report.collection_stats
        assert report.collection_stats["run_summaries"]["total"] == 250


class TestCleanupStaleEntries:
    """Tests for cleanup_stale_entries method."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service.store = Mock()

            # Configure store methods
            service.store.scroll = Mock(return_value=[])
            service.store.delete = Mock(return_value=0)

            yield service

    def test_cleanup_returns_empty_result_when_disabled(self, memory_service):
        """Should return empty result when memory service is disabled."""
        memory_service.enabled = False

        result = memory_service.cleanup_stale_entries("test-project")

        assert result.total_scanned == 0
        assert result.total_removed == 0
        assert "Memory service is disabled" in result.errors

    def test_cleanup_validates_project_id(self, memory_service):
        """Should raise ProjectNamespaceError for empty project_id."""
        from autopack.memory.memory_service import ProjectNamespaceError

        with pytest.raises(ProjectNamespaceError):
            memory_service.cleanup_stale_entries("")

    def test_cleanup_removes_stale_entries(self, memory_service):
        """Should remove entries older than max_age_days."""
        # Create a timestamp older than 90 days
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "old-entry-1", "payload": {"timestamp": old_timestamp, "project_id": "test"}},
            {
                "id": "fresh-entry",
                "payload": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "project_id": "test",
                },
            },
        ]
        memory_service.store.delete.return_value = 1

        result = memory_service.cleanup_stale_entries(
            "test-project",
            max_age_days=90,
            collections=["run_summaries"],  # Limit to single collection
        )

        assert result.total_scanned == 2
        assert result.stale_removed == 1
        # Verify delete was called with the stale entry ID
        delete_calls = [call for call in memory_service.store.delete.call_args_list]
        assert len(delete_calls) >= 1

    def test_cleanup_removes_low_relevance_entries(self, memory_service):
        """Should remove entries with relevance below threshold."""
        memory_service.store.scroll.return_value = [
            {
                "id": "low-relevance-1",
                "payload": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "relevance_score": 0.1,
                    "project_id": "test",
                },
            },
            {
                "id": "high-relevance",
                "payload": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "relevance_score": 0.8,
                    "project_id": "test",
                },
            },
        ]
        memory_service.store.delete.return_value = 1

        result = memory_service.cleanup_stale_entries(
            "test-project",
            min_relevance=0.3,
            collections=["run_summaries"],  # Limit to single collection
        )

        assert result.total_scanned == 2
        assert result.low_relevance_removed == 1

    def test_cleanup_handles_multiple_collections(self, memory_service):
        """Should process all specified collections."""
        memory_service.store.scroll.return_value = []

        result = memory_service.cleanup_stale_entries(
            "test-project",
            collections=["run_summaries", "errors_ci", "doctor_hints"],
        )

        assert result.collections_processed == ["run_summaries", "errors_ci", "doctor_hints"]
        # scroll should be called for each collection
        assert memory_service.store.scroll.call_count == 3

    def test_cleanup_continues_on_collection_error(self, memory_service):
        """Should continue processing other collections if one fails.

        Note: _safe_store_call catches exceptions internally and returns defaults,
        so the outer error handling won't capture scroll errors. But processing
        continues for subsequent collections.
        """
        # First scroll raises exception (caught by _safe_store_call, returns [])
        # Second scroll succeeds with data
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        memory_service.store.scroll.side_effect = [
            Exception("Connection failed"),  # First collection - caught by _safe_store_call
            [{"id": "entry-1", "payload": {"timestamp": old_timestamp}}],  # Second collection
        ]
        memory_service.store.delete.return_value = 1

        result = memory_service.cleanup_stale_entries(
            "test-project",
            collections=["run_summaries", "errors_ci"],
        )

        # Both collections should be processed (scroll called twice)
        assert memory_service.store.scroll.call_count == 2
        # Second collection should have scanned and removed entries
        assert result.total_scanned == 1  # Only second collection had data
        assert result.stale_removed == 1


class TestMeasureMemoryQuality:
    """Tests for measure_memory_quality method."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service.store = Mock()

            # Configure store.scroll to return empty by default
            service.store.scroll = Mock(return_value=[])

            yield service

    def test_measure_returns_empty_report_when_disabled(self, memory_service):
        """Should return empty report when memory service is disabled."""
        memory_service.enabled = False

        report = memory_service.measure_memory_quality("test-project")

        assert report.total_entries == 0
        assert report.quality_score == 0.0

    def test_measure_validates_project_id(self, memory_service):
        """Should raise ProjectNamespaceError for empty project_id."""
        from autopack.memory.memory_service import ProjectNamespaceError

        with pytest.raises(ProjectNamespaceError):
            memory_service.measure_memory_quality("")

    def test_measure_calculates_staleness_metrics(self, memory_service):
        """Should correctly calculate fresh and stale entry counts."""
        fresh_timestamp = datetime.now(timezone.utc).isoformat()
        stale_timestamp = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "fresh-1", "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale-1", "payload": {"timestamp": stale_timestamp}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        assert report.total_entries == 2
        assert report.fresh_entries == 1
        assert report.stale_entries == 1

    def test_measure_calculates_relevance_metrics(self, memory_service):
        """Should correctly calculate high and low relevance entry counts."""
        timestamp = datetime.now(timezone.utc).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "high-1", "payload": {"timestamp": timestamp, "relevance_score": 0.8}},
            {"id": "medium-1", "payload": {"timestamp": timestamp, "relevance_score": 0.5}},
            {"id": "low-1", "payload": {"timestamp": timestamp, "relevance_score": 0.2}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        assert report.total_entries == 3
        assert report.high_relevance_entries == 1  # >= 0.6
        assert report.low_relevance_entries == 1  # < 0.3

    def test_measure_calculates_signal_to_noise_ratio(self, memory_service):
        """Should calculate signal-to-noise ratio correctly."""
        timestamp = datetime.now(timezone.utc).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "high-1", "payload": {"timestamp": timestamp, "relevance_score": 0.8}},
            {"id": "high-2", "payload": {"timestamp": timestamp, "relevance_score": 0.9}},
            {"id": "low-1", "payload": {"timestamp": timestamp, "relevance_score": 0.1}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        # 2 high relevance / 1 low relevance = 2.0
        assert report.signal_to_noise_ratio == 2.0

    def test_measure_calculates_quality_score(self, memory_service):
        """Should calculate overall quality score combining metrics."""
        timestamp = datetime.now(timezone.utc).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "entry-1", "payload": {"timestamp": timestamp, "relevance_score": 0.8}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        # Quality score should be between 0 and 1
        assert 0.0 <= report.quality_score <= 1.0

    def test_measure_includes_collection_stats(self, memory_service):
        """Should include per-collection statistics in report."""
        timestamp = datetime.now(timezone.utc).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "entry-1", "payload": {"timestamp": timestamp, "relevance_score": 0.8}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        assert "run_summaries" in report.collection_stats
        assert report.collection_stats["run_summaries"]["total"] == 1

    def test_measure_handles_missing_timestamps(self, memory_service):
        """Should handle entries without timestamps gracefully."""
        memory_service.store.scroll.return_value = [
            {"id": "no-timestamp", "payload": {"relevance_score": 0.5}},
            {
                "id": "with-timestamp",
                "payload": {"timestamp": datetime.now(timezone.utc).isoformat()},
            },
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        assert report.total_entries == 2
        # Entry without timestamp shouldn't be counted as fresh or stale

    def test_measure_handles_confidence_field(self, memory_service):
        """Should use 'confidence' field if 'relevance_score' is missing."""
        timestamp = datetime.now(timezone.utc).isoformat()

        memory_service.store.scroll.return_value = [
            {"id": "entry-1", "payload": {"timestamp": timestamp, "confidence": 0.8}},
        ]

        report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )

        assert report.high_relevance_entries == 1
        assert report.avg_relevance_score == 0.8


class TestIntegration:
    """Integration tests for memory quality functionality."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service.store = Mock()
            service.store.scroll = Mock(return_value=[])
            service.store.delete = Mock(return_value=0)

            yield service

    def test_cleanup_and_measure_workflow(self, memory_service):
        """Should be able to measure quality, cleanup, and measure again."""
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # Initial state with mixed entries
        memory_service.store.scroll.return_value = [
            {"id": "old-1", "payload": {"timestamp": old_timestamp, "relevance_score": 0.5}},
            {"id": "fresh-1", "payload": {"timestamp": fresh_timestamp, "relevance_score": 0.8}},
        ]

        # Measure initial quality
        initial_report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )
        assert initial_report.total_entries == 2
        assert initial_report.stale_entries == 1

        # After cleanup, only fresh entry remains
        memory_service.store.delete.return_value = 1
        memory_service.store.scroll.return_value = [
            {"id": "old-1", "payload": {"timestamp": old_timestamp, "relevance_score": 0.5}},
            {"id": "fresh-1", "payload": {"timestamp": fresh_timestamp, "relevance_score": 0.8}},
        ]

        cleanup_result = memory_service.cleanup_stale_entries(
            "test-project",
            max_age_days=90,
            collections=["run_summaries"],
        )
        assert cleanup_result.stale_removed == 1

        # After cleanup, simulate only fresh entries remaining
        memory_service.store.scroll.return_value = [
            {"id": "fresh-1", "payload": {"timestamp": fresh_timestamp, "relevance_score": 0.8}},
        ]

        # Measure final quality
        final_report = memory_service.measure_memory_quality(
            "test-project",
            collections=["run_summaries"],
        )
        assert final_report.total_entries == 1
        assert final_report.stale_entries == 0
        assert final_report.quality_score > initial_report.quality_score
