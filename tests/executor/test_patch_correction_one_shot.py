"""Contract-first tests for patch correction one-shot loop (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Max 1 correction attempt per 422 event
- Evidence recorded (inputs, error summary, result)
- Stops after one attempt regardless of outcome
"""

from __future__ import annotations

import json


def test_should_attempt_correction_within_budget():
    """Correction should be attempted when budget allows."""
    from autopack.executor.patch_correction import should_attempt_patch_correction

    http_422_detail = {
        "error": "validation_failed",
        "message": "Field 'name' is required",
        "path": "$.data.name",
    }

    result = should_attempt_patch_correction(http_422_detail, budget_remaining=0.5)

    assert result is True


def test_should_not_attempt_correction_low_budget():
    """Correction should not be attempted when budget is too low."""
    from autopack.executor.patch_correction import should_attempt_patch_correction

    http_422_detail = {
        "error": "validation_failed",
        "message": "Field 'name' is required",
    }

    # Budget too low (< 10% remaining)
    result = should_attempt_patch_correction(http_422_detail, budget_remaining=0.05)

    assert result is False


def test_correct_patch_once_returns_result():
    """Correction attempt returns structured result."""
    from autopack.executor.patch_correction import (
        CorrectedPatchResult,
        correct_patch_once,
    )

    original_patch = '{"data": {}}'
    validator_error = {
        "error": "validation_failed",
        "message": "Field 'name' is required",
        "path": "$.data.name",
    }
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(original_patch, validator_error, context)

    assert isinstance(result, CorrectedPatchResult)
    assert result.attempted is True
    assert result.original_patch == original_patch
    assert result.error_detail == validator_error


def test_correct_patch_once_records_evidence():
    """Correction attempt records evidence regardless of success/failure."""
    from autopack.executor.patch_correction import correct_patch_once

    original_patch = '{"data": {}}'
    validator_error = {
        "error": "validation_failed",
        "message": "Invalid schema",
    }
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(original_patch, validator_error, context)

    # Evidence must be present
    assert result.evidence is not None
    assert "timestamp" in result.evidence
    assert "inputs_hash" in result.evidence
    assert "error_summary" in result.evidence


def test_correct_patch_max_one_attempt():
    """Only one correction attempt is made per 422 event."""
    from autopack.executor.patch_correction import PatchCorrectionTracker

    tracker = PatchCorrectionTracker()

    original_patch = '{"data": {}}'
    validator_error = {"error": "validation_failed", "message": "Invalid"}
    context = {"phase_id": "phase-1", "run_id": "test-run", "event_id": "evt-422-001"}

    # First attempt
    result1 = tracker.attempt_correction(original_patch, validator_error, context)
    assert result1.attempted is True

    # Second attempt for same event_id should be blocked
    result2 = tracker.attempt_correction(original_patch, validator_error, context)
    assert result2.attempted is False
    assert result2.blocked_reason == "max_attempts_exceeded"


def test_correct_patch_different_events_allowed():
    """Different 422 events can each have one correction attempt."""
    from autopack.executor.patch_correction import PatchCorrectionTracker

    tracker = PatchCorrectionTracker()

    # First event
    context1 = {"phase_id": "phase-1", "run_id": "test-run", "event_id": "evt-422-001"}
    result1 = tracker.attempt_correction('{"a": 1}', {"error": "e1"}, context1)
    assert result1.attempted is True

    # Different event
    context2 = {"phase_id": "phase-1", "run_id": "test-run", "event_id": "evt-422-002"}
    result2 = tracker.attempt_correction('{"b": 2}', {"error": "e2"}, context2)
    assert result2.attempted is True


def test_corrected_patch_result_serializable():
    """CorrectedPatchResult can be serialized to JSON for artifact storage."""
    from autopack.executor.patch_correction import CorrectedPatchResult

    result = CorrectedPatchResult(
        attempted=True,
        original_patch='{"data": {}}',
        error_detail={"error": "validation_failed"},
        corrected_patch='{"data": {"name": "fixed"}}',
        correction_successful=True,
        evidence={
            "timestamp": "2025-01-01T12:00:00+00:00",
            "inputs_hash": "abc123",
            "error_summary": "Missing required field",
        },
        blocked_reason=None,
    )

    # Should be JSON serializable
    json_str = json.dumps(result.to_dict())
    parsed = json.loads(json_str)

    assert parsed["attempted"] is True
    assert parsed["correction_successful"] is True


