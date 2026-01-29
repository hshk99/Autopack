"""Unit tests for memory retrieval quality metrics.

IMP-MEM-005: Tests for MemoryRetrievalMetrics, RetrievalQualityTracker,
and integration with MemoryService.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from autopack.telemetry.meta_metrics import (MemoryRetrievalMetrics,
                                             RetrievalQualitySummary,
                                             RetrievalQualityTracker)


class TestMemoryRetrievalMetrics:
    """Tests for MemoryRetrievalMetrics dataclass."""

    def test_create_metrics_with_required_fields(self):
        """Should create metrics with all required fields."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc123",
            hit_count=5,
            avg_relevance=0.75,
            max_relevance=0.95,
            min_relevance=0.55,
            avg_freshness_hours=12.5,
            stale_count=1,
            collection="code",
        )

        assert metrics.query_hash == "abc123"
        assert metrics.hit_count == 5
        assert metrics.avg_relevance == 0.75
        assert metrics.max_relevance == 0.95
        assert metrics.min_relevance == 0.55
        assert metrics.avg_freshness_hours == 12.5
        assert metrics.stale_count == 1
        assert metrics.collection == "code"
        assert metrics.timestamp is not None

    def test_to_dict_serialization(self):
        """Should convert metrics to dictionary correctly."""
        timestamp = datetime(2025, 1, 15, 10, 30, 0)
        metrics = MemoryRetrievalMetrics(
            query_hash="abc123",
            hit_count=5,
            avg_relevance=0.75,
            max_relevance=0.95,
            min_relevance=0.55,
            avg_freshness_hours=12.5,
            stale_count=1,
            collection="code",
            timestamp=timestamp,
        )

        result = metrics.to_dict()

        assert result["query_hash"] == "abc123"
        assert result["hit_count"] == 5
        assert result["avg_relevance"] == 0.75
        assert result["collection"] == "code"
        assert result["timestamp"] == timestamp.isoformat()

    def test_hit_rate_quality_good(self):
        """Should return 'good' when hit count >= 3."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=10,
            stale_count=0,
            collection="code",
        )

        assert metrics.hit_rate_quality == "good"

    def test_hit_rate_quality_sparse(self):
        """Should return 'sparse' when hit count is 1-2."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=2,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=10,
            stale_count=0,
            collection="code",
        )

        assert metrics.hit_rate_quality == "sparse"

    def test_hit_rate_quality_empty(self):
        """Should return 'empty' when hit count is 0."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=0,
            avg_relevance=0.0,
            max_relevance=0.0,
            min_relevance=0.0,
            avg_freshness_hours=0,
            stale_count=0,
            collection="code",
        )

        assert metrics.hit_rate_quality == "empty"

    def test_relevance_quality_high(self):
        """Should return 'high' when avg relevance >= 0.7."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=10,
            stale_count=0,
            collection="code",
        )

        assert metrics.relevance_quality == "high"

    def test_relevance_quality_medium(self):
        """Should return 'medium' when avg relevance is 0.4-0.7."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.5,
            max_relevance=0.6,
            min_relevance=0.4,
            avg_freshness_hours=10,
            stale_count=0,
            collection="code",
        )

        assert metrics.relevance_quality == "medium"

    def test_relevance_quality_low(self):
        """Should return 'low' when avg relevance < 0.4."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.3,
            max_relevance=0.4,
            min_relevance=0.2,
            avg_freshness_hours=10,
            stale_count=0,
            collection="code",
        )

        assert metrics.relevance_quality == "low"

    def test_freshness_quality_fresh(self):
        """Should return 'fresh' when avg freshness <= 24 hours."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=12,
            stale_count=0,
            collection="code",
        )

        assert metrics.freshness_quality == "fresh"

    def test_freshness_quality_aging(self):
        """Should return 'aging' when avg freshness is 24-168 hours."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=72,
            stale_count=0,
            collection="code",
        )

        assert metrics.freshness_quality == "aging"

    def test_freshness_quality_stale(self):
        """Should return 'stale' when avg freshness > 168 hours."""
        metrics = MemoryRetrievalMetrics(
            query_hash="abc",
            hit_count=5,
            avg_relevance=0.8,
            max_relevance=0.9,
            min_relevance=0.7,
            avg_freshness_hours=200,
            stale_count=0,
            collection="code",
        )

        assert metrics.freshness_quality == "stale"


