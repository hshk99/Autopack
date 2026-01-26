"""Tests for prompt improver."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from feedback.prompt_improver import PromptEnhancement, PromptImprover


@pytest.fixture
def mock_failure_analyzer():
    """Create a mock FailureAnalyzer instance."""
    return MagicMock()


@pytest.fixture
def mock_metrics_db():
    """Create a mock MetricsDatabase instance."""
    return MagicMock()


@pytest.fixture
def improver(mock_failure_analyzer, mock_metrics_db):
    """Create a PromptImprover instance with mock components."""
    return PromptImprover(
        failure_analyzer=mock_failure_analyzer,
        metrics_db=mock_metrics_db,
    )


class TestPromptEnhancement:
    """Tests for PromptEnhancement dataclass."""

    def test_enhancement_creation_minimal(self):
        """Test that enhancement can be created with required fields."""
        enhancement = PromptEnhancement(
            category="warning",
            content="Test warning",
            priority="high",
            source="test_source",
        )

        assert enhancement.category == "warning"
        assert enhancement.content == "Test warning"
        assert enhancement.priority == "high"
        assert enhancement.source == "test_source"
        assert enhancement.created_at is not None

    def test_enhancement_categories(self):
        """Test different enhancement categories."""
        categories = ["warning", "pattern", "context", "checklist"]

        for category in categories:
            enhancement = PromptEnhancement(
                category=category,
                content=f"Test {category}",
                priority="medium",
                source="test",
            )
            assert enhancement.category == category

    def test_enhancement_priorities(self):
        """Test different enhancement priorities."""
        priorities = ["high", "medium", "low"]

        for priority in priorities:
            enhancement = PromptEnhancement(
                category="warning",
                content="Test",
                priority=priority,
                source="test",
            )
            assert enhancement.priority == priority


class TestPromptImprover:
    """Tests for PromptImprover class."""

    def test_init_stores_components(self, improver, mock_failure_analyzer, mock_metrics_db):
        """Test that initialization stores component references."""
        assert improver.failure_analyzer is mock_failure_analyzer
        assert improver.metrics_db is mock_metrics_db
        assert improver.template_path is None
        assert improver.base_prompts == {}

    def test_init_without_components(self):
        """Test that improver can be created without components."""
        improver = PromptImprover()

        assert improver.failure_analyzer is None
        assert improver.metrics_db is None
        assert improver.template_path is None

    def test_init_with_template_path(self):
        """Test initialization with template path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "templates.md"
            template_path.write_text(
                "## Template: tel\n```\nTelemetry template\n```\n"
                "## Template: mem\n```\nMemory template\n```\n"
            )

            improver = PromptImprover(prompt_template_path=str(template_path))

            assert improver.template_path == template_path
            assert "tel" in improver.base_prompts
            assert "mem" in improver.base_prompts

    def test_init_with_nonexistent_template_path(self):
        """Test initialization with nonexistent template path."""
        improver = PromptImprover(prompt_template_path="/nonexistent/path.md")

        assert improver.base_prompts == {}


class TestLoadTemplates:
    """Tests for template loading."""

    def test_load_templates_parses_correctly(self):
        """Test that templates are parsed correctly from markdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "templates.md"
            template_path.write_text(
                "# Templates\n\n"
                "## Template: tel\n```\nImplement telemetry logging\n```\n\n"
                "## Template: gen\n```\nGenerate implementation\n```\n"
            )

            improver = PromptImprover(prompt_template_path=str(template_path))

            assert len(improver.base_prompts) == 2
            assert "Implement telemetry logging" in improver.base_prompts["tel"]
            assert "Generate implementation" in improver.base_prompts["gen"]

    def test_load_templates_handles_empty_file(self):
        """Test that empty template file is handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "templates.md"
            template_path.write_text("")

            improver = PromptImprover(prompt_template_path=str(template_path))

            assert improver.base_prompts == {}


