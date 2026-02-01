"""Tests for Memory-to-Task Promoter.

IMP-LOOP-032: Tests for MemoryTaskPromoter which scans memory for recurring
failure patterns and automatically promotes them to tasks.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from autopack.memory.task_promoter import (DEFAULT_PROMOTION_THRESHOLD,
                                           MemoryTaskPromoter,
                                           PromotableInsight, PromotionResult)


class TestPromotableInsight:
    """Tests for PromotableInsight dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a PromotableInsight with required fields."""
        insight = PromotableInsight(
            insight_id="test-insight-001",
            content="Test failure pattern",
        )
        assert insight.insight_id == "test-insight-001"
        assert insight.content == "Test failure pattern"
        assert insight.issue_type == "unknown"
        assert insight.occurrence_count == 1
        assert insight.confidence == 1.0
        assert insight.severity == "medium"

    def test_full_creation(self) -> None:
        """Test creating a PromotableInsight with all fields."""
        last_occurrence = datetime.now(timezone.utc)
        insight = PromotableInsight(
            insight_id="test-insight-002",
            content="Recurring error in API calls",
            issue_type="failure_mode",
            occurrence_count=5,
            confidence=0.85,
            last_occurrence=last_occurrence,
            severity="high",
            source_runs=["run-001", "run-002"],
            details={"error_code": 500},
        )
        assert insight.insight_id == "test-insight-002"
        assert insight.issue_type == "failure_mode"
        assert insight.occurrence_count == 5
        assert insight.confidence == 0.85
        assert insight.last_occurrence == last_occurrence
        assert insight.severity == "high"
        assert len(insight.source_runs) == 2
        assert insight.details["error_code"] == 500

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        insight = PromotableInsight(
            insight_id="test-insight-003",
            content="Test content",
            occurrence_count=3,
        )
        result = insight.to_dict()
        assert result["insight_id"] == "test-insight-003"
        assert result["content"] == "Test content"
        assert result["occurrence_count"] == 3
        assert "last_occurrence" in result


class TestPromotionResult:
    """Tests for PromotionResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful promotion result."""
        result = PromotionResult(
            insight_id="insight-001",
            success=True,
            task_id="TASK-ABC12345",
        )
        assert result.insight_id == "insight-001"
        assert result.success is True
        assert result.task_id == "TASK-ABC12345"
        assert result.error is None
        assert result.promoted_at is not None

    def test_failed_result(self) -> None:
        """Test creating a failed promotion result."""
        result = PromotionResult(
            insight_id="insight-002",
            success=False,
            error="Task generator not configured",
        )
        assert result.insight_id == "insight-002"
        assert result.success is False
        assert result.task_id is None
        assert result.error == "Task generator not configured"


class TestMemoryTaskPromoterInit:
    """Tests for MemoryTaskPromoter initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization."""
        promoter = MemoryTaskPromoter()
        assert promoter._memory_service is None
        assert promoter._task_generator is None
        assert promoter._correlation_engine is None
        assert promoter._threshold == DEFAULT_PROMOTION_THRESHOLD
        assert promoter._project_id == "default"
        assert len(promoter._promoted_insights) == 0

    def test_custom_initialization(self) -> None:
        """Test initialization with custom parameters."""
        mock_memory = MagicMock()
        mock_generator = MagicMock()
        mock_engine = MagicMock()

        promoter = MemoryTaskPromoter(
            memory_service=mock_memory,
            task_generator=mock_generator,
            correlation_engine=mock_engine,
            promotion_threshold=5,
            project_id="test-project",
        )

        assert promoter._memory_service == mock_memory
        assert promoter._task_generator == mock_generator
        assert promoter._correlation_engine == mock_engine
        assert promoter._threshold == 5
        assert promoter._project_id == "test-project"

    def test_set_services(self) -> None:
        """Test setting services after initialization."""
        promoter = MemoryTaskPromoter()

        mock_memory = MagicMock()
        mock_generator = MagicMock()
        mock_engine = MagicMock()

        promoter.set_memory_service(mock_memory)
        promoter.set_task_generator(mock_generator)
        promoter.set_correlation_engine(mock_engine)

        assert promoter._memory_service == mock_memory
        assert promoter._task_generator == mock_generator
        assert promoter._correlation_engine == mock_engine


class TestScanForPromotableInsights:
    """Tests for scan_for_promotable_insights method."""

    def test_no_memory_service(self) -> None:
        """Test scanning without memory service configured."""
        promoter = MemoryTaskPromoter()
        result = promoter.scan_for_promotable_insights()
        assert result == []

    def test_no_high_occurrence_insights(self) -> None:
        """Test scanning when no insights meet the threshold."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "Low occurrence insight",
                "payload": {"occurrence_count": 1},
            },
            {
                "id": "insight-002",
                "content": "Another low occurrence",
                "payload": {"occurrence_count": 2},
            },
        ]

        promoter = MemoryTaskPromoter(
            memory_service=mock_memory,
            promotion_threshold=3,
        )

        result = promoter.scan_for_promotable_insights()
        assert len(result) == 0

    def test_finds_high_occurrence_insights(self) -> None:
        """Test finding insights that exceed the threshold."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "High occurrence insight",
                "issue_type": "failure_mode",
                "severity": "high",
                "confidence": 0.9,
                "payload": {
                    "occurrence_count": 5,
                    "confidence": 0.9,
                },
            },
            {
                "id": "insight-002",
                "content": "Another high occurrence",
                "issue_type": "retry_cause",
                "severity": "medium",
                "confidence": 0.8,
                "payload": {
                    "occurrence_count": 4,
                    "confidence": 0.8,
                },
            },
            {
                "id": "insight-003",
                "content": "Low occurrence",
                "payload": {"occurrence_count": 1},
            },
        ]

        promoter = MemoryTaskPromoter(
            memory_service=mock_memory,
            promotion_threshold=3,
        )

        result = promoter.scan_for_promotable_insights()
        assert len(result) == 2
        # Should be sorted by occurrence count descending
        assert result[0].occurrence_count == 5
        assert result[1].occurrence_count == 4

    def test_excludes_low_confidence(self) -> None:
        """Test that low-confidence insights are excluded."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "High occurrence but low confidence",
                "payload": {
                    "occurrence_count": 10,
                    "confidence": 0.3,  # Below MIN_CONFIDENCE_FOR_PROMOTION
                },
            },
        ]

        promoter = MemoryTaskPromoter(memory_service=mock_memory)
        result = promoter.scan_for_promotable_insights()
        assert len(result) == 0

    def test_excludes_already_promoted(self) -> None:
        """Test that already-promoted insights are excluded."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "Previously promoted",
                "confidence": 0.9,
                "payload": {
                    "occurrence_count": 5,
                    "confidence": 0.9,
                },
            },
        ]

        promoter = MemoryTaskPromoter(memory_service=mock_memory)
        # Pre-mark as promoted
        promoter._promoted_insights.add("insight-001")

        result = promoter.scan_for_promotable_insights()
        assert len(result) == 0

    def test_includes_already_promoted_when_disabled(self) -> None:
        """Test that already-promoted insights are included when exclude_promoted=False."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "Previously promoted",
                "confidence": 0.9,
                "payload": {
                    "occurrence_count": 5,
                    "confidence": 0.9,
                },
            },
        ]

        promoter = MemoryTaskPromoter(memory_service=mock_memory)
        promoter._promoted_insights.add("insight-001")

        result = promoter.scan_for_promotable_insights(exclude_promoted=False)
        assert len(result) == 1

    def test_respects_limit(self) -> None:
        """Test that the limit parameter is respected."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": f"insight-{i}",
                "content": f"Insight {i}",
                "confidence": 0.9,
                "payload": {"occurrence_count": 10 - i, "confidence": 0.9},
            }
            for i in range(10)
        ]

        promoter = MemoryTaskPromoter(memory_service=mock_memory)
        result = promoter.scan_for_promotable_insights(limit=3)
        assert len(result) == 3


class TestPromoteInsightToTask:
    """Tests for promote_insight_to_task method."""

    def test_no_task_generator(self) -> None:
        """Test promoting without task generator configured."""
        promoter = MemoryTaskPromoter()
        insight = PromotableInsight(
            insight_id="insight-001",
            content="Test insight",
            occurrence_count=5,
        )

        result = promoter.promote_insight_to_task(insight)
        assert result.success is False
        assert "not configured" in result.error

    def test_successful_promotion(self) -> None:
        """Test successful promotion of an insight to a task."""
        mock_memory = MagicMock()
        mock_generator = MagicMock()
        mock_correlation = MagicMock()

        # Mock the task generation
        mock_task = MagicMock()
        mock_task.task_id = "TASK-TEST001"
        mock_task.description = "Generated task"
        mock_generator._pattern_to_task.return_value = mock_task
        mock_generator.persist_tasks.return_value = 1

        promoter = MemoryTaskPromoter(
            memory_service=mock_memory,
            task_generator=mock_generator,
            correlation_engine=mock_correlation,
        )

        insight = PromotableInsight(
            insight_id="insight-001",
            content="Recurring failure in API",
            issue_type="failure_mode",
            occurrence_count=5,
            confidence=0.85,
        )

        result = promoter.promote_insight_to_task(insight, run_id="test-run-001")

        assert result.success is True
        assert result.task_id == "TASK-TEST001"
        assert "insight-001" in promoter._promoted_insights

        # Verify correlation was recorded
        mock_correlation.record_task_creation.assert_called_once()

    def test_promotion_failure_handling(self) -> None:
        """Test handling of promotion failures."""
        mock_generator = MagicMock()
        mock_generator._pattern_to_task.side_effect = Exception("Task generation failed")

        promoter = MemoryTaskPromoter(task_generator=mock_generator)

        insight = PromotableInsight(
            insight_id="insight-001",
            content="Test insight",
            occurrence_count=5,
        )

        result = promoter.promote_insight_to_task(insight)
        assert result.success is False
        assert "Task generation failed" in result.error


class TestPromoteAllEligible:
    """Tests for promote_all_eligible method."""

    def test_no_eligible_insights(self) -> None:
        """Test when no insights are eligible for promotion."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = []

        promoter = MemoryTaskPromoter(memory_service=mock_memory)
        results = promoter.promote_all_eligible()
        assert len(results) == 0

    def test_promotes_all_eligible(self) -> None:
        """Test promoting all eligible insights."""
        mock_memory = MagicMock()
        mock_memory.retrieve_insights.return_value = [
            {
                "id": "insight-001",
                "content": "First insight",
                "confidence": 0.9,
                "payload": {"occurrence_count": 5, "confidence": 0.9},
            },
            {
                "id": "insight-002",
                "content": "Second insight",
                "confidence": 0.8,
                "payload": {"occurrence_count": 4, "confidence": 0.8},
            },
        ]

        mock_generator = MagicMock()
        mock_task = MagicMock()
        mock_task.task_id = "TASK-001"
        mock_task.description = "Test"
        mock_generator._pattern_to_task.return_value = mock_task
        mock_generator.persist_tasks.return_value = 1

        promoter = MemoryTaskPromoter(
            memory_service=mock_memory,
            task_generator=mock_generator,
        )

        results = promoter.promote_all_eligible(run_id="test-run")
        assert len(results) == 2
        # Both should succeed
        assert all(r.success for r in results)


