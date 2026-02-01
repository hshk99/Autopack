"""Tests for DeploymentGuide artifact generator."""

from __future__ import annotations

from autopack.artifact_generators import DeploymentGuide


class TestDeploymentGuide:
    """Test DeploymentGuide artifact generator."""

    def test_initialization(self) -> None:
        """Test DeploymentGuide initialization."""
        generator = DeploymentGuide()
        assert generator is not None

    def test_generate_basic_guide(self) -> None:
        """Test generating a basic deployment guide."""
        generator = DeploymentGuide()

        tech_stack = {
            "languages": ["Python"],
            "frameworks": ["FastAPI"],
            "database": ["PostgreSQL"],
            "cache": ["Redis"],
            "package_manager": "pip",
        }

        guide = generator.generate(
            project_name="MyApp",
            tech_stack=tech_stack,
        )

        # Verify basic structure
        assert "# Deployment Guide" in guide
        assert "## Introduction" in guide
        assert "## Table of Contents" in guide
        assert "## Quick Start" in guide
        assert "## Environment Configuration" in guide
        assert "## Security Checklist" in guide
        assert "## Troubleshooting" in guide
        assert "## Monitoring & Maintenance" in guide

    def test_generate_guide_with_specific_platforms(self) -> None:
        """Test generating deployment guide for specific platforms."""
        generator = DeploymentGuide()

        tech_stack = {
            "languages": ["JavaScript"],
            "frameworks": ["React", "Node.js"],
            "database": ["MongoDB"],
            "package_manager": "npm",
        }

        platforms = ["aws", "heroku"]
        guide = generator.generate(
            project_name="WebApp",
            tech_stack=tech_stack,
            platforms=platforms,
        )

        # Verify platform sections are included
        assert "## Amazon Web Services" in guide
        assert "## Heroku" in guide
        # Other platforms should not be included
        assert "## Google Cloud Platform" not in guide
        assert "## Microsoft Azure" not in guide

    def test_generate_guide_with_all_platforms(self) -> None:
        """Test generating deployment guide with all platforms."""
        generator = DeploymentGuide()

        tech_stack = {
            "languages": ["Go"],
            "frameworks": ["Gin"],
            "database": ["PostgreSQL"],
            "cache": ["Redis"],
        }

        guide = generator.generate(
            project_name="APIService",
            tech_stack=tech_stack,
        )

        # Verify all platform sections are included
        assert "## Amazon Web Services" in guide
        assert "## Google Cloud Platform" in guide
        assert "## Microsoft Azure" in guide
        assert "## Heroku" in guide
        assert "## Self-Hosted" in guide

    def test_guide_contains_aws_instructions(self) -> None:
        """Test that AWS deployment instructions are included."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["FastAPI"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["aws"],
        )

        # Verify AWS-specific content
        assert "EC2" in guide
        assert "Lambda" in guide
        assert "RDS" in guide
        assert "S3" in guide
        assert "aws lambda create-function" in guide

    def test_guide_contains_gcp_instructions(self) -> None:
        """Test that GCP deployment instructions are included."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Node.js"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["gcp"],
        )

        # Verify GCP-specific content
        assert "Compute Engine" in guide
        assert "Cloud Run" in guide
        assert "Firestore" in guide
        assert "gcloud" in guide

    def test_guide_contains_azure_instructions(self) -> None:
        """Test that Azure deployment instructions are included."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Django"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["azure"],
        )

        # Verify Azure-specific content
        assert "App Service" in guide
        assert "Azure Functions" in guide
        assert "CosmosDB" in guide
        assert "az " in guide

    def test_guide_contains_heroku_instructions(self) -> None:
        """Test that Heroku deployment instructions are included."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Express"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["heroku"],
        )

        # Verify Heroku-specific content
        assert "heroku" in guide.lower()
        assert "Procfile" in guide or "dyno" in guide.lower()
        assert "heroku addons:create" in guide

    def test_guide_contains_self_hosted_instructions(self) -> None:
        """Test that self-hosted deployment instructions are included."""
        generator = DeploymentGuide()

        tech_stack = {"container": "Docker"}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["self_hosted"],
        )

        # Verify self-hosted content
        assert "Docker" in guide
        assert "docker-compose" in guide.lower() or "docker compose" in guide.lower()
        assert "Kubernetes" in guide
        assert "Bare Metal" in guide or "VPS" in guide

    def test_guide_contains_security_checklist(self) -> None:
        """Test that security checklist is included."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["FastAPI"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify security checklist sections
        assert "## Security Checklist" in guide
        assert "Application Security" in guide
        assert "Data Security" in guide
        assert "Infrastructure Security" in guide
        assert "Access Control" in guide
        assert "Compliance" in guide

    def test_guide_contains_environment_configuration(self) -> None:
        """Test that environment configuration section is included."""
        generator = DeploymentGuide()

        tech_stack = {"database": ["PostgreSQL"], "cache": ["Redis"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify environment configuration
        assert "## Environment Configuration" in guide
        assert "DATABASE_URL" in guide
        assert "REDIS_URL" in guide
        assert ".env" in guide

    def test_guide_contains_troubleshooting(self) -> None:
        """Test that troubleshooting section is included."""
        generator = DeploymentGuide()

        tech_stack = {}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify troubleshooting section
        assert "## Troubleshooting" in guide
        assert "Common Issues" in guide
        assert "Application won't start" in guide
        assert "Database connection failed" in guide

    def test_guide_contains_monitoring_section(self) -> None:
        """Test that monitoring and maintenance section is included."""
        generator = DeploymentGuide()

        tech_stack = {}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify monitoring section
        assert "## Monitoring & Maintenance" in guide
        assert "Application Monitoring" in guide
        assert "Alerting Rules" in guide
        assert "Maintenance Tasks" in guide

    def test_invalid_platform_defaults_to_all(self) -> None:
        """Test that invalid platform names default to all platforms."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Django"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["invalid_platform", "fake_platform"],
        )

        # Should contain all platform sections
        assert "## Amazon Web Services" in guide
        assert "## Google Cloud Platform" in guide
        assert "## Microsoft Azure" in guide
        assert "## Heroku" in guide
        assert "## Self-Hosted" in guide

    def test_generate_returns_markdown_string(self) -> None:
        """Test that generate method returns a valid markdown string."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["FastAPI"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify it's a markdown string
        assert isinstance(guide, str)
        assert len(guide) > 1000  # Should be a substantial document
        assert guide.startswith("# Deployment Guide")

    def test_project_name_in_guide(self) -> None:
        """Test that project name is included in the guide."""
        generator = DeploymentGuide()

        project_name = "MySpecialProject"
        tech_stack = {"frameworks": ["FastAPI"]}
        guide = generator.generate(
            project_name=project_name,
            tech_stack=tech_stack,
        )

        # Project name should be in the introduction
        assert project_name in guide

    def test_quick_start_section_content(self) -> None:
        """Test that quick start section has proper content."""
        generator = DeploymentGuide()

        tech_stack = {
            "frameworks": ["FastAPI"],
            "package_manager": "pip",
        }
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
        )

        # Verify quick start content
        assert "## Quick Start" in guide
        assert "Prerequisites" in guide
        assert "General Deployment Steps" in guide
        assert "git clone" in guide

    def test_platform_specific_content_accuracy(self) -> None:
        """Test that platform-specific content is accurate and relevant."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Node.js"]}

        # Test GCP
        gcp_guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["gcp"],
        )
        assert "gcloud" in gcp_guide
        assert "Cloud Run" in gcp_guide

        # Test AWS
        aws_guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["aws"],
        )
        assert "aws " in aws_guide
        assert "EC2" in aws_guide

    def test_empty_platforms_list_uses_all(self) -> None:
        """Test that empty platforms list defaults to all platforms."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Django"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=[],
        )

        # Should contain all platforms since empty list defaults to all
        assert "## Amazon Web Services" in guide
        assert "## Google Cloud Platform" in guide
        assert "## Microsoft Azure" in guide

    def test_generate_with_project_requirements(self) -> None:
        """Test generate with project requirements."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["FastAPI"]}
        requirements = {
            "high_availability": True,
            "multi_region": True,
            "compliance": ["GDPR", "SOC2"],
        }

        guide = generator.generate(
            project_name="EnterpriseApp",
            tech_stack=tech_stack,
            project_requirements=requirements,
        )

        # Should have generated successfully
        assert isinstance(guide, str)
        assert "# Deployment Guide" in guide


