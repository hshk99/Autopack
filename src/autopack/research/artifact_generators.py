"""Artifact Generators Registry for research projects.

Provides a central registry for all artifact generators that produce
deployment configurations, documentation, and other outputs from
research findings.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from autopack.executor.post_build_generator import (
    PostBuildArtifactGenerator,
)
from autopack.research.analysis.deployment_analysis import (
    DeploymentAnalyzer,
    DeploymentArchitecture,
)
from autopack.research.analysis.monetization_analysis import (
    MonetizationAnalysisResult,
    MonetizationAnalyzer,
    ProjectType,
)
from autopack.research.discovery.mcp_discovery import MCPScanResult
from autopack.research.generators.cicd_generator import (
    CICDAnalyzer,
    CICDWorkflowGenerator,
    GitLabCIGenerator,
    JenkinsPipelineGenerator,
)
from autopack.research.sot_summarizer import SOTSummarizer, SOTSummary, get_sot_summarizer
from autopack.research.validators.artifact_validator import ArtifactValidator

logger = logging.getLogger(__name__)


# Type validation and safe access utility functions
def safe_get_string(value: Any, default: str = "") -> str:
    """Safely convert any value to a string with a default fallback.

    Args:
        value: The value to convert to string
        default: Default string if value is None or invalid

    Returns:
        String representation of value or default
    """
    if value is None:
        logger.debug(f"[safe_get_string] None value provided, using default: {default!r}")
        return default
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception as e:
        logger.warning(f"[safe_get_string] Failed to convert {type(value)} to string: {e}")
        return default


def safe_get_float(value: Any, default: float = 0.0) -> float:
    """Safely convert any value to a float with type validation.

    Args:
        value: The value to convert to float
        default: Default float if value is None or not numeric

    Returns:
        Float value or default
    """
    if value is None:
        logger.debug(f"[safe_get_float] None value provided, using default: {default}")
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            logger.warning(
                f"[safe_get_float] Cannot convert string '{value}' to float, using default: {default}"
            )
            return default
    logger.warning(
        f"[safe_get_float] Unexpected type {type(value)} for value {value!r}, using default: {default}"
    )
    return default


def safe_get_int(value: Any, default: int = 0) -> int:
    """Safely convert any value to an int with type validation.

    Args:
        value: The value to convert to int
        default: Default int if value is None or not numeric

    Returns:
        Integer value or default
    """
    if value is None:
        logger.debug(f"[safe_get_int] None value provided, using default: {default}")
        return default
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            logger.warning(
                f"[safe_get_int] Cannot convert string '{value}' to int, using default: {default}"
            )
            return default
    logger.warning(
        f"[safe_get_int] Unexpected type {type(value)} for value {value!r}, using default: {default}"
    )
    return default


def safe_dict_get(
    data: dict, key: str, default: Any = None, expected_type: Optional[Type] = None
) -> Any:
    """Safely get value from dict with optional type validation.

    Args:
        data: Dictionary to access
        key: Key to retrieve
        default: Default value if key missing or type invalid
        expected_type: If provided, validates value is this type

    Returns:
        Value from dict or default if missing/invalid type
    """
    if not isinstance(data, dict):
        logger.warning(f"[safe_dict_get] Expected dict, got {type(data)}")
        return default

    value = data.get(key, default)

    if value is default or value is None:
        logger.debug(f"[safe_dict_get] Key '{key}' not found in dict, using default")
        return default

    if expected_type is not None and not isinstance(value, expected_type):
        logger.warning(
            f"[safe_dict_get] Key '{key}' has type {type(value)}, "
            f"expected {expected_type.__name__}, using default"
        )
        return default

    return value


def safe_enum_value(enum_obj: Any, default: str = "unknown") -> str:
    """Safely get the string value of an enum object.

    Args:
        enum_obj: Enum object to extract value from
        default: Default string if value is None or not accessible

    Returns:
        String representation of enum value or default
    """
    if enum_obj is None:
        logger.debug(f"[safe_enum_value] None enum provided, using default: {default!r}")
        return default

    try:
        if hasattr(enum_obj, "value"):
            value = enum_obj.value
            if isinstance(value, str):
                return value
            return str(value)
        return str(enum_obj)
    except Exception as e:
        logger.warning(
            f"[safe_enum_value] Failed to extract enum value: {e}, using default: {default!r}"
        )
        return default


def safe_format_currency(value: Any, prefix: str = "$", decimals: int = 0) -> str:
    """Safely format a value as currency string.

    Args:
        value: Numeric value to format
        prefix: Currency prefix (default: "$")
        decimals: Number of decimal places (default: 0)

    Returns:
        Formatted currency string
    """
    numeric_value = safe_get_float(value, 0.0)
    format_str = f"{{:,.{decimals}f}}"
    return f"{prefix}{format_str.format(numeric_value)}"


class MonetizationStrategyGenerator:
    """Generates MONETIZATION_STRATEGY.md from research findings.

    Produces a comprehensive monetization strategy document including
    pricing models, benchmarks, conversion metrics, and revenue projections.

    Can generate from raw research_findings dict or from a MonetizationAnalysisResult
    produced by the MonetizationAnalyzer.
    """

    def __init__(self, budget_enforcer: Optional[Any] = None):
        """Initialize the generator.

        Args:
            budget_enforcer: Optional BudgetEnforcer for cost control
        """
        self._budget_enforcer = budget_enforcer
        self._analyzer: Optional[MonetizationAnalyzer] = None

    def generate(self, research_findings: Dict[str, Any]) -> str:
        """Generate monetization strategy markdown.

        Args:
            research_findings: Research findings dict with monetization data

        Returns:
            Markdown string with monetization strategy
        """
        logger.info("[MonetizationStrategyGenerator] Generating monetization strategy")

        content = "# Monetization Strategy\n\n"

        # Overview
        overview = research_findings.get("overview", "")
        if overview:
            content += f"## Overview\n\n{overview}\n\n"

        # Pricing Models
        models = research_findings.get("models", [])
        if models:
            content += self._generate_pricing_models_section(models)

        # Pricing Benchmarks
        benchmarks = research_findings.get("pricing_benchmarks", {})
        if benchmarks:
            content += self._generate_benchmarks_section(benchmarks)

        # Conversion Metrics
        conversion = research_findings.get("conversion_benchmarks", {})
        if conversion:
            content += self._generate_conversion_section(conversion)

        # Revenue Potential
        revenue = research_findings.get("revenue_potential", {})
        if revenue:
            content += self._generate_revenue_section(revenue)

        # Recommended Model
        recommended = research_findings.get("recommended_model", {})
        if recommended:
            content += self._generate_recommended_section(recommended)

        return content

    def _generate_pricing_models_section(self, models: list) -> str:
        """Generate pricing models section.

        Args:
            models: List of pricing model dicts

        Returns:
            Markdown section string
        """
        section = "## Pricing Models\n\n"

        for model in models:
            if not isinstance(model, dict):
                logger.warning(
                    f"[_generate_pricing_models_section] Expected dict, got {type(model)}"
                )
                continue

            model_type = safe_get_string(model.get("model"), "Unknown")
            prevalence = safe_get_string(model.get("prevalence"), "")
            pros = model.get("pros", [])
            cons = model.get("cons", [])

            section += f"### {model_type.title()}\n\n"

            if prevalence:
                section += f"**Prevalence**: {prevalence}\n\n"

            examples = model.get("examples", [])
            if examples and isinstance(examples, list):
                section += "**Examples:**\n"
                for example in examples:
                    if not isinstance(example, dict):
                        logger.debug(
                            f"[_generate_pricing_models_section] Skipping non-dict example: {type(example)}"
                        )
                        continue

                    company = safe_get_string(example.get("company"), "Unknown")
                    url = safe_get_string(example.get("url"), "")
                    tiers = example.get("tiers", [])

                    section += f"\n- **{company}**"
                    if url:
                        section += f" ([link]({url}))"
                    section += "\n"

                    if isinstance(tiers, list):
                        for tier in tiers:
                            if not isinstance(tier, dict):
                                logger.debug(
                                    f"[_generate_pricing_models_section] Skipping non-dict tier: {type(tier)}"
                                )
                                continue

                            tier_name = safe_get_string(tier.get("name"), "")
                            price = safe_get_string(tier.get("price"), "")
                            limits = safe_get_string(tier.get("limits"), "")
                            section += f"  - {tier_name}: {price}"
                            if limits:
                                section += f" ({limits})"
                            section += "\n"

                section += "\n"

            if pros and isinstance(pros, list):
                section += "**Pros:**\n"
                for pro in pros:
                    pro_str = safe_get_string(pro, "Benefit")
                    section += f"- {pro_str}\n"
                section += "\n"

            if cons and isinstance(cons, list):
                section += "**Cons:**\n"
                for con in cons:
                    con_str = safe_get_string(con, "Limitation")
                    section += f"- {con_str}\n"
                section += "\n"

        return section

    def _generate_benchmarks_section(self, benchmarks: Dict[str, Any]) -> str:
        """Generate pricing benchmarks section.

        Args:
            benchmarks: Pricing benchmarks dict

        Returns:
            Markdown section string
        """
        section = "## Pricing Benchmarks\n\n"

        for tier, data in benchmarks.items():
            # Safely convert tier key to string
            tier_str = safe_get_string(tier, "tier").replace("_", " ").title()
            section += f"### {tier_str}\n\n"

            if isinstance(data, dict):
                range_val = safe_get_string(data.get("range"), "")
                if range_val:
                    section += f"- **Range**: {range_val}\n"

                median = safe_get_string(data.get("median"), "")
                if median:
                    section += f"- **Median**: {median}\n"

                source = safe_get_string(data.get("source"), "")
                if source:
                    section += f"- **Source**: {source}\n"

                extraction = safe_get_string(data.get("extraction_span"), "")
                if extraction:
                    section += f"- **Extraction**: {extraction}\n"

            section += "\n"

        return section

    def _generate_conversion_section(self, conversion: Dict[str, Any]) -> str:
        """Generate conversion metrics section.

        Args:
            conversion: Conversion benchmarks dict

        Returns:
            Markdown section string
        """
        section = "## Conversion Metrics\n\n"

        for metric_key, metric_data in conversion.items():
            # Safely convert metric key to string
            metric_key_str = safe_get_string(metric_key, "metric").replace("_", " ").title()
            section += f"### {metric_key_str}\n\n"

            if isinstance(metric_data, dict):
                industry_avg = safe_get_string(metric_data.get("industry_average"), "")
                if industry_avg:
                    section += f"- **Industry Average**: {industry_avg}\n"

                top_performers = safe_get_string(metric_data.get("top_performers"), "")
                if top_performers:
                    section += f"- **Top Performers**: {top_performers}\n"

                source = safe_get_string(metric_data.get("source"), "")
                if source:
                    section += f"- **Source**: {source}\n"

            section += "\n"

        return section

    def _generate_revenue_section(self, revenue: Dict[str, Any]) -> str:
        """Generate revenue potential section.

        Args:
            revenue: Revenue potential dict

        Returns:
            Markdown section string
        """
        section = "## Revenue Potential\n\n"

        for scenario, data in revenue.items():
            # Safely convert scenario key to string
            scenario_str = safe_get_string(scenario, "scenario").title()
            section += f"### {scenario_str} Scenario\n\n"

            if isinstance(data, dict):
                monthly = safe_get_string(data.get("monthly"), "")
                if monthly:
                    section += f"- **Monthly Revenue**: {monthly}\n"

                assumptions = data.get("assumptions", [])
                if assumptions and isinstance(assumptions, list):
                    section += "- **Assumptions**:\n"
                    for assumption in assumptions:
                        assumption_str = safe_get_string(assumption, "Assumption")
                        section += f"  - {assumption_str}\n"

            section += "\n"

        return section

    def _generate_recommended_section(self, recommended: Dict[str, Any]) -> str:
        """Generate recommended model section.

        Args:
            recommended: Recommended model dict

        Returns:
            Markdown section string
        """
        section = "## Recommended Model\n\n"

        model = safe_get_string(recommended.get("model"), "")
        if model:
            section += f"**Model**: {model}\n\n"

        rationale = safe_get_string(recommended.get("rationale"), "")
        if rationale:
            section += f"**Rationale**: {rationale}\n\n"

        suggested = recommended.get("suggested_pricing", {})
        if suggested and isinstance(suggested, dict):
            section += "**Suggested Pricing**:\n"
            for tier, price in suggested.items():
                # Safely convert tier key to string
                tier_str = safe_get_string(tier, "tier").title()
                price_str = safe_get_string(price, "Custom pricing")
                section += f"- {tier_str}: {price_str}\n"
            section += "\n"

        differentiation = safe_get_string(recommended.get("differentiation"), "")
        if differentiation:
            section += f"**Differentiation**: {differentiation}\n\n"

        return section

    def generate_from_analysis(
        self,
        analysis_result: MonetizationAnalysisResult,
    ) -> str:
        """Generate monetization strategy from MonetizationAnalysisResult.

        Args:
            analysis_result: Result from MonetizationAnalyzer.analyze()

        Returns:
            Markdown string with monetization strategy
        """
        logger.info("[MonetizationStrategyGenerator] Generating from analysis result")

        content = "# Monetization Strategy\n\n"

        # Overview
        content += "## Overview\n\n"
        # Safely format enum values with proper string methods
        recommended_model = (
            safe_enum_value(analysis_result.recommended_model, "standard").replace("_", " ").title()
        )
        pricing_strategy = (
            safe_enum_value(analysis_result.pricing_strategy, "tiered").replace("_", " ").title()
        )
        project_type = (
            safe_enum_value(analysis_result.project_type, "general").replace("_", " ").title()
        )
        content += f"**Recommended Model**: {recommended_model}\n"
        content += f"**Pricing Strategy**: {pricing_strategy}\n"
        content += f"**Project Type**: {project_type}\n\n"
        pricing_rationale = safe_get_string(analysis_result.pricing_rationale, "Analysis complete.")
        content += f"{pricing_rationale}\n\n"

        # Model Fits
        if analysis_result.model_fits:
            content += "## Monetization Models Analysis\n\n"
            for fit in analysis_result.model_fits[:3]:  # Top 3
                model_name = safe_enum_value(fit.model, "unknown").replace("_", " ").title()
                content += f"### {model_name}\n\n"
                fit_score = safe_get_float(fit.fit_score, 0.0)
                content += f"**Fit Score**: {fit_score:.1f}/10\n\n"

                if fit.pros:
                    content += "**Pros**:\n"
                    for pro in fit.pros:
                        content += f"- {pro}\n"
                    content += "\n"

                if fit.cons:
                    content += "**Cons**:\n"
                    for con in fit.cons:
                        content += f"- {con}\n"
                    content += "\n"

        # Pricing Tiers
        if analysis_result.pricing_tiers:
            content += "## Pricing Tiers\n\n"
            content += "| Tier | Monthly | Yearly | Target Audience |\n"
            content += "|------|---------|--------|----------------|\n"

            for tier in analysis_result.pricing_tiers:
                # Safely format pricing with type validation
                price_monthly = safe_get_float(tier.price_monthly, 0.0)
                price_yearly = safe_get_float(tier.price_yearly, 0.0)
                monthly = safe_format_currency(price_monthly) if price_monthly > 0 else "Free"
                yearly = safe_format_currency(price_yearly) if price_yearly > 0 else "-"
                rec = " **(Recommended)**" if tier.recommended else ""
                target_aud = safe_get_string(tier.target_audience, "General")
                content += f"| {tier.name}{rec} | {monthly} | {yearly} | {target_aud} |\n"

            content += "\n"

            # Tier details
            for tier in analysis_result.pricing_tiers:
                tier_name = safe_get_string(tier.name, "Tier")
                content += f"### {tier_name}\n\n"
                price_monthly = safe_get_float(tier.price_monthly, 0.0)
                content += f"**Price**: {safe_format_currency(price_monthly)}/month"

                price_yearly = safe_get_float(tier.price_yearly, 0.0)
                if price_yearly > 0:
                    discount = safe_get_float(tier.yearly_discount_percent, 0.0)
                    content += (
                        f" ({safe_format_currency(price_yearly)}/year - {discount:.0f}% discount)"
                    )
                content += "\n\n"

                if tier.features:
                    content += "**Features**:\n"
                    for feature in tier.features:
                        feature_str = safe_get_string(feature, "Feature")
                        content += f"- {feature_str}\n"
                    content += "\n"

                if tier.limits:
                    content += "**Limits**: "
                    limit_items = []
                    for k, v in tier.limits.items():
                        key_str = safe_get_string(k, "limit")
                        val_str = safe_get_string(v, "unlimited")
                        limit_items.append(f"{key_str}: {val_str}")
                    limits_str = ", ".join(limit_items)
                    content += f"{limits_str}\n\n"

        # Revenue Projections
        if analysis_result.revenue_projections:
            content += "## Revenue Projections\n\n"
            content += "| Timeframe | Users | Paying Users | MRR | ARR | Confidence |\n"
            content += "|-----------|-------|--------------|-----|-----|------------|\n"

            for proj in analysis_result.revenue_projections:
                # Safely format all projection fields
                timeframe_str = safe_get_string(proj.timeframe, "unknown").replace("_", " ").title()
                users = safe_get_int(proj.users, 0)
                paying_users = safe_get_int(proj.paying_users, 0)
                conversion_rate = safe_get_float(proj.conversion_rate, 0.0)
                mrr = safe_get_float(proj.mrr, 0.0)
                arr = safe_get_float(proj.arr, 0.0)
                confidence_val = safe_enum_value(proj.confidence, "unknown").title()

                content += (
                    f"| {timeframe_str} "
                    f"| {users:,} "
                    f"| {paying_users:,} ({conversion_rate:.1f}%) "
                    f"| {safe_format_currency(mrr)} "
                    f"| {safe_format_currency(arr)} "
                    f"| {confidence_val} |\n"
                )

            content += "\n"

        # Key Metrics
        content += "## Key Metrics Targets\n\n"
        target_arpu = safe_get_float(analysis_result.target_arpu, 0.0)
        target_ltv = safe_get_float(analysis_result.target_ltv, 0.0)
        cac_ratio = safe_get_float(analysis_result.target_cac_ratio, 1.0)
        content += f"- **Target ARPU**: {safe_format_currency(target_arpu)}/month\n"
        content += f"- **Target LTV**: {safe_format_currency(target_ltv)}\n"
        content += f"- **Target LTV:CAC Ratio**: {cac_ratio:.1f}:1\n\n"

        # Competitive Pricing
        if analysis_result.competitor_pricing:
            content += "## Competitive Pricing Analysis\n\n"
            content += "| Competitor | Model | Price Range | Position |\n"
            content += "|------------|-------|-------------|----------|\n"

            for comp in analysis_result.competitor_pricing:
                content += (
                    f"| {comp.competitor_name} "
                    f"| {comp.pricing_model} "
                    f"| {comp.price_range} "
                    f"| {comp.market_position} |\n"
                )

            content += "\n"
            content += f"**Market Positioning**: {analysis_result.market_positioning}\n\n"

        # Assumptions
        if analysis_result.key_assumptions:
            content += "## Key Assumptions\n\n"
            for assumption in analysis_result.key_assumptions:
                content += f"- {assumption}\n"
            content += "\n"

        # Risks
        if analysis_result.risks:
            content += "## Monetization Risks\n\n"
            for risk in analysis_result.risks:
                content += f"- {risk}\n"
            content += "\n"

        # Confidence
        content += "## Analysis Confidence\n\n"
        confidence_level = safe_enum_value(analysis_result.confidence, "medium").title()
        content += f"**Confidence Level**: {confidence_level}\n\n"

        return content

    def analyze_and_generate(
        self,
        project_type: Optional[ProjectType] = None,
        project_characteristics: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None,
        competitive_data: Optional[Dict[str, Any]] = None,
        target_audience: Optional[Dict[str, Any]] = None,
        cost_structure: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Run monetization analysis and generate strategy document.

        This method performs full monetization analysis using MonetizationAnalyzer
        and then generates the strategy document.

        Args:
            project_type: Type of project being analyzed
            project_characteristics: Project features and capabilities
            market_data: Market size and trends data
            competitive_data: Competitor pricing and positioning
            target_audience: Target customer segment data
            cost_structure: Cost structure for pricing decisions

        Returns:
            Markdown string with monetization strategy
        """
        logger.info("[MonetizationStrategyGenerator] Running analysis and generating strategy")

        # Create analyzer with budget enforcer if available
        self._analyzer = MonetizationAnalyzer(budget_enforcer=self._budget_enforcer)

        # Check if we can proceed with analysis
        if not self._analyzer.can_analyze():
            logger.warning("Budget insufficient for full monetization analysis")
            return self._generate_budget_limited_guidance()

        # Run analysis
        result = self._analyzer.analyze(
            project_type=project_type,
            project_characteristics=project_characteristics,
            market_data=market_data,
            competitive_data=competitive_data,
            target_audience=target_audience,
            cost_structure=cost_structure,
        )

        # Generate from result
        return self.generate_from_analysis(result)

    def _generate_budget_limited_guidance(self) -> str:
        """Generate limited guidance when budget is insufficient."""
        return (
            "# Monetization Strategy\n\n"
            "## Notice\n\n"
            "Full monetization analysis was skipped due to budget constraints. "
            "Below is general guidance that may be applicable.\n\n"
            "## General Recommendations\n\n"
            "1. **Start with value-based pricing**: Price based on value delivered, not cost\n"
            "2. **Consider tiered pricing**: Offer multiple tiers to capture different segments\n"
            "3. **Validate early**: Test pricing with real customers before scaling\n"
            "4. **Monitor key metrics**: Track ARPU, LTV, CAC, and churn\n\n"
            "## Common Models\n\n"
            "- **Subscription**: Best for B2B SaaS and continuous value delivery\n"
            "- **Freemium**: Good for consumer apps with network effects\n"
            "- **Usage-based**: Ideal for APIs and variable usage patterns\n\n"
            "Run full analysis when budget allows for detailed recommendations.\n"
        )

    def get_analysis_result(self) -> Optional[MonetizationAnalysisResult]:
        """Get the analysis result if analysis was run.

        Returns:
            MonetizationAnalysisResult or None if not analyzed
        """
        if self._analyzer:
            return self._analyzer._analysis_result
        return None


