"""Tests for content-based semantic deduplication in memory service.

IMP-MEM-006: Tests for semantic similarity-based insight deduplication.

Tests cover:
- _find_similar_insights: Finding semantically similar insights using embeddings
- _merge_insights: Merging duplicate insights with updated metadata
- Integration: write_telemetry_insight detecting and merging similar insights
"""

import threading
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from autopack.memory.deduplication import ContentDeduplicator


class TestFindSimilarInsights:
    """Tests for _find_similar_insights method."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service._deduplicator = ContentDeduplicator()
            service.store = Mock()

            # Configure store.search to return empty by default
            service.store.search = Mock(return_value=[])

            yield service

    def test_find_similar_returns_empty_when_disabled(self, memory_service):
        """Should return empty list when memory service is disabled."""
        memory_service.enabled = False

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}
        )

        assert result == []

    def test_find_similar_returns_empty_for_empty_content(self, memory_service):
        """Should return empty list for insights with no content."""
        result = memory_service._find_similar_insights(
            {"insight_type": "", "description": "", "content": ""}
        )

        assert result == []

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_searches_correct_collection_for_cost_sink(
        self, mock_embed, memory_service
    ):
        """cost_sink insights should search run_summaries collection."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = []

        memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "High cost API call"}
        )

        # Verify search was called on run_summaries collection
        call_args = memory_service.store.search.call_args
        assert call_args is not None
        assert call_args[0][0] == "run_summaries"

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_searches_correct_collection_for_failure_mode(
        self, mock_embed, memory_service
    ):
        """failure_mode insights should search errors_ci collection."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = []

        memory_service._find_similar_insights(
            {"insight_type": "failure_mode", "description": "Test failure"}
        )

        call_args = memory_service.store.search.call_args
        assert call_args is not None
        assert call_args[0][0] == "errors_ci"

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_searches_correct_collection_for_retry_cause(
        self, mock_embed, memory_service
    ):
        """retry_cause insights should search doctor_hints collection."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = []

        memory_service._find_similar_insights(
            {"insight_type": "retry_cause", "description": "Network timeout"}
        )

        call_args = memory_service.store.search.call_args
        assert call_args is not None
        assert call_args[0][0] == "doctor_hints"

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_filters_by_threshold(self, mock_embed, memory_service):
        """Should only return insights above similarity threshold."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {"id": "id_1", "score": 0.95, "payload": {"description": "High match"}},
            {"id": "id_2", "score": 0.85, "payload": {"description": "Low match"}},
            {"id": "id_3", "score": 0.92, "payload": {"description": "Medium match"}},
        ]

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}, threshold=0.9
        )

        # Only entries with score >= 0.9 should be returned
        assert len(result) == 2
        assert result[0]["id"] == "id_1"  # Highest score first
        assert result[1]["id"] == "id_3"

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_returns_sorted_by_score(self, mock_embed, memory_service):
        """Results should be sorted by similarity score descending."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {"id": "id_1", "score": 0.91, "payload": {}},
            {"id": "id_2", "score": 0.99, "payload": {}},
            {"id": "id_3", "score": 0.95, "payload": {}},
        ]

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}, threshold=0.9
        )

        assert len(result) == 3
        assert result[0]["id"] == "id_2"  # 0.99
        assert result[1]["id"] == "id_3"  # 0.95
        assert result[2]["id"] == "id_1"  # 0.91

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_find_similar_handles_search_error(self, mock_embed, memory_service):
        """Should return empty list on search error."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.side_effect = Exception("Search failed")

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}
        )

        assert result == []


class TestMergeInsights:
    """Tests for _merge_insights method."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked store."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service._deduplicator = ContentDeduplicator()
            service.store = Mock()
            service.store.update_payload = Mock(return_value=True)

            yield service

    def test_merge_returns_empty_when_disabled(self, memory_service):
        """Should return empty string when memory service is disabled."""
        memory_service.enabled = False

        result = memory_service._merge_insights(
            {"id": "test_id", "payload": {}, "collection": "run_summaries"},
            {"insight_type": "cost_sink", "description": "Test"},
        )

        assert result == ""

    def test_merge_returns_empty_when_missing_id(self, memory_service):
        """Should return empty string when existing insight has no ID."""
        result = memory_service._merge_insights(
            {"payload": {}, "collection": "run_summaries"},
            {"insight_type": "cost_sink", "description": "Test"},
        )

        assert result == ""

    def test_merge_increments_occurrence_count(self, memory_service):
        """Merge should increment occurrence count."""
        existing = {
            "id": "test_id",
            "payload": {"occurrence_count": 3},
            "collection": "run_summaries",
        }

        result = memory_service._merge_insights(
            existing, {"insight_type": "cost_sink", "description": "Test"}
        )

        assert result == "test_id"
        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert updated_payload["occurrence_count"] == 4

    def test_merge_starts_occurrence_count_at_2(self, memory_service):
        """First merge should set occurrence count to 2."""
        existing = {
            "id": "test_id",
            "payload": {},  # No occurrence_count yet
            "collection": "run_summaries",
        }

        result = memory_service._merge_insights(
            existing, {"insight_type": "cost_sink", "description": "Test"}
        )

        assert result == "test_id"
        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert updated_payload["occurrence_count"] == 2

    def test_merge_keeps_highest_confidence(self, memory_service):
        """Merge should keep the highest confidence value."""
        existing = {
            "id": "test_id",
            "payload": {"confidence": 0.7},
            "collection": "run_summaries",
        }

        memory_service._merge_insights(
            existing,
            {"insight_type": "cost_sink", "description": "Test", "confidence": 0.9},
        )

        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert updated_payload["confidence"] == 0.9

    def test_merge_keeps_existing_confidence_if_higher(self, memory_service):
        """Merge should keep existing confidence if it's higher."""
        existing = {
            "id": "test_id",
            "payload": {"confidence": 0.95},
            "collection": "run_summaries",
        }

        memory_service._merge_insights(
            existing,
            {"insight_type": "cost_sink", "description": "Test", "confidence": 0.6},
        )

        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert updated_payload["confidence"] == 0.95

    def test_merge_updates_timestamp(self, memory_service):
        """Merge should update last_occurrence timestamp."""
        existing = {
            "id": "test_id",
            "payload": {"last_occurrence": "2024-01-01T00:00:00+00:00"},
            "collection": "run_summaries",
        }

        memory_service._merge_insights(
            existing, {"insight_type": "cost_sink", "description": "Test"}
        )

        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]

        # Should have a recent timestamp
        assert "last_occurrence" in updated_payload
        parsed = datetime.fromisoformat(updated_payload["last_occurrence"])
        assert parsed.year >= 2024

    def test_merge_increments_merge_count(self, memory_service):
        """Merge should track number of merges."""
        existing = {
            "id": "test_id",
            "payload": {"merge_count": 5},
            "collection": "run_summaries",
        }

        memory_service._merge_insights(
            existing, {"insight_type": "cost_sink", "description": "Test"}
        )

        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert updated_payload["merge_count"] == 6

    def test_merge_collects_suggested_actions(self, memory_service):
        """Merge should collect multiple suggested actions."""
        existing = {
            "id": "test_id",
            "payload": {"suggested_action": "Action 1"},
            "collection": "run_summaries",
        }

        memory_service._merge_insights(
            existing,
            {
                "insight_type": "cost_sink",
                "description": "Test",
                "suggested_action": "Action 2",
            },
        )

        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]
        assert "suggested_actions" in updated_payload
        assert "Action 2" in updated_payload["suggested_actions"]

    def test_merge_returns_empty_on_update_failure(self, memory_service):
        """Should return empty string if update fails."""
        memory_service.store.update_payload = Mock(return_value=False)

        result = memory_service._merge_insights(
            {"id": "test_id", "payload": {}, "collection": "run_summaries"},
            {"insight_type": "cost_sink", "description": "Test"},
        )

        assert result == ""


