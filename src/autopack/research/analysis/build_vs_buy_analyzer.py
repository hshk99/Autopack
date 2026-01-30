"""
Build vs Buy Analyzer for research pipeline.

Evaluates build vs. buy decisions for external tools, APIs, and frameworks.
Analyzes cost, time, risk, and strategic factors to make recommendations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DecisionRecommendation(Enum):
    """Recommendation types for build vs buy decisions."""

    BUILD = "BUILD"
    BUY = "BUY"
    HYBRID = "HYBRID"


class RiskCategory(Enum):
    """Categories of risks in build vs buy decisions."""

    VENDOR_LOCK_IN = "vendor_lock_in"
    TECHNICAL_DEBT = "technical_debt"
    MAINTENANCE_BURDEN = "maintenance_burden"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    SCALABILITY = "scalability"
    INTEGRATION = "integration"
    COST_OVERRUN = "cost_overrun"
    TIME_TO_MARKET = "time_to_market"
    FEATURE_FIT = "feature_fit"


class StrategicImportance(Enum):
    """Strategic importance levels for components."""

    CORE_DIFFERENTIATOR = "core_differentiator"
    SUPPORTING = "supporting"
    COMMODITY = "commodity"


@dataclass
class RiskAssessment:
    """Assessment of a specific risk."""

    category: RiskCategory
    severity: str  # "low", "medium", "high", "critical"
    description: str
    mitigation: Optional[str] = None


@dataclass
class CostEstimate:
    """Cost estimate for a build or buy option."""

    initial_cost: float
    monthly_recurring: float
    year_1_total: float
    year_3_total: float
    year_5_total: float
    cost_drivers: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)


@dataclass
class BuildVsBuyAnalysis:
    """Result of build-vs-buy analysis."""

    component: str
    recommendation: DecisionRecommendation
    confidence: float  # 0.0 to 1.0
    build_cost: CostEstimate
    buy_cost: CostEstimate
    build_time_weeks: float
    buy_integration_time_weeks: float
    risks: List[RiskAssessment]
    rationale: str
    strategic_importance: StrategicImportance
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    # Scoring breakdown
    build_score: float = 0.0
    buy_score: float = 0.0
    key_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "component": self.component,
            "recommendation": self.recommendation.value,
            "confidence": self.confidence,
            "build_cost": {
                "initial_cost": self.build_cost.initial_cost,
                "monthly_recurring": self.build_cost.monthly_recurring,
                "year_1_total": self.build_cost.year_1_total,
                "year_3_total": self.build_cost.year_3_total,
                "year_5_total": self.build_cost.year_5_total,
                "cost_drivers": self.build_cost.cost_drivers,
                "assumptions": self.build_cost.assumptions,
            },
            "buy_cost": {
                "initial_cost": self.buy_cost.initial_cost,
                "monthly_recurring": self.buy_cost.monthly_recurring,
                "year_1_total": self.buy_cost.year_1_total,
                "year_3_total": self.buy_cost.year_3_total,
                "year_5_total": self.buy_cost.year_5_total,
                "cost_drivers": self.buy_cost.cost_drivers,
                "assumptions": self.buy_cost.assumptions,
            },
            "build_time_weeks": self.build_time_weeks,
            "buy_integration_time_weeks": self.buy_integration_time_weeks,
            "risks": [
                {
                    "category": r.category.value,
                    "severity": r.severity,
                    "description": r.description,
                    "mitigation": r.mitigation,
                }
                for r in self.risks
            ],
            "rationale": self.rationale,
            "strategic_importance": self.strategic_importance.value,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "scores": {
                "build_score": self.build_score,
                "buy_score": self.buy_score,
            },
            "key_factors": self.key_factors,
        }


@dataclass
class ComponentRequirements:
    """Requirements for a component being evaluated."""

    component_name: str
    description: str = ""
    required_features: List[str] = field(default_factory=list)
    nice_to_have_features: List[str] = field(default_factory=list)
    performance_requirements: Dict[str, Any] = field(default_factory=dict)
    security_requirements: List[str] = field(default_factory=list)
    compliance_requirements: List[str] = field(default_factory=list)
    integration_requirements: List[str] = field(default_factory=list)
    strategic_importance: StrategicImportance = StrategicImportance.SUPPORTING
    team_expertise_level: str = "medium"  # "low", "medium", "high"
    time_constraint_weeks: Optional[float] = None
    budget_constraint: Optional[float] = None


@dataclass
class VendorOption:
    """A vendor/SaaS option for buying."""

    name: str
    pricing_model: str  # "subscription", "usage", "one-time", "freemium"
    monthly_cost: float
    initial_cost: float = 0.0
    features: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    lock_in_risk: str = "medium"  # "low", "medium", "high"
    integration_complexity: str = "medium"  # "low", "medium", "high"
    support_quality: str = "medium"  # "low", "medium", "high"
    documentation_quality: str = "medium"  # "low", "medium", "high"


class BuildVsBuyAnalyzer:
    """
    Analyzes build vs. buy decisions for project dependencies.

    Evaluates cost, time, risk, and strategic factors to make
    informed recommendations about whether to build in-house
    or purchase/integrate external solutions.
    """

    # Weights for scoring
    COST_WEIGHT = 0.25
    TIME_WEIGHT = 0.20
    RISK_WEIGHT = 0.20
    FEATURE_FIT_WEIGHT = 0.15
    STRATEGIC_WEIGHT = 0.20

    # Cost assumptions
    DEFAULT_HOURLY_RATE = 75.0
    DEFAULT_MAINTENANCE_RATIO = 0.20  # 20% of initial build cost annually

    # Risk severity scores
    RISK_SCORES = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    def __init__(self, hourly_rate: float = DEFAULT_HOURLY_RATE):
        """Initialize the analyzer with configuration."""
        self.hourly_rate = hourly_rate

    def analyze(
        self,
        requirements: ComponentRequirements,
        vendor_options: Optional[List[VendorOption]] = None,
        build_estimate_hours: Optional[float] = None,
    ) -> BuildVsBuyAnalysis:
        """
        Analyze whether to build or buy a solution.

        Args:
            requirements: Component requirements specification
            vendor_options: Available vendor/SaaS options
            build_estimate_hours: Estimated hours to build in-house

        Returns:
            BuildVsBuyAnalysis with recommendation
        """
        vendor_options = vendor_options or []

        # Estimate build cost and time
        build_hours = build_estimate_hours or self._estimate_build_hours(requirements)
        build_cost = self._calculate_build_cost(build_hours, requirements)
        build_time_weeks = build_hours / 40  # Assuming 40-hour work weeks

        # Estimate buy cost (use best vendor option or defaults)
        buy_cost, buy_time = self._calculate_buy_cost(requirements, vendor_options)

        # Assess risks
        risks = self.risk_assessment(requirements, vendor_options)

        # Calculate scores
        build_score = self._calculate_build_score(build_cost, build_time_weeks, risks, requirements)
        buy_score = self._calculate_buy_score(
            buy_cost, buy_time, risks, requirements, vendor_options
        )

        # Determine recommendation
        recommendation, confidence, key_factors = self._determine_recommendation(
            build_score, buy_score, requirements, risks
        )

        # Generate rationale
        rationale = self._generate_rationale(
            recommendation, build_cost, buy_cost, build_time_weeks, buy_time, key_factors
        )

        return BuildVsBuyAnalysis(
            component=requirements.component_name,
            recommendation=recommendation,
            confidence=confidence,
            build_cost=build_cost,
            buy_cost=buy_cost,
            build_time_weeks=build_time_weeks,
            buy_integration_time_weeks=buy_time,
            risks=risks,
            rationale=rationale,
            strategic_importance=requirements.strategic_importance,
            build_score=build_score,
            buy_score=buy_score,
            key_factors=key_factors,
        )

    def cost_comparison(
        self,
        requirements: ComponentRequirements,
        vendor_options: Optional[List[VendorOption]] = None,
        build_estimate_hours: Optional[float] = None,
        years: int = 5,
    ) -> Dict[str, Any]:
        """
        Perform detailed cost comparison between build and buy options.

        Args:
            requirements: Component requirements
            vendor_options: Available vendor options
            build_estimate_hours: Estimated build hours
            years: Number of years to project

        Returns:
            Detailed cost comparison data
        """
        vendor_options = vendor_options or []
        build_hours = build_estimate_hours or self._estimate_build_hours(requirements)

        build_cost = self._calculate_build_cost(build_hours, requirements)
        buy_cost, _ = self._calculate_buy_cost(requirements, vendor_options)

        # Calculate break-even point
        build_monthly_cost = (
            build_cost.year_1_total - build_cost.initial_cost
        ) / 12 + build_cost.monthly_recurring
        buy_monthly_cost = buy_cost.monthly_recurring

        break_even_months = None
        if buy_monthly_cost > build_monthly_cost:
            cost_diff = buy_monthly_cost - build_monthly_cost
            if cost_diff > 0:
                break_even_months = build_cost.initial_cost / cost_diff

        return {
            "cost_comparison": {
                "build": {
                    "initial": build_cost.initial_cost,
                    "year_1": build_cost.year_1_total,
                    "year_3": build_cost.year_3_total,
                    "year_5": build_cost.year_5_total,
                    "monthly_ongoing": build_cost.monthly_recurring,
                },
                "buy": {
                    "initial": buy_cost.initial_cost,
                    "year_1": buy_cost.year_1_total,
                    "year_3": buy_cost.year_3_total,
                    "year_5": buy_cost.year_5_total,
                    "monthly_ongoing": buy_cost.monthly_recurring,
                },
                "analysis": {
                    "break_even_months": break_even_months,
                    "year_1_savings_build": buy_cost.year_1_total - build_cost.year_1_total,
                    "year_5_savings_build": buy_cost.year_5_total - build_cost.year_5_total,
                    "recommendation": (
                        "BUILD" if build_cost.year_5_total < buy_cost.year_5_total else "BUY"
                    ),
                },
            }
        }

    def risk_assessment(
        self,
        requirements: ComponentRequirements,
        vendor_options: Optional[List[VendorOption]] = None,
    ) -> List[RiskAssessment]:
        """
        Assess risks for both build and buy options.

        Args:
            requirements: Component requirements
            vendor_options: Available vendor options

        Returns:
            List of identified risks
        """
        vendor_options = vendor_options or []
        risks = []

        # Build risks
        if requirements.team_expertise_level == "low":
            risks.append(
                RiskAssessment(
                    category=RiskCategory.TECHNICAL_DEBT,
                    severity="high",
                    description="Low team expertise may result in suboptimal implementation",
                    mitigation="Consider training or hiring before build",
                )
            )

        if requirements.time_constraint_weeks and requirements.time_constraint_weeks < 4:
            risks.append(
                RiskAssessment(
                    category=RiskCategory.TIME_TO_MARKET,
                    severity="high",
                    description="Tight deadline may compromise build quality",
                    mitigation="Consider buying to meet timeline",
                )
            )

        # Maintenance burden risk for builds
        if requirements.strategic_importance == StrategicImportance.COMMODITY:
            risks.append(
                RiskAssessment(
                    category=RiskCategory.MAINTENANCE_BURDEN,
                    severity="medium",
                    description="Building commodity components increases maintenance burden",
                    mitigation="Use well-established external solutions",
                )
            )

        # Buy risks
        for vendor in vendor_options:
            if vendor.lock_in_risk == "high":
                risks.append(
                    RiskAssessment(
                        category=RiskCategory.VENDOR_LOCK_IN,
                        severity="high",
                        description=f"{vendor.name} has high vendor lock-in risk",
                        mitigation="Implement abstraction layer or have migration plan",
                    )
                )

            if vendor.integration_complexity == "high":
                risks.append(
                    RiskAssessment(
                        category=RiskCategory.INTEGRATION,
                        severity="medium",
                        description=f"{vendor.name} has complex integration requirements",
                        mitigation="Allocate additional integration time",
                    )
                )

        # Security and compliance risks
        if requirements.security_requirements:
            if not vendor_options:
                risks.append(
                    RiskAssessment(
                        category=RiskCategory.SECURITY,
                        severity="medium",
                        description="Custom build requires security review and hardening",
                        mitigation="Include security audit in build plan",
                    )
                )
            else:
                risks.append(
                    RiskAssessment(
                        category=RiskCategory.SECURITY,
                        severity="low",
                        description="External vendor handles security updates",
                        mitigation=None,
                    )
                )

        if requirements.compliance_requirements:
            risks.append(
                RiskAssessment(
                    category=RiskCategory.COMPLIANCE,
                    severity="medium",
                    description="Compliance requirements need verification",
                    mitigation="Verify vendor compliance or build with compliance in mind",
                )
            )

        return risks

    def _estimate_build_hours(self, requirements: ComponentRequirements) -> float:
        """Estimate hours required to build component."""
        base_hours = 40  # 1 week minimum

        # Add hours based on feature count
        feature_count = (
            len(requirements.required_features) + len(requirements.nice_to_have_features) * 0.5
        )
        base_hours += feature_count * 8  # 8 hours per feature on average

        # Adjust for complexity
        if requirements.security_requirements:
            base_hours *= 1.3
        if requirements.compliance_requirements:
            base_hours *= 1.2

        # Adjust for team expertise
        expertise_multipliers = {"low": 1.5, "medium": 1.0, "high": 0.8}
        base_hours *= expertise_multipliers.get(requirements.team_expertise_level, 1.0)

        return base_hours

    def _calculate_build_cost(
        self, hours: float, requirements: ComponentRequirements
    ) -> CostEstimate:
        """Calculate build cost estimate."""
        initial_cost = hours * self.hourly_rate
        annual_maintenance = initial_cost * self.DEFAULT_MAINTENANCE_RATIO

        return CostEstimate(
            initial_cost=initial_cost,
            monthly_recurring=annual_maintenance / 12,
            year_1_total=initial_cost + annual_maintenance,
            year_3_total=initial_cost + (annual_maintenance * 3),
            year_5_total=initial_cost + (annual_maintenance * 5),
            cost_drivers=[
                f"Development: {hours} hours @ ${self.hourly_rate}/hr",
                f"Maintenance: {self.DEFAULT_MAINTENANCE_RATIO * 100:.0f}% annually",
            ],
            assumptions=[
                f"Team hourly rate: ${self.hourly_rate}",
                "No major rework required",
                "Standard maintenance effort",
            ],
        )

    def _calculate_buy_cost(
        self,
        requirements: ComponentRequirements,
        vendor_options: List[VendorOption],
    ) -> tuple[CostEstimate, float]:
        """Calculate buy cost estimate and integration time."""
        if vendor_options:
            # Use the best vendor option (lowest total cost)
            best_vendor = min(
                vendor_options,
                key=lambda v: v.initial_cost + (v.monthly_cost * 12),
            )
            monthly = best_vendor.monthly_cost
            initial = best_vendor.initial_cost

            # Estimate integration time
            integration_weeks = {"low": 0.5, "medium": 1.5, "high": 3.0}.get(
                best_vendor.integration_complexity, 1.5
            )
        else:
            # Default estimates if no vendor options provided
            monthly = 100.0  # Conservative estimate
            initial = 0.0
            integration_weeks = 1.0

        integration_cost = integration_weeks * 40 * self.hourly_rate

        return (
            CostEstimate(
                initial_cost=initial + integration_cost,
                monthly_recurring=monthly,
                year_1_total=initial + integration_cost + (monthly * 12),
                year_3_total=initial + integration_cost + (monthly * 36),
                year_5_total=initial + integration_cost + (monthly * 60),
                cost_drivers=[
                    f"Integration: {integration_weeks} weeks",
                    f"Monthly subscription: ${monthly}",
                ],
                assumptions=[
                    "No major price increases",
                    "Feature requirements remain stable",
                ],
            ),
            integration_weeks,
        )

    def _calculate_build_score(
        self,
        build_cost: CostEstimate,
        build_time: float,
        risks: List[RiskAssessment],
        requirements: ComponentRequirements,
    ) -> float:
        """Calculate overall build score (0-100)."""
        score = 50.0  # Base score

        # Cost factor (lower is better, but normalize)
        if build_cost.year_5_total < 50000:
            score += 10
        elif build_cost.year_5_total > 200000:
            score -= 10

        # Time factor
        if requirements.time_constraint_weeks:
            if build_time <= requirements.time_constraint_weeks:
                score += 15
            else:
                score -= 20

        # Strategic importance bonus for build
        if requirements.strategic_importance == StrategicImportance.CORE_DIFFERENTIATOR:
            score += 20

        # Risk penalties
        build_risks = [
            r
            for r in risks
            if r.category
            in [
                RiskCategory.TECHNICAL_DEBT,
                RiskCategory.MAINTENANCE_BURDEN,
                RiskCategory.TIME_TO_MARKET,
            ]
        ]
        for risk in build_risks:
            score -= self.RISK_SCORES.get(risk.severity, 1) * 3

        # Expertise bonus
        if requirements.team_expertise_level == "high":
            score += 10
        elif requirements.team_expertise_level == "low":
            score -= 10

        return max(0, min(100, score))

    def _calculate_buy_score(
        self,
        buy_cost: CostEstimate,
        buy_time: float,
        risks: List[RiskAssessment],
        requirements: ComponentRequirements,
        vendor_options: List[VendorOption],
    ) -> float:
        """Calculate overall buy score (0-100)."""
        score = 50.0  # Base score

        # Cost factor
        if buy_cost.year_5_total < 30000:
            score += 15
        elif buy_cost.year_5_total > 100000:
            score -= 10

        # Time factor (faster is better for buy)
        if requirements.time_constraint_weeks:
            if buy_time <= requirements.time_constraint_weeks * 0.5:
                score += 20
            elif buy_time <= requirements.time_constraint_weeks:
                score += 10

        # Commodity bonus for buy
        if requirements.strategic_importance == StrategicImportance.COMMODITY:
            score += 15

        # Vendor quality bonus
        for vendor in vendor_options:
            if vendor.support_quality == "high":
                score += 5
            if vendor.documentation_quality == "high":
                score += 3

        # Risk penalties
        buy_risks = [
            r
            for r in risks
            if r.category
            in [
                RiskCategory.VENDOR_LOCK_IN,
                RiskCategory.INTEGRATION,
            ]
        ]
        for risk in buy_risks:
            score -= self.RISK_SCORES.get(risk.severity, 1) * 3

        return max(0, min(100, score))

    def _determine_recommendation(
        self,
        build_score: float,
        buy_score: float,
        requirements: ComponentRequirements,
        risks: List[RiskAssessment],
    ) -> tuple[DecisionRecommendation, float, List[str]]:
        """Determine final recommendation based on scores."""
        key_factors = []

        # Calculate score difference
        score_diff = build_score - buy_score

        # Determine recommendation
        if abs(score_diff) < 10:
            # Scores are close - recommend hybrid approach
            recommendation = DecisionRecommendation.HYBRID
            confidence = 0.5
            key_factors.append("Close scores suggest mixed approach")
        elif score_diff > 0:
            recommendation = DecisionRecommendation.BUILD
            confidence = min(0.95, 0.5 + (score_diff / 100))
            if requirements.strategic_importance == StrategicImportance.CORE_DIFFERENTIATOR:
                key_factors.append("Core differentiator - build for competitive advantage")
                confidence = min(0.95, confidence + 0.1)
        else:
            recommendation = DecisionRecommendation.BUY
            confidence = min(0.95, 0.5 + (abs(score_diff) / 100))
            if requirements.strategic_importance == StrategicImportance.COMMODITY:
                key_factors.append("Commodity component - buy to focus resources")
                confidence = min(0.95, confidence + 0.1)

        # Add risk-based factors
        critical_risks = [r for r in risks if r.severity == "critical"]
        if critical_risks:
            key_factors.append(f"Critical risks identified: {len(critical_risks)}")
            confidence = max(0.3, confidence - 0.1)

        # Budget constraint factor
        if requirements.budget_constraint:
            key_factors.append(f"Budget constraint: ${requirements.budget_constraint:,.0f}")

        # Time constraint factor
        if requirements.time_constraint_weeks:
            key_factors.append(f"Time constraint: {requirements.time_constraint_weeks} weeks")

        return recommendation, confidence, key_factors

    def _generate_rationale(
        self,
        recommendation: DecisionRecommendation,
        build_cost: CostEstimate,
        buy_cost: CostEstimate,
        build_time: float,
        buy_time: float,
        key_factors: List[str],
    ) -> str:
        """Generate human-readable rationale for the recommendation."""
        rationale_parts = []

        if recommendation == DecisionRecommendation.BUILD:
            rationale_parts.append(
                f"Building is recommended based on a 5-year TCO of ${build_cost.year_5_total:,.0f} "
                f"vs ${buy_cost.year_5_total:,.0f} for buying."
            )
            if build_time < buy_time * 2:
                rationale_parts.append(f"Development time of {build_time:.1f} weeks is acceptable.")
        elif recommendation == DecisionRecommendation.BUY:
            rationale_parts.append(
                f"Buying is recommended with integration time of {buy_time:.1f} weeks "
                f"and 5-year cost of ${buy_cost.year_5_total:,.0f}."
            )
            if buy_time < build_time:
                rationale_parts.append(f"Faster time-to-value vs {build_time:.1f} weeks to build.")
        else:
            rationale_parts.append(
                "A hybrid approach is recommended, combining external components "
                "with custom integrations for optimal results."
            )

        if key_factors:
            rationale_parts.append("Key factors: " + "; ".join(key_factors[:3]))

        return " ".join(rationale_parts)

    def analyze_multiple(
        self,
        components: List[ComponentRequirements],
        vendor_options_map: Optional[Dict[str, List[VendorOption]]] = None,
    ) -> Dict[str, BuildVsBuyAnalysis]:
        """
        Analyze multiple components for build vs buy decisions.

        Args:
            components: List of component requirements
            vendor_options_map: Mapping of component names to vendor options

        Returns:
            Dictionary mapping component names to analysis results
        """
        vendor_options_map = vendor_options_map or {}
        results = {}

        for req in components:
            vendor_options = vendor_options_map.get(req.component_name, [])
            results[req.component_name] = self.analyze(req, vendor_options)

        return results

    def generate_summary_report(
        self,
        analyses: Dict[str, BuildVsBuyAnalysis],
    ) -> Dict[str, Any]:
        """
        Generate a summary report for multiple component analyses.

        Args:
            analyses: Dictionary of component analyses

        Returns:
            Summary report dictionary
        """
        build_components = [
            name for name, a in analyses.items() if a.recommendation == DecisionRecommendation.BUILD
        ]
        buy_components = [
            name for name, a in analyses.items() if a.recommendation == DecisionRecommendation.BUY
        ]
        hybrid_components = [
            name
            for name, a in analyses.items()
            if a.recommendation == DecisionRecommendation.HYBRID
        ]

        total_build_cost = sum(
            a.build_cost.year_5_total
            for a in analyses.values()
            if a.recommendation == DecisionRecommendation.BUILD
        )
        total_buy_cost = sum(
            a.buy_cost.year_5_total
            for a in analyses.values()
            if a.recommendation == DecisionRecommendation.BUY
        )

        return {
            "build_vs_buy_summary": {
                "analysis_timestamp": datetime.now().isoformat(),
                "total_components": len(analyses),
                "recommendations": {
                    "build": len(build_components),
                    "buy": len(buy_components),
                    "hybrid": len(hybrid_components),
                },
                "build_components": build_components,
                "buy_components": buy_components,
                "hybrid_components": hybrid_components,
                "estimated_5_year_costs": {
                    "build_total": total_build_cost,
                    "buy_total": total_buy_cost,
                    "combined_total": total_build_cost + total_buy_cost,
                },
                "high_risk_items": [
                    {
                        "component": name,
                        "risk": r.description,
                    }
                    for name, a in analyses.items()
                    for r in a.risks
                    if r.severity in ["high", "critical"]
                ],
            }
        }
