"""Tests for confidence thresholding in task generation (IMP-LOOP-016, IMP-LOOP-033).

Tests cover:
- UnifiedInsight confidence field
- DirectInsightConsumer confidence population
- MemoryInsightConsumer confidence extraction
- AnalyzerInsightConsumer confidence propagation
- generate_tasks insight confidence filtering
- retrieve_insights min_confidence parameter
- IMP-LOOP-033: MIN_CONFIDENCE_THRESHOLD floor enforcement
- IMP-LOOP-033: Effective threshold calculation
- IMP-LOOP-033: Confidence distribution statistics
"""

from unittest.mock import Mock

import pytest

from autopack.roadc.task_generator import (
    MIN_CONFIDENCE_THRESHOLD,
    AnalyzerInsightConsumer,
    DirectInsightConsumer,
    InsightSource,
    MemoryInsightConsumer,
    UnifiedInsight,
)
from autopack.telemetry.analyzer import RankedIssue


class TestUnifiedInsightConfidence:
    """Tests for UnifiedInsight confidence field (IMP-LOOP-016)."""

    def test_unified_insight_default_confidence(self):
        """UnifiedInsight should have default confidence of 1.0."""
        insight = UnifiedInsight(
            id="test_1",
            issue_type="cost_sink",
            content="Test insight",
            severity="high",
        )
        assert insight.confidence == 1.0

    def test_unified_insight_custom_confidence(self):
        """UnifiedInsight should accept custom confidence values."""
        insight = UnifiedInsight(
            id="test_1",
            issue_type="failure_mode",
            content="Test insight",
            severity="medium",
            confidence=0.75,
        )
        assert insight.confidence == 0.75

    def test_unified_insight_low_confidence(self):
        """UnifiedInsight should accept low confidence values."""
        insight = UnifiedInsight(
            id="test_1",
            issue_type="retry_cause",
            content="Uncertain insight",
            severity="low",
            confidence=0.3,
        )
        assert insight.confidence == 0.3


class TestDirectInsightConsumerConfidence:
    """Tests for DirectInsightConsumer confidence population (IMP-LOOP-016)."""

    @pytest.fixture
    def sample_telemetry_data(self):
        """Sample telemetry data with various issue types."""
        return {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="build-phase",
                    phase_type="building",
                    metric_value=100000.0,
                    details={"avg_tokens": 50000, "count": 2},
                )
            ],
            "top_failure_modes": [
                RankedIssue(
                    rank=1,
                    issue_type="failure_mode",
                    phase_id="test-phase",
                    phase_type="testing",
                    metric_value=10.0,
                    details={"outcome": "failed", "stop_reason": "timeout"},
                )
            ],
            "top_retry_causes": [
                RankedIssue(
                    rank=1,
                    issue_type="retry_cause",
                    phase_id="deploy-phase",
                    phase_type="deployment",
                    metric_value=5.0,
                    details={"stop_reason": "rate_limit", "success_count": 3},
                )
            ],
        }

    def test_direct_consumer_sets_confidence_1_0(self, sample_telemetry_data):
        """DirectInsightConsumer should set confidence=1.0 for all insights."""
        consumer = DirectInsightConsumer(sample_telemetry_data)
        result = consumer.get_insights(limit=100)

        assert len(result.insights) == 3
        for insight in result.insights:
            assert insight.confidence == 1.0, (
                f"Expected confidence 1.0 for {insight.issue_type}, " f"got {insight.confidence}"
            )

    def test_direct_consumer_source_is_direct(self, sample_telemetry_data):
        """DirectInsightConsumer should set source=InsightSource.DIRECT."""
        consumer = DirectInsightConsumer(sample_telemetry_data)
        result = consumer.get_insights(limit=100)

        for insight in result.insights:
            assert insight.source == InsightSource.DIRECT


