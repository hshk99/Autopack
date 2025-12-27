"""Tests for Competitive Intensity Framework"""

import pytest
from src.research.frameworks.competitive_intensity import CompetitiveIntensity


class TestCompetitiveIntensity:
    """Test cases for CompetitiveIntensity class."""
    
    def test_initialization(self):
        """Test initialization."""
        framework = CompetitiveIntensity()
        assert framework.weights is not None
        assert framework.scores == {}
        assert framework.competitors == []
    
    def test_add_competitor(self):
        """Test adding competitors."""
        framework = CompetitiveIntensity()
        framework.add_competitor(
            name="Competitor A",
            market_share=25.0,
            strengths=["Brand", "Distribution"],
            weaknesses=["Price", "Innovation"]
        )
        assert len(framework.competitors) == 1
        assert framework.competitors[0]['market_share'] == 25.0
    
    def test_add_competitor_invalid_share(self):
        """Test adding competitor with invalid market share."""
        framework = CompetitiveIntensity()
        with pytest.raises(ValueError, match="Market share must be"):
            framework.add_competitor(
                name="Test",
                market_share=150.0,
                strengths=[],
                weaknesses=[]
            )
    
    def test_calculate_score(self):
        """Test score calculation."""
        framework = CompetitiveIntensity()
        framework.set_scores({
            'rivalry': 7.0,
            'threat_of_new_entrants': 5.0,
            'threat_of_substitutes': 6.0,
            'buyer_power': 5.0,
            'supplier_power': 4.0
        })
        score = framework.calculate_score()
        assert 0 <= score <= 10
    
    def test_get_market_concentration(self):
        """Test market concentration calculation."""
        framework = CompetitiveIntensity()
        framework.add_competitor("A", 40.0, [], [])
        framework.add_competitor("B", 30.0, [], [])
        framework.add_competitor("C", 20.0, [], [])
        framework.add_competitor("D", 10.0, [], [])
        
        concentration = framework.get_market_concentration()
        
        assert 'herfindahl_index' in concentration
        assert 'top_3_share' in concentration
        assert 'concentration_level' in concentration
        assert concentration['top_3_share'] == 90.0
    
    def test_get_detailed_analysis(self):
        """Test detailed analysis."""
        framework = CompetitiveIntensity()
        framework.set_scores({
            'rivalry': 7.0,
            'threat_of_new_entrants': 5.0,
            'threat_of_substitutes': 6.0,
            'buyer_power': 5.0,
            'supplier_power': 4.0
        })
        framework.add_competitor("A", 30.0, ["Brand"], ["Price"])
        
        analysis = framework.get_detailed_analysis()
        
        assert 'total_score' in analysis
        assert 'interpretation' in analysis
        assert 'market_concentration' in analysis
        assert 'competitors' in analysis
        assert 'key_competitive_forces' in analysis
    
    def test_get_recommendations(self):
        """Test recommendations generation."""
        framework = CompetitiveIntensity()
        framework.set_scores({
            'rivalry': 8.0,
            'threat_of_new_entrants': 6.0,
            'threat_of_substitutes': 7.0,
            'buyer_power': 6.0,
            'supplier_power': 5.0
        })
        
        recommendations = framework.get_recommendations()
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
