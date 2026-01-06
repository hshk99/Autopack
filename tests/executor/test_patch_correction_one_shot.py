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
    from autopack.executor.patch_correction import (
        correct_patch_once,
    )

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
    from autopack.executor.patch_correction import (
        PatchCorrectionTracker,
    )

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
