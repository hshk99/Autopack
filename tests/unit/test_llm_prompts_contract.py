"""Contract tests for llm/prompts.py module.

These tests verify the prompt builder's public API and output format.
"""

from __future__ import annotations



class TestPromptConfig:
    """Tests for PromptConfig dataclass."""

    def test_default_config_values(self):
        """PromptConfig has sensible defaults."""
        from autopack.llm.prompts import PromptConfig

        config = PromptConfig()
        assert config.use_full_file_mode is True
        assert config.use_structured_edit is False
        assert config.use_ndjson_format is False
        assert config.max_lines_hard_limit == 1000
        assert config.context_budget_tokens == 120000

    def test_config_custom_values(self):
        """PromptConfig accepts custom values."""
        from autopack.llm.prompts import PromptConfig

        config = PromptConfig(
            use_full_file_mode=False,
            use_structured_edit=True,
            use_ndjson_format=False,
            max_lines_hard_limit=500,
            context_budget_tokens=80000,
        )
        assert config.use_full_file_mode is False
        assert config.use_structured_edit is True
        assert config.max_lines_hard_limit == 500
        assert config.context_budget_tokens == 80000


class TestPromptParts:
    """Tests for PromptParts dataclass."""

    def test_prompt_parts_attributes(self):
        """PromptParts stores system and user prompts."""
        from autopack.llm.prompts import PromptParts

        parts = PromptParts(
            system="System prompt",
            user="User prompt",
            estimated_tokens=1000,
        )
        assert parts.system == "System prompt"
        assert parts.user == "User prompt"
        assert parts.estimated_tokens == 1000

    def test_prompt_parts_optional_tokens(self):
        """PromptParts estimated_tokens is optional."""
        from autopack.llm.prompts import PromptParts

        parts = PromptParts(system="System", user="User")
        assert parts.estimated_tokens is None


class TestPromptBuilder:
    """Tests for PromptBuilder class."""

    def test_build_returns_prompt_parts(self):
        """build() returns PromptParts with system and user prompts."""
        from autopack.llm.prompts import PromptBuilder, PromptParts

        builder = PromptBuilder()
        phase_spec = {
            "description": "Add tests for the module",
            "task_category": "testing",
            "complexity": "medium",
        }

        result = builder.build(phase_spec=phase_spec)

        assert isinstance(result, PromptParts)
        assert isinstance(result.system, str)
        assert isinstance(result.user, str)
        assert len(result.system) > 0
        assert len(result.user) > 0

    def test_build_includes_phase_description(self):
        """User prompt includes phase description."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Add authentication middleware"}

        result = builder.build(phase_spec=phase_spec)

        assert "Add authentication middleware" in result.user

    def test_build_includes_category(self):
        """User prompt includes task category."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "task_category": "backend",
        }

        result = builder.build(phase_spec=phase_spec)

        assert "backend" in result.user

    def test_build_includes_complexity(self):
        """User prompt includes complexity level."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "complexity": "high",
        }

        result = builder.build(phase_spec=phase_spec)

        assert "high" in result.user


class TestSystemPromptModes:
    """Tests for different system prompt modes."""

    def test_full_file_mode_prompt(self):
        """Full-file mode includes JSON structure instructions."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()

        prompt = builder.build_system_prompt(
            use_full_file_mode=True,
            phase_spec={"description": "Test"},
        )

        assert "files" in prompt.lower()
        assert "json" in prompt.lower()
        assert "new_content" in prompt.lower()

    def test_structured_edit_mode_prompt(self):
        """Structured edit mode includes operation types."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()

        prompt = builder.build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=True,
            phase_spec={"description": "Test"},
        )

        assert "insert" in prompt.lower()
        assert "replace" in prompt.lower()
        assert "delete" in prompt.lower()
        assert "operations" in prompt.lower()

    def test_ndjson_mode_prompt(self):
        """NDJSON mode includes truncation-tolerant format info."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()

        prompt = builder.build_system_prompt(
            use_full_file_mode=False,
            use_ndjson_format=True,
            phase_spec={"description": "Test"},
        )

        assert "ndjson" in prompt.lower()
        assert "truncation" in prompt.lower()

    def test_diff_mode_prompt(self):
        """Diff mode includes git diff format instructions."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()

        prompt = builder.build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=False,
            use_ndjson_format=False,
            phase_spec={"description": "Test"},
        )

        assert "diff" in prompt.lower()
        assert "@@" in prompt or "hunk" in prompt.lower()

    def test_minimal_prompt_for_simple_phases(self):
        """Simple phases get minimal system prompt."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()

        # Simple phase configuration
        phase_spec = {
            "description": "Add a simple function",
            "complexity": "low",
            "task_category": "feature",
        }

        prompt = builder.build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        # Minimal prompt should be shorter
        # (exact length depends on implementation, just verify it builds)
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestProtectedPathsGuidance:
    """Tests for protected paths isolation guidance."""

    def test_no_protected_paths(self):
        """No guidance when no protected paths."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}

        prompt = builder.build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        assert "PROTECTED" not in prompt

    def test_with_protected_paths(self):
        """Includes guidance when protected paths present."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "protected_paths": ["src/core/", "src/embeddings/"],
        }

        prompt = builder.build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        assert "PROTECTED" in prompt
        assert "src/core/" in prompt
        assert "src/embeddings/" in prompt


