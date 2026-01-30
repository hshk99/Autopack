"""Tests for IMP-LOOP-031: Task-to-Insight Correlation Engine.

Tests cover:
- InsightTaskCorrelation dataclass
- InsightEffectivenessStats dataclass
- InsightCorrelationEngine.record_task_creation()
- InsightCorrelationEngine.record_task_outcome()
- InsightCorrelationEngine.update_insight_confidence()
- High/low performer identification
- Correlation summary statistics
"""

from datetime import datetime, timezone
from unittest.mock import Mock


from autopack.task_generation.insight_correlation import (
    FAILURE_CONFIDENCE_PENALTY,
    MAX_CONFIDENCE,
    MIN_CONFIDENCE,
    MIN_SAMPLE_SIZE_FOR_UPDATE,
    SUCCESS_CONFIDENCE_BOOST,
    InsightCorrelationEngine,
    InsightEffectivenessStats,
    InsightTaskCorrelation,
)


class TestInsightTaskCorrelation:
    """Tests for InsightTaskCorrelation dataclass."""

    def test_correlation_creation(self):
        """InsightTaskCorrelation should be creatable with minimal fields."""
        correlation = InsightTaskCorrelation(
            insight_id="insight_001",
            task_id="TASK-ABC123",
        )

        assert correlation.insight_id == "insight_001"
        assert correlation.task_id == "TASK-ABC123"
        assert correlation.insight_source == "unknown"
        assert correlation.insight_type == "unknown"
        assert correlation.task_outcome is None
        assert correlation.confidence_before == 1.0

    def test_correlation_full_creation(self):
        """InsightTaskCorrelation should handle all fields."""
        correlation = InsightTaskCorrelation(
            insight_id="insight_002",
            task_id="TASK-DEF456",
            insight_source="direct",
            insight_type="cost_sink",
            confidence_before=0.85,
        )

        assert correlation.insight_id == "insight_002"
        assert correlation.task_id == "TASK-DEF456"
        assert correlation.insight_source == "direct"
        assert correlation.insight_type == "cost_sink"
        assert correlation.confidence_before == 0.85

    def test_correlation_to_dict(self):
        """InsightTaskCorrelation.to_dict should serialize all fields."""
        now = datetime.now(timezone.utc)
        correlation = InsightTaskCorrelation(
            insight_id="insight_003",
            task_id="TASK-GHI789",
            insight_source="memory",
            insight_type="failure_mode",
            created_at=now,
            task_outcome="success",
            outcome_timestamp=now,
            confidence_before=0.9,
            confidence_after=0.95,
        )

        data = correlation.to_dict()

        assert data["insight_id"] == "insight_003"
        assert data["task_id"] == "TASK-GHI789"
        assert data["insight_source"] == "memory"
        assert data["insight_type"] == "failure_mode"
        assert data["task_outcome"] == "success"
        assert data["confidence_before"] == 0.9
        assert data["confidence_after"] == 0.95


class TestInsightEffectivenessStats:
    """Tests for InsightEffectivenessStats dataclass."""

    def test_stats_creation(self):
        """InsightEffectivenessStats should be creatable."""
        stats = InsightEffectivenessStats(insight_id="insight_001")

        assert stats.insight_id == "insight_001"
        assert stats.total_tasks == 0
        assert stats.successful_tasks == 0
        assert stats.failed_tasks == 0
        assert stats.partial_tasks == 0
        assert stats.success_rate == 0.0
        assert stats.current_confidence == 1.0

    def test_stats_full_creation(self):
        """InsightEffectivenessStats should handle all fields."""
        stats = InsightEffectivenessStats(
            insight_id="insight_002",
            total_tasks=10,
            successful_tasks=7,
            failed_tasks=2,
            partial_tasks=1,
            success_rate=0.7,
            current_confidence=0.75,
        )

        assert stats.total_tasks == 10
        assert stats.successful_tasks == 7
        assert stats.failed_tasks == 2
        assert stats.partial_tasks == 1
        assert stats.success_rate == 0.7
        assert stats.current_confidence == 0.75


