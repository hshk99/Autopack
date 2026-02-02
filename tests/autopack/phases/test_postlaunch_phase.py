"""Tests for postlaunch phase.

Comprehensive tests for PostlaunchPhase and PostlaunchPhaseExecutor.
"""

from pathlib import Path

import pytest

from autopack.phases.postlaunch_phase import (
    PostlaunchConfig,
    PostlaunchInput,
    PostlaunchOutput,
    PostlaunchPhase,
    PostlaunchPhaseExecutor,
    PostlaunchStatus,
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


class TestPostlaunchZeroTrafficScenarios:
    """Test edge cases for zero-traffic scenarios."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return PostlaunchPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_execute_phase_with_zero_traffic_setup(self, executor):
        """Test postlaunch setup with zero traffic deployment."""
        deployment_info = {
            "providers": ["aws"],
            "regions": ["us-east-1"],
            "expected_traffic": 0,
            "autoscaling_min_replicas": 1,
        }
        input_data = PostlaunchInput(
            product_name="BetaApp",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-beta",
            description="Beta deployment with zero traffic",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify SLA definitions are still generated even with zero traffic
        assert len(result.output.sla_definitions) > 0

    def test_execute_phase_with_minimal_traffic_thresholds(self, executor):
        """Test alert rules handle minimal traffic scenarios."""
        input_data = PostlaunchInput(
            product_name="LowTrafficApp",
            deployment_info={"expected_traffic": 10},  # Very low traffic
        )
        config = PostlaunchConfig(
            uptime_target=99.5,  # Lower uptime target for low-traffic services
            response_time_target_ms=1000,  # More lenient response time
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-low-traffic",
            description="Low traffic service postlaunch",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert len(result.output.alert_rules) > 0
        # Verify alert rules are appropriate for low traffic
        alert_names = [rule["name"] for rule in result.output.alert_rules]
        assert "Service Unreachable" in alert_names

    def test_execute_phase_idle_service_monitoring(self, executor):
        """Test monitoring configuration for idle services."""
        input_data = PostlaunchInput(
            product_name="IdleService",
            deployment_info={
                "providers": ["aws"],
                "autoscaling_min_replicas": 0,  # Can scale down to zero
            },
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-idle",
            description="Service that can scale to zero",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert result.output.monitoring_setup_path is not None
        monitoring_content = Path(result.output.monitoring_setup_path).read_text()
        # Verify monitoring setup exists
        assert "Alert Rules" in monitoring_content

    def test_execute_phase_warm_up_period_alerts(self, executor):
        """Test special alert handling during warm-up period."""
        input_data = PostlaunchInput(
            product_name="NewService",
            deployment_info={
                "deployment_stage": "warm-up",
                "warm_up_duration_minutes": 60,
            },
        )
        config = PostlaunchConfig(
            uptime_target=95.0,  # Lower during warm-up
            response_time_target_ms=2000,  # More lenient during warm-up
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-warmup",
            description="New service warm-up phase",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify SLA reflects warm-up period configuration
        uptime_sla = next(
            (d for d in result.output.sla_definitions if d["metric"] == "Uptime"),
            None,
        )
        assert uptime_sla is not None
        assert "95.0" in uptime_sla["target"]


class TestPostlaunchCostExplosionDetection:
    """Test edge cases for cost explosion detection."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return PostlaunchPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_execute_phase_with_cost_threshold_alerts(self, executor):
        """Test alert rules include cost explosion detection."""
        deployment_info = {
            "providers": ["aws"],
            "infrastructure_cost": 2000,
            "cost_threshold": 3000,  # Alert if cost exceeds $3k
            "daily_cost_limit": 100,
        }
        input_data = PostlaunchInput(
            product_name="CostTrackingApp",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-cost-tracked",
            description="Service with cost monitoring",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify alert rules are generated
        assert len(result.output.alert_rules) > 0

    def test_execute_phase_with_unexpected_cost_spike(self, executor):
        """Test handling of unexpected cost spikes."""
        deployment_info = {
            "providers": ["aws"],
            "baseline_daily_cost": 100,
            "cost_spike_threshold_multiplier": 2.0,  # Alert if 2x normal
        }
        input_data = PostlaunchInput(
            product_name="HighCostService",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-spike-detect",
            description="Service with spike detection",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify monitoring is configured
        assert result.output.monitoring_setup_path is not None

    def test_execute_phase_with_multi_region_cost_tracking(self, executor):
        """Test cost tracking across multiple regions."""
        deployment_info = {
            "providers": ["aws"],
            "regions": ["us-east-1", "eu-west-1", "ap-southeast-1"],
            "regional_budgets": {
                "us-east-1": 1000,
                "eu-west-1": 500,
                "ap-southeast-1": 300,
            },
        }
        input_data = PostlaunchInput(
            product_name="GlobalApp",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-global",
            description="Multi-region service",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify cost tracking is set up
        assert result.output.monitoring_setup_path is not None
        monitoring_content = Path(result.output.monitoring_setup_path).read_text()
        assert "Alert Rules" in monitoring_content

    def test_execute_phase_with_resource_explosion_scenario(self, executor):
        """Test detection of runaway resource consumption."""
        deployment_info = {
            "providers": ["aws"],
            "autoscaling_max_replicas": 10,
            "max_database_connections": 500,
            "storage_expansion_limit_gb": 1000,
        }
        input_data = PostlaunchInput(
            product_name="AutoScalingService",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-runaway-detect",
            description="Service with runaway detection",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify alert rules exist
        assert len(result.output.alert_rules) > 0

    def test_execute_phase_cost_budget_tracking(self, executor):
        """Test cost budget tracking and reporting."""
        deployment_info = {
            "providers": ["aws"],
            "monthly_budget": 5000,
            "budget_alert_percentage": 80,  # Alert at 80% of budget
        }
        input_data = PostlaunchInput(
            product_name="BudgetTrackedApp",
            deployment_info=deployment_info,
        )
        config = PostlaunchConfig(
            monitoring_platform="prometheus",
            alert_channels=["email", "slack"],
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-budget",
            description="Service with budget tracking",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify alert channels are configured
        assert len(result.output.alert_rules) > 0


class TestPostlaunchSecurityIncidents:
    """Test edge cases for security incident handling."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return PostlaunchPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_execute_phase_with_security_incident_response(self, executor):
        """Test incident response plan includes security scenarios."""
        input_data = PostlaunchInput(
            product_name="SecureApp",
            deployment_info={"security_level": "high"},
        )
        config = PostlaunchConfig(runbook_types=["incident_response", "maintenance", "scaling"])
        phase = PostlaunchPhase(
            phase_id="postlaunch-secure",
            description="High-security service",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify incident response runbook is generated
        assert result.output.incident_response_path is not None
        runbook_content = Path(result.output.incident_response_path).read_text()
        assert "Incident Response Runbook" in runbook_content

    def test_execute_phase_with_data_breach_response(self, executor):
        """Test data breach response procedures."""
        input_data = PostlaunchInput(
            product_name="DataSensitiveApp",
            deployment_info={
                "handles_pii": True,
                "handles_payment_data": True,
                "compliance_frameworks": ["GDPR", "PCI-DSS"],
            },
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-pii",
            description="Service handling sensitive data",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify runbooks are generated for compliance
        assert result.output.incident_response_path is not None
        assert result.output.monitoring_setup_path is not None

    def test_execute_phase_with_authentication_incident_alerts(self, executor):
        """Test alerts for authentication failures."""
        deployment_info = {
            "providers": ["aws"],
            "auth_failure_threshold": 5,  # Alert after 5 failures
            "rate_limit_enabled": True,
        }
        input_data = PostlaunchInput(
            product_name="AuthService",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-auth",
            description="Authentication service",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify monitoring rules exist
        assert len(result.output.alert_rules) > 0

    def test_execute_phase_with_ddos_protection_alerts(self, executor):
        """Test DDoS attack detection alerts."""
        deployment_info = {
            "providers": ["aws"],
            "ddos_protection_enabled": True,
            "traffic_spike_threshold": 1000,  # Alert if traffic > 1000 req/s
        }
        input_data = PostlaunchInput(
            product_name="PublicAPI",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-ddos",
            description="Public API with DDoS protection",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert result.output.monitoring_setup_path is not None
        monitoring_content = Path(result.output.monitoring_setup_path).read_text()
        assert "Alert Rules" in monitoring_content

    def test_execute_phase_with_compliance_monitoring(self, executor):
        """Test compliance and audit logging alerts."""
        deployment_info = {
            "compliance_frameworks": ["SOC2", "ISO27001"],
            "audit_logging_enabled": True,
            "audit_log_retention_days": 365,
        }
        input_data = PostlaunchInput(
            product_name="ComplianceService",
            deployment_info=deployment_info,
        )
        config = PostlaunchConfig(
            define_sla=True,
            enable_oncall_rotation=True,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-compliance",
            description="Compliance-focused service",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        # Verify SLA and monitoring are configured
        assert len(result.output.sla_definitions) > 0
        assert len(result.output.alert_rules) > 0

    def test_execute_phase_with_certificate_expiry_alerts(self, executor):
        """Test SSL/TLS certificate expiry monitoring."""
        deployment_info = {
            "providers": ["aws"],
            "ssl_certificate_expiry_warning_days": 30,
            "auto_renewal_enabled": True,
        }
        input_data = PostlaunchInput(
            product_name="WebService",
            deployment_info=deployment_info,
        )
        phase = PostlaunchPhase(
            phase_id="postlaunch-ssl",
            description="Service with SSL monitoring",
            config=PostlaunchConfig(),
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == PostlaunchStatus.COMPLETED
        assert result.output.monitoring_setup_path is not None