def test_patch_correction_no_retry_on_failure():
    """Failed correction does not trigger automatic retry."""
    from autopack.executor.patch_correction import PatchCorrectionTracker

    tracker = PatchCorrectionTracker()

    context = {"phase_id": "phase-1", "run_id": "test-run", "event_id": "evt-422-001"}

    # First attempt (simulating failure internally)
    _ = tracker.attempt_correction('{"bad": true}', {"error": "complex"}, context)

    # Even if correction failed, no retry allowed
    result2 = tracker.attempt_correction('{"bad": true}', {"error": "complex"}, context)

    assert result2.attempted is False
    assert result2.blocked_reason == "max_attempts_exceeded"


# BUILD-195: LLM correction tests


def test_llm_correction_with_custom_caller():
    """LLM correction can use custom caller for testability."""
    from autopack.executor.patch_correction import correct_patch_once

    # Mock LLM caller that returns a fixed corrected patch
    def mock_llm_caller(prompt: str) -> str:
        return '{"data": {"fixed": "by_llm"}}'

    # Use an error that won't trigger simple rule-based correction
    # (simple rules only handle "required" or "missing" keywords)
    original_patch = '{"data": {"wrong_type": 123}}'
    validator_error = {
        "error": "type_error",
        "message": "Expected string, got number at $.data.wrong_type",
        "path": "$.data.wrong_type",
    }
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(
        original_patch, validator_error, context, llm_caller=mock_llm_caller
    )

    assert result.correction_successful is True
    assert result.corrected_patch == '{"data": {"fixed": "by_llm"}}'
    assert result.evidence["correction_method"] == "llm"


def test_llm_correction_fallback_on_simple_rule_success():
    """When simple rules succeed, LLM is not called."""
    from autopack.executor.patch_correction import correct_patch_once

    call_count = [0]

    def mock_llm_caller(prompt: str) -> str:
        call_count[0] += 1
        return '{"should_not_be_used": true}'

    # This error pattern triggers simple rule-based correction
    original_patch = '{"data": {}}'
    validator_error = {
        "error": "validation_failed",
        "message": "Field 'name' is required",
        "path": "$.data.name",
    }
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(
        original_patch, validator_error, context, llm_caller=mock_llm_caller
    )

    # Simple rules should have succeeded, LLM should not be called
    assert result.correction_successful is True
    assert result.evidence["correction_method"] == "rule_based"
    assert call_count[0] == 0  # LLM was not called


def test_llm_correction_records_method_in_evidence():
    """Evidence includes which correction method was used."""
    from autopack.executor.patch_correction import correct_patch_once

    def mock_llm_caller(prompt: str) -> str:
        return '{"fixed": true}'

    # Error that simple rules won't fix
    original_patch = '{"complex_structure": "invalid"}'
    validator_error = {
        "error": "schema_mismatch",
        "message": "Expected array, got string",
    }
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(
        original_patch, validator_error, context, llm_caller=mock_llm_caller
    )

    assert result.evidence is not None
    assert "correction_method" in result.evidence
    # Since simple rules won't match, LLM should be used
    assert result.evidence["correction_method"] == "llm"


def test_tracker_with_llm_caller():
    """PatchCorrectionTracker passes LLM caller to correction function."""
    from autopack.executor.patch_correction import PatchCorrectionTracker

    def mock_llm_caller(prompt: str) -> str:
        return '{"llm_corrected": true}'

    tracker = PatchCorrectionTracker(llm_caller=mock_llm_caller)

    # Error that simple rules won't fix
    original_patch = '{"invalid": "structure"}'
    validator_error = {"error": "type_mismatch", "message": "Expected number"}
    context = {"phase_id": "phase-1", "run_id": "test-run", "event_id": "evt-001"}

    result = tracker.attempt_correction(original_patch, validator_error, context)

    assert result.attempted is True
    # LLM should have been called since simple rules don't match
    assert result.evidence["correction_method"] == "llm"


def test_llm_correction_strips_markdown_code_blocks():
    """LLM response with markdown code blocks is cleaned."""
    from autopack.executor.patch_correction import correct_patch_once

    def mock_llm_with_markdown(prompt: str) -> str:
        return """```json
{"cleaned": "patch"}
```"""

    original_patch = '{"invalid": true}'
    validator_error = {"error": "syntax", "message": "Parse error"}
    context = {"phase_id": "phase-1", "run_id": "test-run"}

    result = correct_patch_once(
        original_patch, validator_error, context, llm_caller=mock_llm_with_markdown
    )

    assert result.correction_successful is True
    # Code block markers should be stripped
    assert result.corrected_patch == '{"cleaned": "patch"}'
