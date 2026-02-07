"""TechStackProposer for Advisory Recommendations (Phase 3).

Propose technology choices with pros/cons analysis. Provides 2+ options
per project type, includes cost estimates, flags ToS/legal risks.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from autopack.research.idea_parser import ProjectType
from autopack.research.validators.artifact_validator import ArtifactValidator

logger = logging.getLogger(__name__)


class CostTier(str, Enum):
    """Cost tier classification."""

    FREE = "free"
    LOW = "low"  # $0-50/month
    MEDIUM = "medium"  # $50-500/month
    HIGH = "high"  # $500+/month
    VARIABLE = "variable"  # Usage-based


class CostEstimate(BaseModel):
    """Cost estimate for a technology option."""

    monthly_min: float = Field(..., ge=0, description="Minimum monthly cost in USD")
    monthly_max: float = Field(..., ge=0, description="Maximum monthly cost in USD")
    currency: str = Field(default="USD", description="Currency code")
    tier: CostTier = Field(default=CostTier.VARIABLE, description="Cost tier classification")
    notes: str = Field(default="", description="Additional cost notes (scaling, hidden fees, etc.)")

    def __str__(self) -> str:
        if self.monthly_min == self.monthly_max:
            return f"${self.monthly_min:.0f}/month ({self.tier.value})"
        return f"${self.monthly_min:.0f}-${self.monthly_max:.0f}/month ({self.tier.value})"


class TosRiskLevel(str, Enum):
    """Terms of Service risk level."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"  # May result in account termination


class TosRisk(BaseModel):
    """Terms of Service or legal risk."""

    description: str = Field(..., description="Description of the risk")
    level: TosRiskLevel = Field(default=TosRiskLevel.LOW, description="Risk level")
    mitigation: Optional[str] = Field(default=None, description="How to mitigate this risk")


class TechStackOption(BaseModel):
    """A single technology stack option with pros/cons analysis."""

    name: str = Field(..., description="Name of the technology/stack")
    category: str = Field(
        ..., description="Category (e.g., 'Full Stack Framework', 'Payment Provider')"
    )
    description: str = Field(..., description="Brief description of the technology")
    pros: list[str] = Field(default_factory=list, description="List of advantages")
    cons: list[str] = Field(default_factory=list, description="List of disadvantages")
    estimated_cost: CostEstimate = Field(..., description="Cost estimate")
    mcp_available: bool = Field(
        default=False,
        description="Whether MCP (Model Context Protocol) server is available",
    )
    mcp_server_name: Optional[str] = Field(
        default=None, description="Name of the MCP server if available"
    )
    tos_risks: list[TosRisk] = Field(
        default_factory=list, description="Terms of Service and legal risks"
    )
    setup_complexity: str = Field(
        default="medium", description="Setup complexity: low, medium, high"
    )
    documentation_url: Optional[str] = Field(
        default=None, description="URL to official documentation"
    )
    recommended_for: list[str] = Field(
        default_factory=list,
        description="Scenarios this option is recommended for",
    )


class TechStackProposal(BaseModel):
    """Full proposal with multiple technology options for a project type."""

    project_type: ProjectType = Field(..., description="Project type this proposal is for")
    requirements: list[str] = Field(
        default_factory=list, description="Requirements considered in this proposal"
    )
    options: list[TechStackOption] = Field(
        ..., min_length=2, description="At least 2 technology options"
    )
    recommendation: Optional[str] = Field(
        default=None,
        description="Recommended option name with reasoning (if clear winner exists)",
    )
    recommendation_reasoning: Optional[str] = Field(
        default=None, description="Detailed reasoning for the recommendation"
    )
    confidence_score: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence in the proposal"
    )


