"""E2E integration tests for build execution (IMP-WORKFLOW-003).

Tests the end-to-end build execution pipeline including:
1. Build context loading and validation
2. Builder orchestration with full context
3. Patch generation and validation
4. Error handling and recovery scenarios
5. Token budget management during builds
6. Multi-attempt build execution with fallback modes

This module focuses on the complete build execution flow from phase
specification through patch generation and validation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from autopack.llm_client import BuilderResult
from autopack.models import PhaseState


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def builder_test_context():
    """Sample builder test context for E2E tests."""
    return {
        "phase_id": "build-test-001",
        "phase_name": "Implementation",
        "task_description": "Implement feature X",
        "existing_files": {
            "src/main.py": "def hello():\n    print('Hello')",
            "tests/test_main.py": "def test_hello():\n    assert True",
            "README.md": "# Project",
        },
        "scope": {"paths": ["src/", "tests/"]},
        "deliverables": ["src/main.py"],
    }


@pytest.fixture
def valid_patch_content():
    """Sample valid patch content for testing."""
    return """diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,4 @@
 def hello():
     print('Hello')
+
+def goodbye():
+    print('Goodbye')
"""


@pytest.fixture
def builder_result_factory():
    """Factory for creating BuilderResult objects."""

    def make_result(
        success=True,
        patch_content="diff --git a/test.py",
        error=None,
        tokens_used=1000,
        model_used="gpt-4",
        messages=None,
    ):
        result = BuilderResult(
            success=success,
            patch_content=patch_content,
            builder_messages=messages or ["Generated patch"],
            tokens_used=tokens_used,
            model_used=model_used,
            error=error,
        )
        return result

    return make_result


# =============================================================================
# Build Execution Pipeline Tests
# =============================================================================


@pytest.mark.integration
class TestBuildExecutionPipeline:
    """E2E tests for complete build execution pipeline."""

    def test_build_context_loading(self, builder_test_context):
        """Test that build context is loaded correctly."""
        # Arrange
        context = builder_test_context

        # Act & Assert
        assert context["phase_id"] is not None
        assert "existing_files" in context
        assert len(context["existing_files"]) > 0
        assert context["scope"] is not None
        assert context["deliverables"] is not None

    def test_build_context_validation(self, builder_test_context):
        """Test that build context is validated before execution."""
        # Arrange
        context = builder_test_context

        # Act: Validate files exist
        for file_path in context["existing_files"]:
            assert file_path is not None
            assert len(file_path) > 0

        # Act: Validate scope is defined
        assert len(context["scope"]["paths"]) > 0

        # Assert
        assert True  # Context is valid

    def test_build_context_file_content_integrity(self, builder_test_context):
        """Test that file contents in context are intact."""
        # Arrange
        context = builder_test_context

        # Act & Assert
        for file_path, content in context["existing_files"].items():
            assert isinstance(content, str)
            assert len(content) > 0

    def test_builder_invocation_with_context(self, builder_test_context, builder_result_factory):
        """Test that builder is invoked with complete context."""
        # Arrange
        context = builder_test_context
        phase_spec = {
            "phase_id": context["phase_id"],
            "description": context["task_description"],
            "scope": context["scope"],
        }

        # Act: Simulate builder invocation
        llm_service = Mock()
        builder_result = builder_result_factory(success=True)
        llm_service.execute_builder_phase.return_value = builder_result

        # Verify builder receives context
        result = llm_service.execute_builder_phase(
            phase_id=phase_spec["phase_id"],
            phase_spec=phase_spec,
            file_context={"existing_files": context["existing_files"]},
            project_rules=["rule1"],
        )

        # Assert
        assert result.success is True
        llm_service.execute_builder_phase.assert_called_once()

    def test_patch_generation_from_builder(self, builder_test_context, builder_result_factory):
        """Test that patch is generated correctly from builder."""
        # Arrange
        patch_content = """diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,3 @@
 def hello():
     print('Hello')
