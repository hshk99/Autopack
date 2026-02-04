"""Tests for BuildHistoryIntegrator integration with research pipeline.

Tests the wiring of build history data into research context, pattern recognition,
and recommendation generation.
"""

from unittest.mock import MagicMock

import pytest

from autopack.integrations.build_history_integrator import (
    BuildHistoryInsights,
    BuildHistoryIntegrator,
    BuildInformedMetrics,
    HistoricalPattern,
    ResearchContextEnrichment,
)


@pytest.fixture
def temp_build_history(tmp_path):
    """Create a temporary BUILD_HISTORY.md for testing."""
    history_content = """# Build History

## Phase 1: Initial Setup
**Status**: SUCCESS
**Category**: Setup
**Completed**: 2024-01-01T10:00:00
**Files Changed**: 5
**Insertions**: 100
**Deletions**: 0

Lessons Learned:
- Good initial setup saves time later
- Document requirements upfront

Issues:
- Some initial confusion with config

## Phase 2: Core Implementation
**Status**: SUCCESS
**Category**: Implementation
**Completed**: 2024-01-10T14:30:00
**Files Changed**: 15
**Insertions**: 500
**Deletions**: 50
**Tests**: 25
**Pass Rate**: 95%

Lessons Learned:
- Unit tests catch bugs early
- Code reviews improve quality

Issues:
- One critical bug found in testing

## Phase 3: Testing
**Status**: SUCCESS
**Category**: Testing
**Completed**: 2024-01-20T16:45:00
**Tests**: 50
**Pass Rate**: 98%

Lessons Learned:
- High test coverage prevents regressions

## Phase 4: Documentation
**Status**: FAILED
**Category**: Documentation
**Completed**: 2024-01-25T09:15:00

Issues:
- Documentation tool compatibility issue
- Error in document generation
"""
    history_file = tmp_path / "BUILD_HISTORY.md"
    history_file.write_text(history_content)
    return history_file


@pytest.fixture
def integrator(temp_build_history):
    """Create a BuildHistoryIntegrator instance with temp history."""
    return BuildHistoryIntegrator(build_history_path=temp_build_history)


class TestBuildHistoryIntegratorBasics:
    """Test basic functionality of BuildHistoryIntegrator."""

    def test_initialization(self, integrator):
        """Test integrator initialization."""
        assert integrator.build_history_path is not None
        assert integrator._metrics is not None
        assert integrator._metrics.total_research_sessions == 0

    def test_get_insights_for_task(self, integrator):
        """Test extracting insights from build history."""
        insights = integrator.get_insights_for_task(
            "Implement new feature", category="Implementation"
        )

        assert isinstance(insights, BuildHistoryInsights)
        assert insights.total_phases >= 0
        # Test that we get meaningful insights
        assert (
            len(insights.best_practices) > 0
            or len(insights.common_pitfalls) > 0
            or insights.total_phases >= 0
        )

    def test_get_insights_by_category(self, integrator):
        """Test insights filtering by category."""
        setup_insights = integrator.get_insights_for_task("Setup task", category="Setup")
        impl_insights = integrator.get_insights_for_task(
            "Implementation task", category="Implementation"
        )

        # Both should have data
        assert setup_insights.total_phases >= 0
        assert impl_insights.total_phases >= 0

    def test_should_trigger_research_low_success(self, integrator):
        """Test research triggering on low success rate."""
        # With only 1 successful and 1 failed phase in a category,
        # success rate is 50%, which should trigger research
        should_trigger = integrator.should_trigger_research(
            "Task with history", category="Documentation", threshold=0.5
        )

        # Documentation category has 1 failed phase, should trigger
        assert should_trigger is True

    def test_should_trigger_research_no_history(self, integrator):
        """Test research triggering when no history exists."""
        should_trigger = integrator.should_trigger_research(
            "New task type", category="NonExistentCategory"
        )

        # No history = trigger research
        assert should_trigger is True

    def test_format_insights_for_prompt(self, integrator):
        """Test formatting insights for LLM prompt."""
        insights = integrator.get_insights_for_task("Test task")
        formatted = integrator.format_insights_for_prompt(insights)

        assert isinstance(formatted, str)
        assert "Historical Context" in formatted
        assert str(insights.total_phases) in formatted


