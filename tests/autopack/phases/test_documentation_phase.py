"""Tests for documentation phase.

Comprehensive tests for DocumentationPhase, DocumentationConfig, DocumentationInput,
and DocumentationPhaseExecutor.
"""

from datetime import datetime
from pathlib import Path

import pytest

from autopack.phases.documentation_phase import (
    DocumentationArtifact,
    DocumentationConfig,
    DocumentationInput,
    DocumentationOutput,
    DocumentationPhase,
    DocumentationPhaseExecutor,
    DocumentationStatus,
    create_documentation_phase,
)


class TestDocumentationConfig:
    """Test DocumentationConfig dataclass."""

    def test_documentation_config_defaults(self):
        """Test DocumentationConfig with default values."""
        config = DocumentationConfig()

        assert config.documentation_types == ["api", "architecture", "user_guide", "onboarding"]
        assert config.output_format == "markdown"
        assert config.include_diagrams is True
        assert config.include_examples is True
        assert config.save_to_history is True
        assert config.max_duration_minutes is None

    def test_documentation_config_custom_values(self):
        """Test DocumentationConfig with custom values."""
        config = DocumentationConfig(
            documentation_types=["api", "user_guide"],
            output_format="html",
            include_diagrams=False,
            include_examples=False,
        )

        assert config.documentation_types == ["api", "user_guide"]
        assert config.output_format == "html"
        assert config.include_diagrams is False
        assert config.include_examples is False


class TestDocumentationInput:
    """Test DocumentationInput dataclass."""

    def test_documentation_input_basic(self):
        """Test basic DocumentationInput creation."""
        input_data = DocumentationInput(
            project_name="MyAPI",
            project_description="A REST API for user management",
            tech_stack={"language": "python", "framework": "fastapi"},
        )

        assert input_data.project_name == "MyAPI"
        assert input_data.project_description == "A REST API for user management"
        assert input_data.tech_stack["language"] == "python"
        assert input_data.api_endpoints is None

    def test_documentation_input_with_endpoints(self):
        """Test DocumentationInput with API endpoints."""
        endpoints = [
            {"method": "GET", "path": "/users", "description": "List all users"},
            {"method": "POST", "path": "/users", "description": "Create a new user"},
        ]
        input_data = DocumentationInput(
            project_name="MyAPI",
            project_description="A REST API",
            tech_stack={"language": "python"},
            api_endpoints=endpoints,
        )

        assert len(input_data.api_endpoints) == 2
        assert input_data.api_endpoints[0]["method"] == "GET"

    def test_documentation_input_with_architecture(self):
        """Test DocumentationInput with architecture info."""
        architecture = {
            "components": [
                {"name": "API Server", "description": "FastAPI application"},
                {"name": "Database", "description": "PostgreSQL instance"},
            ]
        }
        input_data = DocumentationInput(
            project_name="MyAPI",
            project_description="A REST API",
            tech_stack={"language": "python"},
            architecture=architecture,
        )

        assert len(input_data.architecture["components"]) == 2


class TestDocumentationOutput:
    """Test DocumentationOutput dataclass."""

    def test_documentation_output_defaults(self):
        """Test DocumentationOutput with default values."""
        output = DocumentationOutput()

        assert output.api_docs_path is None
        assert output.architecture_guide_path is None
        assert output.user_guide_path is None
        assert output.onboarding_guide_path is None
        assert output.artifacts_generated == []
        assert output.total_pages_estimated == 0
        assert output.documentation_coverage == 0.0

    def test_documentation_output_with_artifacts(self):
        """Test DocumentationOutput with artifacts."""
        artifacts = [
            DocumentationArtifact(
                artifact_type="api",
                file_path="/path/to/API.md",
                title="API Documentation",
                description="Complete API reference",
            ),
            DocumentationArtifact(
                artifact_type="architecture",
                file_path="/path/to/ARCHITECTURE.md",
                title="Architecture Guide",
                description="System architecture overview",
            ),
        ]
        output = DocumentationOutput(
            api_docs_path="/path/to/API.md",
            architecture_guide_path="/path/to/ARCHITECTURE.md",
            artifacts_generated=artifacts,
            total_pages_estimated=10,
            documentation_coverage=50.0,
        )

        assert len(output.artifacts_generated) == 2
        assert output.documentation_coverage == 50.0
        assert output.total_pages_estimated == 10


