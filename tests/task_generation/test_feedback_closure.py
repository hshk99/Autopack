"""Tests for IMP-LOOP-019: Task Effectiveness Feedback Closure.

Tests the feedback loop where task completion telemetry is used to improve
future task generation by factoring historical effectiveness into priority
calculation and insight conversion.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopack.task_generation.insight_to_task import InsightToTaskGenerator
from autopack.task_generation.priority_engine import PriorityEngine
from autopack.telemetry.analyzer import TaskEffectivenessStats


@pytest.fixture
def mock_learning_db() -> MagicMock:
    """Create a mock LearningDatabase for testing."""
    db = MagicMock()
    db.get_success_rate.return_value = 0.7
    db.get_likely_blockers.return_value = []
    db.get_historical_patterns.return_value = {
        "top_blocking_reasons": [],
        "category_success_rates": {},
        "recent_trends": {"sample_size": 0},
        "improvement_outcome_summary": {},
        "total_improvements_tracked": 0,
        "total_cycles_tracked": 0,
    }
    return db


@pytest.fixture
def sample_effectiveness_stats() -> TaskEffectivenessStats:
    """Create sample TaskEffectivenessStats for testing."""
    return TaskEffectivenessStats(
        total_completed=100,
        successful_tasks=75,
        failed_tasks=25,
        success_rate=0.75,
        targets_achieved=60,
        targets_missed=40,
        target_achievement_rate=0.60,
        avg_improvement_pct=15.5,
        avg_execution_duration_ms=5000.0,
        effectiveness_by_type={
            "telemetry": {"success_rate": 0.90, "target_rate": 0.85, "total": 20},
            "memory": {"success_rate": 0.50, "target_rate": 0.40, "total": 10},
            "slot_reliability": {"success_rate": 0.80, "target_rate": 0.70, "total": 15},
            "cost_sink": {"success_rate": 0.60, "target_rate": 0.50, "total": 8},
        },
        effectiveness_by_priority={
            "critical": {"success_rate": 0.85, "target_rate": 0.80, "total": 25},
            "high": {"success_rate": 0.75, "target_rate": 0.65, "total": 35},
            "medium": {"success_rate": 0.65, "target_rate": 0.55, "total": 30},
            "low": {"success_rate": 0.45, "target_rate": 0.35, "total": 10},
        },
    )


@pytest.fixture
def low_effectiveness_stats() -> TaskEffectivenessStats:
    """Create TaskEffectivenessStats with low success rates."""
    return TaskEffectivenessStats(
        total_completed=50,
        successful_tasks=15,
        failed_tasks=35,
        success_rate=0.30,
        targets_achieved=10,
        targets_missed=40,
        target_achievement_rate=0.20,
        avg_improvement_pct=5.0,
        avg_execution_duration_ms=8000.0,
        effectiveness_by_type={
            "cost_sink": {"success_rate": 0.20, "target_rate": 0.10, "total": 10},
            "failure_mode": {"success_rate": 0.30, "target_rate": 0.20, "total": 15},
        },
        effectiveness_by_priority={
            "critical": {"success_rate": 0.40, "target_rate": 0.30, "total": 10},
            "high": {"success_rate": 0.30, "target_rate": 0.20, "total": 20},
        },
    )


@pytest.fixture
def priority_engine_with_stats(
    mock_learning_db: MagicMock,
    sample_effectiveness_stats: TaskEffectivenessStats,
) -> PriorityEngine:
    """Create a PriorityEngine with effectiveness stats."""
    engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)
    return engine


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def mock_analyzer() -> MagicMock:
    """Create a mock TelemetryAnalyzer."""
    analyzer = MagicMock()
    analyzer.generate_insights.return_value = {
        "health_score": 0.85,
        "prioritized_actions": [
            {
                "source": "slot_reliability",
                "slot_id": 5,
                "escalation_rate": 0.4,
                "action": "Investigate slot 5 reliability",
                "severity": "high",
            },
            {
                "source": "cost_sink",
                "phase_type": "build",
                "action": "Optimize build phase cost",
                "severity": "medium",
            },
        ],
        "slot_reliability": {"problematic_slots": []},
        "nudge_effectiveness": {"escalation_patterns": []},
    }
    return analyzer


class TestPriorityEngineWithEffectivenessStats:
    """Tests for PriorityEngine with TaskEffectivenessStats integration."""

    def test_init_with_effectiveness_stats(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test engine initializes with effectiveness stats."""
        engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)
        assert engine._effectiveness_stats is sample_effectiveness_stats

    def test_init_without_effectiveness_stats(
        self,
        mock_learning_db: MagicMock,
    ) -> None:
        """Test engine works without effectiveness stats."""
        engine = PriorityEngine(mock_learning_db)
        assert engine._effectiveness_stats is None

    def test_set_effectiveness_stats(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test setting effectiveness stats after init."""
        engine = PriorityEngine(mock_learning_db)
        assert engine._effectiveness_stats is None

        engine.set_effectiveness_stats(sample_effectiveness_stats)
        assert engine._effectiveness_stats is sample_effectiveness_stats

    def test_get_effectiveness_factor_no_stats(
        self,
        mock_learning_db: MagicMock,
    ) -> None:
        """Test effectiveness factor returns 1.0 when no stats available."""
        engine = PriorityEngine(mock_learning_db)
        imp = {"imp_id": "IMP-TEL-001", "priority": "high"}
        factor = engine.get_effectiveness_factor(imp)
        assert factor == 1.0

    def test_get_effectiveness_factor_by_type(
        self,
        priority_engine_with_stats: PriorityEngine,
    ) -> None:
        """Test effectiveness factor uses type-specific rates."""
        # Telemetry has high success rate (0.90)
        tel_imp = {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "high"}
        tel_factor = priority_engine_with_stats.get_effectiveness_factor(tel_imp)

        # Memory has low success rate (0.50)
        mem_imp = {"imp_id": "IMP-MEM-001", "category": "memory", "priority": "high"}
        mem_factor = priority_engine_with_stats.get_effectiveness_factor(mem_imp)

        # Telemetry should have higher factor
        assert tel_factor > mem_factor

    def test_get_effectiveness_factor_by_priority(
        self,
        priority_engine_with_stats: PriorityEngine,
    ) -> None:
        """Test effectiveness factor considers priority-based rates."""
        # Critical has higher success rate
        critical_imp = {"imp_id": "IMP-GEN-001", "priority": "critical"}
        critical_factor = priority_engine_with_stats.get_effectiveness_factor(critical_imp)

        # Low has lower success rate
        low_imp = {"imp_id": "IMP-GEN-002", "priority": "low"}
        low_factor = priority_engine_with_stats.get_effectiveness_factor(low_imp)

        assert critical_factor > low_factor

    def test_get_effectiveness_factor_range(
        self,
        priority_engine_with_stats: PriorityEngine,
    ) -> None:
        """Test effectiveness factor stays within expected range [0.5, 1.2]."""
        test_cases = [
            {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "critical"},
            {"imp_id": "IMP-MEM-001", "category": "memory", "priority": "low"},
            {"imp_id": "IMP-GEN-001", "priority": "medium"},
        ]

        for imp in test_cases:
            factor = priority_engine_with_stats.get_effectiveness_factor(imp)
            assert 0.5 <= factor <= 1.2, f"Factor {factor} out of range for {imp}"

    def test_calculate_priority_score_includes_effectiveness(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test priority score calculation includes effectiveness factor."""
        # Engine without effectiveness stats
        engine_no_stats = PriorityEngine(mock_learning_db)
        imp = {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "high"}
        score_no_stats = engine_no_stats.calculate_priority_score(imp)

        # Engine with effectiveness stats
        engine_with_stats = PriorityEngine(mock_learning_db, sample_effectiveness_stats)
        score_with_stats = engine_with_stats.calculate_priority_score(imp)

        # Scores should differ (telemetry has good effectiveness)
        assert score_no_stats != score_with_stats

    def test_high_effectiveness_boosts_score(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test that high effectiveness increases priority score."""
        engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)

        # Telemetry has high effectiveness (0.90)
        tel_imp = {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "medium"}
        tel_score = engine.calculate_priority_score(tel_imp)

        # Memory has lower effectiveness (0.50)
        mem_imp = {"imp_id": "IMP-MEM-001", "category": "memory", "priority": "medium"}
        mem_score = engine.calculate_priority_score(mem_imp)

        assert tel_score > mem_score

    def test_low_effectiveness_reduces_score(
        self,
        mock_learning_db: MagicMock,
        low_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test that low effectiveness reduces priority score."""
        # Engine with low effectiveness stats
        engine_low = PriorityEngine(mock_learning_db, low_effectiveness_stats)

        # Engine without effectiveness stats (neutral)
        engine_neutral = PriorityEngine(mock_learning_db)

        imp = {"imp_id": "IMP-COST-001", "category": "cost_sink", "priority": "high"}

        score_low = engine_low.calculate_priority_score(imp)
        score_neutral = engine_neutral.calculate_priority_score(imp)

        # Low effectiveness should result in lower score
        assert score_low < score_neutral

    def test_rank_improvements_with_effectiveness(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test improvement ranking considers effectiveness data."""
        engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)

        improvements = [
            {"imp_id": "IMP-MEM-001", "category": "memory", "priority": "high"},
            {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "high"},
        ]

        ranked = engine.rank_improvements(improvements, include_scores=True)

        # Telemetry should rank higher due to better effectiveness
        assert ranked[0]["imp_id"] == "IMP-TEL-001"
        assert ranked[1]["imp_id"] == "IMP-MEM-001"


class TestInsightToTaskGeneratorWithEffectivenessStats:
    """Tests for InsightToTaskGenerator with TaskEffectivenessStats integration."""

    def test_init_with_effectiveness_stats(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test generator initializes with effectiveness stats."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)
        assert generator._effectiveness_stats is sample_effectiveness_stats

    def test_init_without_effectiveness_stats(
        self,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test generator works without effectiveness stats."""
        generator = InsightToTaskGenerator(mock_analyzer)
        assert generator._effectiveness_stats is None

    def test_set_effectiveness_stats(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test setting effectiveness stats after init."""
        generator = InsightToTaskGenerator(mock_analyzer)
        assert generator._effectiveness_stats is None

        generator.set_effectiveness_stats(sample_effectiveness_stats)
        assert generator._effectiveness_stats is sample_effectiveness_stats

    def test_get_success_rate_for_insight_type_no_stats(
        self,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test success rate returns 1.0 when no stats available."""
        generator = InsightToTaskGenerator(mock_analyzer)
        rate = generator.get_success_rate_for_insight_type("slot_reliability")
        assert rate == 1.0

    def test_get_success_rate_for_known_type(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test success rate for known insight type."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)

        # slot_reliability has success_rate 0.80
        rate = generator.get_success_rate_for_insight_type("slot_reliability")
        assert rate == 0.80

    def test_get_success_rate_for_unknown_type(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test success rate falls back to overall rate for unknown type."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)

        # Unknown type should fall back to overall success rate (0.75)
        rate = generator.get_success_rate_for_insight_type("unknown_type")
        assert rate == 0.75  # Falls back to overall success rate

    def test_format_as_imp_includes_confidence(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test IMP entry includes confidence field."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)

        insight = {"source": "slot_reliability", "action": "Test action"}
        imp = generator.format_as_imp(insight)

        assert "confidence" in imp
        assert "historical_success_rate" in imp

    def test_format_as_imp_confidence_adjusted_by_success_rate(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test confidence is adjusted by historical success rate."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)

        # slot_reliability has 80% success rate
        insight_high = {"source": "slot_reliability", "action": "Test", "confidence": 1.0}
        imp_high = generator.format_as_imp(insight_high)

        # cost_sink has 60% success rate
        insight_low = {"source": "cost_sink", "action": "Test", "confidence": 1.0}
        imp_low = generator.format_as_imp(insight_low)

        # Higher success rate should result in higher confidence
        assert imp_high["confidence"] > imp_low["confidence"]

    def test_format_as_imp_includes_historical_rate(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test IMP includes historical success rate in output."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)

        insight = {"source": "slot_reliability", "action": "Test"}
        imp = generator.format_as_imp(insight)

        assert imp["historical_success_rate"] == 0.80

    def test_format_as_imp_adds_note_for_low_success_rate(
        self,
        mock_analyzer: MagicMock,
        low_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test description includes note when historical success rate is low."""
        generator = InsightToTaskGenerator(mock_analyzer, low_effectiveness_stats)

        # cost_sink has only 20% success rate in low_effectiveness_stats
        insight = {"source": "cost_sink", "action": "Test action"}
        imp = generator.format_as_imp(insight)

        # Description should include warning note
        assert "Historical success rate" in imp["description"] or "20%" in imp["description"]

    def test_generate_improvements_with_effectiveness(
        self,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test improvements include effectiveness feedback data."""
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)
        improvements = generator.generate_improvements_from_insights()

        # All improvements should have confidence and historical_success_rate
        for imp in improvements:
            assert "confidence" in imp
            assert "historical_success_rate" in imp
            assert 0.0 <= imp["confidence"] <= 1.0
            assert 0.0 <= imp["historical_success_rate"] <= 1.0


class TestFeedbackClosureIntegration:
    """Integration tests for the complete feedback closure loop."""

    def test_feedback_loop_affects_task_ranking(
        self,
        mock_learning_db: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test that effectiveness feedback changes task ranking."""
        engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)

        # Two tasks with same priority but different categories
        improvements = [
            {
                "imp_id": "IMP-MEM-001",
                "category": "memory",  # 50% success rate
                "title": "Memory improvement",
                "priority": "high",
            },
            {
                "imp_id": "IMP-TEL-001",
                "category": "telemetry",  # 90% success rate
                "title": "Telemetry improvement",
                "priority": "high",
            },
        ]

        ranked = engine.rank_improvements(improvements, include_scores=True)

        # Telemetry should be ranked higher due to better effectiveness
        assert ranked[0]["imp_id"] == "IMP-TEL-001"

    def test_feedback_loop_comprehensive(
        self,
        mock_learning_db: MagicMock,
        mock_analyzer: MagicMock,
        sample_effectiveness_stats: TaskEffectivenessStats,
    ) -> None:
        """Test complete feedback loop from insight to prioritized task."""
        # Step 1: Generate tasks from insights with effectiveness data
        generator = InsightToTaskGenerator(mock_analyzer, sample_effectiveness_stats)
        improvements = generator.generate_improvements_from_insights()

        assert len(improvements) > 0

        # Step 2: Verify improvements have feedback data
        for imp in improvements:
            assert "confidence" in imp
            assert "historical_success_rate" in imp

        # Step 3: Prioritize using effectiveness data
        engine = PriorityEngine(mock_learning_db, sample_effectiveness_stats)
        ranked = engine.rank_improvements(improvements, include_scores=True)

        assert len(ranked) > 0

        # Step 4: Verify scores incorporate effectiveness
        for imp in ranked:
            assert "priority_score" in imp
            assert 0.0 <= imp["priority_score"] <= 1.0

    def test_no_effectiveness_data_works(
        self,
        mock_learning_db: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        """Test system works correctly without effectiveness data."""
        # Generator without stats
        generator = InsightToTaskGenerator(mock_analyzer)
        improvements = generator.generate_improvements_from_insights()

        # Should still have confidence (default) and historical_success_rate (1.0)
        for imp in improvements:
            assert "confidence" in imp
            assert "historical_success_rate" in imp
            assert imp["historical_success_rate"] == 1.0

        # Engine without stats
        engine = PriorityEngine(mock_learning_db)
        ranked = engine.rank_improvements(improvements, include_scores=True)

        # Should still produce valid rankings
        assert len(ranked) > 0
        for imp in ranked:
            assert "priority_score" in imp


class TestEffectivenessWeightConfiguration:
    """Tests for effectiveness weight configuration in PriorityEngine."""

    def test_effectiveness_weight_constant(self) -> None:
        """Test EFFECTIVENESS_WEIGHT constant exists and is reasonable."""
        assert hasattr(PriorityEngine, "EFFECTIVENESS_WEIGHT")
        assert 0.0 < PriorityEngine.EFFECTIVENESS_WEIGHT < 1.0

    def test_all_weights_sum_correctly(self) -> None:
        """Test all priority weights sum to approximately 1.0."""
        total = (
            PriorityEngine.CATEGORY_SUCCESS_WEIGHT
            + PriorityEngine.BLOCKING_RISK_WEIGHT
            + PriorityEngine.PRIORITY_LEVEL_WEIGHT
            + PriorityEngine.COMPLEXITY_WEIGHT
            + PriorityEngine.EFFECTIVENESS_WEIGHT
        )
        # Allow small floating point tolerance
        assert 0.99 <= total <= 1.01
