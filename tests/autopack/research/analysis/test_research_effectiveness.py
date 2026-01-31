"""Tests for ResearchEffectivenessAnalyzer in autopack.research.analysis module.

IMP-SEG-002: Tests for research cycle outcome tracking and effectiveness measurement.

Tests cover:
- Research cycle outcome recording and tracking
- Decision quality improvement measurement
- Confidence improvement calculation
- Return on investment (ROI) calculation
- Follow-up research effectiveness tracking
- Outcome reporting and analysis
- Feedback collection and prioritization
- Effectiveness metrics aggregation
"""

import pytest
from datetime import datetime, timezone
from typing import List

from autopack.research.analysis.research_effectiveness import (
    DecisionQualityLevel,
    FeedbackCategory,
    ResearchCycleOutcome,
    ResearchEffectivenessAnalyzer,
    ResearchEffectivenessFeedback,
    ResearchEffectivenessMetrics,
    ResearchOutcomeType,
)


class TestResearchCycleOutcome:
    """Test suite for ResearchCycleOutcome class."""

    def test_outcome_creation(self):
        """Test creating a research cycle outcome."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.FAIR,
            decision_quality_after=DecisionQualityLevel.GOOD,
            confidence_before=40,
            confidence_after=75,
            time_spent_seconds=3600,
            research_cost=50.0,
            key_findings=["Finding 1", "Finding 2"],
            decisions_made=["Decision 1"],
            follow_up_triggers_executed=2,
            follow_up_triggers_successful=2,
        )

        assert outcome.cycle_id == "cycle_001"
        assert outcome.research_session_id == "session_001"
        assert outcome.outcome_type == ResearchOutcomeType.DECISION_MADE
        assert outcome.confidence_before == 40
        assert outcome.confidence_after == 75

    def test_quality_improvement_calculation(self):
        """Test calculating quality improvement."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.POOR,  # 25
            decision_quality_after=DecisionQualityLevel.EXCELLENT,  # 100
        )

        improvement = outcome.calculate_quality_improvement()
        assert improvement == 75  # 100 - 25

    def test_confidence_improvement_calculation(self):
        """Test calculating confidence improvement."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            confidence_before=30,
            confidence_after=85,
        )

        improvement = outcome.calculate_confidence_improvement()
        assert improvement == 55  # 85 - 30

    def test_roi_calculation_with_cost(self):
        """Test ROI calculation with research cost."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.FAIR,  # 50
            decision_quality_after=DecisionQualityLevel.EXCELLENT,  # 100
            research_cost=100.0,
            key_findings=["Finding 1", "Finding 2"],
            decisions_made=["Decision 1", "Decision 2"],
        )

        roi = outcome.calculate_roi()
        # Value = quality_improvement (50) + decisions (2 * 10) + findings (2 * 5) = 80
        # ROI = 80 / 100 = 0.8
        assert roi == pytest.approx(0.8, rel=0.01)

    def test_roi_calculation_zero_cost(self):
        """Test ROI calculation with zero cost."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            research_cost=0.0,
        )

        roi = outcome.calculate_roi()
        assert roi == float("inf")

    def test_success_determination_by_quality(self):
        """Test success determination based on quality improvement."""
        # Successful: quality improved
        successful = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.POOR,
            decision_quality_after=DecisionQualityLevel.GOOD,
        )
        assert successful.is_successful()

        # Unsuccessful: no improvement
        unsuccessful = ResearchCycleOutcome(
            cycle_id="cycle_002",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.BLOCKED,
            decision_quality_before=DecisionQualityLevel.POOR,
            decision_quality_after=DecisionQualityLevel.POOR,
        )
        assert not unsuccessful.is_successful()

    def test_success_determination_by_findings(self):
        """Test success determination based on key findings."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.INCONCLUSIVE,
            key_findings=["Finding 1"],
        )
        assert outcome.is_successful()

    def test_outcome_serialization(self):
        """Test serializing outcome to dictionary."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.FAIR,
            decision_quality_after=DecisionQualityLevel.GOOD,
            confidence_before=50,
            confidence_after=80,
            time_spent_seconds=1800,
            research_cost=25.0,
            key_findings=["Finding 1"],
            decisions_made=["Decision 1"],
        )

        result = outcome.to_dict()
        assert result["cycle_id"] == "cycle_001"
        assert result["outcome_type"] == "decision_made"
        assert result["confidence_improvement"] == 30
        assert result["quality_improvement"] == 25
        assert result["was_successful"] is True


class TestResearchEffectivenessAnalyzer:
    """Test suite for ResearchEffectivenessAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> ResearchEffectivenessAnalyzer:
        """Create a fresh analyzer for each test."""
        return ResearchEffectivenessAnalyzer()

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.outcomes == []
        assert analyzer.feedback == []
        assert analyzer.metrics.total_cycles == 0
        assert analyzer.metrics.successful_cycles == 0

    def test_record_single_outcome(self, analyzer):
        """Test recording a single research cycle outcome."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.POOR,
            decision_quality_after=DecisionQualityLevel.GOOD,
            confidence_before=30,
            confidence_after=80,
            time_spent_seconds=1800,
            research_cost=50.0,
        )

        analyzer.record_outcome(outcome)

        assert len(analyzer.outcomes) == 1
        assert analyzer.metrics.total_cycles == 1
        assert analyzer.metrics.successful_cycles == 1
        assert analyzer.metrics.confidence_improvement_avg == 50

    def test_record_multiple_outcomes(self, analyzer):
        """Test recording multiple research cycle outcomes."""
        outcomes = [
            ResearchCycleOutcome(
                cycle_id=f"cycle_{i:03d}",
                research_session_id=f"session_{i:03d}",
                outcome_type=ResearchOutcomeType.DECISION_MADE if i % 2 == 0 else ResearchOutcomeType.BLOCKED,
                decision_quality_before=DecisionQualityLevel.POOR,
                decision_quality_after=DecisionQualityLevel.GOOD if i % 2 == 0 else DecisionQualityLevel.POOR,
                confidence_before=30 + i,
                confidence_after=80 + i if i % 2 == 0 else 30 + i,
                time_spent_seconds=1800,
                research_cost=50.0,
            )
            for i in range(5)
        ]

        for outcome in outcomes:
            analyzer.record_outcome(outcome)

        assert len(analyzer.outcomes) == 5
        assert analyzer.metrics.total_cycles == 5
        assert analyzer.metrics.successful_cycles == 3  # indices 0, 2, 4

    def test_success_rate_calculation(self, analyzer):
        """Test success rate calculation."""
        # Add 3 successful, 2 unsuccessful
        for i in range(3):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id=f"session_{i:03d}",
                    outcome_type=ResearchOutcomeType.DECISION_MADE,
                    decision_quality_before=DecisionQualityLevel.POOR,
                    decision_quality_after=DecisionQualityLevel.GOOD,
                )
            )

        for i in range(3, 5):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id=f"session_{i:03d}",
                    outcome_type=ResearchOutcomeType.BLOCKED,
                    decision_quality_before=DecisionQualityLevel.POOR,
                    decision_quality_after=DecisionQualityLevel.POOR,
                )
            )

        success_rate = analyzer.metrics.success_rate()
        assert success_rate == 60.0  # 3/5 = 60%

    def test_get_outcome_by_id(self, analyzer):
        """Test retrieving a specific outcome by ID."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_target",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
        )
        analyzer.record_outcome(outcome)

        retrieved = analyzer.get_outcome("cycle_target")
        assert retrieved is not None
        assert retrieved.cycle_id == "cycle_target"

        missing = analyzer.get_outcome("cycle_missing")
        assert missing is None

    def test_get_outcomes_by_type(self, analyzer):
        """Test filtering outcomes by type."""
        outcomes_data = [
            (ResearchOutcomeType.DECISION_MADE, 3),
            (ResearchOutcomeType.CONFIDENCE_IMPROVED, 2),
            (ResearchOutcomeType.BLOCKED, 1),
        ]

        for outcome_type, count in outcomes_data:
            for i in range(count):
                analyzer.record_outcome(
                    ResearchCycleOutcome(
                        cycle_id=f"cycle_{outcome_type.value}_{i}",
                        research_session_id="session_001",
                        outcome_type=outcome_type,
                    )
                )

        decision_made = analyzer.get_outcomes_by_type(ResearchOutcomeType.DECISION_MADE)
        assert len(decision_made) == 3

        confidence_improved = analyzer.get_outcomes_by_type(
            ResearchOutcomeType.CONFIDENCE_IMPROVED
        )
        assert len(confidence_improved) == 2

    def test_get_recent_outcomes(self, analyzer):
        """Test getting recent outcomes."""
        for i in range(15):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id="session_001",
                    outcome_type=ResearchOutcomeType.DECISION_MADE,
                )
            )

        recent = analyzer.get_recent_outcomes(limit=5)
        assert len(recent) == 5
        # Most recent should be last recorded
        assert recent[0].cycle_id == "cycle_014"

    def test_record_feedback(self, analyzer):
        """Test recording feedback."""
        feedback = ResearchEffectivenessFeedback(
            cycle_id="cycle_001",
            category=FeedbackCategory.RESEARCH_QUALITY,
            feedback_text="Research findings were unclear",
            priority=7,
            action_suggested="Improve source selection",
        )

        analyzer.record_feedback(feedback)

        assert len(analyzer.feedback) == 1
        assert analyzer.feedback[0].category == FeedbackCategory.RESEARCH_QUALITY

    def test_get_high_priority_feedback(self, analyzer):
        """Test getting high priority feedback."""
        feedback_items = [
            ResearchEffectivenessFeedback(
                cycle_id="cycle_001",
                category=FeedbackCategory.RESEARCH_QUALITY,
                feedback_text="Low quality",
                priority=3,
            ),
            ResearchEffectivenessFeedback(
                cycle_id="cycle_002",
                category=FeedbackCategory.TIME_EFFICIENCY,
                feedback_text="Too slow",
                priority=8,
            ),
            ResearchEffectivenessFeedback(
                cycle_id="cycle_003",
                category=FeedbackCategory.COST_EFFICIENCY,
                feedback_text="Too expensive",
                priority=9,
            ),
        ]

        for item in feedback_items:
            analyzer.record_feedback(item)

        high_priority = analyzer.get_high_priority_feedback()
        assert len(high_priority) == 3
        # Should be sorted by priority descending
        assert high_priority[0].priority == 9
        assert high_priority[1].priority == 8
        assert high_priority[2].priority == 3

    def test_generate_improvement_report(self, analyzer):
        """Test generating improvement report."""
        # Add some successful outcomes
        for i in range(7):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id="session_001",
                    outcome_type=ResearchOutcomeType.DECISION_MADE,
                    decision_quality_before=DecisionQualityLevel.POOR,
                    decision_quality_after=DecisionQualityLevel.EXCELLENT,
                    confidence_before=30,
                    confidence_after=85,
                    research_cost=100.0,
                )
            )

        # Add some unsuccessful outcomes
        for i in range(7, 10):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id="session_001",
                    outcome_type=ResearchOutcomeType.BLOCKED,
                    research_cost=100.0,
                )
            )

        report = analyzer.generate_improvement_report()

        assert "report_generated_at" in report
        assert "metrics" in report
        assert "recent_outcomes" in report
        assert "insights" in report
        assert "recommendations" in report

        # Should have insights about high success rate
        assert any("confidence" in insight.lower() for insight in report["insights"])

    def test_metrics_aggregation(self, analyzer):
        """Test metrics aggregation across multiple outcomes."""
        # Add outcomes with various qualities and costs
        for i in range(5):
            analyzer.record_outcome(
                ResearchCycleOutcome(
                    cycle_id=f"cycle_{i:03d}",
                    research_session_id="session_001",
                    outcome_type=ResearchOutcomeType.DECISION_MADE,
                    decision_quality_before=DecisionQualityLevel.FAIR,
                    decision_quality_after=DecisionQualityLevel.EXCELLENT,
                    confidence_before=40,
                    confidence_after=90,
                    time_spent_seconds=3600,
                    research_cost=50.0,
                    follow_up_triggers_executed=3,
                    follow_up_triggers_successful=2,
                )
            )

        metrics = analyzer.get_metrics()

        assert metrics.total_cycles == 5
        assert metrics.successful_cycles == 5
        assert metrics.success_rate() == 100.0
        assert metrics.confidence_improvement_avg == 50.0
        assert metrics.follow_up_trigger_success_rate == pytest.approx(2/3, rel=0.01)
        assert metrics.cost_per_successful_decision == 50.0
        assert metrics.time_per_successful_decision == 3600.0

    def test_export_outcomes(self, analyzer):
        """Test exporting outcomes."""
        outcome = ResearchCycleOutcome(
            cycle_id="cycle_001",
            research_session_id="session_001",
            outcome_type=ResearchOutcomeType.DECISION_MADE,
            decision_quality_before=DecisionQualityLevel.POOR,
            decision_quality_after=DecisionQualityLevel.GOOD,
        )
        analyzer.record_outcome(outcome)

        exports = analyzer.export_outcomes()
        assert len(exports) == 1
        assert exports[0]["cycle_id"] == "cycle_001"
        assert exports[0]["outcome_type"] == "decision_made"

    def test_export_feedback(self, analyzer):
        """Test exporting feedback."""
        feedback = ResearchEffectivenessFeedback(
            cycle_id="cycle_001",
            category=FeedbackCategory.RESEARCH_QUALITY,
            feedback_text="Test feedback",
            priority=5,
        )
        analyzer.record_feedback(feedback)

        exports = analyzer.export_feedback()
        assert len(exports) == 1
        assert exports[0]["cycle_id"] == "cycle_001"
        assert exports[0]["category"] == "research_quality"


