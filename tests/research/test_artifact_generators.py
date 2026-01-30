"""Tests for artifact generators."""

from __future__ import annotations


from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry,
    MonetizationStrategyGenerator,
    ProjectReadmeGenerator,
    get_monetization_generator,
    get_readme_generator,
    get_registry,
)


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


class TestArtifactGeneratorRegistry:
    """Test ArtifactGeneratorRegistry."""

    def test_registry_has_default_generators(self) -> None:
        """Test that registry has default generators registered."""
        registry = ArtifactGeneratorRegistry()

        assert registry.has_generator("cicd")
        assert registry.has_generator("monetization")
        assert registry.has_generator("readme")

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
