"""
Tests for sub-agent output contracts.

BUILD-197: Claude Code sub-agent glue work
"""

import json

import pytest

from autopack.subagent.output_contract import (
    ANALYSIS_CONTRACT,
    PLAN_CONTRACT,
    RESEARCH_CONTRACT,
    OutputContract,
    OutputType,
    SubagentOutput,
    SubagentOutputValidator,
    create_contract,
)


class TestOutputContract:
    """Tests for OutputContract dataclass."""

    def test_get_filename_research(self):
        """Test filename generation for research."""
        contract = OutputContract(
            output_type=OutputType.RESEARCH,
            topic="codebase analysis",
        )
        assert contract.get_filename() == "research_codebase_analysis.md"

    def test_get_filename_sanitizes_special_chars(self):
        """Test that special characters are sanitized in filename."""
        contract = OutputContract(
            output_type=OutputType.PLAN,
            topic="API/Integration (v2)",
        )
        filename = contract.get_filename()
        assert "/" not in filename
        assert "(" not in filename
        assert ")" not in filename
        assert filename.endswith(".md")

    def test_get_schema(self):
        """Test schema generation."""
        contract = OutputContract(
            output_type=OutputType.ANALYSIS,
            topic="performance",
            required_sections=["Scope", "Results"],
            optional_sections=["Methodology"],
            max_length_chars=30000,
            require_file_references=True,
            require_confidence_scores=True,
        )
        schema = contract.get_schema()

        assert schema["output_type"] == "analysis"
        assert schema["topic"] == "performance"
        assert schema["required_sections"] == ["Scope", "Results"]
        assert schema["max_length_chars"] == 30000
        assert schema["require_confidence_scores"] is True


class TestPredefinedContracts:
    """Tests for pre-defined contracts."""

    def test_research_contract_has_required_sections(self):
        """Test research contract has expected sections."""
        assert "Objective" in RESEARCH_CONTRACT.required_sections
        assert "Findings" in RESEARCH_CONTRACT.required_sections
        assert "Recommendations" in RESEARCH_CONTRACT.required_sections

    def test_plan_contract_has_required_sections(self):
        """Test plan contract has expected sections."""
        assert "Objective" in PLAN_CONTRACT.required_sections
        assert "Implementation Steps" in PLAN_CONTRACT.required_sections
        assert "Acceptance Criteria" in PLAN_CONTRACT.required_sections

    def test_analysis_contract_requires_confidence(self):
        """Test analysis contract requires confidence scores."""
        assert ANALYSIS_CONTRACT.require_confidence_scores is True


