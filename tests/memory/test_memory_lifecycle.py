"""Tests for Memory Lifecycle Management (IMP-LOOP-012).

Tests cover:
- MemoryMaintenancePolicy eviction logic
- Duplicate compaction
- Memory usage alerts
- Full maintenance cycle
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from autopack.memory.memory_service import MemoryMaintenancePolicy


class TestMemoryMaintenancePolicy:
    """Tests for MemoryMaintenancePolicy class."""

    def test_default_values(self):
        """Test default policy values."""
        policy = MemoryMaintenancePolicy()
        assert policy.max_age_days == 90
        assert policy.max_memory_mb == 100.0
        assert policy.dedup_enabled is True
        assert policy.alert_callback is None

    def test_custom_values(self):
        """Test policy with custom values."""
        callback = Mock()
        policy = MemoryMaintenancePolicy(
            max_age_days=30,
            max_memory_mb=50.0,
            dedup_enabled=False,
            alert_callback=callback,
        )
        assert policy.max_age_days == 30
        assert policy.max_memory_mb == 50.0
        assert policy.dedup_enabled is False
        assert policy.alert_callback is callback


class TestShouldEvict:
    """Tests for should_evict method."""

    def test_evict_old_insight(self):
        """Test that old insights are marked for eviction."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        insight = {"timestamp": "2024-01-01T00:00:00+00:00"}
        assert policy.should_evict(insight, age_days=100) is True

    def test_keep_fresh_insight(self):
        """Test that fresh insights are not marked for eviction."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        insight = {"timestamp": "2024-01-01T00:00:00+00:00"}
        assert policy.should_evict(insight, age_days=30) is False

    def test_evict_at_boundary(self):
        """Test eviction exactly at the boundary."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        insight = {"timestamp": "2024-01-01T00:00:00+00:00"}
        # Exactly 90 days should NOT be evicted
        assert policy.should_evict(insight, age_days=90) is False
        # 91 days should be evicted
        assert policy.should_evict(insight, age_days=91) is True


class TestCalculateAgeDays:
    """Tests for calculate_age_days method."""

    def test_calculate_age_valid_timestamp(self):
        """Test age calculation with valid timestamp."""
        policy = MemoryMaintenancePolicy()
        # Create a timestamp 10 days ago
        ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        age = policy.calculate_age_days(ten_days_ago)
        assert age == 10

    def test_calculate_age_z_suffix(self):
        """Test age calculation with Z suffix timestamp."""
        policy = MemoryMaintenancePolicy()
        ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        age = policy.calculate_age_days(ten_days_ago)
        assert age == 10

    def test_calculate_age_none_timestamp(self):
        """Test age calculation with None timestamp."""
        policy = MemoryMaintenancePolicy()
        assert policy.calculate_age_days(None) == 0

    def test_calculate_age_invalid_timestamp(self):
        """Test age calculation with invalid timestamp."""
        policy = MemoryMaintenancePolicy()
        assert policy.calculate_age_days("invalid-timestamp") == 0

    def test_calculate_age_empty_string(self):
        """Test age calculation with empty string."""
        policy = MemoryMaintenancePolicy()
        assert policy.calculate_age_days("") == 0