class TestPromotionStats:
    """Tests for promotion statistics and tracking."""

    def test_get_promotion_stats(self) -> None:
        """Test getting promotion statistics."""
        promoter = MemoryTaskPromoter(
            promotion_threshold=5,
            project_id="test-project",
        )
        promoter._promoted_insights.add("insight-001")
        promoter._promoted_insights.add("insight-002")

        stats = promoter.get_promotion_stats()
        assert stats["promoted_count"] == 2
        assert "insight-001" in stats["promoted_insight_ids"]
        assert "insight-002" in stats["promoted_insight_ids"]
        assert stats["threshold"] == 5
        assert stats["project_id"] == "test-project"

    def test_clear_promotion_history(self) -> None:
        """Test clearing promotion history."""
        promoter = MemoryTaskPromoter()
        promoter._promoted_insights.add("insight-001")
        promoter._promoted_insights.add("insight-002")

        count = promoter.clear_promotion_history()
        assert count == 2
        assert len(promoter._promoted_insights) == 0

    def test_is_already_promoted(self) -> None:
        """Test checking if an insight is already promoted."""
        promoter = MemoryTaskPromoter()
        promoter._promoted_insights.add("insight-001")

        assert promoter.is_already_promoted("insight-001") is True
        assert promoter.is_already_promoted("insight-002") is False