class TestRecordTaskCreation:
    """Tests for InsightCorrelationEngine.record_task_creation."""

    def test_record_task_creation_basic(self):
        """record_task_creation should create a correlation record."""
        engine = InsightCorrelationEngine()

        correlation = engine.record_task_creation(
            insight_id="insight_001",
            task_id="TASK-001",
        )

        assert correlation.insight_id == "insight_001"
        assert correlation.task_id == "TASK-001"
        assert engine.get_correlation("TASK-001") is correlation

    def test_record_task_creation_with_metadata(self):
        """record_task_creation should store all metadata."""
        engine = InsightCorrelationEngine()

        correlation = engine.record_task_creation(
            insight_id="insight_002",
            task_id="TASK-002",
            insight_source="direct",
            insight_type="cost_sink",
            confidence=0.85,
        )

        assert correlation.insight_source == "direct"
        assert correlation.insight_type == "cost_sink"
        assert correlation.confidence_before == 0.85

    def test_record_task_creation_tracks_by_insight(self):
        """record_task_creation should track multiple tasks per insight."""
        engine = InsightCorrelationEngine()

        engine.record_task_creation("insight_001", "TASK-001")
        engine.record_task_creation("insight_001", "TASK-002")
        engine.record_task_creation("insight_001", "TASK-003")

        tasks = engine.get_tasks_for_insight("insight_001")
        assert len(tasks) == 3
        assert set(tasks) == {"TASK-001", "TASK-002", "TASK-003"}

    def test_record_task_creation_initializes_stats(self):
        """record_task_creation should initialize insight stats."""
        engine = InsightCorrelationEngine()

        engine.record_task_creation(
            insight_id="insight_001",
            task_id="TASK-001",
            confidence=0.9,
        )

        stats = engine.get_insight_stats("insight_001")
        assert stats is not None
        assert stats.total_tasks == 1
        assert stats.current_confidence == 0.9