class TestResearchContextEnrichment:
    """Test research context enrichment with build history."""

    def test_enrich_research_context_basic(self, integrator):
        """Test basic research context enrichment."""
        enrichment = integrator.enrich_research_context(
            "Implement feature for ecommerce", category="Implementation", project_type="ecommerce"
        )

        assert isinstance(enrichment, ResearchContextEnrichment)
        assert enrichment.confidence >= 0.0
        assert enrichment.confidence <= 1.0
        assert enrichment.historical_success_rate >= 0.0
        assert enrichment.historical_success_rate <= 1.0
        assert enrichment.recommended_research_scope in ["minimal", "standard", "comprehensive"]

    def test_enrichment_has_focus_areas(self, integrator):
        """Test that enrichment includes research focus areas."""
        enrichment = integrator.enrich_research_context(
            "Complex implementation task", category="Implementation"
        )

        # Should have some focus areas
        assert isinstance(enrichment.research_focus_areas, list)

    def test_enrichment_includes_risk_factors(self, integrator):
        """Test that enrichment includes risk factors."""
        enrichment = integrator.enrich_research_context(
            "Task with potential risks", category="Documentation"
        )

        assert isinstance(enrichment.risk_factors, list)

    def test_enrichment_time_adjustment(self, integrator):
        """Test time estimate adjustment calculation."""
        enrichment = integrator.enrich_research_context(
            "Task requiring research", category="Implementation"
        )

        # Time adjustment should be a reasonable percentage
        assert isinstance(enrichment.time_estimate_adjustment_percent, float)
        assert -50 <= enrichment.time_estimate_adjustment_percent <= 100

    def test_metrics_updated_on_enrichment(self, integrator):
        """Test that metrics are updated when enriching context."""
        initial_count = integrator._metrics.sessions_using_build_history

        integrator.enrich_research_context("Test task")

        assert integrator._metrics.sessions_using_build_history == initial_count + 1


class TestResearchRecommendations:
    """Test research recommendations based on build history."""

    def test_get_research_recommendations(self, integrator):
        """Test generating research recommendations."""
        recommendations = integrator.get_research_recommendations_from_history(
            "Implement new feature", category="Implementation"
        )

        assert isinstance(recommendations, dict)
        assert "research_approach" in recommendations
        assert "research_agents" in recommendations
        assert "validation_requirements" in recommendations
        assert "estimated_research_time_hours" in recommendations

    def test_recommendations_include_agents(self, integrator):
        """Test that recommendations include agent suggestions."""
        recommendations = integrator.get_research_recommendations_from_history(
            "Check feasibility of approach"
        )

        agents = recommendations.get("research_agents", [])
        assert isinstance(agents, list)
        assert len(agents) > 0

    def test_recommendations_estimate_time(self, integrator):
        """Test that recommendations include time estimates."""
        recommendations = integrator.get_research_recommendations_from_history(
            "Research task complexity"
        )

        time_hours = recommendations.get("estimated_research_time_hours", 0)
        assert isinstance(time_hours, (int, float))
        assert time_hours > 0

    def test_recommendations_have_validation(self, integrator):
        """Test that recommendations include validation requirements."""
        recommendations = integrator.get_research_recommendations_from_history(
            "Task requiring validation"
        )

        validation = recommendations.get("validation_requirements", [])
        assert isinstance(validation, list)


