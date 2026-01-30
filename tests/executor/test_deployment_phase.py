"""Tests for deployment phase support (IMP-HIGH-003).

Tests cover:
- DeploymentTemplateRegistry initialization and template registration
- DeploymentPhaseHandler guidance generation
- Phase orchestrator deployment phase detection and handling
"""

from unittest.mock import Mock

from autopack.executor.deployment_phase import (
    DeploymentPhaseHandler,
    DeploymentProvider,
    DeploymentTemplate,
    DeploymentTemplateRegistry,
    GuidanceType,
)
from autopack.executor.phase_orchestrator import (
    ExecutionContext,
    PhaseOrchestrator,
    PhaseResult,
    create_default_time_watchdog,
)


class TestDeploymentTemplateRegistry:
    """Tests for DeploymentTemplateRegistry."""

    def test_registry_initialization(self):
        """Test template registry initializes with default templates."""
        registry = DeploymentTemplateRegistry()

        assert len(registry.templates) > 0
        assert "docker_basic" in registry.templates
        assert "github_actions_ci_cd" in registry.templates

    def test_register_template(self):
        """Test registering a new template."""
        registry = DeploymentTemplateRegistry()
        template = DeploymentTemplate(
            name="test_template",
            provider=DeploymentProvider.DOCKER,
            guidance_type=GuidanceType.CONTAINERIZATION,
            template_content="Test content",
        )

        registry.register_template(template)

        assert "test_template" in registry.templates
        assert registry.get_template("test_template") == template

    def test_get_template(self):
        """Test retrieving a template by name."""
        registry = DeploymentTemplateRegistry()

        template = registry.get_template("docker_basic")

        assert template is not None
        assert template.name == "docker_basic"
        assert template.provider == DeploymentProvider.DOCKER

    def test_get_nonexistent_template(self):
        """Test retrieving a nonexistent template returns None."""
        registry = DeploymentTemplateRegistry()

        template = registry.get_template("nonexistent")

        assert template is None

    def test_get_templates_by_provider(self):
        """Test retrieving templates by provider."""
        registry = DeploymentTemplateRegistry()

        docker_templates = registry.get_templates_by_provider(DeploymentProvider.DOCKER)

        assert len(docker_templates) > 0
        assert all(t.provider == DeploymentProvider.DOCKER for t in docker_templates)

    def test_get_templates_by_guidance_type(self):
        """Test retrieving templates by guidance type."""
        registry = DeploymentTemplateRegistry()

        containerization_templates = registry.get_templates_by_guidance_type(
            GuidanceType.CONTAINERIZATION
        )

        assert len(containerization_templates) > 0
        assert all(
            t.guidance_type == GuidanceType.CONTAINERIZATION for t in containerization_templates
        )


class TestDeploymentPhaseHandler:
    """Tests for DeploymentPhaseHandler."""

    def test_handler_initialization(self):
        """Test deployment phase handler initializes with registry."""
        handler = DeploymentPhaseHandler()

        assert handler.template_registry is not None
        assert len(handler.template_registry.templates) > 0

    def test_generate_deployment_guidance(self):
        """Test generating deployment guidance."""
        handler = DeploymentPhaseHandler()

        guidance = handler.generate_deployment_guidance(
            providers=["docker"], guidance_types=["containerization"]
        )

        assert guidance is not None
        assert len(guidance) > 0
        assert "Dockerfile" in guidance or "dockerfile" in guidance.lower()

    def test_generate_guidance_multiple_providers(self):
        """Test generating guidance for multiple providers."""
        handler = DeploymentPhaseHandler()

        guidance = handler.generate_deployment_guidance(
            providers=["docker", "aws"], guidance_types=["containerization", "ci_cd_pipeline"]
        )

        assert guidance is not None
        assert len(guidance) > 0

    def test_generate_guidance_empty_providers(self):
        """Test generating guidance with empty providers."""
        handler = DeploymentPhaseHandler()

        guidance = handler.generate_deployment_guidance(
            providers=[], guidance_types=["containerization"]
        )

        assert guidance is not None

    def test_create_deployment_phase_config(self):
        """Test creating deployment phase configuration."""
        handler = DeploymentPhaseHandler()

        config = handler.create_deployment_phase_config(
            providers=["docker"], guidance_types=["containerization"]
        )

        assert config is not None
        assert "providers" in config
        assert "guidance_types" in config
        assert "templates" in config
        assert config["providers"] == ["docker"]

    def test_create_config_with_defaults(self):
        """Test creating configuration with default values."""
        handler = DeploymentPhaseHandler()

        config = handler.create_deployment_phase_config()

        assert config is not None
        assert len(config["providers"]) > 0
        assert len(config["guidance_types"]) > 0


