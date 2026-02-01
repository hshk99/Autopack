"""Tests for monetization phase.

Comprehensive tests for MonetizationPhase and MonetizationPhaseExecutor.
"""

import pytest
from datetime import datetime
from pathlib import Path
from autopack.phases.monetization_phase import (
    MonetizationStatus,
    MonetizationConfig,
    MonetizationInput,
    MonetizationOutput,
    MonetizationPhase,
    MonetizationPhaseExecutor,
    create_monetization_phase,
)


class TestMonetizationConfig:
    """Test MonetizationConfig dataclass."""

    def test_monetization_config_defaults(self):
        """Test MonetizationConfig with defaults."""
        config = MonetizationConfig()

        assert "freemium" in config.revenue_models
        assert "subscription" in config.revenue_models
        assert config.payment_providers == ["stripe"]
        assert config.pricing_strategy == "tiered"
        assert config.enable_trial_period is True
        assert config.gdpr_compliance is True

    def test_monetization_config_custom(self):
        """Test MonetizationConfig with custom values."""
        config = MonetizationConfig(
            revenue_models=["subscription"],
            payment_providers=["stripe", "paypal"],
            pricing_strategy="usage_based",
            enable_trial_period=False,
        )

        assert config.revenue_models == ["subscription"]
        assert len(config.payment_providers) == 2
        assert config.pricing_strategy == "usage_based"


class TestMonetizationInput:
    """Test MonetizationInput dataclass."""

    def test_monetization_input_basic(self):
        """Test basic MonetizationInput."""
        input_data = MonetizationInput(
            product_name="SaaS App",
            target_audience="Small businesses",
            value_proposition="Easy automation",
        )

        assert input_data.product_name == "SaaS App"
        assert input_data.target_audience == "Small businesses"

    def test_monetization_input_with_deployment_info(self):
        """Test MonetizationInput with deployment info."""
        deployment_info = {
            "infrastructure_cost": 2000,
            "monthly_cost": 2000,
            "providers": ["aws"],
        }
        input_data = MonetizationInput(
            product_name="App",
            target_audience="Enterprises",
            value_proposition="Premium features",
            deployment_info=deployment_info,
        )

        assert input_data.deployment_info["infrastructure_cost"] == 2000


class TestMonetizationOutput:
    """Test MonetizationOutput dataclass."""

    def test_monetization_output_defaults(self):
        """Test MonetizationOutput defaults."""
        output = MonetizationOutput()

        assert output.monetization_guide_path is None
        assert output.recommended_tiers == []
        assert output.compliance_checklist == []


class TestMonetizationPhase:
    """Test MonetizationPhase dataclass."""

    def test_monetization_phase_creation(self):
        """Test creating monetization phase."""
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Create monetization strategy",
            config=MonetizationConfig(),
        )

        assert phase.phase_id == "monetize-001"
        assert phase.status == MonetizationStatus.PENDING

    def test_monetization_phase_to_dict(self):
        """Test serialization."""
        input_data = MonetizationInput(
            product_name="App",
            target_audience="SMBs",
            value_proposition="Value",
        )
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=MonetizationConfig(),
            input_data=input_data,
        )

        phase_dict = phase.to_dict()

        assert phase_dict["phase_id"] == "monetize-001"
        assert phase_dict["input_data"]["product_name"] == "App"


class TestMonetizationPhaseExecutor:
    """Test MonetizationPhaseExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return MonetizationPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_executor_initialization(self, executor, tmp_path):
        """Test executor initialization."""
        assert executor.workspace_path == tmp_path

    def test_execute_phase_no_input(self, executor):
        """Test executing phase with no input."""
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=MonetizationConfig(),
        )

        result = executor.execute(phase)

        assert result.status == MonetizationStatus.FAILED
        assert "No input data" in result.error

    def test_execute_phase_success(self, executor):
        """Test successful execution."""
        input_data = MonetizationInput(
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Easy automation tool",
        )
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=MonetizationConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == MonetizationStatus.COMPLETED
        assert result.output is not None

    def test_execute_phase_generates_pricing_model(self, executor):
        """Test pricing model generation."""
        input_data = MonetizationInput(
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Automation",
        )
        config = MonetizationConfig(pricing_strategy="tiered")
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.pricing_model_path is not None
        assert Path(result.output.pricing_model_path).exists()
        assert len(result.output.recommended_tiers) > 0

    def test_execute_phase_generates_integration_guide(self, executor):
        """Test payment integration guide generation."""
        input_data = MonetizationInput(
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Automation",
        )
        config = MonetizationConfig(payment_providers=["stripe"])
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output.integration_guide_path is not None
        assert Path(result.output.integration_guide_path).exists()
        assert "stripe" in result.output.payment_providers_configured

    def test_execute_phase_generates_compliance_checklist(self, executor):
        """Test compliance checklist generation."""
        input_data = MonetizationInput(
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Automation",
        )
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=MonetizationConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert len(result.output.compliance_checklist) > 0
        assert any("GDPR" in item or "ToS" in item for item in result.output.compliance_checklist)

    def test_execute_phase_saves_to_history(self, executor, tmp_path):
        """Test history saving."""
        input_data = MonetizationInput(
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Automation",
        )
        config = MonetizationConfig(save_to_history=True)
        phase = MonetizationPhase(
            phase_id="monetize-001",
            description="Monetization",
            config=config,
            input_data=input_data,
        )

        executor = MonetizationPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )
        result = executor.execute(phase)

        history_file = tmp_path / "BUILD_HISTORY.md"
        assert history_file.exists()
        content = history_file.read_text()
        assert "Monetization Phase" in content


class TestMonetizationPhaseFactory:
    """Test factory function."""

    def test_create_monetization_phase(self):
        """Test factory function."""
        phase = create_monetization_phase(
            phase_id="monetize-prod",
            product_name="MyApp",
            target_audience="SMBs",
            value_proposition="Easy automation",
        )

        assert phase.phase_id == "monetize-prod"
        assert phase.input_data.product_name == "MyApp"


class TestMonetizationPhaseIntegration:
    """Integration tests."""

    def test_full_monetization_workflow(self, tmp_path):
        """Test complete workflow."""
        phase = create_monetization_phase(
            phase_id="monetize-prod",
            product_name="TestApp",
            target_audience="SMBs",
            value_proposition="Great value",
            revenue_models=["freemium", "subscription"],
            payment_providers=["stripe"],
            pricing_strategy="tiered",
        )

        executor = MonetizationPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        assert result.status == MonetizationStatus.COMPLETED
        assert result.output.pricing_model_path is not None
        assert result.output.integration_guide_path is not None
        assert len(result.output.recommended_tiers) >= 2
        assert len(result.output.compliance_checklist) > 0