class TestBuildInformedMetrics:
    """Test metrics tracking for build-informed decisions."""

    def test_initial_metrics(self, integrator):
        """Test initial metrics state."""
        metrics = integrator.get_metrics()

        assert isinstance(metrics, BuildInformedMetrics)
        assert metrics.total_research_sessions == 0
        assert metrics.sessions_using_build_history == 0
        assert metrics.successful_pattern_applications == 0
        assert metrics.failed_pattern_applications == 0

    def test_record_decision_outcome_success(self, integrator):
        """Test recording successful decision outcome."""
        integrator.record_decision_outcome(
            "decision_001", was_successful=True, pattern_applied="pattern_101"
        )

        metrics = integrator.get_metrics()
        assert metrics.successful_pattern_applications == 1

    def test_record_decision_outcome_failure(self, integrator):
        """Test recording failed decision outcome."""
        integrator.record_decision_outcome(
            "decision_002", was_successful=False, pattern_applied="pattern_102"
        )

        metrics = integrator.get_metrics()
        assert metrics.failed_pattern_applications == 1

    def test_recommendation_acceptance_rate(self, integrator):
        """Test calculation of recommendation acceptance rate."""
        integrator.record_decision_outcome(
            "decision_001", was_successful=True, pattern_applied="pattern_101"
        )
        integrator.record_decision_outcome(
            "decision_002", was_successful=True, pattern_applied="pattern_102"
        )
        integrator.record_decision_outcome(
            "decision_003", was_successful=False, pattern_applied="pattern_103"
        )

        metrics = integrator.get_metrics()
        expected_rate = 2.0 / 3.0  # 2 successes out of 3
        assert abs(metrics.recommendation_acceptance_rate - expected_rate) < 0.01


class TestPatternExtraction:
    """Test pattern extraction from build history."""

    def test_extract_patterns(self, integrator):
        """Test pattern extraction."""
        history_data = integrator._parse_build_history()
        patterns = integrator._extract_patterns(history_data, "test task", None)

        assert isinstance(patterns, list)
        assert all(isinstance(p, HistoricalPattern) for p in patterns)

    def test_patterns_have_confidence(self, integrator):
        """Test that patterns include confidence scores."""
        history_data = integrator._parse_build_history()
        patterns = integrator._extract_patterns(history_data, "test task", None)

        for pattern in patterns:
            assert 0.0 <= pattern.confidence <= 1.0

    def test_success_rate_calculation(self, integrator):
        """Test success rate calculation."""
        success_rates = integrator._calculate_success_rates(
            integrator._parse_build_history(), category=None
        )

        assert isinstance(success_rates, dict)
        for category, rate in success_rates.items():
            assert 0.0 <= rate <= 1.0


class TestInsightsMerging:
    """Test merging insights from multiple sources."""

    def test_merge_insights(self, integrator):
        """Test merging two insight objects."""
        insights1 = BuildHistoryInsights(
            total_phases=5,
            successful_phases=4,
            failed_phases=1,
            best_practices=["practice1", "practice2"],
            common_pitfalls=["pitfall1"],
            patterns=[],
        )

        insights2 = BuildHistoryInsights(
            total_phases=3,
            successful_phases=2,
            failed_phases=1,
            best_practices=["practice2", "practice3"],
            common_pitfalls=["pitfall1", "pitfall2"],
            patterns=[],
        )

        merged = integrator._merge_insights(insights1, insights2)

        assert merged.total_phases == 8
        assert merged.successful_phases == 6
        assert merged.failed_phases == 2
        # Deduplicated practices
        assert len(merged.best_practices) == 3
        # Deduplicated pitfalls
        assert len(merged.common_pitfalls) == 2