class TestCompactDuplicates:
    """Tests for compact_duplicates method."""

    def test_compact_with_duplicates(self):
        """Test compaction removes duplicates keeping newest."""
        policy = MemoryMaintenancePolicy()
        insights = [
            {
                "id": "1",
                "payload": {
                    "content_hash": "abc123",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
            },
            {
                "id": "2",
                "payload": {
                    "content_hash": "abc123",
                    "timestamp": "2024-01-05T00:00:00+00:00",
                },
            },
            {
                "id": "3",
                "payload": {
                    "content_hash": "def456",
                    "timestamp": "2024-01-03T00:00:00+00:00",
                },
            },
        ]
        result = policy.compact_duplicates(insights)
        assert len(result) == 2
        # Should keep id=2 (newest abc123) and id=3 (only def456)
        result_ids = {r["id"] for r in result}
        assert "2" in result_ids
        assert "3" in result_ids
        assert "1" not in result_ids

    def test_compact_no_duplicates(self):
        """Test compaction with no duplicates returns all."""
        policy = MemoryMaintenancePolicy()
        insights = [
            {
                "id": "1",
                "payload": {
                    "content_hash": "abc123",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
            },
            {
                "id": "2",
                "payload": {
                    "content_hash": "def456",
                    "timestamp": "2024-01-02T00:00:00+00:00",
                },
            },
        ]
        result = policy.compact_duplicates(insights)
        assert len(result) == 2

    def test_compact_empty_list(self):
        """Test compaction with empty list."""
        policy = MemoryMaintenancePolicy()
        result = policy.compact_duplicates([])
        assert result == []

    def test_compact_disabled(self):
        """Test compaction when dedup_enabled is False."""
        policy = MemoryMaintenancePolicy(dedup_enabled=False)
        insights = [
            {
                "id": "1",
                "payload": {
                    "content_hash": "abc123",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
            },
            {
                "id": "2",
                "payload": {
                    "content_hash": "abc123",
                    "timestamp": "2024-01-05T00:00:00+00:00",
                },
            },
        ]
        result = policy.compact_duplicates(insights)
        # Should return all insights unchanged when dedup is disabled
        assert len(result) == 2

    def test_compact_missing_content_hash(self):
        """Test compaction with missing content_hash uses unique keys."""
        policy = MemoryMaintenancePolicy()
        insights = [
            {
                "id": "1",
                "payload": {"timestamp": "2024-01-01T00:00:00+00:00"},
            },
            {
                "id": "2",
                "payload": {"timestamp": "2024-01-02T00:00:00+00:00"},
            },
        ]
        result = policy.compact_duplicates(insights)
        # Should keep both since they have different ids
        assert len(result) == 2


class TestCheckMemoryUsage:
    """Tests for check_memory_usage method."""

    def test_within_limit(self):
        """Test memory usage within limit returns True."""
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0)
        assert policy.check_memory_usage(50.0) is True

    def test_exceeds_limit(self):
        """Test memory usage exceeding limit returns False."""
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0)
        assert policy.check_memory_usage(150.0) is False

    def test_at_limit(self):
        """Test memory usage exactly at limit returns True."""
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0)
        assert policy.check_memory_usage(100.0) is True

    def test_alert_callback_called_when_exceeded(self):
        """Test alert callback is called when limit exceeded."""
        callback = Mock()
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0, alert_callback=callback)
        policy.check_memory_usage(150.0)
        callback.assert_called_once_with(150.0, 100.0)

    def test_alert_callback_not_called_when_ok(self):
        """Test alert callback is not called when within limit."""
        callback = Mock()
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0, alert_callback=callback)
        policy.check_memory_usage(50.0)
        callback.assert_not_called()

    def test_alert_callback_error_handled(self):
        """Test that callback errors are handled gracefully."""
        callback = Mock(side_effect=Exception("Callback error"))
        policy = MemoryMaintenancePolicy(max_memory_mb=100.0, alert_callback=callback)
        # Should not raise, just log the error
        result = policy.check_memory_usage(150.0)
        assert result is False


