"""Tests for monetize phase implementation."""

import pytest
from pathlib import Path

from autopack.phases.monetize_phase import (
    MonetizePhase,
    MonetizePhaseExecutor,
    MonetizeStatus,
    MonetizeConfig,
    MonetizeInput,
    MonetizeOutput,
    create_monetize_phase,
)


@pytest.fixture
def workspace_path(tmp_path):
    """Create temporary workspace."""
    return tmp_path / "workspace"


@pytest.fixture
def build_history_path(tmp_path):
    """Create temporary build history file."""
    history_file = tmp_path / "BUILD_HISTORY.md"
    history_file.write_text("# Build History\n\n", encoding="utf-8")
    return history_file


@pytest.fixture
def executor(workspace_path, build_history_path):
    """Create monetize phase executor."""
    workspace_path.mkdir(parents=True, exist_ok=True)
    return MonetizePhaseExecutor(
        workspace_path=workspace_path,
        build_history_path=build_history_path,
    )


@pytest.fixture
def sample_phase():
    """Create a sample monetize phase."""
    config = MonetizeConfig(
        revenue_model="freemium",
        enable_payment_integration=True,
        payment_provider="stripe",
    )
    input_data = MonetizeInput(
        product_name="Test Product",
        target_market="B2B SaaS",
        value_proposition="Fast and reliable service",
    )
    return MonetizePhase(
        phase_id="monetize-001",
        description="Test monetize phase",
        config=config,
        input_data=input_data,
    )


class TestMonetizePhase:
    """Test monetize phase data structures."""

    def test_phase_creation(self, sample_phase):
        """Test creating a monetize phase."""
        assert sample_phase.phase_id == "monetize-001"
        assert sample_phase.status == MonetizeStatus.PENDING
        assert sample_phase.output is None
        assert sample_phase.started_at is None
        assert sample_phase.completed_at is None

    def test_phase_to_dict(self, sample_phase):
        """Test phase serialization to dictionary."""
        phase_dict = sample_phase.to_dict()

        assert phase_dict["phase_id"] == "monetize-001"
        assert phase_dict["status"] == "pending"
        assert phase_dict["config"]["revenue_model"] == "freemium"
        assert phase_dict["input_data"]["product_name"] == "Test Product"
        assert phase_dict["output"] is None

    def test_phase_with_output(self, sample_phase):
        """Test phase serialization with output."""
        sample_phase.output = MonetizeOutput(
            strategy_path="/tmp/strategy.md",
            revenue_model="subscription",
            payment_provider="stripe",
            recommendations=["Test recommendation"],
        )

        phase_dict = sample_phase.to_dict()
        output = phase_dict["output"]

        assert output is not None
        assert output["revenue_model"] == "subscription"
        assert output["payment_provider"] == "stripe"
        assert len(output["recommendations"]) == 1