class TestDocumentationPhase:
    """Test DocumentationPhase dataclass."""

    def test_documentation_phase_creation(self):
        """Test creating a documentation phase."""
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate project documentation",
            config=DocumentationConfig(),
        )

        assert phase.phase_id == "doc-001"
        assert phase.status == DocumentationStatus.PENDING
        assert phase.output is None
        assert phase.started_at is None

    def test_documentation_phase_to_dict(self):
        """Test DocumentationPhase serialization."""
        config = DocumentationConfig(documentation_types=["api", "user_guide"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="Test API project",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=config,
            input_data=input_data,
            status=DocumentationStatus.COMPLETED,
        )

        phase_dict = phase.to_dict()

        assert phase_dict["phase_id"] == "doc-001"
        assert phase_dict["status"] == "completed"
        assert phase_dict["config"]["documentation_types"] == ["api", "user_guide"]
        assert phase_dict["input_data"]["project_name"] == "TestAPI"
        assert phase_dict["error"] is None

    def test_documentation_phase_with_error(self):
        """Test DocumentationPhase with error state."""
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=DocumentationConfig(),
            status=DocumentationStatus.FAILED,
            error="Project description is missing",
        )

        phase_dict = phase.to_dict()
        assert phase_dict["status"] == "failed"
        assert "missing" in phase_dict["error"]


