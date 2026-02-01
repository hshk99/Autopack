"""Tests for artifact generators."""

from __future__ import annotations

from autopack.research.analysis.budget_enforcement import BudgetEnforcer
from autopack.research.analysis.monetization_analysis import (
    MonetizationAnalysisResult, MonetizationAnalyzer, MonetizationModel,
    PricingStrategy, PricingTier, ProjectType, RevenueConfidence,
    RevenueProjection)
from autopack.research.artifact_generators import (
    ArtifactGeneratorRegistry, MonetizationStrategyGenerator,
    ProjectBriefGenerator, ProjectReadmeGenerator, get_monetization_analyzer,
    get_monetization_generator, get_project_brief_generator,
    get_readme_generator, get_registry)


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

    def test_generate_from_analysis(self) -> None:
        """Test generating strategy from MonetizationAnalysisResult."""
        generator = MonetizationStrategyGenerator()

        # Create a mock analysis result
        result = MonetizationAnalysisResult(
            project_type=ProjectType.SAAS,
            recommended_model=MonetizationModel.SUBSCRIPTION,
            pricing_strategy=PricingStrategy.VALUE_BASED,
            pricing_rationale="Value-based pricing aligns cost with outcomes",
            pricing_tiers=[
                PricingTier(
                    name="Starter",
                    price_monthly=19.0,
                    price_yearly=190.0,
                    features=["Core features", "Email support"],
                    target_audience="Individuals",
                ),
                PricingTier(
                    name="Pro",
                    price_monthly=49.0,
                    price_yearly=490.0,
                    features=["All features", "Priority support"],
                    target_audience="Teams",
                    recommended=True,
                ),
            ],
            revenue_projections=[
                RevenueProjection(
                    timeframe="year_1",
                    users=5000,
                    paying_users=150,
                    mrr=4500.0,
                    arr=54000.0,
                    confidence=RevenueConfidence.MEDIUM,
                ),
            ],
            target_arpu=35.0,
            target_ltv=700.0,
            confidence=RevenueConfidence.MEDIUM,
            key_assumptions=["3% conversion rate"],
            risks=["Churn may exceed projections"],
        )

        content = generator.generate_from_analysis(result)

        # Verify structure
        assert "# Monetization Strategy" in content
        assert "## Overview" in content
        assert "## Pricing Tiers" in content
        assert "## Revenue Projections" in content
        assert "## Key Metrics Targets" in content

        # Verify content
        assert "Subscription" in content
        assert "Value Based" in content
        assert "Starter" in content
        assert "$19" in content
        assert "Pro" in content
        assert "(Recommended)" in content
        assert "$4,500" in content  # MRR
        assert "$35" in content  # ARPU
        assert "3% conversion rate" in content
        assert "Churn may exceed projections" in content

    def test_analyze_and_generate(self) -> None:
        """Test analyze_and_generate flow."""
        generator = MonetizationStrategyGenerator()

        content = generator.analyze_and_generate(
            project_type=ProjectType.SAAS,
            project_characteristics={
                "has_api": True,
                "is_b2b": True,
            },
        )

        # Should produce complete strategy document
        assert "# Monetization Strategy" in content
        assert "## Overview" in content
        assert "## Pricing Tiers" in content
        assert "## Revenue Projections" in content

        # Should be able to get the analysis result
        result = generator.get_analysis_result()
        assert result is not None
        assert result.project_type == ProjectType.SAAS

    def test_analyze_and_generate_with_budget_enforcer(self) -> None:
        """Test analyze_and_generate with budget enforcement."""
        budget_enforcer = BudgetEnforcer(total_budget=5000.0)
        generator = MonetizationStrategyGenerator(budget_enforcer=budget_enforcer)

        content = generator.analyze_and_generate(project_type=ProjectType.SAAS)

        # Should complete successfully
        assert "# Monetization Strategy" in content

        # Budget should have been used
        assert budget_enforcer.metrics.total_spent > 0

    def test_analyze_and_generate_budget_insufficient(self) -> None:
        """Test analyze_and_generate with insufficient budget."""
        budget_enforcer = BudgetEnforcer(total_budget=50.0)
        budget_enforcer.record_cost("previous", 50.0)  # Exhaust budget

        generator = MonetizationStrategyGenerator(budget_enforcer=budget_enforcer)

        content = generator.analyze_and_generate(project_type=ProjectType.SAAS)

        # Should return limited guidance
        assert "# Monetization Strategy" in content
        assert "budget constraints" in content.lower()
        assert "General Recommendations" in content

    def test_get_analysis_result_without_analysis(self) -> None:
        """Test get_analysis_result returns None when no analysis performed."""
        generator = MonetizationStrategyGenerator()

        result = generator.get_analysis_result()
        assert result is None

    def test_generator_with_competitive_data(self) -> None:
        """Test analyze_and_generate with competitive data."""
        generator = MonetizationStrategyGenerator()

        content = generator.analyze_and_generate(
            project_type=ProjectType.SAAS,
            competitive_data={
                "competitors": [
                    {
                        "name": "Competitor A",
                        "pricing_model": "subscription",
                        "price_range": "$29-99/month",
                        "market_position": "leader",
                    },
                ]
            },
        )

        assert "# Monetization Strategy" in content
        assert "Competitive Pricing Analysis" in content
        assert "Competitor A" in content


