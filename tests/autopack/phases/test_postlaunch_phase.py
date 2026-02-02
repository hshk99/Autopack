"""Tests for postlaunch phase.

Comprehensive tests for PostlaunchPhase and PostlaunchPhaseExecutor.
"""

import pytest
from pathlib import Path
from autopack.phases.postlaunch_phase import (
    PostlaunchStatus,
    PostlaunchConfig,
    PostlaunchInput,
    PostlaunchOutput,
    PostlaunchPhase,
    PostlaunchPhaseExecutor,
    create_postlaunch_phase,
)


class TestPostlaunchConfig:
    """Test PostlaunchConfig dataclass."""

    def test_postlaunch_config_defaults(self):
        """Test PostlaunchConfig defaults."""
        config = PostlaunchConfig()

        assert "incident_response" in config.runbook_types
        assert config.define_sla is True
        assert config.uptime_target == 99.9
        assert config.response_time_target_ms == 500
        assert config.enable_oncall_rotation is True

    def test_postlaunch_config_custom(self):
        """Test PostlaunchConfig custom values."""
        config = PostlaunchConfig(
            runbook_types=["incident_response"],
            uptime_target=99.99,
            response_time_target_ms=200,
        )

        assert len(config.runbook_types) == 1
        assert config.uptime_target == 99.99
        assert config.response_time_target_ms == 200


class TestPostlaunchInput:
    """Test PostlaunchInput dataclass."""

    def test_postlaunch_input_basic(self):
        """Test basic PostlaunchInput."""
        input_data = PostlaunchInput(
            product_name="MyApp",
        )

        assert input_data.product_name == "MyApp"
        assert input_data.deployment_info is None

    def test_postlaunch_input_with_dependencies(self):
        """Test PostlaunchInput with deployment and monetization info."""
        deployment_info = {"providers": ["aws"], "regions": ["us-east-1"]}
        monetization_info = {"pricing_model": "subscription", "tiers": 3}
        input_data = PostlaunchInput(
            product_name="MyApp",
            deployment_info=deployment_info,
            monetization_info=monetization_info,
        )

        assert input_data.deployment_info["providers"] == ["aws"]
        assert input_data.monetization_info["tiers"] == 3


class TestPostlaunchOutput:
    """Test PostlaunchOutput dataclass."""

    def test_postlaunch_output_defaults(self):
        """Test PostlaunchOutput defaults."""
        output = PostlaunchOutput()

        assert output.runbook_dir_path is None
        assert output.sla_definitions == []
        assert output.alert_rules == []


class TestPostlaunchPhase:
    """Test PostlaunchPhase dataclass."""

    def test_postlaunch_phase_creation(self):
        """Test creating postlaunch phase."""
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch operations",
            config=PostlaunchConfig(),
        )

        assert phase.phase_id == "postlaunch-001"
        assert phase.status == PostlaunchStatus.PENDING

    def test_postlaunch_phase_to_dict(self):
        """Test serialization."""
        input_data = PostlaunchInput(product_name="MyApp")
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        phase_dict = phase.to_dict()

        assert phase_dict["phase_id"] == "postlaunch-001"
        assert phase_dict["input_data"]["product_name"] == "MyApp"