class TestDocumentationPhaseExecutor:
    """Test DocumentationPhaseExecutor."""

    @pytest.fixture
    def executor(self, tmp_path):
        """Create executor with temp workspace."""
        return DocumentationPhaseExecutor(
            workspace_path=tmp_path,
            build_history_path=tmp_path / "BUILD_HISTORY.md",
        )

    def test_executor_initialization(self, executor, tmp_path):
        """Test executor initialization."""
        assert executor.workspace_path == tmp_path
        assert executor.build_history_path is not None

    def test_execute_phase_no_input(self, executor):
        """Test executing phase with no input data."""
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=DocumentationConfig(),
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.FAILED
        assert "No input data" in result.error

    def test_execute_phase_success(self, executor):
        """Test successful phase execution."""
        config = DocumentationConfig(
            documentation_types=["api", "architecture", "user_guide", "onboarding"]
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python", "framework": "fastapi"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.error is None

    def test_execute_phase_generates_api_docs(self, executor):
        """Test that API documentation is generated."""
        config = DocumentationConfig(documentation_types=["api"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
            api_endpoints=[
                {"method": "GET", "path": "/users", "description": "List users"},
            ],
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate API docs",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.api_docs_path is not None
        assert Path(result.output.api_docs_path).exists()
        content = Path(result.output.api_docs_path).read_text()
        assert "API Documentation" in content

    def test_execute_phase_generates_architecture_guide(self, executor):
        """Test that architecture guide is generated."""
        config = DocumentationConfig(documentation_types=["architecture"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python", "database": "postgresql"},
            architecture={
                "components": [
                    {"name": "API Server", "description": "FastAPI server"},
                ]
            },
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate architecture guide",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.architecture_guide_path is not None
        assert Path(result.output.architecture_guide_path).exists()
        content = Path(result.output.architecture_guide_path).read_text()
        assert "Architecture" in content

    def test_execute_phase_generates_user_guide(self, executor):
        """Test that user guide is generated."""
        config = DocumentationConfig(documentation_types=["user_guide"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
            target_audience="API developers",
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate user guide",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.user_guide_path is not None
        assert Path(result.output.user_guide_path).exists()
        content = Path(result.output.user_guide_path).read_text()
        assert "User Guide" in content

    def test_execute_phase_generates_onboarding_flow(self, executor):
        """Test that onboarding guide is generated."""
        config = DocumentationConfig(documentation_types=["onboarding"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate onboarding guide",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.output is not None
        assert result.output.onboarding_guide_path is not None
        assert Path(result.output.onboarding_guide_path).exists()
        content = Path(result.output.onboarding_guide_path).read_text()
        assert "Onboarding" in content

    def test_execute_phase_saves_to_history(self, executor, tmp_path):
        """Test that phase is saved to BUILD_HISTORY."""
        config = DocumentationConfig(
            documentation_types=["api"],
            save_to_history=True,
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        history_file = tmp_path / "BUILD_HISTORY.md"
        assert history_file.exists()
        content = history_file.read_text()
        assert "Documentation Phase" in content
        assert "doc-001" in content
        assert "completed" in content

    def test_execute_phase_multiple_documentation_types(self, executor):
        """Test execution with multiple documentation types."""
        config = DocumentationConfig(
            documentation_types=["api", "architecture", "user_guide", "onboarding"]
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate all documentation",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.COMPLETED
        assert len(result.output.artifacts_generated) == 4
        assert result.output.documentation_coverage == 100.0

    def test_execute_phase_partial_documentation(self, executor):
        """Test execution with partial documentation types."""
        config = DocumentationConfig(documentation_types=["api", "user_guide"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate partial documentation",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.COMPLETED
        assert len(result.output.artifacts_generated) == 2
        # Coverage should be 100% since we generated all configured types (2 out of 2)
        assert result.output.documentation_coverage == 100.0

    def test_execute_phase_artifacts_created(self, executor):
        """Test that artifacts are properly created."""
        config = DocumentationConfig(documentation_types=["api"])
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate documentation",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert len(result.output.artifacts_generated) > 0
        for artifact in result.output.artifacts_generated:
            assert Path(artifact.file_path).exists()
            assert artifact.title is not None
            assert artifact.artifact_type is not None

    def test_execute_phase_without_examples(self, executor):
        """Test execution with examples disabled."""
        config = DocumentationConfig(
            documentation_types=["api"],
            include_examples=False,
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate API docs without examples",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.COMPLETED
        api_path = Path(result.output.api_docs_path)
        content = api_path.read_text()
        assert "Usage Examples" not in content

    def test_execute_phase_without_diagrams(self, executor):
        """Test execution with diagrams disabled."""
        config = DocumentationConfig(
            documentation_types=["architecture"],
            include_diagrams=False,
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate architecture guide without diagrams",
            config=config,
            input_data=input_data,
        )

        result = executor.execute(phase)

        assert result.status == DocumentationStatus.COMPLETED
        arch_path = Path(result.output.architecture_guide_path)
        content = arch_path.read_text()
        assert "System Diagrams" not in content


class TestDocumentationPhaseFactory:
    """Test factory function for creating documentation phases."""

    def test_create_documentation_phase(self):
        """Test factory function."""
        phase = create_documentation_phase(
            phase_id="doc-prod",
            project_name="MyAPI",
            project_description="My REST API",
            tech_stack={"language": "python", "framework": "fastapi"},
        )

        assert phase.phase_id == "doc-prod"
        assert phase.input_data.project_name == "MyAPI"
        assert phase.status == DocumentationStatus.PENDING

    def test_create_documentation_phase_with_options(self):
        """Test factory function with custom options."""
        phase = create_documentation_phase(
            phase_id="doc-prod",
            project_name="MyAPI",
            project_description="My REST API",
            tech_stack={"language": "python"},
            documentation_types=["api", "user_guide"],
            output_format="html",
            include_diagrams=False,
        )

        assert phase.config.documentation_types == ["api", "user_guide"]
        assert phase.config.output_format == "html"
        assert phase.config.include_diagrams is False

    def test_create_documentation_phase_with_endpoints(self):
        """Test factory function with API endpoints."""
        endpoints = [
            {"method": "GET", "path": "/users", "description": "List users"},
        ]
        phase = create_documentation_phase(
            phase_id="doc-prod",
            project_name="MyAPI",
            project_description="My REST API",
            tech_stack={"language": "python"},
            api_endpoints=endpoints,
        )

        assert len(phase.input_data.api_endpoints) == 1
        assert phase.input_data.api_endpoints[0]["path"] == "/users"


class TestDocumentationPhaseIntegration:
    """Integration tests for documentation phase."""

    def test_full_documentation_workflow(self, tmp_path):
        """Test complete documentation workflow."""
        # Create phase
        phase = create_documentation_phase(
            phase_id="doc-prod",
            project_name="TestAPI",
            project_description="A test REST API",
            tech_stack={"language": "python", "framework": "fastapi"},
            api_endpoints=[
                {"method": "GET", "path": "/users", "description": "List users"},
                {"method": "POST", "path": "/users", "description": "Create user"},
            ],
            architecture={
                "components": [
                    {"name": "API Server", "description": "FastAPI server"},
                    {"name": "Database", "description": "PostgreSQL"},
                ]
            },
            target_audience="API developers",
        )

        # Execute phase
        executor = DocumentationPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        # Verify results
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert len(result.output.artifacts_generated) == 4
        assert result.output.api_docs_path is not None
        assert result.output.architecture_guide_path is not None
        assert result.output.user_guide_path is not None
        assert result.output.onboarding_guide_path is not None

    def test_phase_serialization_roundtrip(self, tmp_path):
        """Test phase serialization and deserialization."""
        phase = create_documentation_phase(
            phase_id="doc-001",
            project_name="MyAPI",
            project_description="Test API",
            tech_stack={"language": "python"},
        )

        # Execute to populate output
        executor = DocumentationPhaseExecutor(workspace_path=tmp_path)
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

    def test_documentation_coverage_calculation(self, tmp_path):
        """Test documentation coverage metric calculation."""
        config = DocumentationConfig(
            documentation_types=["api", "architecture", "user_guide", "onboarding"]
        )
        input_data = DocumentationInput(
            project_name="TestAPI",
            project_description="A test API",
            tech_stack={"language": "python"},
        )
        phase = DocumentationPhase(
            phase_id="doc-001",
            description="Generate full documentation",
            config=config,
            input_data=input_data,
        )

        executor = DocumentationPhaseExecutor(workspace_path=tmp_path)
        result = executor.execute(phase)

        # All types generated should give 100% coverage
        assert result.output.documentation_coverage == 100.0
        assert result.output.total_pages_estimated > 0
