"""Contract tests for service/doctor.py.

These tests verify the Doctor subsystem's behavior independently
of the full LlmService, using mock LLM responses.
"""

from __future__ import annotations

import json
import pytest

from autopack.service.doctor import (
    DOCTOR_SYSTEM_PROMPT,
    DoctorCallResult,
    DoctorDiagnosisContext,
    build_doctor_user_message,
    parse_doctor_json,
    create_default_doctor_response,
    validate_doctor_action,
    validate_fix_type,
    calculate_health_ratio,
    should_consider_rollback,
)
from autopack.error_recovery import DoctorRequest, DoctorResponse


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_doctor_request() -> DoctorRequest:
    """Create a sample DoctorRequest for testing."""
    return DoctorRequest(
        phase_id="phase-123",
        error_category="patch_apply_error",
        builder_attempts=2,
        run_id="run-456",
        health_budget={
            "http_500": 1,
            "patch_failures": 3,
            "total_failures": 4,
            "total_cap": 25,
        },
        patch_errors=[
            {"error_type": "context_mismatch", "message": "Line 42 does not match"},
        ],
        last_patch="--- a/foo.py\n+++ b/foo.py\n@@ -40,3 +40,4 @@\n context",
        logs_excerpt="Error: Failed to apply patch to foo.py",
    )


@pytest.fixture
def minimal_doctor_request() -> DoctorRequest:
    """Create a minimal DoctorRequest for testing."""
    return DoctorRequest(
        phase_id="phase-minimal",
        error_category="infra_error",
        builder_attempts=1,
        health_budget={"total_failures": 0, "total_cap": 25},
    )


# ============================================================================
# DOCTOR_SYSTEM_PROMPT tests
# ============================================================================


class TestDoctorSystemPrompt:
    """Tests for the Doctor system prompt."""

    def test_prompt_contains_json_instruction(self) -> None:
        assert "JSON object" in DOCTOR_SYSTEM_PROMPT

    def test_prompt_lists_valid_actions(self) -> None:
        assert "retry_with_fix" in DOCTOR_SYSTEM_PROMPT
        assert "replan" in DOCTOR_SYSTEM_PROMPT
        assert "rollback_run" in DOCTOR_SYSTEM_PROMPT
        assert "skip_phase" in DOCTOR_SYSTEM_PROMPT
        assert "mark_fatal" in DOCTOR_SYSTEM_PROMPT
        assert "execute_fix" in DOCTOR_SYSTEM_PROMPT

    def test_prompt_has_execute_fix_guidelines(self) -> None:
        assert "execute_fix Guidelines" in DOCTOR_SYSTEM_PROMPT
        assert "git" in DOCTOR_SYSTEM_PROMPT
        assert "file" in DOCTOR_SYSTEM_PROMPT
        assert "python" in DOCTOR_SYSTEM_PROMPT

    def test_prompt_warns_about_infrastructure_only(self) -> None:
        assert "INFRASTRUCTURE" in DOCTOR_SYSTEM_PROMPT
        assert "NOT code logic" in DOCTOR_SYSTEM_PROMPT


# ============================================================================
# build_doctor_user_message tests
# ============================================================================


