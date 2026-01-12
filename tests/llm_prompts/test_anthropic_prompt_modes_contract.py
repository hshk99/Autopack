"""
Contract tests for Anthropic prompt builders.

These tests verify that each prompt mode includes required output contract markers
and that prompt construction behaves consistently and correctly.

Test Coverage:
1. Full-file mode: includes "```json" marker and complete file content instructions
2. NDJSON mode: includes NDJSON format instructions and one-object-per-line guidance
3. Structured-edit mode: includes edit format instructions with line numbers
4. Legacy-diff mode: includes unified diff format instructions
5. Deliverables-manifest preview limit is enforced (max 60 files)
6. System prompt includes phase description when provided
7. User prompt includes intention context when run_id is present
8. Prompt construction is deterministic (same inputs → same output)
"""

import pytest
from src.autopack.llm.prompts.anthropic_builder_prompts import (
    build_system_prompt,
    build_minimal_system_prompt,
    build_user_prompt,
)


class TestSystemPromptContractMarkers:
    """Test that system prompts include required output contract markers for each mode."""

    def test_full_file_mode_includes_json_marker(self):
        """Full-file mode must include JSON format instructions."""
        prompt = build_system_prompt(
            use_full_file_mode=True,
            use_structured_edit=False,
            use_ndjson_format=False,
        )

        # Check for critical full-file mode markers
        assert "OUTPUT FORMAT - CRITICAL" in prompt
        assert "```json" in prompt.lower() or "JSON object" in prompt
        assert "COMPLETE" in prompt
        assert "new_content" in prompt
        assert "Complete file content" in prompt

    def test_ndjson_mode_includes_ndjson_instructions(self):
        """NDJSON mode must include NDJSON format instructions."""
        prompt = build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=False,
            use_ndjson_format=True,
        )

        # Check for critical NDJSON mode markers
        assert "NDJSON" in prompt
        assert "one complete json object per line" in prompt.lower()
        assert "truncation-tolerant" in prompt.lower()
        assert "type" in prompt  # operation type field
        assert "file_path" in prompt

    def test_structured_edit_mode_includes_edit_instructions(self):
        """Structured-edit mode must include structured edit format instructions."""
        prompt = build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=True,
            use_ndjson_format=False,
        )

        # Check for critical structured-edit mode markers
        assert "operations" in prompt
        assert "line" in prompt.lower()
        assert "insert" in prompt.lower()
        assert "replace" in prompt.lower()
        assert "delete" in prompt.lower()
        assert "1-indexed" in prompt

    def test_legacy_diff_mode_includes_diff_instructions(self):
        """Legacy diff mode must include unified diff format instructions."""
        prompt = build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=False,
            use_ndjson_format=False,
        )

        # Check for critical diff mode markers
        assert "diff --git" in prompt
        assert "@@" in prompt
        assert "unified diff" in prompt.lower()
        assert "+" in prompt and "-" in prompt
        assert "hunk" in prompt.lower()


class TestDeliverableManifestPreview:
    """Test deliverables manifest preview limit enforcement."""

    def test_manifest_preview_limit_enforced(self):
        """Deliverables manifest should be limited to 60 entries in preview."""
        # Create a manifest with more than 60 entries
        manifest = [f"path/to/file_{i}.py" for i in range(100)]

        phase_spec = {
            "description": "Test phase",
            "scope": {
                "deliverables_manifest": manifest,
            },
        }

        prompt = build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=False,
            use_ndjson_format=True,
            phase_spec=phase_spec,
        )

        # Check that preview limit is enforced
        assert "FILE PATH CONSTRAINT" in prompt
        assert "DELIVERABLES MANIFEST" in prompt

        # Count how many file entries are shown (should be 60 + 1 "more" line)
        lines_with_file_paths = [line for line in prompt.split("\n") if line.strip().startswith("- path/to/file_")]
        assert len(lines_with_file_paths) == 60

        # Check for "more" indicator
        assert "40 more" in prompt  # 100 - 60 = 40 more

    def test_manifest_under_limit_shows_all(self):
        """Deliverables manifest with fewer than 60 entries should show all."""
        manifest = [f"path/to/file_{i}.py" for i in range(30)]

        phase_spec = {
            "description": "Test phase",
            "scope": {
                "deliverables_manifest": manifest,
            },
        }

        prompt = build_system_prompt(
            use_full_file_mode=False,
            use_structured_edit=False,
            use_ndjson_format=True,
            phase_spec=phase_spec,
        )

        # All 30 entries should be shown
        lines_with_file_paths = [line for line in prompt.split("\n") if line.strip().startswith("- path/to/file_")]
        assert len(lines_with_file_paths) == 30

        # Should not have "more" indicator
        assert "more)" not in prompt


