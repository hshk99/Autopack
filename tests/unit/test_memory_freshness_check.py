"""Unit tests for IMP-LOOP-003: Memory Retrieval Freshness Check.
Also includes IMP-LOOP-019: Context Relevance/Confidence Metadata tests.

Tests the freshness validation logic added to memory retrieval
for task generation, ensuring only recent and relevant memories are used.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from autopack.memory.memory_service import (  # IMP-LOOP-019: New imports
    DEFAULT_MEMORY_FRESHNESS_HOURS,
    LOW_CONFIDENCE_THRESHOLD,
    ContextMetadata,
    MemoryService,
    _calculate_age_hours,
    _calculate_confidence,
    _enrich_with_metadata,
    _is_fresh,
    _parse_timestamp,
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

    def test_zero_max_age_uses_default(self):
        """Test that max_age_hours=0 uses default (IMP-LOOP-014: no bypass allowed)."""
        now = datetime.now(timezone.utc)
        # Old timestamp beyond default threshold
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old
        # IMP-LOOP-014: Zero max_age should use DEFAULT and filter stale data
        assert _is_fresh(old_ts, max_age_hours=0, now=now) is False

    def test_negative_max_age_uses_default(self):
        """Test that negative max_age_hours uses default (IMP-LOOP-014: no bypass allowed)."""
        now = datetime.now(timezone.utc)
        # Old timestamp beyond default threshold
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old
        # IMP-LOOP-014: Negative max_age should use DEFAULT and filter stale data
        assert _is_fresh(old_ts, max_age_hours=-1, now=now) is False

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

    def test_retrieve_insights_zero_max_age_uses_default_with_warning(
        self, mock_memory_service, caplog
    ):
        """Test that max_age_hours=0 is ignored with warning (IMP-LOOP-014)."""
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old - beyond default threshold

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

        import logging

        with caplog.at_level(logging.WARNING):
            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 384,
            ):
                insights = mock_memory_service.retrieve_insights(
                    query="test query",
                    limit=10,
                    max_age_hours=0,  # Try to disable filtering
                )

        # IMP-LOOP-014: Should filter old insight since bypass is not allowed
        assert len(insights) == 0
        # Should log a warning about the override being ignored
        assert any("IMP-LOOP-014" in record.message for record in caplog.records)
        assert any("invalid" in record.message.lower() for record in caplog.records)

    def test_retrieve_insights_negative_max_age_uses_default_with_warning(
        self, mock_memory_service, caplog
    ):
        """Test that negative max_age_hours is ignored with warning (IMP-LOOP-014)."""
        old_ts = "2020-01-01T00:00:00+00:00"  # Very old - beyond default threshold

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

        import logging

        with caplog.at_level(logging.WARNING):
            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 384,
            ):
                insights = mock_memory_service.retrieve_insights(
                    query="test query",
                    limit=10,
                    max_age_hours=-5,  # Try to disable filtering with negative
                )

        # IMP-LOOP-014: Should filter old insight since bypass is not allowed
        assert len(insights) == 0
        # Should log a warning about the override being ignored
        assert any("IMP-LOOP-014" in record.message for record in caplog.records)

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

    def test_retrieve_insights_logs_audit_trail(self, mock_memory_service, caplog):
        """Test that retrieve_insights logs audit trail for freshness filter (IMP-LOOP-014)."""
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

        import logging

        with caplog.at_level(logging.INFO):
            with patch(
                "autopack.memory.memory_service.sync_embed_text",
                return_value=[0.1] * 384,
            ):
                insights = mock_memory_service.retrieve_insights(
                    query="test query",
                    limit=10,
                    max_age_hours=48,
                    project_id="test-project",
                )

        assert len(insights) == 1
        # IMP-LOOP-014: Should log audit trail with freshness filter info
        audit_logs = [r for r in caplog.records if "IMP-LOOP-014" in r.message]
        assert len(audit_logs) >= 1
        audit_message = audit_logs[0].message
        assert "freshness_filter=48" in audit_message
        assert "project_id=test-project" in audit_message


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
            generator._telemetry_analyzer = None
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


# ---------------------------------------------------------------------------
# IMP-LOOP-019: Context Relevance/Confidence Metadata Tests
# ---------------------------------------------------------------------------


class TestCalculateAgeHours:
    """Tests for _calculate_age_hours helper function."""

    def test_calculate_age_hours_valid_timestamp(self):
        """Test age calculation for valid timestamp."""
        now = datetime.now(timezone.utc)
        past = (now - timedelta(hours=10)).isoformat()

        age = _calculate_age_hours(past, now)
        assert 9.9 < age < 10.1  # Allow small margin

    def test_calculate_age_hours_future_timestamp(self):
        """Test age calculation for future timestamp returns 0."""
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=10)).isoformat()

        age = _calculate_age_hours(future, now)
        assert age == 0.0

    def test_calculate_age_hours_invalid_timestamp(self):
        """Test age calculation for invalid timestamp returns -1."""
        age = _calculate_age_hours("not-a-timestamp")
        assert age == -1.0

    def test_calculate_age_hours_none_timestamp(self):
        """Test age calculation for None timestamp returns -1."""
        age = _calculate_age_hours(None)
        assert age == -1.0


class TestCalculateConfidence:
    """Tests for _calculate_confidence helper function."""

    def test_calculate_confidence_high_relevance_fresh(self):
        """Test confidence for high relevance, fresh content."""
        confidence = _calculate_confidence(relevance_score=0.9, age_hours=5.0)
        # 0.7 * 0.9 + 0.3 * 1.0 = 0.63 + 0.30 = 0.93
        assert confidence >= 0.9

    def test_calculate_confidence_high_relevance_stale(self):
        """Test confidence for high relevance, stale content."""
        confidence = _calculate_confidence(relevance_score=0.9, age_hours=200.0)
        # age_factor should be 0.5 for stale content
        # 0.7 * 0.9 + 0.3 * 0.5 = 0.63 + 0.15 = 0.78
        assert 0.75 < confidence < 0.85

    def test_calculate_confidence_low_relevance_fresh(self):
        """Test confidence for low relevance, fresh content."""
        confidence = _calculate_confidence(relevance_score=0.2, age_hours=5.0)
        # 0.7 * 0.2 + 0.3 * 1.0 = 0.14 + 0.30 = 0.44
        assert 0.4 < confidence < 0.5

    def test_calculate_confidence_unknown_age(self):
        """Test confidence with unknown age (-1)."""
        confidence = _calculate_confidence(relevance_score=0.8, age_hours=-1.0)
        # age_factor = 0.5 for unknown
        # 0.7 * 0.8 + 0.3 * 0.5 = 0.56 + 0.15 = 0.71
        assert 0.65 < confidence < 0.75

    def test_calculate_confidence_clamps_to_range(self):
        """Test confidence is clamped to 0-1 range."""
        # Very high relevance (above 1.0)
        confidence = _calculate_confidence(relevance_score=1.5, age_hours=0.0)
        assert confidence <= 1.0

        # Negative relevance (shouldn't happen but test edge case)
        confidence = _calculate_confidence(relevance_score=-0.5, age_hours=0.0)
        assert confidence >= 0.0


class TestEnrichWithMetadata:
    """Tests for _enrich_with_metadata helper function."""

    def test_enrich_with_metadata_basic(self):
        """Test basic enrichment of a search result."""
        now = datetime.now(timezone.utc)
        past = (now - timedelta(hours=10)).isoformat()

        result = {
            "id": "error:123",
            "score": 0.85,
            "payload": {
                "type": "error",
                "error_text": "ImportError: No module named 'foo'",
                "timestamp": past,
            },
        }

        metadata = _enrich_with_metadata(result, "error", "error_text", now)

        assert isinstance(metadata, ContextMetadata)
        assert metadata.content == "ImportError: No module named 'foo'"
        assert metadata.relevance_score == 0.85
        assert 9.9 < metadata.age_hours < 10.1
        assert metadata.source_type == "error"
        assert metadata.source_id == "error:123"

    def test_enrich_with_metadata_low_confidence(self):
        """Test that low confidence is flagged correctly."""
        now = datetime.now(timezone.utc)
        past = (now - timedelta(hours=200)).isoformat()

        result = {
            "id": "old:1",
            "score": 0.2,  # Low relevance
            "payload": {
                "type": "error",
                "content": "Old error",
                "timestamp": past,  # Old
            },
        }

        metadata = _enrich_with_metadata(result, "error", "content", now)

        assert metadata.is_low_confidence is True
        assert metadata.confidence < LOW_CONFIDENCE_THRESHOLD

    def test_enrich_with_metadata_missing_timestamp(self):
        """Test enrichment with missing timestamp."""
        result = {
            "id": "no-ts:1",
            "score": 0.9,
            "payload": {
                "type": "error",
                "content": "Error without timestamp",
                # No timestamp
            },
        }

        metadata = _enrich_with_metadata(result, "error")

        assert metadata.age_hours == -1.0  # Unknown age
        assert metadata.content == "Error without timestamp"

    def test_enrich_with_metadata_fallback_content_key(self):
        """Test that enrichment falls back to other content keys."""
        result = {
            "id": "fallback:1",
            "score": 0.8,
            "payload": {
                "summary": "This is a summary",  # Not the specified key
            },
        }

        metadata = _enrich_with_metadata(result, "summary", "description")

        assert metadata.content == "This is a summary"


class TestContextMetadataDataclass:
    """Tests for ContextMetadata dataclass."""

    def test_context_metadata_confidence_level_high(self):
        """Test confidence_level property for high confidence."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.75,
            is_low_confidence=False,
        )
        assert metadata.confidence_level == "high"

    def test_context_metadata_confidence_level_medium(self):
        """Test confidence_level property for medium confidence."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.5,
            age_hours=100.0,
            confidence=0.45,
            is_low_confidence=False,
        )
        assert metadata.confidence_level == "medium"

    def test_context_metadata_confidence_level_low(self):
        """Test confidence_level property for low confidence."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.2,
            is_low_confidence=True,
        )
        assert metadata.confidence_level == "low"