class TestBuildDoctorUserMessage:
    """Tests for build_doctor_user_message function."""

    def test_includes_phase_id(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "phase-123" in message

    def test_includes_error_category(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "patch_apply_error" in message

    def test_includes_builder_attempts(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "Builder Attempts**: 2" in message

    def test_includes_health_budget(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "HTTP 500 errors: 1" in message
        assert "Patch failures: 3" in message
        assert "Total failures: 4" in message
        assert "Total cap: 25" in message

    def test_includes_patch_errors(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "Patch Validation Errors" in message
        assert "context_mismatch" in message

    def test_includes_last_patch_truncated(
        self, sample_doctor_request: DoctorRequest
    ) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "Last Patch (truncated)" in message
        assert "foo.py" in message

    def test_includes_logs_excerpt(self, sample_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(sample_doctor_request)
        assert "Relevant Logs" in message
        assert "Failed to apply patch" in message

    def test_minimal_request_works(self, minimal_doctor_request: DoctorRequest) -> None:
        message = build_doctor_user_message(minimal_doctor_request)
        assert "phase-minimal" in message
        assert "infra_error" in message
        # Should not have optional sections
        assert "Patch Validation Errors" not in message
        assert "Last Patch" not in message


# ============================================================================
# parse_doctor_json tests
# ============================================================================


class TestParseDoctorJson:
    """Tests for parse_doctor_json function."""

    def test_parses_clean_json(self) -> None:
        content = json.dumps({
            "action": "retry_with_fix",
            "confidence": 0.85,
            "rationale": "Simple patch error",
            "builder_hint": "Re-read the file",
        })
        response = parse_doctor_json(content)

        assert response.action == "retry_with_fix"
        assert response.confidence == 0.85
        assert response.rationale == "Simple patch error"
        assert response.builder_hint == "Re-read the file"

    def test_extracts_json_from_markdown_block(self) -> None:
        content = """Here's my analysis:

```json
{
  "action": "replan",
  "confidence": 0.7,
  "rationale": "Phase spec is ambiguous"
}
```

Let me know if you need more details."""
        response = parse_doctor_json(content)

        assert response.action == "replan"
        assert response.confidence == 0.7

    def test_extracts_json_from_text(self) -> None:
        content = """After analyzing the failure, I recommend:
{"action": "skip_phase", "confidence": 0.6, "rationale": "Optional phase"}
This should help."""
        response = parse_doctor_json(content)

        assert response.action == "skip_phase"
        assert response.confidence == 0.6

    def test_extracts_fields_via_regex(self) -> None:
        # Malformed JSON but with extractable fields
        content = '"action": "mark_fatal", "confidence": 0.3, "rationale": "Unrecoverable"}'
        response = parse_doctor_json(content)

        assert response.action == "mark_fatal"
        assert response.confidence == 0.3

    def test_returns_default_for_unparseable(self) -> None:
        content = "This is not JSON at all, just random text."
        response = parse_doctor_json(content)

        # Should return conservative default
        assert response.action == "replan"
        assert response.confidence == 0.4
        assert "Could not parse" in response.rationale

    def test_handles_empty_content(self) -> None:
        response = parse_doctor_json("")

        assert response.action == "replan"
        assert response.confidence == 0.4


# ============================================================================
# create_default_doctor_response tests
# ============================================================================


class TestCreateDefaultDoctorResponse:
    """Tests for create_default_doctor_response function."""

    def test_creates_replan_response(self) -> None:
        response = create_default_doctor_response("Connection timeout")

        assert response.action == "replan"
        assert response.confidence == 0.2
        assert "Connection timeout" in response.rationale

    def test_truncates_long_error(self) -> None:
        long_error = "x" * 200
        response = create_default_doctor_response(long_error)

        # Rationale should contain truncated error
        assert len(response.rationale) < 200

    def test_has_no_hints_or_patches(self) -> None:
        response = create_default_doctor_response("Error")

        assert response.builder_hint is None
        assert response.suggested_patch is None


# ============================================================================
# validate_doctor_action tests
# ============================================================================


class TestValidateDoctorAction:
    """Tests for validate_doctor_action function."""

    def test_valid_actions(self) -> None:
        assert validate_doctor_action("retry_with_fix") is True
        assert validate_doctor_action("replan") is True
        assert validate_doctor_action("rollback_run") is True
        assert validate_doctor_action("skip_phase") is True
        assert validate_doctor_action("mark_fatal") is True
        assert validate_doctor_action("execute_fix") is True

    def test_invalid_actions(self) -> None:
        assert validate_doctor_action("invalid") is False
        assert validate_doctor_action("") is False
        assert validate_doctor_action("REPLAN") is False  # Case sensitive


# ============================================================================
# validate_fix_type tests
# ============================================================================


class TestValidateFixType:
    """Tests for validate_fix_type function."""

    def test_valid_fix_types(self) -> None:
        assert validate_fix_type("git") is True
        assert validate_fix_type("file") is True
        assert validate_fix_type("python") is True

    def test_invalid_fix_types(self) -> None:
        assert validate_fix_type("shell") is False
        assert validate_fix_type("bash") is False
        assert validate_fix_type("") is False


# ============================================================================
# calculate_health_ratio tests
# ============================================================================


class TestCalculateHealthRatio:
    """Tests for calculate_health_ratio function."""

    def test_zero_failures(self) -> None:
        budget = {"total_failures": 0, "total_cap": 25}
        assert calculate_health_ratio(budget) == 0.0

    def test_half_budget_used(self) -> None:
        budget = {"total_failures": 10, "total_cap": 20}
        assert calculate_health_ratio(budget) == 0.5

    def test_full_budget_used(self) -> None:
        budget = {"total_failures": 25, "total_cap": 25}
        assert calculate_health_ratio(budget) == 1.0

    def test_over_budget(self) -> None:
        budget = {"total_failures": 30, "total_cap": 25}
        assert calculate_health_ratio(budget) == 1.2

    def test_handles_missing_keys(self) -> None:
        # Missing total_failures defaults to 0
        budget = {"total_cap": 25}
        assert calculate_health_ratio(budget) == 0.0

    def test_handles_zero_cap(self) -> None:
        # Zero cap should use 1 to avoid division by zero
        budget = {"total_failures": 5, "total_cap": 0}
        assert calculate_health_ratio(budget) == 5.0


# ============================================================================
# should_consider_rollback tests
# ============================================================================


class TestShouldConsiderRollback:
    """Tests for should_consider_rollback function."""

    def test_below_threshold_no_rollback(self) -> None:
        budget = {"total_failures": 10, "total_cap": 25}  # 0.4 ratio
        assert should_consider_rollback(budget) is False

    def test_at_threshold_rollback(self) -> None:
        budget = {"total_failures": 20, "total_cap": 25}  # 0.8 ratio
        assert should_consider_rollback(budget) is True

    def test_above_threshold_rollback(self) -> None:
        budget = {"total_failures": 24, "total_cap": 25}  # 0.96 ratio
        assert should_consider_rollback(budget) is True

    def test_custom_threshold(self) -> None:
        budget = {"total_failures": 15, "total_cap": 25}  # 0.6 ratio
        assert should_consider_rollback(budget, threshold=0.5) is True
        assert should_consider_rollback(budget, threshold=0.7) is False


# ============================================================================
# DoctorDiagnosisContext tests
# ============================================================================


class TestDoctorDiagnosisContext:
    """Tests for DoctorDiagnosisContext dataclass."""

    def test_initial_state(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")

        assert ctx.phase_id == "phase-1"
        assert ctx.error_categories == []
        assert ctx.escalation_count == 0
        assert ctx.last_model is None

    def test_record_error_category(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")

        ctx.record_error_category("patch_error")
        ctx.record_error_category("infra_error")

        assert "patch_error" in ctx.error_categories
        assert "infra_error" in ctx.error_categories

    def test_record_error_category_deduplicates(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")

        ctx.record_error_category("patch_error")
        ctx.record_error_category("patch_error")

        assert ctx.error_categories.count("patch_error") == 1

    def test_record_error_category_ignores_empty(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")

        ctx.record_error_category("")
        ctx.record_error_category(None)  # type: ignore[arg-type]

        assert len(ctx.error_categories) == 0

    def test_record_escalation(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")

        ctx.record_escalation("claude-opus-4-5")

        assert ctx.escalation_count == 1
        assert ctx.last_model == "claude-opus-4-5"

    def test_has_diverse_errors_false(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")
        ctx.record_error_category("error1")
        ctx.record_error_category("error2")

        assert ctx.has_diverse_errors() is False

    def test_has_diverse_errors_true(self) -> None:
        ctx = DoctorDiagnosisContext(phase_id="phase-1")
        ctx.record_error_category("error1")
        ctx.record_error_category("error2")
        ctx.record_error_category("error3")

        assert ctx.has_diverse_errors() is True


# ============================================================================
# DoctorCallResult dataclass tests
# ============================================================================


class TestDoctorCallResult:
    """Tests for DoctorCallResult dataclass."""

    def test_frozen_dataclass(self) -> None:
        response = DoctorResponse(
            action="replan",
            confidence=0.5,
            rationale="test",
        )
        result = DoctorCallResult(
            response=response,
            model_used="claude-sonnet-4-5",
            tokens_used=500,
            prompt_tokens=400,
            completion_tokens=100,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            result.model_used = "changed"  # type: ignore[misc]

    def test_with_token_split(self) -> None:
        response = DoctorResponse(action="retry_with_fix", confidence=0.9, rationale="ok")
        result = DoctorCallResult(
            response=response,
            model_used="gpt-4o",
            tokens_used=300,
            prompt_tokens=200,
            completion_tokens=100,
        )

        assert result.tokens_used == 300
        assert result.prompt_tokens == 200
        assert result.completion_tokens == 100

    def test_without_token_split(self) -> None:
        response = DoctorResponse(action="replan", confidence=0.6, rationale="test")
        result = DoctorCallResult(
            response=response,
            model_used="gemini-2.5-pro",
            tokens_used=500,
            prompt_tokens=None,
            completion_tokens=None,
        )

        assert result.tokens_used == 500
        assert result.prompt_tokens is None
        assert result.completion_tokens is None
