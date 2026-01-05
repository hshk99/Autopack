"""Tests for Market Attractiveness Framework"""

import pytest
from autopack.research.frameworks.market_attractiveness import MarketAttractiveness


class TestMarketAttractiveness:
    """Test cases for MarketAttractiveness class."""

    def test_initialization_default_weights(self):
        """Test initialization with default weights."""
        framework = MarketAttractiveness()
        assert framework.weights is not None
        assert abs(sum(framework.weights.values()) - 1.0) < 0.01

    def test_initialization_custom_weights(self):
        """Test initialization with custom weights."""
        custom_weights = {
            "market_size": 0.4,
            "growth_rate": 0.3,
            "profitability": 0.2,
            "accessibility": 0.05,
            "stability": 0.05,
        }
        framework = MarketAttractiveness(weights=custom_weights)
        assert framework.weights == custom_weights

    def test_invalid_weights_sum(self):
        """Test that invalid weight sums raise error."""
        invalid_weights = {
            "market_size": 0.5,
            "growth_rate": 0.3,
            "profitability": 0.1,
            "accessibility": 0.05,
            "stability": 0.05,
        }
        with pytest.raises(ValueError, match="must sum to 1.0"):
            MarketAttractiveness(weights=invalid_weights)

    def test_set_score_valid(self):
        """Test setting valid scores."""
        framework = MarketAttractiveness()
        framework.set_score("market_size", 8.5)
        assert framework.scores["market_size"] == 8.5

    def test_set_score_invalid_criterion(self):
        """Test setting score for invalid criterion."""
        framework = MarketAttractiveness()
        with pytest.raises(ValueError, match="Unknown criterion"):
            framework.set_score("invalid_criterion", 5.0)

    def test_set_score_out_of_range(self):
        """Test setting score outside valid range."""
        framework = MarketAttractiveness()
        with pytest.raises(ValueError, match="must be between 0 and 10"):
            framework.set_score("market_size", 11.0)
        with pytest.raises(ValueError, match="must be between 0 and 10"):
            framework.set_score("market_size", -1.0)

    def test_set_scores_multiple(self):
        """Test setting multiple scores at once."""
        framework = MarketAttractiveness()
        scores = {"market_size": 8.0, "growth_rate": 7.5, "profitability": 6.0}
        framework.set_scores(scores)
        assert framework.scores["market_size"] == 8.0
        assert framework.scores["growth_rate"] == 7.5
        assert framework.scores["profitability"] == 6.0

    def test_calculate_score_complete(self):
        """Test score calculation with all criteria."""
        framework = MarketAttractiveness()
        framework.set_scores(
            {
                "market_size": 8.0,
                "growth_rate": 7.0,
                "profitability": 6.0,
                "accessibility": 5.0,
                "stability": 7.0,
            }
        )
        score = framework.calculate_score()
        assert 0 <= score <= 10
        assert isinstance(score, float)

    def test_calculate_score_missing_criteria(self):
        """Test that missing criteria raises error."""
        framework = MarketAttractiveness()
        framework.set_score("market_size", 8.0)
        with pytest.raises(ValueError, match="Missing scores"):
            framework.calculate_score()

    def test_get_interpretation(self):
        """Test interpretation generation."""
        framework = MarketAttractiveness()
        framework.set_scores(
            {
                "market_size": 9.0,
                "growth_rate": 8.5,
                "profitability": 8.0,
                "accessibility": 7.5,
                "stability": 8.0,
            }
        )
        interpretation = framework.get_interpretation()
        assert interpretation == "Highly Attractive"

    def test_get_detailed_analysis(self):
        """Test detailed analysis generation."""
        framework = MarketAttractiveness()
        framework.set_scores(
            {
                "market_size": 8.0,
                "growth_rate": 7.0,
                "profitability": 6.0,
                "accessibility": 5.0,
                "stability": 7.0,
            }
        )
        analysis = framework.get_detailed_analysis()

        assert "total_score" in analysis
        assert "interpretation" in analysis
        assert "scores" in analysis
        assert "weights" in analysis
        assert "contributions" in analysis
        assert "top_factors" in analysis
        assert "weak_factors" in analysis

    def test_get_recommendations(self):
        """Test recommendations generation."""
        framework = MarketAttractiveness()
        framework.set_scores(
            {
                "market_size": 8.0,
                "growth_rate": 9.0,
                "profitability": 7.0,
                "accessibility": 4.0,
                "stability": 6.0,
            }
        )
        recommendations = framework.get_recommendations()

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        assert any("growth" in rec.lower() for rec in recommendations)
        assert any("access" in rec.lower() for rec in recommendations)