class TestRetrievalQualitySummary:
    """Tests for RetrievalQualitySummary dataclass."""

    def test_overall_quality_healthy(self):
        """Should return 'healthy' for good metrics."""
        summary = RetrievalQualitySummary(
            total_retrievals=100,
            avg_hit_count=4.5,
            avg_relevance=0.75,
            avg_freshness_hours=24,
            empty_retrieval_rate=0.1,
            low_relevance_rate=0.15,
            stale_result_rate=0.2,
            period_start=datetime.utcnow() - timedelta(hours=24),
            period_end=datetime.utcnow(),
        )

        assert summary.overall_quality == "healthy"

    def test_overall_quality_degraded(self):
        """Should return 'degraded' for medium issues."""
        summary = RetrievalQualitySummary(
            total_retrievals=100,
            avg_hit_count=4.5,
            avg_relevance=0.45,  # Low relevance
            avg_freshness_hours=24,
            empty_retrieval_rate=0.1,
            low_relevance_rate=0.15,
            stale_result_rate=0.2,
            period_start=datetime.utcnow() - timedelta(hours=24),
            period_end=datetime.utcnow(),
        )

        assert summary.overall_quality == "degraded"

    def test_overall_quality_poor(self):
        """Should return 'poor' for high empty retrieval rate."""
        summary = RetrievalQualitySummary(
            total_retrievals=100,
            avg_hit_count=0.5,
            avg_relevance=0.75,
            avg_freshness_hours=24,
            empty_retrieval_rate=0.4,  # High empty rate
            low_relevance_rate=0.15,
            stale_result_rate=0.2,
            period_start=datetime.utcnow() - timedelta(hours=24),
            period_end=datetime.utcnow(),
        )

        assert summary.overall_quality == "poor"

    def test_to_dict_serialization(self):
        """Should convert summary to dictionary correctly."""
        start = datetime(2025, 1, 15, 10, 0, 0)
        end = datetime(2025, 1, 15, 12, 0, 0)
        summary = RetrievalQualitySummary(
            total_retrievals=50,
            avg_hit_count=3.5,
            avg_relevance=0.65,
            avg_freshness_hours=36,
            empty_retrieval_rate=0.1,
            low_relevance_rate=0.2,
            stale_result_rate=0.15,
            period_start=start,
            period_end=end,
        )

        result = summary.to_dict()

        assert result["total_retrievals"] == 50
        assert result["avg_hit_count"] == 3.5
        assert result["avg_relevance"] == 0.65
        assert result["period_start"] == start.isoformat()
        assert result["period_end"] == end.isoformat()


