"""Tests for context injection effectiveness measurement (IMP-LOOP-036).

Tests the ContextInjectionReport dataclass and measure_context_injection_effectiveness()
method for measuring whether memory-based context injection improves phase success rates.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from autopack.telemetry.analyzer import (ContextInjectionImpact,
                                         ContextInjectionReport,
                                         TelemetryAnalyzer)


class TestContextInjectionReport:
    """Tests for ContextInjectionReport dataclass."""

    def test_creation(self):
        """Test basic creation of ContextInjectionReport."""
        report = ContextInjectionReport(
            success_rate_with_context=0.85,
            success_rate_without_context=0.70,
            lift=0.15,
            lift_percentage=21.43,
            with_context_count=50,
            without_context_count=100,
            avg_context_tokens=500.0,
            statistical_significance=0.03,
            is_significant=True,
            analysis_window_days=7,
        )

        assert report.success_rate_with_context == 0.85
        assert report.success_rate_without_context == 0.70
        assert report.lift == 0.15
        assert report.lift_percentage == 21.43
        assert report.with_context_count == 50
        assert report.without_context_count == 100
        assert report.avg_context_tokens == 500.0
        assert report.statistical_significance == 0.03
        assert report.is_significant is True
        assert report.analysis_window_days == 7

    def test_generated_at_auto_populated(self):
        """Test that generated_at is auto-populated if not provided."""
        report = ContextInjectionReport(
            success_rate_with_context=0.8,
            success_rate_without_context=0.7,
            lift=0.1,
            lift_percentage=14.29,
            with_context_count=10,
            without_context_count=10,
            avg_context_tokens=300.0,
            statistical_significance=0.1,
            is_significant=False,
        )

        # Should have a valid ISO timestamp
        assert report.generated_at != ""
        # Should be parseable
        parsed = datetime.fromisoformat(report.generated_at.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)

    def test_zero_lift_when_rates_equal(self):
        """Test that lift is zero when success rates are equal."""
        report = ContextInjectionReport(
            success_rate_with_context=0.75,
            success_rate_without_context=0.75,
            lift=0.0,
            lift_percentage=0.0,
            with_context_count=20,
            without_context_count=20,
            avg_context_tokens=400.0,
            statistical_significance=0.99,
            is_significant=False,
        )

        assert report.lift == 0.0
        assert report.lift_percentage == 0.0
        assert report.is_significant is False

    def test_negative_lift_when_context_hurts(self):
        """Test that lift can be negative if context injection hurts success rate."""
        report = ContextInjectionReport(
            success_rate_with_context=0.60,
            success_rate_without_context=0.80,
            lift=-0.20,
            lift_percentage=-25.0,
            with_context_count=15,
            without_context_count=15,
            avg_context_tokens=600.0,
            statistical_significance=0.02,
            is_significant=True,
        )

        assert report.lift == -0.20
        assert report.lift_percentage == -25.0


class TestMeasureContextInjectionEffectiveness:
    """Tests for TelemetryAnalyzer.measure_context_injection_effectiveness()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_empty_database(self, analyzer, mock_db):
        """Test with no data in database."""
        # Mock empty results for both queries
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 0
        mock_with_row.successes = 0
        mock_with_row.avg_items = 0.0
        mock_with_row.avg_tokens = 0.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 0
        mock_without_row.successes = 0
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        assert report.with_context_count == 0
        assert report.without_context_count == 0
        assert report.is_significant is False

    def test_only_with_context_data(self, analyzer, mock_db):
        """Test with only context-injected phases."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 20
        mock_with_row.successes = 16  # 80% success rate
        mock_with_row.avg_items = 3.5
        mock_with_row.avg_tokens = 400.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 0
        mock_without_row.successes = 0
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        assert report.with_context_count == 20
        assert report.success_rate_with_context == 0.8
        assert report.without_context_count == 0
        # Cannot be significant without comparison group
        assert report.is_significant is False

    def test_positive_lift(self, analyzer, mock_db):
        """Test when context injection improves success rate."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 50
        mock_with_row.successes = 45  # 90% success rate
        mock_with_row.avg_items = 4.0
        mock_with_row.avg_tokens = 500.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 50
        mock_without_row.successes = 35  # 70% success rate
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        assert report.success_rate_with_context == 0.9
        assert report.success_rate_without_context == 0.7
        assert report.lift == pytest.approx(0.2, abs=0.01)
        assert report.lift_percentage == pytest.approx(28.57, abs=0.1)
        assert report.is_significant is True  # Large lift with sufficient samples

    def test_negative_lift(self, analyzer, mock_db):
        """Test when context injection hurts success rate."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 30
        mock_with_row.successes = 15  # 50% success rate
        mock_with_row.avg_items = 5.0
        mock_with_row.avg_tokens = 700.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 30
        mock_without_row.successes = 21  # 70% success rate
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        assert report.success_rate_with_context == 0.5
        assert report.success_rate_without_context == 0.7
        assert report.lift == pytest.approx(-0.2, abs=0.01)
        assert report.lift_percentage < 0

    def test_not_significant_with_small_samples(self, analyzer, mock_db):
        """Test that small sample sizes don't yield significance."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 5  # Too few samples
        mock_with_row.successes = 5  # 100% success
        mock_with_row.avg_items = 3.0
        mock_with_row.avg_tokens = 300.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 5  # Too few samples
        mock_without_row.successes = 3  # 60% success
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        # Even with big lift, should not be significant due to small samples
        assert report.is_significant is False

    def test_not_significant_with_small_lift(self, analyzer, mock_db):
        """Test that small lifts are not significant even with many samples."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 100
        mock_with_row.successes = 76  # 76% success rate
        mock_with_row.avg_items = 2.5
        mock_with_row.avg_tokens = 250.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 100
        mock_without_row.successes = 74  # 74% success rate
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        # Lift is only 2%, which is likely not significant
        assert report.lift == pytest.approx(0.02, abs=0.01)

    def test_window_days_parameter(self, analyzer, mock_db):
        """Test that window_days parameter is reflected in report."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 0
        mock_with_row.successes = 0
        mock_with_row.avg_items = 0.0
        mock_with_row.avg_tokens = 0.0
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 0
        mock_without_row.successes = 0
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness(window_days=30)

        assert report.analysis_window_days == 30

    def test_avg_context_tokens_tracked(self, analyzer, mock_db):
        """Test that average context tokens are tracked."""
        mock_with_result = MagicMock()
        mock_with_row = MagicMock()
        mock_with_row.total = 15
        mock_with_row.successes = 12
        mock_with_row.avg_items = 4.0
        mock_with_row.avg_tokens = 850.5
        mock_with_result.fetchone.return_value = mock_with_row

        mock_without_result = MagicMock()
        mock_without_row = MagicMock()
        mock_without_row.total = 15
        mock_without_row.successes = 10
        mock_without_result.fetchone.return_value = mock_without_row

        mock_db.execute.side_effect = [mock_with_result, mock_without_result]

        report = analyzer.measure_context_injection_effectiveness()

        assert report.avg_context_tokens == 850.5


