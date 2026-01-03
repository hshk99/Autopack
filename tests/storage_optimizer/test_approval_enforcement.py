"""
Tests for approval artifact enforcement in storage optimizer execution.

Validates BUILD-165 requirement: execution safety gate must require
approval artifact before destructive actions.
"""

import pytest
from pathlib import Path
import json
import subprocess
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.storage_optimizer.approval import ExecutionApproval, compute_report_id


def test_execute_without_approval_file_refuses():
    """Test that --execute without --approval-file is refused."""
    # This test validates the CLI argument check, not the full execution path
    # We test with --dry-run to avoid needing a real database

    result = subprocess.run(
        [
            sys.executable,
            "scripts/storage/scan_and_report.py",
            "--execute",
            "--scan-id", "999",
            # Intentionally omit --approval-file
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )

    # Should fail with error about missing approval file
    # Note: Will also fail about missing scan, but approval check comes first
    assert result.returncode != 0
    # The error message should mention approval
    assert "--approval-file is required" in result.stdout or "approval" in result.stdout.lower()


def test_execute_with_missing_approval_file_refuses(temp_dir):
    """Test that --execute with non-existent approval file is refused."""
    nonexistent = temp_dir / "nonexistent_approval.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/storage/scan_and_report.py",
            "--execute",
            "--scan-id", "999",
            "--approval-file", str(nonexistent)
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )

    assert result.returncode != 0
    # Should mention the approval file not being found
    assert "not found" in result.stdout or "ERROR" in result.stdout


def test_execute_with_malformed_approval_file_refuses(temp_dir):
    """Test that --execute with malformed approval file is refused."""
    malformed = temp_dir / "malformed_approval.json"
    malformed.write_text("{ invalid json")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/storage/scan_and_report.py",
            "--execute",
            "--scan-id", "999",
            "--approval-file", str(malformed)
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )

    assert result.returncode != 0
    assert "Failed to load approval" in result.stdout or "ERROR" in result.stdout


def test_dry_run_does_not_require_approval():
    """Test that --dry-run mode does not require approval artifact."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/storage/scan_and_report.py",
            "--execute",
            "--dry-run",
            "--scan-id", "999",
            # Intentionally omit --approval-file
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent
    )

    # Will fail due to missing scan, but should not fail on missing approval
    # Check that it doesn't complain about missing approval file
    assert "--approval-file is required" not in result.stdout


def test_approval_artifact_roundtrip(temp_dir):
    """Test creating and loading an approval artifact."""
    approval_path = temp_dir / "test_approval.json"

    # Create approval
    approval = ExecutionApproval(
        report_id="abc123",
        timestamp="2026-01-03T12:00:00Z",
        operator="test_user",
        notes="Test approval"
    )

    # Save and reload
    approval.to_file(approval_path)
    loaded = ExecutionApproval.from_file(approval_path)

    assert loaded.report_id == "abc123"
    assert loaded.timestamp == "2026-01-03T12:00:00Z"
    assert loaded.operator == "test_user"
    assert loaded.notes == "Test approval"


def test_compute_report_id_deterministic():
    """Test that report_id computation is deterministic."""
    report = {
        "metadata": {
            "generated_at": "2026-01-03T12:00:00Z",  # Volatile field
            "runtime_seconds": 45.2,  # Volatile field
            "version": "1.0"
        },
        "summary": {
            "total_candidates": 100,
            "potential_savings_gb": 5.2
        },
        "candidates": [
            {"path": "/path/to/file1.txt", "size_bytes": 1024},
            {"path": "/path/to/file2.txt", "size_bytes": 2048}
        ]
    }

    # Compute report ID twice
    report_id_1 = compute_report_id(report)
    report_id_2 = compute_report_id(report)

    # Should be identical (deterministic)
    assert report_id_1 == report_id_2

    # Changing volatile fields should NOT change report ID
    report["metadata"]["generated_at"] = "2026-01-03T13:00:00Z"
    report["metadata"]["runtime_seconds"] = 60.5
    report_id_3 = compute_report_id(report)

    assert report_id_3 == report_id_1

    # Changing non-volatile fields SHOULD change report ID
    report["summary"]["total_candidates"] = 101
    report_id_4 = compute_report_id(report)

    assert report_id_4 != report_id_1


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for test files."""
    return tmp_path
