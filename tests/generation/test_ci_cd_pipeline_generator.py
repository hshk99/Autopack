"""Tests for CI/CD Pipeline Generator.

Tests for CICDPipelineGenerator class that generates CI/CD configurations
for GitHub Actions, GitLab CI, and generic pipeline platforms.
"""

import pytest
import yaml

from autopack.generation.ci_cd_pipeline_generator import (
    CICDConfig,
    CICDPipelineGenerator,
)


class TestCICDConfig:
    """Tests for CICDConfig dataclass."""

    def test_cicd_config_creation_default(self):
        """Test CICDConfig creation with default values."""
        config = CICDConfig(provider="github_actions")

        assert config.provider == "github_actions"
        assert config.default_branch == "main"
        assert config.include_build is True
        assert config.include_test is True
        assert config.include_security_scan is True
        assert config.include_deploy is True
        assert config.language is None
        assert config.deployment_targets is None
        assert config.env_vars is None

    def test_cicd_config_creation_custom(self):
        """Test CICDConfig creation with custom values."""
        env_vars = {"NODE_ENV": "production", "LOG_LEVEL": "debug"}
        config = CICDConfig(
            provider="gitlab_ci",
            default_branch="develop",
            include_build=False,
            include_security_scan=False,
            language="python",
            deployment_targets=["aws", "docker"],
            env_vars=env_vars,
        )

        assert config.provider == "gitlab_ci"
        assert config.default_branch == "develop"
        assert config.include_build is False
        assert config.include_security_scan is False
        assert config.language == "python"
        assert config.deployment_targets == ["aws", "docker"]
        assert config.env_vars == env_vars


class TestCICDPipelineGeneratorBasics:
    """Basic tests for CICDPipelineGenerator."""

    def test_generator_initialization_default(self):
        """Test CICDPipelineGenerator initialization with defaults."""
        generator = CICDPipelineGenerator()

        assert generator.provider == "github_actions"
        assert generator.default_branch == "main"
        assert generator.include_build is True
        assert generator.include_test is True
        assert generator.include_security_scan is True
        assert generator.include_deploy is True

    def test_generator_initialization_custom(self):
        """Test CICDPipelineGenerator initialization with custom values."""
        generator = CICDPipelineGenerator(
            provider="gitlab_ci",
            default_branch="develop",
            include_build=False,
            include_deploy=False,
        )

        assert generator.provider == "gitlab_ci"
        assert generator.default_branch == "develop"
        assert generator.include_build is False
        assert generator.include_deploy is False

    def test_language_detection_next_js(self):
        """Test language detection for Next.js."""
        generator = CICDPipelineGenerator()
        language = generator._detect_language("Next.js", "Full Stack")

        assert language == "node"

    def test_language_detection_django(self):
        """Test language detection for Django."""
        generator = CICDPipelineGenerator()
        language = generator._detect_language("Django", "Web Framework")

        assert language == "python"

    def test_language_detection_rust(self):
        """Test language detection for Rust."""
        generator = CICDPipelineGenerator()
        language = generator._detect_language("Rust", "Systems")

        assert language == "rust"

    def test_language_detection_unknown(self):
        """Test language detection for unknown stack defaults to node."""
        generator = CICDPipelineGenerator()
        language = generator._detect_language("UnknownTech", "Unknown")

        assert language == "node"


