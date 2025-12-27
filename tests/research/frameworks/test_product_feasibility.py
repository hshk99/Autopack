"""Tests for Product Feasibility Framework"""

import pytest
from src.research.frameworks.product_feasibility import ProductFeasibility


class TestProductFeasibility:
    """Test suite for ProductFeasibility class."""
    
    def test_initialization(self):
        """Test initialization."""
        framework = ProductFeasibility()
        assert framework.weights is not None
        assert framework.risk_factors == []
        assert abs(sum(framework.weights.values()) - 1.0) < 0.001
    
    def test_set_score(self):
        """Test setting scores."""
        framework = ProductFeasibility()
        framework.set_score('technical_feasibility', 7.5)
        assert framework.scores['technical_feasibility'] == 7.5
    
    def test_add_risk_factor(self):
        """Test adding risk factors."""
        framework = ProductFeasibility()
        framework.add_risk_factor('Technical complexity', 'high', 'Hire specialists')
        
        assert len(framework.risk_factors) == 1
        assert framework.risk_factors[0]['name'] == 'Technical complexity'
        assert framework.risk_factors[0]['severity'] == 'high'
        assert framework.risk_factors[0]['mitigation'] == 'Hire specialists'
    
    def test_add_risk_factor_invalid_severity(self):
        """Test that invalid severity raises ValueError."""
        framework = ProductFeasibility()
        with pytest.raises(ValueError, match="Severity must be one of"):
            framework.add_risk_factor('Risk', 'invalid')
    
    def test_calculate_score(self):
        """Test base score calculation."""
        framework = ProductFeasibility()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.0)
        
        score = framework.calculate_score()
        assert score == 8.0
    
    def test_get_risk_adjusted_score(self):
        """Test risk-adjusted score calculation."""
        framework = ProductFeasibility()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.0)
        
        # Add a high-severity risk
        framework.add_risk_factor('Major risk', 'high')
        
        adjusted_score = framework.get_risk_adjusted_score()
        base_score = framework.calculate_score()
        
        # Adjusted score should be lower due to risk
        assert adjusted_score < base_score
    
    def test_risk_mitigation_reduces_penalty(self):
        """Test that mitigation reduces risk penalty."""
        framework1 = ProductFeasibility()
        framework2 = ProductFeasibility()
        
        for criterion in framework1.weights.keys():
            framework1.set_score(criterion, 8.0)
            framework2.set_score(criterion, 8.0)
        
        # Same risk, but one has mitigation
        framework1.add_risk_factor('Risk', 'high')
        framework2.add_risk_factor('Risk', 'high', 'Mitigation plan')
        
        score1 = framework1.get_risk_adjusted_score()
        score2 = framework2.get_risk_adjusted_score()
        
        # Score with mitigation should be higher
        assert score2 > score1
    
    def test_get_interpretation(self):
        """Test interpretation generation."""
        framework = ProductFeasibility()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 9.0)
        
        interpretation = framework.get_interpretation()
        assert interpretation == "Highly Feasible"
    
    def test_get_detailed_breakdown(self):
        """Test detailed breakdown."""
        framework = ProductFeasibility()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)
        framework.add_risk_factor('Test risk', 'medium')
        
        breakdown = framework.get_detailed_breakdown()
        assert 'base_score' in breakdown
        assert 'risk_adjusted_score' in breakdown
        assert 'risks' in breakdown
        assert len(breakdown['risks']) == 1
    
    def test_get_recommendations(self):
        """Test recommendation generation."""
        framework = ProductFeasibility()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 7.0)
        framework.add_risk_factor('Critical issue', 'critical')
        
        recommendations = framework.get_recommendations()
        assert len(recommendations) > 0
        assert any('critical' in rec.lower() for rec in recommendations)
