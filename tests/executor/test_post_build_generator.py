"""Tests for post-build artifact generation (IMP-INT-003).

Tests cover:
- BuildCharacteristics dataclass
- PostBuildArtifactGenerator artifact generation
- Deployment config generation
- Runbook generation
- Monitoring template generation
- Alerting rules generation
- Docker configuration generation
- Integration with artifact generator registry
"""

from unittest.mock import Mock


from autopack.executor.post_build_generator import (
    ArtifactType,
    BuildCharacteristics,
    PostBuildArtifact,
    PostBuildArtifactGenerator,
    RunbookCategory,
    capture_build_characteristics,
    generate_post_build_artifacts,
)


class TestBuildCharacteristics:
    """Tests for BuildCharacteristics dataclass."""

    def test_default_values(self):
        """Test BuildCharacteristics has sensible defaults."""
        characteristics = BuildCharacteristics(project_name="TestProject")

        assert characteristics.project_name == "TestProject"
        assert characteristics.language == "unknown"
        assert characteristics.framework == "unknown"
        assert characteristics.build_tool == "unknown"
        assert characteristics.has_database is False
        assert characteristics.has_api is False
        assert characteristics.is_containerized is False
        assert characteristics.port == 3000

    def test_custom_values(self):
        """Test BuildCharacteristics with custom values."""
        characteristics = BuildCharacteristics(
            project_name="MyApp",
            language="python",
            framework="fastapi",
            build_tool="pip",
            has_database=True,
            has_api=True,
            is_containerized=True,
            port=8000,
            environment_variables=["DATABASE_URL", "API_KEY"],
        )

        assert characteristics.project_name == "MyApp"
        assert characteristics.language == "python"
        assert characteristics.framework == "fastapi"
        assert characteristics.build_tool == "pip"
        assert characteristics.has_database is True
        assert characteristics.has_api is True
        assert characteristics.is_containerized is True
        assert characteristics.port == 8000
        assert "DATABASE_URL" in characteristics.environment_variables

    def test_tech_stack_dict(self):
        """Test BuildCharacteristics with tech_stack dict."""
        tech_stack = {
            "name": "FastAPI + PostgreSQL",
            "category": "Python Backend",
        }
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            tech_stack=tech_stack,
        )

        assert characteristics.tech_stack == tech_stack


class TestCaptureFunction:
    """Tests for capture_build_characteristics function."""

    def test_capture_node_project(self):
        """Test capturing characteristics for a Node.js project."""
        tech_stack = {
            "name": "Next.js + Supabase",
            "category": "Full Stack JavaScript",
        }
        characteristics = capture_build_characteristics(
            project_name="MyNextApp",
            tech_stack=tech_stack,
        )

        assert characteristics.project_name == "MyNextApp"
        assert characteristics.language == "node"
        assert characteristics.framework == "next"
        assert characteristics.port == 3000

    def test_capture_python_project(self):
        """Test capturing characteristics for a Python project."""
        tech_stack = {
            "name": "FastAPI + PostgreSQL",
            "category": "Python Backend API",
        }
        characteristics = capture_build_characteristics(
            project_name="MyPythonAPI",
            tech_stack=tech_stack,
        )

        assert characteristics.project_name == "MyPythonAPI"
        assert characteristics.language == "python"
        assert characteristics.framework == "fastapi"
        assert characteristics.port == 8000
        assert characteristics.has_database is True
        assert characteristics.has_api is True

    def test_capture_django_project(self):
        """Test capturing characteristics for a Django project."""
        tech_stack = {
            "name": "Django + MySQL",
            "category": "Python Web Framework",
        }
        characteristics = capture_build_characteristics(
            project_name="MyDjangoApp",
            tech_stack=tech_stack,
        )

        assert characteristics.language == "python"
        assert characteristics.framework == "django"
        assert characteristics.has_database is True

    def test_capture_containerized_project(self):
        """Test capturing characteristics for a containerized project."""
        tech_stack = {
            "name": "Express + Docker + Kubernetes",
            "category": "Containerized Node.js Backend",
        }
        characteristics = capture_build_characteristics(
            project_name="ContainerApp",
            tech_stack=tech_stack,
        )

        assert characteristics.is_containerized is True

    def test_capture_with_build_result(self):
        """Test capturing characteristics with build result data."""
        tech_stack = {"name": "React App", "category": "Frontend"}
        build_result = {
            "duration_seconds": 45.5,
            "test_coverage_percent": 85.0,
        }
        characteristics = capture_build_characteristics(
            project_name="ReactApp",
            tech_stack=tech_stack,
            build_result=build_result,
        )

        assert characteristics.build_duration_seconds == 45.5
        assert characteristics.test_coverage_percent == 85.0


