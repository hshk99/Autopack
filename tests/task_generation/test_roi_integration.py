"""Tests for ROI integration with PriorityEngine (IMP-TASK-002).

Tests the integration between ROIAnalyzer and PriorityEngine to ensure
tasks with shorter payback periods receive priority boosts.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autopack.task_generation.priority_engine import PriorityEngine
from autopack.task_generation.roi_analyzer import (DEFAULT_EFFECTIVENESS,
                                                   PaybackAnalysis,
                                                   ROIAnalyzer)


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
def roi_analyzer() -> ROIAnalyzer:
    """Create an ROIAnalyzer for testing."""
    return ROIAnalyzer()


@pytest.fixture
def priority_engine_with_roi(
    mock_learning_db: MagicMock, roi_analyzer: ROIAnalyzer
) -> PriorityEngine:
    """Create a PriorityEngine with ROI analyzer integration."""
    return PriorityEngine(mock_learning_db, roi_analyzer=roi_analyzer)


@pytest.fixture
def priority_engine_without_roi(mock_learning_db: MagicMock) -> PriorityEngine:
    """Create a PriorityEngine without ROI analyzer."""
    return PriorityEngine(mock_learning_db)


class TestROIIntegrationInit:
    """Tests for ROI analyzer integration in PriorityEngine initialization."""

    def test_init_with_roi_analyzer(
        self, mock_learning_db: MagicMock, roi_analyzer: ROIAnalyzer
    ) -> None:
        """Test PriorityEngine initializes with ROI analyzer."""
        engine = PriorityEngine(mock_learning_db, roi_analyzer=roi_analyzer)
        assert engine._roi_analyzer is roi_analyzer

    def test_init_without_roi_analyzer(self, mock_learning_db: MagicMock) -> None:
        """Test PriorityEngine initializes without ROI analyzer."""
        engine = PriorityEngine(mock_learning_db)
        assert engine._roi_analyzer is None

    def test_set_roi_analyzer(self, mock_learning_db: MagicMock, roi_analyzer: ROIAnalyzer) -> None:
        """Test setting ROI analyzer after initialization."""
        engine = PriorityEngine(mock_learning_db)
        assert engine._roi_analyzer is None

        engine.set_roi_analyzer(roi_analyzer)
        assert engine._roi_analyzer is roi_analyzer


class TestGetROIFactor:
    """Tests for get_roi_factor method."""

    def test_roi_factor_without_analyzer(self, priority_engine_without_roi: PriorityEngine) -> None:
        """Test ROI factor is 1.0 when no analyzer is set."""
        imp = {"imp_id": "IMP-TEST-001", "title": "Test task"}
        factor = priority_engine_without_roi.get_roi_factor(imp)
        assert factor == 1.0

    def test_roi_factor_quick_payback(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test ROI factor for quick payback task (max boost)."""
        # High savings, low cost = quick payback
        imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Quick payback task",
            "estimated_tokens": 100.0,  # Low cost
            "estimated_savings": 200.0,  # High savings
        }
        factor = priority_engine_with_roi.get_roi_factor(imp)
        # Quick payback should get maximum boost (2.0)
        assert factor == 2.0

    def test_roi_factor_slow_payback(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test ROI factor for slow payback task (minimum factor)."""
        # Low savings, high cost = slow payback
        imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Slow payback task",
            "estimated_tokens": 10000.0,  # High cost
            "estimated_savings": 1.0,  # Very low savings
        }
        factor = priority_engine_with_roi.get_roi_factor(imp)
        # Slow payback should get minimum factor (0.5)
        assert factor == 0.5

    def test_roi_factor_neutral_payback(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test ROI factor for neutral payback task."""
        # Moderate savings and cost = neutral payback (~30 phases)
        imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Neutral payback task",
            "estimated_tokens": 750.0,  # Moderate cost
            "estimated_savings": 50.0,  # Moderate savings (50 * 0.5 = 25/phase)
            # Payback = 750 / 25 = 30 phases
        }
        factor = priority_engine_with_roi.get_roi_factor(imp)
        # Neutral payback should be close to 1.0
        assert 0.9 <= factor <= 1.1

    def test_roi_factor_uses_defaults_when_missing(
        self, priority_engine_with_roi: PriorityEngine
    ) -> None:
        """Test ROI factor uses defaults when estimates are missing."""
        imp = {"imp_id": "IMP-TEST-001", "title": "Task without estimates"}
        factor = priority_engine_with_roi.get_roi_factor(imp)
        # Should return a valid factor using defaults
        assert 0.5 <= factor <= 2.0

    def test_roi_factor_handles_calculation_error(self, mock_learning_db: MagicMock) -> None:
        """Test ROI factor returns 1.0 on calculation error."""
        # Create analyzer that raises an error
        mock_roi_analyzer = MagicMock()
        mock_roi_analyzer.calculate_payback_period.side_effect = ValueError("Test error")

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi_analyzer)

        imp = {"imp_id": "IMP-TEST-001", "title": "Test task"}
        factor = engine.get_roi_factor(imp)
        # Should return neutral factor on error
        assert factor == 1.0


