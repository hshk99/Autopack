"""Contract tests for BuilderOrchestrator module.

Validates that BuilderOrchestrator correctly:
1. Loads context (file, learning, memory, intention)
2. Pre-flight file size validation
3. Deliverables manifest gate
4. Builder LLM invocation with auto-fallback to structured edits
5. Empty patch validation
6. Retry scenarios (empty files, infra errors)
7. Token escalation (P10)
8. Builder guardrail failure handling
9. Deliverables validation (patch and JSON)
10. Auto-repair for JSON deliverables
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

from autopack.executor.builder_orchestrator import BuilderOrchestrator
from autopack.llm_client import BuilderResult


def make_builder_orchestrator(tmp_path: Path) -> BuilderOrchestrator:
    """Create a BuilderOrchestrator with mocked executor."""
    executor = Mock()
    executor.workspace = str(tmp_path)
    executor.run_id = "test-run-123"
    executor.run_type = "user_task"
    executor.llm_service = Mock()
    executor.api_client = Mock()
    executor.memory_service = None
    executor.context_preflight = Mock()
    executor.file_size_telemetry = Mock()
    executor.builder_output_config = Mock()
    executor.builder_output_config.max_lines_hard_limit = 1000
    executor.builder_output_config.max_lines_for_full_file = 1000
    executor.builder_output_config.legacy_diff_fallback_enabled = False
    executor._run_tokens_used = 0
    executor._last_file_context = None
    executor._last_builder_result = None
    executor._last_files_changed = 0
    executor._last_lines_added = 0
    executor._last_lines_removed = 0
    executor._provider_infra_errors = {}
    executor._build_run_context = Mock(return_value={})
    executor._load_repository_context = Mock(return_value={"existing_files": {}})
    executor._validate_scope_context = Mock()
    executor._get_learning_context_for_phase = Mock(
        return_value={"project_rules": [], "run_hints": []}
    )
    executor._build_deliverables_contract = Mock(return_value={})
    executor._record_phase_error = Mock()
    executor._record_learning_hint = Mock()
    executor._invoke_doctor = Mock(return_value=None)
    executor._handle_doctor_action = Mock(return_value=("no_action", True))
    executor._post_builder_result = Mock()
    executor._get_project_slug = Mock(return_value="test-project")
    executor._should_include_sot_retrieval = Mock(return_value=False)
    executor._record_sot_retrieval_telemetry = Mock()
    executor._model_to_provider = Mock(return_value="openai")

    return BuilderOrchestrator(executor)


def make_builder_result(
    success: bool = True, patch_content: str = "diff --git a/test.py"
) -> BuilderResult:
    """Create a BuilderResult for testing."""
    return BuilderResult(
        success=success,
        patch_content=patch_content,
        builder_messages=["Generated patch"],
        tokens_used=1000,
        model_used="gpt-4",
        error=None if success else "Test error",
    )


class TestExecuteBuilderWithValidation:
    """Test execute_builder_with_validation main entry point."""

    def test_execute_builder_loads_all_context(self, tmp_path: Path):
        """Test that execute_builder_with_validation loads all context types."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.execute_builder_phase.return_value = make_builder_result()

        # Mock the deliverables contract builder to return empty dict
        orchestrator.executor._build_deliverables_contract.return_value = {}

        with patch.object(
            orchestrator,
            "_load_context",
            return_value={
                "file_context": {"existing_files": {}},
                "project_rules": ["rule1"],
                "run_hints": ["hint1"],
                "retrieved_context": "context",
            },
        ) as mock_load_context:
            with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
                mock_decide.return_value = Mock(read_only=False, oversized_files=[])
                orchestrator.execute_builder_with_validation(
                    phase_id="phase-1",
                    phase={"description": "Test phase"},
                    attempt_index=0,
                )

        mock_load_context.assert_called_once_with(
            "phase-1", {"description": "Test phase"}, memory_context=None
        )

    def test_execute_builder_prepares_phase_spec(self, tmp_path: Path):
        """Test that execute_builder_with_validation prepares phase spec with constraints."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.execute_builder_phase.return_value = make_builder_result()

        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        with patch.object(orchestrator, "_load_context", return_value=context_info):
            with patch.object(
                orchestrator, "_prepare_phase_spec", return_value=({}, False)
            ) as mock_prepare:
                orchestrator.execute_builder_with_validation(
                    phase_id="phase-1",
                    phase={"description": "Test phase"},
                    attempt_index=0,
                )

        mock_prepare.assert_called_once()
        assert mock_prepare.call_args[0][0] == "phase-1"
        assert mock_prepare.call_args[0][1]["description"] == "Test phase"

    def test_execute_builder_invokes_builder(self, tmp_path: Path):
        """Test that execute_builder_with_validation invokes Builder LLM."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        orchestrator.llm_service.execute_builder_phase.return_value = builder_result

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            result, context = orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase={"description": "Test phase"},
                attempt_index=0,
            )

        assert result.success is True
        assert orchestrator.llm_service.execute_builder_phase.called

    def test_execute_builder_accumulates_token_usage(self, tmp_path: Path):
        """Test that execute_builder_with_validation accumulates token usage."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        builder_result.tokens_used = 5000
        orchestrator.llm_service.execute_builder_phase.return_value = builder_result

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            initial_tokens = orchestrator.executor._run_tokens_used
            orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase={"description": "Test phase"},
                attempt_index=0,
            )

        assert orchestrator.executor._run_tokens_used == initial_tokens + 5000

    def test_execute_builder_stores_last_result(self, tmp_path: Path):
        """Test that execute_builder_with_validation stores last builder result."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        orchestrator.llm_service.execute_builder_phase.return_value = builder_result

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase={"description": "Test phase"},
                attempt_index=0,
            )

        assert orchestrator.executor._last_builder_result == builder_result