class TestWriteTelemetryInsightDeduplication:
    """Integration tests for deduplication in write_telemetry_insight."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance with mocked dependencies."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service._deduplicator = ContentDeduplicator()
            service.store = Mock()
            service.store.search = Mock(return_value=[])
            service.store.update_payload = Mock(return_value=True)

            # Mock the write methods
            service.write_phase_summary = Mock(return_value="new_id_1")
            service.write_error = Mock(return_value="new_id_2")
            service.write_doctor_hint = Mock(return_value="new_id_3")

            yield service

    @patch("autopack.memory.memory_service.sync_embed_text")
    @patch("autopack.memory.memory_service.TelemetryFeedbackValidator")
    def test_new_insight_stored_when_no_similar(self, mock_validator, mock_embed, memory_service):
        """New insights should be stored when no similar ones exist."""
        mock_validator.validate_insight.return_value = (True, [])
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = []

        result = memory_service.write_telemetry_insight(
            {"insight_type": "cost_sink", "description": "New unique insight"}
        )

        assert result == "new_id_1"
        memory_service.write_phase_summary.assert_called_once()

    @patch("autopack.memory.memory_service.sync_embed_text")
    @patch("autopack.memory.memory_service.TelemetryFeedbackValidator")
    def test_similar_insight_merged_instead_of_stored(
        self, mock_validator, mock_embed, memory_service
    ):
        """Similar insights should be merged instead of stored as new."""
        mock_validator.validate_insight.return_value = (True, [])
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {
                "id": "existing_id",
                "score": 0.95,
                "payload": {"description": "Similar existing insight"},
            }
        ]

        result = memory_service.write_telemetry_insight(
            {"insight_type": "cost_sink", "description": "Similar new insight"}
        )

        # Should return existing ID after merge
        assert result == "existing_id"
        # write_phase_summary should NOT be called (merged instead)
        memory_service.write_phase_summary.assert_not_called()
        # update_payload should be called for merge
        memory_service.store.update_payload.assert_called_once()

    @patch("autopack.memory.memory_service.sync_embed_text")
    @patch("autopack.memory.memory_service.TelemetryFeedbackValidator")
    def test_rules_skip_semantic_deduplication(self, mock_validator, mock_embed, memory_service):
        """Rules should not be subject to semantic deduplication."""
        mock_validator.validate_insight.return_value = (True, [])
        mock_embed.return_value = [0.1] * 1536

        # Even with similar insights, rules should be written via lifecycle
        memory_service._write_rule_with_lifecycle = Mock(return_value="rule_id")

        result = memory_service.write_telemetry_insight(
            {"insight_type": "promoted_rule", "description": "Test rule", "is_rule": True}
        )

        # Should use rule lifecycle path
        assert result == "rule_id"
        memory_service._write_rule_with_lifecycle.assert_called_once()
        # Should not search for similar insights
        memory_service.store.search.assert_not_called()

    @patch("autopack.memory.memory_service.sync_embed_text")
    @patch("autopack.memory.memory_service.TelemetryFeedbackValidator")
    def test_falls_back_to_store_on_merge_failure(self, mock_validator, mock_embed, memory_service):
        """Should store as new if merge fails."""
        mock_validator.validate_insight.return_value = (True, [])
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {"id": "existing_id", "score": 0.95, "payload": {}}
        ]
        # Simulate merge failure
        memory_service.store.update_payload.return_value = False

        result = memory_service.write_telemetry_insight(
            {"insight_type": "cost_sink", "description": "Test insight"}
        )

        # Should fall back to normal storage
        assert result == "new_id_1"
        memory_service.write_phase_summary.assert_called_once()

    @patch("autopack.memory.memory_service.sync_embed_text")
    @patch("autopack.memory.memory_service.TelemetryFeedbackValidator")
    def test_below_threshold_stored_as_new(self, mock_validator, mock_embed, memory_service):
        """Insights below similarity threshold should be stored as new."""
        mock_validator.validate_insight.return_value = (True, [])
        mock_embed.return_value = [0.1] * 1536
        # Return result below threshold (0.9)
        memory_service.store.search.return_value = [
            {"id": "existing_id", "score": 0.85, "payload": {}}
        ]

        result = memory_service.write_telemetry_insight(
            {"insight_type": "cost_sink", "description": "Somewhat different insight"}
        )

        # Should store as new (not merged)
        assert result == "new_id_1"
        memory_service.write_phase_summary.assert_called_once()


class TestDeduplicationThreshold:
    """Tests for deduplication threshold behavior."""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance."""
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._write_lock = threading.Lock()
            service._content_hashes = set()
            service._deduplicator = ContentDeduplicator()
            service.store = Mock()
            service.store.search = Mock(return_value=[])

            yield service

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_threshold_0_9_default(self, mock_embed, memory_service):
        """Default threshold should be 0.9."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {"id": "id_1", "score": 0.89, "payload": {}},  # Below 0.9
            {"id": "id_2", "score": 0.91, "payload": {}},  # Above 0.9
        ]

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}
        )

        # Only 0.91 should pass default 0.9 threshold
        assert len(result) == 1
        assert result[0]["id"] == "id_2"

    @patch("autopack.memory.memory_service.sync_embed_text")
    def test_custom_threshold(self, mock_embed, memory_service):
        """Custom threshold should be respected."""
        mock_embed.return_value = [0.1] * 1536
        memory_service.store.search.return_value = [
            {"id": "id_1", "score": 0.75, "payload": {}},
            {"id": "id_2", "score": 0.85, "payload": {}},
        ]

        result = memory_service._find_similar_insights(
            {"insight_type": "cost_sink", "description": "Test"}, threshold=0.8
        )

        # Only 0.85 should pass 0.8 threshold
        assert len(result) == 1
        assert result[0]["id"] == "id_2"
