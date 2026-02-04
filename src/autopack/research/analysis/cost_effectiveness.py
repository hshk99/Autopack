"""
Cost-Effectiveness Analyzer for Autopack research.

Provides comprehensive cost-effectiveness analysis at the project level,
aggregating component-level build-vs-buy decisions and adding infrastructure,
operational, and scaling cost projections.

Core Principle: Optimize for total value delivered per dollar spent,
not just minimizing costs.
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ValidationError, confloat, validator

logger = logging.getLogger(__name__)


# Pydantic models for cost analysis validation
class CostCategoryModel(BaseModel):
    """Validated cost category breakdown."""

    name: str
    monthly_cost: confloat(ge=0)
    annual_cost: confloat(ge=0)

    @validator("monthly_cost", "annual_cost", pre=False)
    def validate_not_nan(cls, v):
        """Ensure costs are not NaN or Infinity."""
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Cost cannot be NaN or Infinity")
        return v


class CostAnalysisModel(BaseModel):
    """Validated cost analysis output."""

    total_monthly: confloat(ge=0)
    total_annual: confloat(ge=0)
    categories: List[CostCategoryModel]
    currency: str = "USD"

    @validator("total_monthly", "total_annual", pre=False)
    def validate_totals_not_nan(cls, v):
        """Ensure totals are not NaN or Infinity."""
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ValueError("Total cost cannot be NaN or Infinity")
        return v

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class BudgetCostModel(BaseModel):
    """Validated BudgetCost anchor model."""

    pivot_type: str
    budget_constraints: Dict[str, Any]
    cost_breakdown: Dict[str, confloat(ge=0)]
    cost_optimization_strategies: List[str]
    source: str

    @validator("cost_breakdown")
    def validate_breakdown_values(cls, v):
        """Ensure all breakdown values are valid numbers."""
        for key, val in v.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                raise ValueError(f"Cost breakdown value for {key} cannot be NaN or Infinity")
        return v


class CostCategory(Enum):
    """Categories of project costs."""

    DEVELOPMENT = "development"
    INFRASTRUCTURE = "infrastructure"
    SERVICES = "services"
    AI_TOKENS = "ai_tokens"
    OPERATIONAL = "operational"
    HIDDEN = "hidden"


class ScalingModel(Enum):
    """How costs scale with usage/users."""

    FLAT = "flat"  # Fixed cost regardless of users
    LINEAR = "linear"  # Cost grows linearly with users
    STEP_FUNCTION = "step_function"  # Cost jumps at thresholds
    LOGARITHMIC = "logarithmic"  # Cost grows slowly with scale
    EXPONENTIAL = "exponential"  # Cost grows rapidly (avoid these)


class DecisionType(Enum):
    """Build vs Buy vs Integrate decision."""

    BUILD = "build"
    BUY = "buy"
    INTEGRATE = "integrate"
    OUTSOURCE = "outsource"


class VendorLockInLevel(Enum):
    """Level of vendor lock-in risk."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComponentCostData:
    """Cost data for a single component."""

    component: str
    description: str = ""
    decision: DecisionType = DecisionType.BUILD
    service_name: Optional[str] = None

    # Cost breakdown
    initial_cost: float = 0.0
    monthly_ongoing: float = 0.0
    scaling_model: ScalingModel = ScalingModel.FLAT
    scaling_factor: float = 0.0  # Cost per additional user/unit

    # Projections
    year_1_total: float = 0.0
    year_3_total: float = 0.0
    year_5_total: float = 0.0

    # Vendor lock-in
    vendor_lock_in_level: VendorLockInLevel = VendorLockInLevel.LOW
    migration_cost: float = 0.0
    migration_time: str = ""
    alternatives: List[str] = field(default_factory=list)

    # Metadata
    is_core_differentiator: bool = False
    rationale: str = ""

    def calculate_projections(
        self,
        year_1_users: int = 1000,
        year_3_users: int = 10000,
        year_5_users: int = 50000,
    ) -> None:
        """Calculate cost projections based on scaling model."""
        self.year_1_total = self._calculate_year_cost(year_1_users, 12)
        self.year_3_total = self._calculate_year_cost(year_3_users, 36)
        self.year_5_total = self._calculate_year_cost(year_5_users, 60)

    def _calculate_year_cost(self, users: int, months: int) -> float:
        """Calculate total cost for a given user count and months."""
        base = self.initial_cost + (self.monthly_ongoing * months)

        if self.scaling_model == ScalingModel.FLAT:
            return base
        elif self.scaling_model == ScalingModel.LINEAR:
            return base + (self.scaling_factor * users * months)
        elif self.scaling_model == ScalingModel.STEP_FUNCTION:
            # Assume steps at 1k, 10k, 100k users
            steps = 0
            if users > 1000:
                steps += 1
            if users > 10000:
                steps += 1
            if users > 100000:
                steps += 1
            return base + (self.scaling_factor * steps * months)
        elif self.scaling_model == ScalingModel.LOGARITHMIC:
            import math

            return base + (self.scaling_factor * math.log10(max(users, 1)) * months)
        else:
            return base