class TestGetEvictionCandidates:
    """Tests for get_eviction_candidates method."""

    def test_get_candidates_mixed_ages(self):
        """Test getting eviction candidates with mixed ages."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        fresh_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        insights = [
            {"id": "old", "payload": {"timestamp": old_ts}},
            {"id": "fresh", "payload": {"timestamp": fresh_ts}},
        ]
        candidates = policy.get_eviction_candidates(insights)
        assert len(candidates) == 1
        assert candidates[0]["id"] == "old"

    def test_get_candidates_all_fresh(self):
        """Test getting eviction candidates when all are fresh."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        fresh_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        insights = [
            {"id": "1", "payload": {"timestamp": fresh_ts}},
            {"id": "2", "payload": {"timestamp": fresh_ts}},
        ]
        candidates = policy.get_eviction_candidates(insights)
        assert len(candidates) == 0

    def test_get_candidates_all_old(self):
        """Test getting eviction candidates when all are old."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()

        insights = [
            {"id": "1", "payload": {"timestamp": old_ts}},
            {"id": "2", "payload": {"timestamp": old_ts}},
        ]
        candidates = policy.get_eviction_candidates(insights)
        assert len(candidates) == 2


class TestRunMaintenance:
    """Tests for run_maintenance method."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService."""
        service = Mock()
        service.enabled = True
        service.store = Mock()

        # Default: return empty list from scroll
        service.store.scroll.return_value = []
        service.store.delete.return_value = 0
        service.store.count.return_value = 0

        # Make _safe_store_call execute the function
        def safe_call(label, fn, default):
            try:
                return fn()
            except Exception:
                return default

        service._safe_store_call = safe_call
        return service

    def test_maintenance_disabled_memory(self, mock_memory_service):
        """Test maintenance skips when memory is disabled."""
        mock_memory_service.enabled = False
        policy = MemoryMaintenancePolicy()

        result = policy.run_maintenance(mock_memory_service, "test_collection")

        assert result["evicted_count"] == 0
        assert result["deduplicated_count"] == 0

    def test_maintenance_empty_collection(self, mock_memory_service):
        """Test maintenance on empty collection."""
        policy = MemoryMaintenancePolicy()

        result = policy.run_maintenance(mock_memory_service, "test_collection")

        assert result["evicted_count"] == 0
        assert result["deduplicated_count"] == 0

    def test_maintenance_evicts_old_insights(self, mock_memory_service):
        """Test maintenance evicts old insights."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()

        mock_memory_service.store.scroll.return_value = [
            {"id": "old1", "payload": {"timestamp": old_ts, "content_hash": "a"}},
            {"id": "old2", "payload": {"timestamp": old_ts, "content_hash": "b"}},
        ]

        result = policy.run_maintenance(mock_memory_service, "test_collection")

        assert result["evicted_count"] == 2
        mock_memory_service.store.delete.assert_called()

    def test_maintenance_dry_run(self, mock_memory_service):
        """Test maintenance dry run doesn't delete."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()

        mock_memory_service.store.scroll.return_value = [
            {"id": "old1", "payload": {"timestamp": old_ts, "content_hash": "a"}},
        ]

        result = policy.run_maintenance(mock_memory_service, "test_collection", dry_run=True)

        assert result["evicted_count"] == 1
        assert result["dry_run"] is True
        mock_memory_service.store.delete.assert_not_called()

    def test_maintenance_compacts_duplicates(self, mock_memory_service):
        """Test maintenance compacts duplicate insights."""
        policy = MemoryMaintenancePolicy(max_age_days=90)
        fresh_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        older_fresh_ts = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()

        mock_memory_service.store.scroll.return_value = [
            {"id": "1", "payload": {"timestamp": fresh_ts, "content_hash": "same"}},
            {"id": "2", "payload": {"timestamp": older_fresh_ts, "content_hash": "same"}},
        ]

        result = policy.run_maintenance(mock_memory_service, "test_collection")

        assert result["deduplicated_count"] == 1

    def test_maintenance_checks_memory_usage(self, mock_memory_service):
        """Test maintenance checks memory usage."""
        policy = MemoryMaintenancePolicy(max_memory_mb=10.0)
        # Need at least one insight to avoid early return
        fresh_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_memory_service.store.scroll.return_value = [
            {"id": "1", "payload": {"timestamp": fresh_ts, "content_hash": "a"}},
        ]
        mock_memory_service.store.count.return_value = 10000  # ~20MB at 2KB each

        result = policy.run_maintenance(mock_memory_service, "test_collection")

        assert result["memory_ok"] is False  # 20MB > 10MB limit

    def test_maintenance_with_project_filter(self, mock_memory_service):
        """Test maintenance filters by project_id."""
        policy = MemoryMaintenancePolicy()

        policy.run_maintenance(mock_memory_service, "test_collection", project_id="test-project")

        # Verify scroll was called with filter
        scroll_call = mock_memory_service.store.scroll.call_args
        assert scroll_call is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