class TestSeverityCalculation:
    """Tests for severity score calculation."""

    def test_high_severity_base(self) -> None:
        """Test severity calculation for high severity insight."""
        promoter = MemoryTaskPromoter(promotion_threshold=3)
        insight = PromotableInsight(
            insight_id="test",
            content="Test",
            severity="high",
            occurrence_count=3,
            confidence=0.7,
        )
        score = promoter._calculate_severity_score(insight)
        # High base (8) + no occurrence boost (3-3=0) + no confidence boost (<0.8)
        assert score == 8

    def test_occurrence_boost(self) -> None:
        """Test that occurrence count boosts severity."""
        promoter = MemoryTaskPromoter(promotion_threshold=3)
        insight = PromotableInsight(
            insight_id="test",
            content="Test",
            severity="medium",
            occurrence_count=6,  # 3 above threshold
            confidence=0.7,
        )
        score = promoter._calculate_severity_score(insight)
        # Medium base (5) + occurrence boost (min(6-3, 3)=3) + no confidence boost
        assert score == 8

    def test_confidence_boost(self) -> None:
        """Test that high confidence boosts severity."""
        promoter = MemoryTaskPromoter(promotion_threshold=3)
        insight = PromotableInsight(
            insight_id="test",
            content="Test",
            severity="low",
            occurrence_count=3,
            confidence=0.9,  # Above 0.8 threshold
        )
        score = promoter._calculate_severity_score(insight)
        # Low base (2) + no occurrence boost + confidence boost (1)
        assert score == 3

    def test_severity_capped_at_10(self) -> None:
        """Test that severity is capped at 10."""
        promoter = MemoryTaskPromoter(promotion_threshold=3)
        insight = PromotableInsight(
            insight_id="test",
            content="Test",
            severity="high",
            occurrence_count=10,  # High occurrence
            confidence=0.95,  # High confidence
        )
        score = promoter._calculate_severity_score(insight)
        # Should be capped at 10
        assert score == 10