class TestDeploymentGuidePlatformSections:
    """Test platform-specific sections in DeploymentGuide."""

    def test_aws_section_has_ec2_and_lambda_options(self) -> None:
        """Test that AWS section includes both EC2 and Lambda options."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Node.js"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["aws"],
        )

        # Check for both deployment options
        assert "Option 1: EC2" in guide
        assert "Option 2: Lambda" in guide
        assert "RDS" in guide

    def test_gcp_section_has_compute_engine_and_cloud_run(self) -> None:
        """Test that GCP section includes Compute Engine and Cloud Run."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["Python"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["gcp"],
        )

        # Check for both deployment options
        assert "Option 1: Compute Engine" in guide
        assert "Option 2: Cloud Run" in guide

    def test_azure_section_has_app_service_and_functions(self) -> None:
        """Test that Azure section includes App Service and Functions."""
        generator = DeploymentGuide()

        tech_stack = {"frameworks": ["ASP.NET"]}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["azure"],
        )

        # Check for both deployment options
        assert "Option 1: App Service" in guide
        assert "Option 2: Azure Functions" in guide

    def test_self_hosted_section_has_multiple_options(self) -> None:
        """Test that self-hosted section includes Docker, Kubernetes, and bare metal."""
        generator = DeploymentGuide()

        tech_stack = {"container": "Docker"}
        guide = generator.generate(
            project_name="TestApp",
            tech_stack=tech_stack,
            platforms=["self_hosted"],
        )

        # Check for multiple deployment options
        assert "Option 1: Docker Containerization" in guide
        assert "Option 2: Docker Compose" in guide
        assert "Option 3: Kubernetes" in guide
        assert "Option 4: Bare Metal / VPS" in guide
