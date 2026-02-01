"""Tests for BuildHistoryAnalyzer in autopack.research.analysis module.

Tests cover:
- Build metrics collection from BUILD_HISTORY.md
- Feasibility signal extraction
- Cost-effectiveness analysis from history
- Feasibility adjustment calculation
- Trend detection
- Analysis result generation
"""

from datetime import datetime
from pathlib import Path

import pytest

from autopack.research.analysis.build_history_analyzer import (
    BuildHistoryAnalysisResult, BuildHistoryAnalyzer, BuildMetrics,
    BuildOutcome, CostEffectivenessFeedback, FeasibilityFeedback,
    FeasibilitySignal, MetricTrend, get_build_history_feedback)


@pytest.fixture
def sample_build_history_content() -> str:
    """Create sample BUILD_HISTORY.md content."""
    # Use recent dates relative to today to avoid max_history_days filtering
    return """# BUILD_HISTORY

## Phase 1: Initial Setup
**Status**: ✓ SUCCESS
**Category**: setup
Completed: 2026-01-15T10:00:00

Estimated: 4 hours
Duration: 3.5 hours
5 files changed, 200 insertions, 50 deletions
10 tests passed

Tech: python, fastapi, postgresql

## Phase 2: API Implementation
**Status**: ✓ SUCCESS
**Category**: api
Completed: 2026-01-20T14:00:00

Estimated: 8 hours
Actual: 10 hours
15 files changed, 800 insertions, 100 deletions
25 tests, 92% pass rate

Tech: python, fastapi, redis

Lessons Learned:
- Always add proper error handling
- Use async operations for I/O

## Phase 3: Frontend Development
**Status**: ✗ FAILED
**Category**: frontend
Completed: 2026-01-22T09:00:00

Estimated: 6 hours
Duration: 12 hours
20 files changed, 1500 insertions, 200 deletions
Error: Build failed due to dependency conflict
5 errors, 3 warnings

Tech: typescript, react, vite

Issues:
- Dependency version mismatch
- Missing type definitions

## Phase 4: Testing Enhancement
**Status**: ✓ SUCCESS
**Category**: testing
Completed: 2026-01-25T11:00:00

Estimated: 4 hours
Duration: 4.5 hours
8 files changed, 400 insertions, 50 deletions
50 tests, 100% pass rate

Tech: python, pytest

## Phase 5: Deployment Setup
**Status**: ✓ SUCCESS
**Category**: deployment
Completed: 2026-01-28T16:00:00

Estimated cost: $500
Actual: 3 hours
5 files changed, 150 insertions, 20 deletions
12 tests passed

Tech: docker, kubernetes, aws
"""


@pytest.fixture
def temp_build_history(sample_build_history_content: str, tmp_path: Path) -> Path:
    """Create a temporary BUILD_HISTORY.md file."""
    history_path = tmp_path / "BUILD_HISTORY.md"
    history_path.write_text(sample_build_history_content, encoding="utf-8")
    return history_path


@pytest.fixture
def build_history_analyzer(temp_build_history: Path) -> BuildHistoryAnalyzer:
    """Create a BuildHistoryAnalyzer instance with sample data."""
    return BuildHistoryAnalyzer(
        build_history_path=temp_build_history,
        max_history_days=365,
    )


