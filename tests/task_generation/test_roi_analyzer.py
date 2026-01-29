"""Tests for ROIAnalyzer in autopack.task_generation module."""

from unittest.mock import MagicMock

import pytest

from autopack.task_generation.roi_analyzer import (
    DEFAULT_EFFECTIVENESS,
    DEFAULT_PHASES_HORIZON,
    EXCELLENT_ROI,
    GOOD_ROI,
    MIN_SAVINGS_PER_PHASE,
    MODERATE_ROI,
    PaybackAnalysis,
    ROIAnalyzer,
    ROIHistory,
)


class TestPaybackAnalysis:
    """Tests for PaybackAnalysis dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic PaybackAnalysis."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
        )
        assert analysis.task_id == "IMP-TEST-001"
        assert analysis.execution_cost_tokens == 1000.0
        assert analysis.risk_adjusted_roi == 7.2

    def test_get_roi_grade_excellent(self) -> None:
        """Test excellent grade for high ROI."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=EXCELLENT_ROI,
        )
        assert analysis.get_roi_grade() == "excellent"

    def test_get_roi_grade_good(self) -> None:
        """Test good grade for moderate-high ROI."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=50.0,
            payback_phases=20,
            lifetime_value_tokens=4000.0,
            risk_adjusted_roi=GOOD_ROI,
        )
        assert analysis.get_roi_grade() == "good"

    def test_get_roi_grade_moderate(self) -> None:
        """Test moderate grade for break-even ROI."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=20.0,
            payback_phases=50,
            lifetime_value_tokens=1000.0,
            risk_adjusted_roi=MODERATE_ROI,
        )
        assert analysis.get_roi_grade() == "moderate"

    def test_get_roi_grade_poor(self) -> None:
        """Test poor grade for low ROI."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=5.0,
            payback_phases=200,
            lifetime_value_tokens=-500.0,
            risk_adjusted_roi=0.3,
        )
        assert analysis.get_roi_grade() == "poor"

    def test_is_profitable_true(self) -> None:
        """Test is_profitable returns True for positive lifetime value."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
        )
        assert analysis.is_profitable() is True

    def test_is_profitable_false(self) -> None:
        """Test is_profitable returns False for negative lifetime value."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=10000.0,
            estimated_savings_per_phase=1.0,
            payback_phases=10000,
            lifetime_value_tokens=-9900.0,
            risk_adjusted_roi=-0.79,
        )
        assert analysis.is_profitable() is False

    def test_has_quick_payback_true(self) -> None:
        """Test has_quick_payback returns True for short payback."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=100.0,
            estimated_savings_per_phase=50.0,
            payback_phases=3,
            lifetime_value_tokens=4900.0,
            risk_adjusted_roi=39.2,
        )
        assert analysis.has_quick_payback(threshold_phases=10) is True

    def test_has_quick_payback_false(self) -> None:
        """Test has_quick_payback returns False for long payback."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=10.0,
            payback_phases=100,
            lifetime_value_tokens=0.0,
            risk_adjusted_roi=0.0,
        )
        assert analysis.has_quick_payback(threshold_phases=10) is False

    def test_optional_fields(self) -> None:
        """Test optional confidence and category fields."""
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
            confidence=0.9,
            category="telemetry",
        )
        assert analysis.confidence == 0.9
        assert analysis.category == "telemetry"


class TestROIHistory:
    """Tests for ROIHistory dataclass."""

    def test_empty_history(self) -> None:
        """Test empty history initialization."""
        history = ROIHistory()
        assert len(history.analyses) == 0
        assert len(history.category_stats) == 0

    def test_add_analysis(self) -> None:
        """Test adding an analysis to history."""
        history = ROIHistory()
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
            category="telemetry",
        )
        history.add_analysis(analysis)

        assert len(history.analyses) == 1
        assert "telemetry" in history.category_stats

    def test_category_stats_aggregation(self) -> None:
        """Test category statistics are correctly aggregated."""
        history = ROIHistory()

        analysis1 = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
            category="telemetry",
        )
        analysis2 = PaybackAnalysis(
            task_id="IMP-TEST-002",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=50.0,
            payback_phases=20,
            lifetime_value_tokens=4000.0,
            risk_adjusted_roi=3.2,
            category="telemetry",
        )

        history.add_analysis(analysis1)
        history.add_analysis(analysis2)

        stats = history.category_stats["telemetry"]
        assert stats["total_analyses"] == 2
        assert stats["avg_roi"] == pytest.approx(5.2)  # (7.2 + 3.2) / 2
        assert stats["profitable_count"] == 2

    def test_get_category_avg_roi(self) -> None:
        """Test getting average ROI for a category."""
        history = ROIHistory()
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
            category="memory",
        )
        history.add_analysis(analysis)

        assert history.get_category_avg_roi("memory") == 7.2
        assert history.get_category_avg_roi("unknown") == 1.0  # Default neutral

    def test_general_category_fallback(self) -> None:
        """Test empty category falls back to general."""
        history = ROIHistory()
        analysis = PaybackAnalysis(
            task_id="IMP-TEST-001",
            execution_cost_tokens=1000.0,
            estimated_savings_per_phase=100.0,
            payback_phases=10,
            lifetime_value_tokens=9000.0,
            risk_adjusted_roi=7.2,
            category="",
        )
        history.add_analysis(analysis)

        assert "general" in history.category_stats


class TestROIAnalyzer:
    """Tests for ROIAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer without effectiveness tracker."""
        return ROIAnalyzer()

    @pytest.fixture
    def analyzer_with_tracker(self) -> ROIAnalyzer:
        """Create an analyzer with mock effectiveness tracker."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.8
        mock_tracker.get_category_effectiveness.return_value = 0.75
        return ROIAnalyzer(effectiveness_tracker=mock_tracker)

    def test_init_without_tracker(self) -> None:
        """Test analyzer initializes without tracker."""
        analyzer = ROIAnalyzer()
        assert analyzer.effectiveness_tracker is None
        assert len(analyzer.history.analyses) == 0
        assert analyzer.phases_horizon == DEFAULT_PHASES_HORIZON

    def test_init_with_tracker(self) -> None:
        """Test analyzer initializes with tracker."""
        mock_tracker = MagicMock()
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)
        assert analyzer.effectiveness_tracker is mock_tracker

    def test_init_custom_horizon(self) -> None:
        """Test analyzer with custom phases horizon."""
        analyzer = ROIAnalyzer(phases_horizon=50)
        assert analyzer.phases_horizon == 50