class TestPostBuildArtifactGenerator:
    """Tests for PostBuildArtifactGenerator class."""

    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        generator = PostBuildArtifactGenerator()

        assert generator._deployment_analyzer is None
        assert generator._cicd_generator is None
        assert generator._generated_artifacts == []

    def test_generator_with_analyzers(self):
        """Test generator accepts optional analyzers."""
        mock_deployment = Mock()
        mock_cicd = Mock()
        generator = PostBuildArtifactGenerator(
            deployment_analyzer=mock_deployment,
            cicd_generator=mock_cicd,
        )

        assert generator._deployment_analyzer == mock_deployment
        assert generator._cicd_generator == mock_cicd

    def test_generate_all_artifacts(self):
        """Test generating all artifacts for a build."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
            framework="express",
            is_containerized=True,
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        artifacts = generator.generate_all_artifacts(characteristics)

        assert len(artifacts) > 0
        artifact_types = [a.artifact_type for a in artifacts]
        assert ArtifactType.DEPLOYMENT_CONFIG in artifact_types
        assert ArtifactType.RUNBOOK in artifact_types
        assert ArtifactType.MONITORING in artifact_types
        assert ArtifactType.ALERTING in artifact_types
        assert ArtifactType.DOCKER in artifact_types  # Because is_containerized=True

    def test_generate_artifacts_without_docker(self):
        """Test generating artifacts without Docker config."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="python",
            framework="flask",
            is_containerized=False,
        )
        generator = PostBuildArtifactGenerator()

        artifacts = generator.generate_all_artifacts(characteristics)

        artifact_types = [a.artifact_type for a in artifacts]
        assert ArtifactType.DOCKER not in artifact_types

    def test_get_generated_artifacts(self):
        """Test retrieving previously generated artifacts."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        # Initially empty
        assert generator.get_generated_artifacts() == []

        # After generation
        generator.generate_all_artifacts(characteristics)
        assert len(generator.get_generated_artifacts()) > 0


class TestDeploymentConfigGeneration:
    """Tests for deployment configuration generation."""

    def test_generate_deployment_config(self):
        """Test generating deployment configuration artifact."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
            framework="express",
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_deployment_config(characteristics, {})

        assert artifact.artifact_type == ArtifactType.DEPLOYMENT_CONFIG
        assert artifact.name == "DEPLOYMENT_CONFIG"
        assert artifact.file_extension == "md"
        assert "TestProject" in artifact.content
        assert "node" in artifact.content
        assert "3000" in artifact.content

    def test_deployment_config_has_health_checks(self):
        """Test deployment config includes health check configuration."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            port=8080,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_deployment_config(characteristics, {})

        assert "readinessProbe" in artifact.content
        assert "livenessProbe" in artifact.content
        assert "/health" in artifact.content

    def test_deployment_config_has_resource_limits(self):
        """Test deployment config includes resource limits."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_deployment_config(characteristics, {})

        assert "Resource" in artifact.content
        assert "CPU" in artifact.content or "cpu" in artifact.content.lower()
        assert "Memory" in artifact.content or "memory" in artifact.content.lower()


