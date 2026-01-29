"""Tests for IMP-MEM-013: Confidence Filter Missing in Context Retrieval.

Tests the confidence filtering logic added to retrieve_context_with_metadata(),
ensuring low-confidence context entries are filtered out before being returned.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from autopack.memory.memory_service import (
    LOW_CONFIDENCE_THRESHOLD,
    ContextMetadata,
    MemoryService,
)


class TestRetrieveContextWithMetadataConfidenceFiltering:
    """Tests for IMP-MEM-013: Confidence filtering in retrieve_context_with_metadata."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a mock MemoryService for testing."""
        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service.store = Mock()
            service.top_k = 5
            return service

    def test_filters_low_confidence_entries_by_default(self, mock_memory_service):
        """Test that entries below LOW_CONFIDENCE_THRESHOLD are filtered by default."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=5)).isoformat()
        old_ts = (now - timedelta(hours=200)).isoformat()

        # High confidence error (recent, high relevance)
        high_conf_error = {
            "id": "error:high",
            "score": 0.9,
            "payload": {
                "type": "error",
                "error_text": "High confidence error",
                "timestamp": recent_ts,
            },
        }

        # Low confidence error (old, low relevance)
        low_conf_error = {
            "id": "error:low",
            "score": 0.2,
            "payload": {
                "type": "error",
                "error_text": "Low confidence error",
                "timestamp": old_ts,
            },
        }

        mock_memory_service.search_errors = Mock(return_value=[high_conf_error, low_conf_error])
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        # Should only include high confidence error
        assert len(result["errors"]) == 1
        assert result["errors"][0].content == "High confidence error"
        assert result["errors"][0].confidence >= LOW_CONFIDENCE_THRESHOLD

    def test_respects_custom_min_confidence(self, mock_memory_service):
        """Test that custom min_confidence parameter is respected."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=10)).isoformat()
        older_ts = (now - timedelta(hours=100)).isoformat()

        # Lower confidence error (relevance 0.4, old - should be below 0.7 threshold)
        lower_conf_error = {
            "id": "error:lower",
            "score": 0.4,
            "payload": {
                "type": "error",
                "error_text": "Lower confidence error",
                "timestamp": older_ts,
            },
        }

        # High confidence error (relevance 0.9, recent)
        high_conf_error = {
            "id": "error:high",
            "score": 0.9,
            "payload": {
                "type": "error",
                "error_text": "High confidence error",
                "timestamp": recent_ts,
            },
        }

        mock_memory_service.search_errors = Mock(return_value=[high_conf_error, lower_conf_error])
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        # Use higher threshold of 0.7 - only high confidence should pass
        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
            min_confidence=0.7,
        )

        # Only high confidence error should pass 0.7 threshold
        assert len(result["errors"]) == 1
        assert result["errors"][0].content == "High confidence error"

    def test_zero_min_confidence_disables_filtering(self, mock_memory_service):
        """Test that min_confidence=0.0 disables filtering entirely."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=200)).isoformat()

        # Very low confidence error
        low_conf_error = {
            "id": "error:verylow",
            "score": 0.1,
            "payload": {
                "type": "error",
                "error_text": "Very low confidence error",
                "timestamp": old_ts,
            },
        }

        mock_memory_service.search_errors = Mock(return_value=[low_conf_error])
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        # Disable filtering with min_confidence=0.0
        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
            min_confidence=0.0,
        )

        # Should include even very low confidence items
        assert len(result["errors"]) == 1
        assert result["errors"][0].content == "Very low confidence error"

    def test_filters_across_all_collections(self, mock_memory_service):
        """Test that filtering applies to all collection types."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=5)).isoformat()
        old_ts = (now - timedelta(hours=200)).isoformat()

        # High confidence items
        high_conf_error = {
            "id": "error:high",
            "score": 0.9,
            "payload": {"error_text": "High conf error", "timestamp": recent_ts},
        }
        high_conf_hint = {
            "id": "hint:high",
            "score": 0.85,
            "payload": {"hint": "High conf hint", "timestamp": recent_ts},
        }

        # Low confidence items
        low_conf_code = {
            "id": "code:low",
            "score": 0.15,
            "payload": {"content_preview": "Low conf code", "timestamp": old_ts},
        }
        low_conf_summary = {
            "id": "summary:low",
            "score": 0.1,
            "payload": {"summary": "Low conf summary", "timestamp": old_ts},
        }

        mock_memory_service.search_errors = Mock(return_value=[high_conf_error])
        mock_memory_service.search_doctor_hints = Mock(return_value=[high_conf_hint])
        mock_memory_service.search_code = Mock(return_value=[low_conf_code])
        mock_memory_service.search_summaries = Mock(return_value=[low_conf_summary])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        # High confidence items should be included
        assert len(result["errors"]) == 1
        assert len(result["hints"]) == 1

        # Low confidence items should be filtered
        assert len(result["code"]) == 0
        assert len(result["summaries"]) == 0

    def test_logs_filtered_count(self, mock_memory_service, caplog):
        """Test that filtering logs the count of filtered entries."""
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(hours=5)).isoformat()
        old_ts = (now - timedelta(hours=200)).isoformat()

        high_conf = {
            "id": "error:high",
            "score": 0.9,
            "payload": {"error_text": "High", "timestamp": recent_ts},
        }
        low_conf = {
            "id": "error:low",
            "score": 0.1,
            "payload": {"error_text": "Low", "timestamp": old_ts},
        }

        mock_memory_service.search_errors = Mock(return_value=[high_conf, low_conf])
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        import logging

        with caplog.at_level(logging.INFO):
            mock_memory_service.retrieve_context_with_metadata(
                query="test query",
                project_id="test-project",
            )

        # Should log about filtered entries
        assert any("filtered" in record.message.lower() for record in caplog.records)

    def test_maintains_sort_order_after_filtering(self, mock_memory_service):
        """Test that results remain sorted by confidence after filtering."""
        now = datetime.now(timezone.utc)
        ts1 = (now - timedelta(hours=5)).isoformat()
        ts2 = (now - timedelta(hours=10)).isoformat()
        ts3 = (now - timedelta(hours=15)).isoformat()

        # Three errors with different confidence levels (all above threshold)
        errors = [
            {
                "id": "error:1",
                "score": 0.6,
                "payload": {"error_text": "Medium confidence", "timestamp": ts2},
            },
            {
                "id": "error:2",
                "score": 0.9,
                "payload": {"error_text": "High confidence", "timestamp": ts1},
            },
            {
                "id": "error:3",
                "score": 0.5,
                "payload": {"error_text": "Lower confidence", "timestamp": ts3},
            },
        ]

        mock_memory_service.search_errors = Mock(return_value=errors)
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        # Results should be sorted by confidence (highest first)
        confidences = [e.confidence for e in result["errors"]]
        assert confidences == sorted(confidences, reverse=True)
        assert result["errors"][0].content == "High confidence"

    def test_empty_results_after_filtering(self, mock_memory_service):
        """Test handling when all results are filtered out."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=200)).isoformat()

        # All low confidence
        low_conf_error = {
            "id": "error:low",
            "score": 0.1,
            "payload": {"error_text": "Low conf", "timestamp": old_ts},
        }

        mock_memory_service.search_errors = Mock(return_value=[low_conf_error])
        mock_memory_service.search_code = Mock(return_value=[])
        mock_memory_service.search_summaries = Mock(return_value=[])
        mock_memory_service.search_doctor_hints = Mock(return_value=[])

        result = mock_memory_service.retrieve_context_with_metadata(
            query="test query",
            project_id="test-project",
        )

        # All collections should be empty
        assert result["errors"] == []
        assert result["code"] == []
        assert result["summaries"] == []
        assert result["hints"] == []


class TestLowConfidenceThresholdConstant:
    """Tests for LOW_CONFIDENCE_THRESHOLD constant."""

    def test_low_confidence_threshold_value(self):
        """Test that LOW_CONFIDENCE_THRESHOLD is set to 0.3."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.3

    def test_low_confidence_threshold_is_used_by_default(self):
        """Test that default filtering uses LOW_CONFIDENCE_THRESHOLD."""
        # The ContextMetadata.is_low_confidence uses this threshold
        low_conf = ContextMetadata(
            content="test",
            relevance_score=0.2,
            age_hours=100.0,
            confidence=0.25,
            is_low_confidence=True,
        )
        assert low_conf.confidence < LOW_CONFIDENCE_THRESHOLD
        assert low_conf.is_low_confidence is True

        high_conf = ContextMetadata(
            content="test",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        assert high_conf.confidence >= LOW_CONFIDENCE_THRESHOLD
        assert high_conf.is_low_confidence is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
