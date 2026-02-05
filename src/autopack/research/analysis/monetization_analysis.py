"""
Monetization Analysis Module for Autopack research.

Provides comprehensive monetization analysis for different project types
(e-commerce, SaaS, content, subscription). Generates recommendations for
pricing strategies, subscription tiers, and revenue potential.

Integrates with budget enforcement to skip expensive analysis when budget is low.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from autopack.research.idea_parser import ProjectType


class MonetizationModel(Enum):
    """Available monetization models."""

    SUBSCRIPTION = "subscription"
    FREEMIUM = "freemium"
    USAGE_BASED = "usage_based"
    ONE_TIME_PURCHASE = "one_time_purchase"
    MARKETPLACE_COMMISSION = "marketplace_commission"
    ADVERTISING = "advertising"
    AFFILIATE = "affiliate"
    LICENSING = "licensing"
    TIERED_PRICING = "tiered_pricing"
    HYBRID = "hybrid"


class PricingStrategy(Enum):
    """Pricing strategy approaches."""

    VALUE_BASED = "value_based"
    COST_PLUS = "cost_plus"
    COMPETITIVE = "competitive"
    PENETRATION = "penetration"
    PREMIUM = "premium"
    DYNAMIC = "dynamic"
    FREEMIUM_UPSELL = "freemium_upsell"


class RevenueConfidence(Enum):
    """Confidence level in revenue projections."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    SPECULATIVE = "speculative"


@dataclass
class PricingTier:
    """A single pricing tier definition."""

    name: str
    price_monthly: float
    price_yearly: Optional[float] = None
    features: List[str] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)
    target_audience: str = ""
    recommended: bool = False

    @property
    def yearly_discount_percent(self) -> float:
        """Calculate yearly discount percentage."""
        if not self.price_yearly or not self.price_monthly:
            return 0.0
        expected_yearly = self.price_monthly * 12
        if expected_yearly == 0:
            return 0.0
        return ((expected_yearly - self.price_yearly) / expected_yearly) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "price_monthly": self.price_monthly,
            "price_yearly": self.price_yearly,
            "yearly_discount_percent": round(self.yearly_discount_percent, 1),
            "features": self.features,
            "limits": self.limits,
            "target_audience": self.target_audience,
            "recommended": self.recommended,
        }


@dataclass
class RevenueProjection:
    """Revenue projection for a specific timeframe."""

    timeframe: str  # e.g., "month_6", "year_1", "year_3"
    users: int
    paying_users: int
    mrr: float  # Monthly Recurring Revenue
    arr: float  # Annual Recurring Revenue
    assumptions: List[str] = field(default_factory=list)
    confidence: RevenueConfidence = RevenueConfidence.MEDIUM

    @property
    def conversion_rate(self) -> float:
        """Calculate conversion rate."""
        if self.users == 0:
            return 0.0
        return (self.paying_users / self.users) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeframe": self.timeframe,
            "users": self.users,
            "paying_users": self.paying_users,
            "conversion_rate_percent": round(self.conversion_rate, 2),
            "mrr": round(self.mrr, 2),
            "arr": round(self.arr, 2),
            "assumptions": self.assumptions,
            "confidence": self.confidence.value,
        }


@dataclass
class MonetizationModelFit:
    """Fit score for a monetization model."""

    model: MonetizationModel
    fit_score: float  # 0-10
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    recommended_for: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model": self.model.value,
            "fit_score": self.fit_score,
            "pros": self.pros,
            "cons": self.cons,
            "requirements": self.requirements,
            "recommended_for": self.recommended_for,
        }


@dataclass
class CompetitorPricing:
    """Competitor pricing data."""

    competitor_name: str
    pricing_model: str
    price_range: str
    key_features: List[str] = field(default_factory=list)
    market_position: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "competitor": self.competitor_name,
            "model": self.pricing_model,
            "price_range": self.price_range,
            "key_features": self.key_features,
            "market_position": self.market_position,
            "source": self.source,
        }