class TestAcceptanceCriteria:
    """Tests for acceptance criteria section."""

    def test_custom_acceptance_criteria(self):
        """User prompt includes custom acceptance criteria."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "acceptance_criteria": [
                "Must handle edge cases",
                "Must include tests",
            ],
        }

        result = builder.build(phase_spec=phase_spec)

        assert "Must handle edge cases" in result.user
        assert "Must include tests" in result.user

    def test_universal_acceptance_criteria(self):
        """User prompt includes universal criteria when none specified."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}

        result = builder.build(phase_spec=phase_spec)

        assert "Acceptance Criteria" in result.user
        assert "COMPLETE" in result.user


class TestScopeConstraints:
    """Tests for scope constraints section."""

    def test_scope_paths_included(self):
        """User prompt includes allowed scope paths."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "scope": {
                "paths": ["src/module.py", "tests/test_module.py"],
            },
        }

        result = builder.build(phase_spec=phase_spec)

        assert "src/module.py" in result.user
        assert "tests/test_module.py" in result.user
        assert "ONLY modify" in result.user

    def test_directory_prefix_paths(self):
        """Directory prefixes are labeled correctly."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "scope": {
                "paths": ["src/components/"],
            },
        }

        result = builder.build(phase_spec=phase_spec)

        assert "src/components/" in result.user
        assert "directory prefix" in result.user

    def test_readonly_context(self):
        """User prompt includes read-only context entries."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "scope": {
                "paths": ["src/module.py"],
                "read_only_context": ["src/utils.py"],
            },
        }

        result = builder.build(phase_spec=phase_spec)

        assert "src/utils.py" in result.user
        assert "Read-only" in result.user or "read-only" in result.user


class TestDeliverablesContract:
    """Tests for deliverables contract section."""

    def test_deliverables_from_phase_spec(self):
        """User prompt includes deliverables from phase spec."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "deliverables": ["src/new_module.py", "tests/test_new_module.py"],
        }

        result = builder.build(phase_spec=phase_spec)

        assert "src/new_module.py" in result.user
        assert "tests/test_new_module.py" in result.user
        assert "REQUIRED DELIVERABLES" in result.user

    def test_deliverables_from_scope(self):
        """User prompt includes deliverables from scope config."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {
            "description": "Test",
            "scope": {
                "deliverables": ["src/feature.py"],
            },
        }

        result = builder.build(phase_spec=phase_spec)

        assert "src/feature.py" in result.user


class TestRulesAndHints:
    """Tests for learned rules and hints sections."""

    def test_project_rules_dict_format(self):
        """User prompt includes project rules (dict format)."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        project_rules = [
            {"rule_text": "Always use type hints"},
            {"constraint": "No print statements in production"},
        ]

        result = builder.build(
            phase_spec=phase_spec,
            project_rules=project_rules,
        )

        assert "Always use type hints" in result.user
        assert "No print statements" in result.user

    def test_run_hints_dict_format(self):
        """User prompt includes run hints (dict format)."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        run_hints = [
            {"hint_text": "Use the existing auth middleware"},
        ]

        result = builder.build(
            phase_spec=phase_spec,
            run_hints=run_hints,
        )

        assert "Use the existing auth middleware" in result.user

    def test_rules_capped_at_10(self):
        """Project rules are capped at 10."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        project_rules = [{"rule_text": f"Rule {i}"} for i in range(15)]

        result = builder.build(
            phase_spec=phase_spec,
            project_rules=project_rules,
        )

        # Should have Rule 0 through Rule 9
        assert "Rule 0" in result.user
        assert "Rule 9" in result.user
        # Should not have Rule 10+
        assert "Rule 10" not in result.user


class TestFileContext:
    """Tests for file context section."""

    def test_file_context_modifiable_files(self):
        """User prompt includes modifiable files with content."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        file_context = {
            "existing_files": {
                "src/module.py": "def hello():\n    pass\n",
            },
            "scope_metadata": {
                "src/module.py": {"category": "modifiable"},
            },
        }

        result = builder.build(
            phase_spec=phase_spec,
            file_context=file_context,
        )

        assert "src/module.py" in result.user
        assert "def hello():" in result.user

    def test_file_context_readonly_files(self):
        """User prompt marks read-only files appropriately."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        file_context = {
            "existing_files": {
                "src/utils.py": "# Utility module\n" * 100,
            },
            "scope_metadata": {
                "src/utils.py": {"category": "read_only"},
            },
        }

        result = builder.build(
            phase_spec=phase_spec,
            file_context=file_context,
        )

        assert "READ-ONLY" in result.user or "read-only" in result.user

    def test_missing_scope_files(self):
        """User prompt includes missing scope files."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}
        file_context = {
            "existing_files": {},
            "missing_scope_files": ["src/new_file.py"],
        }

        result = builder.build(
            phase_spec=phase_spec,
            file_context=file_context,
        )

        assert "src/new_file.py" in result.user
        assert "Missing" in result.user or "missing" in result.user


class TestRetrievedContext:
    """Tests for retrieved context section."""

    def test_retrieved_context_included(self):
        """User prompt includes retrieved context when provided."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}

        result = builder.build(
            phase_spec=phase_spec,
            retrieved_context="Previous implementation used a factory pattern.",
        )

        assert "Retrieved Context" in result.user
        assert "factory pattern" in result.user

    def test_no_retrieved_context(self):
        """User prompt omits section when no retrieved context."""
        from autopack.llm.prompts import PromptBuilder

        builder = PromptBuilder()
        phase_spec = {"description": "Test"}

        result = builder.build(
            phase_spec=phase_spec,
            retrieved_context=None,
        )

        assert "Retrieved Context" not in result.user
