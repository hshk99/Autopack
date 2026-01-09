"""
Tests for task brief generation.

BUILD-197: Claude Code sub-agent glue work
"""

import pytest

from autopack.subagent.context import ContextFileManager, SubagentFinding
from autopack.subagent.output_contract import OutputType
from autopack.subagent.task_brief import (
    CONSTRAINT_DESCRIPTIONS,
    TaskBrief,
    TaskBriefGenerator,
    TaskConstraint,
)


class TestTaskConstraint:
    """Tests for TaskConstraint enum and descriptions."""

    def test_all_constraints_have_descriptions(self):
        """Test that all constraints have descriptions."""
        for constraint in TaskConstraint:
            assert constraint in CONSTRAINT_DESCRIPTIONS
            assert len(CONSTRAINT_DESCRIPTIONS[constraint]) > 0

    def test_no_secrets_description_mentions_redact(self):
        """Test that no_secrets constraint mentions redaction."""
        desc = CONSTRAINT_DESCRIPTIONS[TaskConstraint.NO_SECRETS]
        assert "redact" in desc.lower() or "secret" in desc.lower()

    def test_no_side_effects_description_mentions_api(self):
        """Test that no_side_effects constraint mentions API calls."""
        desc = CONSTRAINT_DESCRIPTIONS[TaskConstraint.NO_SIDE_EFFECTS]
        assert "api" in desc.lower() or "side effect" in desc.lower()


class TestTaskBrief:
    """Tests for TaskBrief dataclass."""

    def test_to_markdown_basic(self):
        """Test basic markdown generation."""
        brief = TaskBrief(
            task_id="task-001",
            run_id="run-001",
            project_id="test",
            family="build",
            objective="Research the codebase structure",
            constraints=[TaskConstraint.NO_CODE_CHANGES, TaskConstraint.NO_SECRETS],
        )
        md = brief.to_markdown()

        assert "# Task Brief" in md
        assert "`task-001`" in md
        assert "`run-001`" in md
        assert "Research the codebase structure" in md
        assert "No Code Changes" in md
        assert "No Secrets" in md

    def test_to_markdown_with_all_sections(self):
        """Test markdown with all sections populated."""
        from autopack.subagent.output_contract import create_contract

        contract = create_contract(OutputType.RESEARCH, "codebase")

        brief = TaskBrief(
            task_id="task-002",
            run_id="run-002",
            project_id="autopack",
            family="research",
            objective="Analyze code patterns",
            success_criteria=["Identify patterns", "Document findings"],
            context_file="handoff/context.md",
            required_reads=["src/main.py", "src/utils.py"],
            optional_reads=["docs/README.md"],
            output_contract=contract,
            output_filename=contract.get_filename(),
            constraints=[TaskConstraint.NO_CODE_CHANGES],
            additional_constraints=["Focus only on Python files"],
            background="This is a Python project with FastAPI backend.",
            prior_findings=["Found FastAPI usage", "SQLAlchemy for ORM"],
            timeout_minutes=45,
        )
        md = brief.to_markdown()

        # Check all major sections
        assert "## Objective" in md
        assert "### Success Criteria" in md
        assert "## Background" in md
        assert "### Prior Findings" in md
        assert "## What to Read" in md
        assert "### Required Reading" in md
        assert "### Optional Reading" in md
        assert "## What to Produce" in md
        assert "### Output Requirements" in md
        assert "### Required Sections" in md
        assert "## Constraints" in md
        assert "### Additional Constraints" in md
        assert "## Reminder" in md

        # Check specific content
        assert "`src/main.py`" in md
        assert "`docs/README.md`" in md
        assert "Focus only on Python files" in md
        assert "45 minutes" in md

    def test_to_json_serialization(self):
        """Test JSON serialization."""
        from autopack.subagent.output_contract import create_contract

        contract = create_contract(OutputType.PLAN, "feature")

        brief = TaskBrief(
            task_id="task-003",
            run_id="run-003",
            project_id="test",
            family="build",
            objective="Plan feature implementation",
            constraints=[TaskConstraint.NO_CODE_CHANGES, TaskConstraint.BOUNDED_SCOPE],
            output_contract=contract,
        )
        json_data = brief.to_json()

        assert json_data["task_id"] == "task-003"
        assert json_data["objective"] == "Plan feature implementation"
        assert "no_code_changes" in json_data["constraints"]
        assert "bounded_scope" in json_data["constraints"]
        assert json_data["output_contract"]["output_type"] == "plan"

    def test_default_timeout(self):
        """Test default timeout is 30 minutes."""
        brief = TaskBrief(
            task_id="task-004",
            run_id="run-004",
            project_id="test",
            family="build",
            objective="Test defaults",
        )
        assert brief.timeout_minutes == 30