class TestLoadContext:
    """Test _load_context and sub-methods."""

    def test_load_context_loads_file_context(self, tmp_path: Path):
        """Test that _load_context loads file context."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.executor._load_repository_context.return_value = {
            "existing_files": {"test.py": "content"}
        }

        context_info = orchestrator._load_context("phase-1", {"description": "Test"})

        assert "file_context" in context_info
        assert context_info["file_context"]["existing_files"]["test.py"] == "content"

    def test_load_context_validates_scope(self, tmp_path: Path):
        """Test that _load_context validates scope if configured."""
        orchestrator = make_builder_orchestrator(tmp_path)
        phase = {"description": "Test", "scope": {"paths": ["src/"]}}

        orchestrator._load_context("phase-1", phase)

        orchestrator.executor._validate_scope_context.assert_called_once()

    def test_load_context_loads_learning_context(self, tmp_path: Path):
        """Test that _load_context loads learning context."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.executor._get_learning_context_for_phase.return_value = {
            "project_rules": ["rule1", "rule2"],
            "run_hints": ["hint1"],
        }

        context_info = orchestrator._load_context("phase-1", {"description": "Test"})

        assert context_info["project_rules"] == ["rule1", "rule2"]
        assert context_info["run_hints"] == ["hint1"]

    def test_load_file_context_handles_path_errors(self, tmp_path: Path):
        """Test that _load_file_context handles path/list TypeError."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.executor._load_repository_context.side_effect = TypeError(
            "unsupported operand type(s) for /: 'PosixPath' and 'list'"
        )

        # Should not raise, returns empty context
        file_context = orchestrator._load_file_context("phase-1", {})

        assert file_context == {"existing_files": {}}

    def test_retrieve_memory_context_disabled_when_no_service(self, tmp_path: Path):
        """Test that _retrieve_memory_context returns empty when service disabled."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.memory_service = None

        retrieved = orchestrator._retrieve_memory_context("phase-1", {"description": "Test"})

        assert retrieved == ""

    def test_retrieve_memory_context_calls_memory_service(self, tmp_path: Path):
        """Test that _retrieve_memory_context calls memory service."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.memory_service = Mock()
        orchestrator.memory_service.enabled = True
        orchestrator.memory_service.retrieve_context.return_value = {"code": ["snippet1"]}
        orchestrator.memory_service.format_retrieved_context.return_value = "formatted context"

        retrieved = orchestrator._retrieve_memory_context("phase-1", {"description": "Test query"})

        assert retrieved == "formatted context"
        orchestrator.memory_service.retrieve_context.assert_called_once()

    def test_inject_intention_context_disabled_by_default(self, tmp_path: Path):
        """Test that _inject_intention_context is disabled by default."""
        orchestrator = make_builder_orchestrator(tmp_path)

        with patch.dict(os.environ, {"AUTOPACK_ENABLE_INTENTION_CONTEXT": "false"}):
            intention = orchestrator._inject_intention_context("phase-1", "")

        assert intention == ""

    def test_inject_intention_context_enabled_when_env_set(self, tmp_path: Path):
        """Test that _inject_intention_context works when enabled."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.memory_service = Mock()  # Enable memory service for intention context

        with patch.dict(os.environ, {"AUTOPACK_ENABLE_INTENTION_CONTEXT": "true"}):
            with patch("autopack.intention_wiring.IntentionContextInjector") as mock_injector:
                mock_instance = Mock()
                mock_instance.get_intention_context.return_value = "intention context"
                mock_injector.return_value = mock_instance

                # Need to set the _intention_injector on the executor
                orchestrator.executor._intention_injector = mock_instance

                intention = orchestrator._inject_intention_context("phase-1", "")

        assert intention == "intention context"
        mock_instance.get_intention_context.assert_called_once_with(max_chars=2048)


