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
        'rivalry_intensity': 0.25,
        'threat_of_new_entrants': 0.20,
        'bargaining_power_suppliers': 0.15,
        'bargaining_power_buyers': 0.20,
        'threat_of_substitutes': 0.20
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
        self.metadata: Dict[str, Any] = {}
        
        if abs(sum(self.weights.values()) - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {sum(self.weights.values())}")
    
    def set_score(self, criterion: str, score: float, evidence: Optional[str] = None) -> None:
        """Set score for a specific criterion.
        
        Args:
            criterion: Name of the criterion
            score: Score value (0-10, higher = more intense competition)
            evidence: Supporting evidence for the score
            
        Raises:
            ValueError: If criterion not in weights or score out of range
        """
        if criterion not in self.weights:
            raise ValueError(f"Unknown criterion: {criterion}")
        if not 0 <= score <= 10:
            raise ValueError(f"Score must be between 0 and 10, got {score}")
        
        self.scores[criterion] = score
        if evidence:
            if 'evidence' not in self.metadata:
                self.metadata['evidence'] = {}
            self.metadata['evidence'][criterion] = evidence
    
    def add_competitor(self, name: str, market_share: Optional[float] = None, 
                      strengths: Optional[List[str]] = None,
                      weaknesses: Optional[List[str]] = None) -> None:
        """Add a competitor to the analysis.
        
        Args:
            name: Competitor name
            market_share: Estimated market share (0-100)
            strengths: List of competitor strengths
            weaknesses: List of competitor weaknesses
        """
        competitor = {
            'name': name,
            'market_share': market_share,
            'strengths': strengths or [],
            'weaknesses': weaknesses or []
        }
        self.competitors.append(competitor)
    
    def calculate_score(self) -> float:
        """Calculate weighted overall competitive intensity score.
        
        Returns:
            Weighted score (0-10 scale, higher = more intense)
            
        Raises:
            ValueError: If not all criteria have been scored
        """
        missing = set(self.weights.keys()) - set(self.scores.keys())
        if missing:
            raise ValueError(f"Missing scores for criteria: {missing}")
        
        total = sum(self.scores[criterion] * self.weights[criterion] 
                   for criterion in self.weights.keys())
        return round(total, 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the overall score.
        
        Returns:
            Interpretation string
        """
        score = self.calculate_score()
        
        if score >= 8.0:
            return "Extremely Intense Competition"
        elif score >= 6.0:
            return "High Competition"
        elif score >= 4.0:
            return "Moderate Competition"
        elif score >= 2.0:
            return "Low Competition"
        else:
            return "Minimal Competition"
    
    def get_market_concentration(self) -> Dict[str, Any]:
        """Calculate market concentration metrics.
        
        Returns:
            Dictionary with concentration analysis
        """
        if not self.competitors:
            return {'herfindahl_index': None, 'top_3_share': None, 'concentration': 'Unknown'}
        
        # Calculate Herfindahl-Hirschman Index (HHI)
        competitors_with_share = [c for c in self.competitors if c.get('market_share')]
        
        if not competitors_with_share:
            return {'herfindahl_index': None, 'top_3_share': None, 'concentration': 'Unknown'}
        
        shares = [c['market_share'] for c in competitors_with_share]
        hhi = sum(s ** 2 for s in shares)
        
        # Top 3 concentration
        top_3_share = sum(sorted(shares, reverse=True)[:3])
        
        # Interpret concentration
        if hhi > 2500:
            concentration = "Highly Concentrated"
        elif hhi > 1500:
            concentration = "Moderately Concentrated"
        else:
            concentration = "Unconcentrated"
        
        return {
            'herfindahl_index': round(hhi, 2),
            'top_3_share': round(top_3_share, 2),
            'concentration': concentration,
            'num_competitors': len(competitors_with_share)
        }
    
    def get_detailed_breakdown(self) -> Dict[str, Any]:
        """Get detailed breakdown of competitive analysis.
        
        Returns:
            Dictionary with detailed analysis
        """
        total_score = self.calculate_score()
        
        breakdown = {
            'overall_score': total_score,
            'interpretation': self.get_interpretation(),
            'criteria': [],
            'competitors': self.competitors,
            'market_concentration': self.get_market_concentration()
        }
        
        for criterion, weight in sorted(self.weights.items(), 
                                       key=lambda x: x[1], reverse=True):
            score = self.scores[criterion]
            contribution = score * weight
            
            criterion_data = {
                'name': criterion,
                'score': score,
                'weight': weight,
                'contribution': round(contribution, 2),
                'evidence': self.metadata.get('evidence', {}).get(criterion)
            }
            breakdown['criteria'].append(criterion_data)
        
        return breakdown
    
    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on competitive analysis.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        overall = self.calculate_score()
        
        if overall >= 7.0:
            recommendations.append("High competition - differentiation strategy critical")
            recommendations.append("Consider niche markets or blue ocean opportunities")
        elif overall < 4.0:
            recommendations.append("Low competition - opportunity for market leadership")
        
        # Analyze specific forces
        if self.scores.get('threat_of_new_entrants', 0) < 4.0:
            recommendations.append("Low barriers to entry - establish strong market position quickly")
        
        if self.scores.get('bargaining_power_buyers', 0) >= 7.0:
            recommendations.append("High buyer power - focus on value proposition and customer lock-in")
        
        if self.scores.get('threat_of_substitutes', 0) >= 7.0:
            recommendations.append("High substitution threat - emphasize unique value and switching costs")
        
        # Market concentration insights
        concentration = self.get_market_concentration()
        if concentration.get('concentration') == 'Highly Concentrated':
            recommendations.append("Concentrated market - consider partnership or acquisition strategies")
        
        return recommendations
