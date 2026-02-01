"""Tests for deployment phase.

Comprehensive tests for DeployPhase, DeployConfig, DeployInput, and DeployPhaseExecutor.
"""

import pytest
from datetime import datetime
from pathlib import Path
from autopack.phases.deploy_phase import (
    DeployStatus,
    DeployConfig,
    DeployInput,
    DeployOutput,
    DeployPhase,
    DeployPhaseExecutor,
    create_deploy_phase,
)


class TestDeployConfig:
    """Test DeployConfig dataclass."""

    def test_deploy_config_defaults(self):
        """Test DeployConfig with default values."""
        config = DeployConfig()

        assert config.providers == ["docker"]
        assert config.guidance_types == ["containerization"]
        assert config.enable_cicd is True
        assert config.cicd_platform == "github_actions"
        assert config.enable_monitoring is True
        assert config.save_to_history is True
        assert config.max_duration_minutes is None

    def test_deploy_config_custom_values(self):
        """Test DeployConfig with custom values."""
        config = DeployConfig(
            providers=["docker", "aws", "gcp"],
            guidance_types=["containerization", "ci_cd"],
            cicd_platform="gitlab_ci",
            enable_monitoring=False,
        )

        assert config.providers == ["docker", "aws", "gcp"]
        assert config.guidance_types == ["containerization", "ci_cd"]
        assert config.cicd_platform == "gitlab_ci"
        assert config.enable_monitoring is False


class TestDeployInput:
    """Test DeployInput dataclass."""

    def test_deploy_input_basic(self):
        """Test basic DeployInput creation."""
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python", "framework": "fastapi"},
        )

        assert input_data.project_name == "MyApp"
        assert input_data.tech_stack["language"] == "python"
        assert input_data.project_requirements is None

    def test_deploy_input_with_requirements(self):
        """Test DeployInput with project requirements."""
        requirements = {
            "min_availability": 99.9,
            "max_latency_ms": 500,
            "compliance": ["GDPR"],
        }
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
            project_requirements=requirements,
        )

        assert input_data.project_requirements["compliance"] == ["GDPR"]


class TestDeployOutput:
    """Test DeployOutput dataclass."""

    def test_deploy_output_defaults(self):
        """Test DeployOutput with default values."""
        output = DeployOutput()

        assert output.deployment_guide_path is None
        assert output.docker_config_path is None
        assert output.cicd_config_path is None
        assert output.providers_configured == []
        assert output.artifacts_generated == []
        assert output.warnings == []

    def test_deploy_output_with_data(self):
        """Test DeployOutput with data."""
        output = DeployOutput(
            deployment_guide_path="/path/to/guide.md",
            providers_configured=["docker", "aws"],
            artifacts_generated=["/path/to/Dockerfile", "/path/to/.github/workflows/deploy.yml"],
            warnings=["No Kubernetes config provided"],
        )

        assert len(output.artifacts_generated) == 2
        assert "docker" in output.providers_configured
        assert len(output.warnings) == 1


class TestDeployPhase:
    """Test DeployPhase dataclass."""

    def test_deploy_phase_creation(self):
        """Test creating a deployment phase."""
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy to production",
            config=DeployConfig(),
        )

        assert phase.phase_id == "deploy-001"
        assert phase.status == DeployStatus.PENDING
        assert phase.output is None
        assert phase.started_at is None

    def test_deploy_phase_to_dict(self):
        """Test DeployPhase serialization."""
        config = DeployConfig(providers=["docker", "aws"])
        input_data = DeployInput(
            project_name="TestApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy to production",
            config=config,
            input_data=input_data,
            status=DeployStatus.COMPLETED,
        )

        phase_dict = phase.to_dict()

        assert phase_dict["phase_id"] == "deploy-001"
        assert phase_dict["status"] == "completed"
        assert phase_dict["config"]["providers"] == ["docker", "aws"]
        assert phase_dict["input_data"]["project_name"] == "TestApp"
        assert phase_dict["error"] is None

    def test_deploy_phase_with_error(self):
        """Test DeployPhase with error state."""
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy to production",
            config=DeployConfig(),
            status=DeployStatus.FAILED,
            error="Database connection failed",
        )

        phase_dict = phase.to_dict()
        assert phase_dict["status"] == "failed"
        assert "connection failed" in phase_dict["error"]