class TestRunbookGeneration:
    """Tests for operational runbook generation."""

    def test_generate_runbooks(self):
        """Test generating operational runbooks."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="python",
        )
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})

        assert len(runbooks) == 4  # deployment, troubleshooting, scaling, incident response
        assert all(r.artifact_type == ArtifactType.RUNBOOK for r in runbooks)

    def test_deployment_runbook_content(self):
        """Test deployment runbook has proper content."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
        )
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})
        deployment_runbook = next(r for r in runbooks if "DEPLOYMENT" in r.name)

        assert "Pre-Deployment Checklist" in deployment_runbook.content
        assert "Rollback" in deployment_runbook.content
        assert deployment_runbook.metadata["category"] == RunbookCategory.DEPLOYMENT.value

    def test_troubleshooting_runbook_content(self):
        """Test troubleshooting runbook has proper content."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})
        troubleshooting_runbook = next(r for r in runbooks if "TROUBLESHOOTING" in r.name)

        assert "Common Issues" in troubleshooting_runbook.content
        assert "Escalation" in troubleshooting_runbook.content

    def test_scaling_runbook_content(self):
        """Test scaling runbook has proper content."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})
        scaling_runbook = next(r for r in runbooks if "SCALING" in r.name)

        assert "Horizontal Scaling" in scaling_runbook.content
        assert "HorizontalPodAutoscaler" in scaling_runbook.content

    def test_incident_response_runbook_content(self):
        """Test incident response runbook has proper content."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})
        incident_runbook = next(r for r in runbooks if "INCIDENT" in r.name)

        assert "Severity" in incident_runbook.content
        assert "SEV1" in incident_runbook.content
        assert "Mitigate" in incident_runbook.content


class TestMonitoringGeneration:
    """Tests for monitoring template generation."""

    def test_generate_monitoring_templates(self):
        """Test generating monitoring configuration templates."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_monitoring_templates(characteristics, {})

        assert artifact.artifact_type == ArtifactType.MONITORING
        assert artifact.name == "MONITORING_CONFIG"

    def test_monitoring_has_prometheus_config(self):
        """Test monitoring config includes Prometheus configuration."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_monitoring_templates(characteristics, {})

        assert "Prometheus" in artifact.content
        assert "scrape_configs" in artifact.content

    def test_monitoring_has_grafana_dashboard(self):
        """Test monitoring config includes Grafana dashboard."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_monitoring_templates(characteristics, {})

        assert "Grafana" in artifact.content
        assert "dashboard" in artifact.content.lower()

    def test_monitoring_has_instrumentation_examples(self):
        """Test monitoring config includes instrumentation examples."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_monitoring_templates(characteristics, {})

        # Should have examples for different languages
        assert "Python" in artifact.content or "python" in artifact.content
        assert "Node.js" in artifact.content or "node" in artifact.content.lower()


class TestAlertingGeneration:
    """Tests for alerting rules generation."""

    def test_generate_alerting_rules(self):
        """Test generating alerting rules configuration."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_alerting_rules(characteristics, {})

        assert artifact.artifact_type == ArtifactType.ALERTING
        assert artifact.name == "ALERTING_RULES"

    def test_alerting_has_common_alerts(self):
        """Test alerting config includes common alert rules."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_alerting_rules(characteristics, {})

        assert "HighErrorRate" in artifact.content
        assert "HighLatency" in artifact.content
        assert "ServiceDown" in artifact.content
        assert "HighMemoryUsage" in artifact.content

    def test_alerting_has_severity_levels(self):
        """Test alerting config includes severity levels."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_alerting_rules(characteristics, {})

        assert "critical" in artifact.content
        assert "warning" in artifact.content

    def test_alerting_has_integration_examples(self):
        """Test alerting config includes integration examples."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_alerting_rules(characteristics, {})

        assert "PagerDuty" in artifact.content
        assert "Slack" in artifact.content


class TestDockerConfigGeneration:
    """Tests for Docker configuration generation."""

    def test_generate_docker_config(self):
        """Test generating Docker configuration."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
            is_containerized=True,
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert artifact.artifact_type == ArtifactType.DOCKER
        assert artifact.name == "DOCKER_CONFIG"

    def test_docker_config_has_dockerfile(self):
        """Test Docker config includes Dockerfile template."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert "FROM" in artifact.content
        assert "EXPOSE" in artifact.content
        assert "CMD" in artifact.content

    def test_docker_config_node_specific(self):
        """Test Docker config is specific to Node.js."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
            port=3000,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert "node" in artifact.content.lower()
        assert "npm" in artifact.content.lower() or "node" in artifact.content.lower()

    def test_docker_config_python_specific(self):
        """Test Docker config is specific to Python."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="python",
            port=8000,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert "python" in artifact.content.lower()

    def test_docker_config_has_compose(self):
        """Test Docker config includes docker-compose.yml."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="node",
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert "docker-compose" in artifact.content
        assert "services:" in artifact.content

    def test_docker_config_has_dockerignore(self):
        """Test Docker config includes .dockerignore."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_docker_config(characteristics, {})

        assert ".dockerignore" in artifact.content
        assert "node_modules" in artifact.content or "__pycache__" in artifact.content


class TestConvenienceFunction:
    """Tests for generate_post_build_artifacts convenience function."""

    def test_generate_post_build_artifacts(self):
        """Test convenience function generates artifacts."""
        tech_stack = {
            "name": "Express + MongoDB",
            "category": "Node.js Backend",
        }
        artifacts = generate_post_build_artifacts(
            project_name="TestAPI",
            tech_stack=tech_stack,
        )

        assert len(artifacts) > 0
        assert all(isinstance(a, PostBuildArtifact) for a in artifacts)

    def test_generate_with_build_result(self):
        """Test convenience function with build result."""
        tech_stack = {"name": "FastAPI", "category": "Python"}
        build_result = {"duration_seconds": 30.0}

        artifacts = generate_post_build_artifacts(
            project_name="TestAPI",
            tech_stack=tech_stack,
            build_result=build_result,
        )

        assert len(artifacts) > 0


class TestRegistryIntegration:
    """Tests for integration with artifact generator registry."""

    def test_post_build_generator_in_registry(self):
        """Test PostBuildArtifactGenerator is registered in the registry."""
        from autopack.research.artifact_generators import get_registry

        registry = get_registry()

        assert registry.has_generator("post_build")

    def test_get_post_build_generator(self):
        """Test getting post-build generator from registry."""
        from autopack.research.artifact_generators import get_post_build_generator

        generator = get_post_build_generator()

        assert isinstance(generator, PostBuildArtifactGenerator)

    def test_registry_list_includes_post_build(self):
        """Test registry list includes post-build generator."""
        from autopack.research.artifact_generators import get_registry

        registry = get_registry()
        generators = registry.list_generators()
        names = [g["name"] for g in generators]

        assert "post_build" in names


class TestArtifactExport:
    """Tests for artifact export functionality."""

    def test_export_artifacts_to_markdown(self):
        """Test exporting artifacts to markdown files."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            is_containerized=True,
        )
        generator = PostBuildArtifactGenerator()
        generator.generate_all_artifacts(characteristics)

        file_paths = generator.export_artifacts_to_markdown()

        assert len(file_paths) > 0
        assert all(path.endswith(".md") for path in file_paths.values())