class TestPriorityScoreWithROI:
    """Tests for priority score calculation with ROI integration."""

    def test_score_higher_with_quick_payback(
        self, priority_engine_with_roi: PriorityEngine
    ) -> None:
        """Test that quick payback tasks score higher."""
        quick_payback_imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Quick payback",
            "priority": "medium",
            "estimated_tokens": 100.0,
            "estimated_savings": 200.0,
        }
        slow_payback_imp = {
            "imp_id": "IMP-TEST-002",
            "title": "Slow payback",
            "priority": "medium",
            "estimated_tokens": 10000.0,
            "estimated_savings": 1.0,
        }

        quick_score = priority_engine_with_roi.calculate_priority_score(quick_payback_imp)
        slow_score = priority_engine_with_roi.calculate_priority_score(slow_payback_imp)

        # Quick payback should score higher
        assert quick_score > slow_score

    def test_score_same_without_roi(self, priority_engine_without_roi: PriorityEngine) -> None:
        """Test that without ROI, scores are based on other factors only."""
        imp1 = {
            "imp_id": "IMP-TEST-001",
            "title": "Task 1",
            "priority": "high",
            "estimated_tokens": 100.0,
            "estimated_savings": 200.0,
        }
        imp2 = {
            "imp_id": "IMP-TEST-002",
            "title": "Task 2",
            "priority": "high",
            "estimated_tokens": 10000.0,
            "estimated_savings": 1.0,
        }

        score1 = priority_engine_without_roi.calculate_priority_score(imp1)
        score2 = priority_engine_without_roi.calculate_priority_score(imp2)

        # Without ROI, scores should be similar (same priority, same category)
        # Allow small difference due to complexity estimation
        assert abs(score1 - score2) < 0.1

    def test_roi_factor_in_score_calculation(
        self, priority_engine_with_roi: PriorityEngine
    ) -> None:
        """Test that ROI factor is applied in score calculation."""
        imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Test task",
            "priority": "high",
            "estimated_tokens": 100.0,
            "estimated_savings": 200.0,  # Quick payback
        }

        # Get ROI factor
        roi_factor = priority_engine_with_roi.get_roi_factor(imp)
        assert roi_factor > 1.0  # Should be boosted

        # Get score
        score = priority_engine_with_roi.calculate_priority_score(imp)

        # Score should be positive and affected by ROI
        assert score > 0