# Pre-defined tech stack options per project type
_ECOMMERCE_STACKS: list[TechStackOption] = [
    TechStackOption(
        name="Shopify + Custom App",
        category="Hosted E-commerce Platform",
        description="Shopify platform with custom app integration for extensibility",
        pros=[
            "Rapid setup and deployment",
            "Built-in payment processing (Shopify Payments)",
            "Extensive app ecosystem",
            "Handles PCI compliance automatically",
            "24/7 support and high uptime SLA",
        ],
        cons=[
            "Transaction fees on third-party payment gateways",
            "Limited customization compared to self-hosted",
            "Monthly platform fees add up",
            "Vendor lock-in concerns",
        ],
        estimated_cost=CostEstimate(
            monthly_min=29,
            monthly_max=299,
            tier=CostTier.MEDIUM,
            notes="Plus transaction fees (0.5-2%) if not using Shopify Payments",
        ),
        mcp_available=False,
        tos_risks=[
            TosRisk(
                description="Shopify may restrict certain product categories",
                level=TosRiskLevel.MEDIUM,
                mitigation="Review Shopify Acceptable Use Policy before committing",
            )
        ],
        setup_complexity="low",
        documentation_url="https://shopify.dev/docs",
        recommended_for=["quick launch", "non-technical founders", "standard retail"],
    ),
    TechStackOption(
        name="Next.js + Stripe + Supabase",
        category="Custom Stack",
        description="Self-hosted solution with Next.js frontend, Stripe payments, Supabase backend",
        pros=[
            "Full control over customization",
            "No platform fees beyond hosting",
            "Modern developer experience",
            "Excellent performance with SSG/SSR",
            "Open source core components",
        ],
        cons=[
            "Requires development expertise",
            "You handle PCI compliance scope",
            "More complex deployment and maintenance",
            "Need to build features Shopify provides out-of-box",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=100,
            tier=CostTier.LOW,
            notes="Vercel free tier + Supabase free tier + Stripe 2.9% + $0.30 per transaction",
        ),
        mcp_available=True,
        mcp_server_name="supabase-mcp",
        tos_risks=[
            TosRisk(
                description="Stripe prohibited business list applies",
                level=TosRiskLevel.LOW,
                mitigation="Review Stripe prohibited businesses list",
            )
        ],
        setup_complexity="high",
        documentation_url="https://nextjs.org/docs",
        recommended_for=["custom requirements", "developer-led teams", "unique UX needs"],
    ),
    TechStackOption(
        name="WooCommerce + WordPress",
        category="Self-hosted CMS",
        description="WordPress with WooCommerce plugin for e-commerce",
        pros=[
            "Huge plugin ecosystem",
            "Familiar WordPress admin",
            "One-time theme costs (no monthly fees)",
            "Full ownership of data and code",
        ],
        cons=[
            "Requires hosting management",
            "Security updates are your responsibility",
            "Performance can degrade with many plugins",
            "PHP-based stack may not suit all teams",
        ],
        estimated_cost=CostEstimate(
            monthly_min=10,
            monthly_max=50,
            tier=CostTier.LOW,
            notes="Hosting costs + optional premium plugins/themes",
        ),
        mcp_available=False,
        tos_risks=[],
        setup_complexity="medium",
        documentation_url="https://woocommerce.com/documentation/",
        recommended_for=["content-heavy stores", "existing WordPress sites", "budget-conscious"],
    ),
]

_TRADING_STACKS: list[TechStackOption] = [
    TechStackOption(
        name="Python + CCXT + PostgreSQL",
        category="Algorithmic Trading Stack",
        description="Python-based trading with CCXT library for exchange connectivity",
        pros=[
            "CCXT supports 100+ exchanges with unified API",
            "Rich Python ecosystem for data analysis (pandas, numpy)",
            "Easy backtesting integration",
            "Large community and documentation",
        ],
        cons=[
            "Python may have latency issues for HFT",
            "Need to manage exchange API rate limits",
            "Requires careful error handling for financial operations",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0, monthly_max=50, tier=CostTier.LOW, notes="Hosting + data feeds if needed"
        ),
        mcp_available=True,
        mcp_server_name="postgres-mcp",
        tos_risks=[
            TosRisk(
                description="Exchange API ToS may prohibit automated trading or specific strategies",
                level=TosRiskLevel.HIGH,
                mitigation="Review each exchange's API ToS; some ban HFT or arbitrage",
            ),
            TosRisk(
                description="Regulatory compliance varies by jurisdiction",
                level=TosRiskLevel.CRITICAL,
                mitigation="Consult legal counsel for trading regulations in your jurisdiction",
            ),
        ],
        setup_complexity="medium",
        documentation_url="https://docs.ccxt.com/",
        recommended_for=["crypto trading", "backtesting strategies", "medium-frequency trading"],
    ),
    TechStackOption(
        name="Alpaca API + FastAPI",
        category="Stock Trading Platform",
        description="Commission-free stock trading API with FastAPI backend",
        pros=[
            "Commission-free stock and ETF trading",
            "Paper trading for testing",
            "Real-time market data included",
            "Well-documented REST and WebSocket APIs",
        ],
        cons=[
            "US markets only",
            "Limited to stocks/ETFs (no options, futures)",
            "Rate limits on free tier",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=99,
            tier=CostTier.LOW,
            notes="Free tier available; paid tiers for more data",
        ),
        mcp_available=False,
        tos_risks=[
            TosRisk(
                description="Pattern day trader rules apply (FINRA)",
                level=TosRiskLevel.MEDIUM,
                mitigation="Maintain $25k+ account balance for unlimited day trades",
            ),
        ],
        setup_complexity="low",
        documentation_url="https://alpaca.markets/docs/",
        recommended_for=["US stock trading", "beginners", "paper trading development"],
    ),
]