class TestDeployPhaseExecutor:
    """Test DeployPhaseExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return DeployPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_executor_initialization(self, executor, tmp_path):
        """Test executor initialization."""
        assert executor.workspace_path == tmp_path
        assert executor.build_history_path is not None

    def test_execute_phase_no_input(self, executor):
        """Test executing phase with no input data."""
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=DeployConfig(),
        )

        result = executor.execute(phase)

        assert result.status == DeployStatus.FAILED
        assert "No input data" in result.error

    def test_execute_phase_success(self, executor):
        """Test successful phase execution."""
        config = DeployConfig(providers=["docker"])
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python", "framework": "fastapi"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy MyApp",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DeployStatus.COMPLETED
        assert result.output is not None
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.error is None

    def test_execute_phase_generates_docker_config(self, executor):
        """Test that Docker config is generated."""
        config = DeployConfig(providers=["docker"])
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.docker_config_path is not None

        # Verify Docker file was created
        docker_path = Path(result.output.docker_config_path)
        assert docker_path.exists()
        content = docker_path.read_text()
        assert "Dockerfile" in content or "FROM" in content

    def test_execute_phase_generates_cicd_config(self, executor):
        """Test that CI/CD config is generated."""
        config = DeployConfig(
            providers=["docker"],
            enable_cicd=True,
            cicd_platform="github_actions",
        )
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.cicd_config_path is not None

    def test_execute_phase_generates_monitoring_config(self, executor):
        """Test that monitoring config is generated."""
        config = DeployConfig(
            providers=["docker"],
            enable_monitoring=True,
        )
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.monitoring_config_path is not None

    def test_execute_phase_saves_to_history(self, executor, tmp_path):
        """Test that phase is saved to BUILD_HISTORY."""
        config = DeployConfig(save_to_history=True)
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy MyApp",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        history_file = tmp_path / "BUILD_HISTORY.md"
        assert history_file.exists()
        content = history_file.read_text()
        assert "Deploy Phase" in content
        assert "deploy-001" in content
        assert "completed" in content

    def test_execute_phase_invalid_provider(self, executor):
        """Test execution with invalid provider."""
        config = DeployConfig(providers=["invalid_provider"])
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DeployStatus.COMPLETED
        assert len(result.output.warnings) > 0

    def test_execute_phase_multiple_providers(self, executor):
        """Test execution with multiple providers."""
        config = DeployConfig(
            providers=["docker", "aws"],
            enable_cicd=True,
        )
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DeployStatus.COMPLETED
        assert "docker" in result.output.providers_configured
        assert "aws" in result.output.providers_configured

    def test_execute_phase_artifacts_created(self, executor):
        """Test that artifacts are properly listed."""
        config = DeployConfig(providers=["docker"])
        input_data = DeployInput(
            project_name="MyApp",
            tech_stack={"language": "python"},
        )
        phase = DeployPhase(
            phase_id="deploy-001",
            description="Deploy",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert len(result.output.artifacts_generated) > 0
        for artifact in result.output.artifacts_generated:
            assert Path(artifact).exists()


class TestDeployPhaseFactory:
    """Test factory function for creating deploy phases."""

    def test_create_deploy_phase(self):
        """Test factory function."""
        phase = create_deploy_phase(
            phase_id="deploy-prod",
            project_name="MyApp",
            tech_stack={"language": "python", "framework": "fastapi"},
        )

        assert phase.phase_id == "deploy-prod"
        assert phase.input_data.project_name == "MyApp"
        assert phase.status == DeployStatus.PENDING

    def test_create_deploy_phase_with_options(self):
        """Test factory function with custom options."""
        phase = create_deploy_phase(
            phase_id="deploy-prod",
            project_name="MyApp",
            tech_stack={"language": "python"},
            providers=["aws", "gcp"],
            cicd_platform="gitlab_ci",
        )

        assert phase.config.providers == ["aws", "gcp"]
        assert phase.config.cicd_platform == "gitlab_ci"


class TestDeployPhaseIntegration:
    """Integration tests for deploy phase."""

    def test_full_deploy_workflow(self, tmp_path):
        """Test complete deploy workflow."""
        # Create phase
        phase = create_deploy_phase(
            phase_id="deploy-prod",
            project_name="TestApp",
            tech_stack={"language": "python", "framework": "fastapi"},
            providers=["docker"],
            enable_cicd=True,
            enable_monitoring=True,
        )

        # Execute phase
        executor = DeployPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        # Verify results
        assert result.status == DeployStatus.COMPLETED
        assert result.output is not None
        assert result.output.docker_config_path is not None
        assert result.output.cicd_config_path is not None
        assert result.output.monitoring_config_path is not None
        assert len(result.output.artifacts_generated) >= 3

    def test_phase_serialization_roundtrip(self, tmp_path):
        """Test phase serialization and deserialization."""
        phase = create_deploy_phase(
            phase_id="deploy-001",
            project_name="MyApp",
            tech_stack={"language": "python"},
        )

        # Execute to populate output
        executor = DeployPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        # Serialize
        phase_dict = result.to_dict()

        # Verify all fields are present
        assert "phase_id" in phase_dict
        assert "status" in phase_dict
        assert "config" in phase_dict
        assert "input_data" in phase_dict
        assert "output" in phase_dict
        assert "started_at" in phase_dict
        assert "completed_at" in phase_dict
