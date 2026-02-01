"""Tests for CICDGenerator class.

Tests comprehensive CI/CD pipeline configuration generation for multiple platforms:
- GitHub Actions
- GitLab CI/CD
- Jenkins

Validates generation of test automation, build workflows, deployment workflows,
and monitoring/alerting configuration.
"""

import pytest

from autopack.research.artifact_generators import CICDGenerator


class TestCICDGeneratorInitialization:
    """Tests for CICDGenerator initialization."""

    def test_init_creates_generator(self):
        """Test that CICDGenerator initializes successfully."""
        generator = CICDGenerator()
        assert generator is not None
        assert hasattr(generator, "_analyzer")
        assert hasattr(generator, "_github_generator")
        assert hasattr(generator, "_gitlab_generator")
        assert hasattr(generator, "_jenkins_generator")

    def test_init_creates_all_platform_generators(self):
        """Test that all platform-specific generators are initialized."""
        generator = CICDGenerator()
        # Verify generators exist (they should be non-None)
        assert generator._analyzer is not None
        assert generator._github_generator is not None
        assert generator._gitlab_generator is not None
        assert generator._jenkins_generator is not None


class TestCICDGeneratorBasicGeneration:
    """Tests for basic CI/CD generation functionality."""

    @pytest.fixture
    def generator(self):
        """Provide a CICDGenerator instance for tests."""
        return CICDGenerator()

    @pytest.fixture
    def basic_tech_stack(self):
        """Provide a basic tech stack for testing."""
        return {
            "language": "python",
            "framework": "django",
            "package_manager": "pip",
            "build_tool": "make",
            "test_framework": "pytest",
        }

    def test_generate_returns_markdown_string(self, generator, basic_tech_stack):
        """Test that generate() returns a markdown string."""
        result = generator.generate(basic_tech_stack)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "# CI/CD Pipeline Guide" in result

    def test_generate_includes_executive_summary(self, generator, basic_tech_stack):
        """Test that generated content includes executive summary."""
        result = generator.generate(basic_tech_stack)
        assert "## Executive Summary" in result
        assert "Language" in result
        assert "Package Manager" in result

    def test_generate_includes_platform_recommendation(self, generator, basic_tech_stack):
        """Test that generated content includes platform recommendation."""
        result = generator.generate(basic_tech_stack)
        assert "## Platform Recommendation" in result
        assert "Recommended Platform" in result

    def test_generate_includes_pipeline_overview(self, generator, basic_tech_stack):
        """Test that generated content includes pipeline stages overview."""
        result = generator.generate(basic_tech_stack)
        assert "## Pipeline Stages Overview" in result
        assert "Lint & Format Checking" in result
        assert "Testing" in result
        assert "Build" in result

    def test_generate_includes_github_actions_section(self, generator, basic_tech_stack):
        """Test that generated content includes GitHub Actions configuration."""
        result = generator.generate(basic_tech_stack)
        assert "## GitHub Actions Configuration" in result
        assert ".github/workflows" in result

    def test_generate_includes_gitlab_ci_section(self, generator, basic_tech_stack):
        """Test that generated content includes GitLab CI configuration."""
        result = generator.generate(basic_tech_stack)
        assert "## GitLab CI/CD Configuration" in result
        assert ".gitlab-ci.yml" in result

    def test_generate_includes_jenkins_section(self, generator, basic_tech_stack):
        """Test that generated content includes Jenkins configuration."""
        result = generator.generate(basic_tech_stack)
        assert "## Jenkins Pipeline Configuration" in result
        assert "Jenkinsfile" in result

    def test_generate_includes_monitoring_section_by_default(self, generator, basic_tech_stack):
        """Test that monitoring section is included by default."""
        result = generator.generate(basic_tech_stack)
        assert "## Monitoring & Alerting" in result
        assert "Key Metrics to Monitor" in result

    def test_generate_excludes_monitoring_when_disabled(self, generator, basic_tech_stack):
        """Test that monitoring section is excluded when disabled."""
        result = generator.generate(basic_tech_stack, include_monitoring=False)
        assert "## Monitoring & Alerting" not in result

    def test_generate_includes_environment_section(self, generator, basic_tech_stack):
        """Test that generated content includes environment configuration."""
        result = generator.generate(basic_tech_stack)
        assert "## Environment Configuration" in result
        assert "Development" in result
        assert "Staging" in result
        assert "Production" in result

    def test_generate_includes_secrets_section(self, generator, basic_tech_stack):
        """Test that generated content includes secrets management."""
        result = generator.generate(basic_tech_stack)
        assert "## Secrets Management" in result
        assert "Required Secrets" in result
        assert "Best Practices" in result

    def test_generate_includes_best_practices(self, generator, basic_tech_stack):
        """Test that generated content includes CI/CD best practices."""
        result = generator.generate(basic_tech_stack)
        assert "## CI/CD Best Practices" in result
        assert "Code Quality" in result
        assert "Testing" in result
        assert "Security" in result