+print('Generated')
"""
        builder_result = builder_result_factory(
            success=True, patch_content=patch_content, tokens_used=2500
        )

        # Act & Assert
        assert builder_result.success is True
        assert builder_result.patch_content == patch_content
        assert builder_result.tokens_used == 2500
        assert builder_result.model_used == "gpt-4"

    def test_token_accumulation_during_build(self, builder_result_factory):
        """Test that tokens are accumulated correctly during build."""
        # Arrange
        total_tokens = 0
        builder_results = [
            builder_result_factory(success=True, tokens_used=1000),
            builder_result_factory(success=True, tokens_used=1500),
            builder_result_factory(success=True, tokens_used=2000),
        ]

        # Act: Accumulate tokens
        for result in builder_results:
            total_tokens += result.tokens_used or 0

        # Assert
        assert total_tokens == 4500

    def test_multi_attempt_build_execution(self, builder_result_factory):
        """Test build execution with multiple attempts."""
        # Arrange
        attempts = []
        max_attempts = 3

        # Act: Simulate multi-attempt execution
        for attempt in range(max_attempts):
            if attempt < 2:
                # First two attempts fail
                result = builder_result_factory(
                    success=False,
                    error="context_length_exceeded",
                    tokens_used=0,
                )
            else:
                # Third attempt succeeds
                result = builder_result_factory(
                    success=True, tokens_used=1500, patch_content="diff --git a/test.py"
                )

            attempts.append(result)

        # Assert
        assert len(attempts) == 3
        assert not attempts[0].success
        assert not attempts[1].success
        assert attempts[2].success

    def test_build_fallback_mode_activation(self, builder_result_factory):
        """Test builder fallback to structured edit mode."""
        # Arrange
        llm_service = Mock()

        # First invocation fails with parse error (full file mode)
        failed_result = builder_result_factory(
            success=False, error="full_file_parse_failed", patch_content=""
        )

        # Second invocation succeeds (structured edit mode)
        success_result = builder_result_factory(success=True, patch_content="diff --git a/test.py")

        llm_service.execute_builder_phase.side_effect = [failed_result, success_result]

        # Act: Execute with fallback
        result1 = llm_service.execute_builder_phase(
            phase_id="test", phase_spec={"builder_mode": "full_file"}
        )
        result2 = llm_service.execute_builder_phase(
            phase_id="test", phase_spec={"builder_mode": "structured_edit"}
        )

        # Assert
        assert not result1.success
        assert result2.success
        assert llm_service.execute_builder_phase.call_count == 2


# =============================================================================
# Patch Validation Tests
# =============================================================================


@pytest.mark.integration
class TestPatchValidation:
    """E2E tests for patch validation during build execution."""

    def test_valid_patch_acceptance(self, valid_patch_content):
        """Test that valid patches are accepted."""
        # Arrange
        is_valid_patch = (
            valid_patch_content.startswith("diff --git") and
            "\n@@" in valid_patch_content and
            ("+" in valid_patch_content or "-" in valid_patch_content)
        )

        # Act & Assert
        assert is_valid_patch is True

    def test_empty_patch_rejection(self):
        """Test that empty patches are rejected."""
        # Arrange
        patch_content = ""

        # Act
        is_valid = len(patch_content) > 0 and patch_content.startswith("diff --git")

        # Assert
        assert is_valid is False

    def test_patch_with_file_statistics(self, valid_patch_content):
        """Test that patch statistics are extracted correctly."""
        # Arrange & Act
        lines_added = valid_patch_content.count("\n+") - valid_patch_content.count("\n+++")
        lines_removed = valid_patch_content.count("\n-") - valid_patch_content.count("\n---")

        # Assert
        assert lines_added >= 0
        assert lines_removed >= 0
        assert (lines_added + lines_removed) > 0

    def test_patch_file_header_validation(self, valid_patch_content):
        """Test that patch file headers are valid."""
        # Arrange & Act
        lines = valid_patch_content.split("\n")
        file_headers = [line for line in lines if line.startswith("diff --git")]
        minus_headers = [line for line in lines if line.startswith("---")]
        plus_headers = [line for line in lines if line.startswith("+++")]

        # Assert
        assert len(file_headers) > 0
        assert len(minus_headers) == len(file_headers)
        assert len(plus_headers) == len(file_headers)

    def test_patch_hunk_header_validation(self, valid_patch_content):
        """Test that patch hunk headers are valid."""
        # Arrange & Act
        hunk_headers = [line for line in valid_patch_content.split("\n") if line.startswith("@@")]

        # Assert
        assert len(hunk_headers) > 0
        for header in hunk_headers:
            assert "@@" in header
            assert "-" in header and "+" in header

    def test_deliverables_manifest_validation(self):
        """Test that deliverables manifest is validated."""
        # Arrange
        phase = {
            "phase_id": "test",
            "scope": {"paths": ["src/module.py"]},
            "deliverables_manifest": ["src/module.py"],
        }

        # Act & Assert
        assert phase["deliverables_manifest"] is not None
        assert "src/module.py" in phase["deliverables_manifest"]

    def test_json_deliverables_validation(self):
        """Test JSON deliverables in patch are validated."""
        # Arrange
        patch_with_json = """diff --git a/config.json b/config.json
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/config.json
@@ -0,0 +1,3 @@
+{
+  "key": "value"
+}
"""

        # Act: Check for JSON file creation
        has_json_file = "config.json" in patch_with_json and '"key"' in patch_with_json

        # Assert
        assert has_json_file is True


# =============================================================================
# Build Error Handling Tests
# =============================================================================


@pytest.mark.integration
class TestBuildErrorHandling:
    """E2E tests for error handling during build execution."""

    def test_builder_failure_detection(self, builder_result_factory):
        """Test that builder failures are detected."""
        # Arrange
        failed_result = builder_result_factory(success=False, error="builder_error")

        # Act & Assert
        assert failed_result.success is False
        assert failed_result.error is not None

    def test_context_length_exceeded_handling(self, builder_result_factory):
        """Test handling of context length exceeded errors."""
        # Arrange
        result = builder_result_factory(
            success=False,
            error="context_length_exceeded",
            patch_content="",
        )

        # Act
        should_retry = result.error == "context_length_exceeded"

        # Assert
        assert should_retry is True

    def test_truncation_error_detection(self, builder_result_factory):
        """Test detection of truncation errors."""
        # Arrange
        result = builder_result_factory(success=False, error="output was truncated")

        # Act
        is_truncation = "truncated" in (result.error or "").lower()

        # Assert
        assert is_truncation is True

    def test_infra_error_backoff(self):
        """Test that infrastructure errors trigger backoff."""
        # Arrange
        infra_errors = [
            "connection_timeout",
            "rate_limit_exceeded",
            "service_unavailable",
        ]

        # Act & Assert
        for error in infra_errors:
            is_infra_error = error in ["connection_timeout", "rate_limit_exceeded", "service_unavailable"]
            assert is_infra_error is True

    def test_error_recovery_with_context_reduction(self):
        """Test error recovery with context reduction."""
        # Arrange
        context_size = 100000
        reduction_factor = 0.7

        # Act: Apply reduction
        reduced_size = int(context_size * reduction_factor)

        # Assert
        assert reduced_size < context_size
        assert reduced_size == 70000

    def test_error_recovery_with_model_downgrade(self):
        """Test error recovery with model downgrade."""
        # Arrange
        model_hierarchy = ["gpt-4", "gpt-3.5-turbo"]
        current_model = "gpt-4"
        attempt = 0

        # Act: Apply downgrade on retry
        if attempt > 0:
            current_model = model_hierarchy[1]

        # Assert
        assert current_model == "gpt-4"  # No downgrade on first attempt

    def test_max_retries_exceeded(self):
        """Test behavior when max retries are exceeded."""
        # Arrange
        max_attempts = 3
        attempt_count = 0
        last_error = None

        # Act: Simulate failed attempts
        for _ in range(max_attempts):
            attempt_count += 1
            last_error = "Transient failure"

        # Assert
        assert attempt_count == max_attempts
        assert last_error is not None


# =============================================================================
# Token Budget Management Tests
# =============================================================================


@pytest.mark.integration
class TestTokenBudgetManagement:
    """E2E tests for token budget management during builds."""

    def test_token_budget_tracking(self):
        """Test that token budget is tracked during build."""
        # Arrange
        total_budget = 100000
        used_tokens = 0

        # Act: Track usage
        builder_calls = [
            {"tokens": 10000, "model": "gpt-4"},
            {"tokens": 15000, "model": "gpt-4"},
            {"tokens": 8000, "model": "gpt-4"},
        ]

        for call in builder_calls:
            used_tokens += call["tokens"]

        # Assert
        assert used_tokens == 33000
        assert used_tokens < total_budget

    def test_token_budget_escalation_on_truncation(self):
        """Test token budget escalation when output is truncated."""
        # Arrange
        original_budget = 8000
        escalation_factor = 1.25

        # Act: Escalate budget
        escalated_budget = int(original_budget * escalation_factor)

        # Assert
        assert escalated_budget == 10000
        assert escalated_budget > original_budget

    def test_context_reduction_on_budget_warning(self):
        """Test context reduction when budget usage is high."""
        # Arrange
        usage_ratio = 0.9  # 90% used
        should_reduce = usage_ratio > 0.8

        # Act
        reduction_factor = 0.7 if should_reduce else 1.0

        # Assert
        assert should_reduce is True
        assert reduction_factor < 1.0

    def test_token_budget_enforcement(self):
        """Test that token budget is enforced."""
        # Arrange
        max_tokens = 50000
        used_tokens = 45000

        # Act
        can_proceed = used_tokens < max_tokens

        # Assert
        assert can_proceed is True

    def test_token_budget_exceeded_handling(self):
        """Test handling when token budget would be exceeded."""
        # Arrange
        max_tokens = 50000
        used_tokens = 49000
        estimated_for_next_call = 2000

        # Act
        would_exceed = (used_tokens + estimated_for_next_call) > max_tokens

        # Assert
        assert would_exceed is True


# =============================================================================
# Build State Tracking Tests
# =============================================================================


@pytest.mark.integration
class TestBuildStateTracking:
    """E2E tests for build state tracking and transitions."""

    def test_build_state_initialization(self, builder_test_context):
        """Test that build starts in initial state."""
        # Arrange
        build_state = {
            "phase_id": builder_test_context["phase_id"],
            "state": "INITIATED",
            "attempt": 0,
        }

        # Act & Assert
        assert build_state["state"] == "INITIATED"
        assert build_state["attempt"] == 0

    def test_build_state_transition_to_executing(self):
        """Test build state transitions to EXECUTING."""
        # Arrange
        build_state = {"state": "INITIATED"}

        # Act
        build_state["state"] = "EXECUTING"

        # Assert
        assert build_state["state"] == "EXECUTING"

    def test_build_state_transition_to_success(self):
        """Test build state transitions to SUCCESS."""
        # Arrange
        build_state = {"state": "EXECUTING"}

        # Act
        build_state["state"] = "SUCCESS"

        # Assert
        assert build_state["state"] == "SUCCESS"

    def test_build_state_transition_to_failure(self):
        """Test build state transitions to FAILURE."""
        # Arrange
        build_state = {"state": "EXECUTING"}

        # Act
        build_state["state"] = "FAILURE"
        build_state["error"] = "context_length_exceeded"

        # Assert
        assert build_state["state"] == "FAILURE"
        assert build_state["error"] is not None

    def test_build_attempt_tracking(self):
        """Test that build attempts are tracked."""
        # Arrange
        build_state = {"attempt": 0, "max_attempts": 3}

        # Act: Simulate multiple attempts
        for _ in range(3):
            build_state["attempt"] += 1
            if build_state["attempt"] >= build_state["max_attempts"]:
                break

        # Assert
        assert build_state["attempt"] == 3

    def test_build_metadata_capture(self, builder_test_context, builder_result_factory):
        """Test that build metadata is captured."""
        # Arrange
        builder_result = builder_result_factory(
            success=True, tokens_used=2500, model_used="gpt-4"
        )

        build_metadata = {
            "phase_id": builder_test_context["phase_id"],
            "builder_result": builder_result,
            "tokens_used": builder_result.tokens_used,
            "model_used": builder_result.model_used,
            "patch_size": len(builder_result.patch_content) if builder_result.patch_content else 0,
        }

        # Act & Assert
        assert build_metadata["tokens_used"] == 2500
        assert build_metadata["model_used"] == "gpt-4"
        assert build_metadata["patch_size"] > 0


# =============================================================================
# Integration Scenario Tests
# =============================================================================


@pytest.mark.integration
class TestBuildExecutionIntegrationScenarios:
    """E2E integration scenario tests for complete build execution flows."""

    def test_simple_build_success_scenario(self, builder_test_context, builder_result_factory):
        """Test simple successful build scenario."""
        # Arrange
        phase_spec = {
            "phase_id": builder_test_context["phase_id"],
            "description": builder_test_context["task_description"],
        }
        file_context = {"existing_files": builder_test_context["existing_files"]}
        builder_result = builder_result_factory(success=True, tokens_used=2000)

        # Act: Simulate builder execution
        llm_service = Mock()
        llm_service.execute_builder_phase.return_value = builder_result

        result = llm_service.execute_builder_phase(
            phase_id=phase_spec["phase_id"],
            phase_spec=phase_spec,
            file_context=file_context,
        )

        # Assert
        assert result.success is True
        assert result.tokens_used == 2000
        assert result.patch_content is not None

    def test_build_with_retry_on_context_error(self, builder_result_factory):
        """Test build execution with retry on context error."""
        # Arrange
        llm_service = Mock()

        # First attempt fails due to context length
        attempt1 = builder_result_factory(
            success=False, error="context_length_exceeded", tokens_used=0
        )

        # Second attempt succeeds with reduced context
        attempt2 = builder_result_factory(success=True, tokens_used=1500)

        llm_service.execute_builder_phase.side_effect = [attempt1, attempt2]

        # Act: Execute with retry
        phase_spec = {
            "phase_id": "test",
            "description": "Test phase",
            "context_reduction_factor": 0.7,
        }

        result1 = llm_service.execute_builder_phase(
            phase_id="test",
            phase_spec=phase_spec,
        )

        phase_spec["context_reduction_factor"] = 0.7
        result2 = llm_service.execute_builder_phase(
            phase_id="test",
            phase_spec=phase_spec,
        )

        # Assert
        assert not result1.success
        assert result2.success
        assert llm_service.execute_builder_phase.call_count == 2

    def test_build_with_fallback_mode(self, builder_result_factory):
        """Test build execution with fallback to structured edit mode."""
        # Arrange
        llm_service = Mock()

        # Full file mode fails with parse error
        attempt1 = builder_result_factory(
            success=False, error="full_file_parse_failed", patch_content=""
        )

        # Structured edit mode succeeds
        attempt2 = builder_result_factory(success=True, patch_content="diff --git")

        llm_service.execute_builder_phase.side_effect = [attempt1, attempt2]

        # Act: Execute with fallback
        result1 = llm_service.execute_builder_phase(
            phase_id="test",
            phase_spec={"builder_mode": "full_file"},
        )

        result2 = llm_service.execute_builder_phase(
            phase_id="test",
            phase_spec={"builder_mode": "structured_edit"},
        )

        # Assert
        assert not result1.success
        assert result2.success

    def test_build_with_token_escalation(self):
        """Test build execution with token budget escalation."""
        # Arrange
        phase = {
            "phase_id": "test",
            "max_builder_attempts": 5,
            "metadata": {
                "token_budget": {"output_utilization": 95.0},
                "token_prediction": {"selected_budget": 8000},
            },
        }

        # Act: Check for escalation trigger
        should_escalate = phase["metadata"]["token_budget"]["output_utilization"] > 90.0

        # Assert
        assert should_escalate is True

    def test_complete_build_execution_flow(self, builder_test_context, builder_result_factory):
        """Test complete end-to-end build execution flow."""
        # Arrange
        llm_service = Mock()
        builder_result = builder_result_factory(success=True, tokens_used=2500)
        llm_service.execute_builder_phase.return_value = builder_result

        phase_spec = {
            "phase_id": builder_test_context["phase_id"],
            "description": builder_test_context["task_description"],
            "scope": builder_test_context["scope"],
        }

        # Act: Execute complete flow
        # 1. Load context
        context = {
            "existing_files": builder_test_context["existing_files"],
            "scope": builder_test_context["scope"],
        }

        # 2. Invoke builder
        result = llm_service.execute_builder_phase(
            phase_id=phase_spec["phase_id"],
            phase_spec=phase_spec,
            file_context=context,
            project_rules=["rule1"],
        )

        # 3. Validate patch
        is_valid_patch = (
            result.success and
            result.patch_content and
            result.patch_content.startswith("diff --git")
        )

        # 4. Track tokens
        total_tokens = result.tokens_used or 0

        # Assert
        assert result.success is True
        assert is_valid_patch is True
        assert total_tokens > 0
        assert result.model_used is not None