class TestMonetizePhaseExecutor:
    """Test monetize phase executor."""

    def test_execute_success(self, executor, sample_phase):
        """Test successful phase execution."""
        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.error is None
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.output is not None

    def test_execute_generates_strategy(self, executor, workspace_path, sample_phase):
        """Test that execution generates strategy file."""
        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.output.strategy_path is not None

        strategy_file = Path(result.output.strategy_path)
        assert strategy_file.exists()
        assert strategy_file.read_text().find("Test Product") >= 0
        assert strategy_file.read_text().find("Freemium") >= 0

    def test_execute_no_input(self, executor):
        """Test execution fails without input data."""
        phase = MonetizePhase(
            phase_id="test-001",
            description="Test phase",
            config=MonetizeConfig(),
            input_data=None,
        )

        result = executor.execute(phase)

        assert result.status == MonetizeStatus.FAILED
        assert "No input data" in result.error

    def test_execute_with_freemium_model(self, executor, sample_phase):
        """Test execution with freemium revenue model."""
        sample_phase.config.revenue_model = "freemium"

        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.output.revenue_model == "freemium"
        assert len(result.output.recommendations) > 0

        # Check that freemium recommendations are included
        rec_text = "\n".join(result.output.recommendations)
        assert "feature" in rec_text.lower() or "free" in rec_text.lower()

    def test_execute_with_subscription_model(self, executor, sample_phase):
        """Test execution with subscription revenue model."""
        sample_phase.config.revenue_model = "subscription"

        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.output.revenue_model == "subscription"

    def test_execute_with_pay_per_use_model(self, executor, sample_phase):
        """Test execution with pay-per-use revenue model."""
        sample_phase.config.revenue_model = "pay_per_use"

        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.output.revenue_model == "pay_per_use"

    def test_execute_saves_to_history(self, executor, build_history_path, sample_phase):
        """Test that execution saves to build history."""
        initial_size = build_history_path.stat().st_size

        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED

        # Build history should have grown
        final_size = build_history_path.stat().st_size
        assert final_size > initial_size

        # Check content
        history_content = build_history_path.read_text()
        assert "Monetize Phase" in history_content
        assert "monetize-001" in history_content
        assert "completed" in history_content.lower()

    def test_execute_payment_integration(self, executor, sample_phase):
        """Test execution with payment integration enabled."""
        sample_phase.config.enable_payment_integration = True
        sample_phase.config.payment_provider = "stripe"

        result = executor.execute(sample_phase)

        assert result.status == MonetizeStatus.COMPLETED
        assert result.output.payment_provider == "stripe"

        # Check strategy file mentions payment provider
        strategy_content = Path(result.output.strategy_path).read_text()
        assert "stripe" in strategy_content.lower()


class TestCreateMonetizePhase:
    """Test factory function for creating monetize phases."""

    def test_create_phase_basic(self):
        """Test creating a phase with factory function."""
        phase = create_monetize_phase(
            phase_id="test-monetize-001",
            product_name="Test Product",
            target_market="Enterprise",
            value_proposition="Quick deployment",
        )

        assert phase.phase_id == "test-monetize-001"
        assert phase.input_data.product_name == "Test Product"
        assert phase.input_data.target_market == "Enterprise"
        assert phase.status == MonetizeStatus.PENDING

    def test_create_phase_with_config(self):
        """Test creating a phase with custom configuration."""
        phase = create_monetize_phase(
            phase_id="test-monetize-002",
            product_name="Premium Product",
            target_market="SMB",
            value_proposition="Affordable solution",
            revenue_model="subscription",
            payment_provider="paypal",
        )

        assert phase.config.revenue_model == "subscription"
        assert phase.config.payment_provider == "paypal"
        assert phase.input_data.product_name == "Premium Product"


class TestMonetizeConfig:
    """Test monetize configuration."""

    def test_default_config(self):
        """Test default configuration."""
        config = MonetizeConfig()

        assert config.revenue_model == "freemium"
        assert config.enable_payment_integration is True
        assert config.payment_provider == "stripe"
        assert config.save_to_history is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = MonetizeConfig(
            revenue_model="subscription",
            enable_payment_integration=False,
            payment_provider="paypal",
        )

        assert config.revenue_model == "subscription"
        assert config.enable_payment_integration is False
        assert config.payment_provider == "paypal"


class TestMonetizeOutput:
    """Test monetize output."""

    def test_empty_output(self):
        """Test creating empty output."""
        output = MonetizeOutput()

        assert output.strategy_path is None
        assert output.revenue_model == "freemium"
        assert output.payment_provider == "stripe"
        assert len(output.recommendations) == 0
        assert len(output.warnings) == 0

    def test_populated_output(self):
        """Test creating populated output."""
        output = MonetizeOutput(
            strategy_path="/tmp/strategy.md",
            revenue_model="subscription",
            payment_provider="paypal",
            recommendations=["Rec 1", "Rec 2"],
            warnings=["Warning 1"],
        )

        assert output.strategy_path == "/tmp/strategy.md"
        assert output.revenue_model == "subscription"
        assert output.payment_provider == "paypal"
        assert len(output.recommendations) == 2
        assert len(output.warnings) == 1