class TestPostlaunchPhaseExecutor:
    """Test PostlaunchPhaseExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return PostlaunchPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_executor_initialization(self, executor, tmp_path):
        """Test executor initialization."""
        assert executor.workspace_path == tmp_path

    def test_execute_phase_no_input(self, executor):
        """Test executing phase with no input."""
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=PostlaunchConfig(),
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.FAILED
        assert "No input data" in result.error

    def test_execute_phase_success(self, executor):
        """Test successful execution."""
        input_data = PostlaunchInput(product_name="MyApp")
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert result.output is not None
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_execute_phase_generates_incident_runbook(self, executor):
        """Test incident response runbook generation."""
        input_data = PostlaunchInput(product_name="MyApp")
        config = PostlaunchConfig(runbook_types=["incident_response"])
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.incident_response_path is not None
        assert Path(result.output.incident_response_path).exists()

    def test_execute_phase_generates_sla(self, executor):
        """Test SLA document generation."""
        input_data = PostlaunchInput(product_name="MyApp")
        config = PostlaunchConfig(
            define_sla=True,
            uptime_target=99.9,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.sla_document_path is not None
        assert Path(result.output.sla_document_path).exists()
        assert len(result.output.sla_definitions) > 0

    def test_execute_phase_sla_definitions_correct(self, executor):
        """Test SLA definitions match config."""
        input_data = PostlaunchInput(product_name="MyApp")
        config = PostlaunchConfig(
            uptime_target=99.99,
            response_time_target_ms=300,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        uptime_def = next(
            (d for d in result.output.sla_definitions if d["metric"] == "Uptime"), None
        )
        assert uptime_def is not None
        assert "99.99" in uptime_def["target"]

    def test_execute_phase_generates_alert_rules(self, executor):
        """Test alert rules generation."""
        input_data = PostlaunchInput(product_name="MyApp")
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert len(result.output.alert_rules) > 0

    def test_execute_phase_generates_monitoring_setup(self, executor):
        """Test monitoring setup generation."""
        input_data = PostlaunchInput(product_name="MyApp")
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.monitoring_setup_path is not None
        assert Path(result.output.monitoring_setup_path).exists()

    def test_execute_phase_generates_all_runbooks(self, executor):
        """Test all runbook types generated."""
        input_data = PostlaunchInput(product_name="MyApp")
        config = PostlaunchConfig(runbook_types=["incident_response", "maintenance", "scaling"])
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.runbook_dir_path is not None
        runbook_dir = Path(result.output.runbook_dir_path)
        assert runbook_dir.exists()

    def test_execute_phase_saves_to_history(self, executor, tmp_path):
        """Test history saving."""
        input_data = PostlaunchInput(product_name="MyApp")
        config = PostlaunchConfig(save_to_history=True)
        phase = PostlaunchPhase(
            phase_id="postlaunch-001",
            description="Post-launch",
            config=config,
            input_data=input_data,
        )

        executor_with_history = PostlaunchPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )
        executor_with_history.execute(phase)

        history_file = tmp_path / "BUILD_HISTORY.md"
        assert history_file.exists()
        content = history_file.read_text()
        assert "Postlaunch Phase" in content
        assert "postlaunch-001" in content


class TestPostlaunchPhaseFactory:
    """Test factory function."""

    def test_create_postlaunch_phase(self):
        """Test factory function."""
        phase = create_postlaunch_phase(
            phase_id="postlaunch-prod",
            product_name="MyApp",
        )

        assert phase.phase_id == "postlaunch-prod"
        assert phase.input_data.product_name == "MyApp"
        assert phase.status == PostlaunchStatus.PENDING

    def test_create_postlaunch_phase_with_config(self):
        """Test factory with custom config."""
        phase = create_postlaunch_phase(
            phase_id="postlaunch-prod",
            product_name="MyApp",
            uptime_target=99.99,
            response_time_target_ms=200,
        )

        assert phase.config.uptime_target == 99.99
        assert phase.config.response_time_target_ms == 200


class TestPostlaunchPhaseIntegration:
    """Integration tests."""

    def test_full_postlaunch_workflow(self, tmp_path):
        """Test complete workflow."""
        phase = create_postlaunch_phase(
            phase_id="postlaunch-prod",
            product_name="TestApp",
            uptime_target=99.9,
            response_time_target_ms=500,
        )

        executor = PostlaunchPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert result.output.incident_response_path is not None
        assert result.output.sla_document_path is not None
        assert result.output.monitoring_setup_path is not None
        assert len(result.output.sla_definitions) >= 3
        assert len(result.output.alert_rules) > 0

    def test_postlaunch_with_dependencies(self, tmp_path):
        """Test postlaunch with deployment and monetization info."""
        deployment_info = {
            "providers": ["aws"],
            "regions": ["us-east-1"],
            "infrastructure_cost": 2000,
        }
        monetization_info = {
            "pricing_model": "subscription",
            "tiers": ["starter", "pro", "enterprise"],
        }
        input_data = PostlaunchInput(
            product_name="TestApp",
            deployment_info=deployment_info,
            monetization_info=monetization_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-prod",
            description="Post-launch operations",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        executor = PostlaunchPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify it can access dependency info
        assert result.input_data.deployment_info is not None
        assert result.input_data.monetization_info is not None
