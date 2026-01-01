"""Tests for Product Feasibility Framework"""

import pytest
from autopack.research.frameworks.product_feasibility import ProductFeasibility


class TestProductFeasibility:
    """Test cases for ProductFeasibility class."""
    
    def test_initialization(self):
        """Test initialization."""
        framework = ProductFeasibility()
        assert framework.weights is not None
        assert framework.scores == {}
        assert framework.risk_factors == []
    
    def test_add_risk_factor(self):
        """Test adding risk factors."""
        framework = ProductFeasibility()
        framework.add_risk_factor(
            name="Technical complexity",
            severity="high",
            mitigation="Hire specialized expertise"
        )
        assert len(framework.risk_factors) == 1
        assert framework.risk_factors[0]['severity'] == 'high'
    
    def test_add_risk_factor_invalid_severity(self):
        """Test adding risk with invalid severity."""
        framework = ProductFeasibility()
        with pytest.raises(ValueError, match="Severity must be one of"):
            framework.add_risk_factor(
                name="Test risk",
                severity="invalid",
                mitigation="Test"
            )
    
    def test_calculate_score(self):
        """Test base score calculation."""
        framework = ProductFeasibility()
        framework.set_scores({
            'technical_feasibility': 8.0,
            'resource_availability': 7.0,
            'cost_viability': 6.0,
            'time_to_market': 7.0,
            'scalability': 8.0
        })
        score = framework.calculate_score()
        assert 0 <= score <= 10
    
    def test_get_risk_adjusted_score(self):
        """Test risk-adjusted score calculation."""
        framework = ProductFeasibility()
        framework.set_scores({
            'technical_feasibility': 8.0,
            'resource_availability': 7.0,
            'cost_viability': 6.0,
            'time_to_market': 7.0,
            'scalability': 8.0
        })
        framework.add_risk_factor(
            name="High complexity",
            severity="high",
            mitigation="Phased approach"
        )
        
        base_score = framework.calculate_score()
        adjusted_score = framework.get_risk_adjusted_score()
        
        assert adjusted_score < base_score
        assert adjusted_score >= 0
    
    def test_get_detailed_analysis(self):
        """Test detailed analysis."""
        framework = ProductFeasibility()
        framework.set_scores({
            'technical_feasibility': 8.0,
            'resource_availability': 7.0,
            'cost_viability': 6.0,
            'time_to_market': 7.0,
            'scalability': 8.0
        })
        framework.add_risk_factor(
            name="Test risk",
            severity="medium",
            mitigation="Test mitigation"
        )
        
        analysis = framework.get_detailed_analysis()
        
        assert 'base_score' in analysis
        assert 'risk_adjusted_score' in analysis
        assert 'interpretation' in analysis
        assert 'risk_factors' in analysis
        assert 'critical_risks' in analysis
        assert 'weak_areas' in analysis
    
    def test_get_recommendations(self):
        """Test recommendations generation."""
        framework = ProductFeasibility()
        framework.set_scores({
            'technical_feasibility': 5.0,
            'resource_availability': 7.0,
            'cost_viability': 6.0,
            'time_to_market': 4.0,
            'scalability': 8.0
        })
        
        recommendations = framework.get_recommendations()
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