class TestResearchEffectivenessMetrics:
    """Test suite for ResearchEffectivenessMetrics class."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = ResearchEffectivenessMetrics()

        assert metrics.total_cycles == 0
        assert metrics.successful_cycles == 0
        assert metrics.confidence_improvement_avg == 0.0
        assert metrics.quality_improvement_avg == 0.0
        assert metrics.roi_avg == 0.0

    def test_success_rate_calculation(self):
        """Test success rate calculation in metrics."""
        metrics = ResearchEffectivenessMetrics()
        metrics.total_cycles = 10
        metrics.successful_cycles = 7

        success_rate = metrics.success_rate()
        assert success_rate == 70.0

    def test_metrics_serialization(self):
        """Test serializing metrics to dictionary."""
        metrics = ResearchEffectivenessMetrics(
            total_cycles=10,
            successful_cycles=8,
            confidence_improvement_avg=25.5,
            quality_improvement_avg=15.3,
            roi_avg=1.25,
            follow_up_trigger_success_rate=0.75,
        )

        result = metrics.to_dict()

        assert result["total_cycles"] == 10
        assert result["successful_cycles"] == 8
        assert result["success_rate_percent"] == 80.0
        assert result["confidence_improvement_avg"] == 25.5
        assert result["quality_improvement_avg"] == 15.3
        assert result["roi_avg"] == 1.25


class TestResearchEffectivenessFeedback:
    """Test suite for ResearchEffectivenessFeedback class."""

    def test_feedback_creation(self):
        """Test creating feedback."""
        feedback = ResearchEffectivenessFeedback(
            cycle_id="cycle_001",
            category=FeedbackCategory.RESEARCH_QUALITY,
            feedback_text="Research quality was excellent",
            priority=8,
            action_suggested="Maintain current approach",
        )

        assert feedback.cycle_id == "cycle_001"
        assert feedback.category == FeedbackCategory.RESEARCH_QUALITY
        assert feedback.priority == 8

    def test_feedback_serialization(self):
        """Test serializing feedback to dictionary."""
        feedback = ResearchEffectivenessFeedback(
            cycle_id="cycle_001",
            category=FeedbackCategory.COST_EFFICIENCY,
            feedback_text="Research was too expensive",
            priority=7,
            action_suggested="Reduce scope",
        )

        result = feedback.to_dict()

        assert result["cycle_id"] == "cycle_001"
        assert result["category"] == "cost_efficiency"
        assert result["priority"] == 7
        assert "created_at" in result
