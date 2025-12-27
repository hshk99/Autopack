"""Competitive Intensity Framework

This module evaluates the level of competition within a market using Porter's Five Forces
inspired methodology.
"""

from typing import Dict, Any, Optional, List


class CompetitiveIntensity:
    """Examines competitive dynamics within a market.
    
    Attributes:
        weights: Dictionary of criterion weights (must sum to 1.0)
        scores: Dictionary of criterion scores (0-10 scale, higher = more intense)
        competitors: List of identified key competitors
    """
    
    DEFAULT_WEIGHTS = {
        'rivalry': 0.25,
        'threat_of_new_entrants': 0.20,
        'threat_of_substitutes': 0.20,
        'buyer_power': 0.20,
        'supplier_power': 0.15
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the Competitive Intensity framework.
        
        Args:
            weights: Custom weights for criteria (must sum to 1.0)
        
        Raises:
            ValueError: If weights don't sum to 1.0
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.scores: Dict[str, float] = {}
        self.competitors: List[Dict[str, Any]] = []
        self._validate_weights()
    
    def _validate_weights(self) -> None:
        """Validate that weights sum to 1.0."""
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Weights must sum to 1.0, got {total}")
    
    def set_score(self, criterion: str, score: float) -> None:
        """Set score for a specific criterion.
        
        Args:
            criterion: Name of the criterion
            score: Score value (0-10 scale, higher = more intense competition)
        
        Raises:
            ValueError: If criterion not in weights or score out of range
        """
        if criterion not in self.weights:
            raise ValueError(f"Unknown criterion: {criterion}")
        if not (0 <= score <= 10):
            raise ValueError(f"Score must be between 0 and 10, got {score}")
        self.scores[criterion] = score
    
    def set_scores(self, scores: Dict[str, float]) -> None:
        """Set multiple scores at once.
        
        Args:
            scores: Dictionary of criterion scores
        """
        for criterion, score in scores.items():
            self.set_score(criterion, score)
    
    def add_competitor(self, name: str, market_share: float, 
                      strengths: List[str], weaknesses: List[str]) -> None:
        """Add a competitor to the analysis.
        
        Args:
            name: Competitor name
            market_share: Market share percentage (0-100)
            strengths: List of competitor strengths
            weaknesses: List of competitor weaknesses
        """
        if not (0 <= market_share <= 100):
            raise ValueError("Market share must be between 0 and 100")
        
        self.competitors.append({
            'name': name,
            'market_share': market_share,
            'strengths': strengths.copy(),
            'weaknesses': weaknesses.copy()
        })
    
    def calculate_score(self) -> float:
        """Calculate weighted competitive intensity score.
        
        Returns:
            Weighted score (0-10 scale, higher = more intense)
        
        Raises:
            ValueError: If not all criteria have scores
        """
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")
        
        total_score = sum(
            self.weights[criterion] * self.scores[criterion]
            for criterion in self.weights.keys()
        )
        return round(total_score, 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the competitive intensity score.
        
        Returns:
            Interpretation string
        """
        score = self.calculate_score()
        if score >= 8.0:
            return "Extremely Intense"
        elif score >= 6.0:
            return "Highly Competitive"
        elif score >= 4.0:
            return "Moderately Competitive"
        else:
            return "Low Competition"
    
    def get_market_concentration(self) -> Dict[str, Any]:
        """Calculate market concentration metrics.
        
        Returns:
            Dictionary with concentration analysis
        """
        if not self.competitors:
            return {
                'herfindahl_index': 0.0,
                'top_3_share': 0.0,
                'concentration_level': 'Unknown'
            }
        
        # Calculate Herfindahl-Hirschman Index (HHI)
        hhi = sum(comp['market_share'] ** 2 for comp in self.competitors)
        
        # Calculate top 3 market share
        sorted_competitors = sorted(
            self.competitors,
            key=lambda x: x['market_share'],
            reverse=True
        )
        top_3_share = sum(comp['market_share'] for comp in sorted_competitors[:3])
        
        # Determine concentration level
        if hhi < 1500:
            concentration = 'Fragmented'
        elif hhi < 2500:
            concentration = 'Moderate Concentration'
        else:
            concentration = 'High Concentration'
        
        return {
            'herfindahl_index': round(hhi, 2),
            'top_3_share': round(top_3_share, 2),
            'concentration_level': concentration,
            'number_of_competitors': len(self.competitors)
        }
    
    def get_detailed_analysis(self) -> Dict[str, Any]:
        """Get detailed competitive analysis.
        
        Returns:
            Dictionary with comprehensive competitive analysis
        """
        contributions = {
            criterion: round(self.weights[criterion] * self.scores[criterion], 2)
            for criterion in self.weights.keys()
        }
        
        total_score = self.calculate_score()
        
        return {
            'total_score': total_score,
            'interpretation': self.get_interpretation(),
            'scores': self.scores.copy(),
            'weights': self.weights.copy(),
            'contributions': contributions,
            'market_concentration': self.get_market_concentration(),
            'competitors': self.competitors.copy(),
            'key_competitive_forces': self._get_key_forces(contributions),
            'competitive_advantages': self._identify_opportunities()
        }
    
    def _get_key_forces(self, contributions: Dict[str, float]) -> List[str]:
        """Identify the most significant competitive forces."""
        sorted_forces = sorted(
            contributions.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [force for force, _ in sorted_forces[:3]]
    
    def _identify_opportunities(self) -> List[str]:
        """Identify potential competitive opportunities."""
        opportunities = []
        
        if self.scores.get('threat_of_new_entrants', 10) < 5.0:
            opportunities.append("Low barriers to entry - market accessible")
        
        if self.scores.get('buyer_power', 10) < 5.0:
            opportunities.append("Weak buyer power - pricing flexibility")
        
        if self.scores.get('threat_of_substitutes', 10) < 5.0:
            opportunities.append("Few substitutes - strong market position")
        
        concentration = self.get_market_concentration()
        if concentration['concentration_level'] == 'Fragmented':
            opportunities.append("Fragmented market - consolidation opportunity")
        
        return opportunities
    
    def get_recommendations(self) -> List[str]:
        """Generate strategic recommendations based on competitive analysis.
        
        Returns:
            List of strategic recommendations
        """
        recommendations = []
        score = self.calculate_score()
        opportunities = self._identify_opportunities()
        
        if score >= 7.0:
            recommendations.append("High competition - differentiation strategy critical")
            recommendations.append("Consider niche markets or blue ocean opportunities")
        elif score >= 5.0:
            recommendations.append("Moderate competition - focus on competitive advantages")
        else:
            recommendations.append("Low competition - opportunity for market leadership")
        
        if opportunities:
            recommendations.append("Leverage identified opportunities:")
            recommendations.extend(opportunities)
        
        if self.scores.get('rivalry', 0) >= 7.0:
            recommendations.append("Intense rivalry - build strong brand and customer loyalty")
        
        concentration = self.get_market_concentration()
        if concentration['concentration_level'] == 'High Concentration':
            recommendations.append("Concentrated market - partnership or acquisition strategy")
        
        return recommendations