class TestProjectBriefGenerator:
    """Test ProjectBriefGenerator with monetization enhancements."""

    def test_generate_basic_project_brief(self) -> None:
        """Test generating a basic project brief."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "problem_statement": "Users need better project management",
            "solution": "AI-powered project tracking",
            "target_audience": "Small to medium businesses",
            "market_opportunity": {"total_addressable_market": "$10B"},
            "features": [
                {"name": "Task Tracking", "description": "Track tasks", "priority": "HIGH"},
                {"name": "Reporting", "description": "Generate reports"},
            ],
        }

        brief = generator.generate(research_findings=research_findings)

        # Verify structure
        assert "# Project Brief" in brief
        assert "## Executive Summary" in brief
        assert "## Technical Requirements" in brief
        assert "## Feature Scope" in brief
        assert "## Monetization Strategy" in brief
        assert "## Market Positioning" in brief
        assert "## Unit Economics" in brief

        # Verify content
        assert "Users need better project management" in brief
        assert "AI-powered project tracking" in brief
        assert "$10B" in brief

    def test_generate_monetization_with_data(self) -> None:
        """Test monetization section with complete data."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "monetization": {
                "revenue_models": [
                    {
                        "name": "Subscription",
                        "description": "Monthly recurring revenue",
                        "fit_score": "8",
                    },
                    {"name": "Usage-Based", "description": "Pay per API call"},
                ],
                "primary_model": "Subscription",
                "pricing_strategy": {
                    "type": "Value-based pricing",
                    "rationale": "Align price with value delivered",
                },
                "pricing_tiers": [
                    {
                        "name": "Free",
                        "price": "$0/mo",
                        "features": ["5 projects", "1 user"],
                        "target": "Individual users",
                    },
                    {
                        "name": "Pro",
                        "price": "$29/mo",
                        "features": ["Unlimited projects", "5 users", "API access"],
                        "target": "Small teams",
                    },
                    {
                        "name": "Enterprise",
                        "price": "Custom",
                        "features": ["SSO", "Dedicated support"],
                        "target": "Large organizations",
                    },
                ],
            }
        }

        section = generator.generate_monetization(research_findings)

        assert "## Monetization Strategy" in section
        assert "### Revenue Models" in section
        assert "Subscription" in section
        assert "(Fit: 8/10)" in section
        assert "### Pricing Strategy" in section
        assert "Value-based pricing" in section
        assert "### Pricing Tiers" in section
        assert "| Free | $0/mo" in section
        assert "| Pro | $29/mo" in section

    def test_generate_monetization_without_data(self) -> None:
        """Test monetization section generates default guidance when no data."""
        generator = ProjectBriefGenerator()

        research_findings = {}

        section = generator.generate_monetization(research_findings)

        assert "## Monetization Strategy" in section
        assert "### Revenue Model Options" in section
        assert "Subscription (SaaS)" in section
        assert "Freemium" in section
        assert "Usage-Based" in section

    def test_generate_market_positioning_with_data(self) -> None:
        """Test market positioning section with competitive data."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "market_opportunity": {
                "total_addressable_market": "$50B",
                "serviceable_addressable_market": "$5B",
                "serviceable_obtainable_market": "$500M",
                "segments": [
                    {"name": "Enterprise", "size": "60%"},
                    {"name": "SMB", "size": "40%"},
                ],
            },
            "differentiation": {
                "unique_value_proposition": "Only AI-native solution",
                "competitive_advantages": [
                    "10x faster processing",
                    "Built-in integrations",
                ],
                "moat": "Proprietary ML models",
            },
            "positioning_statement": "For teams who need speed, we provide the fastest solution.",
        }

        competitive_data = {
            "competitors": [
                {
                    "name": "Competitor A",
                    "strengths": ["Market leader", "Brand recognition"],
                    "weaknesses": ["Slow innovation", "High price"],
                    "price_point": "$99/mo",
                },
                {
                    "name": "Competitor B",
                    "strengths": ["Low cost"],
                    "weaknesses": ["Limited features"],
                    "price_point": "$19/mo",
                },
            ]
        }

        section = generator.generate_market_positioning(research_findings, competitive_data)

        assert "## Market Positioning" in section
        assert "### Target Market" in section
        assert "TAM" in section
        assert "$50B" in section
        assert "SAM" in section
        assert "SOM" in section
        assert "### Competitive Landscape" in section
        assert "Competitor A" in section
        assert "Competitor B" in section
        assert "### Differentiation Strategy" in section
        assert "Only AI-native solution" in section
        assert "10x faster processing" in section
        assert "Proprietary ML models" in section
        assert "### Positioning Statement" in section

    def test_analyze_unit_economics_with_data(self) -> None:
        """Test unit economics analysis with complete data."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "unit_economics": {
                "customer_acquisition_cost": "$150",
                "lifetime_value": "$600",
                "ltv_cac_ratio": "4:1",
                "payback_period": "6 months",
                "margins": {
                    "gross_margin": "75%",
                    "contribution_margin": "60%",
                    "net_margin": "15%",
                },
                "projections": {
                    "Year 1": {"revenue": "$100K", "users": "500", "mrr": "$8K"},
                    "Year 2": {"revenue": "$500K", "users": "2000", "mrr": "$42K"},
                },
                "breakeven": {
                    "point": "1,000 customers",
                    "timeline": "18 months",
                    "assumptions": ["5% monthly churn", "$50 ARPU"],
                },
            }
        }

        section = generator.analyze_unit_economics(research_findings)

        assert "## Unit Economics" in section
        assert "### Key Metrics" in section
        assert "CAC" in section
        assert "$150" in section
        assert "LTV" in section
        assert "$600" in section
        assert "4:1" in section
        assert "6 months" in section
        assert "### Margin Analysis" in section
        assert "75%" in section
        assert "### Revenue Projections" in section
        assert "Year 1" in section
        assert "$100K" in section
        assert "### Break-even Analysis" in section
        assert "1,000 customers" in section

    def test_analyze_unit_economics_without_data(self) -> None:
        """Test unit economics generates framework when no data."""
        generator = ProjectBriefGenerator()

        research_findings = {}

        section = generator.analyze_unit_economics(research_findings)

        assert "## Unit Economics" in section
        assert "### Key Metrics to Track" in section
        assert "Customer Acquisition Cost (CAC)" in section
        assert "Lifetime Value (LTV)" in section
        assert "LTV:CAC Ratio" in section
        assert "### Margin Targets" in section

    def test_generate_executive_summary(self) -> None:
        """Test executive summary section generation."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "problem_statement": "Complex problem",
            "solution": "Simple solution",
            "market_opportunity": {"total_addressable_market": "$1B"},
            "target_audience": "Developers",
        }

        section = generator._generate_executive_summary(research_findings)

        assert "## Executive Summary" in section
        assert "Complex problem" in section
        assert "Simple solution" in section
        assert "$1B" in section
        assert "Developers" in section

    def test_generate_technical_section(self) -> None:
        """Test technical requirements section generation."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "technical_constraints": ["Must support offline mode", "Low latency required"]
        }

        tech_stack = {
            "languages": ["Python", "TypeScript"],
            "frameworks": ["FastAPI", "React"],
            "architecture_pattern": "Microservices",
            "infrastructure": ["AWS", "Kubernetes"],
        }

        section = generator._generate_technical_section(research_findings, tech_stack)

        assert "## Technical Requirements" in section
        assert "Python, TypeScript" in section
        assert "FastAPI, React" in section
        assert "Microservices" in section
        assert "AWS" in section
        assert "Must support offline mode" in section

    def test_generate_feature_scope(self) -> None:
        """Test feature scope section generation."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "features": [
                {"name": "Auth", "description": "User authentication", "priority": "HIGH"},
                "Basic CRUD operations",
            ],
            "mvp_features": ["User login", "Basic dashboard"],
            "future_features": ["AI recommendations", "Mobile app"],
        }

        section = generator._generate_feature_scope(research_findings)

        assert "## Feature Scope" in section
        assert "### Core Features" in section
        assert "Auth" in section
        assert "[HIGH]" in section
        assert "Basic CRUD operations" in section
        assert "### MVP Scope" in section
        assert "User login" in section
        assert "### Future Features" in section
        assert "AI recommendations" in section

    def test_generate_growth_strategy(self) -> None:
        """Test growth strategy section generation."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "growth_strategy": {
                "acquisition_channels": [
                    {"name": "SEO", "priority": "HIGH"},
                    {"name": "Content Marketing", "priority": "MEDIUM"},
                ],
                "growth_levers": ["Viral referrals", "API integrations"],
                "expansion": "Expand to European markets in Year 2",
            }
        }

        section = generator._generate_growth_strategy(research_findings)

        assert "## Growth Strategy" in section
        assert "SEO" in section
        assert "[HIGH]" in section
        assert "Viral referrals" in section
        assert "European markets" in section

    def test_generate_risk_assessment(self) -> None:
        """Test risk assessment section generation."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "risks": [
                {
                    "name": "Market competition",
                    "impact": "High",
                    "likelihood": "Medium",
                    "mitigation": "Differentiate on speed",
                },
                "Regulatory changes",
            ]
        }

        section = generator._generate_risk_assessment(research_findings)

        assert "## Risk Assessment" in section
        assert "Market competition" in section
        assert "High" in section
        assert "Differentiate on speed" in section
        assert "Regulatory changes" in section

    def test_full_brief_generation_with_all_data(self) -> None:
        """Test complete brief generation with all data provided."""
        generator = ProjectBriefGenerator()

        research_findings = {
            "problem_statement": "Teams struggle with project visibility",
            "solution": "Real-time collaborative dashboard",
            "target_audience": "Engineering teams",
            "market_opportunity": {
                "total_addressable_market": "$25B",
                "serviceable_addressable_market": "$2.5B",
            },
            "features": [
                {"name": "Dashboard", "description": "Real-time metrics"},
            ],
            "monetization": {
                "primary_model": "Subscription",
                "pricing_tiers": [
                    {
                        "name": "Starter",
                        "price": "$0",
                        "features": ["Basic"],
                        "target": "Individuals",
                    }
                ],
            },
            "unit_economics": {
                "customer_acquisition_cost": "$100",
                "lifetime_value": "$500",
            },
            "differentiation": {
                "unique_value_proposition": "Built for remote teams",
            },
            "growth_strategy": {
                "acquisition_channels": [{"name": "Product Hunt", "priority": "HIGH"}],
            },
            "risks": [
                {
                    "name": "Tech debt",
                    "impact": "Medium",
                    "likelihood": "High",
                    "mitigation": "Regular refactoring",
                }
            ],
        }

        tech_stack = {
            "languages": ["TypeScript"],
            "frameworks": ["Next.js"],
        }

        competitive_data = {
            "competitors": [
                {
                    "name": "Jira",
                    "strengths": ["Market leader"],
                    "weaknesses": ["Complex"],
                    "price_point": "$10/user",
                }
            ]
        }

        brief = generator.generate(
            research_findings=research_findings,
            tech_stack=tech_stack,
            competitive_data=competitive_data,
        )

        # Verify all major sections exist
        assert "# Project Brief" in brief
        assert "## Executive Summary" in brief
        assert "## Technical Requirements" in brief
        assert "## Feature Scope" in brief
        assert "## Monetization Strategy" in brief
        assert "## Market Positioning" in brief
        assert "## Unit Economics" in brief
        assert "## Growth Strategy" in brief
        assert "## Risk Assessment" in brief

        # Verify key content
        assert "Teams struggle with project visibility" in brief
        assert "$25B" in brief
        assert "TypeScript" in brief
        assert "Subscription" in brief
        assert "$100" in brief
        assert "Jira" in brief


class TestArtifactGeneratorRegistry:
    """Test ArtifactGeneratorRegistry."""

    def test_registry_has_default_generators(self) -> None:
        """Test that registry has default generators registered."""
        registry = ArtifactGeneratorRegistry()

        assert registry.has_generator("cicd")
        assert registry.has_generator("monetization")
        assert registry.has_generator("readme")
        assert registry.has_generator("project_brief")

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

    def test_get_project_brief_generator(self) -> None:
        """Test getting project brief generator via convenience function."""
        generator = get_project_brief_generator()

        assert isinstance(generator, ProjectBriefGenerator)

    def test_get_monetization_generator_with_budget(self) -> None:
        """Test getting monetization generator with budget enforcer."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        generator = get_monetization_generator(budget_enforcer=budget_enforcer)

        assert isinstance(generator, MonetizationStrategyGenerator)
        assert generator._budget_enforcer is budget_enforcer

    def test_get_monetization_analyzer(self) -> None:
        """Test getting monetization analyzer via convenience function."""
        analyzer = get_monetization_analyzer()

        assert isinstance(analyzer, MonetizationAnalyzer)

    def test_get_monetization_analyzer_with_budget(self) -> None:
        """Test getting monetization analyzer with budget enforcer."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        analyzer = get_monetization_analyzer(budget_enforcer=budget_enforcer)

        assert isinstance(analyzer, MonetizationAnalyzer)
        assert analyzer._budget_enforcer is budget_enforcer
