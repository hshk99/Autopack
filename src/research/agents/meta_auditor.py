"""Meta-Auditor Agent

This module implements the Meta-Auditor agent responsible for synthesizing findings from
various decision frameworks and generating strategic recommendations.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

# NOTE: repo uses PYTHONPATH=src, so modules under src/research are imported as `research.*`
from research.frameworks.market_attractiveness import MarketAttractiveness, AttractivenessLevel
from research.frameworks.product_feasibility import ProductFeasibility, FeasibilityLevel
from research.frameworks.competitive_intensity import CompetitiveIntensity, IntensityLevel
from research.frameworks.adoption_readiness import AdoptionReadiness, ReadinessLevel


class StrategicRecommendation(Enum):
    """Strategic recommendation categories."""
    PURSUE_AGGRESSIVELY = "pursue_aggressively"
    PURSUE_CAUTIOUSLY = "pursue_cautiously"
    MONITOR_AND_PREPARE = "monitor_and_prepare"
    DEPRIORITIZE = "deprioritize"
    REJECT = "reject"


class ConfidenceLevel(Enum):
    """Confidence level in recommendations."""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class FrameworkResults:
    """Container for all framework analysis results."""
    market_attractiveness: Optional[Dict[str, Any]] = None
    product_feasibility: Optional[Dict[str, Any]] = None
    competitive_intensity: Optional[Dict[str, Any]] = None
    adoption_readiness: Optional[Dict[str, Any]] = None


@dataclass
class MetaAuditor:
    """Meta-auditor agent that synthesizes framework findings into strategic recommendations."""
    framework_results: FrameworkResults
    business_context: Dict[str, Any] = field(default_factory=dict)
    risk_tolerance: str = "moderate"  # conservative, moderate, aggressive
    
    def calculate_composite_score(self) -> float:
        """Calculate composite opportunity score from all frameworks.
        
        Returns:
            Weighted composite score (0-100)
        """
        scores = []
        weights = []
        
        # Market attractiveness (30% weight)
        if self.framework_results.market_attractiveness:
            scores.append(self.framework_results.market_attractiveness.get("overall_score", 50))
            weights.append(0.30)
        
        # Product feasibility (25% weight)
        if self.framework_results.product_feasibility:
            scores.append(self.framework_results.product_feasibility.get("overall_score", 50))
            weights.append(0.25)
        
        # Competitive intensity (20% weight, inverted - lower is better)
        if self.framework_results.competitive_intensity:
            comp_score = self.framework_results.competitive_intensity.get("overall_score", 50)
            scores.append(100 - comp_score)  # Invert: low competition = high score
            weights.append(0.20)
        
        # Adoption readiness (25% weight)
        if self.framework_results.adoption_readiness:
            scores.append(self.framework_results.adoption_readiness.get("overall_score", 50))
            weights.append(0.25)
        
        if not scores:
            return 50.0  # Neutral if no data
        
        # Normalize weights
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        
        # Calculate weighted average
        composite = sum(s * w for s, w in zip(scores, normalized_weights))
        return round(composite, 2)
    
    def assess_strategic_fit(self) -> Dict[str, Any]:
        """Assess strategic fit based on framework alignment.
        
        Returns:
            Dictionary with fit assessment and alignment analysis
        """
        alignments = []
        conflicts = []
        
        # Check market-feasibility alignment
        if (self.framework_results.market_attractiveness and 
            self.framework_results.product_feasibility):
            market_level = self.framework_results.market_attractiveness.get("attractiveness_level", "")
            feasibility_level = self.framework_results.product_feasibility.get("feasibility_level", "")
            
            if "high" in market_level and "high" in feasibility_level:
                alignments.append("Strong alignment: Attractive market with high feasibility")
            elif "low" in market_level and "high" in feasibility_level:
                conflicts.append("Mismatch: High feasibility but unattractive market")
            elif "high" in market_level and "low" in feasibility_level:
                conflicts.append("Mismatch: Attractive market but low feasibility")
        
        # Check competition-readiness alignment
        if (self.framework_results.competitive_intensity and 
            self.framework_results.adoption_readiness):
            comp_level = self.framework_results.competitive_intensity.get("intensity_level", "")
            readiness_level = self.framework_results.adoption_readiness.get("readiness_level", "")
            
            if "high" in comp_level and "not_ready" in readiness_level:
                conflicts.append("High risk: Intense competition with low market readiness")
            elif ("low" in comp_level or "moderate" in comp_level) and "ready" in readiness_level:
                alignments.append("Favorable conditions: Moderate competition with ready market")
        
        # Overall fit score
        fit_score = len(alignments) * 20 - len(conflicts) * 15
        fit_score = max(0, min(100, 50 + fit_score))  # Normalize around 50
        
        return {
            "fit_score": fit_score,
            "alignments": alignments,
            "conflicts": conflicts,
            "alignment_count": len(alignments),
            "conflict_count": len(conflicts)
        }
    
    def identify_key_risks(self) -> List[Dict[str, Any]]:
        """Identify key risks across all frameworks.
        
        Returns:
            List of identified risks with severity and mitigation
        """
        risks = []
        
        # Feasibility risks
        if self.framework_results.product_feasibility:
            risk_analysis = self.framework_results.product_feasibility.get("risk_analysis", {})
            critical_risks = risk_analysis.get("critical_risk_details", [])
            for risk in critical_risks:
                risks.append({
                    "source": "Product Feasibility",
                    "type": risk.get("level", "unknown"),
                    "description": risk.get("description", "Unspecified risk"),
                    "impact": risk.get("impact", "medium")
                })
        
        # Competitive risks
        if self.framework_results.competitive_intensity:
            comp_score = self.framework_results.competitive_intensity.get("overall_score", 0)
            if comp_score > 70:
                risks.append({
                    "source": "Competitive Intensity",
                    "type": "high",
                    "description": "High competitive intensity may limit market entry success",
                    "impact": "high"
                })
        
        # Adoption risks
        if self.framework_results.adoption_readiness:
            barriers = self.framework_results.adoption_readiness.get("barriers", {})
            critical_count = barriers.get("critical_barriers", 0)
            if critical_count > 0:
                risks.append({
                    "source": "Adoption Readiness",
                    "type": "high",
                    "description": f"{critical_count} critical adoption barriers identified",
                    "impact": "high"
                })
        
        # Market risks
        if self.framework_results.market_attractiveness:
            market_metrics = self.framework_results.market_attractiveness.get("market_metrics", {})
            growth_rate = market_metrics.get("growth_rate", 0)
            if growth_rate < 5:
                risks.append({
                    "source": "Market Attractiveness",
                    "type": "medium",
                    "description": "Low market growth rate may limit expansion potential",
                    "impact": "medium"
                })
        
        return risks
    
    def identify_key_opportunities(self) -> List[Dict[str, Any]]:
        """Identify key opportunities across all frameworks.
        
        Returns:
            List of identified opportunities with potential impact
        """
        opportunities = []
        
        # Market opportunities
        if self.framework_results.market_attractiveness:
            market_metrics = self.framework_results.market_attractiveness.get("market_metrics", {})
            growth_rate = market_metrics.get("growth_rate", 0)
            if growth_rate > 15:
                opportunities.append({
                    "source": "Market Attractiveness",
                    "description": f"High market growth rate ({growth_rate}%) enables rapid expansion",
                    "potential_impact": "high"
                })
            
            tech_trends = self.framework_results.market_attractiveness.get("key_factors", {}).get("technology_trends", [])
            if len(tech_trends) > 3:
                opportunities.append({
                    "source": "Market Attractiveness",
                    "description": "Multiple favorable technology trends support market entry",
                    "potential_impact": "medium"
                })
        
        # Competitive opportunities
        if self.framework_results.competitive_intensity:
            positioning = self.framework_results.competitive_intensity.get("positioning_analysis", {})
            opps = positioning.get("opportunities", [])
            for opp in opps:
                opportunities.append({
                    "source": "Competitive Intensity",
                    "description": opp,
                    "potential_impact": "medium"
                })
        
        # Adoption opportunities
        if self.framework_results.adoption_readiness:
            recommendations = self.framework_results.adoption_readiness.get("strategic_recommendations", {})
            if recommendations.get("readiness_level") in ["ready", "highly_ready"]:
                opportunities.append({
                    "source": "Adoption Readiness",
                    "description": "Market is ready for adoption - favorable timing for entry",
                    "potential_impact": "high"
                })
        
        return opportunities
    
    def generate_strategic_recommendation(self) -> StrategicRecommendation:
        """Generate overall strategic recommendation.
        
        Returns:
            StrategicRecommendation enum value
        """
        composite_score = self.calculate_composite_score()
        fit_assessment = self.assess_strategic_fit()
        risks = self.identify_key_risks()
        
        # Adjust thresholds based on risk tolerance
        if self.risk_tolerance == "aggressive":
            pursue_threshold = 55
            caution_threshold = 40
            monitor_threshold = 30
        elif self.risk_tolerance == "conservative":
            pursue_threshold = 75
            caution_threshold = 60
            monitor_threshold = 45
        else:  # moderate
            pursue_threshold = 65
            caution_threshold = 50
            monitor_threshold = 35
        
        # Adjust for strategic fit
        fit_score = fit_assessment.get("fit_score", 50)
        adjusted_score = (composite_score * 0.7) + (fit_score * 0.3)
        
        # Count critical risks
        critical_risk_count = sum(1 for r in risks if r.get("type") in ["critical", "high"])
        
        # Decision logic
        if adjusted_score >= pursue_threshold and critical_risk_count <= 1:
            return StrategicRecommendation.PURSUE_AGGRESSIVELY
        elif adjusted_score >= caution_threshold and critical_risk_count <= 3:
            return StrategicRecommendation.PURSUE_CAUTIOUSLY
        elif adjusted_score >= monitor_threshold:
            return StrategicRecommendation.MONITOR_AND_PREPARE
        elif adjusted_score >= 25:
            return StrategicRecommendation.DEPRIORITIZE
        else:
            return StrategicRecommendation.REJECT
    
    def calculate_confidence_level(self) -> ConfidenceLevel:
        """Calculate confidence level in the recommendation.
        
        Returns:
            ConfidenceLevel enum value
        """
        # Count available frameworks
        available_frameworks = sum([
            self.framework_results.market_attractiveness is not None,
            self.framework_results.product_feasibility is not None,
            self.framework_results.competitive_intensity is not None,
            self.framework_results.adoption_readiness is not None
        ])
        
        # Check for conflicts
        fit_assessment = self.assess_strategic_fit()
        conflict_count = fit_assessment.get("conflict_count", 0)
        
        # Calculate confidence
        if available_frameworks == 4 and conflict_count == 0:
            return ConfidenceLevel.VERY_HIGH
        elif available_frameworks >= 3 and conflict_count <= 1:
            return ConfidenceLevel.HIGH
        elif available_frameworks >= 2 and conflict_count <= 2:
            return ConfidenceLevel.MEDIUM
        elif available_frameworks >= 1:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def generate_executive_summary(self) -> str:
        """Generate executive summary of the analysis.
        
        Returns:
            Executive summary string
        """
        recommendation = self.generate_strategic_recommendation()
        composite_score = self.calculate_composite_score()
        confidence = self.calculate_confidence_level()
        
        summary_parts = []
        
        # Opening statement
        summary_parts.append(f"Strategic Recommendation: {recommendation.value.replace('_', ' ').title()}")
        summary_parts.append(f"Composite Opportunity Score: {composite_score}/100")
        summary_parts.append(f"Confidence Level: {confidence.value.replace('_', ' ').title()}")
        summary_parts.append("")
        
        # Key findings
        summary_parts.append("Key Findings:")
        
        if self.framework_results.market_attractiveness:
            level = self.framework_results.market_attractiveness.get("attractiveness_level", "unknown")
            summary_parts.append(f"- Market Attractiveness: {level.replace('_', ' ').title()}")
        
        if self.framework_results.product_feasibility:
            level = self.framework_results.product_feasibility.get("feasibility_level", "unknown")
            summary_parts.append(f"- Product Feasibility: {level.replace('_', ' ').title()}")
        
        if self.framework_results.competitive_intensity:
            level = self.framework_results.competitive_intensity.get("intensity_level", "unknown")
            summary_parts.append(f"- Competitive Intensity: {level.replace('_', ' ').title()}")
        
        if self.framework_results.adoption_readiness:
            level = self.framework_results.adoption_readiness.get("readiness_level", "unknown")
            summary_parts.append(f"- Adoption Readiness: {level.replace('_', ' ').title()}")
        
        return "\n".join(summary_parts)
    
    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive meta-analysis report.
        
        Returns:
            Dictionary containing complete analysis and recommendations
        """
        composite_score = self.calculate_composite_score()
        recommendation = self.generate_strategic_recommendation()
        confidence = self.calculate_confidence_level()
        fit_assessment = self.assess_strategic_fit()
        risks = self.identify_key_risks()
        opportunities = self.identify_key_opportunities()
        executive_summary = self.generate_executive_summary()
        
        return {
            "meta_analysis": {
                "composite_score": composite_score,
                "strategic_recommendation": recommendation.value,
                "confidence_level": confidence.value,
                "risk_tolerance": self.risk_tolerance
            },
            "executive_summary": executive_summary,
            "strategic_fit": fit_assessment,
            "risk_assessment": {
                "total_risks": len(risks),
                "critical_risks": sum(1 for r in risks if r.get("type") in ["critical", "high"]),
                "key_risks": risks[:5]  # Top 5 risks
            },
            "opportunity_assessment": {
                "total_opportunities": len(opportunities),
                "high_impact_opportunities": sum(1 for o in opportunities if o.get("potential_impact") == "high"),
                "key_opportunities": opportunities[:5]  # Top 5 opportunities
            },
            "framework_summaries": {
                "market_attractiveness": self.framework_results.market_attractiveness,
                "product_feasibility": self.framework_results.product_feasibility,
                "competitive_intensity": self.framework_results.competitive_intensity,
                "adoption_readiness": self.framework_results.adoption_readiness
            },
            "business_context": self.business_context
        }