class TestArtifactMetadata:
    """Tests for artifact metadata."""

    def test_deployment_config_metadata(self):
        """Test deployment config has proper metadata."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            language="python",
            framework="django",
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_deployment_config(characteristics, {})

        assert artifact.metadata["project_name"] == "TestProject"
        assert artifact.metadata["language"] == "python"
        assert artifact.metadata["framework"] == "django"

    def test_monitoring_config_metadata(self):
        """Test monitoring config has proper metadata."""
        characteristics = BuildCharacteristics(
            project_name="TestProject",
            port=8080,
        )
        generator = PostBuildArtifactGenerator()

        artifact = generator.generate_monitoring_templates(characteristics, {})

        assert artifact.metadata["project_name"] == "TestProject"
        assert artifact.metadata["port"] == 8080

    def test_runbook_metadata(self):
        """Test runbooks have category metadata."""
        characteristics = BuildCharacteristics(project_name="TestProject")
        generator = PostBuildArtifactGenerator()

        runbooks = generator.generate_runbooks(characteristics, {})

        categories = [r.metadata.get("category") for r in runbooks]
        assert RunbookCategory.DEPLOYMENT.value in categories
        assert RunbookCategory.TROUBLESHOOTING.value in categories
        assert RunbookCategory.SCALING.value in categories
        assert RunbookCategory.INCIDENT_RESPONSE.value in categories
