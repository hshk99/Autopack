"""Tests for IMP-MEM-001: Memory Freshness Integration in Task Generation.

This module tests the freshness filtering functionality in the task generation
pipeline to prevent duplicate/stale task creation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer
from autopack.task_generation.insight_to_task import (
    DEFAULT_INSIGHT_FRESHNESS_HOURS, InsightToTaskGenerator)
from autopack.task_generation.priority_engine import (
    FRESHNESS_BOOST_THRESHOLD_HOURS, FRESHNESS_DECAY_THRESHOLD_HOURS,
    FRESHNESS_NEUTRAL_THRESHOLD_HOURS, PriorityEngine)


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_slot_history() -> dict:
    """Sample slot_history.json with minimal data."""
    return {"slots": [], "events": []}


@pytest.fixture
def populated_state_dir(temp_state_dir: Path, sample_slot_history: dict) -> Path:
    """Create minimal state files in temp directory."""
    (temp_state_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))
    (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
    (temp_state_dir / "ci_retry_state.json").write_text(json.dumps({"retries": []}))
    return temp_state_dir


@pytest.fixture
def generator(populated_state_dir: Path) -> InsightToTaskGenerator:
    """Create an InsightToTaskGenerator."""
    analyzer = TelemetryAnalyzer(populated_state_dir)
    return InsightToTaskGenerator(analyzer)


def _iso_timestamp(hours_ago: float = 0) -> str:
    """Create ISO timestamp for hours ago from now."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.isoformat()