class TestRetrievalQualityTracker:
    """Tests for RetrievalQualityTracker class."""

    def test_initialization(self):
        """Should initialize with default values."""
        tracker = RetrievalQualityTracker()

        assert tracker.freshness_threshold_hours == 168
        assert tracker.max_history_size == 1000

    def test_initialization_with_custom_values(self):
        """Should accept custom initialization values."""
        tracker = RetrievalQualityTracker(
            freshness_threshold_hours=72,
            max_history_size=500,
        )

        assert tracker.freshness_threshold_hours == 72
        assert tracker.max_history_size == 500

    def test_record_retrieval_with_results(self):
        """Should record retrieval metrics correctly."""
        tracker = RetrievalQualityTracker()

        results = [
            {"score": 0.9, "payload": {"timestamp": "2025-01-15T10:00:00Z"}},
            {"score": 0.8, "payload": {"timestamp": "2025-01-15T09:00:00Z"}},
            {"score": 0.7, "payload": {"timestamp": "2025-01-14T10:00:00Z"}},
        ]

        metrics = tracker.record_retrieval(
            query="error handling patterns",
            results=results,
            collection="code",
        )

        assert metrics.hit_count == 3
        assert metrics.avg_relevance == pytest.approx(0.8, rel=0.01)
        assert metrics.max_relevance == 0.9
        assert metrics.min_relevance == 0.7
        assert metrics.collection == "code"

    def test_record_retrieval_with_empty_results(self):
        """Should handle empty results correctly."""
        tracker = RetrievalQualityTracker()

        metrics = tracker.record_retrieval(
            query="nonexistent pattern",
            results=[],
            collection="code",
        )

        assert metrics.hit_count == 0
        assert metrics.avg_relevance == 0.0
        assert metrics.max_relevance == 0.0
        assert metrics.min_relevance == 0.0
        assert metrics.avg_freshness_hours == 0.0

    def test_record_retrieval_detects_stale_results(self):
        """Should count stale results based on freshness threshold."""
        tracker = RetrievalQualityTracker(freshness_threshold_hours=72)

        now = datetime.utcnow()
        old_time = (now - timedelta(hours=200)).isoformat()
        recent_time = (now - timedelta(hours=24)).isoformat()

        results = [
            {"score": 0.9, "payload": {"timestamp": recent_time}},
            {"score": 0.8, "payload": {"timestamp": old_time}},  # Stale
            {"score": 0.7, "payload": {"timestamp": old_time}},  # Stale
        ]

        metrics = tracker.record_retrieval(
            query="test query",
            results=results,
            collection="code",
            timestamp=now,
        )

        assert metrics.stale_count == 2

    def test_get_quality_summary_empty(self):
        """Should return empty summary when no retrievals recorded."""
        tracker = RetrievalQualityTracker()

        summary = tracker.get_quality_summary()

        assert summary.total_retrievals == 0
        assert summary.avg_hit_count == 0.0
        assert summary.avg_relevance == 0.0

    def test_get_quality_summary_with_data(self):
        """Should aggregate quality metrics correctly."""
        tracker = RetrievalQualityTracker()

        # Record several retrievals
        tracker.record_retrieval("query1", [{"score": 0.9}, {"score": 0.8}], "code")
        tracker.record_retrieval("query2", [{"score": 0.7}, {"score": 0.6}], "code")
        tracker.record_retrieval("query3", [], "code")  # Empty

        summary = tracker.get_quality_summary()

        assert summary.total_retrievals == 3
        assert summary.avg_hit_count == pytest.approx(4 / 3, rel=0.01)
        assert summary.empty_retrieval_rate == pytest.approx(1 / 3, rel=0.01)

    def test_get_quality_summary_filter_by_collection(self):
        """Should filter by collection when specified."""
        tracker = RetrievalQualityTracker()

        tracker.record_retrieval("query1", [{"score": 0.9}], "code")
        tracker.record_retrieval("query2", [{"score": 0.8}], "hints")
        tracker.record_retrieval("query3", [{"score": 0.7}], "code")

        summary = tracker.get_quality_summary(collection="code")

        assert summary.total_retrievals == 2

    def test_get_quality_summary_filter_by_time(self):
        """Should filter by time when specified."""
        tracker = RetrievalQualityTracker()

        now = datetime.utcnow()
        old_time = now - timedelta(hours=48)

        tracker.record_retrieval("query1", [{"score": 0.9}], "code", timestamp=old_time)
        tracker.record_retrieval("query2", [{"score": 0.8}], "code", timestamp=now)

        cutoff = now - timedelta(hours=24)
        summary = tracker.get_quality_summary(since=cutoff)

        assert summary.total_retrievals == 1

    def test_get_collection_breakdown(self):
        """Should return breakdown by collection."""
        tracker = RetrievalQualityTracker()

        tracker.record_retrieval("query1", [{"score": 0.9}], "code")
        tracker.record_retrieval("query2", [{"score": 0.8}], "hints")
        tracker.record_retrieval("query3", [{"score": 0.7}], "code")

        breakdown = tracker.get_collection_breakdown()

        assert "code" in breakdown
        assert "hints" in breakdown
        assert breakdown["code"].total_retrievals == 2
        assert breakdown["hints"].total_retrievals == 1

    def test_get_recent_metrics(self):
        """Should return most recent metrics."""
        tracker = RetrievalQualityTracker()

        tracker.record_retrieval("query1", [{"score": 0.9}], "code")
        tracker.record_retrieval("query2", [{"score": 0.8}], "code")
        tracker.record_retrieval("query3", [{"score": 0.7}], "code")

        recent = tracker.get_recent_metrics(count=2)

        assert len(recent) == 2
        # Most recent first
        assert recent[0].avg_relevance == 0.7
        assert recent[1].avg_relevance == 0.8

    def test_clear_history(self):
        """Should clear all retrieval history."""
        tracker = RetrievalQualityTracker()

        tracker.record_retrieval("query1", [{"score": 0.9}], "code")
        tracker.record_retrieval("query2", [{"score": 0.8}], "code")

        tracker.clear_history()

        summary = tracker.get_quality_summary()
        assert summary.total_retrievals == 0

    def test_history_size_limit(self):
        """Should respect max history size."""
        tracker = RetrievalQualityTracker(max_history_size=3)

        for i in range(5):
            tracker.record_retrieval(f"query{i}", [{"score": 0.9}], "code")

        summary = tracker.get_quality_summary()
        assert summary.total_retrievals == 3

    def test_to_dict_serialization(self):
        """Should serialize tracker state correctly."""
        tracker = RetrievalQualityTracker(freshness_threshold_hours=100)

        tracker.record_retrieval("query1", [{"score": 0.9}], "code")

        result = tracker.to_dict()

        assert result["freshness_threshold_hours"] == 100
        assert "summary" in result
        assert "overall_quality" in result
        assert "recent_retrievals" in result
        assert "collection_breakdown" in result


