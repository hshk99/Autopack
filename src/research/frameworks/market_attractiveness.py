"""Market Attractiveness Framework

This module evaluates the potential of a market based on various factors including
market size, growth rate, and competitive landscape.
"""

from typing import Dict, Any, Optional, List


class MarketAttractiveness:
    """Evaluates market potential using weighted scoring methodology.
    
    Attributes:
        weights: Dictionary of criterion weights (must sum to 1.0)
        scores: Dictionary of criterion scores (0-10 scale)
    """
    
    DEFAULT_WEIGHTS = {
        'market_size': 0.30,
        'growth_rate': 0.25,
        'profit_margins': 0.20,
        'market_accessibility': 0.15,
        'customer_willingness': 0.10
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the Market Attractiveness framework.
        
        Args:
            weights: Custom weights for criteria (must sum to 1.0)
            
        Raises:
            ValueError: If weights don't sum to 1.0
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.scores: Dict[str, float] = {}
        self.metadata: Dict[str, Any] = {}
        
        if abs(sum(self.weights.values()) - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {sum(self.weights.values())}")
    
    def set_score(self, criterion: str, score: float, evidence: Optional[str] = None) -> None:
        """Set score for a specific criterion.
        
        Args:
            criterion: Name of the criterion
            score: Score value (0-10)
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
    
    def calculate_score(self) -> float:
        """Calculate weighted overall market attractiveness score.
        
        Returns:
            Weighted score (0-10 scale)
            
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
            return "Highly Attractive"
        elif score >= 6.0:
            return "Attractive"
        elif score >= 4.0:
            return "Moderately Attractive"
        elif score >= 2.0:
            return "Low Attractiveness"
        else:
            return "Unattractive"
    
    def get_detailed_breakdown(self) -> Dict[str, Any]:
        """Get detailed breakdown of scores and contributions.
        
        Returns:
            Dictionary with detailed analysis
        """
        total_score = self.calculate_score()
        
        breakdown = {
            'overall_score': total_score,
            'interpretation': self.get_interpretation(),
            'criteria': []
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
        """Generate recommendations based on scores.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Identify weak areas (score < 5)
        weak_areas = [(k, v) for k, v in self.scores.items() if v < 5.0]
        weak_areas.sort(key=lambda x: self.weights[x[0]], reverse=True)
        
        if weak_areas:
            recommendations.append(
                f"Address weaknesses in: {', '.join(k for k, _ in weak_areas[:3])}"
            )
        
        # Identify strengths (score >= 7)
        strengths = [(k, v) for k, v in self.scores.items() if v >= 7.0]
        if strengths:
            recommendations.append(
                f"Leverage strengths in: {', '.join(k for k, _ in strengths)}"
            )
        
        overall = self.calculate_score()
        if overall >= 7.0:
            recommendations.append("Market shows strong potential - consider aggressive entry strategy")
        elif overall < 4.0:
            recommendations.append("Market shows limited potential - reconsider entry or pivot strategy")
        
        return recommendations
