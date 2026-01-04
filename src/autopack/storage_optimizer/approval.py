"""
Execution safety gate with approval artifacts for storage optimizer.

Implements Track 3 from implementation plan:
- Requires approval artifact before destructive actions
- Deterministic report_id via SHA-256 hash
- Hashed audit trail
- Prevents accidental execution without explicit approval

Design:
1. Generate report.json with deterministic report_id = sha256(normalized_report)
2. Require approval.json containing matching report_id + timestamp + operator
3. Only execute deletions if approval.report_id == report.report_id
4. Log all actions to audit.jsonl with hashes
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


@dataclass
class ExecutionApproval:
    """
    Approval artifact for storage optimizer execution.

    Attributes:
        report_id: SHA-256 hash of normalized report (deterministic)
        timestamp: ISO 8601 timestamp when approval was granted
        operator: Identity of approving operator (email or username)
        notes: Optional approval notes or justification
    """
    report_id: str
    timestamp: str
    operator: str
    notes: Optional[str] = None

    @classmethod
    def from_file(cls, approval_path: Path) -> ExecutionApproval:
        """Load approval from JSON file."""
        with open(approval_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return cls(
            report_id=data['report_id'],
            timestamp=data['timestamp'],
            operator=data['operator'],
            notes=data.get('notes')
        )

    def to_file(self, approval_path: Path) -> None:
        """Save approval to JSON file."""
        approval_path.parent.mkdir(parents=True, exist_ok=True)
        with open(approval_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


def compute_report_id(report: Dict) -> str:
    """
    Compute deterministic report ID via SHA-256 hash.

    Normalizes report before hashing to ensure determinism:
    - Sort all dictionary keys
    - Remove volatile fields (generated_at, runtime_seconds)
    - Ensure consistent JSON serialization

    Args:
        report: Report dictionary

    Returns:
        SHA-256 hash (hex string)
    """
    # Create normalized copy
    normalized = _normalize_dict(report)

    # Remove volatile fields
    if 'metadata' in normalized:
        normalized['metadata'].pop('generated_at', None)
        normalized['metadata'].pop('runtime_seconds', None)

    # Serialize to canonical JSON (sorted keys, no whitespace)
    canonical_json = json.dumps(normalized, sort_keys=True, separators=(',', ':'))

    # Compute SHA-256
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def _normalize_dict(d: Dict) -> Dict:
    """Recursively normalize dictionary for deterministic hashing."""
    if not isinstance(d, dict):
        return d

    normalized = {}
    for key in sorted(d.keys()):
        value = d[key]
        if isinstance(value, dict):
            normalized[key] = _normalize_dict(value)
        elif isinstance(value, list):
            normalized[key] = [
                _normalize_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            normalized[key] = value

    return normalized


def verify_approval(
    report: Dict,
    approval: ExecutionApproval
) -> tuple[bool, Optional[str]]:
    """
    Verify that approval matches report.

    Args:
        report: Report dictionary
        approval: Approval artifact

    Returns:
        (is_valid, error_message) tuple
    """
    report_id = compute_report_id(report)

    if report_id != approval.report_id:
        return False, (
            f"Approval report_id mismatch:\n"
            f"  Expected (from report): {report_id}\n"
            f"  Got (from approval):    {approval.report_id}\n"
            f"  This approval is for a different report."
        )

    return True, None


@dataclass
class AuditEntry:
    """
    Single audit log entry for destructive action.

    Attributes:
        timestamp: ISO 8601 timestamp
        action: Type of action (delete, move, archive)
        src: Source path
        dest: Destination path (for move/archive actions)
        bytes: File size in bytes
        policy_reason: Why this action was taken (duplicate, stale, archive, etc.)
        sha256_before: SHA-256 hash of file before action
        sha256_after: SHA-256 hash after action (for verification)
        report_id: Report ID this action belongs to
        operator: Who approved this action
    """
    timestamp: str
    action: str
    src: str
    dest: Optional[str]
    bytes: int
    policy_reason: str
    sha256_before: Optional[str]
    sha256_after: Optional[str]
    report_id: str
    operator: str

    def to_jsonl_line(self) -> str:
        """Serialize to JSONL format (one JSON object per line)."""
        return json.dumps(asdict(self), ensure_ascii=False)


class AuditLog:
    """
    Hashed audit trail for storage optimizer executions.

    Writes JSONL (JSON Lines) format for easy parsing and streaming.
    """

    def __init__(self, audit_path: Path):
        """
        Initialize audit log.

        Args:
            audit_path: Path to audit.jsonl file
        """
        self.audit_path = audit_path
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: AuditEntry) -> None:
        """
        Append entry to audit log.

        Args:
            entry: Audit entry to append
        """
        with open(self.audit_path, 'a', encoding='utf-8') as f:
            f.write(entry.to_jsonl_line() + '\n')

    def log_delete(
        self,
        src: Path,
        bytes_deleted: int,
        policy_reason: str,
        sha256_before: str,
        report_id: str,
        operator: str
    ) -> None:
        """Log a file deletion."""
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            action='delete',
            src=str(src),
            dest=None,
            bytes=bytes_deleted,
            policy_reason=policy_reason,
            sha256_before=sha256_before,
            sha256_after=None,
            report_id=report_id,
            operator=operator
        )
        self.append(entry)

    def log_move(
        self,
        src: Path,
        dest: Path,
        bytes_moved: int,
        policy_reason: str,
        sha256_before: str,
        sha256_after: str,
        report_id: str,
        operator: str
    ) -> None:
        """Log a file move/archive."""
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat() + 'Z',
            action='move',
            src=str(src),
            dest=str(dest),
            bytes=bytes_moved,
            policy_reason=policy_reason,
            sha256_before=sha256_before,
            sha256_after=sha256_after,
            report_id=report_id,
            operator=operator
        )
        self.append(entry)


def generate_approval_template(report: Dict, output_path: Path) -> None:
    """
    Generate approval template for operator to fill out.

    Args:
        report: Report dictionary
        output_path: Path to save approval template
    """
    report_id = compute_report_id(report)

    template = {
        "report_id": report_id,
        "timestamp": "<ISO 8601 timestamp when approval granted>",
        "operator": "<operator email or username>",
        "notes": "<optional: approval justification or notes>"
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, indent=2, ensure_ascii=False)

    print(f"✅ Approval template generated: {output_path}")
    print()
    print("To approve execution:")
    print(f"  1. Edit {output_path}")
    print("  2. Replace <placeholders> with actual values")
    print("  3. Save the file")
    print(f"  4. Run: python scripts/storage/execute.py --approval-file {output_path} --execute")


def hash_file(file_path: Path) -> str:
    """Compute SHA-256 hash of file for audit trail."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()
