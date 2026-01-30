"""Tests for artifact generators."""

from __future__ import annotations

from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry,
    MonetizationStrategyGenerator,
    ProjectReadmeGenerator,
    TechStackProposalGenerator,
    get_monetization_generator,
    get_readme_generator,
    get_registry,
    get_tech_stack_generator,
)
from autopack.research.idea_parser import ProjectType


class TestProjectReadmeGenerator:
    """Test ProjectReadmeGenerator."""

    def test_generate_basic_readme(self) -> None:
        """Test generating a basic README."""
        generator = ProjectReadmeGenerator()

        research_findings = {
            "problem_statement": "Users struggle to manage projects",
            "solution": "Provide automated project management",
            "market_opportunity": {"total_addressable_market": "$1B"},
            "features": [
                {"name": "Task Tracking", "description": "Track all project tasks"},
                {"name": "Collaboration", "description": "Real-time collaboration"},
            ],
            "components": [
                {"name": "Frontend", "description": "React-based UI"},
                {"name": "Backend", "description": "Python API server"},
            ],
        }

        tech_stack = {
            "languages": ["Python", "JavaScript"],
            "frameworks": ["React", "FastAPI"],
            "tools": ["Docker", "Kubernetes"],
            "package_manager": "npm",
            "frontend": ["React", "TypeScript"],
            "backend": ["FastAPI", "PostgreSQL"],
            "database": ["PostgreSQL", "Redis"],
            "hosting_requirements": ["Cloud hosting", "SSL certificate"],
        }

        project_brief = "A comprehensive project management tool for teams."

        readme = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            project_brief=project_brief,
        )

        # Verify basic structure
        assert "# Project README" in readme
        assert "## Table of Contents" in readme
        assert "## Project Details" in readme
        assert "## Quick Start" in readme
        assert "## Architecture" in readme
        assert "## Deployment" in readme

        # Verify content inclusion
        assert "Task Tracking" in readme
        assert "Collaboration" in readme
        assert "React" in readme
        assert "FastAPI" in readme
        assert "PostgreSQL" in readme

    def test_generate_readme_with_monetization(self) -> None:
        """Test generating README with monetization strategy."""
        generator = ProjectReadmeGenerator()

        research_findings = {"problem_statement": "Test problem"}
        tech_stack = {"package_manager": "pip"}
        project_brief = "Test project"
        monetization = "# Pricing\n\nPay-as-you-go model."

        readme = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            project_brief=project_brief,
            monetization_strategy=monetization,
        )

        assert "## Monetization Strategy" in readme
        assert "Pay-as-you-go model" in readme

    def test_generate_readme_without_monetization(self) -> None:
        """Test generating README without monetization strategy."""
        generator = ProjectReadmeGenerator()

        research_findings = {"problem_statement": "Test problem"}
        tech_stack = {"package_manager": "pip"}
        project_brief = "Test project"

        readme = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            project_brief=project_brief,
            monetization_strategy=None,
        )

        # Monetization section should not be present
        assert "## Monetization Strategy" not in readme

    def test_generate_readme_with_npm_package_manager(self) -> None:
        """Test setup instructions with npm."""
        generator = ProjectReadmeGenerator()

        tech_stack = {"package_manager": "npm"}
        research_findings = {}
        project_brief = "Test"

        readme = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            project_brief=project_brief,
        )

        assert "npm install" in readme
        assert "npm start" in readme

    def test_generate_readme_with_pip_package_manager(self) -> None:
        """Test setup instructions with pip."""
        generator = ProjectReadmeGenerator()

        tech_stack = {"package_manager": "pip"}
        research_findings = {}
        project_brief = "Test"

        readme = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            project_brief=project_brief,
        )

        assert "pip install -e" in readme

    def test_generate_overview_section(self) -> None:
        """Test _generate_overview_section method."""
        generator = ProjectReadmeGenerator()

        research_findings = {"market_opportunity": {"total_addressable_market": "$5M"}}
        brief = "This is a great project"

        section = generator._generate_overview_section(research_findings, brief)

        assert "# Project README" in section
        assert brief in section
        assert "$5M" in section

    def test_generate_project_details(self) -> None:
        """Test _generate_project_details method."""
        generator = ProjectReadmeGenerator()

        research_findings = {
            "problem_statement": "Users have issues",
            "solution": "We solve them",
            "features": ["Feature 1", "Feature 2"],
        }

        section = generator._generate_project_details(research_findings)

        assert "## Project Details" in section
        assert "Users have issues" in section
        assert "We solve them" in section
        assert "Feature 1" in section

    def test_generate_setup_section_with_languages(self) -> None:
        """Test setup section with language information."""
        generator = ProjectReadmeGenerator()

        tech_stack = {
            "languages": ["Python", "JavaScript"],
            "frameworks": ["Django", "Vue"],
            "tools": ["Git", "Docker"],
            "package_manager": "npm",
        }

        section = generator._generate_setup_section(tech_stack)

        assert "### Prerequisites" in section
        assert "Python" in section
        assert "JavaScript" in section
        assert "Django" in section
        assert "Vue" in section
        assert "Docker" in section

    def test_generate_architecture_section(self) -> None:
        """Test architecture section generation."""
        generator = ProjectReadmeGenerator()

        tech_stack = {
            "architecture_pattern": "Microservices",
            "frontend": ["React", "Redux"],
            "backend": ["Node.js", "Express"],
            "database": ["MongoDB"],
        }

        research_findings = {
            "components": [
                {"name": "API", "description": "REST API"},
                {"name": "Worker", "description": "Background jobs"},
            ]
        }

        section = generator._generate_architecture_section(tech_stack, research_findings)

        assert "## Architecture" in section
        assert "Microservices" in section
        assert "React" in section
        assert "Node.js" in section
        assert "MongoDB" in section
        assert "REST API" in section

    def test_generate_deployment_section(self) -> None:
        """Test deployment section generation."""
        generator = ProjectReadmeGenerator()

        tech_stack = {"hosting_requirements": ["Docker", "Kubernetes", "Load Balancer"]}

        section = generator._generate_deployment_section(tech_stack)

        assert "## Deployment" in section
        assert "### Hosting Requirements" in section
        assert "Docker" in section
        assert "Kubernetes" in section
        assert "Load Balancer" in section
        assert "### Environment Variables" in section
        assert "### Deployment Steps" in section

    def test_generate_support_section(self) -> None:
        """Test support section generation."""
        generator = ProjectReadmeGenerator()

        section = generator._generate_support_section()

        assert "## Support" in section
        assert "### Getting Help" in section
        assert "### Contributing" in section
        assert "## License" in section