class TestBuildMetrics:
    """Tests for BuildMetrics dataclass."""

    def test_time_estimate_accuracy_exact(self):
        """Test time estimate accuracy when exact."""
        metrics = BuildMetrics(
            build_id="test-1",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            estimated_duration_hours=4.0,
            actual_duration_hours=4.0,
        )
        assert metrics.time_estimate_accuracy == 1.0

    def test_time_estimate_accuracy_overrun(self):
        """Test time estimate accuracy with overrun."""
        metrics = BuildMetrics(
            build_id="test-2",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            estimated_duration_hours=4.0,
            actual_duration_hours=6.0,
        )
        # Ratio is 1.5, so accuracy is 1 - |1 - 1.5| = 0.5
        assert metrics.time_estimate_accuracy == 0.5

    def test_time_estimate_accuracy_under(self):
        """Test time estimate accuracy when under estimate."""
        metrics = BuildMetrics(
            build_id="test-3",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            estimated_duration_hours=4.0,
            actual_duration_hours=2.0,
        )
        # Ratio is 0.5, so accuracy is 1 - |1 - 0.5| = 0.5
        assert metrics.time_estimate_accuracy == 0.5

    def test_time_estimate_accuracy_no_estimate(self):
        """Test time estimate accuracy with no estimate."""
        metrics = BuildMetrics(
            build_id="test-4",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            estimated_duration_hours=0.0,
            actual_duration_hours=4.0,
        )
        assert metrics.time_estimate_accuracy == 0.0

    def test_success_score_success(self):
        """Test success score for successful build."""
        metrics = BuildMetrics(
            build_id="test-5",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            test_count=10,
            test_pass_rate=1.0,
        )
        assert metrics.success_score == 1.0

    def test_success_score_partial(self):
        """Test success score for partial build."""
        metrics = BuildMetrics(
            build_id="test-6",
            project_type="api",
            outcome=BuildOutcome.PARTIAL,
            timestamp=datetime.now(),
            test_count=10,
            test_pass_rate=1.0,
        )
        assert metrics.success_score == 0.6

    def test_success_score_failed(self):
        """Test success score for failed build."""
        metrics = BuildMetrics(
            build_id="test-7",
            project_type="api",
            outcome=BuildOutcome.FAILED,
            timestamp=datetime.now(),
        )
        assert metrics.success_score == 0.0

    def test_success_score_with_low_test_pass_rate(self):
        """Test success score with low test pass rate."""
        metrics = BuildMetrics(
            build_id="test-8",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            test_count=10,
            test_pass_rate=0.5,
        )
        # 1.0 * 0.5 = 0.5
        assert metrics.success_score == 0.5

    def test_success_score_with_errors(self):
        """Test success score with errors."""
        metrics = BuildMetrics(
            build_id="test-9",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            error_count=5,
            blocking_issues=1,
        )
        # 1.0 * 1.0 * 0.5 (error factor at max penalty)
        assert metrics.success_score < 1.0

    def test_to_dict(self):
        """Test BuildMetrics serialization."""
        metrics = BuildMetrics(
            build_id="test-10",
            project_type="api",
            outcome=BuildOutcome.SUCCESS,
            timestamp=datetime.now(),
            files_changed=10,
            tech_stack=["python", "fastapi"],
        )
        data = metrics.to_dict()

        assert data["build_id"] == "test-10"
        assert data["project_type"] == "api"
        assert data["outcome"] == "success"
        assert data["files_changed"] == 10
        assert "python" in data["tech_stack"]