class TestCalculatePaybackPeriod:
    """Tests for calculate_payback_period method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_basic_calculation(self, analyzer: ROIAnalyzer) -> None:
        """Test basic payback calculation."""
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            confidence=0.8,
        )

        assert analysis.task_id == "IMP-TEST-001"
        assert analysis.execution_cost_tokens == 500.0
        # With default effectiveness (0.5): 100 * 0.5 = 50 savings/phase
        assert analysis.estimated_savings_per_phase == pytest.approx(50.0)
        # Payback: 500 / 50 + 1 = 11 phases
        assert analysis.payback_phases == 11
        # Lifetime value: (50 * 100) - 500 = 4500
        assert analysis.lifetime_value_tokens == pytest.approx(4500.0)
        # ROI: (4500 / 500) * 0.8 = 7.2
        assert analysis.risk_adjusted_roi == pytest.approx(7.2)

    def test_with_tracker_effectiveness(self) -> None:
        """Test calculation uses tracker effectiveness."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.9
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            confidence=0.8,
        )

        # With effectiveness 0.9: 100 * 0.9 = 90 savings/phase
        assert analysis.estimated_savings_per_phase == pytest.approx(90.0)
        mock_tracker.get_effectiveness.assert_called_once_with("IMP-TEST-001")

    def test_category_fallback_effectiveness(self) -> None:
        """Test falls back to category effectiveness when task not found."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = DEFAULT_EFFECTIVENESS
        mock_tracker.get_category_effectiveness.return_value = 0.75
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            confidence=0.8,
            category="telemetry",
        )

        # Falls back to category effectiveness (0.75)
        assert analysis.estimated_savings_per_phase == pytest.approx(75.0)
        mock_tracker.get_category_effectiveness.assert_called_once_with("telemetry")

    def test_with_category(self, analyzer: ROIAnalyzer) -> None:
        """Test calculation with category."""
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        assert analysis.category == "telemetry"
        assert "telemetry" in analyzer.history.category_stats

    def test_stored_in_history(self, analyzer: ROIAnalyzer) -> None:
        """Test analysis is stored in history."""
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        assert len(analyzer.history.analyses) == 1
        assert analyzer.history.analyses[0].task_id == "IMP-TEST-001"

    def test_invalid_execution_cost_zero(self, analyzer: ROIAnalyzer) -> None:
        """Test error on zero execution cost."""
        with pytest.raises(ValueError, match="Execution cost must be positive"):
            analyzer.calculate_payback_period(
                task_id="IMP-TEST-001",
                estimated_token_reduction=100.0,
                execution_cost=0,
            )

    def test_invalid_execution_cost_negative(self, analyzer: ROIAnalyzer) -> None:
        """Test error on negative execution cost."""
        with pytest.raises(ValueError, match="Execution cost must be positive"):
            analyzer.calculate_payback_period(
                task_id="IMP-TEST-001",
                estimated_token_reduction=100.0,
                execution_cost=-100.0,
            )

    def test_invalid_confidence_above_one(self, analyzer: ROIAnalyzer) -> None:
        """Test error on confidence above 1.0."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            analyzer.calculate_payback_period(
                task_id="IMP-TEST-001",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
                confidence=1.5,
            )

    def test_invalid_confidence_negative(self, analyzer: ROIAnalyzer) -> None:
        """Test error on negative confidence."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            analyzer.calculate_payback_period(
                task_id="IMP-TEST-001",
                estimated_token_reduction=100.0,
                execution_cost=500.0,
                confidence=-0.1,
            )

    def test_zero_token_reduction(self, analyzer: ROIAnalyzer) -> None:
        """Test calculation with zero token reduction uses minimum."""
        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=0.0,
            execution_cost=500.0,
        )

        # Should use MIN_SAVINGS_PER_PHASE to prevent division by zero
        assert analysis.estimated_savings_per_phase == pytest.approx(MIN_SAVINGS_PER_PHASE)

    def test_custom_phases_horizon(self) -> None:
        """Test calculation with custom phases horizon."""
        analyzer = ROIAnalyzer(phases_horizon=50)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        # With 50 phases: (50 * 50) - 500 = 2000 lifetime value
        assert analysis.lifetime_value_tokens == pytest.approx(2000.0)


class TestRankTasks:
    """Tests for ranking methods."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    @pytest.fixture
    def sample_analyses(self) -> list[PaybackAnalysis]:
        """Create sample analyses for ranking tests."""
        return [
            PaybackAnalysis(
                task_id="IMP-TEST-001",
                execution_cost_tokens=1000.0,
                estimated_savings_per_phase=100.0,
                payback_phases=10,
                lifetime_value_tokens=9000.0,
                risk_adjusted_roi=7.2,
            ),
            PaybackAnalysis(
                task_id="IMP-TEST-002",
                execution_cost_tokens=500.0,
                estimated_savings_per_phase=200.0,
                payback_phases=3,
                lifetime_value_tokens=19500.0,
                risk_adjusted_roi=31.2,
            ),
            PaybackAnalysis(
                task_id="IMP-TEST-003",
                execution_cost_tokens=2000.0,
                estimated_savings_per_phase=50.0,
                payback_phases=40,
                lifetime_value_tokens=3000.0,
                risk_adjusted_roi=1.2,
            ),
        ]

    def test_rank_by_roi(
        self, analyzer: ROIAnalyzer, sample_analyses: list[PaybackAnalysis]
    ) -> None:
        """Test ranking by ROI (descending)."""
        ranked = analyzer.rank_tasks_by_roi(sample_analyses)

        assert ranked[0].task_id == "IMP-TEST-002"  # ROI 31.2
        assert ranked[1].task_id == "IMP-TEST-001"  # ROI 7.2
        assert ranked[2].task_id == "IMP-TEST-003"  # ROI 1.2

    def test_rank_by_payback(
        self, analyzer: ROIAnalyzer, sample_analyses: list[PaybackAnalysis]
    ) -> None:
        """Test ranking by payback (ascending)."""
        ranked = analyzer.rank_tasks_by_payback(sample_analyses)

        assert ranked[0].task_id == "IMP-TEST-002"  # 3 phases
        assert ranked[1].task_id == "IMP-TEST-001"  # 10 phases
        assert ranked[2].task_id == "IMP-TEST-003"  # 40 phases

    def test_rank_empty_list(self, analyzer: ROIAnalyzer) -> None:
        """Test ranking empty list."""
        assert analyzer.rank_tasks_by_roi([]) == []
        assert analyzer.rank_tasks_by_payback([]) == []