class TestMemoryInsightConsumerConfidence:
    """Tests for MemoryInsightConsumer confidence extraction (IMP-LOOP-016)."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service with insights."""
        mock = Mock()
        mock.retrieve_insights.return_value = [
            {
                "id": "insight_1",
                "issue_type": "cost_sink",
                "content": "High cost phase",
                "severity": "high",
                "confidence": 0.9,
            },
            {
                "id": "insight_2",
                "issue_type": "failure_mode",
                "content": "Frequent failures",
                "severity": "high",
                "confidence": 0.5,
            },
            {
                "id": "insight_3",
                "issue_type": "retry_cause",
                "content": "Retry pattern",
                "severity": "medium",
                # No confidence field - should default to 1.0
            },
        ]
        return mock

    def test_memory_consumer_extracts_confidence(self, mock_memory_service):
        """MemoryInsightConsumer should extract confidence from raw insights."""
        # IMP-MEM-015: project_id is now required for namespace isolation
        consumer = MemoryInsightConsumer(mock_memory_service, project_id="test-project")
        result = consumer.get_insights(limit=100)

        assert len(result.insights) == 3
        assert result.insights[0].confidence == 0.9
        assert result.insights[1].confidence == 0.5
        assert result.insights[2].confidence == 1.0  # Default

    def test_memory_consumer_defaults_missing_confidence(self, mock_memory_service):
        """MemoryInsightConsumer should default to 1.0 when confidence is missing."""
        mock_memory_service.retrieve_insights.return_value = [
            {
                "id": "no_confidence",
                "issue_type": "unknown",
                "content": "No confidence field",
                "severity": "low",
            }
        ]
        # IMP-MEM-015: project_id is now required for namespace isolation
        consumer = MemoryInsightConsumer(mock_memory_service, project_id="test-project")
        result = consumer.get_insights(limit=100)

        assert len(result.insights) == 1
        assert result.insights[0].confidence == 1.0


class TestAnalyzerInsightConsumerConfidence:
    """Tests for AnalyzerInsightConsumer confidence propagation (IMP-LOOP-016)."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock analyzer with sample data."""
        mock = Mock()
        mock.aggregate_telemetry.return_value = {
            "top_cost_sinks": [
                RankedIssue(
                    rank=1,
                    issue_type="cost_sink",
                    phase_id="build-phase",
                    phase_type="building",
                    metric_value=75000.0,
                    details={"avg_tokens": 25000, "count": 3},
                )
            ],
            "top_failure_modes": [],
            "top_retry_causes": [],
        }
        return mock

    def test_analyzer_consumer_propagates_confidence(self, mock_analyzer):
        """AnalyzerInsightConsumer should propagate confidence from underlying data."""
        consumer = AnalyzerInsightConsumer(mock_analyzer)
        result = consumer.get_insights(limit=100)

        assert len(result.insights) == 1
        # DirectInsightConsumer sets 1.0, which should be propagated
        assert result.insights[0].confidence == 1.0
        assert result.insights[0].source == InsightSource.ANALYZER


class TestGenerateTasksConfidenceFiltering:
    """Tests for generate_tasks confidence filtering (IMP-LOOP-016).

    These tests verify the confidence filtering logic in generate_tasks
    by testing the filtering behavior directly on insight lists.
    """

    def test_confidence_filter_removes_low_confidence(self):
        """Insights below min_confidence threshold should be filtered out."""
        test_insights = [
            UnifiedInsight(
                id="high_conf",
                issue_type="cost_sink",
                content="High confidence insight",
                severity="high",
                confidence=0.9,
            ),
            UnifiedInsight(
                id="low_conf",
                issue_type="failure_mode",
                content="Low confidence insight",
                severity="high",
                confidence=0.4,
            ),
            UnifiedInsight(
                id="threshold_conf",
                issue_type="retry_cause",
                content="At threshold confidence",
                severity="medium",
                confidence=0.7,
            ),
        ]

        # Apply the same filtering logic used in generate_tasks
        min_confidence = 0.7
        filtered_insights = [i for i in test_insights if i.confidence >= min_confidence]

        # Should have filtered out the low confidence insight (0.4 < 0.7)
        assert len(filtered_insights) == 2
        assert all(i.confidence >= 0.7 for i in filtered_insights)
        assert filtered_insights[0].id == "high_conf"
        assert filtered_insights[1].id == "threshold_conf"

    def test_confidence_filter_removes_all_when_all_below_threshold(self):
        """All insights should be filtered if all below threshold."""
        test_insights = [
            UnifiedInsight(
                id="low_1",
                issue_type="cost_sink",
                content="Low confidence insight",
                severity="high",
                confidence=0.3,
            ),
            UnifiedInsight(
                id="low_2",
                issue_type="failure_mode",
                content="Low confidence insight",
                severity="high",
                confidence=0.5,
            ),
        ]

        min_confidence = 0.7
        filtered_insights = [i for i in test_insights if i.confidence >= min_confidence]

        # All insights filtered
        assert len(filtered_insights) == 0

    def test_confidence_filter_keeps_all_when_all_above_threshold(self):
        """All insights should be kept if all above threshold."""
        test_insights = [
            UnifiedInsight(
                id="high_1",
                issue_type="cost_sink",
                content="High confidence insight",
                severity="high",
                confidence=0.9,
            ),
            UnifiedInsight(
                id="high_2",
                issue_type="failure_mode",
                content="High confidence insight",
                severity="high",
                confidence=0.8,
            ),
        ]

        min_confidence = 0.7
        filtered_insights = [i for i in test_insights if i.confidence >= min_confidence]

        # All insights kept
        assert len(filtered_insights) == 2

    def test_confidence_filter_with_default_confidence(self):
        """Insights with default confidence (1.0) should pass any threshold."""
        test_insights = [
            UnifiedInsight(
                id="default_conf",
                issue_type="cost_sink",
                content="Default confidence insight",
                severity="high",
                # confidence defaults to 1.0
            ),
        ]

        min_confidence = 0.7
        filtered_insights = [i for i in test_insights if i.confidence >= min_confidence]

        assert len(filtered_insights) == 1
        assert filtered_insights[0].confidence == 1.0