class TestGetImprovedPrompt:
    """Tests for get_improved_prompt method."""

    def test_get_improved_prompt_uses_base_template(self):
        """Test that improved prompt uses base template when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "templates.md"
            template_path.write_text("## Template: tel\n```\nBase telemetry prompt\n```\n")

            improver = PromptImprover(prompt_template_path=str(template_path))
            result = improver.get_improved_prompt("tel001", "tel", {})

            assert "Base telemetry prompt" in result

    def test_get_improved_prompt_uses_context_original(self):
        """Test that improved prompt falls back to context original prompt."""
        improver = PromptImprover()
        context = {"original_prompt": "Original prompt from context"}

        result = improver.get_improved_prompt("tel001", "tel", context)

        assert "Original prompt from context" in result

    def test_get_improved_prompt_caches_enhancements(self, improver):
        """Test that enhancements are cached for phase."""
        improver.failure_analyzer.get_failure_statistics.return_value = {"top_patterns": []}
        improver.metrics_db.get_phase_outcomes.return_value = []

        improver.get_improved_prompt("tel001", "tel", {"original_prompt": "Test"})

        assert "tel001" in improver.enhancement_cache


class TestGetFailureWarnings:
    """Tests for failure warning generation."""

    def test_no_warnings_without_analyzer(self):
        """Test that no warnings are generated without failure analyzer."""
        improver = PromptImprover()
        warnings = improver._get_failure_warnings("tel001", "tel")

        assert warnings == []

    def test_warnings_for_recurring_failures(self, improver, mock_failure_analyzer):
        """Test that warnings are generated for recurring failures."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "lint_failure",
                    "occurrence_count": 3,
                    "resolution": None,
                }
            ]
        }

        warnings = improver._get_failure_warnings("tel001", "tel")

        assert len(warnings) == 1
        assert warnings[0].category == "warning"
        assert warnings[0].priority == "high"
        assert "lint_failure" in warnings[0].content
        assert "RECURRING ISSUE" in warnings[0].content

    def test_warnings_include_resolution_when_available(self, improver, mock_failure_analyzer):
        """Test that warnings include resolution when available."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "lint_failure",
                    "occurrence_count": 5,
                    "resolution": "Run pre-commit hooks",
                }
            ]
        }

        warnings = improver._get_failure_warnings("tel001", "tel")

        assert len(warnings) == 1
        assert "Run pre-commit hooks" in warnings[0].content

    def test_no_warnings_for_low_occurrence(self, improver, mock_failure_analyzer):
        """Test that no warnings for failures below threshold."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "lint_failure",
                    "occurrence_count": 1,  # Below threshold of 2
                    "resolution": None,
                }
            ]
        }

        warnings = improver._get_failure_warnings("tel001", "tel")

        assert warnings == []

    def test_warnings_for_phase_specific_failures(self, improver, mock_metrics_db):
        """Test that phase-specific failure warnings are included."""
        mock_metrics_db.get_phase_outcomes.return_value = [
            {
                "phase_id": "tel001",
                "outcome": "failed",
                "error_summary": "Import error in module",
            }
        ]
        improver.failure_analyzer.get_failure_statistics.return_value = {"top_patterns": []}

        warnings = improver._get_failure_warnings("tel001", "tel")

        assert len(warnings) == 1
        assert "Import error in module" in warnings[0].content


class TestGetSuccessPatterns:
    """Tests for success pattern extraction."""

    def test_no_patterns_without_metrics_db(self):
        """Test that no patterns are generated without metrics database."""
        improver = PromptImprover()
        patterns = improver._get_success_patterns("tel")

        assert patterns == []

    def test_patterns_from_successful_phases(self, improver, mock_metrics_db):
        """Test that patterns are generated from successful phases."""
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "tel001", "outcome": "success", "duration_seconds": 300},
            {"phase_id": "tel002", "outcome": "success", "duration_seconds": 360},
            {"phase_id": "tel003", "outcome": "success", "duration_seconds": 420},
        ]

        patterns = improver._get_success_patterns("tel")

        assert len(patterns) == 1
        assert patterns[0].category == "pattern"
        assert "minutes" in patterns[0].content

    def test_no_patterns_with_few_successes(self, improver, mock_metrics_db):
        """Test that no patterns with fewer than 3 successes."""
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "tel001", "outcome": "success", "duration_seconds": 300},
            {"phase_id": "tel002", "outcome": "success", "duration_seconds": 360},
        ]

        patterns = improver._get_success_patterns("tel")

        assert patterns == []