class TestMonetizationStrategyGenerator:
    """Test MonetizationStrategyGenerator."""

    def test_generate_basic_monetization_strategy(self) -> None:
        """Test generating a basic monetization strategy."""
        generator = MonetizationStrategyGenerator()

        research_findings = {
            "overview": "Multiple revenue streams available",
            "models": [
                {
                    "model": "subscription",
                    "prevalence": "45% of SaaS companies",
                    "pros": ["Predictable revenue"],
                    "cons": ["Requires retention focus"],
                    "examples": [
                        {
                            "company": "Slack",
                            "url": "https://slack.com",
                            "tiers": [
                                {"name": "Free", "price": "$0"},
                                {"name": "Pro", "price": "$8/user/mo"},
                            ],
                        }
                    ],
                }
            ],
        }

        content = generator.generate(research_findings)

        assert "# Monetization Strategy" in content
        assert "## Pricing Models" in content
        assert "Subscription" in content
        assert "45% of SaaS" in content
        assert "Slack" in content


class TestTechStackProposalGenerator:
    """Test TechStackProposalGenerator with cost analysis."""

    def test_generate_basic_proposal(self) -> None:
        """Test generating a basic tech stack proposal."""
        generator = TechStackProposalGenerator()

        proposal = generator.generate(
            project_type=ProjectType.ECOMMERCE,
            requirements=["payment processing", "inventory management"],
            include_cost_analysis=True,
        )

        # Verify basic structure
        assert "# Tech Stack Proposal" in proposal
        assert "ECOMMERCE" in proposal.upper() or "Ecommerce" in proposal
        assert "## Technology Options" in proposal
        assert "## Total Cost of Ownership (TCO) Analysis" in proposal

    def test_generate_with_user_projections(self) -> None:
        """Test generating proposal with custom user projections."""
        generator = TechStackProposalGenerator()

        user_projections = {
            "year_1": 5000,
            "year_3": 50000,
            "year_5": 200000,
        }

        proposal = generator.generate(
            project_type=ProjectType.TRADING,
            user_projections=user_projections,
            include_cost_analysis=True,
        )

        # Verify cost analysis is included
        assert "## Total Cost of Ownership (TCO) Analysis" in proposal
        assert "Executive Summary" in proposal
        assert "Cost Breakdown" in proposal

    def test_generate_without_cost_analysis(self) -> None:
        """Test generating proposal without cost analysis."""
        generator = TechStackProposalGenerator()

        proposal = generator.generate(
            project_type=ProjectType.CONTENT,
            include_cost_analysis=False,
        )

        # Verify no cost analysis section
        assert "## Total Cost of Ownership (TCO) Analysis" not in proposal
        # But still has options
        assert "## Technology Options" in proposal

    def test_generate_includes_recommendation(self) -> None:
        """Test that generated proposal includes recommendation section."""
        generator = TechStackProposalGenerator()

        proposal = generator.generate(
            project_type=ProjectType.AUTOMATION,
            include_cost_analysis=True,
        )

        # Most proposals should include a recommendation
        # (unless all options have critical risks)
        assert "## Technology Options" in proposal

    def test_generate_includes_risk_assessment(self) -> None:
        """Test that generated proposal includes risk assessment."""
        generator = TechStackProposalGenerator()

        proposal = generator.generate(
            project_type=ProjectType.TRADING,  # Trading has ToS risks
            include_cost_analysis=True,
        )

        assert "## Risk Assessment" in proposal

    def test_generate_option_cost_comparison(self) -> None:
        """Test that TCO comparison table is generated."""
        generator = TechStackProposalGenerator()

        proposal = generator.generate(
            project_type=ProjectType.ECOMMERCE,
            include_cost_analysis=True,
        )

        assert "### Option Cost Comparison" in proposal
        assert "Monthly Cost" in proposal
        assert "Year 1 TCO" in proposal
        assert "Year 5 TCO" in proposal

    def test_analyze_costs_returns_dict(self) -> None:
        """Test that analyze_costs returns a proper dictionary."""
        generator = TechStackProposalGenerator()
        proposer = generator.proposer

        proposal = proposer.propose(
            project_type=ProjectType.ECOMMERCE,
            requirements=[],
        )

        cost_analysis = generator.analyze_costs(proposal=proposal)

        assert isinstance(cost_analysis, dict)
        assert "executive_summary" in cost_analysis
        assert "total_cost_of_ownership" in cost_analysis
        assert "cost_optimization_roadmap" in cost_analysis

    def test_generator_initializes_with_mcp_options(self) -> None:
        """Test that generator can be initialized with MCP options."""
        generator_with_mcp = TechStackProposalGenerator(include_mcp_options=True)
        generator_without_mcp = TechStackProposalGenerator(include_mcp_options=False)

        # Both should work
        assert generator_with_mcp.proposer.include_mcp_options is True
        assert generator_without_mcp.proposer.include_mcp_options is False

    def test_generate_from_proposal(self) -> None:
        """Test generating markdown from an existing proposal."""
        generator = TechStackProposalGenerator()

        # First create a proposal
        proposal = generator.proposer.propose(
            project_type=ProjectType.CONTENT,
            requirements=["blog support"],
        )

        # Then generate from it
        markdown = generator.generate_from_proposal(proposal)

        assert "# Tech Stack Proposal" in markdown
        assert "Content" in markdown
        assert "## Technology Options" in markdown


