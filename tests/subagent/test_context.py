"""
Tests for context file management.

BUILD-197: Claude Code sub-agent glue work
"""

import pytest

from autopack.subagent.context import (ContextFile, ContextFileManager,
                                       SubagentFinding, SubagentProposal)


class TestSubagentFinding:
    """Tests for SubagentFinding dataclass."""

    def test_to_markdown_basic(self):
        """Test basic markdown generation."""
        finding = SubagentFinding(
            topic="Test Topic",
            summary="This is a test finding.",
            confidence=0.85,
        )
        md = finding.to_markdown()

        assert "### Test Topic" in md
        assert "**Confidence**: 85%" in md
        assert "This is a test finding." in md

    def test_to_markdown_with_references(self):
        """Test markdown with file references."""
        finding = SubagentFinding(
            topic="Code Analysis",
            summary="Found issues in the codebase.",
            confidence=0.9,
            file_references=["src/main.py", "src/utils.py"],
        )
        md = finding.to_markdown()

        assert "**References**:" in md
        assert "`src/main.py`" in md
        assert "`src/utils.py`" in md


class TestSubagentProposal:
    """Tests for SubagentProposal dataclass."""

    def test_to_markdown_basic(self):
        """Test basic markdown generation."""
        proposal = SubagentProposal(
            action="Implement feature X",
            rationale="This will improve performance.",
            priority="P1",
        )
        md = proposal.to_markdown()

        assert "### Implement feature X" in md
        assert "**Priority**: P1" in md
        assert "This will improve performance." in md

    def test_to_markdown_with_dependencies_and_risks(self):
        """Test markdown with dependencies and risks."""
        proposal = SubagentProposal(
            action="Refactor module",
            rationale="Needed for maintainability.",
            priority="P0",
            estimated_effort="2 days",
            dependencies=["Complete testing", "Update docs"],
            risks=["May break existing integrations"],
        )
        md = proposal.to_markdown()

        assert "**Effort**: 2 days" in md
        assert "**Dependencies**:" in md
        assert "Complete testing" in md
        assert "**Risks**:" in md
        assert "May break existing integrations" in md


class TestContextFile:
    """Tests for ContextFile dataclass."""

    def test_to_markdown_minimal(self):
        """Test markdown generation with minimal data."""
        context = ContextFile(
            run_id="run-001",
            project_id="test-project",
            family="build",
            objective="Test the system",
        )
        md = context.to_markdown()

        assert "# Run Context" in md
        assert "`run-001`" in md
        assert "`test-project`" in md
        assert "`build`" in md
        assert "Test the system" in md

    def test_to_markdown_full(self):
        """Test markdown generation with full data."""
        context = ContextFile(
            run_id="run-002",
            project_id="autopack",
            family="research",
            objective="Analyze codebase structure",
            success_criteria=["Document all modules", "Identify patterns"],
            current_phase="analysis",
            gaps=["Missing tests", "No docs"],
            blockers=["API key expired"],
            selected_plan="Start with src/ directory",
            plan_rationale="Most critical code lives there",
            constraints=["No code changes", "Read-only"],
            artifact_paths={"source_map": "handoff/source_map.md"},
            findings=[
                SubagentFinding(
                    topic="Architecture",
                    summary="Well-structured",
                    confidence=0.9,
                )
            ],
            proposals=[
                SubagentProposal(
                    action="Add tests",
                    rationale="Improve coverage",
                    priority="P1",
                )
            ],
        )
        md = context.to_markdown()

        # Check all sections present
        assert "## Objective" in md
        assert "### Success Criteria" in md
        assert "## Current State" in md
        assert "### Gaps" in md
        assert "### Blockers" in md
        assert "## Selected Plan" in md
        assert "## Constraints" in md
        assert "## Artifacts" in md
        assert "## Findings" in md
        assert "## Proposals" in md

    def test_to_json_and_from_json_roundtrip(self):
        """Test JSON serialization roundtrip."""
        original = ContextFile(
            run_id="run-003",
            project_id="test",
            family="build",
            objective="Test roundtrip",
            success_criteria=["Works correctly"],
            gaps=["Missing data"],
            constraints=["No side effects"],
            findings=[
                SubagentFinding(
                    topic="Test",
                    summary="It works",
                    confidence=0.8,
                    file_references=["test.py"],
                )
            ],
            proposals=[
                SubagentProposal(
                    action="Continue",
                    rationale="Going well",
                    priority="P2",
                )
            ],
        )

        json_data = original.to_json()
        restored = ContextFile.from_json(json_data)

        assert restored.run_id == original.run_id
        assert restored.project_id == original.project_id
        assert restored.objective == original.objective
        assert restored.success_criteria == original.success_criteria
        assert restored.gaps == original.gaps
        assert len(restored.findings) == 1
        assert restored.findings[0].topic == "Test"
        assert len(restored.proposals) == 1
        assert restored.proposals[0].action == "Continue"


