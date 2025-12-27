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
    
    def add_risk_factor(self, name: str, severity: str, mitigation: Optional[str] = None) -> None:
        """Add a risk factor to the analysis.
        
        Args:
            name: Name/description of the risk
            severity: Risk severity (low, medium, high, critical)
            mitigation: Proposed mitigation strategy
            
        Raises:
            ValueError: If severity is invalid
        """
        valid_severities = ['low', 'medium', 'high', 'critical']
        if severity.lower() not in valid_severities:
            raise ValueError(f"Severity must be one of {valid_severities}")
        
        risk = {
            'name': name,
            'severity': severity.lower(),
            'mitigation': mitigation
        }
        self.risk_factors.append(risk)
    
    def calculate_score(self) -> float:
        """Calculate weighted overall feasibility score.
        
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
    
    def get_risk_adjusted_score(self) -> float:
        """Calculate risk-adjusted feasibility score.
        
        Returns:
            Risk-adjusted score (0-10 scale)
        """
        base_score = self.calculate_score()
        
        # Calculate risk penalty
        risk_penalty = 0.0
        severity_weights = {'low': 0.1, 'medium': 0.3, 'high': 0.6, 'critical': 1.0}
        
        for risk in self.risk_factors:
            penalty = severity_weights[risk['severity']]
            # Reduce penalty if mitigation exists
            if risk.get('mitigation'):
                penalty *= 0.5
            risk_penalty += penalty
        
        # Cap penalty at 40% of base score
        max_penalty = base_score * 0.4
        risk_penalty = min(risk_penalty, max_penalty)
        
        adjusted_score = base_score - risk_penalty
        return round(max(0, adjusted_score), 2)
    
    def get_interpretation(self) -> str:
        """Get interpretation of the overall score.
        
        Returns:
            Interpretation string
        """
        score = self.get_risk_adjusted_score()
        
        if score >= 8.0:
            return "Highly Feasible"
        elif score >= 6.0:
            return "Feasible"
        elif score >= 4.0:
            return "Moderately Feasible"
        elif score >= 2.0:
            return "Low Feasibility"
        else:
            return "Not Feasible"
    
    def get_detailed_breakdown(self) -> Dict[str, Any]:
        """Get detailed breakdown of scores and risk analysis.
        
        Returns:
            Dictionary with detailed analysis
        """
        base_score = self.calculate_score()
        adjusted_score = self.get_risk_adjusted_score()
        
        breakdown = {
            'base_score': base_score,
            'risk_adjusted_score': adjusted_score,
            'interpretation': self.get_interpretation(),
            'criteria': [],
            'risks': self.risk_factors
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
        """Generate recommendations based on scores and risks.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Address critical and high risks
        critical_risks = [r for r in self.risk_factors if r['severity'] in ['critical', 'high']]
        if critical_risks:
            recommendations.append(
                f"Urgently address {len(critical_risks)} critical/high-severity risks before proceeding"
            )
        
        # Identify weak areas
        weak_areas = [(k, v) for k, v in self.scores.items() if v < 5.0]
        if weak_areas:
            recommendations.append(
                f"Improve feasibility in: {', '.join(k for k, _ in weak_areas)}"
            )
        
        # Overall assessment
        adjusted_score = self.get_risk_adjusted_score()
        if adjusted_score >= 7.0:
            recommendations.append("Product shows strong feasibility - proceed with development")
        elif adjusted_score < 4.0:
            recommendations.append("Product shows limited feasibility - consider redesign or alternative approaches")
        
        return recommendations
