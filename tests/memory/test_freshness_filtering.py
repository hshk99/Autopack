"""Tests for freshness filtering in basic memory search methods (IMP-MEM-010).

Tests cover:
- _is_fresh function timestamp validation
- search_code with max_age_hours filtering
- search_errors with max_age_hours filtering
- search_summaries with max_age_hours filtering
- search_doctor_hints with max_age_hours filtering
- context_injector passing freshness thresholds to search methods
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from autopack.memory.memory_service import _is_fresh


class TestIsFreshFunction:
    """Tests for _is_fresh utility function."""

    def test_fresh_timestamp_within_threshold(self):
        """Timestamp within max_age_hours should be considered fresh."""
        # Create timestamp 1 hour ago
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert _is_fresh(one_hour_ago, max_age_hours=24) is True

    def test_stale_timestamp_beyond_threshold(self):
        """Timestamp beyond max_age_hours should not be considered fresh."""
        # Create timestamp 48 hours ago
        two_days_ago = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        assert _is_fresh(two_days_ago, max_age_hours=24) is False

    def test_timestamp_exactly_at_boundary(self):
        """Timestamp exactly at max_age_hours boundary should be fresh."""
        now = datetime.now(timezone.utc)
        exactly_24_hours_ago = (now - timedelta(hours=24)).isoformat()
        # Should be considered fresh (<=)
        assert _is_fresh(exactly_24_hours_ago, max_age_hours=24, now=now) is True

    def test_none_timestamp_not_fresh(self):
        """None timestamp should not be considered fresh."""
        assert _is_fresh(None, max_age_hours=24) is False

    def test_empty_timestamp_not_fresh(self):
        """Empty timestamp should not be considered fresh."""
        assert _is_fresh("", max_age_hours=24) is False

    def test_invalid_timestamp_not_fresh(self):
        """Invalid timestamp should not be considered fresh."""
        assert _is_fresh("not-a-timestamp", max_age_hours=24) is False

    def test_z_suffix_timestamp(self):
        """Timestamp with Z suffix should be parsed correctly."""
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert _is_fresh(one_hour_ago, max_age_hours=24) is True

    def test_168_hours_threshold(self):
        """Test 168 hours (7 days) threshold as used in context_injector."""
        # 6 days ago should be fresh
        six_days_ago = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
        assert _is_fresh(six_days_ago, max_age_hours=168) is True

        # 8 days ago should not be fresh
        eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        assert _is_fresh(eight_days_ago, max_age_hours=168) is False


class TestSearchMethodsFreshnessFiltering:
    """Tests for freshness filtering in search methods."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock memory service with search capabilities."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self: None):
            service = MemoryService()
            service.enabled = True
            service.top_k = 10
            service.store = Mock()
            service._retrieval_quality_tracker = None
            return service

    def test_search_errors_filters_stale_results(self, mock_memory_service):
        """search_errors should filter out stale results when max_age_hours provided."""
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(hours=12)).isoformat()
        stale_timestamp = (now - timedelta(hours=48)).isoformat()

        # Mock store.search to return mix of fresh and stale results
        mock_memory_service.store.search.return_value = [
            {"id": "fresh1", "score": 0.9, "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale1", "score": 0.85, "payload": {"timestamp": stale_timestamp}},
            {"id": "fresh2", "score": 0.8, "payload": {"timestamp": fresh_timestamp}},
        ]

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            results = mock_memory_service.search_errors(
                query="test error",
                project_id="test_project",
                limit=3,
                max_age_hours=24,  # 24 hours threshold
            )

        # Should only return fresh results
        assert len(results) == 2
        assert all(r["id"].startswith("fresh") for r in results)

    def test_search_errors_without_max_age_returns_all(self, mock_memory_service):
        """search_errors without max_age_hours should return all results."""
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(hours=12)).isoformat()
        stale_timestamp = (now - timedelta(hours=48)).isoformat()

        mock_memory_service.store.search.return_value = [
            {"id": "fresh1", "score": 0.9, "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale1", "score": 0.85, "payload": {"timestamp": stale_timestamp}},
        ]

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            results = mock_memory_service.search_errors(
                query="test error",
                project_id="test_project",
                limit=3,
            )

        # Should return all results (no filtering)
        assert len(results) == 2

    def test_search_summaries_filters_stale_results(self, mock_memory_service):
        """search_summaries should filter out stale results when max_age_hours provided."""
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(days=3)).isoformat()
        stale_timestamp = (now - timedelta(days=10)).isoformat()

        mock_memory_service.store.search.return_value = [
            {"id": "fresh1", "score": 0.9, "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale1", "score": 0.85, "payload": {"timestamp": stale_timestamp}},
        ]

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            results = mock_memory_service.search_summaries(
                query="test summary",
                project_id="test_project",
                limit=3,
                max_age_hours=168,  # 7 days
            )

        # Should only return fresh results
        assert len(results) == 1
        assert results[0]["id"] == "fresh1"

    def test_search_code_filters_stale_results(self, mock_memory_service):
        """search_code should filter out stale results when max_age_hours provided."""
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(hours=100)).isoformat()
        stale_timestamp = (now - timedelta(hours=200)).isoformat()

        mock_memory_service.store.search.return_value = [
            {"id": "fresh1", "score": 0.9, "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale1", "score": 0.85, "payload": {"timestamp": stale_timestamp}},
        ]

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            results = mock_memory_service.search_code(
                query="test code",
                project_id="test_project",
                limit=3,
                max_age_hours=168,  # 7 days
            )

        assert len(results) == 1
        assert results[0]["id"] == "fresh1"

    def test_search_doctor_hints_filters_stale_results(self, mock_memory_service):
        """search_doctor_hints should filter out stale results when max_age_hours provided."""
        now = datetime.now(timezone.utc)
        fresh_timestamp = (now - timedelta(days=5)).isoformat()
        stale_timestamp = (now - timedelta(days=14)).isoformat()

        mock_memory_service.store.search.return_value = [
            {"id": "fresh1", "score": 0.9, "payload": {"timestamp": fresh_timestamp}},
            {"id": "stale1", "score": 0.85, "payload": {"timestamp": stale_timestamp}},
        ]

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            results = mock_memory_service.search_doctor_hints(
                query="test hint",
                project_id="test_project",
                limit=3,
                max_age_hours=168,  # 7 days
            )

        assert len(results) == 1
        assert results[0]["id"] == "fresh1"

    def test_overfetch_when_filtering(self, mock_memory_service):
        """Search methods should over-fetch (2x limit) when filtering is enabled."""
        mock_memory_service.store.search.return_value = []

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            mock_memory_service.search_errors(
                query="test",
                project_id="test_project",
                limit=5,
                max_age_hours=24,
            )

        # Should fetch 10 (2 * 5) when filtering is enabled
        call_args = mock_memory_service.store.search.call_args
        assert call_args.kwargs.get("limit") == 10 or call_args[1].get("limit") == 10

    def test_no_overfetch_when_not_filtering(self, mock_memory_service):
        """Search methods should not over-fetch when filtering is not enabled."""
        mock_memory_service.store.search.return_value = []

        with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.1] * 384):
            mock_memory_service.search_errors(
                query="test",
                project_id="test_project",
                limit=5,
            )

        # Should fetch 5 when filtering is not enabled
        call_args = mock_memory_service.store.search.call_args
        assert call_args.kwargs.get("limit") == 5 or call_args[1].get("limit") == 5


