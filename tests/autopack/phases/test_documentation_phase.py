"""Tests for documentation phase implementation."""

from pathlib import Path

import pytest

from autopack.phases.documentation_phase import (
    DocumentationConfig,
    DocumentationInput,
    DocumentationOutput,
    DocumentationPhase,
    DocumentationPhaseExecutor,
    DocumentationStatus,
    create_documentation_phase,
)


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace for tests."""
    return tmp_path / "workspace"


@pytest.fixture
def executor(temp_workspace):
    """Create documentation phase executor."""
    temp_workspace.mkdir(parents=True, exist_ok=True)
    return DocumentationPhaseExecutor(workspace_path=temp_workspace)


@pytest.fixture
def sample_input_data():
    """Sample input data for documentation phase."""
    return DocumentationInput(
        project_name="TestProject",
        project_description="A test project for documentation",
        tech_stack={
            "language": "Python",
            "framework": "FastAPI",
            "database": "PostgreSQL",
        },
        source_paths=["src/", "tests/"],
    )


class TestDocumentationPhase:
    """Test documentation phase data structures."""

    def test_documentation_phase_creation(self, sample_input_data):
        """Test creating a documentation phase."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test Documentation Phase",
            config=DocumentationConfig(),
            input_data=sample_input_data,
        )

        assert phase.phase_id == "test_phase"
        assert phase.status == DocumentationStatus.PENDING
        assert phase.input_data == sample_input_data
        assert phase.output is None

    def test_documentation_phase_to_dict(self, sample_input_data):
        """Test phase serialization to dictionary."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test Documentation Phase",
            config=DocumentationConfig(include_api_docs=True),
            input_data=sample_input_data,
        )

        data = phase.to_dict()
        assert data["phase_id"] == "test_phase"
        assert data["status"] == "pending"
        assert data["config"]["include_api_docs"] is True
        assert data["input_data"]["project_name"] == "TestProject"

    def test_documentation_config_defaults(self):
        """Test default configuration values."""
        config = DocumentationConfig()
        assert config.include_api_docs is True
        assert config.include_architecture_docs is True
        assert config.include_user_guide is True
        assert config.include_examples is True
        assert config.output_format == "markdown"
        assert config.save_to_history is True

    def test_documentation_output_creation(self):
        """Test creating documentation output."""
        output = DocumentationOutput()
        assert output.api_docs_path is None
        assert output.architecture_docs_path is None
        assert output.user_guide_path is None
        assert len(output.artifacts_generated) == 0
        assert len(output.warnings) == 0


class TestDocumentationPhaseExecutor:
    """Test documentation phase executor."""

    def test_executor_initialization(self, temp_workspace):
        """Test executor initialization."""
        executor = DocumentationPhaseExecutor(workspace_path=temp_workspace)
        assert executor.workspace_path == temp_workspace

    def test_execute_phase_without_input(self, executor):
        """Test executing phase without input data."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(),
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.FAILED
        assert result.error == "No input data provided for documentation phase"

    def test_execute_phase_successfully(self, executor, sample_input_data):
        """Test successful phase execution."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test Documentation Phase",
            config=DocumentationConfig(),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_api_documentation_generation(self, executor, sample_input_data):
        """Test API documentation generation."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(include_api_docs=True),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.output.api_docs_path is not None
        assert "api" in result.output.documentation_types_generated

        # Verify file was created
        api_path = Path(result.output.api_docs_path)
        assert api_path.exists()
        content = api_path.read_text()
        assert "API Documentation" in content
        assert sample_input_data.project_name in content

    def test_architecture_documentation_generation(self, executor, sample_input_data):
        """Test architecture documentation generation."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(include_architecture_docs=True),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.output.architecture_docs_path is not None
        assert "architecture" in result.output.documentation_types_generated

        # Verify file was created
        arch_path = Path(result.output.architecture_docs_path)
        assert arch_path.exists()
        content = arch_path.read_text()
        assert "Architecture Documentation" in content

    def test_user_guide_generation(self, executor, sample_input_data):
        """Test user guide documentation generation."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(include_user_guide=True),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.output.user_guide_path is not None
        assert "usage" in result.output.documentation_types_generated

        # Verify file was created
        guide_path = Path(result.output.user_guide_path)
        assert guide_path.exists()
        content = guide_path.read_text()
        assert "User Guide" in content

    def test_examples_generation(self, executor, sample_input_data):
        """Test examples documentation generation."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(include_examples=True),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.output.examples_path is not None

        # Verify file was created
        examples_path = Path(result.output.examples_path)
        assert examples_path.exists()
        content = examples_path.read_text()
        assert "Examples" in content

    def test_documentation_index_generation(self, executor, sample_input_data):
        """Test documentation index generation."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert result.output.documentation_index_path is not None

        # Verify file was created
        index_path = Path(result.output.documentation_index_path)
        assert index_path.exists()
        content = index_path.read_text()
        assert "Documentation" in content
        assert sample_input_data.project_name in content

    def test_all_documentation_types(self, executor, sample_input_data):
        """Test generating all documentation types."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(
                include_api_docs=True,
                include_architecture_docs=True,
                include_user_guide=True,
                include_examples=True,
            ),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED
        assert result.output is not None
        assert len(result.output.artifacts_generated) > 0
        assert "api" in result.output.documentation_types_generated
        assert "architecture" in result.output.documentation_types_generated
        assert "usage" in result.output.documentation_types_generated

    def test_documentation_in_workspace(self, executor, sample_input_data):
        """Test that documentation is created in the correct workspace."""
        phase = DocumentationPhase(
            phase_id="test_phase",
            description="Test",
            config=DocumentationConfig(),
            input_data=sample_input_data,
        )

        result = executor.execute(phase)
        assert result.status == DocumentationStatus.COMPLETED

        # Verify docs directory exists
        docs_dir = executor.workspace_path / "docs"
        assert docs_dir.exists()
        assert docs_dir.is_dir()

        # Verify documentation files are in the correct location
        for artifact in result.output.artifacts_generated:
            artifact_path = Path(artifact)
            assert artifact_path.exists()
            assert str(docs_dir) in str(artifact_path)


class TestCreateDocumentationPhase:
    """Test documentation phase factory function."""

    def test_create_documentation_phase(self):
        """Test creating a documentation phase with factory function."""
        tech_stack = {"Python": "3.11", "FastAPI": "0.100.0"}
        phase = create_documentation_phase(
            phase_id="doc_phase_1",
            project_name="TestProject",
            project_description="A test project",
            tech_stack=tech_stack,
        )

        assert phase.phase_id == "doc_phase_1"
        assert phase.input_data is not None
        assert phase.input_data.project_name == "TestProject"
        assert phase.input_data.tech_stack == tech_stack
        assert phase.status == DocumentationStatus.PENDING

    def test_create_documentation_phase_with_options(self):
        """Test creating a documentation phase with custom options."""
        tech_stack = {"Python": "3.11"}
        phase = create_documentation_phase(
            phase_id="doc_phase_2",
            project_name="TestProject",
            project_description="A test project",
            tech_stack=tech_stack,
            include_examples=False,
            output_format="html",
        )

        assert phase.config.include_examples is False
        assert phase.config.output_format == "html"