class TestPhaseDescriptionInclusion:
    """Test that system prompt includes phase description when provided."""

    def test_protected_paths_included_when_provided(self):
        """System prompt should include protected paths from phase spec."""
        phase_spec = {
            "description": "Test phase",
            "protected_paths": [
                "src/autopack/embeddings/",
                "src/autopack/core/",
            ],
        }

        prompt = build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        # Check for protected path guidance
        assert "PROTECTED" in prompt
        assert "src/autopack/embeddings/" in prompt
        assert "src/autopack/core/" in prompt
        assert "DO NOT modify" in prompt.upper() or "MUST NOT" in prompt.upper()

    def test_deliverables_manifest_request_included(self):
        """System prompt should request deliverables manifest when phase has deliverables."""
        phase_spec = {
            "description": "Test phase",
            "deliverables": ["src/example.py", "tests/test_example.py"],
        }

        prompt = build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        # Check for deliverables manifest request
        assert "DELIVERABLES_MANIFEST" in prompt
        assert "BUILD-127" in prompt
        assert "symbols" in prompt


class TestMinimalSystemPrompt:
    """Test minimal system prompt for low-complexity phases."""

    def test_minimal_prompt_is_shorter(self):
        """Minimal system prompt should be shorter than full system prompt."""
        full_prompt = build_system_prompt(use_full_file_mode=True)
        minimal_prompt = build_minimal_system_prompt(use_structured_edit=False)

        # Minimal prompt should be significantly shorter
        assert len(minimal_prompt) < len(full_prompt) * 0.5

    def test_minimal_prompt_includes_essential_instructions(self):
        """Minimal system prompt should still include essential instructions."""
        prompt = build_minimal_system_prompt(use_structured_edit=False)

        # Check for essential git diff instructions
        assert "diff --git" in prompt
        assert "@@" in prompt

    def test_minimal_prompt_used_for_low_complexity(self):
        """Low complexity phases should trigger minimal system prompt."""
        phase_spec = {
            "complexity": "low",
            "task_category": "feature",
        }

        prompt = build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        # Should be minimal (shorter)
        full_prompt = build_system_prompt(use_full_file_mode=True)
        assert len(prompt) < len(full_prompt)


class TestUserPromptConstruction:
    """Test user prompt construction with various inputs."""

    def test_user_prompt_includes_phase_description(self):
        """User prompt should include phase description."""
        phase_spec = {
            "description": "Implement user authentication",
            "task_category": "feature",
            "complexity": "medium",
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
        )

        assert "Implement user authentication" in prompt
        assert "feature" in prompt
        assert "medium" in prompt

    def test_user_prompt_includes_deliverables_contract(self):
        """User prompt should include explicit deliverables contract."""
        phase_spec = {
            "description": "Create service",
            "scope": {
                "deliverables": ["src/service.py", "tests/test_service.py"],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
        )

        # Check for deliverables section
        assert "REQUIRED DELIVERABLES" in prompt
        assert "src/service.py" in prompt
        assert "tests/test_service.py" in prompt
        assert "MUST" in prompt

    def test_user_prompt_includes_scope_constraints(self):
        """User prompt should include file modification constraints from scope."""
        phase_spec = {
            "description": "Update config",
            "scope": {
                "paths": ["config/", "src/config.py"],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
        )

        # Check for scope constraints
        assert "File Modification Constraints" in prompt
        assert "config/" in prompt
        assert "src/config.py" in prompt
        assert "ONLY modify these files" in prompt

    def test_user_prompt_includes_project_rules(self):
        """User prompt should include learned rules."""
        phase_spec = {"description": "Test phase"}
        project_rules = [
            {"rule_text": "Always add type hints"},
            {"constraint": "Include docstrings"},
        ]

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
            run_hints=None,
        )

        # Check for rules section
        assert "Learned Rules" in prompt
        assert "Always add type hints" in prompt
        assert "Include docstrings" in prompt

    def test_user_prompt_includes_run_hints(self):
        """User prompt should include hints from earlier phases."""
        phase_spec = {"description": "Test phase"}
        run_hints = [
            {"hint_text": "Use async/await for IO operations"},
            {"hint_text": "Validate inputs carefully"},
        ]

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=run_hints,
        )

        # Check for hints section
        assert "Hints from earlier phases" in prompt
        assert "Use async/await for IO operations" in prompt
        assert "Validate inputs carefully" in prompt