class ProjectReadmeGenerator:
    """Generates comprehensive README.md from research artifacts.

    Produces a README that includes project overview, setup instructions,
    architecture overview, deployment guide, and monetization notes.
    """

    def generate(
        self,
        research_findings: Dict[str, Any],
        tech_stack: Dict[str, Any],
        project_brief: str,
        monetization_strategy: Optional[str] = None,
    ) -> str:
        """Generate comprehensive README.md content.

        Args:
            research_findings: Research findings dict with project context
            tech_stack: Tech stack proposal dict with technologies
            project_brief: Project brief description
            monetization_strategy: Optional monetization strategy content

        Returns:
            Markdown string with comprehensive README content
        """
        logger.info("[ProjectReadmeGenerator] Generating project README")

        content = ""

        # Project Title and Overview
        content += self._generate_overview_section(research_findings, project_brief)

        # Table of Contents
        content += self._generate_table_of_contents()

        # Project Details
        content += self._generate_project_details(research_findings)

        # Setup Instructions
        content += self._generate_setup_section(tech_stack)

        # Architecture Overview
        content += self._generate_architecture_section(tech_stack, research_findings)

        # Deployment Guide
        content += self._generate_deployment_section(tech_stack)

        # Monetization Notes
        if monetization_strategy:
            content += self._generate_monetization_section(monetization_strategy)

        # Getting Help and Contributing
        content += self._generate_support_section()

        return content

    def _generate_overview_section(
        self, research_findings: Dict[str, Any], project_brief: str
    ) -> str:
        """Generate project overview section.

        Args:
            research_findings: Research findings dict
            project_brief: Project brief description

        Returns:
            Markdown section string
        """
        section = "# Project README\n\n"

        if project_brief:
            section += f"{project_brief}\n\n"

        # Add market opportunity if available
        market_info = research_findings.get("market_opportunity", {})
        if market_info:
            tam = market_info.get("total_addressable_market")
            if tam:
                section += f"**Market Opportunity**: ${tam} addressable market\n\n"

        return section

    def _generate_table_of_contents(self) -> str:
        """Generate table of contents section.

        Returns:
            Markdown table of contents
        """
        return (
            "## Table of Contents\n\n"
            "- [Quick Start](#quick-start)\n"
            "- [Project Details](#project-details)\n"
            "- [Architecture](#architecture)\n"
            "- [Deployment](#deployment)\n"
            "- [Support](#support)\n\n"
        )

    def _generate_project_details(self, research_findings: Dict[str, Any]) -> str:
        """Generate project details section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Project Details\n\n"

        # Problem Statement
        problem = research_findings.get("problem_statement", "")
        if problem:
            section += f"### Problem\n\n{problem}\n\n"

        # Solution
        solution = research_findings.get("solution", "")
        if solution:
            section += f"### Solution\n\n{solution}\n\n"

        # Key Features
        features = research_findings.get("features", [])
        if features:
            section += "### Key Features\n\n"
            for feature in features:
                if isinstance(feature, dict):
                    name = feature.get("name", "Feature")
                    description = feature.get("description", "")
                    section += f"- **{name}**: {description}\n"
                else:
                    section += f"- {feature}\n"
            section += "\n"

        return section

    def _generate_setup_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate setup instructions section.

        Args:
            tech_stack: Tech stack proposal dict

        Returns:
            Markdown section string
        """
        section = "## Quick Start\n\n"

        # Prerequisites
        section += "### Prerequisites\n\n"

        languages = tech_stack.get("languages", [])
        frameworks = tech_stack.get("frameworks", [])
        tools = tech_stack.get("tools", [])

        if languages:
            section += "- "
            section += ", ".join(languages)
            section += "\n"

        if frameworks:
            section += "- Frameworks: "
            section += ", ".join(frameworks)
            section += "\n"

        if tools:
            section += "- Tools: "
            section += ", ".join(tools)
            section += "\n"

        section += "\n"

        # Installation
        section += "### Installation\n\n"

        package_manager = tech_stack.get("package_manager", "npm")
        if package_manager in ["npm", "yarn", "pnpm"]:
            section += f"```bash\n" f"{package_manager} install\n" f"```\n\n"
        elif package_manager == "pip":
            section += "```bash\n" "pip install -e .\n" "```\n\n"

        # Running the Project
        section += "### Running the Project\n\n"
        section += "```bash\n" f"{package_manager} start\n" "```\n\n"

        return section

    def _generate_architecture_section(
        self, tech_stack: Dict[str, Any], research_findings: Dict[str, Any]
    ) -> str:
        """Generate architecture overview section.

        Args:
            tech_stack: Tech stack proposal dict
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Architecture\n\n"

        # Architecture Pattern
        pattern = tech_stack.get("architecture_pattern", "")
        if pattern:
            section += f"**Architecture Pattern**: {pattern}\n\n"

        # Core Components
        components = research_findings.get("components", [])
        if components and isinstance(components, list):
            section += "### Core Components\n\n"
            for component in components:
                if isinstance(component, dict):
                    name = safe_get_string(component.get("name"), "Component")
                    description = safe_get_string(component.get("description"), "")
                    section += f"- **{name}**: {description}\n"
                else:
                    component_str = safe_get_string(component, "Component")
                    section += f"- {component_str}\n"
            section += "\n"

        # Technology Stack Details
        section += "### Technology Stack\n\n"

        frontend = tech_stack.get("frontend", [])
        if frontend and isinstance(frontend, list):
            frontend_strs = [safe_get_string(f, "Framework") for f in frontend]
            section += f"**Frontend**: {', '.join(frontend_strs)}\n\n"

        backend = tech_stack.get("backend", [])
        if backend and isinstance(backend, list):
            backend_strs = [safe_get_string(b, "Framework") for b in backend]
            section += f"**Backend**: {', '.join(backend_strs)}\n\n"

        database = tech_stack.get("database", [])
        if database and isinstance(database, list):
            database_strs = [safe_get_string(d, "Database") for d in database]
            section += f"**Database**: {', '.join(database_strs)}\n\n"

        return section

    def _generate_deployment_section(self, tech_stack: Dict[str, Any]) -> str:
        """Generate deployment guide section.

        Args:
            tech_stack: Tech stack proposal dict

        Returns:
            Markdown section string
        """
        section = "## Deployment\n\n"

        # Hosting Requirements
        hosting = tech_stack.get("hosting_requirements", [])
        if hosting:
            section += "### Hosting Requirements\n\n"
            for req in hosting:
                section += f"- {req}\n"
            section += "\n"

        # Environment Setup
        section += "### Environment Variables\n\n"
        section += (
            "Create a `.env` file in the project root with the following variables:\n\n"
            "```\n"
            "NODE_ENV=production\n"
            "API_KEY=your_api_key\n"
            "DATABASE_URL=your_database_url\n"
            "```\n\n"
        )

        # Deployment Steps
        section += "### Deployment Steps\n\n"
        section += (
            "1. Set up hosting environment\n"
            "2. Configure environment variables\n"
            "3. Build the project\n"
            "4. Deploy to hosting service\n"
            "5. Verify deployment\n\n"
        )

        return section

    def _generate_monetization_section(self, monetization_strategy: str) -> str:
        """Generate monetization notes section.

        Args:
            monetization_strategy: Monetization strategy content

        Returns:
            Markdown section string
        """
        return f"## Monetization Strategy\n\n{monetization_strategy}\n\n"

    def _generate_support_section(self) -> str:
        """Generate support and contributing section.

        Returns:
            Markdown section string
        """
        section = "## Support\n\n"

        section += (
            "### Getting Help\n\n"
            "- Check the documentation\n"
            "- Open an issue on GitHub\n"
            "- Contact the development team\n\n"
        )

        section += (
            "### Contributing\n\n"
            "Contributions are welcome! Please feel free to submit a Pull Request.\n\n"
        )

        section += (
            "## License\n\n"
            "This project is licensed under the MIT License - "
            "see the LICENSE file for details.\n"
        )

        return section


class ProjectBriefGenerator:
    """Generates comprehensive PROJECT_BRIEF.md with monetization guidance.

    Produces a project brief that includes technical requirements, feature
    scope, and comprehensive monetization strategy with revenue models,
    pricing strategy, market positioning, and unit economics analysis.

    Can optionally include SOT (Source of Truth) document summaries to provide
    historical context from BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md.
    """

    def __init__(
        self,
        sot_summarizer: Optional[SOTSummarizer] = None,
        include_sot_context: bool = True,
    ):
        """Initialize the project brief generator.

        Args:
            sot_summarizer: Optional SOTSummarizer instance for extracting
                            context from SOT documents.
            include_sot_context: Whether to include SOT context by default.
        """
        self._sot_summarizer = sot_summarizer
        self._include_sot_context = include_sot_context

    def generate(
        self,
        research_findings: Dict[str, Any],
        tech_stack: Optional[Dict[str, Any]] = None,
        competitive_data: Optional[Dict[str, Any]] = None,
        include_sot_context: Optional[bool] = None,
        sot_summary: Optional[SOTSummary] = None,
    ) -> str:
        """Generate comprehensive project brief with monetization.

        Args:
            research_findings: Research findings dict with project context
            tech_stack: Optional tech stack proposal dict
            competitive_data: Optional competitive analysis data
            include_sot_context: Whether to include SOT context. Overrides instance default.
            sot_summary: Pre-computed SOT summary. If not provided and SOT context
                        is requested, will attempt to generate using sot_summarizer.

        Returns:
            Markdown string with comprehensive project brief
        """
        logger.info("[ProjectBriefGenerator] Generating project brief with monetization")

        content = "# Project Brief\n\n"

        # Executive Summary
        content += self._generate_executive_summary(research_findings)

        # Technical Requirements
        content += self._generate_technical_section(research_findings, tech_stack)

        # Feature Scope
        content += self._generate_feature_scope(research_findings)

        # SOT Context (if requested)
        should_include_sot = (
            include_sot_context if include_sot_context is not None else self._include_sot_context
        )
        if should_include_sot:
            content += self._generate_sot_context_section(research_findings, sot_summary)

        # Monetization Strategy
        content += self.generate_monetization(research_findings)

        # Deployment Architecture
        content += self._generate_deployment_architecture(research_findings, tech_stack)

        # Hosting & Infrastructure Costs
        content += self._generate_hosting_costs(research_findings)

        # Market Positioning
        content += self.generate_market_positioning(research_findings, competitive_data or {})

        # Market Entry Plan
        content += self._generate_market_entry_plan(research_findings)

        # Unit Economics
        content += self.analyze_unit_economics(research_findings)

        # Growth Strategy
        content += self._generate_growth_strategy(research_findings)

        # Risk Assessment
        content += self._generate_risk_assessment(research_findings)

        return content

    def _generate_sot_context_section(
        self,
        research_findings: Dict[str, Any],
        sot_summary: Optional[SOTSummary] = None,
    ) -> str:
        """Generate SOT context section for project brief.

        Includes summaries from BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md
        to provide historical context for project decisions.

        Args:
            research_findings: Research findings dict (may contain sot_context)
            sot_summary: Pre-computed SOT summary

        Returns:
            Markdown section string with SOT context
        """
        section = "## Historical Context (SOT)\n\n"

        # Check if SOT context is in research_findings
        sot_context = research_findings.get("sot_context", {})

        # Use provided summary, or try to generate one
        if sot_summary:
            section += sot_summary.to_markdown()
            return section + "\n"

        # Try to use sot_summarizer if available
        if self._sot_summarizer:
            try:
                summary = self._sot_summarizer.summarize()
                section += summary.to_markdown()
                return section + "\n"
            except Exception as e:
                logger.warning(f"[ProjectBriefGenerator] Error generating SOT summary: {e}")

        # Fall back to sot_context in research_findings
        if sot_context:
            section += self._format_sot_context_from_dict(sot_context)
            return section + "\n"

        # No SOT context available
        section += "*No historical context available from SOT documents.*\n\n"
        return section

    def _format_sot_context_from_dict(self, sot_context: Dict[str, Any]) -> str:
        """Format SOT context from dictionary.

        Args:
            sot_context: Dictionary containing SOT context data

        Returns:
            Markdown formatted string
        """
        parts = []

        # Build History
        build_history = sot_context.get("build_history", {})
        if build_history:
            parts.append("### Build History Context\n")
            total_builds = build_history.get("total_builds", 0)
            recent_summary = build_history.get("recent_summary", "")
            if total_builds:
                parts.append(f"{total_builds} builds documented.")
            if recent_summary:
                parts.append(f" {recent_summary}")
            parts.append("\n")

            recent_builds = build_history.get("recent_builds", [])
            if recent_builds:
                parts.append("\n**Recent Builds:**\n")
                for build in recent_builds[:5]:
                    build_id = build.get("id", "Unknown")
                    date = build.get("date", "")
                    summary = build.get("summary", "")[:100]
                    parts.append(f"- **{build_id}** ({date}): {summary}...\n")

        # Architecture Decisions
        arch_decisions = sot_context.get("architecture_decisions", {})
        if arch_decisions:
            parts.append("\n### Architecture Decisions Context\n")
            total_decisions = arch_decisions.get("total_decisions", 0)
            summary = arch_decisions.get("summary", "")
            if total_decisions:
                parts.append(f"{total_decisions} decisions documented.")
            if summary:
                parts.append(f" {summary}")
            parts.append("\n")

            key_decisions = arch_decisions.get("key_decisions", [])
            if key_decisions:
                parts.append("\n**Key Decisions:**\n")
                for dec in key_decisions[:5]:
                    dec_id = dec.get("id", "Unknown")
                    title = dec.get("title", "")
                    status = dec.get("status", "")
                    status_icon = "✅" if status == "Implemented" else "🧭"
                    parts.append(f"- **{dec_id}** {status_icon}: {title}\n")

        return "".join(parts) if parts else "*No SOT context data available.*\n"

    def _generate_executive_summary(self, research_findings: Dict[str, Any]) -> str:
        """Generate executive summary section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Executive Summary\n\n"

        # Problem Statement
        problem = research_findings.get("problem_statement", "")
        if problem:
            section += f"**Problem**: {problem}\n\n"

        # Solution
        solution = research_findings.get("solution", "")
        if solution:
            section += f"**Solution**: {solution}\n\n"

        # Market Opportunity
        market = research_findings.get("market_opportunity", {})
        if market:
            tam = market.get("total_addressable_market", "")
            if tam:
                section += f"**Market Opportunity**: {tam} total addressable market\n\n"

        # Target Audience
        target = research_findings.get("target_audience", "")
        if target:
            section += f"**Target Audience**: {target}\n\n"

        return section

    def _generate_technical_section(
        self,
        research_findings: Dict[str, Any],
        tech_stack: Optional[Dict[str, Any]],
    ) -> str:
        """Generate technical requirements section.

        Args:
            research_findings: Research findings dict
            tech_stack: Tech stack proposal dict

        Returns:
            Markdown section string
        """
        section = "## Technical Requirements\n\n"

        if tech_stack:
            # Languages and Frameworks
            languages = tech_stack.get("languages", [])
            if languages:
                section += f"**Languages**: {', '.join(languages)}\n\n"

            frameworks = tech_stack.get("frameworks", [])
            if frameworks:
                section += f"**Frameworks**: {', '.join(frameworks)}\n\n"

            # Architecture
            architecture = tech_stack.get("architecture_pattern", "")
            if architecture:
                section += f"**Architecture**: {architecture}\n\n"

            # Infrastructure
            infrastructure = tech_stack.get("infrastructure", [])
            if infrastructure:
                section += "**Infrastructure**:\n"
                for item in infrastructure:
                    section += f"- {item}\n"
                section += "\n"

        # Technical constraints from research
        constraints = research_findings.get("technical_constraints", [])
        if constraints:
            section += "**Technical Constraints**:\n"
            for constraint in constraints:
                section += f"- {constraint}\n"
            section += "\n"

        return section

    def _generate_feature_scope(self, research_findings: Dict[str, Any]) -> str:
        """Generate feature scope section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Feature Scope\n\n"

        # Core Features
        features = research_findings.get("features", [])
        if features:
            section += "### Core Features\n\n"
            for feature in features:
                if isinstance(feature, dict):
                    name = feature.get("name", "Feature")
                    description = feature.get("description", "")
                    priority = feature.get("priority", "")
                    section += f"- **{name}**"
                    if priority:
                        section += f" [{priority}]"
                    if description:
                        section += f": {description}"
                    section += "\n"
                else:
                    section += f"- {feature}\n"
            section += "\n"

        # MVP Scope
        mvp = research_findings.get("mvp_features", [])
        if mvp:
            section += "### MVP Scope\n\n"
            for item in mvp:
                section += f"- {item}\n"
            section += "\n"

        # Future Features
        future = research_findings.get("future_features", [])
        if future:
            section += "### Future Features\n\n"
            for item in future:
                section += f"- {item}\n"
            section += "\n"

        return section

    def generate_monetization(self, research_findings: Dict[str, Any]) -> str:
        """Generate monetization strategy section.

        Includes revenue models, pricing strategy, and pricing tiers.

        Args:
            research_findings: Research findings dict with monetization data

        Returns:
            Markdown section string with monetization strategy
        """
        section = "## Monetization Strategy\n\n"

        monetization = research_findings.get("monetization", {})
        if not monetization:
            # Provide default guidance if no monetization data
            section += self._generate_default_monetization_guidance()
            return section

        # Revenue Models
        models = monetization.get("revenue_models", [])
        if models:
            section += "### Revenue Models\n\n"
            for model in models:
                if isinstance(model, dict):
                    name = model.get("name", "Model")
                    description = model.get("description", "")
                    fit_score = model.get("fit_score", "")
                    section += f"**{name}**"
                    if fit_score:
                        section += f" (Fit: {fit_score}/10)"
                    section += "\n"
                    if description:
                        section += f"{description}\n"
                    section += "\n"
                else:
                    section += f"- {model}\n"

        # Primary Revenue Model
        primary = monetization.get("primary_model", "")
        if primary:
            section += f"**Primary Model**: {primary}\n\n"

        # Pricing Strategy
        pricing = monetization.get("pricing_strategy", {})
        if pricing:
            section += "### Pricing Strategy\n\n"
            strategy_type = pricing.get("type", "")
            if strategy_type:
                section += f"**Strategy**: {strategy_type}\n\n"

            rationale = pricing.get("rationale", "")
            if rationale:
                section += f"**Rationale**: {rationale}\n\n"

        # Pricing Tiers
        tiers = monetization.get("pricing_tiers", [])
        if tiers:
            section += "### Pricing Tiers\n\n"
            section += "| Tier | Price | Features | Target |\n"
            section += "|------|-------|----------|--------|\n"
            for tier in tiers:
                name = tier.get("name", "")
                price = tier.get("price", "")
                features = tier.get("features", "")
                if isinstance(features, list):
                    features = ", ".join(features[:3])
                    if len(tier.get("features", [])) > 3:
                        features += "..."
                target = tier.get("target", "")
                section += f"| {name} | {price} | {features} | {target} |\n"
            section += "\n"

        return section

    def _generate_default_monetization_guidance(self) -> str:
        """Generate default monetization guidance when no data available.

        Returns:
            Markdown string with default guidance
        """
        return (
            "### Revenue Model Options\n\n"
            "Consider the following monetization approaches:\n\n"
            "1. **Subscription (SaaS)**: Recurring revenue, predictable income\n"
            "   - Best for: B2B tools, continuous value delivery\n"
            "   - Typical conversion: 2-5% free to paid\n\n"
            "2. **Freemium**: Free tier with premium upgrades\n"
            "   - Best for: Consumer apps, network effects\n"
            "   - Typical conversion: 1-10% to paid\n\n"
            "3. **Usage-Based**: Pay per use/API calls\n"
            "   - Best for: APIs, infrastructure services\n"
            "   - Aligns cost with value delivered\n\n"
            "4. **One-Time Purchase**: Single payment\n"
            "   - Best for: Desktop apps, plugins, templates\n"
            "   - Lower LTV but simpler\n\n"
            "5. **Marketplace/Commission**: Take percentage of transactions\n"
            "   - Best for: Platforms connecting buyers/sellers\n"
            "   - Typical rate: 5-20%\n\n"
        )

    def generate_market_positioning(
        self,
        research_findings: Dict[str, Any],
        competitive_data: Dict[str, Any],
    ) -> str:
        """Generate market positioning analysis section.

        Includes competitive positioning, differentiation strategy,
        and target market analysis.

        Args:
            research_findings: Research findings dict
            competitive_data: Competitive analysis data

        Returns:
            Markdown section string with market positioning
        """
        section = "## Market Positioning\n\n"

        # Target Market
        market = research_findings.get("market_opportunity", {})
        if market:
            section += "### Target Market\n\n"

            tam = market.get("total_addressable_market", "")
            sam = market.get("serviceable_addressable_market", "")
            som = market.get("serviceable_obtainable_market", "")

            if tam:
                section += f"- **TAM (Total Addressable Market)**: {tam}\n"
            if sam:
                section += f"- **SAM (Serviceable Addressable Market)**: {sam}\n"
            if som:
                section += f"- **SOM (Serviceable Obtainable Market)**: {som}\n"
            section += "\n"

            segments = market.get("segments", [])
            if segments:
                section += "**Target Segments**:\n"
                for segment in segments:
                    if isinstance(segment, dict):
                        name = segment.get("name", "")
                        size = segment.get("size", "")
                        section += f"- {name}"
                        if size:
                            section += f" ({size})"
                        section += "\n"
                    else:
                        section += f"- {segment}\n"
                section += "\n"

        # Competitive Landscape
        competitors = competitive_data.get("competitors", [])
        if competitors:
            section += "### Competitive Landscape\n\n"
            section += "| Competitor | Strengths | Weaknesses | Price Point |\n"
            section += "|------------|-----------|------------|-------------|\n"
            for comp in competitors:
                name = comp.get("name", "Unknown")
                strengths = comp.get("strengths", [])
                if isinstance(strengths, list):
                    strengths = ", ".join(strengths[:2])
                weaknesses = comp.get("weaknesses", [])
                if isinstance(weaknesses, list):
                    weaknesses = ", ".join(weaknesses[:2])
                price = comp.get("price_point", "")
                section += f"| {name} | {strengths} | {weaknesses} | {price} |\n"
            section += "\n"

        # Differentiation Strategy
        differentiation = research_findings.get("differentiation", {})
        if differentiation:
            section += "### Differentiation Strategy\n\n"

            unique_value = differentiation.get("unique_value_proposition", "")
            if unique_value:
                section += f"**Unique Value Proposition**: {unique_value}\n\n"

            advantages = differentiation.get("competitive_advantages", [])
            if advantages:
                section += "**Competitive Advantages**:\n"
                for adv in advantages:
                    section += f"- {adv}\n"
                section += "\n"

            moat = differentiation.get("moat", "")
            if moat:
                section += f"**Competitive Moat**: {moat}\n\n"

        # Positioning Statement
        positioning = research_findings.get("positioning_statement", "")
        if positioning:
            section += f"### Positioning Statement\n\n> {positioning}\n\n"

        return section

    def analyze_unit_economics(self, research_findings: Dict[str, Any]) -> str:
        """Analyze and generate unit economics section.

        Includes CAC, LTV, margins, and payback period analysis.

        Args:
            research_findings: Research findings dict with economics data

        Returns:
            Markdown section string with unit economics analysis
        """
        section = "## Unit Economics\n\n"

        economics = research_findings.get("unit_economics", {})
        if not economics:
            # Provide framework for analysis
            section += self._generate_unit_economics_framework()
            return section

        # Key Metrics
        section += "### Key Metrics\n\n"

        cac = economics.get("customer_acquisition_cost", "")
        if cac:
            section += f"- **CAC (Customer Acquisition Cost)**: {cac}\n"

        ltv = economics.get("lifetime_value", "")
        if ltv:
            section += f"- **LTV (Lifetime Value)**: {ltv}\n"

        ltv_cac_ratio = economics.get("ltv_cac_ratio", "")
        if ltv_cac_ratio:
            section += f"- **LTV:CAC Ratio**: {ltv_cac_ratio}\n"

        payback = economics.get("payback_period", "")
        if payback:
            section += f"- **Payback Period**: {payback}\n"

        section += "\n"

        # Margin Analysis
        margins = economics.get("margins", {})
        if margins:
            section += "### Margin Analysis\n\n"

            gross = margins.get("gross_margin", "")
            if gross:
                section += f"- **Gross Margin**: {gross}\n"

            contribution = margins.get("contribution_margin", "")
            if contribution:
                section += f"- **Contribution Margin**: {contribution}\n"

            net = margins.get("net_margin", "")
            if net:
                section += f"- **Net Margin**: {net}\n"

            section += "\n"

        # Revenue Projections
        projections = economics.get("projections", {})
        if projections:
            section += "### Revenue Projections\n\n"
            section += "| Timeframe | Revenue | Users | MRR |\n"
            section += "|-----------|---------|-------|-----|\n"

            for timeframe, data in projections.items():
                if isinstance(data, dict):
                    revenue = data.get("revenue", "")
                    users = data.get("users", "")
                    mrr = data.get("mrr", "")
                    section += f"| {timeframe} | {revenue} | {users} | {mrr} |\n"

            section += "\n"

        # Break-even Analysis
        breakeven = economics.get("breakeven", {})
        if breakeven:
            section += "### Break-even Analysis\n\n"

            point = breakeven.get("point", "")
            if point:
                section += f"- **Break-even Point**: {point}\n"

            timeline = breakeven.get("timeline", "")
            if timeline:
                section += f"- **Expected Timeline**: {timeline}\n"

            assumptions = breakeven.get("assumptions", [])
            if assumptions:
                section += "- **Key Assumptions**:\n"
                for assumption in assumptions:
                    section += f"  - {assumption}\n"

            section += "\n"

        return section

    def _generate_unit_economics_framework(self) -> str:
        """Generate unit economics analysis framework.

        Returns:
            Markdown string with framework guidance
        """
        return (
            "### Key Metrics to Track\n\n"
            "**Customer Acquisition Cost (CAC)**:\n"
            "- Total marketing & sales spend / New customers acquired\n"
            "- Target: Below 1/3 of LTV\n\n"
            "**Lifetime Value (LTV)**:\n"
            "- Average revenue per user × Average customer lifespan\n"
            "- Or: ARPU / Churn rate (for subscription)\n\n"
            "**LTV:CAC Ratio**:\n"
            "- Healthy: 3:1 or higher\n"
            "- Below 1:1 indicates unsustainable growth\n\n"
            "**Payback Period**:\n"
            "- Months to recover CAC\n"
            "- Target: Under 12 months for SaaS\n\n"
            "### Margin Targets\n\n"
            "| Business Type | Gross Margin | Net Margin |\n"
            "|---------------|--------------|------------|\n"
            "| SaaS | 70-85% | 10-20% |\n"
            "| Marketplace | 20-40% | 5-15% |\n"
            "| E-commerce | 30-50% | 5-10% |\n"
            "| Services | 50-70% | 15-25% |\n\n"
        )

    def _generate_growth_strategy(self, research_findings: Dict[str, Any]) -> str:
        """Generate growth strategy section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Growth Strategy\n\n"

        growth = research_findings.get("growth_strategy", {})
        if not growth:
            return section + "*Growth strategy to be defined based on market validation.*\n\n"

        # Acquisition Channels
        channels = growth.get("acquisition_channels", [])
        if channels:
            section += "### Acquisition Channels\n\n"
            for channel in channels:
                if isinstance(channel, dict):
                    name = channel.get("name", "")
                    priority = channel.get("priority", "")
                    section += f"- **{name}**"
                    if priority:
                        section += f" [{priority}]"
                    section += "\n"
                else:
                    section += f"- {channel}\n"
            section += "\n"

        # Growth Levers
        levers = growth.get("growth_levers", [])
        if levers:
            section += "### Growth Levers\n\n"
            for lever in levers:
                section += f"- {lever}\n"
            section += "\n"

        # Expansion Strategy
        expansion = growth.get("expansion", "")
        if expansion:
            section += f"### Expansion Strategy\n\n{expansion}\n\n"

        return section

    def _generate_deployment_architecture(
        self, research_findings: Dict[str, Any], tech_stack: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate deployment architecture section.

        Args:
            research_findings: Research findings dict
            tech_stack: Optional tech stack proposal dict

        Returns:
            Markdown section string
        """
        section = "## Deployment Architecture\n\n"

        deployment = research_findings.get("deployment_architecture", {})
        if not deployment and not tech_stack:
            section += "### Recommended Deployment Options\n\n"
            section += "#### Docker & Kubernetes\n"
            section += "- **Best for**: Scalable, containerized deployments\n"
            section += "- **Complexity**: Medium to High\n"
            section += "- **Cost**: Moderate (depends on infrastructure)\n"
            section += "- **Scaling**: Horizontal scaling with orchestration\n\n"

            section += "#### Serverless (AWS Lambda, Google Cloud Functions)\n"
            section += "- **Best for**: Event-driven, variable load applications\n"
            section += "- **Complexity**: Low to Medium\n"
            section += "- **Cost**: Pay-per-execution\n"
            section += "- **Scaling**: Automatic, built-in\n\n"

            section += "#### Platform-as-a-Service (Heroku, Vercel)\n"
            section += "- **Best for**: Rapid development and deployment\n"
            section += "- **Complexity**: Low\n"
            section += "- **Cost**: Fixed monthly tiers\n"
            section += "- **Scaling**: Limited, may require migration for enterprise\n\n"

            section += "#### Virtual Machines (AWS EC2, Google Compute Engine)\n"
            section += "- **Best for**: Full control, traditional applications\n"
            section += "- **Complexity**: High\n"
            section += "- **Cost**: Predictable, hourly billing\n"
            section += "- **Scaling**: Manual or with auto-scaling groups\n\n"

            return section

        # Add specific deployment details if available
        if deployment:
            section += "### Architecture Overview\n\n"
            if "type" in deployment:
                section += f"**Deployment Type**: {deployment['type']}\n\n"
            if "cloud_provider" in deployment:
                section += f"**Cloud Provider**: {deployment['cloud_provider']}\n\n"

            if "components" in deployment:
                section += "### Components\n\n"
                for component in deployment["components"]:
                    if isinstance(component, dict):
                        name = component.get("name", "Unknown")
                        description = component.get("description", "")
                        technology = component.get("technology", "")
                        section += f"- **{name}**: {description}"
                        if technology:
                            section += f" ({technology})"
                        section += "\n"
                section += "\n"

            if "scaling_strategy" in deployment:
                section += "### Scaling Strategy\n\n"
                strategy = deployment["scaling_strategy"]
                if isinstance(strategy, dict):
                    if "horizontal" in strategy:
                        section += f"- **Horizontal Scaling**: {strategy['horizontal']}\n"
                    if "vertical" in strategy:
                        section += f"- **Vertical Scaling**: {strategy['vertical']}\n"
                else:
                    section += f"{strategy}\n"
                section += "\n"

            if "high_availability" in deployment:
                section += "### High Availability\n\n"
                ha = deployment["high_availability"]
                if isinstance(ha, dict):
                    if "replicas" in ha:
                        section += f"- **Replicas**: {ha['replicas']}\n"
                    if "failover" in ha:
                        section += f"- **Failover**: {ha['failover']}\n"
                else:
                    section += f"{ha}\n"
                section += "\n"

        return section

    def _generate_hosting_costs(self, research_findings: Dict[str, Any]) -> str:
        """Generate hosting and infrastructure costs section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Hosting & Infrastructure Costs\n\n"

        costs = research_findings.get("infrastructure_costs", {})
        if not costs:
            section += "### Cost Estimation Framework\n\n"
            section += "#### Typical Monthly Infrastructure Costs by Scale\n\n"
            section += "| Scale | Monthly Cost Range | Compute | Storage | Data Transfer |\n"
            section += "|-------|-------------------|---------|---------|----------------|\n"
            section += "| MVP (0-1k users) | $50-500 | $30-300 | $5-50 | $10-150 |\n"
            section += "| Growth (1k-10k users) | $500-5,000 | $300-3k | $50-500 | $100-1.5k |\n"
            section += "| Scale (10k-100k users) | $5k-50k | $3k-30k | $500-5k | $1.5k-15k |\n"
            section += "| Enterprise (100k+ users) | $50k+ | $30k+ | $5k+ | $15k+ |\n\n"

            section += "### Cost Optimization Tips\n\n"
            section += "- **Reserved Instances**: 30-40% savings with 1-3 year commitments\n"
            section += "- **Spot Instances**: 70-90% discount for non-critical workloads\n"
            section += "- **Auto-scaling**: Scale down during low-traffic periods\n"
            section += "- **CDN Usage**: Reduce bandwidth costs with content delivery networks\n"
            section += "- **Database Optimization**: Use read replicas and connection pooling\n\n"

            return section

        # Add specific cost details if available
        section += "### Monthly Cost Breakdown\n\n"

        if "breakdown" in costs:
            breakdown = costs["breakdown"]
            section += "| Component | Monthly Cost | Notes |\n"
            section += "|-----------|--------------|-------|\n"

            for component, cost_info in breakdown.items():
                if isinstance(cost_info, dict):
                    amount = cost_info.get("amount", "$0")
                    notes = cost_info.get("notes", "")
                    section += f"| {component} | {amount} | {notes} |\n"
                else:
                    section += f"| {component} | {cost_info} | |\n"
            section += "\n"

        if "estimated_total" in costs:
            section += f"**Estimated Monthly Total**: {costs['estimated_total']}\n\n"

        if "cost_per_user" in costs:
            section += f"**Cost Per User**: {costs['cost_per_user']}\n\n"

        if "optimization_opportunities" in costs:
            section += "### Optimization Opportunities\n\n"
            for opportunity in costs["optimization_opportunities"]:
                if isinstance(opportunity, dict):
                    title = opportunity.get("title", "Opportunity")
                    savings = opportunity.get("savings", "")
                    implementation = opportunity.get("implementation", "")
                    section += f"- **{title}**: {savings}\n"
                    if implementation:
                        section += f"  - Implementation: {implementation}\n"
                else:
                    section += f"- {opportunity}\n"
            section += "\n"

        return section

    def _generate_market_entry_plan(self, research_findings: Dict[str, Any]) -> str:
        """Generate market entry plan section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Market Entry Plan\n\n"

        plan = research_findings.get("market_entry_plan", {})
        if not plan:
            section += "### Go-To-Market Strategy Framework\n\n"
            section += "#### Phase 1: Preparation (Weeks 1-4)\n\n"
            section += "- Finalize product MVP\n"
            section += "- Complete regulatory and legal checks\n"
            section += "- Prepare marketing materials\n"
            section += "- Set up analytics and tracking\n\n"

            section += "#### Phase 2: Soft Launch (Weeks 5-8)\n\n"
            section += "- Release to limited user group (beta)\n"
            section += "- Gather initial feedback\n"
            section += "- Make rapid iterations\n"
            section += "- Document edge cases and bugs\n\n"

            section += "#### Phase 3: Public Launch (Weeks 9-12)\n\n"
            section += "- Announce to target market\n"
            section += "- Execute marketing campaign\n"
            section += "- Scale customer support\n"
            section += "- Monitor performance and metrics\n\n"

            section += "#### Phase 4: Growth (Month 4+)\n\n"
            section += "- Expand to adjacent markets\n"
            section += "- Optimize conversion funnel\n"
            section += "- Build partnership ecosystem\n"
            section += "- Plan next feature roadmap\n\n"

            return section

        # Add specific market entry plan if available
        if "launch_timeline" in plan:
            section += "### Launch Timeline\n\n"
            timeline = plan["launch_timeline"]
            for phase, details in timeline.items():
                if isinstance(details, dict):
                    duration = details.get("duration", "")
                    activities = details.get("activities", [])
                    section += f"**{phase}**"
                    if duration:
                        section += f" ({duration})"
                    section += "\n\n"

                    for activity in activities:
                        section += f"- {activity}\n"
                    section += "\n"
                else:
                    section += f"**{phase}**: {details}\n\n"

        if "target_segments" in plan:
            section += "### Target Customer Segments\n\n"
            segments = plan["target_segments"]
            for segment in segments:
                if isinstance(segment, dict):
                    name = segment.get("name", "Segment")
                    size = segment.get("size", "")
                    characteristics = segment.get("characteristics", [])
                    section += f"**{name}**"
                    if size:
                        section += f" (~{size} market)"
                    section += "\n\n"

                    for char in characteristics:
                        section += f"- {char}\n"
                    section += "\n"
                else:
                    section += f"- {segment}\n"
            section += "\n"

        if "channels" in plan:
            section += "### Distribution Channels\n\n"
            channels = plan["channels"]
            section += "| Channel | Priority | Effort | Expected Reach |\n"
            section += "|---------|----------|--------|----------------|\n"

            for channel in channels:
                if isinstance(channel, dict):
                    name = channel.get("name", "Channel")
                    priority = channel.get("priority", "Medium")
                    effort = channel.get("effort", "Medium")
                    reach = channel.get("reach", "TBD")
                    section += f"| {name} | {priority} | {effort} | {reach} |\n"
            section += "\n"

        if "success_metrics" in plan:
            section += "### Success Metrics\n\n"
            metrics = plan["success_metrics"]
            for metric in metrics:
                if isinstance(metric, dict):
                    name = metric.get("name", "Metric")
                    target = metric.get("target", "TBD")
                    timeline = metric.get("timeline", "30 days")
                    section += f"- **{name}**: {target} ({timeline})\n"
                else:
                    section += f"- {metric}\n"
            section += "\n"

        return section

    def _generate_risk_assessment(self, research_findings: Dict[str, Any]) -> str:
        """Generate risk assessment section.

        Args:
            research_findings: Research findings dict

        Returns:
            Markdown section string
        """
        section = "## Risk Assessment\n\n"

        risks = research_findings.get("risks", [])
        if not risks:
            return section + "*Risk assessment to be completed.*\n\n"

        section += "| Risk | Impact | Likelihood | Mitigation |\n"
        section += "|------|--------|------------|------------|\n"

        for risk in risks:
            if isinstance(risk, dict):
                name = risk.get("name", "Unknown")
                impact = risk.get("impact", "Medium")
                likelihood = risk.get("likelihood", "Medium")
                mitigation = risk.get("mitigation", "")
                section += f"| {name} | {impact} | {likelihood} | {mitigation} |\n"
            else:
                section += f"| {risk} | Medium | Medium | TBD |\n"

        section += "\n"
        return section


class MCPToolRecommendationGenerator:
    """Generates MCP_INTEGRATIONS.md with recommended tools and integration guidance.

    Produces a comprehensive guide for integrating available MCP tools into
    the project, including installation instructions and usage examples.
    """

    def generate(self, mcp_scan_result: Optional[MCPScanResult] = None) -> str:
        """Generate MCP tool recommendations markdown.

        Args:
            mcp_scan_result: Optional MCPScanResult with available tools

        Returns:
            Markdown string with MCP integration recommendations
        """
        logger.info("[MCPToolRecommendationGenerator] Generating MCP tool recommendations")

        content = "# MCP Tool Integrations\n\n"

        if not mcp_scan_result or mcp_scan_result.total_matches == 0:
            content += self._generate_no_tools_section()
            return content

        # Summary
        content += self._generate_summary_section(mcp_scan_result)

        # Recommended Tools
        content += self._generate_recommended_tools_section(mcp_scan_result)

        # Installation Instructions
        content += self._generate_installation_section(mcp_scan_result)

        # Integration Examples
        content += self._generate_integration_examples_section(mcp_scan_result)

        # Requirements by Feature
        content += self._generate_requirements_mapping_section(mcp_scan_result)

        return content

    def _generate_no_tools_section(self) -> str:
        """Generate section when no MCP tools found.

        Returns:
            Markdown section string
        """
        return (
            "## No Recommended Tools Found\n\n"
            "The project requirements don't directly match available MCP tools. "
            "Consider:\n\n"
            "- Reviewing project requirements for integration opportunities\n"
            "- Implementing custom MCP tools for specialized needs\n"
            "- Checking back when new MCP tools become available\n\n"
        )

    def _generate_summary_section(self, mcp_scan_result: MCPScanResult) -> str:
        """Generate summary of MCP scan results.

        Args:
            mcp_scan_result: MCPScanResult with tools

        Returns:
            Markdown section string
        """
        section = "## Available Tools Summary\n\n"

        section += (
            f"**Scan Date**: {mcp_scan_result.scan_timestamp or 'Unknown'}\n"
            f"**Project Type**: {mcp_scan_result.project_type}\n"
            f"**Total Tools Found**: {mcp_scan_result.total_matches}\n\n"
        )

        # Breakdown by requirement
        if mcp_scan_result.matches_by_requirement:
            section += "### Matches by Requirement\n\n"
            for requirement, tools in mcp_scan_result.matches_by_requirement.items():
                section += f"- **{requirement}**: {len(tools)} tool(s)\n"
            section += "\n"

        return section

    def _generate_recommended_tools_section(self, mcp_scan_result: MCPScanResult) -> str:
        """Generate detailed tool recommendations.

        Args:
            mcp_scan_result: MCPScanResult with tools

        Returns:
            Markdown section string
        """
        section = "## Recommended Tools\n\n"

        for tool in mcp_scan_result.discovered_tools:
            section += self._generate_tool_card(tool)

        return section

    def _generate_tool_card(self, tool: Any) -> str:
        """Generate a detailed card for a single tool.

        Args:
            tool: MCPToolDescriptor

        Returns:
            Markdown section string
        """
        card = f"### {tool.name}\n\n"
        card += f"{tool.description}\n\n"

        # Metadata
        card += f"- **Maturity**: {tool.maturity.value if hasattr(tool.maturity, 'value') else tool.maturity}\n"
        card += f"- **Maintainer**: {tool.maintainer.value if hasattr(tool.maintainer, 'value') else tool.maintainer}\n"
        card += f"- **Installation Difficulty**: {tool.installation_difficulty}\n"
        card += f"- **Async Support**: {'Yes' if tool.support_async else 'No'}\n\n"

        # Capabilities
        if tool.capabilities:
            card += "**Capabilities**:\n"
            for cap in tool.capabilities:
                card += f"- {cap.name}: {cap.description}\n"
            card += "\n"

        # Links
        if tool.npm_package or tool.github_url or tool.documentation_url:
            card += "**Resources**:\n"
            if tool.npm_package:
                card += f"- NPM: `{tool.npm_package}`\n"
            if tool.github_url:
                card += f"- GitHub: [{tool.github_url}]({tool.github_url})\n"
            if tool.documentation_url:
                card += f"- Docs: [{tool.documentation_url}]({tool.documentation_url})\n"
            card += "\n"

        # Requirements
        if tool.requirements:
            card += "**Requirements**:\n"
            for req_key, req_val in tool.requirements.items():
                card += f"- {req_key}: {req_val}\n"
            card += "\n"

        return card

    def _generate_installation_section(self, mcp_scan_result: MCPScanResult) -> str:
        """Generate installation instructions.

        Args:
            mcp_scan_result: MCPScanResult with tools

        Returns:
            Markdown section string
        """
        section = "## Installation Instructions\n\n"

        section += "### Quick Start\n\n"
        section += "MCP tools can be installed via npm for Node.js environments:\n\n"

        for tool in mcp_scan_result.discovered_tools:
            if tool.npm_package:
                section += f"**{tool.name}**:\n"
                section += f"```bash\nnpm install {tool.npm_package}\n```\n\n"

        section += "### Configuration\n\n"
        section += (
            "Each MCP tool requires specific configuration. Refer to the "
            "documentation for setup details.\n\n"
        )

        return section

    def _generate_integration_examples_section(self, mcp_scan_result: MCPScanResult) -> str:
        """Generate integration examples.

        Args:
            mcp_scan_result: MCPScanResult with tools

        Returns:
            Markdown section string
        """
        section = "## Integration Examples\n\n"

        section += "### General Integration Pattern\n\n"
        section += (
            "```javascript\n"
            "import { initializeMCP } from '@modelcontextprotocol/sdk';\n\n"
            "const mcp = await initializeMCP({\n"
            "  tools: [\n"
            "    // Add enabled tools here\n"
            "  ]\n"
            "});\n"
            "```\n\n"
        )

        section += "### Use Case Examples\n\n"

        # Group tools by capability tags
        capability_groups: Dict[str, List[Any]] = {}
        for tool in mcp_scan_result.discovered_tools:
            for tag in tool.tags:
                if tag not in capability_groups:
                    capability_groups[tag] = []
                if tool not in capability_groups[tag]:
                    capability_groups[tag].append(tool)

        for capability, tools in sorted(capability_groups.items()):
            section += f"#### {capability.title()}\n\n"
            for tool in tools[:2]:  # Show first 2 tools per capability
                section += f"- **{tool.name}**: {tool.description}\n"
            section += "\n"

        return section

    def _generate_requirements_mapping_section(self, mcp_scan_result: MCPScanResult) -> str:
        """Generate mapping of requirements to tools.

        Args:
            mcp_scan_result: MCPScanResult with tools

        Returns:
            Markdown section string
        """
        section = "## Requirements to Tools Mapping\n\n"

        if not mcp_scan_result.matches_by_requirement:
            return section + "*No specific requirement-tool mappings found.*\n\n"

        section += "| Requirement | Recommended Tools |\n"
        section += "|-------------|-------------------|\n"

        for requirement, tools in mcp_scan_result.matches_by_requirement.items():
            tool_names = ", ".join([f"`{t.name}`" for t in tools])
            section += f"| {requirement} | {tool_names} |\n"

        section += "\n"
        return section


class DeploymentGuidanceGenerator:
    """Generates DEPLOYMENT_GUIDE.md and deployment configuration templates.

    Produces comprehensive deployment guidance including architecture
    recommendations, Docker/Kubernetes templates, and IaC configurations.
    """

    def __init__(self):
        """Initialize the deployment guidance generator."""
        self._analyzer = DeploymentAnalyzer()

    def generate(
        self,
        tech_stack: Dict[str, Any],
        project_requirements: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate deployment guidance markdown.

        Args:
            tech_stack: Technology stack configuration
            project_requirements: Optional project requirements

        Returns:
            Markdown string with deployment guidance
        """
        logger.info("[DeploymentGuidanceGenerator] Generating deployment guidance")

        # Run deployment analysis
        architecture = self._analyzer.analyze(tech_stack, project_requirements)

        content = "# Deployment Guide\n\n"

        # Executive summary
        content += self._generate_summary_section(architecture)

        # Architecture recommendation
        content += self._generate_architecture_section(architecture)

        # Alternative approaches
        content += self._generate_alternatives_section(architecture)

        # Docker configuration
        if architecture.container_config:
            content += self._generate_docker_section(architecture)

        # Kubernetes configuration
        if architecture.kubernetes_config:
            content += self._generate_kubernetes_section(architecture)

        # Serverless configuration
        if architecture.serverless_config:
            content += self._generate_serverless_section(architecture)

        # Environment requirements
        content += self._generate_environment_section(architecture)

        # Infrastructure requirements
        content += self._generate_infrastructure_section(architecture)

        return content

    def _generate_summary_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate executive summary section."""
        primary = architecture.primary_recommendation
        section = "## Executive Summary\n\n"

        section += f"**Project**: {architecture.project_name}\n"
        section += f"**Type**: {architecture.project_type.replace('_', ' ').title()}\n\n"

        section += f"**Recommended Deployment**: {primary.target.value.title()} on {primary.provider.value.replace('_', ' ').title()}\n\n"

        section += f"> {primary.rationale}\n\n"

        section += "**Key Metrics**:\n"
        section += f"- Estimated Monthly Cost: {primary.estimated_monthly_cost}\n"
        section += f"- Setup Complexity: {primary.setup_complexity.title()}\n"
        section += f"- Scaling Strategy: {primary.scaling_strategy.value.title()}\n\n"

        return section

    def _generate_architecture_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate architecture recommendation section."""
        primary = architecture.primary_recommendation
        section = "## Recommended Architecture\n\n"

        section += f"### {primary.target.value.title()} on {primary.provider.value.replace('_', ' ').title()}\n\n"

        # Pros
        if primary.pros:
            section += "**Advantages**:\n"
            for pro in primary.pros:
                section += f"- {pro}\n"
            section += "\n"

        # Cons
        if primary.cons:
            section += "**Considerations**:\n"
            for con in primary.cons:
                section += f"- {con}\n"
            section += "\n"

        return section

    def _generate_alternatives_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate alternative approaches section."""
        if not architecture.alternative_recommendations:
            return ""

        section = "## Alternative Approaches\n\n"

        for i, alt in enumerate(architecture.alternative_recommendations, 1):
            section += f"### Option {i}: {alt.target.value.title()} on {alt.provider.value.replace('_', ' ').title()}\n\n"
            section += f"{alt.rationale}\n\n"
            section += f"- **Cost**: {alt.estimated_monthly_cost}\n"
            section += f"- **Complexity**: {alt.setup_complexity.title()}\n\n"

        return section

    def _generate_docker_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate Docker configuration section with templates."""
        config = architecture.container_config
        if not config:
            return ""

        section = "## Docker Configuration\n\n"

        # Dockerfile template
        section += "### Dockerfile\n\n"
        section += "```dockerfile\n"
        section += self.generate_dockerfile(architecture)
        section += "```\n\n"

        # Docker Compose template
        section += "### docker-compose.yml\n\n"
        section += "```yaml\n"
        section += self.generate_docker_compose(architecture)
        section += "```\n\n"

        # Configuration notes
        section += "### Configuration Notes\n\n"
        section += f"- **Base Image**: `{config.base_image}`\n"
        section += f"- **Exposed Port**: `{config.port}`\n"
        section += f"- **Health Check**: `{config.health_check_path}`\n"
        section += f"- **Resource Limits**: CPU: {config.resource_limits.get('cpu', 'N/A')}, Memory: {config.resource_limits.get('memory', 'N/A')}\n\n"

        return section

    def _generate_kubernetes_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate Kubernetes configuration section with templates."""
        k8s_config = architecture.kubernetes_config
        if not k8s_config:
            return ""

        section = "## Kubernetes Configuration\n\n"

        # Deployment manifest
        section += "### deployment.yaml\n\n"
        section += "```yaml\n"
        section += self.generate_k8s_deployment(architecture)
        section += "```\n\n"

        # Service manifest
        section += "### service.yaml\n\n"
        section += "```yaml\n"
        section += self.generate_k8s_service(architecture)
        section += "```\n\n"

        # Ingress manifest
        if k8s_config.ingress_enabled:
            section += "### ingress.yaml\n\n"
            section += "```yaml\n"
            section += self.generate_k8s_ingress(architecture)
            section += "```\n\n"

        # HPA manifest
        if k8s_config.hpa_enabled:
            section += "### hpa.yaml\n\n"
            section += "```yaml\n"
            section += self.generate_k8s_hpa(architecture)
            section += "```\n\n"

        # Configuration notes
        section += "### Kubernetes Notes\n\n"
        section += f"- **Namespace**: `{k8s_config.namespace}`\n"
        section += f"- **Replicas**: {k8s_config.replicas}\n"
        section += f"- **Service Type**: {k8s_config.service_type}\n"
        if k8s_config.hpa_enabled:
            section += (
                f"- **HPA Range**: {k8s_config.min_replicas}-{k8s_config.max_replicas} replicas\n"
            )
            section += f"- **Target CPU**: {k8s_config.target_cpu_utilization}%\n"
        section += "\n"

        return section

    def _generate_serverless_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate serverless configuration section."""
        config = architecture.serverless_config
        if not config:
            return ""

        section = "## Serverless Configuration\n\n"

        section += "### serverless.yml (AWS Lambda)\n\n"
        section += "```yaml\n"
        section += self.generate_serverless_config(architecture)
        section += "```\n\n"

        section += "### Configuration Notes\n\n"
        section += f"- **Provider**: {config.provider}\n"
        section += f"- **Runtime**: {config.runtime}\n"
        section += f"- **Memory**: {config.memory_size}MB\n"
        section += f"- **Timeout**: {config.timeout}s\n\n"

        return section

    def _generate_environment_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate environment requirements section."""
        section = "## Environment Variables\n\n"

        if architecture.environment_requirements:
            section += "Configure the following environment variables:\n\n"
            section += "```bash\n"
            for env_var in architecture.environment_requirements:
                section += f"export {env_var}=your_{env_var.lower()}_value\n"
            section += "```\n\n"

            section += "| Variable | Description | Required |\n"
            section += "|----------|-------------|----------|\n"
            for env_var in architecture.environment_requirements:
                desc = self._get_env_var_description(env_var)
                section += f"| `{env_var}` | {desc} | Yes |\n"
            section += "\n"
        else:
            section += "No specific environment variables required.\n\n"

        return section

    def _generate_infrastructure_section(self, architecture: DeploymentArchitecture) -> str:
        """Generate infrastructure requirements section."""
        section = "## Infrastructure Requirements\n\n"

        if architecture.infrastructure_requirements:
            for req in architecture.infrastructure_requirements:
                section += f"- {req}\n"
            section += "\n"
        else:
            section += "No specific infrastructure requirements beyond the deployment target.\n\n"

        return section

    def _get_env_var_description(self, env_var: str) -> str:
        """Get description for environment variable."""
        descriptions = {
            "NODE_ENV": "Runtime environment (development/production)",
            "LOG_LEVEL": "Logging verbosity level",
            "DATABASE_URL": "Database connection string",
            "REDIS_URL": "Redis connection string",
            "AUTH_SECRET": "Authentication secret key",
            "AUTH_URL": "Authentication service URL",
            "STRIPE_SECRET_KEY": "Stripe API secret key",
            "STRIPE_WEBHOOK_SECRET": "Stripe webhook signing secret",
            "API_KEY": "API authentication key",
        }
        return descriptions.get(env_var, f"{env_var} configuration value")

    def generate_dockerfile(self, architecture: DeploymentArchitecture) -> str:
        """Generate Dockerfile template.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Dockerfile content as string
        """
        config = architecture.container_config
        if not config:
            return "# No container configuration available\n"

        # Determine language from base image
        is_node = "node" in config.base_image.lower()
        is_python = "python" in config.base_image.lower()
        is_go = "go" in config.base_image.lower()

        dockerfile = f"FROM {config.base_image}\n\n"
        dockerfile += "WORKDIR /app\n\n"

        if is_node:
            dockerfile += "# Install dependencies\n"
            dockerfile += "COPY package*.json ./\n"
            dockerfile += "RUN npm ci --only=production\n\n"
            dockerfile += "# Copy application code\n"
            dockerfile += "COPY . .\n\n"
            dockerfile += "# Build if needed\n"
            dockerfile += "RUN npm run build --if-present\n\n"
        elif is_python:
            dockerfile += "# Install dependencies\n"
            dockerfile += "COPY requirements.txt ./\n"
            dockerfile += "RUN pip install --no-cache-dir -r requirements.txt\n\n"
            dockerfile += "# Copy application code\n"
            dockerfile += "COPY . .\n\n"
        elif is_go:
            dockerfile += "# Copy go mod files\n"
            dockerfile += "COPY go.mod go.sum ./\n"
            dockerfile += "RUN go mod download\n\n"
            dockerfile += "# Copy source code\n"
            dockerfile += "COPY . .\n\n"
            dockerfile += "# Build\n"
            dockerfile += "RUN go build -o main .\n\n"
        else:
            dockerfile += "# Copy application code\n"
            dockerfile += "COPY . .\n\n"

        dockerfile += f"EXPOSE {config.port}\n\n"
        dockerfile += "# Health check\n"
        dockerfile += "HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\\n"
        dockerfile += f"  CMD wget --no-verbose --tries=1 --spider http://localhost:{config.port}{config.health_check_path} || exit 1\n\n"

        if is_node:
            dockerfile += 'CMD ["node", "dist/index.js"]\n'
        elif is_python:
            dockerfile += 'CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
        elif is_go:
            dockerfile += 'CMD ["./main"]\n'
        else:
            dockerfile += 'CMD ["./start.sh"]\n'

        return dockerfile

    def generate_docker_compose(self, architecture: DeploymentArchitecture) -> str:
        """Generate docker-compose.yml template.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            docker-compose.yml content as string
        """
        config = architecture.container_config
        if not config:
            return "# No container configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        compose = "version: '3.8'\n\n"
        compose += "services:\n"
        compose += f"  {project_name}:\n"
        compose += "    build:\n"
        compose += "      context: .\n"
        compose += "      dockerfile: Dockerfile\n"
        compose += "    ports:\n"
        compose += f'      - "{config.port}:{config.port}"\n'

        if config.environment_variables:
            compose += "    environment:\n"
            for env_var in config.environment_variables:
                compose += f"      - {env_var}=${{${env_var}}}\n"

        if config.volumes:
            compose += "    volumes:\n"
            for volume in config.volumes:
                compose += f"      - {volume}\n"

        compose += "    healthcheck:\n"
        compose += f"      test: ['CMD', 'wget', '--spider', '-q', 'http://localhost:{config.port}{config.health_check_path}']\n"
        compose += "      interval: 30s\n"
        compose += "      timeout: 10s\n"
        compose += "      retries: 3\n"
        compose += "      start_period: 40s\n"
        compose += "    deploy:\n"
        compose += "      resources:\n"
        compose += "        limits:\n"
        compose += f"          cpus: '{config.resource_limits.get('cpu', '0.5').rstrip('m')}'\n"
        compose += f"          memory: {config.resource_limits.get('memory', '512M')}\n"
        compose += "    restart: unless-stopped\n"

        # Add common supporting services
        has_db = "DATABASE_URL" in config.environment_variables
        has_redis = "REDIS_URL" in config.environment_variables

        if has_db or has_redis:
            compose += "\n"

        if has_db:
            compose += "  postgres:\n"
            compose += "    image: postgres:15-alpine\n"
            compose += "    environment:\n"
            compose += "      - POSTGRES_DB=app\n"
            compose += "      - POSTGRES_USER=app\n"
            compose += "      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}\n"
            compose += "    volumes:\n"
            compose += "      - postgres_data:/var/lib/postgresql/data\n"
            compose += "    healthcheck:\n"
            compose += "      test: ['CMD-SHELL', 'pg_isready -U app']\n"
            compose += "      interval: 10s\n"
            compose += "      timeout: 5s\n"
            compose += "      retries: 5\n\n"

        if has_redis:
            compose += "  redis:\n"
            compose += "    image: redis:7-alpine\n"
            compose += "    volumes:\n"
            compose += "      - redis_data:/data\n"
            compose += "    healthcheck:\n"
            compose += "      test: ['CMD', 'redis-cli', 'ping']\n"
            compose += "      interval: 10s\n"
            compose += "      timeout: 5s\n"
            compose += "      retries: 5\n\n"

        if has_db or has_redis:
            compose += "volumes:\n"
            if has_db:
                compose += "  postgres_data:\n"
            if has_redis:
                compose += "  redis_data:\n"

        return compose

    def generate_k8s_deployment(self, architecture: DeploymentArchitecture) -> str:
        """Generate Kubernetes Deployment manifest.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Kubernetes Deployment YAML as string
        """
        config = architecture.container_config
        k8s_config = architecture.kubernetes_config
        if not config or not k8s_config:
            return "# No Kubernetes configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        deployment = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {project_name}
  namespace: {k8s_config.namespace}
  labels:
    app: {project_name}
spec:
  replicas: {k8s_config.replicas}
  selector:
    matchLabels:
      app: {project_name}
  template:
    metadata:
      labels:
        app: {project_name}
    spec:
      containers:
        - name: {project_name}
          image: ${{REGISTRY}}/{project_name}:${{TAG}}
          ports:
            - containerPort: {config.port}
          resources:
            limits:
              cpu: {config.resource_limits.get('cpu', '500m')}
              memory: {config.resource_limits.get('memory', '512Mi')}
            requests:
              cpu: {config.resource_limits.get('cpu', '500m').replace('m', '')}m
              memory: {config.resource_limits.get('memory', '512Mi').replace('Mi', '')}Mi
          livenessProbe:
            httpGet:
              path: {config.health_check_path}
              port: {config.port}
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: {config.health_check_path}
              port: {config.port}
            initialDelaySeconds: 5
            periodSeconds: 5
          envFrom:
            - configMapRef:
                name: {project_name}-config
            - secretRef:
                name: {project_name}-secrets
"""
        return deployment

    def generate_k8s_service(self, architecture: DeploymentArchitecture) -> str:
        """Generate Kubernetes Service manifest.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Kubernetes Service YAML as string
        """
        config = architecture.container_config
        k8s_config = architecture.kubernetes_config
        if not config or not k8s_config:
            return "# No Kubernetes configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        service = f"""apiVersion: v1
kind: Service
metadata:
  name: {project_name}
  namespace: {k8s_config.namespace}
  labels:
    app: {project_name}
spec:
  type: {k8s_config.service_type}
  ports:
    - port: 80
      targetPort: {config.port}
      protocol: TCP
  selector:
    app: {project_name}
"""
        return service

    def generate_k8s_ingress(self, architecture: DeploymentArchitecture) -> str:
        """Generate Kubernetes Ingress manifest.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Kubernetes Ingress YAML as string
        """
        k8s_config = architecture.kubernetes_config
        if not k8s_config:
            return "# No Kubernetes configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        ingress = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {project_name}
  namespace: {k8s_config.namespace}
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - ${{DOMAIN}}
      secretName: {project_name}-tls
  rules:
    - host: ${{DOMAIN}}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {project_name}
                port:
                  number: 80
"""
        return ingress

    def generate_k8s_hpa(self, architecture: DeploymentArchitecture) -> str:
        """Generate Kubernetes HorizontalPodAutoscaler manifest.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Kubernetes HPA YAML as string
        """
        k8s_config = architecture.kubernetes_config
        if not k8s_config:
            return "# No Kubernetes configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        hpa = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {project_name}
  namespace: {k8s_config.namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {project_name}
  minReplicas: {k8s_config.min_replicas}
  maxReplicas: {k8s_config.max_replicas}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {k8s_config.target_cpu_utilization}
"""
        return hpa

    def generate_serverless_config(self, architecture: DeploymentArchitecture) -> str:
        """Generate serverless.yml configuration.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            serverless.yml content as string
        """
        config = architecture.serverless_config
        if not config:
            return "# No serverless configuration available\n"

        project_name = architecture.project_name.lower().replace(" ", "-").replace("+", "-")

        serverless = f"""service: {project_name}

provider:
  name: aws
  runtime: {config.runtime}
  stage: ${{opt:stage, 'dev'}}
  region: ${{opt:region, 'us-east-1'}}
  memorySize: {config.memory_size}
  timeout: {config.timeout}
  environment:
"""
        for env_var in architecture.environment_requirements:
            serverless += f"    {env_var}: ${{env:{env_var}}}\n"

        serverless += """
functions:
  main:
    handler: handler.main
    events:
      - http:
          path: /
          method: ANY
      - http:
          path: /{proxy+}
          method: ANY

plugins:
  - serverless-offline
"""
        return serverless

    def generate_terraform(self, architecture: DeploymentArchitecture) -> str:
        """Generate basic Terraform configuration.

        Args:
            architecture: Deployment architecture configuration

        Returns:
            Terraform HCL content as string
        """
        primary = architecture.primary_recommendation

        terraform = """# Terraform Configuration
# This is a basic template - customize for your specific needs

terraform {
  required_version = ">= 1.0"
  required_providers {
"""
        if primary.provider.value == "aws":
            terraform += """    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
"""
        elif primary.provider.value == "gcp":
            terraform += """    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
"""

        terraform += """  }
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "region" {
  description = "Deployment region"
  type        = string
"""
        if primary.provider.value == "aws":
            terraform += '  default     = "us-east-1"\n'
        elif primary.provider.value == "gcp":
            terraform += '  default     = "us-central1"\n'
        terraform += "}\n"

        return terraform


class ArtifactGeneratorRegistry:
    """Registry for artifact generators.

    Provides a central place to register and retrieve generators
    for different artifact types.
    """

    def __init__(self):
        """Initialize the registry with default generators."""
        self._generators: Dict[str, Any] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default generators."""
        self.register("cicd", CICDWorkflowGenerator, "GitHub Actions workflow generator")
        self.register("gitlab_ci", GitLabCIGenerator, "GitLab CI/CD pipeline generator")
        self.register("jenkins", JenkinsPipelineGenerator, "Jenkins pipeline generator")
        self.register("cicd_analyzer", CICDAnalyzer, "CI/CD analyzer for multi-platform generation")
        self.register("deployment", DeploymentGuidanceGenerator, "Deployment guidance generator")
        self.register("monetization", MonetizationStrategyGenerator)
        self.register("readme", ProjectReadmeGenerator)
        self.register("project_brief", ProjectBriefGenerator)
        self.register("mcp_tools", MCPToolRecommendationGenerator)
        self.register(
            "post_build",
            PostBuildArtifactGenerator,
            "Post-build artifact generator for deployment configs, runbooks, and monitoring",
        )

    def register(
        self,
        name: str,
        generator_class: Type[Any],
        description: str = "",
    ) -> None:
        """Register a generator class.

        Args:
            name: Unique name for the generator
            generator_class: The generator class to register
            description: Optional description of what this generator produces
        """
        self._generators[name] = {
            "class": generator_class,
            "description": description or f"Generator for {name} artifacts",
        }
        logger.debug(f"[ArtifactGeneratorRegistry] Registered generator: {name}")

    def get(self, name: str, **kwargs: Any) -> Optional[Any]:
        """Get an instantiated generator by name.

        Args:
            name: Name of the generator
            **kwargs: Arguments to pass to the generator constructor

        Returns:
            Instantiated generator or None if not found
        """
        if name not in self._generators:
            logger.warning(f"[ArtifactGeneratorRegistry] Generator not found: {name}")
            return None

        generator_info = self._generators[name]
        generator_class = safe_dict_get(generator_info, "class", None, Type)
        if generator_class is None:
            logger.warning(f"[ArtifactGeneratorRegistry] Generator class not found for: {name}")
            return None
        return generator_class(**kwargs)

    def list_generators(self) -> List[Dict[str, str]]:
        """List all registered generators.

        Returns:
            List of dicts with generator name and description
        """
        result = []
        for name, info in self._generators.items():
            description = safe_dict_get(info, "description", "No description", str)
            result.append({"name": name, "description": description})
        return result

    def has_generator(self, name: str) -> bool:
        """Check if a generator is registered.

        Args:
            name: Name of the generator

        Returns:
            True if generator exists
        """
        return name in self._generators


# Default global registry instance
_default_registry: Optional[ArtifactGeneratorRegistry] = None


def get_registry() -> ArtifactGeneratorRegistry:
    """Get the default artifact generator registry.

    Returns:
        The global ArtifactGeneratorRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ArtifactGeneratorRegistry()
    return _default_registry


def get_cicd_generator(**kwargs: Any) -> CICDWorkflowGenerator:
    """Convenience function to get the CI/CD workflow generator.

    Args:
        **kwargs: Arguments to pass to CICDWorkflowGenerator

    Returns:
        CICDWorkflowGenerator instance
    """
    generator = get_registry().get("cicd", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return CICDWorkflowGenerator(**kwargs)
    return generator


def get_monetization_generator(
    budget_enforcer: Optional[Any] = None, **kwargs: Any
) -> MonetizationStrategyGenerator:
    """Convenience function to get the monetization strategy generator.

    Args:
        budget_enforcer: Optional BudgetEnforcer for cost control
        **kwargs: Additional arguments to pass to MonetizationStrategyGenerator

    Returns:
        MonetizationStrategyGenerator instance with budget integration
    """
    generator = get_registry().get("monetization", budget_enforcer=budget_enforcer, **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return MonetizationStrategyGenerator(budget_enforcer=budget_enforcer, **kwargs)
    return generator


def get_monetization_analyzer(
    budget_enforcer: Optional[Any] = None,
) -> MonetizationAnalyzer:
    """Convenience function to get the monetization analyzer.

    Args:
        budget_enforcer: Optional BudgetEnforcer for cost control

    Returns:
        MonetizationAnalyzer instance
    """
    return MonetizationAnalyzer(budget_enforcer=budget_enforcer)


def get_readme_generator(**kwargs: Any) -> ProjectReadmeGenerator:
    """Convenience function to get the project README generator.

    Args:
        **kwargs: Arguments to pass to ProjectReadmeGenerator

    Returns:
        ProjectReadmeGenerator instance
    """
    generator = get_registry().get("readme", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return ProjectReadmeGenerator(**kwargs)
    return generator


def get_project_brief_generator(
    sot_summarizer: Optional[SOTSummarizer] = None,
    include_sot_context: bool = True,
    **kwargs: Any,
) -> ProjectBriefGenerator:
    """Convenience function to get the project brief generator.

    Args:
        sot_summarizer: Optional SOTSummarizer instance for extracting
                        context from SOT documents.
        include_sot_context: Whether to include SOT context by default.
        **kwargs: Additional arguments to pass to ProjectBriefGenerator

    Returns:
        ProjectBriefGenerator instance
    """
    generator = get_registry().get(
        "project_brief",
        sot_summarizer=sot_summarizer,
        include_sot_context=include_sot_context,
        **kwargs,
    )
    if generator is None:
        # Fallback to direct instantiation
        return ProjectBriefGenerator(
            sot_summarizer=sot_summarizer,
            include_sot_context=include_sot_context,
            **kwargs,
        )
    return generator


def get_project_brief_generator_with_sot(
    project_root: Optional[Any] = None,
    **kwargs: Any,
) -> ProjectBriefGenerator:
    """Convenience function to get a project brief generator with SOT integration.

    Creates a ProjectBriefGenerator with an automatically configured SOTSummarizer
    that will extract context from BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md.

    Args:
        project_root: Root path of the project for locating SOT documents.
                     Defaults to current working directory.
        **kwargs: Additional arguments to pass to ProjectBriefGenerator

    Returns:
        ProjectBriefGenerator instance with SOT summarizer configured
    """
    from pathlib import Path

    root = Path(project_root) if project_root else None
    summarizer = get_sot_summarizer(project_root=root)

    return get_project_brief_generator(
        sot_summarizer=summarizer,
        include_sot_context=True,
        **kwargs,
    )


def get_mcp_recommendation_generator(**kwargs: Any) -> MCPToolRecommendationGenerator:
    """Convenience function to get the MCP tool recommendation generator.

    Args:
        **kwargs: Arguments to pass to MCPToolRecommendationGenerator

    Returns:
        MCPToolRecommendationGenerator instance
    """
    generator = get_registry().get("mcp_tools", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return MCPToolRecommendationGenerator(**kwargs)
    return generator


def get_deployment_generator(**kwargs: Any) -> DeploymentGuidanceGenerator:
    """Convenience function to get the deployment guidance generator.

    Args:
        **kwargs: Arguments to pass to DeploymentGuidanceGenerator

    Returns:
        DeploymentGuidanceGenerator instance
    """
    generator = get_registry().get("deployment", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return DeploymentGuidanceGenerator(**kwargs)
    return generator


def get_gitlab_ci_generator(**kwargs: Any) -> GitLabCIGenerator:
    """Convenience function to get the GitLab CI generator.

    Args:
        **kwargs: Arguments to pass to GitLabCIGenerator

    Returns:
        GitLabCIGenerator instance
    """
    generator = get_registry().get("gitlab_ci", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return GitLabCIGenerator(**kwargs)
    return generator


def get_jenkins_generator(**kwargs: Any) -> JenkinsPipelineGenerator:
    """Convenience function to get the Jenkins pipeline generator.

    Args:
        **kwargs: Arguments to pass to JenkinsPipelineGenerator

    Returns:
        JenkinsPipelineGenerator instance
    """
    generator = get_registry().get("jenkins", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return JenkinsPipelineGenerator(**kwargs)
    return generator


def get_cicd_analyzer(**kwargs: Any) -> CICDAnalyzer:
    """Convenience function to get the CI/CD analyzer.

    The analyzer can generate CI/CD configs for multiple platforms
    and integrates with deployment guidance.

    Args:
        **kwargs: Arguments to pass to CICDAnalyzer

    Returns:
        CICDAnalyzer instance
    """
    generator = get_registry().get("cicd_analyzer", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return CICDAnalyzer(**kwargs)
    return generator


def get_post_build_generator(**kwargs: Any) -> PostBuildArtifactGenerator:
    """Convenience function to get the post-build artifact generator.

    The generator produces deployment configs, operational runbooks,
    and monitoring templates after successful project builds.

    Implements IMP-INT-003: Post-Build Artifact Generation.

    Args:
        **kwargs: Arguments to pass to PostBuildArtifactGenerator

    Returns:
        PostBuildArtifactGenerator instance
    """
    generator = get_registry().get("post_build", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return PostBuildArtifactGenerator(**kwargs)
    return generator


class TechStackProposalValidator:
    """Validates tech stack proposal artifacts against schema (IMP-SCHEMA-001).

    Ensures tech stack proposals meet schema requirements including:
    - Required fields: project_type, options (min 2)
    - Cost estimates with valid monthly_min/max ranges
    - Recommendation references existing option
    - Confidence score between 0.0 and 1.0
    """

    def __init__(self, schema_path: Optional[Path | str] = None):
        """Initialize the validator.

        Args:
            schema_path: Optional path to tech_stack_proposal.schema.json.
                        If None, uses default location.
        """
        self._validator = ArtifactValidator(schema_path)

    def validate_tech_stack_proposal(self, proposal: Dict[str, Any]) -> bool:
        """Validate a tech stack proposal artifact.

        Args:
            proposal: Tech stack proposal dict (from TechStackProposal.model_dump())

        Returns:
            True if valid, False otherwise
        """
        result = self._validator.validate(proposal)
        if not result.is_valid:
            for error in result.errors:
                logger.error(f"[TechStackProposalValidator] {error.path}: {error.message}")
        if result.warnings:
            for warning in result.warnings:
                logger.warning(f"[TechStackProposalValidator] {warning}")
        return result.is_valid

    def validate_before_write(
        self, proposal: Dict[str, Any], artifact_path: Optional[Path] = None
    ) -> bool:
        """Validate a tech stack proposal before writing to disk.

        Args:
            proposal: Tech stack proposal dict
            artifact_path: Optional path where artifact will be written (for logging)

        Returns:
            True if valid and can be written, False otherwise
        """
        if artifact_path is None:
            artifact_path = Path("tech_stack_proposal.json")

        result = self._validator.validate_before_write(proposal, artifact_path)
        return result


def get_tech_stack_proposal_validator(
    schema_path: Optional[Path | str] = None,
) -> TechStackProposalValidator:
    """Convenience function to get the tech stack proposal validator.

    Validates tech stack proposal artifacts against schema before writing,
    ensuring all required fields are present and valid.

    Implements IMP-SCHEMA-001: Tech Stack Proposal Artifact Validation.

    Args:
        schema_path: Optional path to tech_stack_proposal.schema.json

    Returns:
        TechStackProposalValidator instance
    """
    return TechStackProposalValidator(schema_path)