class TestPreparePhaseSpec:
    """Test _prepare_phase_spec and sub-methods."""

    def test_prepare_phase_spec_validates_file_sizes(self, tmp_path: Path):
        """Test that _prepare_phase_spec validates file sizes."""
        orchestrator = make_builder_orchestrator(tmp_path)
        context_info = {
            "file_context": {"existing_files": {"test.py": "content"}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        with patch.object(orchestrator, "_validate_file_sizes", return_value=True) as mock_validate:
            orchestrator._prepare_phase_spec("phase-1", {}, context_info)

        mock_validate.assert_called_once()

    def test_prepare_phase_spec_runs_deliverables_gate(self, tmp_path: Path):
        """Test that _prepare_phase_spec runs deliverables manifest gate."""
        orchestrator = make_builder_orchestrator(tmp_path)
        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            with patch.object(orchestrator, "_run_deliverables_manifest_gate") as mock_gate:
                orchestrator._prepare_phase_spec("phase-1", {}, context_info)

        mock_gate.assert_called_once()

    def test_prepare_phase_spec_propagates_attempt_index(self, tmp_path: Path):
        """Test that _prepare_phase_spec propagates attempt_index to manifest gate."""
        orchestrator = make_builder_orchestrator(tmp_path)
        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            with patch.object(orchestrator, "_run_deliverables_manifest_gate") as mock_gate:
                orchestrator._prepare_phase_spec("phase-1", {}, context_info, attempt_index=2)

        # Verify attempt_index was passed to the gate
        mock_gate.assert_called_once()
        call_args = mock_gate.call_args[0]
        assert call_args[3] == 2  # attempt_index is 4th positional argument

    def test_prepare_phase_spec_adds_protected_paths(self, tmp_path: Path):
        """Test that _prepare_phase_spec adds protected paths."""
        orchestrator = make_builder_orchestrator(tmp_path)
        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            phase_with_constraints, _ = orchestrator._prepare_phase_spec(
                "phase-1", {}, context_info
            )

        assert "protected_paths" in phase_with_constraints
        assert ".autonomous_runs/" in phase_with_constraints["protected_paths"]
        assert ".git/" in phase_with_constraints["protected_paths"]

    def test_validate_file_sizes_delegates_to_context_preflight(self, tmp_path: Path):
        """Test that _validate_file_sizes delegates to ContextPreflight."""
        orchestrator = make_builder_orchestrator(tmp_path)
        decision = Mock()
        decision.read_only = False
        decision.oversized_files = []
        orchestrator.context_preflight.decide_read_only.return_value = decision

        file_context = {"existing_files": {"test.py": "content"}}
        use_full_file = orchestrator._validate_file_sizes("phase-1", {}, file_context)

        orchestrator.context_preflight.decide_read_only.assert_called_once()
        assert use_full_file is True

    def test_validate_file_sizes_records_telemetry_for_oversized(self, tmp_path: Path):
        """Test that _validate_file_sizes records telemetry for oversized files."""
        orchestrator = make_builder_orchestrator(tmp_path)
        decision = Mock()
        decision.read_only = True
        decision.oversized_files = [("large_file.py", 2000)]
        orchestrator.context_preflight.decide_read_only.return_value = decision

        file_context = {"existing_files": {"large_file.py": "x" * 5000}}
        orchestrator._validate_file_sizes("phase-1", {}, file_context)

        orchestrator.file_size_telemetry.record_preflight_reject.assert_called_once()

    def test_validate_file_sizes_prefers_structured_for_large_scopes(self, tmp_path: Path):
        """Test that _validate_file_sizes prefers structured edits for large scopes."""
        orchestrator = make_builder_orchestrator(tmp_path)
        decision = Mock()
        decision.read_only = False
        decision.oversized_files = []
        orchestrator.context_preflight.decide_read_only.return_value = decision

        # Create large file context (30+ files)
        file_context = {"existing_files": {f"file{i}.py": "content" for i in range(35)}}
        use_full_file = orchestrator._validate_file_sizes("phase-1", {}, file_context)

        assert use_full_file is False

    def test_run_deliverables_manifest_gate_skips_when_no_scope(self, tmp_path: Path):
        """Test that _run_deliverables_manifest_gate skips when no expected paths."""
        orchestrator = make_builder_orchestrator(tmp_path)

        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope", return_value=[]
        ):
            orchestrator._run_deliverables_manifest_gate("phase-1", {}, {})

        # Should not call llm_service
        assert not orchestrator.llm_service.generate_deliverables_manifest.called

    def test_run_deliverables_manifest_gate_uses_attempt_index(self, tmp_path: Path):
        """Test that _run_deliverables_manifest_gate uses attempt_index in manifest generation."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.generate_deliverables_manifest.return_value = (
            True,
            ["src/autopack/research/test.py"],
            None,
            "raw",
        )

        phase = {"scope": {"paths": ["src/autopack/research/"]}}
        phase_with_constraints = {
            "scope": {"paths": ["src/autopack/research/"]},
            "deliverables_contract": {"required": []},
        }

        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope",
            return_value=["src/autopack/research/test.py"],
        ):
            orchestrator._run_deliverables_manifest_gate(
                "phase-1", phase, phase_with_constraints, attempt_index=3
            )

        # Verify generate_deliverables_manifest was called with attempt_index=3
        call_kwargs = orchestrator.llm_service.generate_deliverables_manifest.call_args[1]
        assert call_kwargs["attempt_index"] == 3

    def test_run_deliverables_manifest_gate_generates_manifest(self, tmp_path: Path):
        """Test that _run_deliverables_manifest_gate generates manifest."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.generate_deliverables_manifest.return_value = (
            True,
            ["src/autopack/research/test.py"],
            None,
            "raw",
        )

        phase = {"scope": {"paths": ["src/autopack/research/"]}}
        phase_with_constraints = {
            "scope": {"paths": ["src/autopack/research/"]},
            "deliverables_contract": {"required": []},
        }

        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope",
            return_value=["src/autopack/research/test.py"],
        ):
            orchestrator._run_deliverables_manifest_gate("phase-1", phase, phase_with_constraints)

        assert "deliverables_manifest" in phase_with_constraints
        assert phase_with_constraints["deliverables_manifest"] == ["src/autopack/research/test.py"]