_CONTENT_STACKS: list[TechStackOption] = [
    TechStackOption(
        name="Next.js + Sanity CMS",
        category="Headless CMS Stack",
        description="Modern headless CMS with Next.js frontend",
        pros=[
            "Flexible content modeling",
            "Real-time collaborative editing",
            "Excellent developer experience",
            "CDN-backed asset delivery",
        ],
        cons=[
            "Learning curve for Sanity's GROQ query language",
            "Costs scale with usage",
            "Requires frontend development expertise",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=99,
            tier=CostTier.LOW,
            notes="Free tier generous; paid for teams/advanced features",
        ),
        mcp_available=False,
        tos_risks=[],
        setup_complexity="medium",
        documentation_url="https://www.sanity.io/docs",
        recommended_for=["editorial teams", "multi-channel content", "custom frontends"],
    ),
    TechStackOption(
        name="Ghost + Mailgun",
        category="Newsletter/Blog Platform",
        description="Ghost publishing platform with integrated newsletters",
        pros=[
            "Built-in membership and subscription",
            "Native newsletter functionality",
            "Clean, fast publishing experience",
            "SEO-optimized out of the box",
        ],
        cons=[
            "Less flexible than headless CMS",
            "Self-hosting requires technical expertise",
            "Limited theme customization compared to WordPress",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=89,
            tier=CostTier.LOW,
            notes="Self-hosted free; Ghost Pro $9-$89/month",
        ),
        mcp_available=False,
        tos_risks=[],
        setup_complexity="low",
        documentation_url="https://ghost.org/docs/",
        recommended_for=["newsletters", "membership sites", "bloggers"],
    ),
]

_AUTOMATION_STACKS: list[TechStackOption] = [
    TechStackOption(
        name="n8n + PostgreSQL",
        category="Self-hosted Workflow Automation",
        description="Open-source workflow automation with 200+ integrations",
        pros=[
            "Self-hosted option (data privacy)",
            "Visual workflow builder",
            "Extensive integration library",
            "One-time setup, no per-execution fees",
        ],
        cons=[
            "Requires hosting infrastructure",
            "Fewer integrations than Zapier",
            "Community support (vs enterprise support)",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=50,
            tier=CostTier.LOW,
            notes="Self-hosted free; cloud starts at $20/month",
        ),
        mcp_available=True,
        mcp_server_name="postgres-mcp",
        tos_risks=[],
        setup_complexity="medium",
        documentation_url="https://docs.n8n.io/",
        recommended_for=["data privacy needs", "complex workflows", "cost-conscious teams"],
    ),
    TechStackOption(
        name="Zapier + Airtable",
        category="No-code Automation Platform",
        description="Popular automation platform with Airtable for data",
        pros=[
            "No coding required",
            "5000+ app integrations",
            "Reliable and well-supported",
            "Quick setup for common use cases",
        ],
        cons=[
            "Costs scale with task volume",
            "Limited customization for complex logic",
            "Vendor lock-in",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=599,
            tier=CostTier.VARIABLE,
            notes="Free tier limited; scales with tasks ($19.99-$599+/month)",
        ),
        mcp_available=False,
        tos_risks=[
            TosRisk(
                description="Task limits can be unexpectedly exceeded",
                level=TosRiskLevel.LOW,
                mitigation="Monitor task usage; consider n8n for high-volume",
            )
        ],
        setup_complexity="low",
        documentation_url="https://zapier.com/help",
        recommended_for=["non-technical users", "quick prototypes", "standard integrations"],
    ),
]