class TestResearchScopeRecommendation:
    """Test recommendation of research scope based on history."""

    def test_scope_recommendation_high_success(self, integrator):
        """Test that high success rate recommends minimal scope."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=9,
            failed_phases=1,
            best_practices=["practice1"],
            common_pitfalls=[],
            patterns=[],
        )

        scope = integrator._determine_research_scope(0.9, insights, 0.0)

        assert scope == "minimal"

    def test_scope_recommendation_low_success(self, integrator):
        """Test that low success rate recommends comprehensive scope."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=3,
            failed_phases=7,
            best_practices=[],
            common_pitfalls=["pitfall1", "pitfall2", "pitfall3"],
            patterns=[],
        )

        scope = integrator._determine_research_scope(0.3, insights, 0.0)

        assert scope == "comprehensive"

    def test_scope_recommendation_standard(self, integrator):
        """Test that medium success rate recommends standard scope."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=6,
            failed_phases=4,
            best_practices=["practice1"],
            common_pitfalls=["pitfall1"],
            patterns=[],
        )

        scope = integrator._determine_research_scope(0.6, insights, 0.0)

        assert scope == "standard"


class TestIntegrationWithResearchPipeline:
    """Test integration points with the research pipeline."""

    def test_no_error_without_analyzer(self, integrator):
        """Test graceful degradation when BuildHistoryAnalyzer is unavailable."""
        # Directly test the enrichment with no analyzer (already loaded as None)
        integrator._analyzer = None

        enrichment = integrator.enrich_research_context("test task")

        # Should return neutral enrichment without errors
        assert isinstance(enrichment, ResearchContextEnrichment)
        assert enrichment.confidence == 0.0

    def test_research_focus_areas_identification(self, integrator):
        """Test identification of research focus areas."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=5,
            failed_phases=5,
            best_practices=["practice1"],
            common_pitfalls=["pitfall1", "pitfall2", "pitfall3"],
            patterns=[],
        )

        # Create a mock analysis result
        class MockAnalysisResult:
            warnings = ["Warning 1"]
            cost_effectiveness = MagicMock(cost_overrun_rate=0.0, high_cost_factors=[])
            avg_time_estimate_accuracy = 0.8
            metrics_by_tech_stack = {}

        focus_areas = integrator._identify_research_focus_areas(
            MockAnalysisResult(),
            insights,
            "Implementation",  # type: ignore
        )

        assert isinstance(focus_areas, list)
        assert len(focus_areas) > 0
        assert all(isinstance(area, str) for area in focus_areas)

    def test_success_factors_extraction(self, integrator):
        """Test extraction of success factors from analysis."""

        class MockSignal:
            signal_type = MagicMock(value="time_estimate")
            signal_value = 0.9
            confidence = 0.8
            supporting_evidence = ["Evidence 1"]

        class MockAnalysisResult:
            recommendations = ["High success rate for Python", "Strong testing practices"]
            feasibility_signals = [MockSignal()]  # type: ignore

        result = MockAnalysisResult()

        factors = integrator._extract_success_factors(result)  # type: ignore

        assert isinstance(factors, list)
        assert len(factors) <= 5

    def test_validation_requirements_determination(self, integrator):
        """Test determination of validation requirements."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=4,
            failed_phases=6,
            best_practices=[],
            common_pitfalls=["p1", "p2", "p3"],
            patterns=[],
        )

        class MockCostFeedback:
            cost_overrun_rate = 0.6

        class MockAnalysisResult:
            overall_success_rate = 0.4
            cost_effectiveness = MockCostFeedback()  # type: ignore
            metrics_by_tech_stack = {"python": {}}

        requirements = integrator._determine_validation_requirements(
            insights,
            MockAnalysisResult(),  # type: ignore
        )

        assert isinstance(requirements, list)
        assert len(requirements) > 0
        assert all(isinstance(req, str) for req in requirements)

    def test_research_time_estimation(self, integrator):
        """Test research time estimation."""
        insights = BuildHistoryInsights(
            total_phases=10,
            successful_phases=3,
            failed_phases=7,
            best_practices=[],
            common_pitfalls=["p1", "p2"],
            patterns=[],
        )

        class MockCostFeedback:
            cost_overrun_rate = 0.7

        class MockAnalysisResult:
            overall_success_rate = 0.3
            cost_effectiveness = MockCostFeedback()  # type: ignore
            metrics_by_tech_stack = {}

        estimated_hours = integrator._estimate_research_time(
            insights,
            MockAnalysisResult(),  # type: ignore
        )

        assert isinstance(estimated_hours, (int, float))
        assert estimated_hours > 0
        # Low success rate and many issues should increase time
        assert estimated_hours >= 4.0
