"""Contract tests for GapReportV1 schema.

Tests validate that:
- Valid samples pass validation
- Invalid samples fail with clear error messages
- Tests run offline and deterministically
"""

from datetime import datetime, timezone

import pytest

from autopack.schema_validation import (SchemaValidationError,
                                        validate_gap_report_v1)


def test_minimal_valid_gap_report_v1():
    """Test minimal valid GapReportV1 artifact."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gaps": [],
    }

    # Should not raise
    validate_gap_report_v1(data)


def test_full_valid_gap_report_v1():
    """Test complete valid GapReportV1 with gaps."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "workspace_state_digest": "abc123def4567890",
        "gaps": [
            {
                "gap_id": "gap-001",
                "gap_type": "doc_drift",
                "title": "README SOT summary drift",
                "description": "SOT summary in README is out of date",
                "detection_signals": [
                    "docs-sot-integrity CI job failed",
                    "README last updated: 2025-01-01",
                ],
                "evidence": {
                    "file_paths": ["README.md"],
                    "test_names": ["test_readme_sot_summary"],
                    "excerpts": [
                        {
                            "source": "README.md:50-60",
                            "content_hash": "abc123",
                            "preview": "<!-- SOT_SUMMARY_START -->",
                        }
                    ],
                },
                "risk_classification": "medium",
                "blocks_autopilot": False,
                "safe_remediation": {
                    "approach": "Run tidy with --execute",
                    "requires_approval": True,
                    "estimated_actions": 1,
                },
            },
            {
                "gap_id": "gap-002",
                "gap_type": "test_infra_drift",
                "title": "Flaky boundary test",
                "description": "test_api_endpoint is flaky",
                "detection_signals": ["Test failed 3/10 runs"],
                "evidence": {
                    "file_paths": ["tests/test_api.py"],
                    "test_names": ["test_api_endpoint"],
                },
                "risk_classification": "high",
                "blocks_autopilot": True,
                "safe_remediation": {
                    "approach": "Rewrite test to exercise real runtime path",
                    "requires_approval": True,
                    "estimated_actions": 2,
                },
            },
        ],
        "summary": {
            "total_gaps": 2,
            "critical_gaps": 0,
            "high_gaps": 1,
            "medium_gaps": 1,
            "low_gaps": 0,
            "autopilot_blockers": 1,
        },
        "metadata": {
            "scanner_version": "1.0.0",
            "scan_duration_ms": 1250,
        },
    }

    # Should not raise
    validate_gap_report_v1(data)


def test_missing_required_fields():
    """Test that missing required fields fail validation."""
    data = {
        "format_version": "v1",
        # Missing: project_id, run_id, generated_at, gaps
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    errors = exc_info.value.errors
    assert len(errors) >= 4
    assert any("project_id" in err for err in errors)
    assert any("run_id" in err for err in errors)
    assert any("generated_at" in err for err in errors)
    assert any("gaps" in err for err in errors)


def test_invalid_format_version():
    """Test that invalid format_version fails validation."""
    data = {
        "format_version": "v2",  # Wrong version
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    assert any("format_version" in err for err in exc_info.value.errors)


def test_invalid_gap_type_enum():
    """Test that invalid gap_type fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [
            {
                "gap_id": "gap-001",
                "gap_type": "not_a_valid_type",  # Not in enum
                "detection_signals": ["signal"],
                "risk_classification": "medium",
                "blocks_autopilot": False,
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    assert any("gap_type" in err for err in exc_info.value.errors)


def test_invalid_risk_classification_enum():
    """Test that invalid risk_classification fails validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [
            {
                "gap_id": "gap-001",
                "gap_type": "doc_drift",
                "detection_signals": ["signal"],
                "risk_classification": "super-critical",  # Not in enum
                "blocks_autopilot": False,
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    assert any("risk_classification" in err for err in exc_info.value.errors)


def test_missing_gap_required_fields():
    """Test that gaps missing required fields fail validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [
            {
                "gap_id": "gap-001",
                # Missing: gap_type, detection_signals, risk_classification, blocks_autopilot
            }
        ],
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    errors = exc_info.value.errors
    assert any("gap_type" in err for err in errors)
    assert any("detection_signals" in err for err in errors)
    assert any("risk_classification" in err for err in errors)
    assert any("blocks_autopilot" in err for err in errors)


def test_negative_summary_values():
    """Test that negative summary values fail validation."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [],
        "summary": {
            "total_gaps": -1,  # Negative not allowed
        },
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_gap_report_v1(data)

    assert any("minimum" in err.lower() for err in exc_info.value.errors)


def test_deterministic_validation():
    """Test that validation is deterministic."""
    data = {
        "format_version": "v1",
        "project_id": "test-project",
        "run_id": "test-run-001",
        "generated_at": "2026-01-06T12:00:00+00:00",
        "gaps": [
            {
                "gap_id": "gap-001",
                "gap_type": "doc_drift",
                "detection_signals": ["CI failed"],
                "risk_classification": "medium",
                "blocks_autopilot": False,
            }
        ],
    }

    # Run validation multiple times
    for _ in range(3):
        validate_gap_report_v1(data)  # Should not raise