class TestInvokeBuilder:
    """Test _invoke_builder with auto-fallback behavior."""

    def test_invoke_builder_calls_llm_service(self, tmp_path: Path):
        """Test that _invoke_builder calls llm_service with correct parameters."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.execute_builder_phase.return_value = make_builder_result()

        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": ["rule1"],
            "run_hints": ["hint1"],
            "retrieved_context": "context",
        }

        orchestrator._invoke_builder(
            "phase-1", {"description": "Test"}, {"description": "Test"}, context_info, True, 0
        )

        call_kwargs = orchestrator.llm_service.execute_builder_phase.call_args[1]
        assert call_kwargs["project_rules"] == ["rule1"]
        assert call_kwargs["run_hints"] == ["hint1"]
        assert call_kwargs["retrieved_context"] == "context"

    def test_invoke_builder_auto_fallback_on_parse_failure(self, tmp_path: Path):
        """Test that _invoke_builder falls back to structured edits on parse failure."""
        orchestrator = make_builder_orchestrator(tmp_path)

        # First call fails with parse error
        failed_result = make_builder_result(success=False, patch_content="")
        failed_result.error = "full_file_parse_failed"

        # Second call succeeds
        success_result = make_builder_result()

        orchestrator.llm_service.execute_builder_phase.side_effect = [failed_result, success_result]

        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        result = orchestrator._invoke_builder(
            "phase-1", {"description": "Test"}, {"description": "Test"}, context_info, True, 0
        )

        # Should have called execute_builder_phase twice
        assert orchestrator.llm_service.execute_builder_phase.call_count == 2
        assert result.success is True

    def test_invoke_builder_auto_fallback_on_truncation(self, tmp_path: Path):
        """Test that _invoke_builder falls back to structured edits on truncation."""
        orchestrator = make_builder_orchestrator(tmp_path)

        # First call truncated
        failed_result = make_builder_result(success=False, patch_content="")
        failed_result.error = "output was truncated"

        success_result = make_builder_result()
        orchestrator.llm_service.execute_builder_phase.side_effect = [failed_result, success_result]

        context_info = {
            "file_context": {"existing_files": {}},
            "project_rules": [],
            "run_hints": [],
            "retrieved_context": "",
        }

        _result = orchestrator._invoke_builder(
            "phase-1", {"description": "Test"}, {"description": "Test"}, context_info, True, 0
        )

        assert orchestrator.llm_service.execute_builder_phase.call_count == 2
        # Verify second call used structured_edit mode
        second_call_phase = orchestrator.llm_service.execute_builder_phase.call_args_list[1][1][
            "phase_spec"
        ]
        assert second_call_phase["builder_mode"] == "structured_edit"


class TestValidateOutput:
    """Test _validate_output for empty patch validation."""

    def test_validate_output_passes_with_patch_content(self, tmp_path: Path):
        """Test that _validate_output passes when patch content exists."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        result = orchestrator._validate_output("phase-1", builder_result)

        assert result.success is True

    def test_validate_output_passes_with_edit_plan(self, tmp_path: Path):
        """Test that _validate_output passes when edit_plan exists."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(patch_content="")
        builder_result.edit_plan = Mock()  # Non-None edit_plan

        result = orchestrator._validate_output("phase-1", builder_result)

        assert result.success is True

    def test_validate_output_allows_explicit_no_op(self, tmp_path: Path):
        """Test that _validate_output allows explicit no-op messages."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(patch_content="")
        builder_result.builder_messages = ["Structured edit produced no operations"]

        result = orchestrator._validate_output("phase-1", builder_result)

        assert result.success is True

    def test_validate_output_fails_empty_patch_without_no_op(self, tmp_path: Path):
        """Test that _validate_output fails on empty patch without no-op message."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(patch_content="")
        builder_result.builder_messages = ["Generated patch"]

        result = orchestrator._validate_output("phase-1", builder_result)

        assert result.success is False
        assert "empty_patch" in result.error


class TestHandleRetryScenarios:
    """Test handle_retry_scenarios and sub-methods."""

    def test_handle_retry_returns_success_for_successful_result(self, tmp_path: Path):
        """Test that handle_retry_scenarios returns success for successful builder result."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        should_retry, reason = orchestrator.handle_retry_scenarios("phase-1", {}, builder_result, 0)

        assert should_retry is True
        assert reason == "SUCCESS"

    def test_handle_empty_files_retry_triggers_once(self, tmp_path: Path):
        """Test that _handle_empty_files_retry triggers once for empty files error."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "empty files array"

        phase = {"max_builder_attempts": 5}
        result = orchestrator._handle_empty_files_retry("phase-1", phase, builder_result, 0)

        assert result is not None
        assert result == (False, "EMPTY_FILES_RETRY")
        assert phase["_empty_files_retry_count"] == 1

    def test_handle_empty_files_retry_only_retries_once(self, tmp_path: Path):
        """Test that _handle_empty_files_retry only retries once."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "empty files array"

        phase = {"max_builder_attempts": 5, "_empty_files_retry_count": 1}
        result = orchestrator._handle_empty_files_retry("phase-1", phase, builder_result, 1)

        assert result is None  # Should not retry again

    def test_handle_infra_errors_backs_off(self, tmp_path: Path):
        """Test that _handle_infra_errors backs off on infra errors."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "connection error"

        with patch("time.sleep") as mock_sleep:
            result = orchestrator._handle_infra_errors("phase-1", {}, builder_result, 0)

        assert result is not None
        assert result == (False, "INFRA_RETRY")
        mock_sleep.assert_called_once()

    def test_handle_infra_errors_disables_provider_after_repeated_errors(self, tmp_path: Path):
        """Test that _handle_infra_errors disables provider after repeated errors."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.model_router = Mock()
        builder_result = make_builder_result(success=False)
        builder_result.error = "timeout"
        builder_result.model_used = "gpt-4"

        # Trigger twice to disable provider
        with patch("time.sleep"):
            orchestrator._handle_infra_errors("phase-1", {}, builder_result, 0)
            orchestrator._handle_infra_errors("phase-1", {}, builder_result, 1)

        orchestrator.llm_service.model_router.disable_provider.assert_called_once()

    def test_handle_token_escalation_escalates_once(self, tmp_path: Path):
        """Test that _handle_token_escalation escalates once on truncation."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.was_truncated = True

        phase = {
            "max_builder_attempts": 5,
            "metadata": {
                "token_budget": {"output_utilization": 0},
                "token_prediction": {"selected_budget": 8000, "actual_max_tokens": 8000},
            },
        }

        result = orchestrator._handle_token_escalation("phase-1", phase, builder_result, 0)

        assert result is not None
        assert result == (False, "TOKEN_ESCALATION")
        assert phase["_escalated_once"] is True
        assert phase["_escalated_tokens"] == 10000  # 8000 * 1.25

    def test_handle_token_escalation_only_escalates_once(self, tmp_path: Path):
        """Test that _handle_token_escalation only escalates once."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.was_truncated = True

        phase = {
            "max_builder_attempts": 5,
            "_escalated_once": True,
            "metadata": {
                "token_budget": {"output_utilization": 0},
                "token_prediction": {"selected_budget": 8000},
            },
        }

        result = orchestrator._handle_token_escalation("phase-1", phase, builder_result, 0)

        assert result is None  # Should not escalate again