_OTHER_STACKS: list[TechStackOption] = [
    TechStackOption(
        name="Next.js + Supabase",
        category="Full Stack JavaScript",
        description="Modern full-stack development with Next.js and Supabase BaaS",
        pros=[
            "Rapid development with great DX",
            "Built-in auth, database, storage",
            "Real-time subscriptions included",
            "Generous free tier",
        ],
        cons=[
            "Supabase still maturing (vs Firebase)",
            "PostgreSQL-specific queries",
            "Learning curve for Row Level Security",
        ],
        estimated_cost=CostEstimate(
            monthly_min=0,
            monthly_max=25,
            tier=CostTier.LOW,
            notes="Free tier covers most MVPs; paid starts at $25/month",
        ),
        mcp_available=True,
        mcp_server_name="supabase-mcp",
        tos_risks=[],
        setup_complexity="low",
        documentation_url="https://supabase.com/docs",
        recommended_for=["MVPs", "real-time apps", "solo developers"],
    ),
    TechStackOption(
        name="Django + PostgreSQL + Redis",
        category="Python Web Stack",
        description="Battle-tested Python web framework with PostgreSQL",
        pros=[
            "Mature ecosystem with excellent documentation",
            "Built-in admin panel",
            "Strong ORM and security features",
            "Large talent pool",
        ],
        cons=[
            "Monolithic architecture may not suit all projects",
            "Can be slower than Node.js for I/O-bound tasks",
            "Python hosting can be more expensive",
        ],
        estimated_cost=CostEstimate(
            monthly_min=5,
            monthly_max=100,
            tier=CostTier.LOW,
            notes="VPS hosting + managed PostgreSQL optional",
        ),
        mcp_available=True,
        mcp_server_name="postgres-mcp",
        tos_risks=[],
        setup_complexity="medium",
        documentation_url="https://docs.djangoproject.com/",
        recommended_for=["data-heavy apps", "admin-focused tools", "Python teams"],
    ),
]

# Mapping of project types to their stack options
_STACKS_BY_TYPE: dict[ProjectType, list[TechStackOption]] = {
    ProjectType.ECOMMERCE: _ECOMMERCE_STACKS,
    ProjectType.TRADING: _TRADING_STACKS,
    ProjectType.CONTENT: _CONTENT_STACKS,
    ProjectType.AUTOMATION: _AUTOMATION_STACKS,
    ProjectType.OTHER: _OTHER_STACKS,
}