class TestContextInjectorFreshnessThresholds:
    """Tests for context_injector passing freshness thresholds."""

    def test_get_context_for_phase_passes_freshness_to_search_errors(self):
        """get_context_for_phase should pass max_age_hours=168 to search_errors."""
        from autopack.memory.context_injector import ContextInjector

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        with patch("autopack.roadc.discovery_context_merger.DiscoveryContextMerger") as mock_merger:
            mock_merger.return_value.merge_sources.return_value = []
            mock_merger.return_value.rank_by_relevance.return_value = []

            injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix tests",
                project_id="test_project",
            )

        # Verify search_errors was called with max_age_hours=168
        mock_memory.search_errors.assert_called_once()
        call_kwargs = mock_memory.search_errors.call_args.kwargs
        assert call_kwargs.get("max_age_hours") == 168

    def test_get_context_for_phase_passes_freshness_to_search_summaries(self):
        """get_context_for_phase should pass max_age_hours=168 to search_summaries."""
        from autopack.memory.context_injector import ContextInjector

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        with patch("autopack.roadc.discovery_context_merger.DiscoveryContextMerger") as mock_merger:
            mock_merger.return_value.merge_sources.return_value = []
            mock_merger.return_value.rank_by_relevance.return_value = []

            injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix tests",
                project_id="test_project",
            )

        # Verify search_summaries was called with max_age_hours=168
        mock_memory.search_summaries.assert_called_once()
        call_kwargs = mock_memory.search_summaries.call_args.kwargs
        assert call_kwargs.get("max_age_hours") == 168

    def test_get_context_for_phase_passes_freshness_to_search_doctor_hints(self):
        """get_context_for_phase should pass max_age_hours=168 to search_doctor_hints."""
        from autopack.memory.context_injector import ContextInjector

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        with patch("autopack.roadc.discovery_context_merger.DiscoveryContextMerger") as mock_merger:
            mock_merger.return_value.merge_sources.return_value = []
            mock_merger.return_value.rank_by_relevance.return_value = []

            injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix tests",
                project_id="test_project",
            )

        # Verify search_doctor_hints was called with max_age_hours=168
        mock_memory.search_doctor_hints.assert_called_once()
        call_kwargs = mock_memory.search_doctor_hints.call_args.kwargs
        assert call_kwargs.get("max_age_hours") == 168

    def test_get_context_for_phase_passes_freshness_to_search_code(self):
        """get_context_for_phase should pass max_age_hours=168 to search_code."""
        from autopack.memory.context_injector import ContextInjector

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        with patch("autopack.roadc.discovery_context_merger.DiscoveryContextMerger") as mock_merger:
            mock_merger.return_value.merge_sources.return_value = []
            mock_merger.return_value.rank_by_relevance.return_value = []

            injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix tests",
                project_id="test_project",
            )

        # Verify search_code was called with max_age_hours=168
        mock_memory.search_code.assert_called_once()
        call_kwargs = mock_memory.search_code.call_args.kwargs
        assert call_kwargs.get("max_age_hours") == 168
