"""
Regression tests for BUILD-141 Telemetry Unblock fixes (T1-T2).

Tests that:
1. _build_user_prompt() includes directory prefix semantics
2. _build_user_prompt() includes required deliverables contract
3. Executor retries "empty files array" errors exactly once

NOTE: Partially graduated - T1 prompt fixes implemented and passing (3 tests),
T2 retry logic still aspirational (3 tests have function-level xfail markers).
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path

# PARTIAL GRADUATION: Module-level xfail removed - T1 tests graduated (BUILD-146 Phase A P15)
# T2 tests still have function-level xfail markers below


class TestT1PromptFixes:
    """Test T1: Prompt ambiguity fixes in _build_user_prompt()"""

    def test_directory_prefix_annotation(self):
        """Test that paths ending with / are annotated as directory prefixes."""
        # Import the implementation function directly to avoid method override issue
        from autopack.llm.prompts.anthropic_builder_prompts import build_user_prompt

        phase_spec = {
            "description": "Create utility module",
            "task_category": "implementation",
            "complexity": "low",
            "scope": {
                "paths": [
                    "examples/telemetry_utils/",  # Directory prefix
                    "src/autopack/utils.py",  # Exact file
                ],
                "read_only_context": [],
                "deliverables": ["examples/telemetry_utils/string_helper.py"],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
            use_full_file_mode=True,
        )

        # Assert directory prefix is annotated
        assert (
            "examples/telemetry_utils/ (directory prefix - creating/modifying files under this path is ALLOWED)"
            in prompt
        )

        # Assert exact file path is NOT annotated (no trailing /)
        assert "src/autopack/utils.py (directory prefix" not in prompt

    def test_required_deliverables_section(self):
        """Test that REQUIRED DELIVERABLES section is added when deliverables exist."""
        # Import the implementation function directly to avoid method override issue
        from autopack.llm.prompts.anthropic_builder_prompts import build_user_prompt

        phase_spec = {
            "description": "Create utility module",
            "task_category": "implementation",
            "complexity": "low",
            "scope": {
                "paths": ["examples/telemetry_utils/"],
                "deliverables": [
                    "examples/telemetry_utils/string_helper.py",
                    "examples/telemetry_utils/number_helper.py",
                ],
            },
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
            use_full_file_mode=True,
        )

        # Assert REQUIRED DELIVERABLES section exists
        assert "## REQUIRED DELIVERABLES" in prompt
        assert "Your output MUST include at least these files:" in prompt

        # Assert deliverables are listed
        assert "examples/telemetry_utils/string_helper.py" in prompt
        assert "examples/telemetry_utils/number_helper.py" in prompt

        # Assert hard requirement is present
        assert "'files' array in your JSON output MUST contain at least one file" in prompt
        assert "Empty files array is NOT allowed" in prompt

    def test_no_deliverables_section_when_no_deliverables(self):
        """Test that REQUIRED DELIVERABLES section is NOT added when no deliverables."""
        # Import the implementation function directly to avoid method override issue
        from autopack.llm.prompts.anthropic_builder_prompts import build_user_prompt

        phase_spec = {
            "description": "Review code",
            "task_category": "review",
            "complexity": "low",
            "scope": {"paths": ["src/autopack/"], "deliverables": []},  # No deliverables
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
            use_full_file_mode=True,
        )

        # Assert REQUIRED DELIVERABLES section does NOT exist
        assert "## REQUIRED DELIVERABLES" not in prompt

    def test_deliverables_from_top_level(self):
        """Test that deliverables can be extracted from top-level phase_spec."""
        # Import the implementation function directly to avoid method override issue
        from autopack.llm.prompts.anthropic_builder_prompts import build_user_prompt

        phase_spec = {
            "description": "Create utility module",
            "task_category": "implementation",
            "complexity": "low",
            "deliverables": ["src/autopack/utils.py"],  # Top-level deliverables
            "scope": {"paths": ["src/autopack/"]},
        }

        prompt = build_user_prompt(
            phase_spec=phase_spec,
            file_context=None,
            project_rules=None,
            run_hints=None,
            use_full_file_mode=True,
        )

        # Assert REQUIRED DELIVERABLES section exists
        assert "## REQUIRED DELIVERABLES" in prompt
        assert "src/autopack/utils.py" in prompt


class TestT2EmptyFilesRetry:
    """Test T2: Targeted retry for empty files array errors"""

    @pytest.mark.xfail(reason="T2 retry logic not yet implemented - aspirational test")
    @patch("autopack.autonomous_executor.time.sleep")  # Mock sleep to speed up tests
    def test_empty_files_retry_once(self, mock_sleep):
        """Test that empty files array error triggers exactly ONE retry."""
        from autopack.autonomous_executor import AutonomousExecutor
        from autopack.llm_client import BuilderResult

        # Create executor with mocked dependencies
        with patch("autopack.autonomous_executor.SessionLocal"):
            executor = AutonomousExecutor(
                run_id="test-run",
                workspace=Path.cwd(),
                run_type="project_build",
                api_url="http://localhost:8000",
            )

        # Mock phase
        phase = {
            "phase_id": "test-phase",
            "description": "Test phase",
            "complexity": "low",
            "task_category": "implementation",
            "max_builder_attempts": 3,
            "scope": {"paths": ["test/"], "deliverables": ["test/file.py"]},
        }

        # Mock Builder result with "empty files array" error
        mock_builder_result = BuilderResult(
            success=False,
            patch_content="",
            builder_messages=["LLM returned empty files array"],
            tokens_used=100,
            model_used="claude-sonnet-4-5",
            error="LLM returned empty files array",
        )

        # Mock the LLM service
        executor.llm_service = Mock()
        executor.llm_service.execute_builder_phase = Mock(return_value=mock_builder_result)

        # Mock other dependencies
        executor._post_builder_result = Mock()
        executor._record_phase_error = Mock()

        # Attempt 1: Should detect empty files error and return EMPTY_FILES_RETRY
        success, reason = executor._run_builder_attempt(
            phase=phase,
            attempt_index=0,
            file_context={},
            project_rules=[],
            run_hints=[],
            use_full_file_mode=True,
        )

        assert success is False
        assert reason == "EMPTY_FILES_RETRY"
        assert phase.get("_empty_files_retry_count") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
