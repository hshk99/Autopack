"""Tests for freshness_filter module (IMP-MAINT-005).

Tests cover:
- parse_timestamp function
- is_fresh function
- calculate_age_hours function
- calculate_confidence function
- FreshnessFilter class
- get_freshness_threshold function
- COLLECTION_FRESHNESS_HOURS constants
- ContextMetadata dataclass
- enrich_with_metadata function
"""

from datetime import datetime, timedelta, timezone

import pytest

from autopack.memory.freshness_filter import (COLLECTION_CODE_DOCS,
                                              COLLECTION_DOCTOR_HINTS,
                                              COLLECTION_ERRORS_CI,
                                              COLLECTION_FRESHNESS_HOURS,
                                              COLLECTION_PLANNING,
                                              COLLECTION_RUN_SUMMARIES,
                                              COLLECTION_SOT_DOCS,
                                              DEFAULT_MEMORY_FRESHNESS_HOURS,
                                              FRESH_AGE_HOURS,
                                              LOW_CONFIDENCE_THRESHOLD,
                                              MEDIUM_CONFIDENCE_THRESHOLD,
                                              STALE_AGE_HOURS, ContextMetadata,
                                              FreshnessFilter,
                                              calculate_age_hours,
                                              calculate_confidence,
                                              enrich_with_metadata,
                                              get_freshness_threshold,
                                              is_fresh, parse_timestamp)


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_valid_iso_timestamp(self):
        """Should parse valid ISO timestamp with timezone."""
        result = parse_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_z_suffix_timestamp(self):
        """Should parse timestamp with Z suffix."""
        result = parse_timestamp("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_none_returns_none(self):
        """Should return None for None input."""
        assert parse_timestamp(None) is None

    def test_parse_empty_string_returns_none(self):
        """Should return None for empty string."""
        assert parse_timestamp("") is None

    def test_parse_invalid_string_returns_none(self):
        """Should return None for invalid timestamp string."""
        assert parse_timestamp("not-a-timestamp") is None
        assert parse_timestamp("2024/01/15") is None


class TestIsFresh:
    """Tests for is_fresh function."""

    def test_fresh_timestamp_within_threshold(self):
        """Timestamp within max_age_hours should be considered fresh."""
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert is_fresh(one_hour_ago, max_age_hours=24) is True

    def test_stale_timestamp_beyond_threshold(self):
        """Timestamp beyond max_age_hours should not be considered fresh."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        assert is_fresh(two_days_ago, max_age_hours=24) is False

    def test_timestamp_exactly_at_boundary(self):
        """Timestamp exactly at max_age_hours boundary should be fresh."""
        now = datetime.now(timezone.utc)
        exactly_24_hours_ago = (now - timedelta(hours=24)).isoformat()
        assert is_fresh(exactly_24_hours_ago, max_age_hours=24, now=now) is True

    def test_none_timestamp_not_fresh(self):
        """None timestamp should not be considered fresh."""
        assert is_fresh(None, max_age_hours=24) is False

    def test_invalid_timestamp_not_fresh(self):
        """Invalid timestamp should not be considered fresh."""
        assert is_fresh("invalid", max_age_hours=24) is False

    def test_non_positive_max_age_uses_default(self):
        """Non-positive max_age_hours should use default."""
        # Create timestamp that's fresh within default (720h) but stale within 0
        five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        # Should use default 720h, so 5 days is fresh
        assert is_fresh(five_days_ago, max_age_hours=0) is True
        assert is_fresh(five_days_ago, max_age_hours=-1) is True


class TestCalculateAgeHours:
    """Tests for calculate_age_hours function."""

    def test_calculate_age_for_recent_timestamp(self):
        """Should correctly calculate age in hours."""
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        age = calculate_age_hours(one_hour_ago, now=now)
        assert 0.9 < age < 1.1  # Allow small tolerance

    def test_calculate_age_for_old_timestamp(self):
        """Should correctly calculate age for older timestamps."""
        now = datetime.now(timezone.utc)
        three_days_ago = (now - timedelta(days=3)).isoformat()
        age = calculate_age_hours(three_days_ago, now=now)
        assert 71 < age < 73  # ~72 hours

    def test_none_timestamp_returns_negative(self):
        """Should return -1.0 for None timestamp."""
        assert calculate_age_hours(None) == -1.0

    def test_invalid_timestamp_returns_negative(self):
        """Should return -1.0 for invalid timestamp."""
        assert calculate_age_hours("invalid") == -1.0

    def test_future_timestamp_returns_zero(self):
        """Should return 0 for future timestamp (negative age clamped)."""
        now = datetime.now(timezone.utc)
        future = (now + timedelta(hours=1)).isoformat()
        age = calculate_age_hours(future, now=now)
        assert age == 0.0


class TestCalculateConfidence:
    """Tests for calculate_confidence function."""

    def test_high_relevance_fresh_content(self):
        """High relevance and fresh content should have high confidence."""
        confidence = calculate_confidence(relevance_score=0.9, age_hours=1)
        assert confidence > MEDIUM_CONFIDENCE_THRESHOLD

    def test_low_relevance_reduces_confidence(self):
        """Low relevance should reduce confidence."""
        confidence = calculate_confidence(relevance_score=0.2, age_hours=1)
        assert confidence < MEDIUM_CONFIDENCE_THRESHOLD

    def test_stale_content_reduces_confidence(self):
        """Stale content should have reduced confidence."""
        confidence_fresh = calculate_confidence(relevance_score=0.8, age_hours=1)
        confidence_stale = calculate_confidence(relevance_score=0.8, age_hours=200)
        assert confidence_stale < confidence_fresh

    def test_unknown_age_gets_penalty(self):
        """Unknown age (-1) should get confidence penalty."""
        confidence_known = calculate_confidence(relevance_score=0.8, age_hours=1)
        confidence_unknown = calculate_confidence(relevance_score=0.8, age_hours=-1)
        assert confidence_unknown < confidence_known

    def test_confidence_normalized_to_0_1(self):
        """Confidence should always be between 0 and 1."""
        # Test with extreme values
        assert 0.0 <= calculate_confidence(0.0, 0) <= 1.0
        assert 0.0 <= calculate_confidence(1.5, 0) <= 1.0  # Score > 1
        assert 0.0 <= calculate_confidence(0.8, 1000) <= 1.0


class TestGetFreshnessThreshold:
    """Tests for get_freshness_threshold function."""

    def test_errors_collection_threshold(self):
        """Errors collection should have 24h threshold."""
        assert get_freshness_threshold(COLLECTION_ERRORS_CI) == 24

    def test_run_summaries_collection_threshold(self):
        """Run summaries should have 48h threshold."""
        assert get_freshness_threshold(COLLECTION_RUN_SUMMARIES) == 48

    def test_doctor_hints_collection_threshold(self):
        """Doctor hints should have 72h threshold."""
        assert get_freshness_threshold(COLLECTION_DOCTOR_HINTS) == 72

    def test_code_docs_collection_threshold(self):
        """Code docs should have 168h (1 week) threshold."""
        assert get_freshness_threshold(COLLECTION_CODE_DOCS) == 168

    def test_planning_collection_threshold(self):
        """Planning should have 168h threshold."""
        assert get_freshness_threshold(COLLECTION_PLANNING) == 168

    def test_sot_docs_collection_threshold(self):
        """SOT docs should have 336h (2 weeks) threshold."""
        assert get_freshness_threshold(COLLECTION_SOT_DOCS) == 336

    def test_unknown_collection_uses_default(self):
        """Unknown collection should use default threshold."""
        assert get_freshness_threshold("unknown_collection") == 720


class TestContextMetadata:
    """Tests for ContextMetadata dataclass."""

    def test_high_confidence_level(self):
        """Confidence >= 0.6 should be 'high'."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.9,
            age_hours=1,
            confidence=0.7,
            is_low_confidence=False,
        )
        assert metadata.confidence_level == "high"

    def test_medium_confidence_level(self):
        """Confidence between 0.3 and 0.6 should be 'medium'."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.5,
            age_hours=100,
            confidence=0.45,
            is_low_confidence=False,
        )
        assert metadata.confidence_level == "medium"

    def test_low_confidence_level(self):
        """Confidence < 0.3 should be 'low'."""
        metadata = ContextMetadata(
            content="test",
            relevance_score=0.2,
            age_hours=200,
            confidence=0.2,
            is_low_confidence=True,
        )
        assert metadata.confidence_level == "low"


class TestEnrichWithMetadata:
    """Tests for enrich_with_metadata function."""

    def test_enriches_search_result(self):
        """Should enrich search result with metadata."""
        now = datetime.now(timezone.utc)
        one_hour_ago = (now - timedelta(hours=1)).isoformat()
        result = {
            "id": "test-id",
            "score": 0.85,
            "payload": {"content": "test content", "timestamp": one_hour_ago, "type": "error"},
        }
        metadata = enrich_with_metadata(result, now=now)
        assert metadata.content == "test content"
        assert metadata.relevance_score == 0.85
        assert 0.9 < metadata.age_hours < 1.1
        assert metadata.source_id == "test-id"
        assert metadata.source_type == "error"

    def test_extracts_content_from_various_keys(self):
        """Should try multiple keys for content extraction."""
        result = {
            "id": "test",
            "score": 0.8,
            "payload": {
                "summary": "summary content",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        metadata = enrich_with_metadata(result)
        assert metadata.content == "summary content"

    def test_handles_missing_payload(self):
        """Should handle results with missing payload."""
        result = {"id": "test", "score": 0.5}
        metadata = enrich_with_metadata(result)
        assert metadata.content == ""
        assert metadata.age_hours == -1.0


class TestFreshnessFilterClass:
    """Tests for FreshnessFilter class."""

    def test_init_with_default_threshold(self):
        """Should initialize with default threshold."""
        ff = FreshnessFilter()
        assert ff.default_max_age_hours == DEFAULT_MEMORY_FRESHNESS_HOURS

    def test_init_with_custom_threshold(self):
        """Should initialize with custom threshold."""
        ff = FreshnessFilter(default_max_age_hours=24)
        assert ff.default_max_age_hours == 24

    def test_is_fresh_method(self):
        """is_fresh method should use default threshold if not specified."""
        ff = FreshnessFilter(default_max_age_hours=24)
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        assert ff.is_fresh(one_hour_ago) is True

    def test_filter_by_freshness(self):
        """filter_by_freshness should filter items by threshold."""
        ff = FreshnessFilter(default_max_age_hours=24)
        now = datetime.now(timezone.utc)
        items = [
            {"payload": {"timestamp": (now - timedelta(hours=1)).isoformat()}},
            {"payload": {"timestamp": (now - timedelta(hours=48)).isoformat()}},
            {"payload": {"timestamp": (now - timedelta(hours=12)).isoformat()}},
        ]
        filtered = ff.filter_by_freshness(items)
        assert len(filtered) == 2

    def test_get_freshness_for_collection(self):
        """Should return correct threshold for collection."""
        ff = FreshnessFilter()
        assert ff.get_freshness_for_collection(COLLECTION_ERRORS_CI) == 24
        assert ff.get_freshness_for_collection(COLLECTION_CODE_DOCS) == 168

    def test_enrich_with_metadata_method(self):
        """enrich_with_metadata method should work correctly."""
        ff = FreshnessFilter()
        result = {
            "id": "test",
            "score": 0.8,
            "payload": {"content": "test", "timestamp": datetime.now(timezone.utc).isoformat()},
        }
        metadata = ff.enrich_with_metadata(result)
        assert isinstance(metadata, ContextMetadata)

    def test_calculate_confidence_method(self):
        """calculate_confidence method should work correctly."""
        ff = FreshnessFilter()
        confidence = ff.calculate_confidence(0.8, 1)
        assert 0.0 <= confidence <= 1.0


class TestConstants:
    """Tests for module constants."""

    def test_default_freshness_hours(self):
        """DEFAULT_MEMORY_FRESHNESS_HOURS should be 720 (30 days)."""
        assert DEFAULT_MEMORY_FRESHNESS_HOURS == 720

    def test_confidence_thresholds(self):
        """Confidence thresholds should have correct values."""
        assert LOW_CONFIDENCE_THRESHOLD == 0.3
        assert MEDIUM_CONFIDENCE_THRESHOLD == 0.6

    def test_age_thresholds(self):
        """Age thresholds should have correct values."""
        assert FRESH_AGE_HOURS == 24
        assert STALE_AGE_HOURS == 168

    def test_collection_freshness_hours_dict(self):
        """COLLECTION_FRESHNESS_HOURS should have all expected collections."""
        assert COLLECTION_ERRORS_CI in COLLECTION_FRESHNESS_HOURS
        assert COLLECTION_RUN_SUMMARIES in COLLECTION_FRESHNESS_HOURS
        assert COLLECTION_DOCTOR_HINTS in COLLECTION_FRESHNESS_HOURS
        assert COLLECTION_CODE_DOCS in COLLECTION_FRESHNESS_HOURS
        assert COLLECTION_PLANNING in COLLECTION_FRESHNESS_HOURS
        assert COLLECTION_SOT_DOCS in COLLECTION_FRESHNESS_HOURS
        assert "default" in COLLECTION_FRESHNESS_HOURS