class TestGitHubActionsGeneration:
    """Tests for GitHub Actions workflow generation."""

    def test_generate_github_actions_basic(self):
        """Test basic GitHub Actions workflow generation."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Node.js", "language": "node"}

        workflow_yaml = generator.generate_github_actions(tech_stack)

        assert workflow_yaml is not None
        assert "name:" in workflow_yaml
        assert "on:" in workflow_yaml
        assert "jobs:" in workflow_yaml

        # Parse YAML to verify structure
        workflow = yaml.safe_load(workflow_yaml)
        assert "name" in workflow
        assert "on" in workflow
        assert "jobs" in workflow
        assert "test" in workflow["jobs"]
        assert "build" in workflow["jobs"]

    def test_generate_github_actions_with_deployment(self):
        """Test GitHub Actions generation with deployment job."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {
            "name": "React App",
            "language": "node",
            "deploy_provider": "vercel",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        assert "deploy" in workflow["jobs"]
        assert workflow["jobs"]["deploy"]["needs"] == "build"

    def test_generate_github_actions_no_security_scan(self):
        """Test GitHub Actions generation without security scanning."""
        generator = CICDPipelineGenerator(include_security_scan=False)
        tech_stack = {"name": "Node.js", "language": "node"}

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        assert "security" not in workflow["jobs"]

    def test_generate_github_actions_python(self):
        """Test GitHub Actions generation for Python project."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "FastAPI", "language": "python"}

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        # Check that Python-specific setup is included
        test_job = workflow["jobs"]["test"]
        assert any(
            step.get("uses", "").startswith("actions/setup-python")
            for step in test_job.get("steps", [])
        )

    def test_github_actions_environment_variables(self):
        """Test GitHub Actions workflow includes environment variables."""
        generator = CICDPipelineGenerator()
        tech_stack = {
            "name": "Node.js",
            "language": "node",
            "env_vars": {"NODE_ENV": "production", "DEBUG": "false"},
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        assert "env" in workflow
        assert workflow["env"]["CI"] == "true"
        assert workflow["env"]["NODE_ENV"] == "production"
        assert workflow["env"]["DEBUG"] == "false"

    def test_github_actions_with_custom_test_command(self):
        """Test GitHub Actions with custom test command."""
        generator = CICDPipelineGenerator()
        tech_stack = {
            "name": "Node.js",
            "language": "node",
            "test_command": "npm run test:ci",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        test_job = workflow["jobs"]["test"]
        test_steps = [s for s in test_job["steps"] if s.get("run") == "npm run test:ci"]
        assert len(test_steps) > 0

    def test_github_actions_docker_deployment(self):
        """Test GitHub Actions with Docker deployment."""
        generator = CICDPipelineGenerator()
        tech_stack = {
            "name": "Node.js",
            "language": "node",
            "deploy_provider": "docker",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        docker_steps = [
            s
            for s in deploy_job["steps"]
            if "docker" in s.get("uses", "").lower() or "docker" in s.get("name", "").lower()
        ]
        assert len(docker_steps) > 0


class TestGitLabCIGeneration:
    """Tests for GitLab CI configuration generation."""

    def test_generate_gitlab_ci_basic(self):
        """Test basic GitLab CI configuration generation."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Node.js", "language": "node"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)

        assert gitlab_ci_yaml is not None
        assert "stages:" in gitlab_ci_yaml
        assert "variables:" in gitlab_ci_yaml

        config = yaml.safe_load(gitlab_ci_yaml)
        assert "stages" in config
        assert "variables" in config
        assert "CI" in config["variables"]

    def test_generate_gitlab_ci_stages(self):
        """Test GitLab CI includes all required stages."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Python", "language": "python"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)
        config = yaml.safe_load(gitlab_ci_yaml)

        assert "stages" in config
        assert "lint" in config["stages"]
        assert "test" in config["stages"]
        assert "build" in config["stages"]
        assert "deploy" in config["stages"]

    def test_generate_gitlab_ci_with_test_job(self):
        """Test GitLab CI generation includes test job."""
        generator = CICDPipelineGenerator(include_test=True)
        tech_stack = {"name": "Python", "language": "python"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)
        config = yaml.safe_load(gitlab_ci_yaml)

        assert "test:script" in config
        assert config["test:script"]["stage"] == "test"
        assert "script" in config["test:script"]

    def test_generate_gitlab_ci_without_test(self):
        """Test GitLab CI generation without test job."""
        generator = CICDPipelineGenerator(include_test=False)
        tech_stack = {"name": "Python", "language": "python"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)
        config = yaml.safe_load(gitlab_ci_yaml)

        assert "test:script" not in config

    def test_generate_gitlab_ci_python_image(self):
        """Test GitLab CI uses correct Python image."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Django", "language": "python"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)
        config = yaml.safe_load(gitlab_ci_yaml)

        assert "test:script" in config
        assert "python:3.11" in config["test:script"]["image"]

    def test_generate_gitlab_ci_artifacts(self):
        """Test GitLab CI build job includes artifacts."""
        generator = CICDPipelineGenerator(include_build=True)
        tech_stack = {"name": "Node.js", "language": "node"}

        gitlab_ci_yaml = generator.generate_gitlab_ci(tech_stack)
        config = yaml.safe_load(gitlab_ci_yaml)

        assert "build:artifacts" in config
        assert "artifacts" in config["build:artifacts"]
        assert "paths" in config["build:artifacts"]["artifacts"]