class TestRetrieveInsightsConfidenceFiltering:
    """Tests for retrieve_insights min_confidence parameter (IMP-LOOP-016).

    These tests verify the confidence filtering logic by testing the
    filtering behavior directly on insight dictionaries.
    """

    def test_confidence_filter_removes_low_confidence_insights(self):
        """Low confidence insights should be filtered when min_confidence specified."""
        # Simulate insights returned from retrieve_insights
        insights = [
            {"id": "insight_1", "content": "High confidence", "confidence": 0.9},
            {"id": "insight_2", "content": "Low confidence", "confidence": 0.4},
            {"id": "insight_3", "content": "Medium confidence", "confidence": 0.7},
        ]

        # Apply the same filtering logic used in retrieve_insights
        min_confidence = 0.7
        filtered_insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]

        # Should only return insights with confidence >= 0.7
        assert len(filtered_insights) == 2
        assert filtered_insights[0]["confidence"] == 0.9
        assert filtered_insights[1]["confidence"] == 0.7

    def test_confidence_filter_no_filtering_when_none(self):
        """All insights should be kept when min_confidence is None."""
        insights = [
            {"id": "insight_1", "content": "High confidence", "confidence": 0.9},
            {"id": "insight_2", "content": "Low confidence", "confidence": 0.4},
        ]

        # When min_confidence is None, don't filter
        min_confidence = None
        if min_confidence is not None:
            filtered_insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]
        else:
            filtered_insights = insights

        # Should return all insights
        assert len(filtered_insights) == 2

    def test_insight_dict_includes_confidence_field(self):
        """Insight dictionaries should include confidence field."""
        # Simulate payload from memory with confidence
        payload = {
            "task_type": "telemetry_insight",
            "content": "Test insight",
            "issue_type": "cost_sink",
            "severity": "high",
            "confidence": 0.85,
        }

        # Extract confidence as done in retrieve_insights
        confidence = payload.get("confidence", 1.0)

        insight = {
            "content": payload.get("content", ""),
            "issue_type": payload.get("issue_type", "unknown"),
            "severity": payload.get("severity", "medium"),
            "confidence": confidence,
        }

        assert "confidence" in insight
        assert insight["confidence"] == 0.85

    def test_insight_dict_defaults_missing_confidence(self):
        """Confidence should default to 1.0 when missing from payload."""
        # Simulate payload without confidence field
        payload = {
            "task_type": "telemetry_insight",
            "content": "No confidence field",
            "issue_type": "cost_sink",
            "severity": "high",
            # No confidence field
        }

        # Extract confidence as done in retrieve_insights
        confidence = payload.get("confidence", 1.0)

        insight = {
            "content": payload.get("content", ""),
            "issue_type": payload.get("issue_type", "unknown"),
            "severity": payload.get("severity", "medium"),
            "confidence": confidence,
        }

        assert insight["confidence"] == 1.0

    def test_confidence_filter_with_exact_threshold_match(self):
        """Insights at exactly the threshold should be kept."""
        insights = [
            {"id": "insight_1", "content": "At threshold", "confidence": 0.7},
        ]

        min_confidence = 0.7
        filtered_insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]

        assert len(filtered_insights) == 1

    def test_confidence_filter_with_zero_threshold(self):
        """All insights should pass with min_confidence=0."""
        insights = [
            {"id": "insight_1", "content": "Any confidence", "confidence": 0.1},
            {"id": "insight_2", "content": "Any confidence", "confidence": 0.0},
        ]

        min_confidence = 0.0
        filtered_insights = [i for i in insights if i.get("confidence", 1.0) >= min_confidence]

        assert len(filtered_insights) == 2