@dataclass
class MonetizationAnalysisResult:
    """Complete monetization analysis result."""

    project_type: ProjectType
    analysis_date: datetime = field(default_factory=datetime.now)

    # Model recommendations
    recommended_model: MonetizationModel = MonetizationModel.SUBSCRIPTION
    model_fits: List[MonetizationModelFit] = field(default_factory=list)

    # Pricing strategy
    pricing_strategy: PricingStrategy = PricingStrategy.VALUE_BASED
    pricing_rationale: str = ""

    # Pricing tiers
    pricing_tiers: List[PricingTier] = field(default_factory=list)

    # Revenue projections
    revenue_projections: List[RevenueProjection] = field(default_factory=list)

    # Competitive analysis
    competitor_pricing: List[CompetitorPricing] = field(default_factory=list)
    market_positioning: str = ""

    # Key metrics
    target_arpu: float = 0.0  # Average Revenue Per User
    target_ltv: float = 0.0  # Lifetime Value
    target_cac_ratio: float = 3.0  # LTV:CAC ratio target

    # Confidence and assumptions
    confidence: RevenueConfidence = RevenueConfidence.MEDIUM
    key_assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    # Analysis metadata
    analysis_cost: float = 0.0  # Cost of running this analysis

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "project_type": self.project_type.value,
            "analysis_date": self.analysis_date.isoformat(),
            "recommended_model": self.recommended_model.value,
            "model_fits": [m.to_dict() for m in self.model_fits],
            "pricing_strategy": self.pricing_strategy.value,
            "pricing_rationale": self.pricing_rationale,
            "pricing_tiers": [t.to_dict() for t in self.pricing_tiers],
            "revenue_projections": [p.to_dict() for p in self.revenue_projections],
            "competitor_pricing": [c.to_dict() for c in self.competitor_pricing],
            "market_positioning": self.market_positioning,
            "target_arpu": self.target_arpu,
            "target_ltv": self.target_ltv,
            "target_cac_ratio": self.target_cac_ratio,
            "confidence": self.confidence.value,
            "key_assumptions": self.key_assumptions,
            "risks": self.risks,
            "analysis_cost": self.analysis_cost,
        }


