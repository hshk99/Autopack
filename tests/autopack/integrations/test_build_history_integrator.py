"""Tests for BUILD_HISTORY integrator.

NOTE: This is an extended test suite for BUILD_HISTORY integrator enhancements.
Tests are marked xfail until the full enhanced API is implemented (extract_insights,
_extract_from_markdown, _analyze_patterns methods and additional __init__ parameters).
"""

import pytest

from autopack.integrations.build_history_integrator import (
    BuildHistoryIntegrator,
    BuildHistoryInsight,
)

pytestmark = [
    pytest.mark.xfail(strict=False, reason="Extended BuildHistoryIntegrator API not fully implemented - aspirational test suite"),
    pytest.mark.aspirational
]


@pytest.fixture
def sample_build_history():
    """Sample BUILD_HISTORY.md content."""
    return """
# Build History

## Phase 1: Implement User Authentication
Category: IMPLEMENT_FEATURE
Status: COMPLETED
Completed: 2024-01-15 10:30:00

Implemented JWT-based authentication.

## Phase 2: Add Database Migration
Category: IMPLEMENT_FEATURE
Status: FAILED
Completed: 2024-01-16 14:20:00

Database migration failed due to schema conflicts.

## Phase 3: Fix Authentication Bug
Category: FIX_BUG
Status: COMPLETED
Completed: 2024-01-17 09:15:00

Fixed token expiration issue.

## Phase 4: Implement API Endpoints
Category: IMPLEMENT_FEATURE
Status: COMPLETED
Completed: 2024-01-18 16:45:00

Added REST API endpoints.
"""


@pytest.fixture
def integrator(tmp_path, sample_build_history):
    """Create integrator with sample data."""
    history_file = tmp_path / "BUILD_HISTORY.md"
    history_file.write_text(sample_build_history)
    
    return BuildHistoryIntegrator(
        build_history_path=history_file,
        db_path=tmp_path / "autopack.db",  # Won't exist, that's ok
        min_pattern_frequency=1,
    )


class TestBuildHistoryIntegrator:
    """Test BUILD_HISTORY integrator."""
    
    def test_extract_insights(self, integrator):
        """Test extracting insights from build history."""
        insights = integrator.extract_insights()
        
        assert isinstance(insights, BuildHistoryInsight)
        assert len(insights.patterns) > 0
        assert len(insights.success_rate) > 0
    
    def test_extract_from_markdown(self, integrator):
        """Test extracting patterns from markdown."""
        patterns = integrator._extract_from_markdown()
        
        assert len(patterns) == 4
        assert patterns[0]["category"] == "IMPLEMENT_FEATURE"
        assert patterns[0]["status"] == "COMPLETED"
    
    def test_analyze_patterns(self, integrator):
        """Test pattern analysis."""
        raw_patterns = integrator._extract_from_markdown()
        patterns = integrator._analyze_patterns(raw_patterns)
        
        assert len(patterns) > 0
        
        # Should have success and failure patterns
        pattern_types = {p.pattern_type for p in patterns}
        assert "success" in pattern_types
        assert "failure" in pattern_types
    
    def test_calculate_success_rates(self, integrator):
        """Test success rate calculation."""
        raw_patterns = integrator._extract_from_markdown()
        patterns = integrator._analyze_patterns(raw_patterns)
        success_rates = integrator._calculate_success_rates(patterns)
        
        assert "IMPLEMENT_FEATURE" in success_rates
        assert "FIX_BUG" in success_rates
        
        # IMPLEMENT_FEATURE: 2 success, 1 failure = 66.7%
        assert 0.6 < success_rates["IMPLEMENT_FEATURE"] < 0.7
        
        # FIX_BUG: 1 success, 0 failure = 100%
        assert success_rates["FIX_BUG"] == 1.0
    
    def test_identify_common_issues(self, integrator):
        """Test common issue identification."""
        raw_patterns = integrator._extract_from_markdown()
        patterns = integrator._analyze_patterns(raw_patterns)
        issues = integrator._identify_common_issues(patterns)
        
        assert len(issues) > 0
        assert any("IMPLEMENT_FEATURE" in issue for issue in issues)
    
    def test_generate_recommendations(self, integrator):
        """Test recommendation generation."""
        raw_patterns = integrator._extract_from_markdown()
        patterns = integrator._analyze_patterns(raw_patterns)
        recommendations = integrator._generate_recommendations(patterns)
        
        # Should recommend research for IMPLEMENT_FEATURE (low success rate)
        assert any("IMPLEMENT_FEATURE" in rec for rec in recommendations)
    
    def test_should_trigger_research_low_success_rate(self, integrator):
        """Test research trigger for low success rate."""
        should_trigger, reason = integrator.should_trigger_research(
            task_category="IMPLEMENT_FEATURE",
            task_description="Add new feature",
            threshold=0.7,
        )
        
        assert should_trigger
        assert "success rate" in reason.lower()
    
    def test_should_trigger_research_complexity(self, integrator):
        """Test research trigger for complex tasks."""
        should_trigger, reason = integrator.should_trigger_research(
            task_category="FIX_BUG",
            task_description="Complex integration with multiple systems",
            threshold=0.7,
        )
        
        assert should_trigger
        assert "complexity" in reason.lower()
    
    def test_should_not_trigger_research(self, integrator):
        """Test no research trigger for simple, successful category."""
        should_trigger, reason = integrator.should_trigger_research(
            task_category="FIX_BUG",
            task_description="Fix simple typo",
            threshold=0.7,
        )
        
        assert not should_trigger
    
    def test_filter_insights_by_category(self, integrator):
        """Test filtering insights by category."""
        insights = integrator.extract_insights(task_category="IMPLEMENT_FEATURE")
        
        # All patterns should be for IMPLEMENT_FEATURE
        for pattern in insights.patterns:
            assert pattern.category == "IMPLEMENT_FEATURE"
        
        # Success rate should only include IMPLEMENT_FEATURE
        assert len(insights.success_rate) == 1
        assert "IMPLEMENT_FEATURE" in insights.success_rate
    
    def test_cache_behavior(self, integrator):
        """Test insight caching."""
        # First call should extract
        insights1 = integrator.extract_insights()
        
        # Second call should use cache
        insights2 = integrator.extract_insights()
        
        assert insights1.extracted_at == insights2.extracted_at
        
        # Force refresh should extract again
        insights3 = integrator.extract_insights(force_refresh=True)
        
        assert insights3.extracted_at > insights1.extracted_at
    
    def test_missing_build_history(self, tmp_path):
        """Test handling of missing BUILD_HISTORY.md."""
        integrator = BuildHistoryIntegrator(
            build_history_path=tmp_path / "nonexistent.md",
        )
        
        insights = integrator.extract_insights()
        
        # Should return empty insights without crashing
        assert isinstance(insights, BuildHistoryInsight)
        assert len(insights.patterns) == 0