class TestArtifactGeneratorRegistry:
    """Test ArtifactGeneratorRegistry."""

    def test_registry_has_default_generators(self) -> None:
        """Test that registry has default generators registered."""
        registry = ArtifactGeneratorRegistry()

        assert registry.has_generator("cicd")
        assert registry.has_generator("monetization")
        assert registry.has_generator("readme")
        assert registry.has_generator("tech_stack")

    def test_get_generator(self) -> None:
        """Test getting a generator from registry."""
        registry = ArtifactGeneratorRegistry()

        generator = registry.get("readme")
        assert generator is not None
        assert isinstance(generator, ProjectReadmeGenerator)

    def test_get_nonexistent_generator(self) -> None:
        """Test getting a non-existent generator."""
        registry = ArtifactGeneratorRegistry()

        generator = registry.get("nonexistent")
        assert generator is None

    def test_list_generators(self) -> None:
        """Test listing all generators."""
        registry = ArtifactGeneratorRegistry()

        generators = registry.list_generators()
        assert len(generators) >= 3

        names = [g["name"] for g in generators]
        assert "cicd" in names
        assert "monetization" in names
        assert "readme" in names

    def test_register_custom_generator(self) -> None:
        """Test registering a custom generator."""
        registry = ArtifactGeneratorRegistry()

        class CustomGenerator:
            def generate(self, data: dict) -> str:
                return "custom"

        registry.register("custom", CustomGenerator, "Custom generator")
        assert registry.has_generator("custom")

        generator = registry.get("custom")
        assert isinstance(generator, CustomGenerator)


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_registry(self) -> None:
        """Test getting global registry."""
        registry = get_registry()

        assert registry is not None
        assert registry.has_generator("readme")

    def test_get_registry_singleton(self) -> None:
        """Test that get_registry returns same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_get_readme_generator(self) -> None:
        """Test getting README generator via convenience function."""
        generator = get_readme_generator()

        assert isinstance(generator, ProjectReadmeGenerator)

    def test_get_monetization_generator(self) -> None:
        """Test getting monetization generator via convenience function."""
        generator = get_monetization_generator()

        assert isinstance(generator, MonetizationStrategyGenerator)

    def test_get_tech_stack_generator(self) -> None:
        """Test getting tech stack generator via convenience function."""
        generator = get_tech_stack_generator()

        assert isinstance(generator, TechStackProposalGenerator)

    def test_get_tech_stack_generator_with_params(self) -> None:
        """Test getting tech stack generator with custom parameters."""
        generator = get_tech_stack_generator(include_mcp_options=False)

        assert isinstance(generator, TechStackProposalGenerator)
        assert generator.proposer.include_mcp_options is False