class MonetizationAnalyzer:
    """
    Analyzes project monetization opportunities.

    Determines suitable monetization models based on project type and scope,
    generates pricing recommendations, and projects revenue potential.
    Integrates with budget enforcement to control analysis costs.
    """

    # Default cost for monetization analysis
    DEFAULT_ANALYSIS_COST = 75.0

    # Model recommendations by project type
    PROJECT_MODEL_RECOMMENDATIONS: Dict[ProjectType, List[Tuple[MonetizationModel, float]]] = {
        ProjectType.ECOMMERCE: [
            (MonetizationModel.MARKETPLACE_COMMISSION, 8.0),
            (MonetizationModel.ONE_TIME_PURCHASE, 7.5),
            (MonetizationModel.SUBSCRIPTION, 6.0),
            (MonetizationModel.AFFILIATE, 5.0),
        ],
        ProjectType.CONTENT: [
            (MonetizationModel.SUBSCRIPTION, 8.0),
            (MonetizationModel.ADVERTISING, 7.0),
            (MonetizationModel.FREEMIUM, 7.5),
            (MonetizationModel.ONE_TIME_PURCHASE, 5.0),
        ],
        ProjectType.TRADING: [
            (MonetizationModel.SUBSCRIPTION, 9.0),
            (MonetizationModel.USAGE_BASED, 8.0),
            (MonetizationModel.TIERED_PRICING, 7.5),
        ],
        ProjectType.AUTOMATION: [
            (MonetizationModel.SUBSCRIPTION, 8.0),
            (MonetizationModel.USAGE_BASED, 7.0),
            (MonetizationModel.ONE_TIME_PURCHASE, 6.0),
            (MonetizationModel.LICENSING, 6.5),
        ],
        ProjectType.OTHER: [
            (MonetizationModel.SUBSCRIPTION, 8.0),
            (MonetizationModel.ONE_TIME_PURCHASE, 7.0),
            (MonetizationModel.FREEMIUM, 6.0),
        ],
    }

    # Pricing benchmarks by model
    PRICING_BENCHMARKS: Dict[MonetizationModel, Dict[str, Any]] = {
        MonetizationModel.SUBSCRIPTION: {
            "starter_range": (9, 29),
            "pro_range": (29, 99),
            "enterprise_range": (99, 499),
            "typical_conversion": 0.03,  # 3% free to paid
        },
        MonetizationModel.FREEMIUM: {
            "conversion_rate_range": (0.01, 0.10),
            "typical_conversion": 0.025,
        },
        MonetizationModel.USAGE_BASED: {
            "typical_markup": 2.5,  # 2.5x cost
            "volume_discount_range": (0.10, 0.40),
        },
        MonetizationModel.MARKETPLACE_COMMISSION: {
            "commission_range": (0.05, 0.20),
            "typical_commission": 0.10,
        },
    }

    def __init__(self, budget_enforcer: Optional[Any] = None):
        """
        Initialize the monetization analyzer.

        Args:
            budget_enforcer: Optional BudgetEnforcer for cost control
        """
        self._budget_enforcer = budget_enforcer
        self._analysis_result: Optional[MonetizationAnalysisResult] = None

    def can_analyze(self) -> bool:
        """
        Check if analysis can proceed based on budget.

        Returns:
            True if budget allows analysis, False otherwise
        """
        if not self._budget_enforcer:
            return True

        return self._budget_enforcer.can_proceed("monetization_analysis")

    def analyze(
        self,
        project_type: Optional[ProjectType] = None,
        project_characteristics: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        competitive_data: Optional[Dict[str, Any]] = None,
        target_audience: Optional[Dict[str, Any]] = None,
        cost_structure: Optional[Dict[str, Any]] = None,
    ) -> MonetizationAnalysisResult:
        """
        Perform comprehensive monetization analysis.

        Args:
            project_type: Type of project being analyzed
            project_characteristics: Project features and capabilities
            market_data: Market size and trends data
            competitive_data: Competitor pricing and positioning
            target_audience: Target customer segment data
            cost_structure: Cost structure for pricing decisions

        Returns:
            MonetizationAnalysisResult with recommendations
        """
        logger.info("Starting monetization analysis")

        # Check budget before proceeding
        if self._budget_enforcer:
            if not self.can_analyze():
                logger.warning("Budget insufficient for monetization analysis")
                return self._create_minimal_result(project_type)
            self._budget_enforcer.start_phase("monetization_analysis")

        # Detect project type if not provided
        if project_type is None:
            project_type = self._detect_project_type(project_characteristics or {})

        # Create result object
        result = MonetizationAnalysisResult(project_type=project_type)

        # Analyze model fit
        result.model_fits = self._analyze_model_fits(project_type, project_characteristics or {})

        # Determine recommended model
        result.recommended_model = self._determine_recommended_model(result.model_fits)

        # Determine pricing strategy
        result.pricing_strategy, result.pricing_rationale = self._determine_pricing_strategy(
            project_type, market_data or {}, competitive_data or {}
        )

        # Generate pricing tiers
        result.pricing_tiers = self._generate_pricing_tiers(
            result.recommended_model,
            result.pricing_strategy,
            cost_structure or {},
            target_audience or {},
        )

        # Analyze competitor pricing
        if competitive_data:
            result.competitor_pricing = self._analyze_competitor_pricing(competitive_data)
            result.market_positioning = self._determine_market_positioning(
                result.pricing_tiers, result.competitor_pricing
            )

        # Generate revenue projections
        result.revenue_projections = self._generate_revenue_projections(
            result.recommended_model,
            result.pricing_tiers,
            market_data or {},
            target_audience or {},
        )

        # Calculate key metrics
        result.target_arpu = self._calculate_target_arpu(result.pricing_tiers)
        result.target_ltv = self._calculate_target_ltv(result.target_arpu, result.recommended_model)

        # Assess confidence
        result.confidence = self._assess_confidence(market_data, competitive_data, target_audience)

        # Identify assumptions and risks
        result.key_assumptions = self._identify_assumptions(
            result.recommended_model, result.pricing_strategy
        )
        result.risks = self._identify_risks(
            result.recommended_model, project_type, competitive_data
        )

        # Record analysis cost
        result.analysis_cost = self.DEFAULT_ANALYSIS_COST
        if self._budget_enforcer:
            self._budget_enforcer.complete_phase("monetization_analysis", result.analysis_cost)

        self._analysis_result = result
        logger.info(
            f"Monetization analysis complete: {result.recommended_model.value} "
            f"with {len(result.pricing_tiers)} tiers"
        )

        return result

    def _create_minimal_result(
        self, project_type: Optional[ProjectType]
    ) -> MonetizationAnalysisResult:
        """Create minimal result when budget is insufficient."""
        return MonetizationAnalysisResult(
            project_type=project_type or ProjectType.OTHER,
            confidence=RevenueConfidence.SPECULATIVE,
            key_assumptions=["Analysis limited due to budget constraints"],
            risks=["Full monetization analysis not performed"],
        )

    def _detect_project_type(self, characteristics: Dict[str, Any]) -> ProjectType:
        """Detect project type from characteristics."""
        keywords = characteristics.get("keywords", [])
        features = characteristics.get("features", [])
        description = characteristics.get("description", "").lower()

        all_text = " ".join(keywords + features) + " " + description

        # Detection rules - map to bootstrap phase ProjectType values
        if any(term in all_text for term in ["shop", "store", "cart", "checkout", "product", "marketplace"]):
            return ProjectType.ECOMMERCE
        elif any(term in all_text for term in ["content", "blog", "article", "media", "news", "video", "creator"]):
            return ProjectType.CONTENT
        elif any(term in all_text for term in ["trade", "trading", "crypto", "stock", "forex", "investment"]):
            return ProjectType.TRADING
        elif any(term in all_text for term in ["api", "sdk", "automation", "workflow", "bot", "tool", "saas"]):
            return ProjectType.AUTOMATION
        else:
            return ProjectType.OTHER

    def _analyze_model_fits(
        self,
        project_type: ProjectType,
        characteristics: Dict[str, Any],
    ) -> List[MonetizationModelFit]:
        """Analyze fit for each monetization model."""
        model_fits = []

        recommendations = self.PROJECT_MODEL_RECOMMENDATIONS.get(
            project_type, self.PROJECT_MODEL_RECOMMENDATIONS[ProjectType.ECOMMERCE]
        )

        for model, base_score in recommendations:
            fit = MonetizationModelFit(
                model=model,
                fit_score=base_score,
                pros=self._get_model_pros(model),
                cons=self._get_model_cons(model),
                requirements=self._get_model_requirements(model),
                recommended_for=self._get_model_recommended_for(model),
            )

            # Adjust score based on characteristics
            fit.fit_score = self._adjust_fit_score(fit, characteristics)

            model_fits.append(fit)

        # Sort by fit score
        model_fits.sort(key=lambda x: x.fit_score, reverse=True)

        return model_fits

    def _get_model_pros(self, model: MonetizationModel) -> List[str]:
        """Get pros for a monetization model."""
        pros_map = {
            MonetizationModel.SUBSCRIPTION: [
                "Predictable recurring revenue",
                "Higher customer lifetime value",
                "Easier financial planning",
                "Continuous customer relationship",
            ],
            MonetizationModel.FREEMIUM: [
                "Lower barrier to entry",
                "Viral growth potential",
                "Large user base for upselling",
                "Market validation at scale",
            ],
            MonetizationModel.USAGE_BASED: [
                "Revenue scales with value delivered",
                "Lower entry price point",
                "Fair pricing for varying usage",
                "Grows with customer success",
            ],
            MonetizationModel.ONE_TIME_PURCHASE: [
                "Simple transaction model",
                "No recurring billing complexity",
                "Immediate revenue recognition",
                "Works for discrete products",
            ],
            MonetizationModel.MARKETPLACE_COMMISSION: [
                "Revenue grows with platform GMV",
                "Low cost to scale",
                "Network effects benefit",
                "Value aligned with transaction success",
            ],
            MonetizationModel.ADVERTISING: [
                "Free for users",
                "Scales with traffic",
                "Multiple revenue streams",
                "Works for content platforms",
            ],
            MonetizationModel.TIERED_PRICING: [
                "Serves multiple segments",
                "Upsell opportunities",
                "Price discrimination",
                "Clear upgrade path",
            ],
        }
        return pros_map.get(model, ["Flexible revenue model"])

    def _get_model_cons(self, model: MonetizationModel) -> List[str]:
        """Get cons for a monetization model."""
        cons_map = {
            MonetizationModel.SUBSCRIPTION: [
                "Churn impacts revenue",
                "Requires continuous value delivery",
                "Billing complexity",
                "Longer time to profitability",
            ],
            MonetizationModel.FREEMIUM: [
                "Low conversion rates (typically 2-5%)",
                "High infrastructure costs for free users",
                "Feature gating complexity",
                "May undervalue product",
            ],
            MonetizationModel.USAGE_BASED: [
                "Revenue unpredictability",
                "Complex metering requirements",
                "May discourage usage",
                "Harder to forecast",
            ],
            MonetizationModel.ONE_TIME_PURCHASE: [
                "No recurring revenue",
                "Constant new customer acquisition",
                "Lower lifetime value",
                "Limited upsell opportunities",
            ],
            MonetizationModel.MARKETPLACE_COMMISSION: [
                "Requires liquidity on both sides",
                "Cold start problem",
                "Price pressure from competition",
                "Payment processing complexity",
            ],
            MonetizationModel.ADVERTISING: [
                "Privacy concerns",
                "User experience impact",
                "CPM rate fluctuations",
                "Requires massive scale",
            ],
            MonetizationModel.TIERED_PRICING: [
                "Complexity in pricing communication",
                "Feature allocation decisions",
                "Customer confusion risk",
                "Support cost scaling",
            ],
        }
        return cons_map.get(model, ["Model-specific challenges"])

    def _get_model_requirements(self, model: MonetizationModel) -> List[str]:
        """Get requirements for a monetization model."""
        requirements_map = {
            MonetizationModel.SUBSCRIPTION: [
                "Recurring value delivery",
                "Billing infrastructure",
                "Churn management system",
            ],
            MonetizationModel.FREEMIUM: [
                "Clear free/paid feature split",
                "High volume infrastructure",
                "Upsell mechanisms",
            ],
            MonetizationModel.USAGE_BASED: [
                "Accurate metering system",
                "Usage dashboard",
                "Cost calculation transparency",
            ],
            MonetizationModel.MARKETPLACE_COMMISSION: [
                "Payment processing",
                "Trust and safety systems",
                "Dispute resolution",
            ],
        }
        return requirements_map.get(model, [])

    def _get_model_recommended_for(self, model: MonetizationModel) -> List[str]:
        """Get recommended use cases for a model."""
        recommended_map = {
            MonetizationModel.SUBSCRIPTION: [
                "B2B SaaS products",
                "Productivity tools",
                "Continuous service delivery",
            ],
            MonetizationModel.FREEMIUM: [
                "Consumer apps",
                "Products with network effects",
                "Low marginal cost services",
            ],
            MonetizationModel.USAGE_BASED: [
                "API services",
                "AI/ML products",
                "Infrastructure services",
            ],
            MonetizationModel.MARKETPLACE_COMMISSION: [
                "Two-sided marketplaces",
                "Service platforms",
                "E-commerce aggregators",
            ],
        }
        return recommended_map.get(model, [])

    def _adjust_fit_score(
        self, fit: MonetizationModelFit, characteristics: Dict[str, Any]
    ) -> float:
        """Adjust fit score based on project characteristics."""
        score = fit.fit_score

        # Adjust based on characteristics
        has_api = characteristics.get("has_api", False)
        has_free_tier = characteristics.get("has_free_tier", False)
        is_b2b = characteristics.get("is_b2b", False)
        has_variable_usage = characteristics.get("has_variable_usage", False)

        if fit.model == MonetizationModel.USAGE_BASED and has_api:
            score += 1.0
        if fit.model == MonetizationModel.FREEMIUM and has_free_tier:
            score += 0.5
        if fit.model == MonetizationModel.SUBSCRIPTION and is_b2b:
            score += 0.5
        if fit.model == MonetizationModel.USAGE_BASED and has_variable_usage:
            score += 0.5

        return min(score, 10.0)  # Cap at 10

    def _determine_recommended_model(
        self, model_fits: List[MonetizationModelFit]
    ) -> MonetizationModel:
        """Determine the recommended monetization model."""
        if not model_fits:
            return MonetizationModel.SUBSCRIPTION

        return model_fits[0].model

    def _determine_pricing_strategy(
        self,
        project_type: ProjectType,
        market_data: Dict[str, Any],
        competitive_data: Dict[str, Any],
    ) -> Tuple[PricingStrategy, str]:
        """Determine pricing strategy and rationale."""
        # Default strategies by project type
        default_strategies = {
            ProjectType.ECOMMERCE: (
                PricingStrategy.COMPETITIVE,
                "E-commerce requires competitive pricing to win in comparison shopping",
            ),
            ProjectType.CONTENT: (
                PricingStrategy.FREEMIUM_UPSELL,
                "Content platforms succeed with freemium models that convert engaged users",
            ),
            ProjectType.AUTOMATION: (
                PricingStrategy.VALUE_BASED,
                "Automation and SaaS tools benefit from value-based pricing",
            ),
            ProjectType.TRADING: (
                PricingStrategy.VALUE_BASED,
                "Trading tools benefit from value-based pricing tied to trading volume",
            ),
        }

        strategy, rationale = default_strategies.get(
            project_type,
            (PricingStrategy.VALUE_BASED, "Value-based pricing maximizes revenue potential"),
        )

        # Adjust based on competitive data
        competitor_count = len(competitive_data.get("competitors", []))
        if competitor_count > 5:
            strategy = PricingStrategy.COMPETITIVE
            rationale = "Crowded market requires competitive positioning"
        elif competitor_count == 0:
            strategy = PricingStrategy.VALUE_BASED
            rationale = "No direct competitors allows premium value-based pricing"

        return strategy, rationale

    def _generate_pricing_tiers(
        self,
        model: MonetizationModel,
        strategy: PricingStrategy,
        cost_structure: Dict[str, Any],
        target_audience: Dict[str, Any],
    ) -> List[PricingTier]:
        """Generate pricing tier recommendations."""
        tiers = []

        # Get benchmarks
        benchmarks = self.PRICING_BENCHMARKS.get(model, {})

        if model in (MonetizationModel.SUBSCRIPTION, MonetizationModel.TIERED_PRICING):
            # Generate standard 3-tier SaaS pricing
            starter_range = benchmarks.get("starter_range", (9, 29))
            pro_range = benchmarks.get("pro_range", (29, 99))
            enterprise_range = benchmarks.get("enterprise_range", (99, 499))

            # Starter tier
            starter_price = (starter_range[0] + starter_range[1]) / 2
            tiers.append(
                PricingTier(
                    name="Starter",
                    price_monthly=starter_price,
                    price_yearly=starter_price * 10,  # 2 months free
                    features=[
                        "Core features",
                        "Email support",
                        "Basic analytics",
                    ],
                    limits={"users": 1, "projects": 3},
                    target_audience="Individual users and small projects",
                )
            )

            # Pro tier (recommended)
            pro_price = (pro_range[0] + pro_range[1]) / 2
            tiers.append(
                PricingTier(
                    name="Pro",
                    price_monthly=pro_price,
                    price_yearly=pro_price * 10,
                    features=[
                        "All Starter features",
                        "Advanced features",
                        "Priority support",
                        "Team collaboration",
                        "Advanced analytics",
                    ],
                    limits={"users": 5, "projects": 10},
                    target_audience="Growing teams and businesses",
                    recommended=True,
                )
            )

            # Enterprise tier
            enterprise_price = (enterprise_range[0] + enterprise_range[1]) / 2
            tiers.append(
                PricingTier(
                    name="Enterprise",
                    price_monthly=enterprise_price,
                    price_yearly=enterprise_price * 10,
                    features=[
                        "All Pro features",
                        "Custom integrations",
                        "Dedicated support",
                        "SLA guarantees",
                        "Admin controls",
                        "SSO/SAML",
                    ],
                    limits={"users": "Unlimited", "projects": "Unlimited"},
                    target_audience="Large organizations with enterprise needs",
                )
            )

        elif model == MonetizationModel.FREEMIUM:
            # Free + Premium tiers
            tiers.append(
                PricingTier(
                    name="Free",
                    price_monthly=0,
                    features=["Basic features", "Community support", "Limited usage"],
                    limits={"usage": "1000/month"},
                    target_audience="Users exploring the product",
                )
            )

            tiers.append(
                PricingTier(
                    name="Premium",
                    price_monthly=29,
                    price_yearly=290,
                    features=[
                        "All features unlocked",
                        "Priority support",
                        "No usage limits",
                        "Advanced features",
                    ],
                    limits={"usage": "Unlimited"},
                    target_audience="Power users and professionals",
                    recommended=True,
                )
            )

        elif model == MonetizationModel.USAGE_BASED:
            # Usage-based tiers
            tiers.append(
                PricingTier(
                    name="Pay as you go",
                    price_monthly=0,
                    features=[
                        "Pay only for what you use",
                        "No minimum commitment",
                        "Standard support",
                    ],
                    limits={"rate": "$0.01 per request"},
                    target_audience="Variable or unpredictable usage",
                )
            )

            tiers.append(
                PricingTier(
                    name="Volume",
                    price_monthly=99,
                    features=[
                        "Included usage quota",
                        "Discounted overage",
                        "Priority support",
                    ],
                    limits={"included": "10,000 requests", "overage": "$0.005 per request"},
                    target_audience="Consistent, predictable usage",
                    recommended=True,
                )
            )

        return tiers

    def _analyze_competitor_pricing(
        self, competitive_data: Dict[str, Any]
    ) -> List[CompetitorPricing]:
        """Analyze competitor pricing from competitive data."""
        competitors = []

        for comp in competitive_data.get("competitors", []):
            competitors.append(
                CompetitorPricing(
                    competitor_name=comp.get("name", "Unknown"),
                    pricing_model=comp.get("pricing_model", "Unknown"),
                    price_range=comp.get("price_range", "Unknown"),
                    key_features=comp.get("key_features", []),
                    market_position=comp.get("market_position", ""),
                    source=comp.get("source", ""),
                )
            )

        return competitors

    def _determine_market_positioning(
        self,
        pricing_tiers: List[PricingTier],
        competitor_pricing: List[CompetitorPricing],
    ) -> str:
        """Determine market positioning based on pricing."""
        if not pricing_tiers:
            return "Unable to determine positioning"

        # Get average price from our tiers
        avg_price = sum(t.price_monthly for t in pricing_tiers if t.price_monthly > 0)
        if avg_price == 0:
            return "Freemium positioning with premium upsell"

        avg_price = avg_price / len([t for t in pricing_tiers if t.price_monthly > 0])

        # Compare to competitors (simplified)
        if not competitor_pricing:
            return f"Market entry at ${avg_price:.0f}/month average"

        return f"Competitive positioning at ${avg_price:.0f}/month with differentiated features"

    def _generate_revenue_projections(
        self,
        model: MonetizationModel,
        pricing_tiers: List[PricingTier],
        market_data: Dict[str, Any],
        target_audience: Dict[str, Any],
    ) -> List[RevenueProjection]:
        """Generate revenue projections."""
        projections = []

        # Get benchmark conversion rate
        benchmarks = self.PRICING_BENCHMARKS.get(model, {})
        conversion_rate = benchmarks.get("typical_conversion", 0.03)

        # Calculate average paying user value (weighted by tier popularity)
        if pricing_tiers:
            paying_tiers = [t for t in pricing_tiers if t.price_monthly > 0]
            if paying_tiers:
                # Assume 60% Starter, 30% Pro, 10% Enterprise distribution
                weights = [0.6, 0.3, 0.1][: len(paying_tiers)]
                weights = weights + [0.0] * (len(paying_tiers) - len(weights))
                arpu = sum(t.price_monthly * w for t, w in zip(paying_tiers, weights))
            else:
                arpu = 0
        else:
            arpu = 29  # Default

        # Generate projections for different timeframes
        timeframes = [
            ("month_6", 1000, "Early traction phase"),
            ("year_1", 5000, "Growth phase"),
            ("year_3", 25000, "Scaling phase"),
        ]

        for timeframe, users, phase in timeframes:
            paying_users = int(users * conversion_rate)
            mrr = paying_users * arpu

            projections.append(
                RevenueProjection(
                    timeframe=timeframe,
                    users=users,
                    paying_users=paying_users,
                    mrr=mrr,
                    arr=mrr * 12,
                    assumptions=[
                        f"Total users: {users}",
                        f"Conversion rate: {conversion_rate * 100:.1f}%",
                        f"ARPU: ${arpu:.0f}/month",
                        phase,
                    ],
                    confidence=RevenueConfidence.MEDIUM,
                )
            )

        return projections

    def _calculate_target_arpu(self, pricing_tiers: List[PricingTier]) -> float:
        """Calculate target Average Revenue Per User."""
        if not pricing_tiers:
            return 0.0

        paying_tiers = [t for t in pricing_tiers if t.price_monthly > 0]
        if not paying_tiers:
            return 0.0

        # Weighted average (assume most users on lowest tier)
        weights = [0.6, 0.3, 0.1][: len(paying_tiers)]
        weights = weights + [0.0] * (len(paying_tiers) - len(weights))

        return sum(t.price_monthly * w for t, w in zip(paying_tiers, weights))

    def _calculate_target_ltv(self, arpu: float, model: MonetizationModel) -> float:
        """Calculate target Lifetime Value."""
        # Default churn assumptions by model
        monthly_churn = {
            MonetizationModel.SUBSCRIPTION: 0.05,  # 5% monthly churn
            MonetizationModel.FREEMIUM: 0.08,
            MonetizationModel.USAGE_BASED: 0.06,
        }.get(model, 0.05)

        if monthly_churn == 0:
            return arpu * 36  # Cap at 3 years

        # LTV = ARPU / churn_rate
        return arpu / monthly_churn

    def _assess_confidence(
        self,
        market_data: Optional[Dict[str, Any]],
        competitive_data: Optional[Dict[str, Any]],
        target_audience: Optional[Dict[str, Any]],
    ) -> RevenueConfidence:
        """Assess confidence in analysis."""
        data_points = 0

        if market_data and len(market_data) > 0:
            data_points += 1
        if competitive_data and len(competitive_data.get("competitors", [])) > 0:
            data_points += 1
        if target_audience and len(target_audience) > 0:
            data_points += 1

        if data_points >= 3:
            return RevenueConfidence.HIGH
        elif data_points >= 2:
            return RevenueConfidence.MEDIUM
        elif data_points >= 1:
            return RevenueConfidence.LOW
        else:
            return RevenueConfidence.SPECULATIVE

    def _identify_assumptions(
        self, model: MonetizationModel, strategy: PricingStrategy
    ) -> List[str]:
        """Identify key assumptions in the analysis."""
        assumptions = [
            f"Monetization model: {model.value}",
            f"Pricing strategy: {strategy.value}",
            "Market conditions remain stable",
            "Product delivers expected value proposition",
        ]

        if model == MonetizationModel.SUBSCRIPTION:
            assumptions.extend(
                [
                    "Assumed 5% monthly churn rate",
                    "Assumed 60/30/10 tier distribution",
                ]
            )
        elif model == MonetizationModel.FREEMIUM:
            assumptions.extend(
                [
                    "Assumed 2.5-3% free to paid conversion",
                    "Free tier costs covered by paid users",
                ]
            )

        return assumptions

    def _identify_risks(
        self,
        model: MonetizationModel,
        project_type: ProjectType,
        competitive_data: Optional[Dict[str, Any]],
    ) -> List[str]:
        """Identify monetization risks."""
        risks = []

        # Model-specific risks
        model_risks = {
            MonetizationModel.SUBSCRIPTION: [
                "Churn may exceed projections",
                "Price sensitivity in target market",
            ],
            MonetizationModel.FREEMIUM: [
                "Free tier may cannibalize paid conversions",
                "Infrastructure costs for free users",
            ],
            MonetizationModel.USAGE_BASED: [
                "Revenue unpredictability",
                "Usage may not scale as expected",
            ],
        }

        risks.extend(model_risks.get(model, []))

        # Competition risks
        if competitive_data:
            competitor_count = len(competitive_data.get("competitors", []))
            if competitor_count > 3:
                risks.append("Competitive pricing pressure")

        # Add general risks
        risks.extend(
            [
                "Market adoption slower than projected",
                "Customer acquisition costs may exceed targets",
            ]
        )

        return risks

    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get a summary of the analysis for reporting."""
        if not self._analysis_result:
            return {"error": "No analysis performed yet"}

        result = self._analysis_result

        return {
            "project_type": result.project_type.value,
            "recommended_model": result.recommended_model.value,
            "pricing_strategy": result.pricing_strategy.value,
            "tier_count": len(result.pricing_tiers),
            "target_arpu": result.target_arpu,
            "target_ltv": result.target_ltv,
            "confidence": result.confidence.value,
            "year_1_projected_arr": (
                result.revenue_projections[1].arr if len(result.revenue_projections) > 1 else 0
            ),
        }

    def generate_research_findings(self) -> Dict[str, Any]:
        """
        Generate research findings dict for MonetizationStrategyGenerator.

        Returns:
            Dict compatible with MonetizationStrategyGenerator.generate()
        """
        if not self._analysis_result:
            return {}

        result = self._analysis_result

        # Build models list
        models = []
        for fit in result.model_fits[:3]:  # Top 3 models
            models.append(
                {
                    "model": fit.model.value.replace("_", " ").title(),
                    "prevalence": f"Fit score: {fit.fit_score}/10",
                    "pros": fit.pros,
                    "cons": fit.cons,
                    "examples": [],
                }
            )

        # Build pricing benchmarks
        benchmarks = {}
        for tier in result.pricing_tiers:
            tier_key = tier.name.lower().replace(" ", "_")
            benchmarks[tier_key] = {
                "range": f"${tier.price_monthly}/month",
                "median": f"${tier.price_monthly}",
                "source": "Monetization analysis",
            }

        # Build revenue potential
        revenue_potential = {}
        for projection in result.revenue_projections:
            revenue_potential[projection.timeframe] = {
                "monthly": f"${projection.mrr:,.0f}",
                "assumptions": projection.assumptions,
            }

        # Build recommended model
        next((t for t in result.pricing_tiers if t.recommended), None)
        recommended_pricing = {}
        for tier in result.pricing_tiers:
            recommended_pricing[tier.name.lower()] = f"${tier.price_monthly}/month"

        return {
            "overview": f"Recommended monetization model: {result.recommended_model.value.replace('_', ' ').title()}. "
            f"Strategy: {result.pricing_strategy.value.replace('_', ' ').title()}. "
            f"{result.pricing_rationale}",
            "models": models,
            "pricing_benchmarks": benchmarks,
            "conversion_benchmarks": {
                "free_to_paid": {
                    "industry_average": "2-5%",
                    "top_performers": "5-10%",
                    "source": "Industry benchmarks",
                },
                "trial_to_paid": {
                    "industry_average": "15-25%",
                    "top_performers": "25-40%",
                    "source": "Industry benchmarks",
                },
            },
            "revenue_potential": revenue_potential,
            "recommended_model": {
                "model": result.recommended_model.value.replace("_", " ").title(),
                "rationale": result.pricing_rationale,
                "suggested_pricing": recommended_pricing,
                "differentiation": result.market_positioning,
            },
        }