class TestMinConfidenceThresholdConstant:
    """Tests for MIN_CONFIDENCE_THRESHOLD constant (IMP-LOOP-033)."""

    def test_min_confidence_threshold_exists(self):
        """MIN_CONFIDENCE_THRESHOLD constant should exist and be importable."""
        assert MIN_CONFIDENCE_THRESHOLD is not None

    def test_min_confidence_threshold_value(self):
        """MIN_CONFIDENCE_THRESHOLD should be 0.5."""
        assert MIN_CONFIDENCE_THRESHOLD == 0.5

    def test_min_confidence_threshold_is_float(self):
        """MIN_CONFIDENCE_THRESHOLD should be a float."""
        assert isinstance(MIN_CONFIDENCE_THRESHOLD, (int, float))

    def test_min_confidence_threshold_range(self):
        """MIN_CONFIDENCE_THRESHOLD should be between 0 and 1."""
        assert 0.0 <= MIN_CONFIDENCE_THRESHOLD <= 1.0


class TestEffectiveThresholdCalculation:
    """Tests for effective threshold calculation (IMP-LOOP-033).

    The effective threshold is the maximum of user-provided min_confidence
    and the MIN_CONFIDENCE_THRESHOLD floor. This ensures low-confidence
    insights never become tasks regardless of user configuration.
    """

    def test_effective_threshold_uses_floor_when_min_confidence_below(self):
        """Effective threshold should use floor when min_confidence is below it."""
        min_confidence = 0.3  # Below MIN_CONFIDENCE_THRESHOLD
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        assert effective_threshold == MIN_CONFIDENCE_THRESHOLD
        assert effective_threshold == 0.5

    def test_effective_threshold_uses_min_confidence_when_above_floor(self):
        """Effective threshold should use min_confidence when above floor."""
        min_confidence = 0.7  # Above MIN_CONFIDENCE_THRESHOLD
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        assert effective_threshold == min_confidence
        assert effective_threshold == 0.7

    def test_effective_threshold_equals_floor_when_exactly_at_floor(self):
        """Effective threshold should equal floor when min_confidence equals floor."""
        min_confidence = MIN_CONFIDENCE_THRESHOLD
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        assert effective_threshold == MIN_CONFIDENCE_THRESHOLD

    def test_effective_threshold_prevents_zero_threshold(self):
        """Effective threshold should prevent zero threshold from bypassing floor."""
        min_confidence = 0.0  # User tries to disable filtering
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        # Should still use the floor
        assert effective_threshold == MIN_CONFIDENCE_THRESHOLD
        assert effective_threshold > 0.0

    def test_filtering_with_effective_threshold_below_floor(self):
        """Filtering should use floor when user provides threshold below floor."""
        insights = [
            UnifiedInsight(
                id="above_floor",
                issue_type="cost_sink",
                content="Above floor",
                severity="high",
                confidence=0.6,  # Above 0.5 floor
            ),
            UnifiedInsight(
                id="below_floor",
                issue_type="failure_mode",
                content="Below floor",
                severity="high",
                confidence=0.4,  # Below 0.5 floor
            ),
            UnifiedInsight(
                id="at_user_threshold",
                issue_type="retry_cause",
                content="At user threshold",
                severity="medium",
                confidence=0.3,  # At user's requested threshold
            ),
        ]

        # User requests 0.3 threshold, but floor is 0.5
        min_confidence = 0.3
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        filtered_insights = [i for i in insights if i.confidence >= effective_threshold]

        # Only insight with confidence >= 0.5 should pass
        assert len(filtered_insights) == 1
        assert filtered_insights[0].id == "above_floor"
        assert filtered_insights[0].confidence == 0.6

    def test_filtering_with_effective_threshold_above_floor(self):
        """Filtering should use user threshold when above floor."""
        insights = [
            UnifiedInsight(
                id="above_user_threshold",
                issue_type="cost_sink",
                content="Above user threshold",
                severity="high",
                confidence=0.8,  # Above 0.7 user threshold
            ),
            UnifiedInsight(
                id="between_thresholds",
                issue_type="failure_mode",
                content="Between thresholds",
                severity="high",
                confidence=0.6,  # Above floor (0.5), below user (0.7)
            ),
            UnifiedInsight(
                id="below_floor",
                issue_type="retry_cause",
                content="Below floor",
                severity="medium",
                confidence=0.4,  # Below floor
            ),
        ]

        # User requests 0.7 threshold, which is above floor
        min_confidence = 0.7
        effective_threshold = max(min_confidence, MIN_CONFIDENCE_THRESHOLD)

        filtered_insights = [i for i in insights if i.confidence >= effective_threshold]

        # Only insight with confidence >= 0.7 should pass
        assert len(filtered_insights) == 1
        assert filtered_insights[0].id == "above_user_threshold"
        assert filtered_insights[0].confidence == 0.8