class TestMemoryServiceRetrievalMetricsIntegration:
    """Tests for MemoryService retrieval quality metrics integration."""

    def test_memory_service_accepts_retrieval_quality_tracker(self):
        """MemoryService should allow setting a retrieval quality tracker."""
        from autopack.memory.memory_service import MemoryService

        tracker = RetrievalQualityTracker()

        # Create disabled memory service to avoid store initialization
        with patch.dict("os.environ", {"AUTOPACK_ENABLE_MEMORY": "false"}):
            service = MemoryService(enabled=False)

        service.set_retrieval_quality_tracker(tracker)

        assert service.retrieval_quality_tracker is tracker

    def test_memory_service_retrieval_quality_tracker_default_none(self):
        """MemoryService should have no tracker by default."""
        from autopack.memory.memory_service import MemoryService

        with patch.dict("os.environ", {"AUTOPACK_ENABLE_MEMORY": "false"}):
            service = MemoryService(enabled=False)

        assert service.retrieval_quality_tracker is None

    def test_get_retrieval_quality_summary_without_tracker(self):
        """get_retrieval_quality_summary should return None without tracker."""
        from autopack.memory.memory_service import MemoryService

        with patch.dict("os.environ", {"AUTOPACK_ENABLE_MEMORY": "false"}):
            service = MemoryService(enabled=False)

        assert service.get_retrieval_quality_summary() is None

    def test_get_retrieval_quality_summary_with_tracker(self):
        """get_retrieval_quality_summary should return tracker data when set."""
        from autopack.memory.memory_service import MemoryService

        tracker = RetrievalQualityTracker()
        tracker.record_retrieval("test", [{"score": 0.9}], "code")

        with patch.dict("os.environ", {"AUTOPACK_ENABLE_MEMORY": "false"}):
            service = MemoryService(enabled=False)

        service.set_retrieval_quality_tracker(tracker)

        summary = service.get_retrieval_quality_summary()

        assert summary is not None
        assert "summary" in summary
        assert summary["summary"]["total_retrievals"] == 1
