"""Tests for Competitive Intensity Framework"""

import pytest
from src.research.frameworks.competitive_intensity import CompetitiveIntensity


class TestCompetitiveIntensity:
    """Test suite for CompetitiveIntensity class."""
    
    def test_initialization(self):
        """Test initialization."""
        framework = CompetitiveIntensity()
        assert framework.weights is not None
        assert framework.competitors == []
        assert abs(sum(framework.weights.values()) - 1.0) < 0.001
    
    def test_set_score(self):
        """Test setting scores."""
        framework = CompetitiveIntensity()
        framework.set_score('rivalry_intensity', 7.0)
        assert framework.scores['rivalry_intensity'] == 7.0
    
    def test_add_competitor(self):
        """Test adding competitors."""
        framework = CompetitiveIntensity()
        framework.add_competitor(
            'Competitor A',
            market_share=25.0,
            strengths=['Brand recognition', 'Distribution'],
            weaknesses=['High prices']
        )
        
        assert len(framework.competitors) == 1
        assert framework.competitors[0]['name'] == 'Competitor A'
        assert framework.competitors[0]['market_share'] == 25.0
    
    def test_calculate_score(self):
        """Test score calculation."""
        framework = CompetitiveIntensity()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 6.0)
        
        score = framework.calculate_score()
        assert score == 6.0
    
    def test_get_interpretation(self):
        """Test interpretation generation."""
        framework = CompetitiveIntensity()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.5)
        
        interpretation = framework.get_interpretation()
        assert interpretation == "Extremely Intense Competition"
    
    def test_get_market_concentration_no_data(self):
        """Test market concentration with no competitor data."""
        framework = CompetitiveIntensity()
        concentration = framework.get_market_concentration()
        
        assert concentration['herfindahl_index'] is None
        assert concentration['concentration'] == 'Unknown'
    
    def test_get_market_concentration_with_data(self):
        """Test market concentration calculation."""
        framework = CompetitiveIntensity()
        framework.add_competitor('A', market_share=40.0)
        framework.add_competitor('B', market_share=30.0)
        framework.add_competitor('C', market_share=20.0)
        framework.add_competitor('D', market_share=10.0)
        
        concentration = framework.get_market_concentration()
        
        # HHI = 40^2 + 30^2 + 20^2 + 10^2 = 3000
        assert concentration['herfindahl_index'] == 3000.0
        assert concentration['concentration'] == 'Highly Concentrated'
        assert concentration['top_3_share'] == 90.0
    
    def test_get_detailed_breakdown(self):
        """Test detailed breakdown."""
        framework = CompetitiveIntensity()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 6.0)
        framework.add_competitor('Competitor', market_share=50.0)
        
        breakdown = framework.get_detailed_breakdown()
        assert 'overall_score' in breakdown
        assert 'competitors' in breakdown
        assert 'market_concentration' in breakdown
    
    def test_get_recommendations(self):
        """Test recommendation generation."""
        framework = CompetitiveIntensity()
        for criterion in framework.weights.keys():
            framework.set_score(criterion, 8.0)
        
        recommendations = framework.get_recommendations()
        assert len(recommendations) > 0
        assert any('competition' in rec.lower() for rec in recommendations)