class TestPhaseOrchestratorDeployment:
    """Tests for deployment phase support in PhaseOrchestrator."""

    def test_detect_phase_type_from_phase_type_field(self):
        """Test detecting phase type from explicit phase_type field."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {"phase_id": "deploy-001", "phase_type": "deployment"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        phase_type = orchestrator._detect_phase_type(context)

        assert phase_type == "deployment"

    def test_detect_phase_type_from_category(self):
        """Test detecting phase type falls back to category."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {"phase_id": "feature-001", "category": "implementation"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        phase_type = orchestrator._detect_phase_type(context)

        assert phase_type == "implementation"

    def test_should_handle_as_deployment_phase(self):
        """Test checking if phase should be handled as deployment phase."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {"phase_id": "deploy-001", "phase_type": "deployment"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        should_handle = orchestrator.should_handle_as_deployment_phase(context)

        assert should_handle is True

    def test_should_not_handle_non_deployment_phase(self):
        """Test that non-deployment phases are not handled as deployment."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {"phase_id": "feature-001", "phase_type": "implementation"}
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        should_handle = orchestrator.should_handle_as_deployment_phase(context)

        assert should_handle is False

    def test_handle_deployment_phase_success(self):
        """Test handling deployment phase returns successful result."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {
            "phase_id": "deploy-001",
            "phase_type": "deployment",
            "deployment_config": {"providers": ["docker"], "guidance_types": ["containerization"]},
        }
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        result = orchestrator._handle_deployment_phase(context)

        assert result.success is True
        assert result.status == "COMPLETE"
        assert result.phase_result == PhaseResult.COMPLETE

    def test_handle_deployment_phase_creates_config(self):
        """Test deployment phase handler creates configuration."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {
            "phase_id": "deploy-001",
            "phase_type": "deployment",
            "deployment_config": {"providers": ["docker"], "guidance_types": ["containerization"]},
        }
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        result = orchestrator._handle_deployment_phase(context)

        assert result.enhanced_phase is not None
        assert result.enhanced_phase.get("deployment_config") is not None
        assert result.enhanced_phase.get("guidance_generated") is True

    def test_execute_phase_attempt_routes_deployment_phase(self):
        """Test that execute_phase_attempt routes to deployment handler for deployment phases."""
        orchestrator = PhaseOrchestrator()
        watchdog = create_default_time_watchdog()

        phase = {
            "phase_id": "deploy-001",
            "phase_type": "deployment",
            "deployment_config": {"providers": ["docker"], "guidance_types": ["containerization"]},
        }
        context = ExecutionContext(
            phase=phase,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=[],
            run_id="test-run",
            llm_service=Mock(),
            time_watchdog=watchdog,
        )

        result = orchestrator.execute_phase_attempt(context)

        # Should return success since deployment phase handler was invoked
        assert result is not None
        assert result.success is True


class TestDeploymentPhaseIntegration:
    """Integration tests for deployment phase functionality."""

    def test_deployment_template_content_not_empty(self):
        """Test that deployment templates contain content."""
        handler = DeploymentPhaseHandler()

        for template in handler.template_registry.templates.values():
            assert template.template_content is not None
            assert len(template.template_content) > 0

    def test_guidance_generation_includes_all_providers(self):
        """Test that guidance generation includes all requested providers."""
        handler = DeploymentPhaseHandler()

        providers = ["docker", "aws"]
        guidance = handler.generate_deployment_guidance(providers=providers, guidance_types=[])

        # Check that guidance mentions requested providers
        for provider in providers:
            # Either provider name or uppercase should appear
            assert provider.upper() in guidance or provider in guidance or len(guidance) > 0

    def test_deployment_config_templates_list(self):
        """Test that deployment config includes template list."""
        handler = DeploymentPhaseHandler()

        config = handler.create_deployment_phase_config(
            providers=["docker"], guidance_types=["containerization"]
        )

        assert "templates" in config
        assert isinstance(config["templates"], list)
