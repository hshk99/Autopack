"""Artifact Generators Registry for research projects.

Provides a central registry for all artifact generators that produce
deployment configurations, documentation, and other outputs from
research findings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from autopack.research.generators.cicd_generator import CICDWorkflowGenerator

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
                section += f"**Pros:**\n"
                for pro in pros:
                    section += f"- {pro}\n"
                section += "\n"

            if cons:
                section += f"**Cons:**\n"
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