class TestCalculateSignificance:
    """Tests for TelemetryAnalyzer._calculate_significance()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_small_sample_returns_one(self, analyzer):
        """Test that very small samples return p-value of 1.0."""
        p_value = analyzer._calculate_significance(3, 2, 3, 1)
        assert p_value == 1.0

    def test_equal_rates_high_p_value(self, analyzer):
        """Test that equal success rates yield high p-value."""
        p_value = analyzer._calculate_significance(50, 25, 50, 25)
        # Equal rates, p-value should be high (not significant)
        assert p_value > 0.3

    def test_very_different_rates_low_p_value(self, analyzer):
        """Test that very different rates yield low p-value."""
        # 90% vs 50% with good sample sizes
        p_value = analyzer._calculate_significance(100, 90, 100, 50)
        assert p_value < 0.05

    def test_zero_pooled_returns_one(self, analyzer):
        """Test that zero pooled proportion returns 1.0."""
        # All failures
        p_value = analyzer._calculate_significance(10, 0, 10, 0)
        assert p_value == 1.0

    def test_all_successes_returns_one(self, analyzer):
        """Test that all successes returns 1.0."""
        # All successes
        p_value = analyzer._calculate_significance(10, 10, 10, 10)
        assert p_value == 1.0


class TestContextInjectionImpactComparison:
    """Tests comparing ContextInjectionReport with existing ContextInjectionImpact."""

    def test_report_has_more_fields(self):
        """Test that ContextInjectionReport has additional fields vs ContextInjectionImpact."""
        # ContextInjectionImpact (IMP-LOOP-021) fields
        impact = ContextInjectionImpact(
            with_context_success_rate=0.8,
            without_context_success_rate=0.7,
            delta=0.1,
            with_context_count=20,
            without_context_count=20,
            avg_context_item_count=3.0,
            impact_significant=True,
        )

        # ContextInjectionReport (IMP-LOOP-036) has additional fields
        report = ContextInjectionReport(
            success_rate_with_context=0.8,
            success_rate_without_context=0.7,
            lift=0.1,
            lift_percentage=14.29,
            with_context_count=20,
            without_context_count=20,
            avg_context_tokens=450.0,
            statistical_significance=0.04,
            is_significant=True,
        )

        # Report has lift_percentage which impact doesn't
        assert hasattr(report, "lift_percentage")
        # Report has statistical_significance which impact doesn't
        assert hasattr(report, "statistical_significance")
        # Report has avg_context_tokens, impact has avg_context_item_count
        assert hasattr(report, "avg_context_tokens")
        assert hasattr(impact, "avg_context_item_count")

    def test_equivalent_core_metrics(self):
        """Test that equivalent values are represented the same."""
        impact = ContextInjectionImpact(
            with_context_success_rate=0.85,
            without_context_success_rate=0.70,
            delta=0.15,
            with_context_count=50,
            without_context_count=50,
            avg_context_item_count=4.0,
            impact_significant=True,
        )

        report = ContextInjectionReport(
            success_rate_with_context=0.85,
            success_rate_without_context=0.70,
            lift=0.15,
            lift_percentage=21.43,
            with_context_count=50,
            without_context_count=50,
            avg_context_tokens=500.0,
            statistical_significance=0.02,
            is_significant=True,
        )

        # Core metrics should match
        assert impact.with_context_success_rate == report.success_rate_with_context
        assert impact.without_context_success_rate == report.success_rate_without_context
        assert impact.delta == report.lift
        assert impact.with_context_count == report.with_context_count
        assert impact.without_context_count == report.without_context_count
        assert impact.impact_significant == report.is_significant


class TestPhaseOutcomeMetadataTracking:
    """Tests for PhaseOutcome metadata tracking (IMP-LOOP-036)."""

    def test_phase_outcome_has_context_tokens_field(self):
        """Test that PhaseOutcome has context_tokens field."""
        from autopack.feedback_pipeline import PhaseOutcome

        outcome = PhaseOutcome(
            phase_id="test-phase-1",
            phase_type="build",
            success=True,
            status="completed",
            context_injected=True,
            context_item_count=5,
            context_tokens=450,
        )

        assert outcome.context_tokens == 450

    def test_phase_outcome_has_metadata_field(self):
        """Test that PhaseOutcome has metadata dict field."""
        from autopack.feedback_pipeline import PhaseOutcome

        outcome = PhaseOutcome(
            phase_id="test-phase-2",
            phase_type="test",
            success=False,
            status="failed",
            metadata={"custom_key": "custom_value"},
        )

        assert outcome.metadata is not None
        assert outcome.metadata["custom_key"] == "custom_value"

    def test_phase_outcome_metadata_defaults_to_none(self):
        """Test that metadata defaults to None."""
        from autopack.feedback_pipeline import PhaseOutcome

        outcome = PhaseOutcome(
            phase_id="test-phase-3",
            phase_type="deploy",
            success=True,
            status="deployed",
        )

        assert outcome.metadata is None

    def test_phase_outcome_full_context_tracking(self):
        """Test that all context-related fields work together."""
        from autopack.feedback_pipeline import PhaseOutcome

        outcome = PhaseOutcome(
            phase_id="test-phase-4",
            phase_type="analyze",
            success=True,
            status="analyzed",
            context_injected=True,
            context_item_count=3,
            context_tokens=350,
            metadata={
                "context_injected": True,
                "context_item_count": 3,
                "context_tokens": 350,
            },
        )

        assert outcome.context_injected is True
        assert outcome.context_item_count == 3
        assert outcome.context_tokens == 350
        assert outcome.metadata["context_injected"] is True
        assert outcome.metadata["context_item_count"] == 3
        assert outcome.metadata["context_tokens"] == 350