class TestContextFileManager:
    """Tests for ContextFileManager."""

    @pytest.fixture
    def temp_runs_dir(self, tmp_path):
        """Create a temporary runs directory."""
        runs_dir = tmp_path / ".autonomous_runs"
        runs_dir.mkdir()
        return runs_dir

    @pytest.fixture
    def manager(self, temp_runs_dir):
        """Create a context file manager."""
        return ContextFileManager(temp_runs_dir)

    def test_create_context(self, manager, temp_runs_dir):
        """Test creating a new context file."""
        context = manager.create_context(
            project_id="test",
            family="build",
            run_id="run-001",
            objective="Test creation",
            success_criteria=["Files created"],
        )

        assert context.run_id == "run-001"
        assert context.project_id == "test"
        assert context.family == "build"
        assert context.objective == "Test creation"

        # Check default constraints are applied
        assert len(context.constraints) >= 5
        assert any("DO NOT execute" in c for c in context.constraints)
        assert any("secrets" in c.lower() for c in context.constraints)

        # Check files exist
        md_path = temp_runs_dir / "test/runs/build/run-001/handoff/context.md"
        json_path = temp_runs_dir / "test/runs/build/run-001/handoff/context.json"
        assert md_path.exists()
        assert json_path.exists()

    def test_load_context(self, manager, temp_runs_dir):
        """Test loading an existing context file."""
        # Create first
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-002",
            objective="Test loading",
        )

        # Load
        loaded = manager.load_context("test", "build", "run-002")

        assert loaded is not None
        assert loaded.run_id == "run-002"
        assert loaded.objective == "Test loading"

    def test_load_nonexistent_context(self, manager):
        """Test loading a context that doesn't exist."""
        loaded = manager.load_context("nonexistent", "family", "run-999")
        assert loaded is None

    def test_save_context_increments_version(self, manager):
        """Test that saving increments version."""
        context = manager.create_context(
            project_id="test",
            family="build",
            run_id="run-003",
            objective="Test versioning",
        )
        initial_version = context.version

        manager.save_context(context)
        assert context.version == initial_version + 1

        manager.save_context(context)
        assert context.version == initial_version + 2

    def test_add_finding(self, manager):
        """Test adding a finding to context."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-004",
            objective="Test findings",
        )

        finding = SubagentFinding(
            topic="New Finding",
            summary="Found something interesting",
            confidence=0.75,
        )

        updated = manager.add_finding("test", "build", "run-004", finding)

        assert len(updated.findings) == 1
        assert updated.findings[0].topic == "New Finding"

    def test_add_proposal(self, manager):
        """Test adding a proposal to context."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-005",
            objective="Test proposals",
        )

        proposal = SubagentProposal(
            action="New Action",
            rationale="Because reasons",
            priority="P1",
        )

        updated = manager.add_proposal("test", "build", "run-005", proposal)

        assert len(updated.proposals) == 1
        assert updated.proposals[0].action == "New Action"

    def test_record_subagent_action(self, manager):
        """Test recording sub-agent actions."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-006",
            objective="Test history",
        )

        updated = manager.record_subagent_action(
            project_id="test",
            family="build",
            run_id="run-006",
            agent_type="researcher",
            action="Analyzed codebase",
            output_file="research_codebase.md",
        )

        assert len(updated.subagent_history) == 1
        assert updated.subagent_history[0]["agent_type"] == "researcher"
        assert updated.subagent_history[0]["action"] == "Analyzed codebase"
        assert updated.subagent_history[0]["output_file"] == "research_codebase.md"

    def test_update_phase(self, manager):
        """Test updating the current phase."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-007",
            objective="Test phases",
        )

        updated = manager.update_phase(
            project_id="test",
            family="build",
            run_id="run-007",
            phase="implementation",
            gaps=["Still need tests"],
            blockers=["Waiting on API"],
        )

        assert updated.current_phase == "implementation"
        assert updated.gaps == ["Still need tests"]
        assert updated.blockers == ["Waiting on API"]

    def test_set_plan(self, manager):
        """Test setting the selected plan."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-008",
            objective="Test planning",
        )

        updated = manager.set_plan(
            project_id="test",
            family="build",
            run_id="run-008",
            plan="Step 1: Do this\nStep 2: Do that",
            rationale="Most efficient approach",
        )

        assert "Step 1" in updated.selected_plan
        assert updated.plan_rationale == "Most efficient approach"

    def test_add_artifact(self, manager):
        """Test adding artifact paths."""
        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-009",
            objective="Test artifacts",
        )

        updated = manager.add_artifact(
            project_id="test",
            family="build",
            run_id="run-009",
            name="Research Output",
            path="handoff/research_analysis.md",
        )

        assert "Research Output" in updated.artifact_paths
        assert updated.artifact_paths["Research Output"] == "handoff/research_analysis.md"

    def test_exists(self, manager):
        """Test checking if context exists."""
        assert not manager.exists("test", "build", "run-010")

        manager.create_context(
            project_id="test",
            family="build",
            run_id="run-010",
            objective="Test existence",
        )

        assert manager.exists("test", "build", "run-010")

    def test_custom_constraints_merged(self, manager):
        """Test that custom constraints are merged with defaults."""
        context = manager.create_context(
            project_id="test",
            family="build",
            run_id="run-011",
            objective="Test constraints",
            constraints=["Custom constraint 1", "Custom constraint 2"],
        )

        # Should have both default and custom constraints
        assert len(context.constraints) >= 7  # 5 default + 2 custom
        assert "Custom constraint 1" in context.constraints
        assert any("DO NOT execute" in c for c in context.constraints)