class TechStackProposer:
    """Proposer for technology stack recommendations.

    Analyzes project requirements and proposes suitable technology stacks
    with pros/cons analysis, cost estimates, and risk assessments.
    """

    def __init__(self, include_mcp_options: bool = True):
        """Initialize the TechStackProposer.

        Args:
            include_mcp_options: Whether to prioritize options with MCP servers
        """
        self.include_mcp_options = include_mcp_options
        self._validator = ArtifactValidator()

    def propose(
        self,
        project_type: ProjectType,
        requirements: list[str] | None = None,
    ) -> TechStackProposal:
        """Propose technology stack options for a project type.

        Args:
            project_type: The type of project
            requirements: Optional list of specific requirements

        Returns:
            TechStackProposal with at least 2 options

        Raises:
            ValueError: If proposal fails schema validation
        """
        requirements = requirements or []

        # Get base options for project type
        options = self._get_options_for_type(project_type)

        # Score and rank options based on requirements
        scored_options = self._score_options(options, requirements)

        # Select top options (at least 2)
        selected_options = scored_options[:3] if len(scored_options) >= 3 else scored_options

        # Generate recommendation if clear winner
        recommendation, reasoning = self._generate_recommendation(selected_options, requirements)

        # Calculate confidence based on requirement matching
        confidence = self._calculate_confidence(selected_options, requirements)

        proposal = TechStackProposal(
            project_type=project_type,
            requirements=requirements,
            options=selected_options,
            recommendation=recommendation,
            recommendation_reasoning=reasoning,
            confidence_score=confidence,
        )

        # Validate proposal against schema
        validation_result = self._validator.validate(proposal.model_dump())
        if not validation_result.is_valid:
            error_messages = [f"{e.path}: {e.message}" for e in validation_result.errors]
            error_text = "; ".join(error_messages)
            logger.error(
                f"[TechStackProposer] Schema validation failed for {project_type.value}: {error_text}"
            )
            raise ValueError(f"Tech stack proposal failed schema validation: {error_text}")

        if validation_result.warnings:
            for warning in validation_result.warnings:
                logger.warning(f"[TechStackProposer] {warning}")

        logger.info(
            f"[TechStackProposer] Generated proposal for {project_type.value} "
            f"with {len(selected_options)} options"
        )

        return proposal

    def _get_options_for_type(self, project_type: ProjectType) -> list[TechStackOption]:
        """Get technology options for a project type.

        Args:
            project_type: The project type

        Returns:
            List of TechStackOption
        """
        options = _STACKS_BY_TYPE.get(project_type, _OTHER_STACKS)

        # Ensure we always have at least 2 options
        if len(options) < 2:
            # Add generic options as fallback
            options = options + _OTHER_STACKS[:2]

        return options

    def _score_options(
        self,
        options: list[TechStackOption],
        requirements: list[str],
    ) -> list[TechStackOption]:
        """Score and sort options based on requirements.

        Args:
            options: List of options to score
            requirements: User requirements

        Returns:
            Sorted list of options (best first)
        """
        if not requirements:
            # Without requirements, prioritize MCP availability if enabled
            if self.include_mcp_options:
                return sorted(options, key=lambda o: (not o.mcp_available, o.name))
            return options

        scored: list[tuple[TechStackOption, float]] = []
        req_lower = [r.lower() for r in requirements]

        for option in options:
            score = 0.0

            # Check if option name or description matches requirements
            option_text = f"{option.name} {option.description}".lower()
            for req in req_lower:
                if any(word in option_text for word in req.split()):
                    score += 1.0

            # Boost score for MCP availability if enabled
            if self.include_mcp_options and option.mcp_available:
                score += 0.5

            # Penalize high ToS risks
            high_risk_count = sum(
                1
                for risk in option.tos_risks
                if risk.level in (TosRiskLevel.HIGH, TosRiskLevel.CRITICAL)
            )
            score -= high_risk_count * 0.3

            scored.append((option, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return [opt for opt, _ in scored]

    def _generate_recommendation(
        self,
        options: list[TechStackOption],
        requirements: list[str],
    ) -> tuple[Optional[str], Optional[str]]:
        """Generate a recommendation if there's a clear winner.

        Args:
            options: Scored options list
            requirements: User requirements

        Returns:
            Tuple of (recommendation name, reasoning) or (None, None)
        """
        if not options:
            return None, None

        # If first option has MCP and user didn't specify otherwise
        top = options[0]

        # Check for high-risk ToS that would prevent recommendation
        has_critical_risk = any(risk.level == TosRiskLevel.CRITICAL for risk in top.tos_risks)

        if has_critical_risk:
            return (
                None,
                "No clear recommendation due to critical ToS/legal risks that require review",
            )

        # Generate reasoning
        reasoning_parts = []

        if top.mcp_available:
            reasoning_parts.append("MCP server available for AI integration")

        if top.setup_complexity == "low":
            reasoning_parts.append("low setup complexity")

        if top.estimated_cost.tier in (CostTier.FREE, CostTier.LOW):
            reasoning_parts.append("cost-effective")

        if top.pros:
            reasoning_parts.append(top.pros[0].lower())

        if reasoning_parts:
            reasoning = f"Recommended due to: {', '.join(reasoning_parts)}"
        else:
            reasoning = "Best overall match for requirements"

        return top.name, reasoning

    def _calculate_confidence(
        self,
        options: list[TechStackOption],
        requirements: list[str],
    ) -> float:
        """Calculate confidence score for the proposal.

        Args:
            options: Selected options
            requirements: User requirements

        Returns:
            Confidence score between 0 and 1
        """
        if not options:
            return 0.5

        base_confidence = 0.7

        # Higher confidence with more requirements matched
        if requirements:
            base_confidence += 0.1

        # Higher confidence if top option has MCP
        if options[0].mcp_available:
            base_confidence += 0.05

        # Lower confidence if high ToS risks
        for option in options:
            if any(r.level == TosRiskLevel.CRITICAL for r in option.tos_risks):
                base_confidence -= 0.1
                break

        return min(0.95, max(0.5, base_confidence))

    def get_all_options_for_type(self, project_type: ProjectType) -> list[TechStackOption]:
        """Get all available options for a project type.

        Args:
            project_type: The project type

        Returns:
            All TechStackOption objects for the type
        """
        return self._get_options_for_type(project_type)

    def get_mcp_enabled_options(self) -> list[TechStackOption]:
        """Get all options that have MCP servers available.

        Returns:
            List of TechStackOption with mcp_available=True
        """
        all_options: list[TechStackOption] = []
        for options in _STACKS_BY_TYPE.values():
            all_options.extend(opt for opt in options if opt.mcp_available)
        return all_options

    def check_tos_risks(self, project_type: ProjectType) -> list[tuple[str, TosRisk]]:
        """Check all ToS risks for options of a project type.

        Args:
            project_type: The project type to check

        Returns:
            List of (option_name, TosRisk) tuples
        """
        risks: list[tuple[str, TosRisk]] = []
        for option in self._get_options_for_type(project_type):
            for risk in option.tos_risks:
                risks.append((option.name, risk))
        return risks
