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
    comprehensive strategic recommendations with risk assessments.
    """
    
    def __init__(self):
        """Initialize the Meta-Auditor agent."""
        self.frameworks: Dict[str, Any] = {}
        self.synthesis: Dict[str, Any] = {}
        self.recommendations: List[Dict[str, Any]] = []
    
    def add_framework_result(self, framework_name: str, framework: Any) -> None:
        """Add a framework result for analysis.
        
        Args:
            framework_name: Name of the framework
            framework: Framework instance with calculated results
        """
        self.frameworks[framework_name] = framework
    
    def calculate_overall_viability(self) -> float:
        """Calculate overall viability score across all frameworks.
        
        Returns:
            Overall viability score (0-10 scale)
            
        Raises:
            ValueError: If required frameworks are missing
        """
        required = ['market_attractiveness', 'product_feasibility', 
                   'competitive_intensity', 'adoption_readiness']
        missing = [f for f in required if f not in self.frameworks]
        
        if missing:
            raise ValueError(f"Missing required frameworks: {missing}")
        
        # Get scores from each framework
        market_score = self.frameworks['market_attractiveness'].calculate_score()
        feasibility_score = self.frameworks['product_feasibility'].get_risk_adjusted_score()
        
        # Competitive intensity is inverse (lower is better)
        competition_score = self.frameworks['competitive_intensity'].calculate_score()
        competition_adjusted = 10 - competition_score
        
        adoption_score = self.frameworks['adoption_readiness'].get_barrier_adjusted_score()
        
        # Weighted average (market and feasibility are most important)
        weights = {
            'market': 0.30,
            'feasibility': 0.30,
            'competition': 0.20,
            'adoption': 0.20
        }
        
        overall = (
            market_score * weights['market'] +
            feasibility_score * weights['feasibility'] +
            competition_adjusted * weights['competition'] +
            adoption_score * weights['adoption']
        )
        
        return round(overall, 2)
    
    def get_viability_interpretation(self) -> str:
        """Get interpretation of overall viability.
        
        Returns:
            Interpretation string
        """
        score = self.calculate_overall_viability()
        
        if score >= 8.0:
            return "Highly Viable - Strong Go"
        elif score >= 6.5:
            return "Viable - Proceed with Caution"
        elif score >= 5.0:
            return "Marginal - Requires Significant Improvements"
        elif score >= 3.0:
            return "Low Viability - Reconsider Strategy"
        else:
            return "Not Viable - Do Not Proceed"
    
    def identify_critical_risks(self) -> List[Dict[str, Any]]:
        """Identify critical risks across all frameworks.
        
        Returns:
            List of critical risk dictionaries
        """
        risks = []
        
        # Market risks
        if 'market_attractiveness' in self.frameworks:
            market = self.frameworks['market_attractiveness']
            if market.calculate_score() < 5.0:
                risks.append({
                    'category': 'Market',
                    'severity': 'high',
                    'description': 'Low market attractiveness score',
                    'impact': 'May not justify investment'
                })
        
        # Feasibility risks
        if 'product_feasibility' in self.frameworks:
            feasibility = self.frameworks['product_feasibility']
            critical_risks = [r for r in feasibility.risk_factors 
                            if r['severity'] in ['critical', 'high']]
            for risk in critical_risks:
                risks.append({
                    'category': 'Feasibility',
                    'severity': risk['severity'],
                    'description': risk['name'],
                    'impact': 'May prevent successful product development',
                    'mitigation': risk.get('mitigation')
                })
        
        # Competition risks
        if 'competitive_intensity' in self.frameworks:
            competition = self.frameworks['competitive_intensity']
            if competition.calculate_score() >= 7.0:
                risks.append({
                    'category': 'Competition',
                    'severity': 'high',
                    'description': 'Extremely intense competitive environment',
                    'impact': 'Difficult to gain market share'
                })
        
        # Adoption risks
        if 'adoption_readiness' in self.frameworks:
            adoption = self.frameworks['adoption_readiness']
            critical_barriers = [b for b in adoption.barriers 
                               if b['impact'] in ['critical', 'high']]
            for barrier in critical_barriers:
                risks.append({
                    'category': 'Adoption',
                    'severity': barrier['impact'],
                    'description': barrier['name'],
                    'impact': 'May slow or prevent market adoption',
                    'mitigation': barrier.get('mitigation')
                })
        
        return risks
    
    def identify_key_opportunities(self) -> List[Dict[str, Any]]:
        """Identify key opportunities across all frameworks.
        
        Returns:
            List of opportunity dictionaries
        """
        opportunities = []
        
        # Market opportunities
        if 'market_attractiveness' in self.frameworks:
            market = self.frameworks['market_attractiveness']
            if market.calculate_score() >= 7.0:
                opportunities.append({
                    'category': 'Market',
                    'description': 'Highly attractive market with strong potential',
                    'action': 'Prioritize market entry and capture'
                })
        
        # Competition opportunities
        if 'competitive_intensity' in self.frameworks:
            competition = self.frameworks['competitive_intensity']
            if competition.calculate_score() < 5.0:
                opportunities.append({
                    'category': 'Competition',
                    'description': 'Low competitive intensity - opportunity for leadership',
                    'action': 'Establish strong market position quickly'
                })
        
        # Adoption opportunities
        if 'adoption_readiness' in self.frameworks:
            adoption = self.frameworks['adoption_readiness']
            strong_enablers = [e for e in adoption.enablers if e['strength'] == 'high']
            if strong_enablers:
                for enabler in strong_enablers:
                    opportunities.append({
                        'category': 'Adoption',
                        'description': f"Strong enabler: {enabler['name']}",
                        'action': enabler.get('leverage', 'Leverage in go-to-market strategy')
                    })
        
        return opportunities
    
    def generate_strategic_recommendations(self) -> List[Dict[str, Any]]:
        """Generate comprehensive strategic recommendations.
        
        Returns:
            List of recommendation dictionaries with priority and rationale
        """
        recommendations = []
        overall_score = self.calculate_overall_viability()
        
        # Overall strategic direction
        if overall_score >= 7.0:
            recommendations.append({
                'priority': 'critical',
                'category': 'Strategy',
                'recommendation': 'Proceed with aggressive market entry strategy',
                'rationale': 'Strong viability across all dimensions',
                'timeline': 'Immediate'
            })
        elif overall_score >= 5.0:
            recommendations.append({
                'priority': 'high',
                'category': 'Strategy',
                'recommendation': 'Proceed with cautious, phased approach',
                'rationale': 'Moderate viability with areas requiring improvement',
                'timeline': 'Short-term (3-6 months)'
            })
        else:
            recommendations.append({
                'priority': 'critical',
                'category': 'Strategy',
                'recommendation': 'Pause and reassess - significant improvements needed',
                'rationale': 'Low overall viability score',
                'timeline': 'Immediate'
            })
        
        # Framework-specific recommendations
        for name, framework in self.frameworks.items():
            if hasattr(framework, 'get_recommendations'):
                framework_recs = framework.get_recommendations()
                for rec in framework_recs:
                    recommendations.append({
                        'priority': 'medium',
                        'category': name.replace('_', ' ').title(),
                        'recommendation': rec,
                        'rationale': f'Based on {name} analysis',
                        'timeline': 'Medium-term'
                    })
        
        # Risk mitigation recommendations
        critical_risks = self.identify_critical_risks()
        for risk in critical_risks[:3]:  # Top 3 risks
            if risk.get('mitigation'):
                recommendations.append({
                    'priority': 'high',
                    'category': 'Risk Mitigation',
                    'recommendation': risk['mitigation'],
                    'rationale': f"Mitigate {risk['severity']} risk: {risk['description']}",
                    'timeline': 'Immediate'
                })
        
        # Opportunity capture recommendations
        opportunities = self.identify_key_opportunities()
        for opp in opportunities[:3]:  # Top 3 opportunities
            recommendations.append({
                'priority': 'medium',
                'category': 'Opportunity',
                'recommendation': opp['action'],
                'rationale': opp['description'],
                'timeline': 'Short-term'
            })
        
        # Sort by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 99))
        
        return recommendations
    
    def synthesize_findings(self) -> Dict[str, Any]:
        """Synthesize all findings into comprehensive analysis.
        
        Returns:
            Dictionary with complete synthesis
        """
        synthesis = {
            'overall_viability': {
                'score': self.calculate_overall_viability(),
                'interpretation': self.get_viability_interpretation()
            },
            'framework_scores': {},
            'critical_risks': self.identify_critical_risks(),
            'key_opportunities': self.identify_key_opportunities(),
            'strategic_recommendations': self.generate_strategic_recommendations()
        }
        
        # Add individual framework scores
        if 'market_attractiveness' in self.frameworks:
            synthesis['framework_scores']['market_attractiveness'] = {
                'score': self.frameworks['market_attractiveness'].calculate_score(),
                'interpretation': self.frameworks['market_attractiveness'].get_interpretation()
            }
        
        if 'product_feasibility' in self.frameworks:
            synthesis['framework_scores']['product_feasibility'] = {
                'score': self.frameworks['product_feasibility'].get_risk_adjusted_score(),
                'interpretation': self.frameworks['product_feasibility'].get_interpretation()
            }
        
        if 'competitive_intensity' in self.frameworks:
            synthesis['framework_scores']['competitive_intensity'] = {
                'score': self.frameworks['competitive_intensity'].calculate_score(),
                'interpretation': self.frameworks['competitive_intensity'].get_interpretation()
            }
        
        if 'adoption_readiness' in self.frameworks:
            synthesis['framework_scores']['adoption_readiness'] = {
                'score': self.frameworks['adoption_readiness'].get_barrier_adjusted_score(),
                'interpretation': self.frameworks['adoption_readiness'].get_interpretation(),
                'timeline': self.frameworks['adoption_readiness'].get_adoption_timeline()
            }
        
        self.synthesis = synthesis
        return synthesis
    
    def get_executive_summary(self) -> str:
        """Generate executive summary of findings.
        
        Returns:
            Executive summary string
        """
        if not self.synthesis:
            self.synthesize_findings()
        
        score = self.synthesis['overall_viability']['score']
        interpretation = self.synthesis['overall_viability']['interpretation']
        
        summary = f"""EXECUTIVE SUMMARY

Overall Viability: {score}/10 - {interpretation}

Key Findings:
"""
        
        # Add framework summaries
        for name, data in self.synthesis['framework_scores'].items():
            summary += f"\n- {name.replace('_', ' ').title()}: {data['score']}/10 ({data['interpretation']})"
        
        # Add critical risks
        if self.synthesis['critical_risks']:
            summary += "\n\nCritical Risks:\n"
            for risk in self.synthesis['critical_risks'][:3]:
                summary += f"- [{risk['severity'].upper()}] {risk['description']}\n"
        
        # Add top opportunities
        if self.synthesis['key_opportunities']:
            summary += "\nKey Opportunities:\n"
            for opp in self.synthesis['key_opportunities'][:3]:
                summary += f"- {opp['description']}\n"
        
        # Add top recommendations
        summary += "\nTop Strategic Recommendations:\n"
        top_recs = [r for r in self.synthesis['strategic_recommendations'] 
                   if r['priority'] in ['critical', 'high']][:3]
        for rec in top_recs:
            summary += f"- [{rec['priority'].upper()}] {rec['recommendation']}\n"
        
        return summary