class TestMemoryServiceRetrieveContextWithMetadata:
    """Tests for MemoryService.retrieve_context_with_metadata method."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService for testing."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service.store = Mock()
            service.top_k = 5
            return service

    def test_retrieve_context_with_metadata_returns_dict(self, mock_memory_service):
        """Test that retrieve_context_with_metadata returns proper structure."""
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_errors = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        assert isinstance(result, dict)
        assert "code" in result
        assert "summaries" in result
        assert "errors" in result
        assert "hints" in result

    def test_retrieve_context_with_metadata_disabled_memory(self, mock_memory_service):
        """Test that disabled memory returns empty result."""
        mock_memory_service.enabled = False

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        assert result["code"] == []
        assert result["errors"] == []

    def test_retrieve_context_with_metadata_enriches_results(self, mock_memory_service):
        """Test that results are enriched with metadata."""
        now = datetime.now(timezone.utc)
        past = (now - timedelta(hours=5)).isoformat()

        mock_memory_service.search_errors = Mock(
            return_value=[
                {
                    "id": "error:1",
                    "score": 0.9,
                    "payload": {
                        "type": "error",
                        "error_text": "Test error",
                        "timestamp": past,
                    },
                }
            ]
        )
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        assert len(result["errors"]) == 1
        assert isinstance(result["errors"][0], ContextMetadata)
        assert result["errors"][0].content == "Test error"
        assert result["errors"][0].relevance_score == 0.9


class TestMemoryServiceGetContextQualitySummary:
    """Tests for MemoryService.get_context_quality_summary method."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService for testing."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            return service

    def test_get_context_quality_summary_empty(self, mock_memory_service):
        """Test quality summary for empty context."""
        result = mock_memory_service.get_context_quality_summary(
            {
                "code": [],
                "errors": [],
            }
        )

        assert result["total_items"] == 0
        assert result["low_confidence_count"] == 0
        assert result["avg_confidence"] == 0.0

    def test_get_context_quality_summary_with_items(self, mock_memory_service):
        """Test quality summary with items."""
        high_conf = ContextMetadata(
            content="c1",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        low_conf = ContextMetadata(
            content="c2",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.2,
            is_low_confidence=True,
        )

        result = mock_memory_service.get_context_quality_summary(
            {
                "errors": [high_conf, low_conf],
                "code": [],
            }
        )

        assert result["total_items"] == 2
        assert result["low_confidence_count"] == 1
        assert result["avg_confidence"] == 0.5  # (0.8 + 0.2) / 2

    def test_get_context_quality_summary_warning_threshold(self, mock_memory_service):
        """Test quality summary warning when > 50% items are low confidence."""
        low_conf1 = ContextMetadata(
            content="c1",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.2,
            is_low_confidence=True,
        )
        low_conf2 = ContextMetadata(
            content="c2",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.25,
            is_low_confidence=True,
        )
        high_conf = ContextMetadata(
            content="c3",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )

        # 2/3 items are low confidence (> 50%)
        result = mock_memory_service.get_context_quality_summary(
            {
                "errors": [low_conf1, low_conf2, high_conf],
            }
        )

        assert result["has_low_confidence_warning"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
