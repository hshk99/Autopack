"""Contract tests for IntentionAnchorV2 schema.

Tests validate that:
- Valid samples pass validation
- Invalid samples fail with clear error messages
- Tests run offline and deterministically
"""

import pytest
from datetime import datetime, timezone

from autopack.schema_validation import (
    validate_intention_anchor_v2,
    SchemaValidationError,
)


def test_minimal_valid_intention_anchor_v2():
    """Test minimal valid IntentionAnchorV2 artifact."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {},
    }

    # Should not raise
    validate_intention_anchor_v2(data)


def test_full_valid_intention_anchor_v2():
    """Test complete valid IntentionAnchorV2 with all pivot types."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "updated_at": "2026-01-06T12:30:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890abcdef1234567890",
        "pivot_intentions": {
            "north_star": {
                "desired_outcomes": ["Build safe autonomous system"],
                "success_signals": ["All tests pass", "No drift detected"],
                "non_goals": ["Not a production system yet"],
            },
            "safety_risk": {
                "never_allow": ["Direct SOT writes from executor"],
                "requires_approval": ["Baseline updates", "Schema changes"],
                "risk_tolerance": "low",
            },
            "evidence_verification": {
                "hard_blocks": ["CI must pass"],
                "required_proofs": ["Phase proof artifacts"],
                "verification_gates": ["Quality gate"],
            },
            "scope_boundaries": {
                "allowed_write_roots": [".autonomous_runs/"],
                "protected_paths": ["docs/", ".git/"],
                "network_allowlist": ["api.anthropic.com"],
            },
            "budget_cost": {
                "token_cap_global": 1000000,
                "token_cap_per_call": 10000,
                "time_cap_seconds": 3600,
                "cost_escalation_policy": "request_approval",
            },
            "memory_continuity": {
                "persist_to_sot": ["build_history", "debug_log"],
                "derived_indexes": ["sot_entries", "qdrant"],
                "retention_rules": {"phase_proofs": "30_days"},
            },
            "governance_review": {
                "default_policy": "deny",
                "auto_approve_rules": [
                    {
                        "rule_id": "safe_test_runs",
                        "description": "Auto-approve test-only runs",
                        "conditions": ["no_writes", "test_scope_only"],
                    }
                ],
                "approval_channels": ["PR", "CLI", "Telegram"],
            },
            "parallelism_isolation": {
                "allowed": True,
                "isolation_model": "four_layer",
                "max_concurrent_runs": 4,
            },
        },
        "metadata": {
            "author": "test-user",
            "source": "manual",
            "tags": ["test", "prototype"],
        },
    }

    # Should not raise
    validate_intention_anchor_v2(data)


def test_missing_required_field():
    """Test that missing required fields fail validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        # Missing: created_at, raw_input_digest, pivot_intentions
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    errors = exc_info.value.errors
    assert len(errors) >= 3
    assert any("created_at" in err for err in errors)
    assert any("raw_input_digest" in err for err in errors)
    assert any("pivot_intentions" in err for err in errors)


def test_invalid_format_version():
    """Test that invalid format_version fails validation."""
    data = {
        "format_version": "v1",  # Wrong version
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {},
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("format_version" in err for err in exc_info.value.errors)


def test_invalid_date_time_format():
    """Test that invalid ISO 8601 date-time fails validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "not-a-date",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {},
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("date-time" in err.lower() for err in exc_info.value.errors)


def test_invalid_digest_pattern():
    """Test that invalid digest pattern fails validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "invalid!digest",  # Not hex
        "pivot_intentions": {},
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("pattern" in err.lower() for err in exc_info.value.errors)


def test_invalid_risk_tolerance_enum():
    """Test that invalid enum value fails validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {
            "safety_risk": {
                "risk_tolerance": "ultra-high",  # Not in enum
            }
        },
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("risk_tolerance" in err for err in exc_info.value.errors)


def test_invalid_budget_negative():
    """Test that negative budget values fail validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {
            "budget_cost": {
                "token_cap_global": -1000,  # Negative not allowed
            }
        },
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("minimum" in err.lower() for err in exc_info.value.errors)


def test_invalid_parallelism_isolation_model():
    """Test that invalid isolation model fails validation."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {
            "parallelism_isolation": {
                "allowed": True,
                "isolation_model": "three_layer",  # Not in enum
            }
        },
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_intention_anchor_v2(data)

    assert any("isolation_model" in err for err in exc_info.value.errors)


def test_deterministic_validation():
    """Test that validation is deterministic (same input always gives same result)."""
    data = {
        "format_version": "v2",
        "project_id": "test-project",
        "created_at": "2026-01-06T12:00:00+00:00",
        "raw_input_digest": "a1b2c3d4e5f67890",
        "pivot_intentions": {},
    }

    # Run validation multiple times
    for _ in range(3):
        validate_intention_anchor_v2(data)  # Should not raise

    # Test that errors are also deterministic
    invalid_data = {
        "format_version": "v2",
        "project_id": "test-project",
        # Missing required fields
    }

    errors_1 = None
    errors_2 = None

    try:
        validate_intention_anchor_v2(invalid_data)
    except SchemaValidationError as e:
        errors_1 = sorted(e.errors)

    try:
        validate_intention_anchor_v2(invalid_data)
    except SchemaValidationError as e:
        errors_2 = sorted(e.errors)

    assert errors_1 == errors_2