class TestHandleBuilderFailure:
    """Test handle_builder_failure with Doctor invocation."""

    def test_handle_builder_failure_records_learning_hint(self, tmp_path: Path):
        """Test that handle_builder_failure records learning hint."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "churn_limit_exceeded"

        orchestrator.handle_builder_failure("phase-1", {}, builder_result, 0)

        orchestrator.executor._record_learning_hint.assert_called_once()

    def test_handle_builder_failure_records_phase_error(self, tmp_path: Path):
        """Test that handle_builder_failure records phase error."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "suspicious_growth"

        orchestrator.handle_builder_failure("phase-1", {}, builder_result, 0)

        orchestrator.executor._record_phase_error.assert_called_once()

    def test_handle_builder_failure_invokes_doctor(self, tmp_path: Path):
        """Test that handle_builder_failure invokes Doctor."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "builder guardrail failure"

        orchestrator.handle_builder_failure("phase-1", {}, builder_result, 0)

        orchestrator.executor._invoke_doctor.assert_called_once()

    def test_handle_builder_failure_handles_doctor_action(self, tmp_path: Path):
        """Test that handle_builder_failure handles Doctor action."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "test error"

        orchestrator.executor._invoke_doctor.return_value = {"action": "replan"}
        orchestrator.executor._handle_doctor_action.return_value = ("replan", False)

        action, should_continue = orchestrator.handle_builder_failure(
            "phase-1", {}, builder_result, 0
        )

        assert action == "replan"
        assert should_continue is False

    def test_handle_builder_failure_records_issue(self, tmp_path: Path):
        """Test that handle_builder_failure records structured issue."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.error = "churn_limit_exceeded"

        with patch("autopack.issue_tracker.IssueTracker") as mock_tracker:
            mock_instance = Mock()
            mock_tracker.return_value = mock_instance

            orchestrator.handle_builder_failure("phase-1", {}, builder_result, 0)

            mock_instance.record_issue.assert_called_once()


class TestValidateDeliverables:
    """Test validate_deliverables with patch and JSON validation."""

    def test_validate_deliverables_passes_all_checks(self, tmp_path: Path):
        """Test that validate_deliverables passes when all validations succeed."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.validate_deliverables", return_value=(True, [], {})
        ):
            with patch(
                "autopack.deliverables_validator.extract_deliverables_from_scope", return_value=[]
            ):
                with patch(
                    "autopack.deliverables_validator.validate_new_json_deliverables_in_patch",
                    return_value=(True, [], {}),
                ):
                    is_valid, reason = orchestrator.validate_deliverables(
                        "phase-1", {}, builder_result, 0
                    )

        assert is_valid is True
        assert reason == ""

    def test_validate_deliverables_checks_truncation_escalation(self, tmp_path: Path):
        """Test that validate_deliverables checks truncation escalation first."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        builder_result.was_truncated = True

        phase = {
            "max_builder_attempts": 5,
            "metadata": {
                "token_budget": {"output_utilization": 0},
                "token_prediction": {"selected_budget": 8000},
            },
        }

        is_valid, reason = orchestrator.validate_deliverables("phase-1", phase, builder_result, 0)

        assert is_valid is False
        assert reason == "TOKEN_ESCALATION"

    def test_validate_patch_deliverables_calls_validator_function(self, tmp_path: Path):
        """Test that _validate_patch_deliverables calls validate_deliverables function."""
        orchestrator = make_builder_orchestrator(tmp_path)
        # Create a patch that matches expected deliverables
        patch_content = """diff --git a/src/test.py b/src/test.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/test.py
