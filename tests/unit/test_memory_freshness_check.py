"""Unit tests for IMP-LOOP-003: Memory Retrieval Freshness Check.

Tests the freshness validation logic added to memory retrieval
for task generation, ensuring only recent and relevant memories are used.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from autopack.memory.memory_service import (
    MemoryService,
    DEFAULT_MEMORY_FRESHNESS_HOURS,
    _parse_timestamp,
    _is_fresh,
)


class TestTimestampParsing:
    """Tests for _parse_timestamp helper function."""

    def test_parse_valid_iso_timestamp(self):
        """Test parsing valid ISO format timestamp."""
        ts = "2024-01-15T10:30:00+00:00"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_timestamp_with_z_suffix(self):
        """Test parsing timestamp with Z suffix (UTC)."""
        ts = "2024-01-15T10:30:00Z"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_timestamp_without_timezone(self):
        """Test parsing timestamp without timezone."""
        ts = "2024-01-15T10:30:00"
        result = _parse_timestamp(ts)
        assert result is not None
        assert result.year == 2024

    def test_parse_empty_timestamp(self):
        """Test parsing empty timestamp returns None."""
        assert _parse_timestamp(None) is None
        assert _parse_timestamp("") is None

    def test_parse_invalid_timestamp(self):
        """Test parsing invalid timestamp returns None."""
        assert _parse_timestamp("not-a-timestamp") is None
        assert _parse_timestamp("2024-99-99T99:99:99") is None


class TestFreshnessCheck:
    """Tests for _is_fresh helper function."""

    def test_fresh_timestamp_within_threshold(self):
        """Test that recent timestamp is considered fresh."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=1)).isoformat()
        assert _is_fresh(recent_ts, max_age_hours=24, now=now) is True

    def test_stale_timestamp_beyond_threshold(self):
        """Test that old timestamp is considered stale."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=48)).isoformat()
        assert _is_fresh(old_ts, max_age_hours=24, now=now) is False

    def test_timestamp_at_exact_threshold(self):
        """Test timestamp at exactly the threshold is still fresh."""
        now = datetime.now(timezone.utc)
        edge_ts = (now - timedelta(hours=24)).isoformat()
        assert _is_fresh(edge_ts, max_age_hours=24, now=now) is True

    def test_zero_max_age_disables_check(self):
        """Test that max_age_hours=0 disables freshness check."""
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old
        assert _is_fresh(old_ts, max_age_hours=0) is True

    def test_negative_max_age_disables_check(self):
        """Test that negative max_age_hours disables freshness check."""
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old
        assert _is_fresh(old_ts, max_age_hours=-1) is True

    def test_invalid_timestamp_not_fresh(self):
        """Test that invalid timestamp is not considered fresh."""
        assert _is_fresh("invalid", max_age_hours=24) is False
        assert _is_fresh(None, max_age_hours=24) is False

    def test_default_freshness_constant(self):
        """Test default freshness hours constant is defined."""
        assert DEFAULT_MEMORY_FRESHNESS_HOURS == 72  # 3 days


class TestMemoryServiceFreshnessFiltering:
    """Tests for freshness filtering in MemoryService.retrieve_insights."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService for testing."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service.store = Mock()
            service.top_k = 5
            return service

    def test_retrieve_insights_filters_stale_data(self, mock_memory_service):
        """Test that retrieve_insights filters out stale insights."""
        now = datetime.now(timezone.utc)
        fresh_ts = (now - timedelta(hours=1)).isoformat()
        stale_ts = (now - timedelta(hours=100)).isoformat()

        # Track which collection we're querying
        call_count = [0]

        def mock_search_side_effect(collection, query_vector, filter, limit):
            call_count[0] += 1
            # Only return results for the first collection
            if call_count[0] == 1:
                return [
                    Mock(
                        id="fresh-1",
                        score=0.9,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": fresh_ts,
                            "summary": "Fresh insight",
                        },
                    ),
                    Mock(
                        id="stale-1",
                        score=0.8,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": stale_ts,
                            "summary": "Stale insight",
                        },
                    ),
                ]
            return []

        mock_memory_service.store.search = Mock(side_effect=mock_search_side_effect)
        mock_memory_service._safe_store_call = lambda label, fn, default: fn()

        with patch(
            "autopack.memory.memory_service.sync_embed_text",
            return_value=[0.1] * 384,
        ):
            insights = mock_memory_service.retrieve_insights(
                query="test query",
                limit=10,
                max_age_hours=72,
            )

        # Should only include fresh insights
        assert len(insights) == 1
        assert insights[0]["id"] == "fresh-1"

    def test_retrieve_insights_uses_default_max_age(self, mock_memory_service):
        """Test that retrieve_insights uses DEFAULT_MEMORY_FRESHNESS_HOURS when not specified."""
        now = datetime.now(timezone.utc)
        # Just within default threshold (72 hours)
        within_default_ts = (now - timedelta(hours=70)).isoformat()
        # Just outside default threshold
        outside_default_ts = (now - timedelta(hours=75)).isoformat()

        call_count = [0]

        def mock_search_side_effect(collection, query_vector, filter, limit):
            call_count[0] += 1
            if call_count[0] == 1:
                return [
                    Mock(
                        id="within-default",
                        score=0.9,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": within_default_ts,
                            "summary": "Within default",
                        },
                    ),
                    Mock(
                        id="outside-default",
                        score=0.8,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": outside_default_ts,
                            "summary": "Outside default",
                        },
                    ),
                ]
            return []

        mock_memory_service.store.search = Mock(side_effect=mock_search_side_effect)
        mock_memory_service._safe_store_call = lambda label, fn, default: fn()

        with patch(
            "autopack.memory.memory_service.sync_embed_text",
            return_value=[0.1] * 384,
        ):
            # Don't specify max_age_hours - should use default
            insights = mock_memory_service.retrieve_insights(
                query="test query",
                limit=10,
            )

        # Should only include insight within default threshold
        assert len(insights) == 1
        assert insights[0]["id"] == "within-default"

    def test_retrieve_insights_zero_max_age_disables_filtering(self, mock_memory_service):
        """Test that max_age_hours=0 disables freshness filtering."""
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old

        call_count = [0]

        def mock_search_side_effect(collection, query_vector, filter, limit):
            call_count[0] += 1
            if call_count[0] == 1:
                return [
                    Mock(
                        id="old-insight",
                        score=0.9,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": old_ts,
                            "summary": "Very old insight",
                        },
                    ),
                ]
            return []

        mock_memory_service.store.search = Mock(side_effect=mock_search_side_effect)
        mock_memory_service._safe_store_call = lambda label, fn, default: fn()

        with patch(
            "autopack.memory.memory_service.sync_embed_text",
            return_value=[0.1] * 384,
        ):
            insights = mock_memory_service.retrieve_insights(
                query="test query",
                limit=10,
                max_age_hours=0,  # Disable filtering
            )

        # Should include old insight since filtering is disabled
        assert len(insights) == 1
        assert insights[0]["id"] == "old-insight"

    def test_retrieve_insights_includes_timestamp_in_result(self, mock_memory_service):
        """Test that retrieved insights include timestamp field."""
        now = datetime.now(timezone.utc)
        fresh_ts = (now - timedelta(hours=1)).isoformat()

        call_count = [0]

        def mock_search_side_effect(collection, query_vector, filter, limit):
            call_count[0] += 1
            if call_count[0] == 1:
                return [
                    Mock(
                        id="insight-1",
                        score=0.9,
                        payload={
                            "task_type": "telemetry_insight",
                            "timestamp": fresh_ts,
                            "summary": "Test insight",
                        },
                    ),
                ]
            return []

        mock_memory_service.store.search = Mock(side_effect=mock_search_side_effect)
        mock_memory_service._safe_store_call = lambda label, fn, default: fn()

        with patch(
            "autopack.memory.memory_service.sync_embed_text",
            return_value=[0.1] * 384,
        ):
            insights = mock_memory_service.retrieve_insights(
                query="test query",
                limit=10,
                max_age_hours=24,
            )

        assert len(insights) == 1
        assert "timestamp" in insights[0]
        assert insights[0]["timestamp"] == fresh_ts

    def test_retrieve_insights_disabled_memory(self, mock_memory_service):
        """Test that disabled memory service returns empty list."""
        mock_memory_service.enabled = False

        insights = mock_memory_service.retrieve_insights(
            query="test query",
            limit=10,
            max_age_hours=24,
        )

        assert insights == []