class TestGetContextualGuidance:
    """Tests for contextual guidance generation."""

    def test_guidance_for_tel_phase_type(self, improver):
        """Test that guidance is generated for telemetry phases."""
        guidance = improver._get_contextual_guidance("tel", {})

        assert len(guidance) == 2
        assert all(g.category == "context" for g in guidance)
        assert any("EventLogger" in g.content for g in guidance)
        assert any("file locking" in g.content for g in guidance)

    def test_guidance_for_mem_phase_type(self, improver):
        """Test that guidance is generated for memory phases."""
        guidance = improver._get_contextual_guidance("mem", {})

        assert len(guidance) == 2
        assert any("parameterized queries" in g.content for g in guidance)
        assert any("database connections" in g.content for g in guidance)

    def test_guidance_for_gen_phase_type(self, improver):
        """Test that guidance is generated for generation phases."""
        guidance = improver._get_contextual_guidance("gen", {})

        assert len(guidance) == 2
        assert any("dependency graph" in g.content for g in guidance)
        assert any("file paths" in g.content for g in guidance)

    def test_guidance_for_loop_phase_type(self, improver):
        """Test that guidance is generated for loop phases."""
        guidance = improver._get_contextual_guidance("loop", {})

        assert len(guidance) == 2
        assert any("rate limiting" in g.content for g in guidance)
        assert any("graceful handling" in g.content for g in guidance)

    def test_no_guidance_for_unknown_type(self, improver):
        """Test that no guidance for unknown phase types."""
        guidance = improver._get_contextual_guidance("unknown", {})

        assert guidance == []

    def test_guidance_handles_empty_phase_type(self, improver):
        """Test that empty phase type is handled."""
        guidance = improver._get_contextual_guidance("", {})

        assert guidance == []


class TestExtractPhaseType:
    """Tests for phase type extraction."""

    def test_extract_from_standard_id(self, improver):
        """Test extraction from standard phase ID."""
        assert improver._extract_phase_type("tel001") == "tel"
        assert improver._extract_phase_type("mem002") == "mem"
        assert improver._extract_phase_type("gen003") == "gen"
        assert improver._extract_phase_type("loop001") == "loop"

    def test_extract_handles_uppercase(self, improver):
        """Test extraction handles uppercase IDs."""
        assert improver._extract_phase_type("TEL001") == "tel"
        assert improver._extract_phase_type("MEM002") == "mem"

    def test_extract_handles_empty_string(self, improver):
        """Test extraction handles empty string."""
        assert improver._extract_phase_type("") == ""

    def test_extract_handles_numeric_only(self, improver):
        """Test extraction handles numeric-only string."""
        assert improver._extract_phase_type("12345") == ""