class TestSubagentOutput:
    """Tests for SubagentOutput dataclass."""

    def test_content_hash_computed_automatically(self):
        """Test that content hash is computed if not provided."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test Output",
            content="This is test content.",
        )

        assert output.content_hash is not None
        assert len(output.content_hash) == 64  # SHA-256

    def test_same_content_same_hash(self):
        """Test that same content produces same hash."""
        output1 = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="Same content",
        )
        output2 = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-002",
            title="Test",
            content="Same content",
        )

        assert output1.content_hash == output2.content_hash

    def test_get_filename(self):
        """Test filename generation."""
        output = SubagentOutput(
            output_type=OutputType.PLAN,
            topic="feature implementation",
            agent_type="planner",
            run_id="run-001",
            title="Feature Plan",
            content="Plan content",
        )

        assert output.get_filename() == "plan_feature_implementation.md"

    def test_to_markdown_includes_all_sections(self):
        """Test markdown output includes all required sections."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="codebase",
            agent_type="researcher",
            run_id="run-001",
            title="Codebase Research",
            content="## Findings\n\nFound interesting patterns.",
            file_references=["src/main.py", "src/utils.py"],
            findings_summary=["Pattern A is common", "Pattern B needs refactoring"],
            proposed_actions=["Refactor Pattern B", "Document Pattern A"],
            confidence_scores={"overall": 0.85, "pattern_detection": 0.9},
        )
        md = output.to_markdown()

        # Check headers
        assert "# Codebase Research" in md
        assert "**Type**: research" in md
        assert "**Agent**: researcher" in md

        # Check content
        assert "## Findings" in md
        assert "Found interesting patterns" in md

        # Check context update section
        assert "## Context Update Summary" in md
        assert "### What This Agent Did" in md
        assert "### Key Findings" in md
        assert "Pattern A is common" in md
        assert "### Proposed Next Actions" in md
        assert "Refactor Pattern B" in md
        assert "### File References" in md
        assert "`src/main.py`" in md
        assert "### Confidence Scores" in md
        assert "overall: 85%" in md

    def test_to_json_and_from_json_roundtrip(self):
        """Test JSON serialization roundtrip."""
        original = SubagentOutput(
            output_type=OutputType.ANALYSIS,
            topic="performance",
            agent_type="analyzer",
            run_id="run-002",
            title="Performance Analysis",
            content="Analysis content here",
            sections={"Scope": "All modules", "Results": "Good performance"},
            file_references=["src/slow.py"],
            findings_summary=["Bottleneck in slow.py"],
            proposed_actions=["Optimize slow.py"],
            confidence_scores={"bottleneck_detection": 0.95},
        )

        json_data = original.to_json()
        restored = SubagentOutput.from_json(json_data)

        assert restored.output_type == original.output_type
        assert restored.topic == original.topic
        assert restored.content == original.content
        assert restored.content_hash == original.content_hash
        assert restored.file_references == original.file_references
        assert restored.confidence_scores == original.confidence_scores