@dataclass
class AITokenCostProjection:
    """Projection for AI/LLM token costs."""

    feature: str
    model: str
    avg_input_tokens: int
    avg_output_tokens: int
    requests_per_user_monthly: int

    # Pricing (per 1M tokens)
    input_price_per_million: float = 3.0  # Claude Sonnet default
    output_price_per_million: float = 15.0

    @property
    def cost_per_request(self) -> float:
        """Calculate cost per request."""
        input_cost = (self.avg_input_tokens / 1_000_000) * self.input_price_per_million
        output_cost = (self.avg_output_tokens / 1_000_000) * self.output_price_per_million
        return input_cost + output_cost

    def monthly_cost_for_users(self, users: int) -> float:
        """Calculate monthly cost for given user count."""
        return self.cost_per_request * self.requests_per_user_monthly * users


@dataclass
class CostOptimizationStrategy:
    """A cost optimization strategy."""

    strategy: str
    description: str
    potential_savings_percent: float  # 0.0 to 1.0
    implementation_effort: str
    priority: str = "medium"  # low, medium, high


@dataclass
class ProjectCostProjection:
    """Complete project cost projection."""

    project_name: str
    analysis_date: datetime = field(default_factory=datetime.now)
    currency: str = "USD"

    # Component costs
    components: List[ComponentCostData] = field(default_factory=list)

    # AI costs
    ai_features: List[AITokenCostProjection] = field(default_factory=list)

    # User projections
    year_1_users: int = 1000
    year_3_users: int = 10000
    year_5_users: int = 50000

    # Development costs
    mvp_dev_hours: int = 400
    hourly_rate: float = 75.0
    monthly_dev_hours: int = 40

    # Infrastructure baseline
    hosting_monthly: float = 100.0
    database_monthly: float = 50.0
    monitoring_monthly: float = 50.0
    other_infra_monthly: float = 50.0

    # Optimization strategies
    optimizations: List[CostOptimizationStrategy] = field(default_factory=list)

    def calculate_all(self) -> Dict[str, Any]:
        """Calculate complete cost analysis."""
        # Calculate component projections
        for component in self.components:
            component.calculate_projections(
                self.year_1_users,
                self.year_3_users,
                self.year_5_users,
            )

        return {
            "executive_summary": self._executive_summary(),
            "component_analysis": self._component_analysis(),
            "ai_token_projection": self._ai_projection(),
            "infrastructure_projection": self._infrastructure_projection(),
            "development_costs": self._development_costs(),
            "total_cost_of_ownership": self._total_tco(),
            "cost_optimization_roadmap": self._optimization_roadmap(),
            "risk_adjusted_costs": self._risk_adjusted(),
            "break_even_analysis": self._break_even(),
            "vendor_lock_in_assessment": self._vendor_assessment(),
        }

    def _executive_summary(self) -> Dict[str, Any]:
        """Generate executive summary."""
        tco = self._total_tco()

        # Find primary cost drivers
        drivers = []
        if tco["year_1"]["ai_apis"] > tco["year_1"]["total"] * 0.2:
            drivers.append(
                f"AI API usage ({tco['year_1']['ai_apis'] / tco['year_1']['total'] * 100:.0f}%)"
            )
        if tco["year_1"]["development"] > tco["year_1"]["total"] * 0.2:
            drivers.append(
                f"Development ({tco['year_1']['development'] / tco['year_1']['total'] * 100:.0f}%)"
            )

        return {
            "total_year_1_cost": tco["year_1"]["total"],
            "total_year_3_cost": tco["year_3_cumulative"]["total"],
            "total_year_5_cost": tco["year_5_cumulative"]["total"],
            "primary_cost_drivers": drivers,
            "key_recommendations": self._generate_recommendations(),
            "cost_confidence": "medium",
        }

    def _component_analysis(self) -> List[Dict[str, Any]]:
        """Analyze component costs."""
        results = []
        for comp in self.components:
            # Calculate vs-build savings if applicable
            vs_build_savings = 0
            if comp.decision in (DecisionType.BUY, DecisionType.INTEGRATE):
                # Estimate build cost (rough: 2 weeks dev time)
                estimated_build_cost = 80 * self.hourly_rate + (
                    500 * 60
                )  # Initial + 5yr maintenance
                vs_build_savings = estimated_build_cost - comp.year_5_total

            results.append(
                {
                    "component": comp.component,
                    "decision": comp.decision.value,
                    "service": comp.service_name,
                    "year_1_cost": comp.year_1_total,
                    "year_5_cost": comp.year_5_total,
                    "vs_build_savings": vs_build_savings,
                    "rationale": comp.rationale,
                }
            )
        return results

    def _ai_projection(self) -> Dict[str, Any]:
        """Project AI/token costs."""
        if not self.ai_features:
            return {"note": "No AI features defined"}

        projections = {}
        for users, label in [
            (self.year_1_users, "year_1"),
            (self.year_3_users, "year_3"),
            (self.year_5_users, "year_5"),
        ]:
            monthly = sum(f.monthly_cost_for_users(users) for f in self.ai_features)
            projections[label] = {
                "estimated_users": users,
                "monthly_cost": round(monthly, 2),
                "yearly_cost": round(monthly * 12, 2),
            }

        # Optimization potential
        total_savings = sum(
            o.potential_savings_percent
            for o in self.optimizations
            if "cache" in o.strategy.lower() or "model" in o.strategy.lower()
        )
        optimized_year_5 = projections["year_5"]["yearly_cost"] * (1 - min(total_savings, 0.6))

        return {
            "projections": projections,
            "optimization_potential": {
                "with_all_optimizations": f"{total_savings * 100:.0f}% reduction",
                "optimized_year_5": round(optimized_year_5, 2),
            },
        }

    def _infrastructure_projection(self) -> Dict[str, Any]:
        """Project infrastructure costs."""
        monthly_base = (
            self.hosting_monthly
            + self.database_monthly
            + self.monitoring_monthly
            + self.other_infra_monthly
        )

        return {
            "hosting": {
                "monthly": self.hosting_monthly,
                "year_1": self.hosting_monthly * 12,
                "year_5": self.hosting_monthly * 60 * 1.5,  # Assume 50% growth
            },
            "database": {
                "monthly": self.database_monthly,
                "year_1": self.database_monthly * 12,
                "year_5": self.database_monthly * 60 * 2,  # Assume 2x for scale
            },
            "total_monthly_base": monthly_base,
            "year_1_total": monthly_base * 12,
            "year_5_total": monthly_base * 60 * 1.75,
        }

    def _development_costs(self) -> Dict[str, Any]:
        """Calculate development costs."""
        mvp_cost = self.mvp_dev_hours * self.hourly_rate
        monthly_dev_cost = self.monthly_dev_hours * self.hourly_rate

        return {
            "mvp_development": {
                "estimated_hours": self.mvp_dev_hours,
                "cost": mvp_cost,
            },
            "ongoing_development": {
                "monthly_hours": self.monthly_dev_hours,
                "monthly_cost": monthly_dev_cost,
            },
            "year_1_total": mvp_cost + (monthly_dev_cost * 8),  # MVP + 8 months
            "year_5_total": mvp_cost + (monthly_dev_cost * 56),  # MVP + 56 months
        }

    def _total_tco(self) -> Dict[str, Any]:
        """Calculate total cost of ownership."""
        dev = self._development_costs()
        infra = self._infrastructure_projection()
        ai = self._ai_projection()

        services_year_1 = sum(c.year_1_total for c in self.components)
        services_year_5 = sum(c.year_5_total for c in self.components)

        ai_year_1 = ai.get("projections", {}).get("year_1", {}).get("yearly_cost", 0)
        ai_year_5 = ai.get("projections", {}).get("year_5", {}).get("yearly_cost", 0)

        year_1 = {
            "development": dev["year_1_total"],
            "infrastructure": infra["year_1_total"],
            "services": services_year_1,
            "ai_apis": ai_year_1,
            "operational": dev["ongoing_development"]["monthly_cost"] * 12 * 0.2,  # 20% for ops
            "total": 0,
        }
        year_1["total"] = sum(year_1.values())

        year_5 = {
            "development": dev["year_5_total"],
            "infrastructure": infra["year_5_total"],
            "services": services_year_5,
            "ai_apis": ai_year_5 * 3,  # Rough 5-year cumulative
            "operational": dev["ongoing_development"]["monthly_cost"] * 60 * 0.2,
            "total": 0,
        }
        year_5["total"] = sum(year_5.values())

        return {
            "year_1": year_1,
            "year_3_cumulative": {k: v * 2 for k, v in year_1.items()},  # Simplified
            "year_5_cumulative": year_5,
        }

    def _optimization_roadmap(self) -> List[Dict[str, Any]]:
        """Generate cost optimization roadmap."""
        return [
            {
                "phase": "MVP (Month 1-4)",
                "focus": "Speed over cost",
                "actions": [
                    "Use managed services everywhere",
                    "Accept higher per-unit costs for faster launch",
                ],
            },
            {
                "phase": "Growth (Month 5-12)",
                "focus": "Unit economics",
                "actions": [
                    "Implement AI caching",
                    "Optimize prompts",
                    "Monitor cost per user",
                ],
            },
            {
                "phase": "Scale (Year 2+)",
                "focus": "Efficiency at scale",
                "actions": [
                    "Consider self-hosting high-cost components",
                    "Negotiate enterprise API rates",
                    "Build vs buy reassessment",
                ],
            },
        ]

    def _risk_adjusted(self) -> Dict[str, Any]:
        """Calculate risk-adjusted cost scenarios."""
        tco = self._total_tco()
        base = tco["year_5_cumulative"]["total"]

        return {
            "optimistic": {
                "year_5_total": base * 0.75,
                "assumptions": "Strong growth, good optimization, no major pivots",
            },
            "expected": {
                "year_5_total": base,
                "assumptions": "Moderate growth, standard optimization",
            },
            "pessimistic": {
                "year_5_total": base * 1.4,
                "assumptions": "Slower growth, higher AI costs, pivot required",
            },
        }

    def _break_even(self) -> Dict[str, Any]:
        """Calculate break-even analysis."""
        tco = self._total_tco()

        # Assume $29/month subscription
        subscription_price = 29

        return {
            "required_mrr_to_cover_costs": {
                "year_1": tco["year_1"]["total"] / 12,
                "year_5": tco["year_5_cumulative"]["total"] / 60,
            },
            "users_needed_at_29_mo": {
                "year_1": int(tco["year_1"]["total"] / 12 / subscription_price),
                "year_5": int(tco["year_5_cumulative"]["total"] / 60 / subscription_price),
            },
        }

    def _vendor_assessment(self) -> List[Dict[str, Any]]:
        """Assess vendor lock-in risks."""
        return [
            {
                "vendor": comp.service_name or comp.component,
                "component": comp.component,
                "lock_in_level": comp.vendor_lock_in_level.value,
                "migration_cost": comp.migration_cost,
                "migration_time": comp.migration_time,
                "alternatives": comp.alternatives,
            }
            for comp in self.components
            if comp.decision in (DecisionType.BUY, DecisionType.INTEGRATE)
        ]

    def _generate_recommendations(self) -> List[str]:
        """Generate key recommendations."""
        recommendations = []

        # Check for high lock-in components
        high_lock_in = [
            c for c in self.components if c.vendor_lock_in_level == VendorLockInLevel.HIGH
        ]
        if high_lock_in:
            recommendations.append(
                f"Consider alternatives for high lock-in components: {', '.join(c.component for c in high_lock_in)}"
            )

        # Check AI costs
        ai = self._ai_projection()
        if ai.get("projections", {}).get("year_5", {}).get("yearly_cost", 0) > 50000:
            recommendations.append(
                "Implement AI caching and model routing early to control scaling costs"
            )

        # Check for build decisions on non-core
        non_core_builds = [
            c
            for c in self.components
            if c.decision == DecisionType.BUILD and not c.is_core_differentiator
        ]
        if non_core_builds:
            recommendations.append(
                f"Reconsider building non-core components: {', '.join(c.component for c in non_core_builds)}"
            )

        return recommendations