class TestBuildHistoryAnalyzer:
    """Tests for BuildHistoryAnalyzer class."""

    def test_init_default_settings(self, tmp_path: Path):
        """Test BuildHistoryAnalyzer initializes with default settings."""
        analyzer = BuildHistoryAnalyzer()
        assert analyzer.build_history_path == Path("BUILD_HISTORY.md")
        assert analyzer.max_history_days == 365

    def test_init_custom_settings(self, tmp_path: Path):
        """Test BuildHistoryAnalyzer initializes with custom settings."""
        custom_path = tmp_path / "custom_history.md"
        analyzer = BuildHistoryAnalyzer(
            build_history_path=custom_path,
            max_history_days=180,
        )
        assert analyzer.build_history_path == custom_path
        assert analyzer.max_history_days == 180

    def test_collect_build_metrics(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test collecting build metrics from history."""
        metrics = build_history_analyzer.collect_build_metrics()

        assert len(metrics) == 5
        assert all(isinstance(m, BuildMetrics) for m in metrics)

    def test_collect_build_metrics_caching(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test build metrics are cached."""
        metrics1 = build_history_analyzer.collect_build_metrics()
        metrics2 = build_history_analyzer.collect_build_metrics()

        # Should return same cached list
        assert metrics1 is metrics2

    def test_collect_build_metrics_force_refresh(
        self, build_history_analyzer: BuildHistoryAnalyzer
    ):
        """Test force refresh bypasses cache."""
        metrics1 = build_history_analyzer.collect_build_metrics()
        metrics2 = build_history_analyzer.collect_build_metrics(force_refresh=True)

        # Should return different list instances
        assert metrics1 is not metrics2

    def test_collect_build_metrics_empty_file(self, tmp_path: Path):
        """Test collecting metrics from empty file."""
        empty_path = tmp_path / "empty.md"
        empty_path.write_text("# BUILD_HISTORY\n\nNo phases yet.", encoding="utf-8")

        analyzer = BuildHistoryAnalyzer(build_history_path=empty_path)
        metrics = analyzer.collect_build_metrics()

        assert len(metrics) == 0

    def test_collect_build_metrics_missing_file(self, tmp_path: Path):
        """Test collecting metrics from missing file."""
        missing_path = tmp_path / "missing.md"
        analyzer = BuildHistoryAnalyzer(build_history_path=missing_path)
        metrics = analyzer.collect_build_metrics()

        assert len(metrics) == 0

    def test_extract_feasibility_signals(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test extracting feasibility signals from history."""
        signals = build_history_analyzer.extract_feasibility_signals()

        assert len(signals) > 0
        assert all(isinstance(s, FeasibilityFeedback) for s in signals)

        # Check for expected signal types
        signal_types = [s.signal_type for s in signals]
        assert FeasibilitySignal.COMPLEXITY_INDICATOR in signal_types
        assert FeasibilitySignal.ERROR_FREQUENCY in signal_types

    def test_extract_feasibility_signals_by_project_type(
        self, build_history_analyzer: BuildHistoryAnalyzer
    ):
        """Test extracting feasibility signals filtered by project type."""
        signals = build_history_analyzer.extract_feasibility_signals(project_type="api")

        # Should return signals based on filtered metrics
        assert isinstance(signals, list)

    def test_extract_feasibility_signals_by_tech_stack(
        self, build_history_analyzer: BuildHistoryAnalyzer
    ):
        """Test extracting feasibility signals filtered by tech stack."""
        signals = build_history_analyzer.extract_feasibility_signals(tech_stack=["python"])

        assert isinstance(signals, list)

    def test_analyze_cost_effectiveness(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test cost-effectiveness analysis from history."""
        feedback = build_history_analyzer.analyze_cost_effectiveness()

        assert isinstance(feedback, CostEffectivenessFeedback)
        assert feedback.sample_size > 0

    def test_analyze_cost_effectiveness_empty(self, tmp_path: Path):
        """Test cost-effectiveness analysis with no data."""
        empty_path = tmp_path / "empty.md"
        empty_path.write_text("# BUILD_HISTORY\n", encoding="utf-8")

        analyzer = BuildHistoryAnalyzer(build_history_path=empty_path)
        feedback = analyzer.analyze_cost_effectiveness()

        assert feedback.sample_size == 0
        assert feedback.estimation_accuracy == 0.0

    def test_analyze_complete(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test complete analysis from history."""
        result = build_history_analyzer.analyze()

        assert isinstance(result, BuildHistoryAnalysisResult)
        assert result.total_builds_analyzed == 5
        assert 0.0 <= result.overall_success_rate <= 1.0
        assert len(result.feasibility_signals) > 0
        assert isinstance(result.cost_effectiveness, CostEffectivenessFeedback)
        assert len(result.recommendations) >= 0
        assert len(result.warnings) >= 0

    def test_analyze_by_project_type(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test analysis filtered by project type."""
        result = build_history_analyzer.analyze(project_type="api")

        assert isinstance(result, BuildHistoryAnalysisResult)

    def test_analyze_by_tech_stack(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test analysis filtered by tech stack."""
        result = build_history_analyzer.analyze(tech_stack=["python"])

        assert isinstance(result, BuildHistoryAnalysisResult)

    def test_analyze_empty_results(self, tmp_path: Path):
        """Test analysis with no matching data."""
        empty_path = tmp_path / "empty.md"
        empty_path.write_text("# BUILD_HISTORY\n", encoding="utf-8")

        analyzer = BuildHistoryAnalyzer(build_history_path=empty_path)
        result = analyzer.analyze()

        assert result.total_builds_analyzed == 0
        assert len(result.recommendations) > 0  # Should have "no data" recommendation

    def test_get_feasibility_adjustment_positive(
        self, build_history_analyzer: BuildHistoryAnalyzer
    ):
        """Test feasibility adjustment calculation."""
        adjustment = build_history_analyzer.get_feasibility_adjustment(
            base_feasibility_score=0.5,
        )

        assert "original_score" in adjustment
        assert "adjusted_score" in adjustment
        assert "adjustment" in adjustment
        assert "confidence" in adjustment
        assert "explanation" in adjustment

        assert adjustment["original_score"] == 0.5
        assert 0.0 <= adjustment["adjusted_score"] <= 1.0

    def test_get_feasibility_adjustment_no_data(self, tmp_path: Path):
        """Test feasibility adjustment with no historical data."""
        empty_path = tmp_path / "empty.md"
        empty_path.write_text("# BUILD_HISTORY\n", encoding="utf-8")

        analyzer = BuildHistoryAnalyzer(build_history_path=empty_path)
        adjustment = analyzer.get_feasibility_adjustment(
            base_feasibility_score=0.5,
        )

        assert adjustment["original_score"] == 0.5
        assert adjustment["adjusted_score"] == 0.5
        assert adjustment["adjustment"] == 0.0
        assert adjustment["confidence"] == 0.0

    def test_calculate_trend_improving(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test trend calculation for improving values."""
        values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        trend = build_history_analyzer._calculate_trend(values)

        assert trend == MetricTrend.IMPROVING

    def test_calculate_trend_declining(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test trend calculation for declining values."""
        values = [0.8, 0.7, 0.6, 0.5, 0.4, 0.3]
        trend = build_history_analyzer._calculate_trend(values)

        assert trend == MetricTrend.DECLINING

    def test_calculate_trend_stable(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test trend calculation for stable values."""
        values = [0.5, 0.51, 0.49, 0.5, 0.51, 0.49]
        trend = build_history_analyzer._calculate_trend(values)

        assert trend == MetricTrend.STABLE

    def test_calculate_trend_insufficient_data(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test trend calculation with insufficient data."""
        values = [0.5, 0.6]
        trend = build_history_analyzer._calculate_trend(values)

        assert trend == MetricTrend.INSUFFICIENT_DATA

    def test_calculate_confidence_high(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test confidence calculation with many samples."""
        confidence = build_history_analyzer._calculate_confidence(25)
        assert confidence == 0.9

    def test_calculate_confidence_low(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test confidence calculation with few samples."""
        confidence = build_history_analyzer._calculate_confidence(3)
        assert confidence == 0.3


class TestFeasibilityFeedback:
    """Tests for FeasibilityFeedback dataclass."""

    def test_to_dict(self):
        """Test FeasibilityFeedback serialization."""
        feedback = FeasibilityFeedback(
            signal_type=FeasibilitySignal.COMPLEXITY_INDICATOR,
            signal_value=0.7,
            confidence=0.8,
            sample_size=10,
            trend=MetricTrend.IMPROVING,
            supporting_evidence=["Evidence 1", "Evidence 2"],
        )
        data = feedback.to_dict()

        assert data["signal_type"] == "complexity_indicator"
        assert data["signal_value"] == 0.7
        assert data["confidence"] == 0.8
        assert data["sample_size"] == 10
        assert data["trend"] == "improving"
        assert len(data["supporting_evidence"]) == 2


class TestCostEffectivenessFeedback:
    """Tests for CostEffectivenessFeedback dataclass."""

    def test_to_dict(self):
        """Test CostEffectivenessFeedback serialization."""
        feedback = CostEffectivenessFeedback(
            estimation_accuracy=0.75,
            cost_overrun_rate=0.2,
            avg_cost_deviation=0.15,
            high_cost_factors=["Factor 1"],
            cost_optimization_opportunities=["Opportunity 1"],
            sample_size=10,
        )
        data = feedback.to_dict()

        assert data["estimation_accuracy"] == 0.75
        assert data["cost_overrun_rate"] == 0.2
        assert data["avg_cost_deviation"] == 0.15
        assert "Factor 1" in data["high_cost_factors"]
        assert data["sample_size"] == 10


class TestBuildHistoryAnalysisResult:
    """Tests for BuildHistoryAnalysisResult dataclass."""

    def test_to_dict(self, build_history_analyzer: BuildHistoryAnalyzer):
        """Test BuildHistoryAnalysisResult serialization."""
        result = build_history_analyzer.analyze()
        data = result.to_dict()

        assert "project_type" in data
        assert "analysis_timestamp" in data
        assert "total_builds_analyzed" in data
        assert "overall_success_rate" in data
        assert "feasibility_signals" in data
        assert "cost_effectiveness" in data
        assert "recommendations" in data
        assert "warnings" in data


class TestConvenienceFunction:
    """Tests for get_build_history_feedback convenience function."""

    def test_get_build_history_feedback(self, temp_build_history: Path):
        """Test convenience function."""
        result = get_build_history_feedback(
            build_history_path=temp_build_history,
        )

        assert isinstance(result, dict)
        assert "total_builds_analyzed" in result
        assert "feasibility_signals" in result
        assert "cost_effectiveness" in result

    def test_get_build_history_feedback_with_filters(self, temp_build_history: Path):
        """Test convenience function with filters."""
        result = get_build_history_feedback(
            build_history_path=temp_build_history,
            project_type="api",
            tech_stack=["python"],
        )

        assert isinstance(result, dict)


class TestBuildOutcomeEnum:
    """Tests for BuildOutcome enum."""

    def test_build_outcome_values(self):
        """Test BuildOutcome enum values."""
        assert BuildOutcome.SUCCESS.value == "success"
        assert BuildOutcome.PARTIAL.value == "partial"
        assert BuildOutcome.FAILED.value == "failed"
        assert BuildOutcome.ABANDONED.value == "abandoned"
        assert BuildOutcome.BLOCKED.value == "blocked"


class TestFeasibilitySignalEnum:
    """Tests for FeasibilitySignal enum."""

    def test_feasibility_signal_values(self):
        """Test FeasibilitySignal enum values."""
        assert FeasibilitySignal.COMPLEXITY_INDICATOR.value == "complexity_indicator"
        assert FeasibilitySignal.TIME_ESTIMATE_ACCURACY.value == "time_estimate_accuracy"
        assert FeasibilitySignal.DEPENDENCY_RISK.value == "dependency_risk"
        assert FeasibilitySignal.TECH_STACK_MATURITY.value == "tech_stack_maturity"
        assert FeasibilitySignal.ERROR_FREQUENCY.value == "error_frequency"


class TestMetricTrendEnum:
    """Tests for MetricTrend enum."""

    def test_metric_trend_values(self):
        """Test MetricTrend enum values."""
        assert MetricTrend.IMPROVING.value == "improving"
        assert MetricTrend.STABLE.value == "stable"
        assert MetricTrend.DECLINING.value == "declining"
        assert MetricTrend.INSUFFICIENT_DATA.value == "insufficient_data"