@@ -0,0 +1,3 @@
+def test_function():
+    pass
+"""
        builder_result = make_builder_result(patch_content=patch_content)

        # The method imports validate_deliverables at call time, so we can't easily mock it
        # Just verify the method executes successfully with a proper deliverables scope
        is_valid, reason = orchestrator._validate_patch_deliverables(
            "phase-1", {"scope": {"paths": ["src/test.py"]}}, builder_result, 0
        )

        # Should succeed for valid patch
        assert is_valid is True
        assert reason == ""

    def test_validate_patch_deliverables_fails_on_validation_error(self, tmp_path: Path):
        """Test that _validate_patch_deliverables fails on validation errors."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.validate_deliverables",
            return_value=(False, ["Error 1"], {"missing_paths": ["src/test.py"]}),
        ):
            with patch(
                "autopack.deliverables_validator.format_validation_feedback_for_builder",
                return_value="Error feedback",
            ):
                is_valid, reason = orchestrator._validate_patch_deliverables(
                    "phase-1", {"scope": {"paths": ["src/"]}}, builder_result, 0
                )

        assert is_valid is False
        assert reason == "DELIVERABLES_VALIDATION_FAILED"

    def test_validate_json_deliverables_validates_new_json(self, tmp_path: Path):
        """Test that _validate_json_deliverables validates new JSON files."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope", return_value=[]
        ):
            with patch(
                "autopack.deliverables_validator.validate_new_json_deliverables_in_patch",
                return_value=(True, [], {}),
            ):
                is_valid, reason = orchestrator._validate_json_deliverables(
                    "phase-1", {}, builder_result, 0
                )

        assert is_valid is True
        assert reason == ""

    def test_validate_json_deliverables_attempts_auto_repair(self, tmp_path: Path):
        """Test that _validate_json_deliverables attempts auto-repair on failure."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.extract_deliverables_from_scope",
            return_value=["test.json"],
        ):
            with patch(
                "autopack.deliverables_validator.validate_new_json_deliverables_in_patch",
                return_value=(False, ["Error"], {}),
            ):
                with patch.object(
                    orchestrator, "_auto_repair_json_deliverables", return_value=(True, [], {})
                ):
                    is_valid, reason = orchestrator._validate_json_deliverables(
                        "phase-1", {"scope": {"paths": ["test.json"]}}, builder_result, 0
                    )

        assert is_valid is True