class TestComposePrompt:
    """Tests for prompt composition."""

    def test_compose_with_no_enhancements(self, improver):
        """Test composition with no enhancements."""
        result = improver._compose_prompt("Base prompt", [], {})

        assert result == "Base prompt"

    def test_compose_with_warnings(self, improver):
        """Test composition includes warnings section."""
        warnings = [
            PromptEnhancement("warning", "Warning 1", "high", "test"),
            PromptEnhancement("warning", "Warning 2", "high", "test"),
        ]

        result = improver._compose_prompt("Base prompt", warnings, {})

        assert "IMPORTANT WARNINGS" in result
        assert "Warning 1" in result
        assert "Warning 2" in result
        assert "Base prompt" in result

    def test_compose_with_guidance(self, improver):
        """Test composition includes guidance section."""
        guidance = [
            PromptEnhancement("context", "Tip 1", "medium", "test"),
            PromptEnhancement("context", "Tip 2", "medium", "test"),
        ]

        result = improver._compose_prompt("Base prompt", guidance, {})

        assert "Guidance" in result
        assert "Tip 1" in result
        assert "Tip 2" in result

    def test_compose_with_patterns(self, improver):
        """Test composition includes patterns section."""
        patterns = [
            PromptEnhancement("pattern", "Pattern 1", "low", "test"),
        ]

        result = improver._compose_prompt("Base prompt", patterns, {})

        assert "Historical Context" in result
        assert "Pattern 1" in result

    def test_compose_sorts_by_priority(self, improver):
        """Test that enhancements are sorted by priority."""
        enhancements = [
            PromptEnhancement("warning", "Low priority", "low", "test"),
            PromptEnhancement("warning", "High priority", "high", "test"),
            PromptEnhancement("warning", "Medium priority", "medium", "test"),
        ]

        result = improver._compose_prompt("Base prompt", enhancements, {})

        # High priority should appear before medium and low
        high_idx = result.index("High priority")
        medium_idx = result.index("Medium priority")
        low_idx = result.index("Low priority")

        assert high_idx < medium_idx < low_idx


class TestRecordPromptOutcome:
    """Tests for outcome recording."""

    def test_record_outcome_without_metrics_db(self):
        """Test that recording without metrics db does nothing."""
        improver = PromptImprover()

        # Should not raise
        improver.record_prompt_outcome("tel001", "hash123", "success")

    def test_record_outcome_calls_metrics_db(self, improver, mock_metrics_db):
        """Test that outcome is recorded in metrics database."""
        improver.enhancement_cache["tel001"] = [
            PromptEnhancement("warning", "Test", "high", "test")
        ]

        improver.record_prompt_outcome("tel001", "hash123", "success", "Good result")

        mock_metrics_db.record_phase_outcome.assert_called_once()
        call_args = mock_metrics_db.record_phase_outcome.call_args
        assert call_args[1]["phase_id"] == "tel001"
        assert call_args[1]["outcome"] == "success"
        assert call_args[1]["metadata"]["prompt_hash"] == "hash123"
        assert call_args[1]["metadata"]["feedback"] == "Good result"
        assert call_args[1]["metadata"]["enhancements_applied"] == 1


class TestGetEnhancementSummary:
    """Tests for enhancement summary."""

    def test_summary_with_no_enhancements(self, improver):
        """Test summary when no enhancements applied."""
        summary = improver.get_enhancement_summary("tel001")

        assert "No enhancements applied" in summary

    def test_summary_with_enhancements(self, improver):
        """Test summary with enhancements."""
        improver.enhancement_cache["tel001"] = [
            PromptEnhancement("warning", "Warning about lint", "high", "test"),
            PromptEnhancement("context", "Tip about formatting", "medium", "test"),
        ]

        summary = improver.get_enhancement_summary("tel001")

        assert "tel001" in summary
        assert "[high]" in summary
        assert "[medium]" in summary
        assert "warning" in summary
        assert "context" in summary


class TestExportState:
    """Tests for state export."""

    def test_export_state_creates_file(self, improver):
        """Test that export_state creates a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "state.json"
            improver.export_state(str(output_path))

            assert output_path.exists()

    def test_export_state_content(self, improver):
        """Test that exported state contains expected fields."""
        improver.base_prompts = {"tel": "Template 1", "mem": "Template 2"}
        improver.enhancement_cache = {
            "tel001": [PromptEnhancement("warning", "Test", "high", "test")]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "state.json"
            improver.export_state(str(output_path))

            with open(output_path) as f:
                state = json.load(f)

            assert state["templates_loaded"] == 2
            assert state["enhancement_cache_size"] == 1
            assert "tel" in state["template_types"]
            assert "mem" in state["template_types"]

    def test_export_state_creates_parent_dirs(self, improver):
        """Test that export_state creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "state.json"
            improver.export_state(str(output_path))

            assert output_path.exists()