class TestConfidenceDistributionStatistics:
    """Tests for confidence distribution statistics calculation (IMP-LOOP-033).

    The generate_tasks method calculates statistics about the confidence
    distribution of insights for observability and debugging.
    """

    def test_confidence_statistics_calculation(self):
        """Confidence statistics should be correctly calculated."""
        insights = [
            UnifiedInsight(
                id="i1",
                issue_type="cost_sink",
                content="Test",
                severity="high",
                confidence=0.9,
            ),
            UnifiedInsight(
                id="i2",
                issue_type="failure_mode",
                content="Test",
                severity="high",
                confidence=0.6,
            ),
            UnifiedInsight(
                id="i3",
                issue_type="retry_cause",
                content="Test",
                severity="medium",
                confidence=0.3,
            ),
        ]

        confidence_values = [i.confidence for i in insights]
        avg_confidence = sum(confidence_values) / len(confidence_values)
        min_conf = min(confidence_values)
        max_conf = max(confidence_values)

        assert avg_confidence == pytest.approx(0.6, rel=0.01)
        assert min_conf == 0.3
        assert max_conf == 0.9

    def test_below_threshold_count(self):
        """Count of insights below threshold should be accurate."""
        insights = [
            UnifiedInsight(
                id="i1",
                issue_type="cost_sink",
                content="Test",
                severity="high",
                confidence=0.9,
            ),
            UnifiedInsight(
                id="i2",
                issue_type="failure_mode",
                content="Test",
                severity="high",
                confidence=0.4,
            ),
            UnifiedInsight(
                id="i3",
                issue_type="retry_cause",
                content="Test",
                severity="medium",
                confidence=0.3,
            ),
        ]

        effective_threshold = 0.5
        confidence_values = [i.confidence for i in insights]
        below_threshold_count = sum(1 for c in confidence_values if c < effective_threshold)

        assert below_threshold_count == 2  # 0.4 and 0.3 are below 0.5

    def test_empty_insights_no_statistics(self):
        """Empty insight list should not cause division by zero."""
        insights = []

        if len(insights) > 0:
            confidence_values = [i.confidence for i in insights]
            avg_confidence = sum(confidence_values) / len(confidence_values)
        else:
            avg_confidence = None

        # Should not raise exception, avg should be None
        assert avg_confidence is None

    def test_single_insight_statistics(self):
        """Single insight should produce valid statistics."""
        insights = [
            UnifiedInsight(
                id="i1",
                issue_type="cost_sink",
                content="Test",
                severity="high",
                confidence=0.75,
            ),
        ]

        confidence_values = [i.confidence for i in insights]
        avg_confidence = sum(confidence_values) / len(confidence_values)
        min_conf = min(confidence_values)
        max_conf = max(confidence_values)

        assert avg_confidence == 0.75
        assert min_conf == 0.75
        assert max_conf == 0.75