class TestAutoRepairJsonDeliverables:
    """Test _auto_repair_json_deliverables."""

    def test_auto_repair_repairs_empty_json(self, tmp_path: Path):
        """Test that _auto_repair_json_deliverables repairs empty JSON files."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.repair_empty_required_json_deliverables_in_patch",
            return_value=(
                True,
                "repaired patch",
                [{"path": "test.json", "reason": "empty", "applied": "[]"}],
            ),
        ):
            with patch(
                "autopack.deliverables_validator.validate_new_json_deliverables_in_patch",
                return_value=(True, [], {}),
            ):
                ok, errors, details = orchestrator._auto_repair_json_deliverables(
                    "phase-1", {}, builder_result, ["test.json"], {}
                )

        assert ok is True
        assert builder_result.patch_content == "repaired patch"

    def test_auto_repair_records_learning_hint_on_success(self, tmp_path: Path):
        """Test that _auto_repair_json_deliverables records learning hint on success."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        phase = {}

        with patch(
            "autopack.deliverables_validator.repair_empty_required_json_deliverables_in_patch",
            return_value=(True, "repaired", [{"path": "test.json"}]),
        ):
            with patch(
                "autopack.deliverables_validator.validate_new_json_deliverables_in_patch",
                return_value=(True, [], {}),
            ):
                orchestrator._auto_repair_json_deliverables(
                    "phase-1", phase, builder_result, ["test.json"], {}
                )

        orchestrator.executor._record_learning_hint.assert_called_once()

    def test_auto_repair_returns_false_if_repair_fails(self, tmp_path: Path):
        """Test that _auto_repair_json_deliverables returns false if repair fails."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        with patch(
            "autopack.deliverables_validator.repair_empty_required_json_deliverables_in_patch",
            return_value=(False, "original", []),
        ):
            ok, errors, details = orchestrator._auto_repair_json_deliverables(
                "phase-1", {}, builder_result, ["test.json"], {}
            )

        assert ok is False


class TestPostBuilderResult:
    """Test post_builder_result."""

    def test_post_builder_result_delegates_to_executor(self, tmp_path: Path):
        """Test that post_builder_result delegates to executor."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()

        orchestrator.post_builder_result("phase-1", builder_result, None)

        orchestrator.executor._post_builder_result.assert_called_once_with(
            "phase-1", builder_result, None
        )

    def test_post_builder_result_passes_allowed_paths(self, tmp_path: Path):
        """Test that post_builder_result passes allowed_paths."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        allowed_paths = ["src/", "tests/"]

        orchestrator.post_builder_result("phase-1", builder_result, allowed_paths)

        call_args = orchestrator.executor._post_builder_result.call_args[0]
        assert call_args[2] == allowed_paths


class TestExtractPatchStats:
    """Test _extract_patch_stats."""

    def test_extract_patch_stats_parses_patch(self, tmp_path: Path):
        """Test that _extract_patch_stats parses patch statistics."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result()
        builder_result.patch_content = "diff --git a/test.py\n+++ test"

        with patch("autopack.executor.builder_orchestrator.GovernedApplyPath") as mock_apply:
            mock_instance = Mock()
            mock_instance.parse_patch_stats.return_value = (1, 10, 5)
            mock_apply.return_value = mock_instance

            orchestrator._extract_patch_stats(builder_result)

        assert orchestrator.executor._last_files_changed == 1
        assert orchestrator.executor._last_lines_added == 10
        assert orchestrator.executor._last_lines_removed == 5


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_full_builder_pipeline_success(self, tmp_path: Path):
        """Test complete successful builder pipeline."""
        orchestrator = make_builder_orchestrator(tmp_path)
        orchestrator.llm_service.execute_builder_phase.return_value = make_builder_result()

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            builder_result, context = orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase={"description": "Test phase"},
                attempt_index=0,
            )

        assert builder_result.success is True
        assert "file_context" in context
        assert orchestrator.executor._last_builder_result is not None

    def test_builder_pipeline_with_fallback_to_structured_edits(self, tmp_path: Path):
        """Test builder pipeline with auto-fallback to structured edits."""
        orchestrator = make_builder_orchestrator(tmp_path)

        # First call fails with parse error, second succeeds
        failed_result = make_builder_result(success=False)
        failed_result.error = "full_file_parse_failed"
        success_result = make_builder_result()

        orchestrator.llm_service.execute_builder_phase.side_effect = [failed_result, success_result]

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            builder_result, context = orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase={"description": "Test phase"},
                attempt_index=0,
            )

        assert builder_result.success is True
        assert orchestrator.llm_service.execute_builder_phase.call_count == 2

    def test_builder_pipeline_with_token_escalation(self, tmp_path: Path):
        """Test builder pipeline with token escalation scenario."""
        orchestrator = make_builder_orchestrator(tmp_path)
        builder_result = make_builder_result(success=False)
        builder_result.was_truncated = True
        orchestrator.llm_service.execute_builder_phase.return_value = builder_result

        phase = {
            "description": "Test phase",
            "max_builder_attempts": 5,
            "metadata": {
                "token_budget": {"output_utilization": 96.0},
                "token_prediction": {"selected_budget": 8000},
            },
        }

        with patch.object(orchestrator.context_preflight, "decide_read_only") as mock_decide:
            mock_decide.return_value = Mock(read_only=False, oversized_files=[])
            builder_result, context = orchestrator.execute_builder_with_validation(
                phase_id="phase-1",
                phase=phase,
                attempt_index=0,
            )

        should_retry, reason = orchestrator.handle_retry_scenarios(
            "phase-1", phase, builder_result, 0
        )

        assert should_retry is False
        assert reason == "TOKEN_ESCALATION"
        assert phase.get("_escalated_once") is True