class TestRecordTaskOutcome:
    """Tests for InsightCorrelationEngine.record_task_outcome."""

    def test_record_outcome_success(self):
        """record_task_outcome should record success outcome."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001")

        correlation = engine.record_task_outcome("TASK-001", "success")

        assert correlation is not None
        assert correlation.task_outcome == "success"
        assert correlation.outcome_timestamp is not None

    def test_record_outcome_failure(self):
        """record_task_outcome should record failure outcome."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001")

        correlation = engine.record_task_outcome("TASK-001", "failure")

        assert correlation is not None
        assert correlation.task_outcome == "failure"

    def test_record_outcome_partial(self):
        """record_task_outcome should record partial outcome."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001")

        correlation = engine.record_task_outcome("TASK-001", "partial")

        assert correlation is not None
        assert correlation.task_outcome == "partial"

    def test_record_outcome_updates_stats(self):
        """record_task_outcome should update insight stats."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001")
        engine.record_task_creation("insight_001", "TASK-002")

        engine.record_task_outcome("TASK-001", "success")
        engine.record_task_outcome("TASK-002", "failure")

        stats = engine.get_insight_stats("insight_001")
        assert stats.successful_tasks == 1
        assert stats.failed_tasks == 1

    def test_record_outcome_invalid_outcome(self):
        """record_task_outcome should reject invalid outcomes."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001")

        result = engine.record_task_outcome("TASK-001", "invalid")

        assert result is None

    def test_record_outcome_task_not_found(self):
        """record_task_outcome should return None for unknown tasks."""
        engine = InsightCorrelationEngine()

        result = engine.record_task_outcome("NONEXISTENT", "success")

        assert result is None


class TestUpdateInsightConfidence:
    """Tests for InsightCorrelationEngine.update_insight_confidence."""

    def test_confidence_requires_min_samples(self):
        """update_insight_confidence should require minimum samples."""
        engine = InsightCorrelationEngine()
        engine.record_task_creation("insight_001", "TASK-001", confidence=0.8)

        # Record fewer than MIN_SAMPLE_SIZE_FOR_UPDATE outcomes
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE - 1):
            engine.record_task_creation("insight_001", f"TASK-{i+2}", confidence=0.8)
            engine.record_task_outcome(f"TASK-{i+2}", "success", auto_update_confidence=False)

        confidence = engine.update_insight_confidence("insight_001")

        # Should return original confidence due to insufficient samples
        assert confidence == 0.8

    def test_confidence_increases_on_success(self):
        """update_insight_confidence should increase on successful tasks."""
        engine = InsightCorrelationEngine()

        # Create and complete enough successful tasks
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE + 2):
            engine.record_task_creation("insight_001", f"TASK-{i}", confidence=0.5)
            engine.record_task_outcome(f"TASK-{i}", "success", auto_update_confidence=False)

        confidence = engine.update_insight_confidence("insight_001")

        # Confidence should be above base (0.5) due to successes
        assert confidence > 0.5

    def test_confidence_decreases_on_failure(self):
        """update_insight_confidence should decrease on failed tasks."""
        engine = InsightCorrelationEngine()

        # Create and fail enough tasks
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE + 2):
            engine.record_task_creation("insight_001", f"TASK-{i}", confidence=0.8)
            engine.record_task_outcome(f"TASK-{i}", "failure", auto_update_confidence=False)

        confidence = engine.update_insight_confidence("insight_001")

        # Confidence should be below base due to failures
        assert confidence < 0.5

    def test_confidence_bounded_by_min_max(self):
        """update_insight_confidence should respect MIN_CONFIDENCE and MAX_CONFIDENCE."""
        engine = InsightCorrelationEngine()

        # Create many failures to try to push below MIN_CONFIDENCE
        for i in range(20):
            engine.record_task_creation("insight_001", f"TASK-{i}", confidence=0.5)
            engine.record_task_outcome(f"TASK-{i}", "failure", auto_update_confidence=False)

        confidence = engine.update_insight_confidence("insight_001")

        assert confidence >= MIN_CONFIDENCE
        assert confidence <= MAX_CONFIDENCE

    def test_confidence_auto_update_on_outcome(self):
        """record_task_outcome with auto_update should update confidence."""
        engine = InsightCorrelationEngine()

        # Create enough tasks for confidence update
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE):
            engine.record_task_creation("insight_001", f"TASK-{i}", confidence=0.5)

        # Record outcomes with auto_update (default is True)
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE):
            correlation = engine.record_task_outcome(f"TASK-{i}", "success")
            if i == MIN_SAMPLE_SIZE_FOR_UPDATE - 1:
                # Last outcome should trigger confidence update
                assert correlation.confidence_after is not None

    def test_confidence_for_unknown_insight(self):
        """update_insight_confidence should return 1.0 for unknown insights."""
        engine = InsightCorrelationEngine()

        confidence = engine.update_insight_confidence("nonexistent")

        assert confidence == 1.0


class TestConfidencePersistence:
    """Tests for confidence persistence to memory service."""

    def test_persists_to_memory_service(self):
        """update_insight_confidence should persist to memory service."""
        mock_memory = Mock()
        mock_memory.update_insight_confidence = Mock(return_value=True)

        engine = InsightCorrelationEngine(memory_service=mock_memory)

        # Create and complete enough tasks
        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE):
            engine.record_task_creation("insight_001", f"TASK-{i}", confidence=0.5)
            engine.record_task_outcome(f"TASK-{i}", "success", auto_update_confidence=False)

        engine.update_insight_confidence("insight_001")

        mock_memory.update_insight_confidence.assert_called()
        call_args = mock_memory.update_insight_confidence.call_args
        assert call_args[0][0] == "insight_001"  # insight_id

    def test_handles_missing_memory_service(self):
        """update_insight_confidence should handle missing memory service."""
        engine = InsightCorrelationEngine()

        for i in range(MIN_SAMPLE_SIZE_FOR_UPDATE):
            engine.record_task_creation("insight_001", f"TASK-{i}")
            engine.record_task_outcome(f"TASK-{i}", "success", auto_update_confidence=False)

        # Should not raise even without memory service
        confidence = engine.update_insight_confidence("insight_001")
        assert confidence > 0

    def test_set_memory_service(self):
        """set_memory_service should allow late binding."""
        engine = InsightCorrelationEngine()
        mock_memory = Mock()

        engine.set_memory_service(mock_memory)

        assert engine._memory_service is mock_memory


class TestHighLowPerformers:
    """Tests for identifying high and low performing insights."""

    def test_high_performers_identification(self):
        """get_high_performing_insights should return high success insights."""
        engine = InsightCorrelationEngine()

        # Insight with high success rate
        for i in range(5):
            engine.record_task_creation("high_insight", f"TASK-H{i}")
            engine.record_task_outcome(f"TASK-H{i}", "success", auto_update_confidence=False)

        # Insight with low success rate
        for i in range(5):
            engine.record_task_creation("low_insight", f"TASK-L{i}")
            engine.record_task_outcome(f"TASK-L{i}", "failure", auto_update_confidence=False)

        high_performers = engine.get_high_performing_insights(
            min_success_rate=0.7,
            min_tasks=3,
        )

        assert len(high_performers) == 1
        assert high_performers[0].insight_id == "high_insight"

    def test_low_performers_identification(self):
        """get_low_performing_insights should return low success insights."""
        engine = InsightCorrelationEngine()

        # Insight with high success rate
        for i in range(5):
            engine.record_task_creation("high_insight", f"TASK-H{i}")
            engine.record_task_outcome(f"TASK-H{i}", "success", auto_update_confidence=False)

        # Insight with low success rate
        for i in range(5):
            engine.record_task_creation("low_insight", f"TASK-L{i}")
            engine.record_task_outcome(f"TASK-L{i}", "failure", auto_update_confidence=False)

        low_performers = engine.get_low_performing_insights(
            max_success_rate=0.3,
            min_tasks=3,
        )

        assert len(low_performers) == 1
        assert low_performers[0].insight_id == "low_insight"

    def test_performers_require_min_tasks(self):
        """High/low performer detection should require minimum tasks."""
        engine = InsightCorrelationEngine()

        # Insight with only 2 tasks
        engine.record_task_creation("insight_001", "TASK-001")
        engine.record_task_outcome("TASK-001", "success", auto_update_confidence=False)
        engine.record_task_creation("insight_001", "TASK-002")
        engine.record_task_outcome("TASK-002", "success", auto_update_confidence=False)

        high_performers = engine.get_high_performing_insights(
            min_success_rate=0.7,
            min_tasks=3,
        )

        assert len(high_performers) == 0


class TestCorrelationSummary:
    """Tests for correlation summary statistics."""

    def test_empty_summary(self):
        """get_correlation_summary should handle empty engine."""
        engine = InsightCorrelationEngine()

        summary = engine.get_correlation_summary()

        assert summary["total_correlations"] == 0
        assert summary["total_insights"] == 0
        assert summary["outcomes_recorded"] == 0
        assert summary["pending_outcomes"] == 0
        assert summary["avg_confidence"] == 1.0

    def test_summary_with_data(self):
        """get_correlation_summary should aggregate statistics."""
        engine = InsightCorrelationEngine()

        # Create correlations from multiple insights
        engine.record_task_creation("insight_001", "TASK-001", insight_source="direct")
        engine.record_task_creation("insight_001", "TASK-002", insight_source="direct")
        engine.record_task_creation("insight_002", "TASK-003", insight_source="memory")

        engine.record_task_outcome("TASK-001", "success", auto_update_confidence=False)
        engine.record_task_outcome("TASK-002", "failure", auto_update_confidence=False)
        # TASK-003 left pending

        summary = engine.get_correlation_summary()

        assert summary["total_correlations"] == 3
        assert summary["total_insights"] == 2
        assert summary["outcomes_recorded"] == 2
        assert summary["pending_outcomes"] == 1
        assert summary["by_outcome"]["success"] == 1
        assert summary["by_outcome"]["failure"] == 1
        assert summary["by_source"]["direct"] == 2
        assert summary["by_source"]["memory"] == 1


class TestThresholdConstants:
    """Tests for threshold constants."""

    def test_success_confidence_boost(self):
        """SUCCESS_CONFIDENCE_BOOST should be positive."""
        assert SUCCESS_CONFIDENCE_BOOST > 0

    def test_failure_confidence_penalty(self):
        """FAILURE_CONFIDENCE_PENALTY should be positive."""
        assert FAILURE_CONFIDENCE_PENALTY > 0

    def test_min_confidence_valid(self):
        """MIN_CONFIDENCE should be between 0 and 1."""
        assert 0 < MIN_CONFIDENCE < 1

    def test_max_confidence_valid(self):
        """MAX_CONFIDENCE should be 1.0."""
        assert MAX_CONFIDENCE == 1.0

    def test_min_sample_size_reasonable(self):
        """MIN_SAMPLE_SIZE_FOR_UPDATE should be at least 3."""
        assert MIN_SAMPLE_SIZE_FOR_UPDATE >= 3
