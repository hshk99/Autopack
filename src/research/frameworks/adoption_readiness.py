"""Adoption Readiness Framework

This module evaluates the adoption readiness of a market or organization for a new product
or technology, considering customer readiness, infrastructure, and regulatory environment.
"""

from typing import Dict, Any, Optional, List


class AdoptionReadiness:
    """Evaluates market/organization readiness for product adoption.
    
    Attributes:
        weights: Dictionary of criterion weights (must sum to 1.0)
        scores: Dictionary of criterion scores (0-10 scale)
        barriers: List of identified adoption barriers
    """
    
    DEFAULT_WEIGHTS = {
        'customer_readiness': 0.30,
        'infrastructure': 0.25,
        'regulatory_environment': 0.20,
        'economic_conditions': 0.15,
        'cultural_fit': 0.10
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the Adoption Readiness framework.
        
        Args:
            weights: Custom weights for criteria (must sum to 1.0)
        
        Raises:
            ValueError: If weights don't sum to 1.0
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.scores: Dict[str, float] = {}
        self.barriers: List[Dict[str, Any]] = []
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
            score: Score value (0-10 scale)
        
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
    
    def add_barrier(self, name: str, impact: str, timeframe: str, 
                   mitigation: str) -> None:
        """Add an adoption barrier to the analysis.
        
        Args:
            name: Name/description of the barrier
            impact: Impact level (low, medium, high, critical)
            timeframe: Time to overcome (short, medium, long)
            mitigation: Proposed mitigation strategy
        """
        valid_impacts = ['low', 'medium', 'high', 'critical']
        valid_timeframes = ['short', 'medium', 'long']
        
        if impact.lower() not in valid_impacts:
            raise ValueError(f"Impact must be one of {valid_impacts}")
        if timeframe.lower() not in valid_timeframes:
            raise ValueError(f"Timeframe must be one of {valid_timeframes}")
        
        self.barriers.append({
            'name': name,
            'impact': impact.lower(),
            'timeframe': timeframe.lower(),
            'mitigation': mitigation
        })
    
    def calculate_score(self) -> float:
        """Calculate weighted adoption readiness score.
        
        Returns:
            Weighted score (0-10 scale)
        
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
    
    def get_barrier_adjusted_score(self) -> float:
        """Calculate barrier-adjusted readiness score.
        
        Returns:
            Barrier-adjusted score (0-10 scale)
        """
        base_score = self.calculate_score()
        
        # Calculate barrier penalty
        barrier_penalty = 0.0
        impact_weights = {
            'low': 0.1,
            'medium': 0.3,
            'high': 0.6,
            'critical': 1.0
        }
        
        for barrier in self.barriers:
            penalty = impact_weights[barrier['impact']]
            # Increase penalty for long-term barriers
            if barrier['timeframe'] == 'long':
                penalty *= 1.5
            barrier_penalty += penalty
        
        # Cap penalty at 50% of base score
        max_penalty = base_score * 0.5
        actual_penalty = min(barrier_penalty, max_penalty)
        
        return round(base_score - actual_penalty, 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the readiness score.
        
        Returns:
            Interpretation string
        """
        score = self.get_barrier_adjusted_score()
        if score >= 8.0:
            return "Highly Ready"
        elif score >= 6.0:
            return "Ready"
        elif score >= 4.0:
            return "Moderately Ready"
        else:
            return "Not Ready"
    
    def get_adoption_timeline(self) -> str:
        """Estimate adoption timeline based on barriers.
        
        Returns:
            Timeline estimate
        """
        if not self.barriers:
            return "Immediate (0-6 months)"
        
        long_term_barriers = sum(
            1 for b in self.barriers if b['timeframe'] == 'long'
        )
        medium_term_barriers = sum(
            1 for b in self.barriers if b['timeframe'] == 'medium'
        )
        
        if long_term_barriers > 0:
            return "Long-term (18+ months)"
        elif medium_term_barriers > 2:
            return "Medium-term (12-18 months)"
        elif medium_term_barriers > 0:
            return "Near-term (6-12 months)"
        else:
            return "Short-term (3-6 months)"
    
    def get_detailed_analysis(self) -> Dict[str, Any]:
        """Get detailed adoption readiness analysis.
        
        Returns:
            Dictionary with comprehensive readiness analysis
        """
        base_score = self.calculate_score()
        adjusted_score = self.get_barrier_adjusted_score()
        
        contributions = {
            criterion: round(self.weights[criterion] * self.scores[criterion], 2)
            for criterion in self.weights.keys()
        }
        
        return {
            'base_score': base_score,
            'barrier_adjusted_score': adjusted_score,
            'interpretation': self.get_interpretation(),
            'adoption_timeline': self.get_adoption_timeline(),
            'scores': self.scores.copy(),
            'weights': self.weights.copy(),
            'contributions': contributions,
            'barriers': self.barriers.copy(),
            'critical_barriers': self._get_critical_barriers(),
            'enablers': self._identify_enablers(),
            'readiness_gaps': self._get_readiness_gaps()
        }
    
    def _get_critical_barriers(self) -> List[Dict[str, Any]]:
        """Get high and critical impact barriers."""
        return [
            barrier for barrier in self.barriers
            if barrier['impact'] in ['high', 'critical']
        ]
    
    def _identify_enablers(self) -> List[str]:
        """Identify factors that enable adoption."""
        enablers = []
        
        if self.scores.get('customer_readiness', 0) >= 7.0:
            enablers.append("Strong customer readiness")
        
        if self.scores.get('infrastructure', 0) >= 7.0:
            enablers.append("Adequate infrastructure in place")
        
        if self.scores.get('regulatory_environment', 0) >= 7.0:
            enablers.append("Favorable regulatory environment")
        
        if self.scores.get('economic_conditions', 0) >= 7.0:
            enablers.append("Strong economic conditions")
        
        return enablers
    
    def _get_readiness_gaps(self) -> List[str]:
        """Identify readiness gaps (score < 5)."""
        return [
            criterion for criterion, score in self.scores.items()
            if score < 5.0
        ]
    
    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on readiness analysis.
        
        Returns:
            List of strategic recommendations
        """
        recommendations = []
        score = self.get_barrier_adjusted_score()
        gaps = self._get_readiness_gaps()
        critical_barriers = self._get_critical_barriers()
        timeline = self.get_adoption_timeline()
        
        if score >= 7.0:
            recommendations.append("Market is ready - proceed with launch")
        elif score >= 5.0:
            recommendations.append("Market is moderately ready - address key barriers")
        else:
            recommendations.append("Market not ready - significant preparation needed")
        
        recommendations.append(f"Expected adoption timeline: {timeline}")
        
        if critical_barriers:
            recommendations.append(
                f"Address {len(critical_barriers)} critical barrier(s) immediately"
            )
            for barrier in critical_barriers[:3]:  # Top 3
                recommendations.append(f"  - {barrier['name']}: {barrier['mitigation']}")
        
        if gaps:
            recommendations.append(f"Close readiness gaps in: {', '.join(gaps)}")
        
        if self.scores.get('customer_readiness', 0) < 6.0:
            recommendations.append("Invest in customer education and awareness programs")
        
        if self.scores.get('infrastructure', 0) < 6.0:
            recommendations.append("Develop infrastructure partnerships or solutions")
        
        if self.scores.get('regulatory_environment', 0) < 6.0:
            recommendations.append("Engage with regulators and industry associations")
        
        return recommendations
