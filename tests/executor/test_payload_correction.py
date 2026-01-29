"""Contract tests for payload schema correction (BUILD-195).

These tests verify correction of FastAPI 422 validation errors on builder_result POST.
These are PAYLOAD SCHEMA errors (missing fields, wrong types, extra keys).
"""

from __future__ import annotations

import json


def test_should_attempt_correction_within_budget():
    """Correction should be attempted when budget allows."""
    from autopack.executor.payload_correction import \
        should_attempt_payload_correction

    http_422_detail = [
        {
            "loc": ["body", "extra_field"],
            "msg": "extra fields not permitted",
            "type": "value_error.extra",
        }
    ]

    result = should_attempt_payload_correction(http_422_detail, budget_remaining=0.5)

    assert result is True


def test_should_not_attempt_correction_low_budget():
    """Correction should not be attempted when budget is too low."""
    from autopack.executor.payload_correction import \
        should_attempt_payload_correction

    http_422_detail = [
        {"loc": ["body", "status"], "msg": "field required", "type": "value_error.missing"}
    ]

    # Budget too low (< 10% remaining)
    result = should_attempt_payload_correction(http_422_detail, budget_remaining=0.05)

    assert result is False


def test_correct_payload_drops_extra_fields():
    """Correction should drop extra fields when extra='forbid' error."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "unknown_field": "should_be_dropped",
    }
    error_detail = [
        {
            "loc": ["body", "unknown_field"],
            "msg": "extra fields not permitted",
            "type": "value_error.extra",
        }
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.correction_successful is True
    assert result.corrected_payload is not None
    assert "unknown_field" not in result.corrected_payload
    assert "dropped_extra_field:unknown_field" in result.evidence["corrections_made"]


def test_correct_payload_adds_missing_optional_fields():
    """Correction should add defaults for missing optional fields."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        # Missing optional fields like notes, lines_added, etc.
    }
    error_detail = [
        {"loc": ["body", "notes"], "msg": "field required", "type": "value_error.missing"},
        {"loc": ["body", "lines_added"], "msg": "field required", "type": "value_error.missing"},
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.correction_successful is True
    assert result.corrected_payload["notes"] == ""
    assert result.corrected_payload["lines_added"] == 0


def test_correct_payload_coerces_string_to_int():
    """Correction should coerce string to int when type error."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "lines_added": "42",  # String instead of int
    }
    error_detail = [
        {
            "loc": ["body", "lines_added"],
            "msg": "value is not a valid integer",
            "type": "type_error.integer",
        }
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.correction_successful is True
    assert result.corrected_payload["lines_added"] == 42
    assert "coerced_type:lines_added" in result.evidence["corrections_made"]


def test_correct_payload_coerces_value_to_list():
    """Correction should wrap single value in list when list expected."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "files_changed": "single_file.py",  # String instead of list
    }
    error_detail = [
        {
            "loc": ["body", "files_changed"],
            "msg": "value is not a valid list",
            "type": "type_error.list",
        }
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.correction_successful is True
    assert result.corrected_payload["files_changed"] == ["single_file.py"]


def test_correct_payload_handles_multiple_errors():
    """Correction should handle multiple validation errors in one pass."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "extra_field": "drop_me",
        "lines_added": "10",  # String instead of int
    }
    error_detail = [
        {
            "loc": ["body", "extra_field"],
            "msg": "extra fields not permitted",
            "type": "value_error.extra",
        },
        {
            "loc": ["body", "lines_added"],
            "msg": "value is not a valid integer",
            "type": "type_error.integer",
        },
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.correction_successful is True
    assert "extra_field" not in result.corrected_payload
    assert result.corrected_payload["lines_added"] == 10
    assert len(result.evidence["corrections_made"]) == 2


def test_correct_payload_max_one_attempt():
    """Only one correction attempt is made per event (one-shot)."""
    from autopack.executor.payload_correction import PayloadCorrectionTracker

    tracker = PayloadCorrectionTracker()

    original_payload = {"phase_id": "phase-1", "run_id": "run-1", "status": "success"}
    error_detail = [{"loc": ["body", "extra"], "msg": "extra", "type": "value_error.extra"}]
    context = {"phase_id": "phase-1", "run_id": "run-1", "event_id": "evt-422-001"}

    # First attempt
    result1 = tracker.attempt_correction(original_payload, error_detail, context)
    assert result1.attempted is True

    # Second attempt for same event_id should be blocked
    result2 = tracker.attempt_correction(original_payload, error_detail, context)
    assert result2.attempted is False
    assert result2.blocked_reason == "max_attempts_exceeded"


def test_correct_payload_different_events_allowed():
    """Different 422 events can each have one correction attempt."""
    from autopack.executor.payload_correction import PayloadCorrectionTracker

    tracker = PayloadCorrectionTracker()

    # First event
    context1 = {"phase_id": "phase-1", "run_id": "run-1", "event_id": "evt-422-001"}
    result1 = tracker.attempt_correction(
        {"phase_id": "phase-1", "run_id": "run-1", "status": "success"},
        [],
        context1,
    )
    assert result1.attempted is True

    # Different event
    context2 = {"phase_id": "phase-1", "run_id": "run-1", "event_id": "evt-422-002"}
    result2 = tracker.attempt_correction(
        {"phase_id": "phase-2", "run_id": "run-1", "status": "success"},
        [],
        context2,
    )
    assert result2.attempted is True


def test_payload_correction_result_serializable():
    """PayloadCorrectionResult can be serialized to JSON for artifact storage."""
    from autopack.executor.payload_correction import PayloadCorrectionResult

    result = PayloadCorrectionResult(
        attempted=True,
        original_payload={"phase_id": "phase-1", "status": "success"},
        error_detail=[{"loc": ["body", "x"], "msg": "extra", "type": "value_error.extra"}],
        corrected_payload={"phase_id": "phase-1", "status": "success"},
        correction_successful=True,
        evidence={
            "timestamp": "2025-01-01T12:00:00+00:00",
            "inputs_hash": "abc123",
            "corrections_made": ["dropped_extra_field:x"],
        },
        blocked_reason=None,
    )

    # Should be JSON serializable
    json_str = json.dumps(result.to_dict())
    parsed = json.loads(json_str)

    assert parsed["attempted"] is True
    assert parsed["correction_successful"] is True


def test_payload_correction_no_retry_on_failure():
    """Failed correction does not trigger automatic retry."""
    from autopack.executor.payload_correction import PayloadCorrectionTracker

    tracker = PayloadCorrectionTracker()

    context = {"phase_id": "phase-1", "run_id": "run-1", "event_id": "evt-422-001"}

    # First attempt (will fail - can't fix missing required field without context)
    _ = tracker.attempt_correction(
        {"status": "success"},  # Missing phase_id and run_id
        [{"loc": ["body", "phase_id"], "msg": "field required", "type": "value_error.missing"}],
        context,
    )

    # Even if correction failed, no retry allowed
    result2 = tracker.attempt_correction(
        {"status": "success"},
        [{"loc": ["body", "phase_id"], "msg": "field required", "type": "value_error.missing"}],
        context,
    )

    assert result2.attempted is False
    assert result2.blocked_reason == "max_attempts_exceeded"


def test_correction_records_method_in_evidence():
    """Evidence includes which correction method was used."""
    from autopack.executor.payload_correction import correct_payload_once

    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "extra": "drop_me",
    }
    error_detail = [
        {"loc": ["body", "extra"], "msg": "extra fields not permitted", "type": "value_error.extra"}
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(original_payload, error_detail, context)

    assert result.evidence is not None
    assert "correction_method" in result.evidence
    assert result.evidence["correction_method"] == "rule_based"


def test_llm_correction_with_custom_caller():
    """LLM correction can use custom caller for testability."""
    from autopack.executor.payload_correction import correct_payload_once

    # Mock LLM caller that returns a fixed corrected payload
    def mock_llm_caller(prompt: str) -> str:
        return '{"phase_id": "phase-1", "run_id": "run-1", "status": "success"}'

    # Error that deterministic rules can't fix (unknown type error)
    original_payload = {
        "phase_id": "phase-1",
        "run_id": "run-1",
        "status": "success",
        "complex_error": {"nested": "value"},
    }
    error_detail = [
        {
            "loc": ["body", "complex_error"],
            "msg": "complex validation error",
            "type": "unknown_error",
        }
    ]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(
        original_payload, error_detail, context, llm_caller=mock_llm_caller
    )

    # Should fall back to LLM since deterministic rules don't match
    assert result.correction_successful is True
    assert result.evidence["correction_method"] == "llm"


def test_llm_correction_strips_markdown():
    """LLM response with markdown code blocks is cleaned."""
    from autopack.executor.payload_correction import correct_payload_once

    def mock_llm_with_markdown(prompt: str) -> str:
        return """```json
{"phase_id": "fixed", "run_id": "fixed", "status": "success"}
```"""

    original_payload = {"broken": "payload"}
    error_detail = [{"loc": ["body"], "msg": "unknown", "type": "unknown"}]
    context = {"phase_id": "phase-1", "run_id": "run-1"}

    result = correct_payload_once(
        original_payload, error_detail, context, llm_caller=mock_llm_with_markdown
    )

    assert result.correction_successful is True
    assert result.corrected_payload == {"phase_id": "fixed", "run_id": "fixed", "status": "success"}


def test_tracker_with_llm_caller():
    """PayloadCorrectionTracker passes LLM caller to correction function."""
    from autopack.executor.payload_correction import PayloadCorrectionTracker

    def mock_llm_caller(prompt: str) -> str:
        return '{"phase_id": "llm-fixed", "run_id": "run-1", "status": "success"}'

    tracker = PayloadCorrectionTracker(llm_caller=mock_llm_caller)

    # Error that deterministic rules won't fix
    original_payload = {"malformed": True}
    error_detail = [{"loc": ["body"], "msg": "complex", "type": "complex_error"}]
    context = {"phase_id": "phase-1", "run_id": "run-1", "event_id": "evt-001"}

    result = tracker.attempt_correction(original_payload, error_detail, context)

    assert result.attempted is True
    assert result.evidence["correction_method"] == "llm"


def test_parse_fastapi_422_detail_formats():
    """Should handle various FastAPI 422 detail formats."""
    from autopack.executor.payload_correction import _parse_fastapi_422_detail

    # List format (direct)
    errors1 = _parse_fastapi_422_detail([{"loc": ["body"], "msg": "err"}])
    assert len(errors1) == 1

    # Dict with detail key
    errors2 = _parse_fastapi_422_detail({"detail": [{"loc": ["body"], "msg": "err"}]})
    assert len(errors2) == 1

    # Empty
    errors3 = _parse_fastapi_422_detail([])
    assert len(errors3) == 0

    # Dict with detail key containing single error (standard FastAPI format)
    errors4 = _parse_fastapi_422_detail({"detail": [{"loc": ["body"], "msg": "error"}]})
    assert len(errors4) == 1