class TestCICDGeneratorWithDifferentLanguages:
    """Tests for generation with different programming languages."""

    @pytest.fixture
    def generator(self):
        """Provide a CICDGenerator instance for tests."""
        return CICDGenerator()

    def test_generate_with_nodejs_stack(self, generator):
        """Test generation with Node.js tech stack."""
        tech_stack = {
            "language": "node",
            "framework": "express",
            "package_manager": "npm",
            "test_framework": "jest",
        }
        result = generator.generate(tech_stack)
        assert "# CI/CD Pipeline Guide" in result
        assert "npm" in result.lower() or "node" in result.lower()

    def test_generate_with_python_stack(self, generator):
        """Test generation with Python tech stack."""
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "package_manager": "pip",
            "test_framework": "pytest",
        }
        result = generator.generate(tech_stack)
        assert "# CI/CD Pipeline Guide" in result
        assert "python" in result.lower()

    def test_generate_with_rust_stack(self, generator):
        """Test generation with Rust tech stack."""
        tech_stack = {
            "language": "rust",
            "package_manager": "cargo",
            "test_framework": "cargo test",
        }
        result = generator.generate(tech_stack)
        assert "# CI/CD Pipeline Guide" in result
        assert "rust" in result.lower()

    def test_generate_with_go_stack(self, generator):
        """Test generation with Go tech stack."""
        tech_stack = {
            "language": "go",
            "package_manager": "go mod",
            "test_framework": "go test",
        }
        result = generator.generate(tech_stack)
        assert "# CI/CD Pipeline Guide" in result
        assert "go" in result.lower()


class TestCICDGeneratorDocumentation:
    """Tests for documentation quality of generated content."""

    @pytest.fixture
    def generator(self):
        """Provide a CICDGenerator instance for tests."""
        return CICDGenerator()

    @pytest.fixture
    def basic_tech_stack(self):
        """Provide a basic tech stack for testing."""
        return {
            "language": "python",
            "framework": "django",
            "package_manager": "pip",
            "test_framework": "pytest",
        }

    def test_generated_content_is_markdown(self, generator, basic_tech_stack):
        """Test that generated content is properly formatted markdown."""
        result = generator.generate(basic_tech_stack)
        # Check for markdown headers
        assert "# " in result or "## " in result
        assert "```" in result  # Code blocks

    def test_github_actions_section_has_file_path(self, generator, basic_tech_stack):
        """Test that GitHub Actions section specifies correct file path."""
        result = generator.generate(basic_tech_stack)
        assert ".github/workflows" in result

    def test_gitlab_ci_section_has_file_path(self, generator, basic_tech_stack):
        """Test that GitLab CI section specifies correct file path."""
        result = generator.generate(basic_tech_stack)
        assert ".gitlab-ci.yml" in result

    def test_jenkins_section_has_file_path(self, generator, basic_tech_stack):
        """Test that Jenkins section specifies correct file path."""
        result = generator.generate(basic_tech_stack)
        assert "Jenkinsfile" in result

    def test_setup_instructions_are_provided_for_all_platforms(
        self, generator, basic_tech_stack
    ):
        """Test that setup instructions are provided for each platform."""
        result = generator.generate(basic_tech_stack)
        assert result.count("Setup Instructions") >= 3  # One for each platform

    def test_pipeline_stages_are_documented(self, generator, basic_tech_stack):
        """Test that all pipeline stages are documented."""
        result = generator.generate(basic_tech_stack)
        stages = [
            "Lint & Format",
            "Testing",
            "Build",
            "Security",
            "Deployment",
        ]
        for stage in stages:
            assert stage in result


