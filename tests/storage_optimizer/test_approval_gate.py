"""
Tests for storage optimizer approval gate (BUILD Track 3).

Tests verify:
- Report ID generation is deterministic
- Approval verification works correctly
- Audit log entries are recorded
- Safety gates prevent execution without approval
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.storage_optimizer.approval import (AuditEntry, AuditLog,
                                                 ExecutionApproval,
                                                 compute_report_id,
                                                 generate_approval_template,
                                                 hash_file, verify_approval)


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_report():
    """Sample report for testing."""
    return {
        "metadata": {
            "generated_at": "2026-01-03T16:00:00Z",
            "scan_root": "/path/to/scan",
            "total_files": 1000,
            "runtime_seconds": 5.42,
        },
        "recommendations": [
            {
                "action": "delete",
                "path": "/path/to/duplicate.txt",
                "reason": "duplicate",
                "bytes": 1024,
            },
            {"action": "archive", "path": "/path/to/old.log", "reason": "stale", "bytes": 2048},
        ],
        "summary": {"total_space_reclaimable": 3072, "total_recommendations": 2},
    }


def test_report_id_is_deterministic(sample_report):
    """Test that report ID is deterministic for same report."""
    id1 = compute_report_id(sample_report)
    id2 = compute_report_id(sample_report)

    assert id1 == id2
    assert len(id1) == 64  # SHA-256 hex length


def test_report_id_ignores_volatile_fields(sample_report):
    """Test that report ID ignores volatile fields like timestamps."""
    id1 = compute_report_id(sample_report)

    # Change volatile fields
    report2 = sample_report.copy()
    report2["metadata"] = sample_report["metadata"].copy()
    report2["metadata"]["generated_at"] = "2026-01-04T10:00:00Z"  # Different timestamp
    report2["metadata"]["runtime_seconds"] = 99.99  # Different runtime

    id2 = compute_report_id(report2)

    # IDs should still match
    assert id1 == id2


def test_report_id_detects_content_changes(sample_report):
    """Test that report ID changes when content changes."""
    id1 = compute_report_id(sample_report)

    # Change actual content
    report2 = sample_report.copy()
    report2["recommendations"] = [sample_report["recommendations"][0]]  # Remove one recommendation

    id2 = compute_report_id(report2)

    # IDs should differ
    assert id1 != id2


def test_execution_approval_roundtrip(temp_dir):
    """Test saving and loading approval artifact."""
    approval = ExecutionApproval(
        report_id="abc123",
        timestamp="2026-01-03T16:00:00Z",
        operator="test@example.com",
        notes="Test approval",
    )

    approval_path = temp_dir / "approval.json"
    approval.to_file(approval_path)

    # Load back
    loaded = ExecutionApproval.from_file(approval_path)

    assert loaded.report_id == approval.report_id
    assert loaded.timestamp == approval.timestamp
    assert loaded.operator == approval.operator
    assert loaded.notes == approval.notes


def test_verify_approval_success(sample_report):
    """Test approval verification succeeds for matching report ID."""
    report_id = compute_report_id(sample_report)

    approval = ExecutionApproval(
        report_id=report_id, timestamp="2026-01-03T16:00:00Z", operator="test@example.com"
    )

    is_valid, error = verify_approval(sample_report, approval)

    assert is_valid
    assert error is None


def test_verify_approval_failure_mismatched_id(sample_report):
    """Test approval verification fails for mismatched report ID."""
    approval = ExecutionApproval(
        report_id="wrong_id_12345", timestamp="2026-01-03T16:00:00Z", operator="test@example.com"
    )

    is_valid, error = verify_approval(sample_report, approval)

    assert not is_valid
    assert "mismatch" in error.lower()
    assert "wrong_id_12345" in error


def test_audit_log_delete_entry(temp_dir):
    """Test audit log records delete action correctly."""
    audit_path = temp_dir / "audit.jsonl"
    audit_log = AuditLog(audit_path)

    audit_log.log_delete(
        src=Path("/path/to/file.txt"),
        bytes_deleted=1024,
        policy_reason="duplicate",
        sha256_before="abc123",
        report_id="report_001",
        operator="test@example.com",
    )

    # Read back
    with open(audit_path, "r") as f:
        line = f.readline()

    entry = json.loads(line)
    assert entry["action"] == "delete"
    assert entry["src"] == str(Path("/path/to/file.txt"))
    assert entry["bytes"] == 1024
    assert entry["policy_reason"] == "duplicate"
    assert entry["sha256_before"] == "abc123"
    assert entry["report_id"] == "report_001"
    assert entry["operator"] == "test@example.com"


def test_audit_log_move_entry(temp_dir):
    """Test audit log records move action correctly."""
    audit_path = temp_dir / "audit.jsonl"
    audit_log = AuditLog(audit_path)

    audit_log.log_move(
        src=Path("/path/to/file.txt"),
        dest=Path("/archive/file.txt"),
        bytes_moved=2048,
        policy_reason="archive",
        sha256_before="abc123",
        sha256_after="def456",
        report_id="report_002",
        operator="test@example.com",
    )

    # Read back
    with open(audit_path, "r") as f:
        line = f.readline()

    entry = json.loads(line)
    assert entry["action"] == "move"
    assert entry["src"] == str(Path("/path/to/file.txt"))
    assert entry["dest"] == str(Path("/archive/file.txt"))
    assert entry["sha256_before"] == "abc123"
    assert entry["sha256_after"] == "def456"


def test_audit_log_multiple_entries(temp_dir):
    """Test audit log handles multiple entries (JSONL format)."""
    audit_path = temp_dir / "audit.jsonl"
    audit_log = AuditLog(audit_path)

    # Log multiple actions
    audit_log.log_delete(
        src=Path("/file1.txt"),
        bytes_deleted=100,
        policy_reason="duplicate",
        sha256_before="hash1",
        report_id="report_001",
        operator="user@example.com",
    )

    audit_log.log_move(
        src=Path("/file2.txt"),
        dest=Path("/archive/file2.txt"),
        bytes_moved=200,
        policy_reason="archive",
        sha256_before="hash2",
        sha256_after="hash2",
        report_id="report_001",
        operator="user@example.com",
    )

    # Read back all entries
    with open(audit_path, "r") as f:
        lines = f.readlines()

    assert len(lines) == 2
    entry1 = json.loads(lines[0])
    entry2 = json.loads(lines[1])

    assert entry1["action"] == "delete"
    assert entry2["action"] == "move"


def test_generate_approval_template(temp_dir, sample_report, capsys):
    """Test approval template generation."""
    output_path = temp_dir / "approval_template.json"

    generate_approval_template(sample_report, output_path)

    # Check template was created
    assert output_path.exists()

    # Load and verify template
    with open(output_path, "r") as f:
        template = json.load(f)

    report_id = compute_report_id(sample_report)
    assert template["report_id"] == report_id
    assert "<" in template["timestamp"]  # Placeholder
    assert "<" in template["operator"]  # Placeholder

    # Check output guidance
    captured = capsys.readouterr()
    assert "approval template generated" in captured.out.lower()
    assert str(output_path) in captured.out


def test_hash_file(temp_dir):
    """Test file hashing for audit trail."""
    test_file = temp_dir / "test.txt"
    test_file.write_bytes(b"Hello, world!")

    hash1 = hash_file(test_file)
    assert len(hash1) == 64  # SHA-256 hex

    # Same file should have same hash
    hash2 = hash_file(test_file)
    assert hash1 == hash2

    # Different content should have different hash
    test_file.write_bytes(b"Different content")
    hash3 = hash_file(test_file)
    assert hash3 != hash1


def test_audit_entry_jsonl_format():
    """Test audit entry serializes to valid JSONL."""
    entry = AuditEntry(
        timestamp="2026-01-03T16:00:00Z",
        action="delete",
        src="/path/to/file.txt",
        dest=None,
        bytes=1024,
        policy_reason="duplicate",
        sha256_before="abc123",
        sha256_after=None,
        report_id="report_001",
        operator="test@example.com",
    )

    jsonl_line = entry.to_jsonl_line()

    # Should be valid JSON
    parsed = json.loads(jsonl_line)
    assert parsed["action"] == "delete"
    assert parsed["bytes"] == 1024

    # Should not have newline (JSONL adds it separately)
    assert "\n" not in jsonl_line


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