class TestTaskBriefGenerator:
    """Tests for TaskBriefGenerator."""

    @pytest.fixture
    def temp_runs_dir(self, tmp_path):
        """Create a temporary runs directory."""
        runs_dir = tmp_path / ".autonomous_runs"
        runs_dir.mkdir()
        return runs_dir

    @pytest.fixture
    def generator(self, temp_runs_dir):
        """Create a task brief generator."""
        return TaskBriefGenerator(temp_runs_dir)

    @pytest.fixture
    def context_manager(self, temp_runs_dir):
        """Create a context file manager."""
        return ContextFileManager(temp_runs_dir)

    def test_default_constraints_applied(self, generator, context_manager):
        """Test that default constraints are applied."""
        # Create context first
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-001",
            objective="Test run",
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-001",
            topic="codebase",
            objective="Research the codebase",
        )

        # Check default constraints are present
        assert TaskConstraint.NO_CODE_CHANGES in brief.constraints
        assert TaskConstraint.NO_SECRETS in brief.constraints
        assert TaskConstraint.NO_SIDE_EFFECTS in brief.constraints
        assert TaskConstraint.DETERMINISTIC_OUTPUT in brief.constraints

    def test_generate_research_brief(self, generator, context_manager):
        """Test generating a research brief."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-001",
            objective="Analyze codebase",
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-001",
            topic="architecture",
            objective="Research the architecture",
            required_reads=["src/main.py"],
            success_criteria=["Document architecture", "Identify patterns"],
        )

        assert brief.task_id.startswith("research-architecture-")
        assert brief.output_contract.output_type == OutputType.RESEARCH
        assert "src/main.py" in brief.required_reads
        assert "Document architecture" in brief.success_criteria

    def test_generate_planning_brief(self, generator, context_manager):
        """Test generating a planning brief."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-002",
            objective="Implement feature",
        )

        brief = generator.generate_planning_brief(
            project_id="test",
            family="build",
            run_id="run-002",
            topic="auth-feature",
            objective="Plan authentication implementation",
        )

        assert brief.task_id.startswith("plan-auth-feature-")
        assert brief.output_contract.output_type == OutputType.PLAN
        # Check default planning success criteria
        assert any("actionable" in c.lower() for c in brief.success_criteria)
        assert any("acceptance criteria" in c.lower() for c in brief.success_criteria)

    def test_generate_analysis_brief(self, generator, context_manager):
        """Test generating an analysis brief."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-003",
            objective="Analyze performance",
        )

        brief = generator.generate_analysis_brief(
            project_id="test",
            family="build",
            run_id="run-003",
            topic="performance",
            objective="Analyze system performance",
        )

        assert brief.task_id.startswith("analysis-performance-")
        assert brief.output_contract.output_type == OutputType.ANALYSIS
        # Check that analysis contract requires confidence
        assert brief.output_contract.require_confidence_scores

    def test_prior_findings_populated_from_context(self, generator, context_manager):
        """Test that prior findings are populated from context."""
        # Create context with findings
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-004",
            objective="Test run",
        )
        context_manager.add_finding(
            project_id="test",
            family="build",
            run_id="run-004",
            finding=SubagentFinding(
                topic="Previous Research",
                summary="Found interesting pattern X",
                confidence=0.9,
            ),
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-004",
            topic="follow-up",
            objective="Follow up on findings",
        )

        assert "Found interesting pattern X" in brief.prior_findings

    def test_background_populated_from_context(self, generator, context_manager):
        """Test that background is populated from context objective."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-005",
            objective="Build a REST API for user management",
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-005",
            topic="api-design",
            objective="Research API patterns",
        )

        assert brief.background == "Build a REST API for user management"

    def test_discover_artifacts(self, generator, temp_runs_dir):
        """Test artifact discovery."""
        # Create some artifacts
        run_dir = temp_runs_dir / "test/runs/build/run-006"
        handoff_dir = run_dir / "handoff"
        phases_dir = run_dir / "phases"
        handoff_dir.mkdir(parents=True)
        phases_dir.mkdir(parents=True)

        (handoff_dir / "research_initial.md").write_text("Initial research")
        (phases_dir / "phase_01.md").write_text("Phase 1")

        artifacts = generator._discover_artifacts(run_dir)

        assert "handoff/research_initial.md" in artifacts
        assert "phases/phase_01.md" in artifacts

    def test_generate_from_context(self, generator, context_manager):
        """Test generating brief from existing context."""
        # Create context with artifacts
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-007",
            objective="Build feature X",
            success_criteria=["Feature works", "Tests pass"],
            artifact_paths={"initial_research": "handoff/research_initial.md"},
        )

        brief = generator.generate_from_context(
            project_id="test",
            family="build",
            run_id="run-007",
            output_type=OutputType.PLAN,
            topic="feature-x",
        )

        assert "Build feature X" in brief.objective
        assert "Feature works" in brief.success_criteria
        assert "handoff/research_initial.md" in brief.required_reads

    def test_generate_from_context_nonexistent_raises(self, generator):
        """Test that generating from nonexistent context raises error."""
        with pytest.raises(ValueError, match="No context file found"):
            generator.generate_from_context(
                project_id="nonexistent",
                family="build",
                run_id="run-999",
                output_type=OutputType.RESEARCH,
                topic="test",
            )

    def test_save_brief(self, generator, context_manager, temp_runs_dir):
        """Test saving a task brief."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-008",
            objective="Test saving",
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-008",
            topic="test",
            objective="Test brief saving",
        )

        md_path = generator.save_brief(brief)

        assert md_path.exists()
        assert "task_brief_" in md_path.name

        # Check JSON also saved
        json_path = md_path.with_suffix(".json")
        assert json_path.exists()

        # Verify content
        content = md_path.read_text()
        assert "# Task Brief" in content
        assert "Test brief saving" in content

    def test_additional_constraints_preserved(self, generator, context_manager):
        """Test that additional constraints are preserved."""
        context_manager.create_context(
            project_id="test",
            family="build",
            run_id="run-009",
            objective="Test constraints",
        )

        brief = generator.generate_research_brief(
            project_id="test",
            family="build",
            run_id="run-009",
            topic="test",
            objective="Test",
            additional_constraints=["Custom constraint 1", "Custom constraint 2"],
        )

        assert "Custom constraint 1" in brief.additional_constraints
        assert "Custom constraint 2" in brief.additional_constraints
