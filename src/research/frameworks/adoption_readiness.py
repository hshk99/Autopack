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
        'infrastructure_readiness': 0.25,
        'regulatory_environment': 0.20,
        'economic_conditions': 0.15,
        'cultural_acceptance': 0.10
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
        self.enablers: List[Dict[str, Any]] = []
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
    
    def add_barrier(self, name: str, impact: str, mitigation: Optional[str] = None) -> None:
        """Add an adoption barrier to the analysis.
        
        Args:
            name: Name/description of the barrier
            impact: Impact level (low, medium, high, critical)
            mitigation: Proposed mitigation strategy
            
        Raises:
            ValueError: If impact is invalid
        """
        valid_impacts = ['low', 'medium', 'high', 'critical']
        if impact.lower() not in valid_impacts:
            raise ValueError(f"Impact must be one of {valid_impacts}")
        
        barrier = {
            'name': name,
            'impact': impact.lower(),
            'mitigation': mitigation
        }
        self.barriers.append(barrier)
    
    def add_enabler(self, name: str, strength: str, leverage: Optional[str] = None) -> None:
        """Add an adoption enabler to the analysis.
        
        Args:
            name: Name/description of the enabler
            strength: Strength level (low, medium, high)
            leverage: How to leverage this enabler
        """
        valid_strengths = ['low', 'medium', 'high']
        if strength.lower() not in valid_strengths:
            raise ValueError(f"Strength must be one of {valid_strengths}")
        
        enabler = {
            'name': name,
            'strength': strength.lower(),
            'leverage': leverage
        }
        self.enablers.append(enabler)
    
    def calculate_score(self) -> float:
        """Calculate weighted overall adoption readiness score.
        
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
    
    def get_barrier_adjusted_score(self) -> float:
        """Calculate barrier-adjusted readiness score.
        
        Returns:
            Barrier-adjusted score (0-10 scale)
        """
        base_score = self.calculate_score()
        
        # Calculate barrier penalty
        barrier_penalty = 0.0
        impact_weights = {'low': 0.1, 'medium': 0.3, 'high': 0.6, 'critical': 1.0}
        
        for barrier in self.barriers:
            penalty = impact_weights[barrier['impact']]
            # Reduce penalty if mitigation exists
            if barrier.get('mitigation'):
                penalty *= 0.6
            barrier_penalty += penalty
        
        # Calculate enabler bonus
        enabler_bonus = 0.0
        strength_weights = {'low': 0.1, 'medium': 0.2, 'high': 0.4}
        
        for enabler in self.enablers:
            bonus = strength_weights[enabler['strength']]
            if enabler.get('leverage'):
                bonus *= 1.2
            enabler_bonus += bonus
        
        # Cap adjustments
        max_penalty = base_score * 0.4
        max_bonus = (10 - base_score) * 0.3
        
        barrier_penalty = min(barrier_penalty, max_penalty)
        enabler_bonus = min(enabler_bonus, max_bonus)
        
        adjusted_score = base_score - barrier_penalty + enabler_bonus
        return round(max(0, min(10, adjusted_score)), 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the overall score.
        
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
        elif score >= 2.0:
            return "Low Readiness"
        else:
            return "Not Ready"
    
    def get_adoption_timeline(self) -> str:
        """Estimate adoption timeline based on readiness.
        
        Returns:
            Timeline estimate string
        """
        score = self.get_barrier_adjusted_score()
        
        if score >= 8.0:
            return "Immediate (0-6 months)"
        elif score >= 6.0:
            return "Short-term (6-12 months)"
        elif score >= 4.0:
            return "Medium-term (1-2 years)"
        elif score >= 2.0:
            return "Long-term (2-5 years)"
        else:
            return "Uncertain (5+ years)"
    
    def get_detailed_breakdown(self) -> Dict[str, Any]:
        """Get detailed breakdown of readiness analysis.
        
        Returns:
            Dictionary with detailed analysis
        """
        base_score = self.calculate_score()
        adjusted_score = self.get_barrier_adjusted_score()
        
        breakdown = {
            'base_score': base_score,
            'adjusted_score': adjusted_score,
            'interpretation': self.get_interpretation(),
            'timeline': self.get_adoption_timeline(),
            'criteria': [],
            'barriers': self.barriers,
            'enablers': self.enablers
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
        """Generate recommendations based on readiness analysis.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Address critical barriers
        critical_barriers = [b for b in self.barriers if b['impact'] in ['critical', 'high']]
        if critical_barriers:
            recommendations.append(
                f"Address {len(critical_barriers)} critical/high-impact barriers before launch"
            )
        
        # Leverage enablers
        strong_enablers = [e for e in self.enablers if e['strength'] == 'high']
        if strong_enablers:
            recommendations.append(
                f"Leverage {len(strong_enablers)} strong enablers in go-to-market strategy"
            )
        
        # Timeline-based recommendations
        timeline = self.get_adoption_timeline()
        if 'Immediate' in timeline or 'Short-term' in timeline:
            recommendations.append("Market is ready - accelerate launch timeline")
        elif 'Long-term' in timeline or 'Uncertain' in timeline:
            recommendations.append("Market needs preparation - invest in education and infrastructure")
        
        # Weak areas
        weak_areas = [(k, v) for k, v in self.scores.items() if v < 5.0]
        if weak_areas:
            recommendations.append(
                f"Improve readiness in: {', '.join(k for k, _ in weak_areas)}"
            )
        
        return recommendations