class TestFilterTasks:
    """Tests for filtering methods."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    @pytest.fixture
    def mixed_analyses(self) -> list[PaybackAnalysis]:
        """Create analyses with mixed profitability."""
        return [
            PaybackAnalysis(
                task_id="IMP-PROFITABLE-001",
                execution_cost_tokens=1000.0,
                estimated_savings_per_phase=100.0,
                payback_phases=10,
                lifetime_value_tokens=9000.0,  # Profitable
                risk_adjusted_roi=7.2,
            ),
            PaybackAnalysis(
                task_id="IMP-UNPROFITABLE-001",
                execution_cost_tokens=10000.0,
                estimated_savings_per_phase=1.0,
                payback_phases=10000,
                lifetime_value_tokens=-9900.0,  # Unprofitable
                risk_adjusted_roi=-0.79,
            ),
            PaybackAnalysis(
                task_id="IMP-QUICK-001",
                execution_cost_tokens=100.0,
                estimated_savings_per_phase=50.0,
                payback_phases=3,  # Quick payback
                lifetime_value_tokens=4900.0,
                risk_adjusted_roi=39.2,
            ),
        ]

    def test_filter_profitable(
        self, analyzer: ROIAnalyzer, mixed_analyses: list[PaybackAnalysis]
    ) -> None:
        """Test filtering to profitable tasks."""
        filtered = analyzer.filter_profitable_tasks(mixed_analyses)

        assert len(filtered) == 2
        task_ids = [a.task_id for a in filtered]
        assert "IMP-PROFITABLE-001" in task_ids
        assert "IMP-QUICK-001" in task_ids
        assert "IMP-UNPROFITABLE-001" not in task_ids

    def test_filter_quick_payback(
        self, analyzer: ROIAnalyzer, mixed_analyses: list[PaybackAnalysis]
    ) -> None:
        """Test filtering to quick payback tasks."""
        filtered = analyzer.filter_quick_payback_tasks(mixed_analyses, threshold_phases=5)

        assert len(filtered) == 1
        assert filtered[0].task_id == "IMP-QUICK-001"

    def test_filter_quick_payback_custom_threshold(
        self, analyzer: ROIAnalyzer, mixed_analyses: list[PaybackAnalysis]
    ) -> None:
        """Test filtering with custom threshold."""
        filtered = analyzer.filter_quick_payback_tasks(mixed_analyses, threshold_phases=15)

        assert len(filtered) == 2
        task_ids = [a.task_id for a in filtered]
        assert "IMP-PROFITABLE-001" in task_ids
        assert "IMP-QUICK-001" in task_ids

    def test_filter_empty_list(self, analyzer: ROIAnalyzer) -> None:
        """Test filtering empty list."""
        assert analyzer.filter_profitable_tasks([]) == []
        assert analyzer.filter_quick_payback_tasks([]) == []


class TestGetSummary:
    """Tests for get_summary method."""

    @pytest.fixture
    def analyzer(self) -> ROIAnalyzer:
        """Create an analyzer for testing."""
        return ROIAnalyzer()

    def test_empty_summary(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with no analyses."""
        summary = analyzer.get_summary()

        assert summary["total_analyses"] == 0
        assert summary["avg_roi"] == 0.0
        assert summary["avg_payback_phases"] == 0.0
        assert summary["by_category"] == {}
        assert summary["profitable_rate"] == 0.0
        assert summary["grade_distribution"] == {
            "excellent": 0,
            "good": 0,
            "moderate": 0,
            "poor": 0,
        }

    def test_summary_with_analyses(self, analyzer: ROIAnalyzer) -> None:
        """Test summary with multiple analyses."""
        # Add excellent ROI task
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=200.0,
            execution_cost=100.0,
            category="telemetry",
        )
        # Add moderate ROI task
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-002",
            estimated_token_reduction=30.0,
            execution_cost=1000.0,
            category="memory",
        )

        summary = analyzer.get_summary()

        assert summary["total_analyses"] == 2
        assert "telemetry" in summary["by_category"]
        assert "memory" in summary["by_category"]
        assert summary["grade_distribution"]["excellent"] >= 0
        assert summary["profitable_rate"] > 0

    def test_profitable_rate_calculation(self, analyzer: ROIAnalyzer) -> None:
        """Test profitable rate calculation."""
        # Add profitable task
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=100.0,
        )
        # Add another profitable task
        analyzer.calculate_payback_period(
            task_id="IMP-TEST-002",
            estimated_token_reduction=100.0,
            execution_cost=200.0,
        )

        summary = analyzer.get_summary()

        # Both tasks should be profitable with these parameters
        assert summary["profitable_rate"] == 1.0