class TestGenericPipelineGeneration:
    """Tests for generic CI/CD pipeline generation."""

    def test_generate_generic_ci_basic(self):
        """Test basic generic CI/CD pipeline generation."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Node.js", "language": "node"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)

        assert pipeline_yaml is not None
        assert "name:" in pipeline_yaml
        assert "stages:" in pipeline_yaml
        assert "jobs:" in pipeline_yaml

        pipeline = yaml.safe_load(pipeline_yaml)
        assert "name" in pipeline
        assert "stages" in pipeline
        assert "jobs" in pipeline

    def test_generate_generic_ci_stages(self):
        """Test generic pipeline includes all stages."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "Python", "language": "python"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        assert "stages" in pipeline
        assert "lint" in pipeline["stages"]
        assert "test" in pipeline["stages"]
        assert "build" in pipeline["stages"]
        assert "deploy" in pipeline["stages"]

    def test_generate_generic_ci_with_jobs(self):
        """Test generic pipeline includes test, build, and deploy jobs."""
        generator = CICDPipelineGenerator(
            include_test=True,
            include_build=True,
            include_deploy=True,
        )
        tech_stack = {"name": "Node.js", "language": "node"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        assert "test" in pipeline["jobs"]
        assert "build" in pipeline["jobs"]
        assert "deploy" in pipeline["jobs"]

    def test_generate_generic_ci_deploy_requires_approval(self):
        """Test generic pipeline deploy job requires approval."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {"name": "Node.js", "language": "node"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        deploy_job = pipeline["jobs"]["deploy"]
        assert deploy_job["requires_approval"] is True

    def test_generic_pipeline_language_detected(self):
        """Test generic pipeline includes detected language."""
        generator = CICDPipelineGenerator()
        tech_stack = {"name": "FastAPI"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        assert pipeline["language"] == "python"

    def test_generic_pipeline_default_branch(self):
        """Test generic pipeline uses correct default branch."""
        generator = CICDPipelineGenerator(default_branch="develop")
        tech_stack = {"name": "Node.js"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        assert pipeline["default_branch"] == "develop"


class TestSecurityScanning:
    """Tests for security scanning configuration."""

    def test_security_job_node_codeql(self):
        """Test security job includes CodeQL for Node.js."""
        generator = CICDPipelineGenerator(include_security_scan=True)
        tech_stack = {"name": "React", "language": "node"}

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        security_job = workflow["jobs"]["security"]
        codeql_steps = [s for s in security_job["steps"] if "codeql" in s.get("uses", "").lower()]
        assert len(codeql_steps) > 0

    def test_security_job_python_codeql(self):
        """Test security job includes CodeQL for Python."""
        generator = CICDPipelineGenerator(include_security_scan=True)
        tech_stack = {"name": "Django", "language": "python"}

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        security_job = workflow["jobs"]["security"]
        codeql_steps = [s for s in security_job["steps"] if "codeql" in s.get("uses", "").lower()]
        assert len(codeql_steps) > 0

    def test_generic_security_scanning_commands(self):
        """Test generic pipeline security scanning commands."""
        generator = CICDPipelineGenerator(include_security_scan=True)
        tech_stack = {"name": "Node.js", "language": "node"}

        pipeline_yaml = generator.generate_generic_ci(tech_stack)
        pipeline = yaml.safe_load(pipeline_yaml)

        assert "security" in pipeline["jobs"]
        security_job = pipeline["jobs"]["security"]
        assert len(security_job["commands"]) > 0


class TestDeploymentProviders:
    """Tests for deployment provider-specific configuration."""

    def test_vercel_deployment_configuration(self):
        """Test Vercel deployment configuration."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {
            "name": "Next.js",
            "language": "node",
            "deploy_provider": "vercel",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        vercel_steps = [s for s in deploy_job["steps"] if "vercel" in s.get("uses", "").lower()]
        assert len(vercel_steps) > 0

    def test_netlify_deployment_configuration(self):
        """Test Netlify deployment configuration."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {
            "name": "React",
            "language": "node",
            "deploy_provider": "netlify",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        netlify_steps = [s for s in deploy_job["steps"] if "netlify" in s.get("uses", "").lower()]
        assert len(netlify_steps) > 0

    def test_docker_deployment_configuration(self):
        """Test Docker deployment configuration."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {
            "name": "Python API",
            "language": "python",
            "deploy_provider": "docker",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        docker_steps = [
            s
            for s in deploy_job["steps"]
            if "docker" in s.get("uses", "").lower() or "docker" in s.get("name", "").lower()
        ]
        assert len(docker_steps) > 0

    def test_unknown_deployment_provider_fallback(self):
        """Test unknown deployment provider uses fallback message."""
        generator = CICDPipelineGenerator(include_deploy=True)
        tech_stack = {
            "name": "App",
            "language": "node",
            "deploy_provider": "unknown_platform",
        }

        workflow_yaml = generator.generate_github_actions(tech_stack)
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        fallback_steps = [
            s for s in deploy_job["steps"] if "Configure deployment" in s.get("run", "")
        ]
        assert len(fallback_steps) > 0


class TestLanguageSupport:
    """Tests for various programming languages."""

    @pytest.mark.parametrize(
        "language,expected_version",
        [
            ("node", "20"),
            ("python", "3.11"),
            ("rust", "stable"),
            ("go", "1.21"),
            ("ruby", "3.2"),
            ("php", "8.2"),
        ],
    )
    def test_language_versions(self, language, expected_version):
        """Test correct language versions are used."""
        generator = CICDPipelineGenerator()

        # Test that versions are correctly mapped
        assert generator._DEFAULT_VERSIONS[language] == expected_version

    @pytest.mark.parametrize(
        "language",
        ["node", "python", "rust", "go", "ruby", "php"],
    )
    def test_test_commands_available(self, language):
        """Test that test commands are available for all languages."""
        generator = CICDPipelineGenerator()

        assert language in generator._TEST_COMMANDS
        assert len(generator._TEST_COMMANDS[language]) > 0

    @pytest.mark.parametrize(
        "language",
        ["node", "python", "rust", "go", "ruby", "php"],
    )
    def test_build_commands_available(self, language):
        """Test that build commands are available for all languages."""
        generator = CICDPipelineGenerator()

        assert language in generator._BUILD_COMMANDS
        assert len(generator._BUILD_COMMANDS[language]) > 0


class TestWorkflowTrigggers:
    """Tests for workflow triggers."""

    def test_github_actions_triggers_on_push_and_pr(self):
        """Test GitHub Actions workflow triggers on push and PR."""
        generator = CICDPipelineGenerator(default_branch="main")
        workflow_yaml = generator.generate_github_actions({})
        workflow = yaml.safe_load(workflow_yaml)

        assert "on" in workflow
        assert "push" in workflow["on"]
        assert "pull_request" in workflow["on"]
        assert "main" in workflow["on"]["push"]["branches"]

    def test_github_actions_deploy_only_on_main_branch(self):
        """Test deploy job only runs on main branch."""
        generator = CICDPipelineGenerator(
            default_branch="main",
            include_deploy=True,
        )
        workflow_yaml = generator.generate_github_actions({})
        workflow = yaml.safe_load(workflow_yaml)

        deploy_job = workflow["jobs"]["deploy"]
        assert "if" in deploy_job
        assert "refs/heads/main" in deploy_job["if"]

    def test_gitlab_deploy_only_on_default_branch(self):
        """Test GitLab deploy job only runs on default branch."""
        generator = CICDPipelineGenerator(
            default_branch="develop",
            include_deploy=True,
        )
        gitlab_ci_yaml = generator.generate_gitlab_ci({})
        config = yaml.safe_load(gitlab_ci_yaml)

        deploy_job = config["deploy:production"]
        assert "only" in deploy_job
        assert "develop" in deploy_job["only"]


class TestEmptyInputHandling:
    """Tests for handling empty or minimal input."""

    def test_generate_with_empty_tech_stack(self):
        """Test generation with empty tech stack dict."""
        generator = CICDPipelineGenerator()

        workflow_yaml = generator.generate_github_actions({})
        workflow = yaml.safe_load(workflow_yaml)

        assert workflow is not None
        assert "jobs" in workflow
        # Should default to node language
        assert len(workflow["jobs"]) > 0

    def test_generate_with_none_tech_stack(self):
        """Test generation with None tech stack."""
        generator = CICDPipelineGenerator()

        workflow_yaml = generator.generate_github_actions(None)
        workflow = yaml.safe_load(workflow_yaml)

        assert workflow is not None
        assert "jobs" in workflow

    def test_gitlab_with_empty_tech_stack(self):
        """Test GitLab CI generation with empty tech stack."""
        generator = CICDPipelineGenerator()

        gitlab_ci_yaml = generator.generate_gitlab_ci({})
        config = yaml.safe_load(gitlab_ci_yaml)

        assert config is not None
        assert "stages" in config
        assert "variables" in config

    def test_generic_with_empty_tech_stack(self):
        """Test generic pipeline generation with empty tech stack."""
        generator = CICDPipelineGenerator()

        pipeline_yaml = generator.generate_generic_ci({})
        pipeline = yaml.safe_load(pipeline_yaml)

        assert pipeline is not None
        assert "stages" in pipeline
        assert "jobs" in pipeline
