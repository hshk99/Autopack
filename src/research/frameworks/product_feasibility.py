"""Product Feasibility Framework

This module assesses the viability of a product by analyzing technical feasibility,
cost implications, and resource requirements.
"""

from typing import Dict, Any, Optional, List


class ProductFeasibility:
    """Assesses product viability using multi-dimensional analysis.
    
    Attributes:
        weights: Dictionary of criterion weights (must sum to 1.0)
        scores: Dictionary of criterion scores (0-10 scale)
        risk_factors: List of identified risks
    """
    
    DEFAULT_WEIGHTS = {
        'technical_feasibility': 0.30,
        'resource_availability': 0.25,
        'cost_viability': 0.20,
        'time_to_market': 0.15,
        'scalability': 0.10
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """Initialize the Product Feasibility framework.
        
        Args:
            weights: Custom weights for criteria (must sum to 1.0)
        
        Raises:
            ValueError: If weights don't sum to 1.0
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.scores: Dict[str, float] = {}
        self.risk_factors: List[Dict[str, Any]] = []
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
    
    def add_risk_factor(self, name: str, severity: str, mitigation: str) -> None:
        """Add a risk factor to the analysis.
        
        Args:
            name: Name/description of the risk
            severity: Risk severity (low, medium, high, critical)
            mitigation: Proposed mitigation strategy
        """
        valid_severities = ['low', 'medium', 'high', 'critical']
        if severity.lower() not in valid_severities:
            raise ValueError(f"Severity must be one of {valid_severities}")
        
        self.risk_factors.append({
            'name': name,
            'severity': severity.lower(),
            'mitigation': mitigation
        })
    
    def calculate_score(self) -> float:
        """Calculate weighted feasibility score.
        
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
    
    def get_risk_adjusted_score(self) -> float:
        """Calculate risk-adjusted feasibility score.
        
        Returns:
            Risk-adjusted score (0-10 scale)
        """
        base_score = self.calculate_score()
        
        # Calculate risk penalty
        risk_penalty = 0.0
        severity_weights = {
            'low': 0.1,
            'medium': 0.3,
            'high': 0.6,
            'critical': 1.0
        }
        
        for risk in self.risk_factors:
            risk_penalty += severity_weights[risk['severity']]
        
        # Cap penalty at 40% of base score
        max_penalty = base_score * 0.4
        actual_penalty = min(risk_penalty, max_penalty)
        
        return round(base_score - actual_penalty, 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the feasibility score.
        
        Returns:
            Interpretation string
        """
        score = self.get_risk_adjusted_score()
        if score >= 8.0:
            return "Highly Feasible"
        elif score >= 6.0:
            return "Feasible"
        elif score >= 4.0:
            return "Marginally Feasible"
        else:
            return "Not Feasible"
    
    def get_detailed_analysis(self) -> Dict[str, Any]:
        """Get detailed analysis including risk assessment.
        
        Returns:
            Dictionary with score breakdown and risk analysis
        """
        base_score = self.calculate_score()
        risk_adjusted_score = self.get_risk_adjusted_score()
        
        contributions = {
            criterion: round(self.weights[criterion] * self.scores[criterion], 2)
            for criterion in self.weights.keys()
        }
        
        return {
            'base_score': base_score,
            'risk_adjusted_score': risk_adjusted_score,
            'interpretation': self.get_interpretation(),
            'scores': self.scores.copy(),
            'weights': self.weights.copy(),
            'contributions': contributions,
            'risk_factors': self.risk_factors.copy(),
            'critical_risks': self._get_critical_risks(),
            'weak_areas': self._get_weak_areas()
        }
    
    def _get_critical_risks(self) -> List[Dict[str, Any]]:
        """Get high and critical severity risks."""
        return [
            risk for risk in self.risk_factors
            if risk['severity'] in ['high', 'critical']
        ]
    
    def _get_weak_areas(self) -> List[str]:
        """Identify weak areas (score < 5)."""
        return [
            criterion for criterion, score in self.scores.items()
            if score < 5.0
        ]
    
    def get_recommendations(self) -> List[str]:
        """Generate recommendations based on analysis.
        
        Returns:
            List of strategic recommendations
        """
        recommendations = []
        score = self.get_risk_adjusted_score()
        weak_areas = self._get_weak_areas()
        critical_risks = self._get_critical_risks()
        
        if score >= 7.0:
            recommendations.append("Product is highly feasible - proceed with development")
        elif score >= 5.0:
            recommendations.append("Product is feasible with risk mitigation")
        else:
            recommendations.append("Product feasibility is questionable - reconsider approach")
        
        if critical_risks:
            recommendations.append(
                f"Address {len(critical_risks)} critical risk(s) before proceeding"
            )
        
        if weak_areas:
            recommendations.append(
                f"Strengthen weak areas: {', '.join(weak_areas)}"
            )
        
        if self.scores.get('technical_feasibility', 0) < 6.0:
            recommendations.append("Conduct technical proof-of-concept")
        
        if self.scores.get('time_to_market', 0) < 5.0:
            recommendations.append("Develop accelerated timeline or phased approach")
        
        return recommendations