class TestROIRanking:
    """Tests for ranking improvements with ROI consideration."""

    def test_rank_by_roi_payback(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test that improvements are ranked by ROI payback period."""
        improvements = [
            {
                "imp_id": "IMP-SLOW-001",
                "title": "Slow payback",
                "priority": "high",
                "estimated_tokens": 5000.0,
                "estimated_savings": 10.0,
            },
            {
                "imp_id": "IMP-QUICK-001",
                "title": "Quick payback",
                "priority": "high",
                "estimated_tokens": 100.0,
                "estimated_savings": 200.0,
            },
            {
                "imp_id": "IMP-MED-001",
                "title": "Medium payback",
                "priority": "high",
                "estimated_tokens": 500.0,
                "estimated_savings": 50.0,
            },
        ]

        ranked = priority_engine_with_roi.rank_improvements(improvements, include_scores=True)

        # Quick payback should rank first
        assert ranked[0]["imp_id"] == "IMP-QUICK-001"
        # Slow payback should rank last
        assert ranked[-1]["imp_id"] == "IMP-SLOW-001"

    def test_rank_preserves_priority_without_roi(
        self, priority_engine_without_roi: PriorityEngine
    ) -> None:
        """Test that ranking works correctly without ROI analyzer."""
        improvements = [
            {"imp_id": "IMP-LOW-001", "title": "Low priority", "priority": "low"},
            {"imp_id": "IMP-HIGH-001", "title": "High priority", "priority": "high"},
            {"imp_id": "IMP-CRIT-001", "title": "Critical priority", "priority": "critical"},
        ]

        ranked = priority_engine_without_roi.rank_improvements(improvements, include_scores=True)

        # Critical should rank first
        assert ranked[0]["imp_id"] == "IMP-CRIT-001"
        # Low should rank last
        assert ranked[-1]["imp_id"] == "IMP-LOW-001"


class TestROIPaybackThresholds:
    """Tests for ROI payback threshold constants."""

    def test_quick_payback_threshold(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test quick payback threshold value."""
        assert priority_engine_with_roi.ROI_QUICK_PAYBACK_PHASES == 10

    def test_neutral_payback_threshold(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test neutral payback threshold value."""
        assert priority_engine_with_roi.ROI_NEUTRAL_PAYBACK_PHASES == 30

    def test_slow_payback_threshold(self, priority_engine_with_roi: PriorityEngine) -> None:
        """Test slow payback threshold value."""
        assert priority_engine_with_roi.ROI_SLOW_PAYBACK_PHASES == 90


class TestROIFactorInterpolation:
    """Tests for ROI factor interpolation between thresholds."""

    def test_factor_at_quick_threshold(self, mock_learning_db: MagicMock) -> None:
        """Test factor at quick payback threshold (10 phases)."""
        mock_roi = MagicMock()
        analysis = PaybackAnalysis(
            task_id="test",
            execution_cost_tokens=500,
            estimated_savings_per_phase=50,
            payback_phases=10,  # Exactly at quick threshold
            lifetime_value_tokens=4500,
            risk_adjusted_roi=7.2,
        )
        mock_roi.calculate_payback_period.return_value = analysis

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi)
        factor = engine.get_roi_factor({"imp_id": "test"})
        assert factor == 2.0

    def test_factor_at_neutral_threshold(self, mock_learning_db: MagicMock) -> None:
        """Test factor at neutral payback threshold (30 phases)."""
        mock_roi = MagicMock()
        analysis = PaybackAnalysis(
            task_id="test",
            execution_cost_tokens=1500,
            estimated_savings_per_phase=50,
            payback_phases=30,  # Exactly at neutral threshold
            lifetime_value_tokens=3500,
            risk_adjusted_roi=2.3,
        )
        mock_roi.calculate_payback_period.return_value = analysis

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi)
        factor = engine.get_roi_factor({"imp_id": "test"})
        assert factor == 1.0

    def test_factor_at_slow_threshold(self, mock_learning_db: MagicMock) -> None:
        """Test factor at slow payback threshold (90 phases)."""
        mock_roi = MagicMock()
        analysis = PaybackAnalysis(
            task_id="test",
            execution_cost_tokens=4500,
            estimated_savings_per_phase=50,
            payback_phases=90,  # Exactly at slow threshold
            lifetime_value_tokens=500,
            risk_adjusted_roi=0.1,
        )
        mock_roi.calculate_payback_period.return_value = analysis

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi)
        factor = engine.get_roi_factor({"imp_id": "test"})
        assert factor == 0.5

    def test_factor_between_quick_and_neutral(self, mock_learning_db: MagicMock) -> None:
        """Test factor interpolation between quick and neutral."""
        mock_roi = MagicMock()
        analysis = PaybackAnalysis(
            task_id="test",
            execution_cost_tokens=1000,
            estimated_savings_per_phase=50,
            payback_phases=20,  # Midpoint between 10 and 30
            lifetime_value_tokens=4000,
            risk_adjusted_roi=3.2,
        )
        mock_roi.calculate_payback_period.return_value = analysis

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi)
        factor = engine.get_roi_factor({"imp_id": "test"})
        # Midpoint should give factor of 1.5 (between 2.0 and 1.0)
        assert factor == pytest.approx(1.5, abs=0.01)

    def test_factor_between_neutral_and_slow(self, mock_learning_db: MagicMock) -> None:
        """Test factor interpolation between neutral and slow."""
        mock_roi = MagicMock()
        analysis = PaybackAnalysis(
            task_id="test",
            execution_cost_tokens=3000,
            estimated_savings_per_phase=50,
            payback_phases=60,  # Midpoint between 30 and 90
            lifetime_value_tokens=2000,
            risk_adjusted_roi=0.67,
        )
        mock_roi.calculate_payback_period.return_value = analysis

        engine = PriorityEngine(mock_learning_db, roi_analyzer=mock_roi)
        factor = engine.get_roi_factor({"imp_id": "test"})
        # Midpoint should give factor of 0.75 (between 1.0 and 0.5)
        assert factor == pytest.approx(0.75, abs=0.01)


class TestROIWithEffectivenessTracker:
    """Tests for ROI analyzer with effectiveness tracker integration."""

    def test_roi_uses_effectiveness_from_tracker(self) -> None:
        """Test that ROI calculations use effectiveness from tracker."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.9

        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        # With 90% effectiveness: 100 * 0.9 = 90 savings/phase
        assert analysis.estimated_savings_per_phase == pytest.approx(90.0)
        mock_tracker.get_effectiveness.assert_called_once()

    def test_priority_engine_passes_tracker_to_roi(self, mock_learning_db: MagicMock) -> None:
        """Test PriorityEngine uses tracker-based ROI calculations."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.9
        mock_tracker.get_category_effectiveness.return_value = 0.85

        roi_analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)
        engine = PriorityEngine(
            mock_learning_db,
            effectiveness_tracker=mock_tracker,
            roi_analyzer=roi_analyzer,
        )

        imp = {
            "imp_id": "IMP-TEST-001",
            "title": "Test task",
            "estimated_tokens": 500.0,
            "estimated_savings": 100.0,
        }

        # Calculate ROI factor to trigger tracker lookup
        factor = engine.get_roi_factor(imp)
        assert 0.5 <= factor <= 2.0
