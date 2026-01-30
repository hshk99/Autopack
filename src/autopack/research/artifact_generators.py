"""Artifact Generators Registry for research projects.

Provides a central registry for all artifact generators that produce
deployment configurations, documentation, and other outputs from
research findings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from autopack.research.analysis.cost_effectiveness import CostEffectivenessAnalyzer
from autopack.research.generators.cicd_generator import CICDWorkflowGenerator
from autopack.research.idea_parser import ProjectType
from autopack.research.tech_stack_proposer import (
    TechStackOption,
    TechStackProposal,
    TechStackProposer,
)

logger = logging.getLogger(__name__)


class MonetizationStrategyGenerator:
    """Generates MONETIZATION_STRATEGY.md from research findings.

    Produces a comprehensive monetization strategy document including
    pricing models, benchmarks, conversion metrics, and revenue projections.
    """

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
            model_type = model.get("model", "Unknown")
            prevalence = model.get("prevalence", "")
            pros = model.get("pros", [])
            cons = model.get("cons", [])

            section += f"### {model_type.title()}\n\n"

            if prevalence:
                section += f"**Prevalence**: {prevalence}\n\n"

            examples = model.get("examples", [])
            if examples:
                section += "**Examples:**\n"
                for example in examples:
                    company = example.get("company", "Unknown")
                    url = example.get("url", "")
                    tiers = example.get("tiers", [])

                    section += f"\n- **{company}**"
                    if url:
                        section += f" ([link]({url}))"
                    section += "\n"

                    for tier in tiers:
                        tier_name = tier.get("name", "")
                        price = tier.get("price", "")
                        limits = tier.get("limits", "")
                        section += f"  - {tier_name}: {price}"
                        if limits:
                            section += f" ({limits})"
                        section += "\n"

                section += "\n"

            if pros:
                section += "**Pros:**\n"
                for pro in pros:
                    section += f"- {pro}\n"
                section += "\n"

            if cons:
                section += "**Cons:**\n"
                for con in cons:
                    section += f"- {con}\n"
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
            section += f"### {tier.replace('_', ' ').title()}\n\n"

            if isinstance(data, dict):
                range_val = data.get("range", "")
                if range_val:
                    section += f"- **Range**: {range_val}\n"

                median = data.get("median", "")
                if median:
                    section += f"- **Median**: {median}\n"

                source = data.get("source", "")
                if source:
                    section += f"- **Source**: {source}\n"

                extraction = data.get("extraction_span", "")
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
            section += f"### {metric_key.replace('_', ' ').title()}\n\n"

            if isinstance(metric_data, dict):
                industry_avg = metric_data.get("industry_average", "")
                if industry_avg:
                    section += f"- **Industry Average**: {industry_avg}\n"

                top_performers = metric_data.get("top_performers", "")
                if top_performers:
                    section += f"- **Top Performers**: {top_performers}\n"

                source = metric_data.get("source", "")
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
            section += f"### {scenario.title()} Scenario\n\n"

            if isinstance(data, dict):
                monthly = data.get("monthly", "")
                if monthly:
                    section += f"- **Monthly Revenue**: {monthly}\n"

                assumptions = data.get("assumptions", [])
                if assumptions:
                    section += "- **Assumptions**:\n"
                    for assumption in assumptions:
                        section += f"  - {assumption}\n"

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

        model = recommended.get("model", "")
        if model:
            section += f"**Model**: {model}\n\n"

        rationale = recommended.get("rationale", "")
        if rationale:
            section += f"**Rationale**: {rationale}\n\n"

        suggested = recommended.get("suggested_pricing", {})
        if suggested:
            section += "**Suggested Pricing**:\n"
            for tier, price in suggested.items():
                section += f"- {tier.title()}: {price}\n"
            section += "\n"

        differentiation = recommended.get("differentiation", "")
        if differentiation:
            section += f"**Differentiation**: {differentiation}\n\n"

        return section


class TechStackProposalGenerator:
    """Generates tech stack proposals with integrated cost analysis.

    Combines TechStackProposer recommendations with CostEffectivenessAnalyzer
    to produce comprehensive proposals including TCO (Total Cost of Ownership)
    estimates for each technology option.
    """

    def __init__(
        self,
        include_mcp_options: bool = True,
        cost_analyzer: Optional[CostEffectivenessAnalyzer] = None,
    ):
        """Initialize the TechStackProposalGenerator.

        Args:
            include_mcp_options: Whether to prioritize MCP-enabled options
            cost_analyzer: Optional pre-configured CostEffectivenessAnalyzer
        """
        self.proposer = TechStackProposer(include_mcp_options=include_mcp_options)
        self.cost_analyzer = cost_analyzer or CostEffectivenessAnalyzer()
        self._build_vs_buy_analyzer: Optional[Any] = None

        # Try to import BuildVsBuyAnalyzer if available (from IMP-HIGH-002)
        try:
            from autopack.research.analysis.build_vs_buy_analyzer import BuildVsBuyAnalyzer

            self._build_vs_buy_analyzer = BuildVsBuyAnalyzer()
            logger.debug("[TechStackProposalGenerator] BuildVsBuyAnalyzer integration enabled")
        except ImportError:
            logger.debug(
                "[TechStackProposalGenerator] BuildVsBuyAnalyzer not available, "
                "proceeding without build-vs-buy analysis"
            )

    def generate(
        self,
        project_type: ProjectType,
        requirements: Optional[List[str]] = None,
        user_projections: Optional[Dict[str, int]] = None,
        include_cost_analysis: bool = True,
    ) -> str:
        """Generate a comprehensive tech stack proposal with cost analysis.

        Args:
            project_type: The type of project (e.g., ECOMMERCE, TRADING)
            requirements: Optional list of specific requirements
            user_projections: Optional user count projections (year_1, year_3, year_5)
            include_cost_analysis: Whether to include TCO analysis

        Returns:
            Markdown string with tech stack proposal and cost analysis
        """
        logger.info(f"[TechStackProposalGenerator] Generating proposal for {project_type.value}")

        # Get tech stack proposal
        proposal = self.proposer.propose(
            project_type=project_type,
            requirements=requirements or [],
        )

        # Generate markdown content
        content = self._generate_header(proposal)
        content += self._generate_options_section(proposal.options)

        if proposal.recommendation:
            content += self._generate_recommendation_section(
                proposal.recommendation,
                proposal.recommendation_reasoning,
            )

        if include_cost_analysis:
            cost_analysis = self.analyze_costs(
                proposal=proposal,
                user_projections=user_projections,
            )
            content += self._generate_cost_analysis_section(cost_analysis)
            content += self._generate_tco_comparison_section(proposal.options, cost_analysis)

        content += self._generate_risk_section(proposal.options)

        return content

    def analyze_costs(
        self,
        proposal: TechStackProposal,
        user_projections: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Analyze costs for the tech stack proposal.

        Args:
            proposal: The TechStackProposal to analyze
            user_projections: Optional user projections by year

        Returns:
            Cost analysis dictionary with TCO estimates
        """
        user_proj = user_projections or {
            "year_1": 1000,
            "year_3": 10000,
            "year_5": 50000,
        }

        # Convert tech stack options to build-vs-buy format for cost analysis
        build_vs_buy_results = self._convert_options_to_cost_data(proposal.options)

        # Run cost effectiveness analysis
        analysis = self.cost_analyzer.analyze(
            project_name=f"{proposal.project_type.value} Project",
            build_vs_buy_results=build_vs_buy_results,
            user_projections=user_proj,
        )

        # Add per-option TCO if BuildVsBuyAnalyzer is available
        if self._build_vs_buy_analyzer:
            analysis["build_vs_buy_recommendations"] = self._get_build_vs_buy_analysis(
                proposal.options
            )

        return analysis

    def _convert_options_to_cost_data(self, options: List[TechStackOption]) -> List[Dict[str, Any]]:
        """Convert TechStackOption objects to cost analysis format.

        Args:
            options: List of TechStackOption objects

        Returns:
            List of cost data dictionaries
        """
        results = []
        for option in options:
            cost_estimate = option.estimated_cost
            monthly_avg = (cost_estimate.monthly_min + cost_estimate.monthly_max) / 2

            results.append(
                {
                    "component": option.name,
                    "description": option.description,
                    "recommendation": {
                        "choice": "buy" if option.mcp_available else "integrate",
                        "specific": option.name,
                        "rationale": option.pros if option.pros else ["Standard option"],
                    },
                    "cost_data": {
                        "initial_cost": 0,
                        "monthly_ongoing": monthly_avg,
                        "scaling_model": (
                            "flat" if cost_estimate.tier.value in ["free", "low"] else "linear"
                        ),
                        "year_1_total": monthly_avg * 12,
                        "year_3_total": monthly_avg * 36,
                        "year_5_total": monthly_avg * 60,
                    },
                    "vendor_lock_in": {
                        "level": (
                            "medium" if "vendor lock-in" in " ".join(option.cons).lower() else "low"
                        ),
                        "alternatives": [],
                    },
                    "is_core": option.category in ["Full Stack Framework", "Custom Stack"],
                }
            )
        return results

    def _get_build_vs_buy_analysis(self, options: List[TechStackOption]) -> List[Dict[str, Any]]:
        """Get build-vs-buy recommendations for each option.

        Args:
            options: List of TechStackOption objects

        Returns:
            List of build-vs-buy analysis results
        """
        results = []
        if not self._build_vs_buy_analyzer:
            return results

        for option in options:
            try:
                analysis = self._build_vs_buy_analyzer.analyze(
                    tool_name=option.name,
                    requirements={
                        "category": option.category,
                        "setup_complexity": option.setup_complexity,
                        "mcp_available": option.mcp_available,
                    },
                )
                results.append(
                    {
                        "option": option.name,
                        "recommendation": analysis.recommendation,
                        "build_cost": analysis.build_cost,
                        "buy_cost": analysis.buy_cost,
                        "rationale": analysis.rationale,
                    }
                )
            except Exception as e:
                logger.warning(
                    f"[TechStackProposalGenerator] Build-vs-buy analysis failed "
                    f"for {option.name}: {e}"
                )
        return results

    def _generate_header(self, proposal: TechStackProposal) -> str:
        """Generate the proposal header section.

        Args:
            proposal: The TechStackProposal

        Returns:
            Markdown header section
        """
        content = f"# Tech Stack Proposal: {proposal.project_type.value.title()}\n\n"
        content += f"**Confidence Score**: {proposal.confidence_score:.0%}\n\n"

        if proposal.requirements:
            content += "## Requirements Considered\n\n"
            for req in proposal.requirements:
                content += f"- {req}\n"
            content += "\n"

        return content

    def _generate_options_section(self, options: List[TechStackOption]) -> str:
        """Generate the technology options section.

        Args:
            options: List of TechStackOption objects

        Returns:
            Markdown options section
        """
        content = "## Technology Options\n\n"

        for i, option in enumerate(options, 1):
            content += f"### Option {i}: {option.name}\n\n"
            content += f"**Category**: {option.category}\n\n"
            content += f"{option.description}\n\n"

            # Cost estimate
            cost = option.estimated_cost
            content += f"**Estimated Cost**: ${cost.monthly_min:.0f}"
            if cost.monthly_min != cost.monthly_max:
                content += f" - ${cost.monthly_max:.0f}"
            content += f"/month ({cost.tier.value})\n"
            if cost.notes:
                content += f"  - *{cost.notes}*\n"
            content += "\n"

            # MCP availability
            if option.mcp_available:
                content += f"✅ **MCP Server Available**: {option.mcp_server_name}\n\n"

            # Pros
            if option.pros:
                content += "**Pros**:\n"
                for pro in option.pros:
                    content += f"- {pro}\n"
                content += "\n"

            # Cons
            if option.cons:
                content += "**Cons**:\n"
                for con in option.cons:
                    content += f"- {con}\n"
                content += "\n"

            # Setup complexity
            content += f"**Setup Complexity**: {option.setup_complexity}\n\n"

            if option.documentation_url:
                content += f"📚 [Documentation]({option.documentation_url})\n\n"

            content += "---\n\n"

        return content

    def _generate_recommendation_section(
        self, recommendation: str, reasoning: Optional[str]
    ) -> str:
        """Generate the recommendation section.

        Args:
            recommendation: Recommended option name
            reasoning: Reasoning for the recommendation

        Returns:
            Markdown recommendation section
        """
        content = "## Recommendation\n\n"
        content += f"**Recommended Option**: {recommendation}\n\n"
        if reasoning:
            content += f"{reasoning}\n\n"
        return content

    def _generate_cost_analysis_section(self, cost_analysis: Dict[str, Any]) -> str:
        """Generate the cost analysis section with TCO estimates.

        Args:
            cost_analysis: Cost analysis dictionary

        Returns:
            Markdown cost analysis section
        """
        content = "## Total Cost of Ownership (TCO) Analysis\n\n"

        # Executive summary
        if "executive_summary" in cost_analysis:
            summary = cost_analysis["executive_summary"]
            content += "### Executive Summary\n\n"
            content += f"- **Year 1 Total**: ${summary.get('total_year_1_cost', 0):,.0f}\n"
            content += f"- **Year 3 Total**: ${summary.get('total_year_3_cost', 0):,.0f}\n"
            content += f"- **Year 5 Total**: ${summary.get('total_year_5_cost', 0):,.0f}\n\n"

            if summary.get("primary_cost_drivers"):
                content += "**Primary Cost Drivers**:\n"
                for driver in summary["primary_cost_drivers"]:
                    content += f"- {driver}\n"
                content += "\n"

            if summary.get("key_recommendations"):
                content += "**Key Recommendations**:\n"
                for rec in summary["key_recommendations"]:
                    content += f"- {rec}\n"
                content += "\n"

        # Cost breakdown
        if "total_cost_of_ownership" in cost_analysis:
            tco = cost_analysis["total_cost_of_ownership"]
            content += "### Cost Breakdown\n\n"
            content += "| Category | Year 1 | Year 5 |\n"
            content += "|----------|--------|--------|\n"

            if "year_1" in tco:
                y1 = tco["year_1"]
                y5 = tco.get("year_5_cumulative", {})
                for category in [
                    "development",
                    "infrastructure",
                    "services",
                    "ai_apis",
                    "operational",
                ]:
                    if category in y1:
                        content += f"| {category.replace('_', ' ').title()} | ${y1[category]:,.0f} | ${y5.get(category, 0):,.0f} |\n"
                content += f"| **Total** | **${y1.get('total', 0):,.0f}** | **${y5.get('total', 0):,.0f}** |\n"
                content += "\n"

        # Optimization roadmap
        if "cost_optimization_roadmap" in cost_analysis:
            content += "### Optimization Roadmap\n\n"
            for phase in cost_analysis["cost_optimization_roadmap"]:
                content += f"**{phase.get('phase', '')}**: {phase.get('focus', '')}\n"
                for action in phase.get("actions", []):
                    content += f"  - {action}\n"
                content += "\n"

        return content

    def _generate_tco_comparison_section(
        self, options: List[TechStackOption], cost_analysis: Dict[str, Any]
    ) -> str:
        """Generate TCO comparison section for all options.

        Args:
            options: List of TechStackOption objects
            cost_analysis: Cost analysis dictionary

        Returns:
            Markdown TCO comparison section
        """
        content = "### Option Cost Comparison\n\n"
        content += "| Option | Monthly Cost | Year 1 TCO | Year 5 TCO |\n"
        content += "|--------|-------------|------------|------------|\n"

        for option in options:
            cost = option.estimated_cost
            monthly_avg = (cost.monthly_min + cost.monthly_max) / 2
            year_1 = monthly_avg * 12
            year_5 = monthly_avg * 60

            content += (
                f"| {option.name} | ${monthly_avg:,.0f} | ${year_1:,.0f} | ${year_5:,.0f} |\n"
            )

        content += "\n"
        content += "*Note: TCO estimates are based on direct costs only. "
        content += "Development and integration costs vary by team.*\n\n"

        return content

    def _generate_risk_section(self, options: List[TechStackOption]) -> str:
        """Generate the risk assessment section.

        Args:
            options: List of TechStackOption objects

        Returns:
            Markdown risk section
        """
        content = "## Risk Assessment\n\n"

        has_risks = False
        for option in options:
            if option.tos_risks:
                has_risks = True
                content += f"### {option.name}\n\n"
                for risk in option.tos_risks:
                    content += f"- **{risk.level.value.upper()}**: {risk.description}\n"
                    if risk.mitigation:
                        content += f"  - *Mitigation*: {risk.mitigation}\n"
                content += "\n"

        if not has_risks:
            content += "No significant ToS or legal risks identified for the proposed options.\n\n"

        return content

    def generate_from_proposal(self, proposal: TechStackProposal) -> str:
        """Generate markdown from an existing TechStackProposal.

        Args:
            proposal: Pre-generated TechStackProposal

        Returns:
            Markdown string with proposal and cost analysis
        """
        return self.generate(
            project_type=proposal.project_type,
            requirements=proposal.requirements,
            include_cost_analysis=True,
        )


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
        if components:
            section += "### Core Components\n\n"
            for component in components:
                if isinstance(component, dict):
                    name = component.get("name", "Component")
                    description = component.get("description", "")
                    section += f"- **{name}**: {description}\n"
                else:
                    section += f"- {component}\n"
            section += "\n"

        # Technology Stack Details
        section += "### Technology Stack\n\n"

        frontend = tech_stack.get("frontend", [])
        if frontend:
            section += f"**Frontend**: {', '.join(frontend)}\n\n"

        backend = tech_stack.get("backend", [])
        if backend:
            section += f"**Backend**: {', '.join(backend)}\n\n"

        database = tech_stack.get("database", [])
        if database:
            section += f"**Database**: {', '.join(database)}\n\n"

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
        self.register("cicd", CICDWorkflowGenerator)
        self.register("monetization", MonetizationStrategyGenerator)
        self.register("readme", ProjectReadmeGenerator)
        self.register(
            "tech_stack",
            TechStackProposalGenerator,
            "Tech stack proposals with TCO analysis",
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

        generator_class = self._generators[name]["class"]
        return generator_class(**kwargs)

    def list_generators(self) -> List[Dict[str, str]]:
        """List all registered generators.

        Returns:
            List of dicts with generator name and description
        """
        return [
            {"name": name, "description": info["description"]}
            for name, info in self._generators.items()
        ]

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


def get_monetization_generator(**kwargs: Any) -> MonetizationStrategyGenerator:
    """Convenience function to get the monetization strategy generator.

    Args:
        **kwargs: Arguments to pass to MonetizationStrategyGenerator

    Returns:
        MonetizationStrategyGenerator instance
    """
    generator = get_registry().get("monetization", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return MonetizationStrategyGenerator(**kwargs)
    return generator


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


def get_tech_stack_generator(**kwargs: Any) -> TechStackProposalGenerator:
    """Convenience function to get the tech stack proposal generator.

    Args:
        **kwargs: Arguments to pass to TechStackProposalGenerator

    Returns:
        TechStackProposalGenerator instance
    """
    generator = get_registry().get("tech_stack", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return TechStackProposalGenerator(**kwargs)
    return generator