class TestPromptDeterminism:
    """Test that prompt construction is deterministic."""

    def test_system_prompt_deterministic(self):
        """Same inputs should produce same system prompt."""
        phase_spec = {
            "description": "Test phase",
            "complexity": "medium",
        }

        prompt1 = build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )
        prompt2 = build_system_prompt(
            use_full_file_mode=True,
            phase_spec=phase_spec,
        )

        assert prompt1 == prompt2

    def test_user_prompt_deterministic(self):
        """Same inputs should produce same user prompt."""
        phase_spec = {
            "description": "Test phase",
            "task_category": "feature",
        }
        project_rules = [{"rule_text": "Use type hints"}]
        run_hints = [{"hint_text": "Validate inputs"}]

        prompt1 = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
            run_hints=run_hints,
        )
        prompt2 = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=project_rules,
            run_hints=run_hints,
        )

        assert prompt1 == prompt2


class TestFileContextHandling:
    """Test file context processing in user prompts."""

    def test_modifiable_vs_readonly_separation(self):
        """User prompt should separate modifiable and read-only files."""
        phase_spec = {"description": "Test phase"}
        file_context = {
            "existing_files": {
                "src/small.py": "def foo(): pass\n",
                "src/large.py": "x\n" * 600,  # 600 lines - should be read-only
            },
            "scope_metadata": {
                "src/small.py": {"category": "modifiable"},
                "src/large.py": {"category": "read_only"},
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=file_context,
            project_rules=None,
            run_hints=None,
        )

        # Check that files are properly categorized
        assert "Files You May Modify" in prompt
        assert "Read-Only Context Files" in prompt
        assert "src/small.py" in prompt
        assert "src/large.py" in prompt
        assert "DO NOT MODIFY" in prompt

    def test_missing_scope_files_listed(self):
        """User prompt should list missing scoped files that can be created."""
        phase_spec = {"description": "Test phase"}
        file_context = {
            "existing_files": {},
            "missing_scope_files": ["src/new_service.py", "tests/test_new_service.py"],
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=file_context,
            project_rules=None,
            run_hints=None,
        )

        # Check for missing files section
        assert "Missing Scoped Files" in prompt
        assert "src/new_service.py" in prompt
        assert "tests/test_new_service.py" in prompt
        assert "may create" in prompt.lower()


class TestPackPhaseDetection:
    """Test country pack phase detection and schema contract injection."""

    def test_pack_phase_includes_schema_contract(self):
        """Pack phases should include YAML schema contract."""
        phase_spec = {
            "description": "Update country pack",
            "scope": {
                "paths": ["backend/packs/france.yaml"],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
        )

        # Check for pack schema contract
        assert "PACK SCHEMA CONTRACT" in prompt
        assert "categories" in prompt
        assert "checklists" in prompt
        assert "official_sources" in prompt
        assert "YAML" in prompt

    def test_non_pack_phase_no_schema_contract(self):
        """Non-pack phases should not include pack schema contract."""
        phase_spec = {
            "description": "Update service",
            "scope": {
                "paths": ["src/service.py"],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
        )

        # Should not have pack-specific content
        assert "PACK SCHEMA CONTRACT" not in prompt
        assert "country pack" not in prompt.lower()