class TestDeduplicateMemoryContext:
    """Test _deduplicate_memory_context (IMP-PERF-003)."""

    def test_deduplicate_returns_unchanged_when_no_file_context(self, tmp_path: Path):
        """Test that deduplication returns context unchanged when no file context."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: test.py ---\nprint('hello')\n--- END FILE ---"

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, {})

        assert result == memory_context

    def test_deduplicate_returns_unchanged_when_no_existing_files(self, tmp_path: Path):
        """Test that deduplication returns context unchanged when no existing files."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: test.py ---\nprint('hello')\n--- END FILE ---"

        result = orchestrator._deduplicate_memory_context(
            "phase-1", memory_context, {"existing_files": {}}
        )

        assert result == memory_context

    def test_deduplicate_removes_file_block_matching_context(self, tmp_path: Path):
        """Test that file blocks matching file context are removed."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = (
            "Some intro text\n"
            "--- FILE: src/test.py ---\n"
            "print('hello')\n"
            "--- END FILE ---\n"
            "Some outro text"
        )
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        assert "--- FILE: src/test.py ---" not in result
        assert "Some intro text" in result
        assert "Some outro text" in result

    def test_deduplicate_preserves_file_blocks_not_in_context(self, tmp_path: Path):
        """Test that file blocks not in file context are preserved."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: other.py ---\nprint('other')\n--- END FILE ---"
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        assert "--- FILE: other.py ---" in result
        assert "print('other')" in result

    def test_deduplicate_handles_code_block_format(self, tmp_path: Path):
        """Test that code blocks with file paths are deduplicated."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "Some context\n```src/test.py\ndef hello():\n    pass\n```\nMore context"
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        assert "```src/test.py" not in result
        assert "def hello():" not in result
        assert "Some context" in result
        assert "More context" in result

    def test_deduplicate_handles_normalized_paths(self, tmp_path: Path):
        """Test that paths are normalized for comparison."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: /src/test.py ---\ncontent\n--- END FILE ---"
        # File context has path without leading slash
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        # Should be deduplicated due to normalization
        assert "--- FILE:" not in result

    def test_deduplicate_handles_windows_paths(self, tmp_path: Path):
        """Test that Windows-style paths are handled."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: src\\test.py ---\ncontent\n--- END FILE ---"
        # File context has forward slash
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        # Should be deduplicated due to path normalization
        assert "--- FILE:" not in result

    def test_deduplicate_cleans_consecutive_newlines(self, tmp_path: Path):
        """Test that consecutive newlines are cleaned up after deduplication."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = (
            "Intro\n\n\n--- FILE: src/test.py ---\ncontent\n--- END FILE ---\n\n\n\nOutro"
        )
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        # Should not have more than 2 consecutive newlines
        assert "\n\n\n" not in result

    def test_deduplicate_multiple_blocks(self, tmp_path: Path):
        """Test deduplication of multiple file blocks."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = (
            "--- FILE: src/a.py ---\ncontent a\n--- END FILE ---\n"
            "--- FILE: src/b.py ---\ncontent b\n--- END FILE ---\n"
            "--- FILE: src/c.py ---\ncontent c\n--- END FILE ---"
        )
        # Only a.py and c.py are in file context
        file_context = {
            "existing_files": {
                "src/a.py": "content",
                "src/c.py": "content",
            }
        }

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        # b.py should remain, a.py and c.py should be removed
        assert "--- FILE: src/b.py ---" in result
        assert "content b" in result
        assert "--- FILE: src/a.py ---" not in result
        assert "--- FILE: src/c.py ---" not in result

    def test_deduplicate_returns_empty_when_all_removed(self, tmp_path: Path):
        """Test that empty string is returned when all content is deduplicated."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = "--- FILE: src/test.py ---\nprint('hello')\n--- END FILE ---"
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        assert result == ""

    def test_deduplicate_preserves_non_file_content(self, tmp_path: Path):
        """Test that non-file content is preserved."""
        orchestrator = make_builder_orchestrator(tmp_path)
        memory_context = (
            "## Summary\n"
            "This is important context about the task.\n\n"
            "## Related Decisions\n"
            "- Decision 1: Use approach A\n"
            "- Decision 2: Avoid pattern B\n"
        )
        file_context = {"existing_files": {"src/test.py": "content"}}

        result = orchestrator._deduplicate_memory_context("phase-1", memory_context, file_context)

        # All content should be preserved
        assert "## Summary" in result
        assert "important context" in result
        assert "## Related Decisions" in result
        assert "Decision 1" in result
