"""Meta-Auditor Agent

This module implements the Meta-Auditor agent responsible for synthesizing findings from
various decision frameworks and generating strategic recommendations.
"""

from typing import Dict, Any, List, Optional
from src.research.frameworks.market_attractiveness import MarketAttractiveness
from src.research.frameworks.product_feasibility import ProductFeasibility
from src.research.frameworks.competitive_intensity import CompetitiveIntensity
from src.research.frameworks.adoption_readiness import AdoptionReadiness


class MetaAuditor:
    """Synthesizes findings from multiple decision frameworks.
    
    The Meta-Auditor analyzes results from various frameworks and generates
    comprehensive strategic recommendations.
    
    Attributes:
        frameworks: Dictionary of initialized framework instances
        synthesis: Synthesized analysis results
    """
    
    def __init__(self):
        """Initialize the Meta-Auditor agent."""
        self.frameworks: Dict[str, Any] = {
            'market_attractiveness': None,
            'product_feasibility': None,
            'competitive_intensity': None,
            'adoption_readiness': None
        }
        self.synthesis: Optional[Dict[str, Any]] = None
    
    def add_framework_analysis(self, framework_name: str, framework: Any) -> None:
        """Add a framework analysis to the meta-auditor.
        
        Args:
            framework_name: Name of the framework
            framework: Initialized framework instance with scores
        
        Raises:
            ValueError: If framework name is not recognized
        """
        if framework_name not in self.frameworks:
            raise ValueError(f"Unknown framework: {framework_name}")
        self.frameworks[framework_name] = framework
    
    def calculate_overall_score(self) -> float:
        """Calculate overall opportunity score across all frameworks.
        
        Returns:
            Overall score (0-10 scale)
        
        Raises:
            ValueError: If not all frameworks are provided
        """
        if any(fw is None for fw in self.frameworks.values()):
            missing = [name for name, fw in self.frameworks.items() if fw is None]
            raise ValueError(f"Missing framework analyses: {missing}")
        
        # Get scores from each framework
        market_score = self.frameworks['market_attractiveness'].calculate_score()
        feasibility_score = self.frameworks['product_feasibility'].get_risk_adjusted_score()
        
        # For competitive intensity, invert score (lower competition = better)
        competition_score = 10 - self.frameworks['competitive_intensity'].calculate_score()
        
        adoption_score = self.frameworks['adoption_readiness'].get_barrier_adjusted_score()
        
        # Weighted average (market and feasibility weighted higher)
        weights = {
            'market': 0.30,
            'feasibility': 0.30,
            'competition': 0.20,
            'adoption': 0.20
        }
        
        overall = (
            weights['market'] * market_score +
            weights['feasibility'] * feasibility_score +
            weights['competition'] * competition_score +
            weights['adoption'] * adoption_score
        )
        
        return round(overall, 2)
    
    def get_decision_recommendation(self) -> str:
        """Get strategic decision recommendation.
        
        Returns:
            Decision recommendation (GO, CONDITIONAL_GO, NO_GO, PIVOT)
        """
        overall_score = self.calculate_overall_score()
        
        # Get individual framework scores
        market_score = self.frameworks['market_attractiveness'].calculate_score()
        feasibility_score = self.frameworks['product_feasibility'].get_risk_adjusted_score()
        competition_score = self.frameworks['competitive_intensity'].calculate_score()
        adoption_score = self.frameworks['adoption_readiness'].get_barrier_adjusted_score()
        
        # Decision logic
        if overall_score >= 7.5:
            return "GO"
        elif overall_score >= 6.0:
            # Check for any critical weaknesses
            if market_score < 5.0 or feasibility_score < 5.0:
                return "PIVOT"
            return "CONDITIONAL_GO"
        elif overall_score >= 4.0:
            # Check if there's a path forward
            if market_score >= 7.0 and feasibility_score >= 6.0:
                return "CONDITIONAL_GO"
            return "PIVOT"
        else:
            return "NO_GO"
    
    def identify_critical_success_factors(self) -> List[str]:
        """Identify critical success factors across all frameworks.
        
        Returns:
            List of critical success factors
        """
        factors = []
        
        # Market factors
        market_analysis = self.frameworks['market_attractiveness'].get_detailed_analysis()
        if market_analysis['total_score'] >= 7.0:
            factors.extend([
                f"Strong market {factor}" 
                for factor in market_analysis['top_factors'][:2]
            ])
        
        # Feasibility factors
        feasibility_analysis = self.frameworks['product_feasibility'].get_detailed_analysis()
        if feasibility_analysis['risk_adjusted_score'] >= 7.0:
            factors.append("High product feasibility")
        if feasibility_analysis['critical_risks']:
            factors.append("Manage critical technical/resource risks")
        
        # Competitive factors
        competition_analysis = self.frameworks['competitive_intensity'].get_detailed_analysis()
        if competition_analysis['total_score'] < 6.0:
            factors.append("Favorable competitive landscape")
        else:
            factors.append("Strong differentiation required")
        
        # Adoption factors
        adoption_analysis = self.frameworks['adoption_readiness'].get_detailed_analysis()
        if adoption_analysis['barrier_adjusted_score'] >= 7.0:
            factors.append("Market ready for adoption")
        elif adoption_analysis['critical_barriers']:
            factors.append("Address adoption barriers early")
        
        return factors[:5]  # Top 5 factors
    
    def identify_key_risks(self) -> List[Dict[str, Any]]:
        """Identify key risks across all frameworks.
        
        Returns:
            List of risk dictionaries with severity and mitigation
        """
        risks = []
        
        # Market risks
        market_analysis = self.frameworks['market_attractiveness'].get_detailed_analysis()
        if market_analysis['total_score'] < 6.0:
            risks.append({
                'category': 'Market',
                'description': 'Weak market attractiveness',
                'severity': 'high',
                'mitigation': 'Validate market assumptions and consider alternative segments'
            })
        
        # Feasibility risks
        feasibility_analysis = self.frameworks['product_feasibility'].get_detailed_analysis()
        for risk in feasibility_analysis['critical_risks']:
            risks.append({
                'category': 'Feasibility',
                'description': risk['name'],
                'severity': risk['severity'],
                'mitigation': risk['mitigation']
            })
        
        # Competitive risks
        competition_analysis = self.frameworks['competitive_intensity'].get_detailed_analysis()
        if competition_analysis['total_score'] >= 7.0:
            risks.append({
                'category': 'Competition',
                'description': 'Intense competitive pressure',
                'severity': 'high',
                'mitigation': 'Develop strong differentiation and competitive moat'
            })
        
        # Adoption risks
        adoption_analysis = self.frameworks['adoption_readiness'].get_detailed_analysis()
        for barrier in adoption_analysis['critical_barriers']:
            risks.append({
                'category': 'Adoption',
                'description': barrier['name'],
                'severity': barrier['impact'],
                'mitigation': barrier['mitigation']
            })
        
        # Sort by severity
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        risks.sort(key=lambda x: severity_order.get(x['severity'], 4))
        
        return risks[:10]  # Top 10 risks
    
    def generate_strategic_recommendations(self) -> List[str]:
        """Generate comprehensive strategic recommendations.
        
        Returns:
            List of strategic recommendations
        """
        recommendations = []
        decision = self.get_decision_recommendation()
        
        # Overall recommendation
        decision_text = {
            'GO': 'Proceed with initiative - strong opportunity identified',
            'CONDITIONAL_GO': 'Proceed with caution - address identified concerns',
            'PIVOT': 'Pivot strategy - significant challenges identified',
            'NO_GO': 'Do not proceed - opportunity not viable'
        }
        recommendations.append(decision_text[decision])
        
        # Framework-specific recommendations
        for framework_name, framework in self.frameworks.items():
            if framework:
                fw_recommendations = framework.get_recommendations()
                recommendations.extend(fw_recommendations[:2])  # Top 2 from each
        
        # Critical success factors
        csf = self.identify_critical_success_factors()
        if csf:
            recommendations.append("Critical Success Factors:")
            recommendations.extend([f"  - {factor}" for factor in csf])
        
        # Key risks
        risks = self.identify_key_risks()
        if risks:
            recommendations.append("Key Risks to Manage:")
            for risk in risks[:3]:  # Top 3 risks
                recommendations.append(
                    f"  - [{risk['severity'].upper()}] {risk['description']}"
                )
        
        return recommendations
    
    def synthesize_analysis(self) -> Dict[str, Any]:
        """Synthesize all framework analyses into comprehensive report.
        
        Returns:
            Comprehensive synthesis dictionary
        """
        overall_score = self.calculate_overall_score()
        decision = self.get_decision_recommendation()
        
        # Collect individual framework analyses
        framework_analyses = {}
        for name, framework in self.frameworks.items():
            if framework:
                framework_analyses[name] = framework.get_detailed_analysis()
        
        self.synthesis = {
            'overall_score': overall_score,
            'decision_recommendation': decision,
            'critical_success_factors': self.identify_critical_success_factors(),
            'key_risks': self.identify_key_risks(),
            'strategic_recommendations': self.generate_strategic_recommendations(),
            'framework_analyses': framework_analyses,
            'confidence_level': self._calculate_confidence_level(),
            'next_steps': self._generate_next_steps(decision)
        }
        
        return self.synthesis
    
    def _calculate_confidence_level(self) -> str:
        """Calculate confidence level in the analysis.
        
        Returns:
            Confidence level (High, Medium, Low)
        """
        # Check score variance across frameworks
        scores = [
            self.frameworks['market_attractiveness'].calculate_score(),
            self.frameworks['product_feasibility'].get_risk_adjusted_score(),
            10 - self.frameworks['competitive_intensity'].calculate_score(),
            self.frameworks['adoption_readiness'].get_barrier_adjusted_score()
        ]
        
        # Calculate standard deviation
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5
        
        # Low variance = high confidence
        if std_dev < 1.5:
            return "High"
        elif std_dev < 2.5:
            return "Medium"
        else:
            return "Low"
    
    def _generate_next_steps(self, decision: str) -> List[str]:
        """Generate next steps based on decision.
        
        Args:
            decision: Decision recommendation
        
        Returns:
            List of next steps
        """
        next_steps = []
        
        if decision == "GO":
            next_steps = [
                "Develop detailed implementation plan",
                "Allocate resources and budget",
                "Establish success metrics and KPIs",
                "Begin execution with regular monitoring"
            ]
        elif decision == "CONDITIONAL_GO":
            next_steps = [
                "Address identified risks and concerns",
                "Conduct additional validation studies",
                "Develop contingency plans",
                "Establish go/no-go checkpoints",
                "Proceed with pilot or phased approach"
            ]
        elif decision == "PIVOT":
            next_steps = [
                "Reassess strategic approach",
                "Explore alternative market segments",
                "Modify product/service offering",
                "Conduct additional market research",
                "Re-evaluate with updated strategy"
            ]
        else:  # NO_GO
            next_steps = [
                "Document lessons learned",
                "Explore alternative opportunities",
                "Reallocate resources to higher-priority initiatives",
                "Monitor market for future opportunities"
            ]
        
        return next_steps
    
    def get_executive_summary(self) -> str:
        """Generate executive summary of the analysis.
        
        Returns:
            Executive summary text
        """
        if not self.synthesis:
            self.synthesize_analysis()
        
        decision = self.synthesis['decision_recommendation']
        score = self.synthesis['overall_score']
        confidence = self.synthesis['confidence_level']
        
        summary = f"""EXECUTIVE SUMMARY

Overall Assessment Score: {score}/10
Recommendation: {decision}
Confidence Level: {confidence}

Key Findings:
"""
        
        # Add top 3 critical success factors
        csf = self.synthesis['critical_success_factors'][:3]
        if csf:
            summary += "\nCritical Success Factors:\n"
            for factor in csf:
                summary += f"  • {factor}\n"
        
        # Add top 3 risks
        risks = self.synthesis['key_risks'][:3]
        if risks:
            summary += "\nKey Risks:\n"
            for risk in risks:
                summary += f"  • [{risk['severity'].upper()}] {risk['description']}\n"
        
        # Add top recommendations
        recommendations = self.synthesis['strategic_recommendations'][:5]
        if recommendations:
            summary += "\nStrategic Recommendations:\n"
            for rec in recommendations:
                summary += f"  • {rec}\n"
        
        return summary