class TestCICDGeneratorErrorHandling:
    """Tests for error handling in CICDGenerator."""

    @pytest.fixture
    def generator(self):
        """Provide a CICDGenerator instance for tests."""
        return CICDGenerator()

    def test_generate_with_empty_tech_stack(self, generator):
        """Test that generate handles empty tech stack gracefully."""
        tech_stack = {}
        result = generator.generate(tech_stack)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "# CI/CD Pipeline Guide" in result

    def test_generate_with_minimal_tech_stack(self, generator):
        """Test that generate handles minimal tech stack."""
        tech_stack = {"language": "python"}
        result = generator.generate(tech_stack)
        assert isinstance(result, str)
        assert "# CI/CD Pipeline Guide" in result

    def test_generate_with_none_values(self, generator):
        """Test that generate handles None values in tech stack."""
        tech_stack = {
            "language": "python",
            "framework": None,
            "test_framework": None,
        }
        result = generator.generate(tech_stack)
        assert isinstance(result, str)
        assert "# CI/CD Pipeline Guide" in result

    def test_generate_with_optional_parameters(self, generator):
        """Test that generate works with optional parameters."""
        tech_stack = {
            "language": "python",
        }
        result = generator.generate(
            tech_stack,
            project_requirements={"name": "test-project"},
            deployment_guidance={"target": "docker"},
            include_monitoring=True,
        )
        assert isinstance(result, str)


class TestCICDGeneratorIntegration:
    """Integration tests for CICDGenerator."""

    def test_generator_can_be_retrieved_from_registry(self):
        """Test that CICDGenerator is registered and retrievable."""
        from autopack.research.artifact_generators import ArtifactGeneratorRegistry

        registry = ArtifactGeneratorRegistry()
        generator = registry.get("cicd_generator")
        assert generator is not None
        assert isinstance(generator, CICDGenerator)

    def test_generator_listed_in_registry(self):
        """Test that CICDGenerator appears in registry listing."""
        from autopack.research.artifact_generators import ArtifactGeneratorRegistry

        registry = ArtifactGeneratorRegistry()
        generators = registry.list_generators()
        cicd_generator = [g for g in generators if g["name"] == "cicd_generator"]
        assert len(cicd_generator) == 1
        assert "comprehensive" in cicd_generator[0]["description"].lower()

    def test_registry_has_cicd_generator_method(self):
        """Test that registry can instantiate CICDGenerator."""
        from autopack.research.artifact_generators import ArtifactGeneratorRegistry

        registry = ArtifactGeneratorRegistry()
        assert registry.has_generator("cicd_generator")

    def test_full_workflow_generate_to_file(self, tmp_path):
        """Test complete workflow from generation to file writing."""
        generator = CICDGenerator()
        tech_stack = {
            "language": "python",
            "framework": "fastapi",
            "package_manager": "pip",
            "test_framework": "pytest",
        }

        # Generate content
        content = generator.generate(tech_stack)
        assert content is not None

        # Write to file with UTF-8 encoding to handle unicode characters
        output_file = tmp_path / "CI_CD_PIPELINE.md"
        output_file.write_text(content, encoding="utf-8")

        # Verify file
        assert output_file.exists()
        assert output_file.stat().st_size > 0

        # Verify content
        file_content = output_file.read_text(encoding="utf-8")
        assert "# CI/CD Pipeline Guide" in file_content