class TestInsightFreshnessFiltering:
    """Tests for _filter_stale_insights and _is_insight_fresh in InsightToTaskGenerator."""

    def test_fresh_insight_within_threshold(self, generator: InsightToTaskGenerator) -> None:
        """Test insight within freshness window is kept."""
        insight = {
            "source": "slot_reliability",
            "timestamp": _iso_timestamp(hours_ago=1),  # 1 hour ago
            "action": "Test action",
        }
        assert generator._is_insight_fresh(insight) is True

    def test_stale_insight_beyond_threshold(self, generator: InsightToTaskGenerator) -> None:
        """Test insight beyond freshness window is filtered."""
        insight = {
            "source": "slot_reliability",
            "timestamp": _iso_timestamp(hours_ago=100),  # 100 hours ago (> 72h default)
            "action": "Test action",
        }
        assert generator._is_insight_fresh(insight) is False

    def test_insight_at_threshold_boundary(self, generator: InsightToTaskGenerator) -> None:
        """Test insight exactly at threshold is fresh."""
        insight = {
            "source": "slot_reliability",
            "timestamp": _iso_timestamp(hours_ago=DEFAULT_INSIGHT_FRESHNESS_HOURS),
            "action": "Test action",
        }
        assert generator._is_insight_fresh(insight) is True

    def test_insight_just_beyond_threshold(self, generator: InsightToTaskGenerator) -> None:
        """Test insight just beyond threshold is stale."""
        insight = {
            "source": "slot_reliability",
            "timestamp": _iso_timestamp(hours_ago=DEFAULT_INSIGHT_FRESHNESS_HOURS + 1),
            "action": "Test action",
        }
        assert generator._is_insight_fresh(insight) is False

    def test_insight_without_timestamp_assumed_fresh(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test insight without timestamp is assumed fresh."""
        insight = {
            "source": "slot_reliability",
            "action": "Test action",
        }
        assert generator._is_insight_fresh(insight) is True

    def test_filter_stale_insights_mixed_list(self, generator: InsightToTaskGenerator) -> None:
        """Test filtering mixed list of fresh and stale insights."""
        insights = [
            {"source": "a", "timestamp": _iso_timestamp(hours_ago=1)},  # Fresh
            {"source": "b", "timestamp": _iso_timestamp(hours_ago=100)},  # Stale
            {"source": "c", "timestamp": _iso_timestamp(hours_ago=50)},  # Fresh
            {"source": "d", "timestamp": _iso_timestamp(hours_ago=80)},  # Stale
        ]
        fresh = generator._filter_stale_insights(insights)
        assert len(fresh) == 2
        sources = [i["source"] for i in fresh]
        assert "a" in sources
        assert "c" in sources

    def test_filter_stale_insights_empty_list(self, generator: InsightToTaskGenerator) -> None:
        """Test filtering empty list returns empty."""
        fresh = generator._filter_stale_insights([])
        assert fresh == []

    def test_filter_stale_insights_all_fresh(self, generator: InsightToTaskGenerator) -> None:
        """Test filtering list with all fresh insights."""
        insights = [
            {"source": "a", "timestamp": _iso_timestamp(hours_ago=1)},
            {"source": "b", "timestamp": _iso_timestamp(hours_ago=10)},
            {"source": "c", "timestamp": _iso_timestamp(hours_ago=24)},
        ]
        fresh = generator._filter_stale_insights(insights)
        assert len(fresh) == 3

    def test_filter_stale_insights_all_stale(self, generator: InsightToTaskGenerator) -> None:
        """Test filtering list with all stale insights."""
        insights = [
            {"source": "a", "timestamp": _iso_timestamp(hours_ago=100)},
            {"source": "b", "timestamp": _iso_timestamp(hours_ago=200)},
        ]
        fresh = generator._filter_stale_insights(insights)
        assert len(fresh) == 0


class TestTimestampParsing:
    """Tests for timestamp parsing in various formats."""

    def test_parse_iso_format_with_timezone(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing ISO format with timezone."""
        insight = {
            "timestamp": "2026-01-28T12:00:00+00:00",
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None
        assert ts.tzinfo is not None

    def test_parse_iso_format_with_z_suffix(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing ISO format with Z suffix."""
        insight = {
            "timestamp": "2026-01-28T12:00:00Z",
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None

    def test_parse_iso_format_naive(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing ISO format without timezone (naive)."""
        insight = {
            "timestamp": "2026-01-28T12:00:00",
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None
        # Should be converted to UTC
        assert ts.tzinfo is not None

    def test_parse_datetime_object(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing datetime object directly."""
        insight = {
            "timestamp": datetime(2026, 1, 28, 12, 0, 0, tzinfo=timezone.utc),
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None
        assert ts.year == 2026

    def test_parse_created_at_field(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing created_at field."""
        insight = {
            "created_at": _iso_timestamp(hours_ago=1),
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None

    def test_parse_detected_at_field(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing detected_at field."""
        insight = {
            "detected_at": _iso_timestamp(hours_ago=1),
            "source": "test",
        }
        ts = generator._parse_insight_timestamp(insight)
        assert ts is not None

    def test_parse_no_timestamp_returns_none(self, generator: InsightToTaskGenerator) -> None:
        """Test parsing insight with no timestamp returns None."""
        insight = {"source": "test"}
        ts = generator._parse_insight_timestamp(insight)
        assert ts is None


class TestCustomFreshnessThreshold:
    """Tests for custom freshness threshold configuration."""

    def test_custom_freshness_hours_in_constructor(self, populated_state_dir: Path) -> None:
        """Test custom freshness hours in constructor."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        generator = InsightToTaskGenerator(analyzer, freshness_hours=24)

        # 20 hours ago should be fresh with 24h threshold
        insight = {"timestamp": _iso_timestamp(hours_ago=20)}
        assert generator._is_insight_fresh(insight) is True

        # 30 hours ago should be stale with 24h threshold
        insight = {"timestamp": _iso_timestamp(hours_ago=30)}
        assert generator._is_insight_fresh(insight) is False

    def test_set_memory_service_updates_threshold(self, generator: InsightToTaskGenerator) -> None:
        """Test set_memory_service can update freshness threshold."""
        # Note: We're testing without an actual memory service since we just
        # need to verify the threshold update works
        generator._freshness_hours = 24

        # Should use the new threshold
        insight = {"timestamp": _iso_timestamp(hours_ago=30)}
        assert generator._is_insight_fresh(insight) is False

        insight = {"timestamp": _iso_timestamp(hours_ago=20)}
        assert generator._is_insight_fresh(insight) is True

    def test_get_freshness_stats(self, generator: InsightToTaskGenerator) -> None:
        """Test get_freshness_stats returns correct info."""
        stats = generator.get_freshness_stats()

        assert "freshness_threshold_hours" in stats
        assert stats["freshness_threshold_hours"] == DEFAULT_INSIGHT_FRESHNESS_HOURS
        assert "memory_service_connected" in stats
        assert stats["memory_service_connected"] is False


class TestPriorityEngineFreshnessIntegration:
    """Tests for freshness factor in PriorityEngine."""

    @pytest.fixture
    def mock_learning_db(self):
        """Create a mock learning database."""

        class MockLearningDB:
            def get_success_rate(self, category: str) -> float:
                return 0.8

            def get_likely_blockers(self, category: str) -> list:
                return []

            def get_historical_patterns(self) -> dict:
                return {}

        return MockLearningDB()

    @pytest.fixture
    def priority_engine(self, mock_learning_db) -> PriorityEngine:
        """Create a PriorityEngine with mock dependencies."""
        return PriorityEngine(mock_learning_db)

    def test_fresh_insight_gets_boost(self, priority_engine: PriorityEngine) -> None:
        """Test very fresh insight gets priority boost."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=1),  # 1 hour ago
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert factor == 1.2  # Maximum boost

    def test_neutral_age_insight(self, priority_engine: PriorityEngine) -> None:
        """Test insight at neutral age gets factor around 1.0."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=72),  # 72 hours = neutral
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert 0.95 <= factor <= 1.05  # Around neutral

    def test_stale_insight_gets_penalty(self, priority_engine: PriorityEngine) -> None:
        """Test stale insight gets priority penalty."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=200),  # Very old
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert factor == 0.5  # Minimum factor

    def test_no_timestamp_gets_neutral(self, priority_engine: PriorityEngine) -> None:
        """Test insight without timestamp gets neutral factor."""
        improvement = {
            "id": "IMP-TEST-001",
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert factor == 1.0

    def test_timestamp_in_evidence_dict(self, priority_engine: PriorityEngine) -> None:
        """Test timestamp in nested evidence dict is used."""
        improvement = {
            "id": "IMP-TEST-001",
            "priority": "medium",
            "evidence": {
                "timestamp": _iso_timestamp(hours_ago=1),
            },
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert factor == 1.2  # Should get boost

    def test_freshness_factor_in_priority_score(self, priority_engine: PriorityEngine) -> None:
        """Test freshness factor affects overall priority score."""
        # Fresh insight
        fresh_improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=1),
            "priority": "medium",
            "category": "test",
        }
        fresh_score = priority_engine.calculate_priority_score(fresh_improvement)

        # Stale insight with same other attributes
        stale_improvement = {
            "id": "IMP-TEST-002",
            "created_at": _iso_timestamp(hours_ago=200),
            "priority": "medium",
            "category": "test",
        }
        stale_score = priority_engine.calculate_priority_score(stale_improvement)

        # Fresh should score higher
        assert fresh_score > stale_score

    def test_freshness_decay_curve_boost_zone(self, priority_engine: PriorityEngine) -> None:
        """Test freshness decay in boost zone (< 24h)."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=12),  # 12 hours
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        assert factor == 1.2  # Still maximum boost under 24h

    def test_freshness_decay_curve_transition_zone(self, priority_engine: PriorityEngine) -> None:
        """Test freshness decay in transition zone (24-72h)."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=48),  # 48 hours (midpoint)
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        # Should be between 1.0 and 1.2
        assert 1.0 < factor < 1.2

    def test_freshness_decay_curve_penalty_zone(self, priority_engine: PriorityEngine) -> None:
        """Test freshness decay in penalty zone (72-168h)."""
        improvement = {
            "id": "IMP-TEST-001",
            "created_at": _iso_timestamp(hours_ago=120),  # 120 hours
            "priority": "medium",
        }
        factor = priority_engine.get_freshness_factor(improvement)
        # Should be between 0.7 and 1.0
        assert 0.7 < factor < 1.0


class TestFreshnessConstants:
    """Tests for freshness-related constants."""

    def test_default_freshness_hours_is_72(self) -> None:
        """Test default freshness threshold is 72 hours."""
        assert DEFAULT_INSIGHT_FRESHNESS_HOURS == 72

    def test_boost_threshold_less_than_neutral(self) -> None:
        """Test boost threshold is less than neutral threshold."""
        assert FRESHNESS_BOOST_THRESHOLD_HOURS < FRESHNESS_NEUTRAL_THRESHOLD_HOURS

    def test_neutral_threshold_less_than_decay(self) -> None:
        """Test neutral threshold is less than decay threshold."""
        assert FRESHNESS_NEUTRAL_THRESHOLD_HOURS < FRESHNESS_DECAY_THRESHOLD_HOURS

    def test_threshold_values(self) -> None:
        """Test specific threshold values."""
        assert FRESHNESS_BOOST_THRESHOLD_HOURS == 24
        assert FRESHNESS_NEUTRAL_THRESHOLD_HOURS == 72
        assert FRESHNESS_DECAY_THRESHOLD_HOURS == 168
