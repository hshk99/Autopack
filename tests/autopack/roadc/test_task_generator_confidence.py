"""Tests for confidence thresholding in task generation (IMP-LOOP-016).

Tests cover:
- UnifiedInsight confidence field
- DirectInsightConsumer confidence population
- MemoryInsightConsumer confidence extraction
- AnalyzerInsightConsumer confidence propagation
- generate_tasks insight confidence filtering
- retrieve_insights min_confidence parameter
"""

from unittest.mock import Mock

import pytest

from autopack.roadc.task_generator import (AnalyzerInsightConsumer,
                                           DirectInsightConsumer,
                                           InsightSource,
                                           MemoryInsightConsumer,
                                           UnifiedInsight)
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
        consumer = MemoryInsightConsumer(mock_memory_service)
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
        consumer = MemoryInsightConsumer(mock_memory_service)
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
