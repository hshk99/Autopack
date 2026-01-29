"""Contract tests for PlanProposalV1 schema.

Tests validate that:
- Valid samples pass validation
- Invalid samples fail with clear error messages
- Tests run offline and deterministically
"""

from datetime import datetime, timezone

import pytest

from autopack.schema_validation import (SchemaValidationError,
                                        validate_plan_proposal_v1)


def test_minimal_valid_plan_proposal_v1():
    """Test minimal valid PlanProposalV1 artifact."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [],
    }

    # Should not raise
    validate_plan_proposal_v1(data)


def test_full_valid_plan_proposal_v1():
    """Test complete valid PlanProposalV1 with actions."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "tidy_apply",
                "title": "Update README SOT summary",
                "description": "Run tidy to update README",
                "target_gap_ids": ["gap-001"],
                "risk_score": 0.2,
                "risk_factors": ["Modifies docs/"],
                "approval_status": "requires_approval",
                "approval_reason": "Modifies protected path",
                "target_paths": ["README.md"],
                "command": "python -m autopack.tidy --execute",
                "estimated_cost": {
                    "tokens": 500,
                    "time_seconds": 10,
                    "api_calls": 0,
                },
                "dependencies": [],
                "rollback_strategy": "git restore README.md",
            },
            {
                "action_id": "action-002",
                "action_type": "test_fix",
                "title": "Fix flaky test",
                "description": "Rewrite test to be deterministic",
                "target_gap_ids": ["gap-002"],
                "risk_score": 0.3,
                "risk_factors": ["Modifies tests"],
                "approval_status": "auto_approved",
                "approval_reason": "Low risk test-only change",
                "target_paths": ["tests/test_api.py"],
                "estimated_cost": {
                    "tokens": 2000,
                    "time_seconds": 60,
                    "api_calls": 2,
                },
                "dependencies": ["action-001"],
                "rollback_strategy": "git restore tests/test_api.py",
            },
        ],
        "summary": {
            "total_actions": 2,
            "auto_approved_actions": 1,
            "requires_approval_actions": 1,
            "blocked_actions": 0,
            "total_estimated_tokens": 2500,
            "total_estimated_time_seconds": 70,
        },
        "governance_checks": {
            "default_deny_applied": True,
            "never_auto_approve_violations": [],
            "protected_path_checks": [
                {
                    "path": "README.md",
                    "is_protected": True,
                    "action_id": "action-001",
                }
            ],
            "budget_compliance": {
                "within_global_cap": True,
                "within_per_call_cap": True,
                "estimated_usage_pct": 0.25,
            },
        },
        "metadata": {
            "proposer_version": "1.0.0",
            "generation_duration_ms": 350,
        },
    }

    # Should not raise
    validate_plan_proposal_v1(data)


def test_missing_required_fields():
    """Test that missing required fields fail validation."""
    data = {
        "format_version": "v1",
        # Missing: project_id, run_id, generated_at, anchor_id, gap_report_id, actions
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    errors = exc_info.value.errors
    assert len(errors) >= 6


def test_invalid_format_version():
    """Test that invalid format_version fails validation."""
    data = {
        "format_version": "v2",  # Wrong version
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    assert any("format_version" in err for err in exc_info.value.errors)


def test_invalid_action_type_enum():
    """Test that invalid action_type fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "not_valid",  # Not in enum
                "target_gap_ids": ["gap-001"],
                "risk_score": 0.5,
                "approval_status": "auto_approved",
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    assert any("action_type" in err for err in exc_info.value.errors)


def test_invalid_approval_status_enum():
    """Test that invalid approval_status fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "tidy_apply",
                "target_gap_ids": ["gap-001"],
                "risk_score": 0.5,
                "approval_status": "maybe_approved",  # Not in enum
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    assert any("approval_status" in err for err in exc_info.value.errors)


def test_invalid_risk_score_range():
    """Test that risk_score outside [0, 1] fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "tidy_apply",
                "target_gap_ids": ["gap-001"],
                "risk_score": 1.5,  # Outside valid range
                "approval_status": "auto_approved",
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    assert any("maximum" in err.lower() or "risk_score" in err for err in exc_info.value.errors)


def test_missing_action_required_fields():
    """Test that actions missing required fields fail validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                # Missing: action_type, target_gap_ids, risk_score, approval_status
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    errors = exc_info.value.errors
    assert any("action_type" in err for err in errors)
    assert any("target_gap_ids" in err for err in errors)
    assert any("risk_score" in err for err in errors)
    assert any("approval_status" in err for err in errors)


def test_negative_estimated_cost():
    """Test that negative estimated cost fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "tidy_apply",
                "target_gap_ids": ["gap-001"],
                "risk_score": 0.5,
                "approval_status": "auto_approved",
                "estimated_cost": {
                    "tokens": -100,  # Negative not allowed
                },
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_plan_proposal_v1(data)

    assert any("minimum" in err.lower() for err in exc_info.value.errors)


def test_deterministic_validation():
    """Test that validation is deterministic."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "anchor_id": "anchor-123",
        "gap_report_id": "gap-report-456",
        "actions": [
            {
                "action_id": "action-001",
                "action_type": "tidy_apply",
                "target_gap_ids": ["gap-001"],
                "risk_score": 0.2,
                "approval_status": "requires_approval",
            }
        ],
    }

    # Run validation multiple times
    for _ in range(3):
        validate_plan_proposal_v1(data)  # Should not raise