class TestSubagentOutputValidator:
    """Tests for SubagentOutputValidator."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return SubagentOutputValidator()

    def test_valid_output_passes(self, validator):
        """Test that valid output passes validation."""
        contract = create_contract(
            output_type=OutputType.RESEARCH,
            topic="test",
            required_sections=["Objective", "Findings"],
        )

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test Research",
            content="## Objective\n\nTest objective.\n\n## Findings\n\nTest findings.",
            file_references=["test.py"],
            findings_summary=["Found something"],
            proposed_actions=["Do something"],
        )

        result = validator.validate(output, contract)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_missing_required_section_fails(self, validator):
        """Test that missing required section causes failure."""
        contract = create_contract(
            output_type=OutputType.RESEARCH,
            topic="test",
            required_sections=["Objective", "Findings", "Conclusions"],
        )

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="## Objective\n\nObjective here.\n\n## Findings\n\nFindings here.",
            file_references=["test.py"],
        )

        result = validator.validate(output, contract)

        assert not result.is_valid
        assert "Conclusions" in result.missing_sections
        assert any("Conclusions" in e for e in result.errors)

    def test_output_type_mismatch_fails(self, validator):
        """Test that output type mismatch causes failure."""
        contract = create_contract(output_type=OutputType.PLAN, topic="test")

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,  # Wrong type
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="Content",
            file_references=["test.py"],
        )

        result = validator.validate(output, contract)

        assert not result.is_valid
        assert any("mismatch" in e.lower() for e in result.errors)

    def test_content_too_long_fails(self, validator):
        """Test that content exceeding max length fails."""
        contract = OutputContract(
            output_type=OutputType.RESEARCH,
            topic="test",
            max_length_chars=100,
        )

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="x" * 200,  # Exceeds limit
            file_references=["test.py"],
        )

        result = validator.validate(output, contract)

        assert not result.is_valid
        assert any("length" in e.lower() for e in result.errors)

    def test_missing_file_references_fails_when_required(self, validator):
        """Test that missing file references fails when required."""
        contract = OutputContract(
            output_type=OutputType.RESEARCH,
            topic="test",
            require_file_references=True,
        )

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="Content",
            file_references=[],  # Empty
        )

        result = validator.validate(output, contract)

        assert not result.is_valid
        assert any("file references" in e.lower() for e in result.errors)

    def test_missing_confidence_scores_fails_when_required(self, validator):
        """Test that missing confidence scores fails when required."""
        contract = OutputContract(
            output_type=OutputType.ANALYSIS,
            topic="test",
            require_confidence_scores=True,
        )

        output = SubagentOutput(
            output_type=OutputType.ANALYSIS,
            topic="test",
            agent_type="analyzer",
            run_id="run-001",
            title="Test",
            content="Content",
            file_references=["test.py"],
            confidence_scores={},  # Empty
        )

        result = validator.validate(output, contract)

        assert not result.is_valid
        assert any("confidence" in e.lower() for e in result.errors)

    def test_missing_findings_summary_warns(self, validator):
        """Test that missing findings summary generates warning."""
        contract = create_contract(output_type=OutputType.RESEARCH, topic="test")

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content="## Objective\nObj\n## Methodology\nMeth\n## Findings\nFind\n## Recommendations\nRec",
            file_references=["test.py"],
            findings_summary=[],  # Empty
            proposed_actions=["Action"],
        )

        result = validator.validate(output, contract)

        assert any("findings summary" in w.lower() for w in result.warnings)

    def test_save_output(self, validator, tmp_path):
        """Test saving validated output."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test Output",
            content="Test content",
            findings_summary=["Finding 1"],
            proposed_actions=["Action 1"],
        )

        handoff_dir = tmp_path / "handoff"
        md_path = validator.save_output(output, handoff_dir, update_context=False)

        assert md_path.exists()
        assert md_path.name == "research_test.md"

        # Check JSON backup exists
        json_path = handoff_dir / "research_test.md.json"
        assert json_path.exists()

    def test_save_output_updates_context(self, validator, tmp_path):
        """Test that save_output updates context.json."""
        # Create initial context
        handoff_dir = tmp_path / "handoff"
        handoff_dir.mkdir(parents=True)
        context_json = handoff_dir / "context.json"
        context_json.write_text(
            json.dumps(
                {
                    "run_id": "run-001",
                    "version": 1,
                    "updated_at": "2024-01-01T00:00:00",
                    "artifact_paths": {},
                    "subagent_history": [],
                }
            )
        )

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test Output",
            content="Test content",
        )

        validator.save_output(output, handoff_dir, update_context=True)

        # Check context was updated
        updated_context = json.loads(context_json.read_text())
        assert len(updated_context["subagent_history"]) == 1
        assert updated_context["subagent_history"][0]["agent_type"] == "researcher"
        assert "research_test" in updated_context["artifact_paths"]


class TestCreateContract:
    """Tests for create_contract factory function."""

    def test_creates_research_with_defaults(self):
        """Test creating research contract with defaults."""
        contract = create_contract(OutputType.RESEARCH, "test")

        assert contract.output_type == OutputType.RESEARCH
        assert "Objective" in contract.required_sections
        assert "Findings" in contract.required_sections

    def test_creates_plan_with_defaults(self):
        """Test creating plan contract with defaults."""
        contract = create_contract(OutputType.PLAN, "feature")

        assert contract.output_type == OutputType.PLAN
        assert "Implementation Steps" in contract.required_sections
        assert "Acceptance Criteria" in contract.required_sections

    def test_creates_analysis_with_defaults(self):
        """Test creating analysis contract with defaults."""
        contract = create_contract(OutputType.ANALYSIS, "performance")

        assert contract.output_type == OutputType.ANALYSIS
        assert "Results" in contract.required_sections
        assert "Conclusions" in contract.required_sections

    def test_custom_sections_override_defaults(self):
        """Test that custom sections override defaults."""
        contract = create_contract(
            OutputType.RESEARCH,
            "test",
            required_sections=["Custom Section 1", "Custom Section 2"],
        )

        assert contract.required_sections == ["Custom Section 1", "Custom Section 2"]
        assert "Objective" not in contract.required_sections
