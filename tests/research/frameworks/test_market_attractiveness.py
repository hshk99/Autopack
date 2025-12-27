"""Tests for Market Attractiveness Framework"""

import pytest
from src.research.frameworks.market_attractiveness import MarketAttractiveness


class TestMarketAttractiveness:
    """Test suite for MarketAttractiveness class."""
    
    def test_initialization_default_weights(self):
        """Test initialization with default weights."""
        framework = MarketAttractiveness()
        assert framework.weights is not None
        assert abs(sum(framework.weights.values()) - 1.0) < 0.001
    
    def test_initialization_custom_weights(self):
        """Test initialization with custom weights."""
        custom_weights = {
            'market_size': 0.4,
            'growth_rate': 0.3,
            'profit_margins': 0.2,
            'market_accessibility': 0.05,
            'customer_willingness': 0.05
        }
        framework = MarketAttractiveness(weights=custom_weights)
        assert framework.weights == custom_weights
    
    def test_initialization_invalid_weights(self):
        """Test that invalid weights raise ValueError."""
        invalid_weights = {
            'market_size': 0.5,
            'growth_rate': 0.3,
            'profit_margins': 0.1,
            'market_accessibility': 0.05,
            'customer_willingness': 0.05
        }
        with pytest.raises(ValueError, match="must sum to 1.0"):
            MarketAttractiveness(weights=invalid_weights)
    
    def test_set_score_valid(self):
        """Test setting valid scores."""
        framework = MarketAttractiveness()
        framework.set_score('market_size', 8.5, 'Large addressable market')
        assert framework.scores['market_size'] == 8.5
        assert framework.metadata['evidence']['market_size'] == 'Large addressable market'
    
    def test_set_score_invalid_criterion(self):
        """Test that invalid criterion raises ValueError."""
        framework = MarketAttractiveness()
        with pytest.raises(ValueError, match="Unknown criterion"):
            framework.set_score('invalid_criterion', 5.0)
    
    def test_set_score_out_of_range(self):
        """Test that out-of-range score raises ValueError."""
        framework = MarketAttractiveness()
        with pytest.raises(ValueError, match="must be between 0 and 10"):
            framework.set_score('market_size', 11.0)
    
    def test_calculate_score(self):
        """Test score calculation."""
        framework = MarketAttractiveness()
        framework.set_score('market_size', 8.0)
        framework.set_score('growth_rate', 7.0)
        framework.set_score('profit_margins', 6.0)
        framework.set_score('market_accessibility', 5.0)
        framework.set_score('customer_willingness', 9.0)
        
        score = framework.calculate_score()
        # Expected: 8*0.3 + 7*0.25 + 6*0.2 + 5*0.15 + 9*0.1 = 7.05
        assert abs(score - 7.05) < 0.01
    
    def test_calculate_score_missing_criteria(self):
        """Test that missing criteria raises ValueError."""
        framework = MarketAttractiveness()
        framework.set_score('market_size', 8.0)
        with pytest.raises(ValueError, match="Missing scores"):
            framework.calculate_score()
    
    def test_get_interpretation(self):
        """Test interpretation generation."""
        framework = MarketAttractiveness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.5)
        
        interpretation = framework.get_interpretation()
        assert interpretation == "Highly Attractive"
    
    def test_get_detailed_breakdown(self):
        """Test detailed breakdown generation."""
        framework = MarketAttractiveness()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)
        
        breakdown = framework.get_detailed_breakdown()
        assert 'overall_score' in breakdown
        assert 'interpretation' in breakdown
        assert 'criteria' in breakdown
        assert len(breakdown['criteria']) == len(framework.weights)
    
    def test_get_recommendations(self):
        """Test recommendation generation."""
        framework = MarketAttractiveness()
        framework.set_score('market_size', 8.0)
        framework.set_score('growth_rate', 7.0)
        framework.set_score('profit_margins', 3.0)  # Weak area
        framework.set_score('market_accessibility', 4.0)  # Weak area
        framework.set_score('customer_willingness', 9.0)
        
        recommendations = framework.get_recommendations()
        assert len(recommendations) > 0
        assert any('weakness' in rec.lower() for rec in recommendations)
