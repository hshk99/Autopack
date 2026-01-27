"""Contract tests for autopilot_session_v1.schema.json."""

from datetime import datetime, timezone

import pytest

from autopack.schema_validation import (
    SchemaValidationError,
    validate_autopilot_session_v1,
)


def test_minimal_valid_autopilot_session_v1():
    """Test minimal valid AutopilotSessionV1."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "running",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
    }
    validate_autopilot_session_v1(data)  # Should not raise


def test_full_valid_autopilot_session_v1():
    """Test full valid AutopilotSessionV1 with all fields."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T00:05:00Z",
        "status": "completed",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "execution_summary": {
            "total_actions": 5,
            "auto_approved_actions": 3,
            "executed_actions": 3,
            "successful_actions": 2,
            "failed_actions": 1,
            "blocked_actions": 0,
        },
        "executed_action_ids": ["action-1", "action-2", "action-3"],
        "approval_requests": [],
        "error_log": [
            {
                "timestamp": "2025-01-01T00:03:00Z",
                "action_id": "action-3",
                "error_type": "ExecutionError",
                "error_message": "Test execution failed",
            }
        ],
        "metadata": {
            "autopilot_version": "0.1.0",
            "session_duration_ms": 300000,
            "enabled_explicitly": True,
        },
    }
    validate_autopilot_session_v1(data)  # Should not raise


def test_blocked_approval_required_autopilot_session_v1():
    """Test AutopilotSessionV1 with blocked status and approval requests."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-blocked",
        "started_at": "2025-01-01T00:00:00Z",
        "completed_at": "2025-01-01T00:01:00Z",
        "status": "blocked_approval_required",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "execution_summary": {
            "total_actions": 5,
            "auto_approved_actions": 0,
            "executed_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "blocked_actions": 2,
        },
        "executed_action_ids": [],
        "blocked_reason": "2 action(s) blocked by governance; 3 action(s) require manual approval",
        "approval_requests": [
            {
                "action_id": "action-1",
                "approval_status": "blocked",
                "reason": "High risk: modifies protected paths",
            },
            {
                "action_id": "action-2",
                "approval_status": "blocked",
                "reason": "High risk: git operation on main branch",
            },
            {
                "action_id": "action-3",
                "approval_status": "requires_approval",
                "reason": "Default-deny: manual review required",
            },
        ],
    }
    validate_autopilot_session_v1(data)  # Should not raise


def test_missing_required_field_format_version():
    """Test that missing format_version is rejected."""
    data = {
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "running",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "format_version" in error_str


def test_invalid_status_value():
    """Test that invalid status value is rejected."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "invalid_status",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "status" in error_str


def test_invalid_approval_status_in_request():
    """Test that invalid approval_status in approval_requests is rejected."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "blocked_approval_required",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "approval_requests": [
            {
                "action_id": "action-1",
                "approval_status": "auto_approved",  # Invalid for approval_requests
                "reason": "Should be requires_approval or blocked",
            }
        ],
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "approval_status" in error_str


def test_execution_summary_negative_counts():
    """Test that negative counts in execution_summary are rejected."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "completed",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "execution_summary": {
            "total_actions": -5,  # Invalid: negative count
            "auto_approved_actions": 0,
            "executed_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "blocked_actions": 0,
        },
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "total_actions" in error_str


def test_missing_approval_request_required_field():
    """Test that missing required field in approval_requests is rejected."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "blocked_approval_required",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "approval_requests": [
            {
                "action_id": "action-1",
                # Missing approval_status
                "reason": "Some reason",
            }
        ],
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "approval_status" in error_str


def test_error_log_entry_missing_timestamp():
    """Test that missing timestamp in error_log is rejected."""
    data = {
        "format_version": "v1",
        "project_id": "autopack",
        "run_id": "test-run-001",
        "session_id": "autopilot-abc123",
        "started_at": "2025-01-01T00:00:00Z",
        "status": "failed",
        "anchor_id": "abc123def4567890",
        "gap_report_id": "gap-xyz789",
        "plan_proposal_id": "plan-xyz789",
        "error_log": [
            {
                # Missing timestamp
                "error_type": "RuntimeError",
                "error_message": "Something went wrong",
            }
        ],
    }
    with pytest.raises(SchemaValidationError) as exc_info:
        validate_autopilot_session_v1(data)
    error_str = str(exc_info.value) + " ".join(exc_info.value.errors)
    assert "timestamp" in error_str


def test_pydantic_model_roundtrip():
    """Test that AutopilotSessionV1 Pydantic model can roundtrip through schema validation."""
    from autopack.autonomy.models import (
        ApprovalRequest,
        AutopilotSessionV1,
        ExecutionSummary,
    )

    session = AutopilotSessionV1(
        format_version="v1",
        project_id="autopack",
        run_id="test-run-001",
        session_id="autopilot-roundtrip",
        started_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc),
        status="blocked_approval_required",
        anchor_id="abc123def4567890",
        gap_report_id="gap-xyz789",
        plan_proposal_id="plan-xyz789",
        execution_summary=ExecutionSummary(
            total_actions=3,
            auto_approved_actions=0,
            executed_actions=0,
            successful_actions=0,
            failed_actions=0,
            blocked_actions=1,
        ),
        blocked_reason="1 action(s) blocked by governance",
        approval_requests=[
            ApprovalRequest(
                action_id="action-1",
                approval_status="blocked",
                reason="High risk operation",
            )
        ],
    )

    # Convert to JSON dict
    data = session.to_json_dict()

    # Validate against schema
    session.validate_against_schema()

    # Roundtrip
    session2 = AutopilotSessionV1.from_json_dict(data)
    assert session2.session_id == session.session_id
    assert session2.status == session.status