class TestIntegrationWithEffectivenessTracker:
    """Integration tests with TaskEffectivenessTracker."""

    def test_uses_task_specific_effectiveness(self) -> None:
        """Test that task-specific effectiveness is used."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = 0.9
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-TEST-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
        )

        # Effectiveness 0.9 means 90 tokens saved per phase
        assert analysis.estimated_savings_per_phase == pytest.approx(90.0)

    def test_falls_back_to_category_when_task_unknown(self) -> None:
        """Test fallback to category effectiveness."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = DEFAULT_EFFECTIVENESS
        mock_tracker.get_category_effectiveness.return_value = 0.8
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-NEW-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="telemetry",
        )

        # Should use category effectiveness (0.8)
        assert analysis.estimated_savings_per_phase == pytest.approx(80.0)

    def test_uses_default_when_no_data(self) -> None:
        """Test default effectiveness when no historical data."""
        mock_tracker = MagicMock()
        mock_tracker.get_effectiveness.return_value = DEFAULT_EFFECTIVENESS
        mock_tracker.get_category_effectiveness.return_value = DEFAULT_EFFECTIVENESS
        analyzer = ROIAnalyzer(effectiveness_tracker=mock_tracker)

        analysis = analyzer.calculate_payback_period(
            task_id="IMP-NEW-001",
            estimated_token_reduction=100.0,
            execution_cost=500.0,
            category="unknown_category",
        )

        # Should use default effectiveness (0.5)
        assert analysis.estimated_savings_per_phase == pytest.approx(50.0)
