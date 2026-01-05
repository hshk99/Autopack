"""Tests for Adoption Readiness Framework"""

import pytest
from autopack.research.frameworks.adoption_readiness import AdoptionReadiness


class TestAdoptionReadiness:
    """Test suite for AdoptionReadiness class."""

    def test_initialization(self):
        """Test initialization."""
        framework = AdoptionReadiness()
        assert framework.weights is not None
        assert framework.barriers == []
        assert framework.enablers == []
        assert abs(sum(framework.weights.values()) - 1.0) < 0.001

    def test_set_score(self):
        """Test setting scores."""
        framework = AdoptionReadiness()
        framework.set_score("customer_readiness", 7.5)
        assert framework.scores["customer_readiness"] == 7.5

    def test_add_barrier(self):
        """Test adding barriers."""
        framework = AdoptionReadiness()
        framework.add_barrier("Regulatory hurdles", "high", "Engage with regulators")

        assert len(framework.barriers) == 1
        assert framework.barriers[0]["name"] == "Regulatory hurdles"
        assert framework.barriers[0]["impact"] == "high"

    def test_add_barrier_invalid_impact(self):
        """Test that invalid impact raises ValueError."""
        framework = AdoptionReadiness()
        with pytest.raises(ValueError, match="Impact must be one of"):
            framework.add_barrier("Barrier", "invalid")

    def test_add_enabler(self):
        """Test adding enablers."""
        framework = AdoptionReadiness()
        framework.add_enabler("Strong demand", "high", "Capitalize on demand")

        assert len(framework.enablers) == 1
        assert framework.enablers[0]["name"] == "Strong demand"
        assert framework.enablers[0]["strength"] == "high"

    def test_calculate_score(self):
        """Test base score calculation."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)

        score = framework.calculate_score()
        assert score == 7.0

    def test_get_barrier_adjusted_score(self):
        """Test barrier-adjusted score."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.0)

        # Add barrier
        framework.add_barrier("Major barrier", "high")

        adjusted_score = framework.get_barrier_adjusted_score()
        base_score = framework.calculate_score()

        # Should be lower due to barrier
        assert adjusted_score < base_score

    def test_enabler_increases_score(self):
        """Test that enablers increase score."""
        framework1 = AdoptionReadiness()
        framework2 = AdoptionReadiness()

        for criterion in framework1.weights.keys():
            framework1.set_score(criterion, 6.0)
            framework2.set_score(criterion, 6.0)

        # Add enabler to framework2
        framework2.add_enabler("Strong enabler", "high", "Leverage it")

        score1 = framework1.get_barrier_adjusted_score()
        score2 = framework2.get_barrier_adjusted_score()

        # Score with enabler should be higher
        assert score2 > score1

    def test_get_interpretation(self):
        """Test interpretation generation."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 9.0)

        interpretation = framework.get_interpretation()
        assert interpretation == "Highly Ready"

    def test_get_adoption_timeline(self):
        """Test timeline estimation."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.5)

        timeline = framework.get_adoption_timeline()
        assert "Immediate" in timeline or "Short-term" in timeline

    def test_get_detailed_breakdown(self):
        """Test detailed breakdown."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)
        framework.add_barrier("Test barrier", "medium")
        framework.add_enabler("Test enabler", "high")

        breakdown = framework.get_detailed_breakdown()
        assert "base_score" in breakdown
        assert "adjusted_score" in breakdown
        assert "timeline" in breakdown
        assert len(breakdown["barriers"]) == 1
        assert len(breakdown["enablers"]) == 1

    def test_get_recommendations(self):
        """Test recommendation generation."""
        framework = AdoptionReadiness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)
        framework.add_barrier("Critical barrier", "critical")
        framework.add_enabler("Strong enabler", "high")

        recommendations = framework.get_recommendations()
        assert len(recommendations) > 0