class CostEffectivenessAnalyzer:
    """
    Main analyzer for project cost-effectiveness.

    Aggregates component-level decisions and produces comprehensive
    cost projections with optimization recommendations.
    """

    def __init__(self):
        """Initialize the analyzer."""
        self.projection: Optional[ProjectCostProjection] = None

    def analyze(
        self,
        project_name: str,
        build_vs_buy_results: List[Dict[str, Any]],
        technical_feasibility: Optional[Dict[str, Any]] = None,
        tool_availability: Optional[Dict[str, Any]] = None,
        ai_features: Optional[List[Dict[str, Any]]] = None,
        user_projections: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Perform comprehensive cost-effectiveness analysis.

        Args:
            project_name: Name of the project
            build_vs_buy_results: Component-level build/buy/integrate decisions
            technical_feasibility: Technical feasibility assessment
            tool_availability: Available tools and their pricing
            ai_features: AI feature definitions for token cost projection
            user_projections: User count projections by year

        Returns:
            Complete cost analysis dictionary
        """
        # Set user projections
        users = user_projections or {}
        year_1_users = users.get("year_1", 1000)
        year_3_users = users.get("year_3", 10000)
        year_5_users = users.get("year_5", 50000)

        # Convert build-vs-buy results to ComponentCostData
        components = []
        for result in build_vs_buy_results:
            component = self._parse_component(result)
            if component:
                components.append(component)

        # Convert AI features
        ai_projections = []
        if ai_features:
            for feature in ai_features:
                ai_projections.append(
                    AITokenCostProjection(
                        feature=feature.get("feature", "Unknown"),
                        model=feature.get("model", "claude-sonnet"),
                        avg_input_tokens=feature.get("avg_input_tokens", 500),
                        avg_output_tokens=feature.get("avg_output_tokens", 1000),
                        requests_per_user_monthly=feature.get("requests_per_user_monthly", 20),
                    )
                )

        # Create projection
        self.projection = ProjectCostProjection(
            project_name=project_name,
            components=components,
            ai_features=ai_projections,
            year_1_users=year_1_users,
            year_3_users=year_3_users,
            year_5_users=year_5_users,
        )

        # Add default optimizations
        self.projection.optimizations = [
            CostOptimizationStrategy(
                strategy="Response caching",
                description="Cache AI responses for common queries",
                potential_savings_percent=0.35,
                implementation_effort="1-2 days",
                priority="high",
            ),
            CostOptimizationStrategy(
                strategy="Model tier routing",
                description="Use haiku for simple queries, sonnet for complex",
                potential_savings_percent=0.45,
                implementation_effort="2-3 days",
                priority="high",
            ),
            CostOptimizationStrategy(
                strategy="Prompt optimization",
                description="Reduce token usage through better prompts",
                potential_savings_percent=0.15,
                implementation_effort="ongoing",
                priority="medium",
            ),
        ]

        # Calculate all projections
        return self.projection.calculate_all()

    def _parse_component(self, result: Dict[str, Any]) -> Optional[ComponentCostData]:
        """Parse build-vs-buy result into ComponentCostData."""
        try:
            # Get recommendation
            recommendation = result.get("recommendation", {})
            choice = recommendation.get("choice", "build")
            decision = (
                DecisionType(choice)
                if choice in [d.value for d in DecisionType]
                else DecisionType.BUILD
            )

            # Get cost data
            cost_data = result.get("cost_data", {})
            options = result.get("options", {})

            # Find the selected option's cost data
            if decision == DecisionType.BUY and "buy" in options:
                selected = options["buy"].get("total_cost_estimate", {})
            elif decision == DecisionType.INTEGRATE and "integrate" in options:
                selected = options["integrate"].get("total_cost_estimate", {})
            else:
                selected = options.get("build", {}).get("total_cost_estimate", {})

            # Parse vendor lock-in
            vendor_info = result.get("vendor_lock_in", {})
            lock_in_level = vendor_info.get("level", "low")
            lock_in = (
                VendorLockInLevel(lock_in_level)
                if lock_in_level in [v.value for v in VendorLockInLevel]
                else VendorLockInLevel.LOW
            )

            return ComponentCostData(
                component=result.get("component", "Unknown"),
                description=result.get("description", ""),
                decision=decision,
                service_name=recommendation.get("specific"),
                initial_cost=cost_data.get(
                    "initial_cost", self._parse_cost_string(selected.get("initial", "0"))
                ),
                monthly_ongoing=cost_data.get("monthly_ongoing", 0),
                scaling_model=ScalingModel(cost_data.get("scaling_model", "flat")),
                year_1_total=cost_data.get("year_1_total", 0),
                year_3_total=cost_data.get("year_3_total", 0),
                year_5_total=cost_data.get(
                    "year_5_total", self._parse_cost_string(selected.get("5_year_total", "0"))
                ),
                vendor_lock_in_level=lock_in,
                migration_cost=vendor_info.get("migration_cost", 0),
                migration_time=vendor_info.get("migration_time", ""),
                alternatives=vendor_info.get("alternatives", []),
                is_core_differentiator=result.get("is_core", False),
                rationale=(
                    " ".join(recommendation.get("rationale", []))
                    if isinstance(recommendation.get("rationale"), list)
                    else recommendation.get("rationale", "")
                ),
            )
        except Exception as e:
            logger.warning(f"Error parsing component: {e}")
            return None

    def _parse_cost_string(self, cost_str: str) -> float:
        """Parse cost string like '$5,000-10,000' into a float (average)."""
        if not cost_str:
            return 0.0

        import re

        # Remove currency symbols and commas
        cleaned = re.sub(r"[$,]", "", str(cost_str))

        # Find all numbers
        numbers = re.findall(r"[\d.]+", cleaned)

        if not numbers:
            return 0.0

        # Return average if range, otherwise single value
        values = [float(n) for n in numbers]
        return sum(values) / len(values)

    def _validate_analysis(self, analysis: Dict[str, Any]) -> bool:
        """
        Validate cost analysis with schema checks.

        Args:
            analysis: Cost analysis dictionary

        Raises:
            ValueError: If analysis fails validation

        Returns:
            True if valid
        """
        # Validate total cost of ownership has required numeric fields
        tco = analysis.get("total_cost_of_ownership", {})
        if not tco:
            raise ValueError("Missing total_cost_of_ownership in analysis")

        # Check year 1 costs
        year_1 = tco.get("year_1", {})
        if not year_1 or "total" not in year_1:
            raise ValueError("Missing year_1 total cost")

        # Validate all cost values are positive numbers and not NaN/Infinity
        for year_key in ["year_1", "year_3_cumulative", "year_5_cumulative"]:
            year_data = tco.get(year_key, {})
            for cost_key, cost_val in year_data.items():
                if isinstance(cost_val, (int, float)):
                    if isinstance(cost_val, float) and (
                        math.isnan(cost_val) or math.isinf(cost_val)
                    ):
                        raise ValueError(
                            f"Invalid cost value in {year_key}[{cost_key}]: "
                            f"cannot be NaN or Infinity"
                        )
                    if cost_val < 0:
                        raise ValueError(
                            f"Invalid cost value in {year_key}[{cost_key}]: "
                            f"cannot be negative ({cost_val})"
                        )

        # Validate break-even analysis
        breakeven = analysis.get("break_even_analysis", {})
        if breakeven:
            mrr = breakeven.get("required_mrr_to_cover_costs", {})
            for year_key, mrr_val in mrr.items():
                if isinstance(mrr_val, float) and (math.isnan(mrr_val) or math.isinf(mrr_val)):
                    raise ValueError(f"Invalid MRR value for {year_key}: cannot be NaN or Infinity")

        # Validate AI token projections
        ai_proj = analysis.get("ai_token_projection", {})
        projections = ai_proj.get("projections", {})
        for year_key, proj_data in projections.items():
            for cost_key in ["monthly_cost", "yearly_cost"]:
                cost_val = proj_data.get(cost_key)
                if isinstance(cost_val, float) and (math.isnan(cost_val) or math.isinf(cost_val)):
                    raise ValueError(
                        f"Invalid AI projection {year_key}[{cost_key}]: cannot be NaN or Infinity"
                    )

        logger.info("Cost analysis validation passed")
        return True

    def to_json(self, filepath: str) -> None:
        """
        Save analysis to JSON file with validation.

        Args:
            filepath: Path to save JSON file

        Raises:
            ValueError: If analysis fails validation
        """
        if not self.projection:
            raise ValueError("No projection data available to save")

        analysis = self.projection.calculate_all()

        try:
            # Validate analysis before saving
            self._validate_analysis(analysis)

            # Write to temp file first for atomic operation
            import os
            import tempfile

            filepath_obj = Path(filepath)
            fd, temp_path = tempfile.mkstemp(
                dir=filepath_obj.parent,
                prefix=f".{filepath_obj.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(analysis, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())  # Ensure data is on disk
                # Atomic replace
                os.replace(temp_path, filepath)
                logger.info(f"Cost analysis saved to {filepath}")
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
        except ValueError as e:
            logger.error(f"Cost analysis validation failed: {e}")
            raise

    def generate_budget_anchor(self) -> Dict[str, Any]:
        """
        Generate BudgetCost anchor for Autopack with schema validation.

        Returns:
            Validated BudgetCost anchor dictionary

        Raises:
            ValueError: If anchor data fails validation
        """
        if not self.projection:
            raise ValueError("No projection data available to generate anchor")

        analysis = self.projection.calculate_all()
        tco = analysis["total_cost_of_ownership"]

        # Build the anchor data
        anchor_data = {
            "pivot_type": "BudgetCost",
            "budget_constraints": {
                "total_mvp_budget": tco["year_1"]["total"],
                "monthly_runway": tco["year_1"]["total"] / 12,
                "timeline_months": 6,
                "buffer_percent": 20,
            },
            "cost_breakdown": {
                "development": tco["year_1"]["development"],
                "infrastructure": tco["year_1"]["infrastructure"],
                "services": tco["year_1"]["services"],
                "ai_apis": tco["year_1"]["ai_apis"],
                "operational": tco["year_1"]["operational"],
            },
            "cost_optimization_strategies": [o.strategy for o in self.projection.optimizations],
            "source": "cost-effectiveness-analyzer",
        }

        # Validate the budget cost breakdown
        try:
            validated = BudgetCostModel(**anchor_data)
            logger.info("BudgetCost anchor validation passed")
            return validated.dict()
        except ValidationError as e:
            logger.error(f"BudgetCost anchor validation failed: {e}")
            raise ValueError(f"Invalid BudgetCost anchor: {e}")