class TestTaskGeneratorFreshnessIntegration:
    """Tests for freshness check integration in AutonomousTaskGenerator."""

    @pytest.fixture
    def mock_task_generator(self):
        """Create a mock AutonomousTaskGenerator for testing."""
        from autopack.roadc.task_generator import AutonomousTaskGenerator

        with patch.object(AutonomousTaskGenerator, "__init__", lambda self, **kwargs: None):
            generator = AutonomousTaskGenerator()
            generator._memory = Mock()
            generator._regression = Mock()
            generator._regression.check_protection = Mock(return_value=Mock(is_protected=True))
            return generator

    def test_generate_tasks_passes_max_age_hours(self, mock_task_generator):
        """Test that generate_tasks passes max_age_hours to retrieve_insights."""
        mock_task_generator._memory.retrieve_insights = Mock(return_value=[])

        with patch("autopack.roadc.task_generator._emit_task_generation_event"):
            mock_task_generator.generate_tasks(
                max_tasks=5,
                max_age_hours=48,
            )

        mock_task_generator._memory.retrieve_insights.assert_called_once()
        call_kwargs = mock_task_generator._memory.retrieve_insights.call_args[1]
        assert call_kwargs["max_age_hours"] == 48

    def test_generate_tasks_uses_default_freshness(self, mock_task_generator):
        """Test that generate_tasks uses default freshness when not specified."""
        mock_task_generator._memory.retrieve_insights = Mock(return_value=[])

        with patch("autopack.roadc.task_generator._emit_task_generation_event"):
            mock_task_generator.generate_tasks(max_tasks=5)

        mock_task_generator._memory.retrieve_insights.assert_called_once()
        call_kwargs = mock_task_generator._memory.retrieve_insights.call_args[1]
        assert call_kwargs["max_age_hours"] == DEFAULT_MEMORY_FRESHNESS_HOURS

    def test_generate_tasks_skips_freshness_for_direct_telemetry(self, mock_task_generator):
        """Test that freshness check is skipped when using direct telemetry."""
        from autopack.telemetry.analyzer import RankedIssue

        telemetry_data = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="test-phase",
                    phase_type="implementation",
                    metric_value=10000.0,
                    details={},
                )
            ],
            "top_failure_modes": [],
            "top_retry_causes": [],
        }

        with patch("autopack.roadc.task_generator._emit_task_generation_event"):
            result = mock_task_generator.generate_tasks(
                max_tasks=5,
                telemetry_insights=telemetry_data,
                max_age_hours=48,  # Should be ignored for direct telemetry
            )

        # Should not call retrieve_insights when using direct telemetry
        mock_task_generator._memory.retrieve_insights.assert_not_called()
        assert result.insights_processed == 1  # One cost sink converted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
