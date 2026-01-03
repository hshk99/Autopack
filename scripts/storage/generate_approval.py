#!/usr/bin/env python3
"""
Storage Optimizer - Approval Artifact Generator

Generates approval artifacts from scan reports for safe cleanup execution.

This script bridges the gap between scanning and execution:
1. Operator reviews scan report (report.json)
2. Operator runs this script to generate approval artifacts
3. Execution script validates approval artifacts before cleanup

Workflow:
    # Step 1: Scan (generates report.json)
    python scripts/storage/scan_and_report.py --dir C:/target --report-out report.json

    # Step 2: Review report.json manually (human approval)

    # Step 3: Generate approval artifacts (this script)
    python scripts/storage/generate_approval.py --report report.json --operator NAME --out approval.json

    # Step 4: Execute cleanup (validates approval artifacts)
    python scripts/storage/scan_and_report.py --dir C:/target --execute --approval-file approval.json

Safety Features:
- Requires explicit operator name (audit trail)
- Validates report structure before generating approval
- Creates audit log entry with timestamp + operator + items count
- Approval artifacts tied to specific scan report (content hash)
- Approval file includes expiry timestamp (default: 7 days)

Exit codes:
    0 - Success (approval artifacts generated)
    1 - Invalid report file or validation errors
    2 - File I/O errors
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any


def validate_report_structure(report_data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate that report has required structure for approval generation.

    Returns:
        (is_valid, error_message)
    """
    required_fields = ["scan_dir", "total_items", "cleanup_candidates"]

    for field in required_fields:
        if field not in report_data:
            return False, f"Missing required field: {field}"

    if not isinstance(report_data["cleanup_candidates"], list):
        return False, "cleanup_candidates must be a list"

    if report_data["total_items"] == 0:
        return False, "No items in report (nothing to approve)"

    return True, ""


def compute_report_hash(report_data: Dict[str, Any]) -> str:
    """
    Compute stable hash of report content for approval binding.

    Uses cleanup_candidates + scan_dir to create a fingerprint.
    This ensures approval is tied to specific scan results.
    """
    # Stable representation of candidates (sorted by path for determinism)
    candidates = sorted(
        report_data["cleanup_candidates"],
        key=lambda x: x.get("path", "")
    )

    content = {
        "scan_dir": report_data["scan_dir"],
        "candidates": [
            {
                "path": c.get("path", ""),
                "size_bytes": c.get("size_bytes", 0),
                "category": c.get("category", "unknown")
            }
            for c in candidates
        ]
    }

    # JSON with sorted keys for stability
    content_json = json.dumps(content, sort_keys=True)
    return hashlib.sha256(content_json.encode("utf-8")).hexdigest()[:16]


def generate_approval_artifacts(
    report_path: Path,
    operator_name: str,
    output_path: Path,
    audit_log_path: Path,
    expiry_days: int = 7
) -> int:
    """
    Generate approval artifacts from scan report.

    Creates:
    1. approved_items.json - List of approved cleanup items
    2. approval_audit.log - Audit trail entry (appended)

    Returns:
        Exit code (0 = success, 1 = validation errors, 2 = I/O errors)
    """
    # Load report
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Report file not found: {report_path}")
        return 2
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in report file: {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Failed to read report: {e}")
        return 2

    # Validate report structure
    is_valid, error_msg = validate_report_structure(report_data)
    if not is_valid:
        print(f"[ERROR] Invalid report structure: {error_msg}")
        return 1

    # Compute report hash for approval binding
    report_hash = compute_report_hash(report_data)

    # Create approval artifact
    approval_data = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat(),
        "operator": operator_name,
        "report_hash": report_hash,
        "scan_dir": report_data["scan_dir"],
        "approved_items": report_data["cleanup_candidates"],
        "total_items": len(report_data["cleanup_candidates"]),
        "metadata": {
            "expiry_days": expiry_days,
            "source_report": str(report_path.resolve()),
            "generated_by": "scripts/storage/generate_approval.py"
        }
    }

    # Write approval file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(approval_data, f, indent=2)
        print(f"[OK] Approval file written: {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write approval file: {e}")
        return 2

    # Append audit log entry
    audit_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operator": operator_name,
        "action": "approval_generated",
        "report_hash": report_hash,
        "approved_items_count": len(report_data["cleanup_candidates"]),
        "scan_dir": report_data["scan_dir"],
        "approval_file": str(output_path.resolve()),
        "expires_at": approval_data["expires_at"]
    }

    try:
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")
        print(f"[OK] Audit log appended: {audit_log_path}")
    except Exception as e:
        print(f"[WARN] Failed to append audit log: {e}")
        # Don't fail if audit log write fails (approval file is primary)

    # Print summary
    print()
    print("=" * 70)
    print("APPROVAL ARTIFACTS GENERATED")
    print("=" * 70)
    print(f"Operator: {operator_name}")
    print(f"Report hash: {report_hash}")
    print(f"Approved items: {len(report_data['cleanup_candidates'])}")
    print(f"Scan directory: {report_data['scan_dir']}")
    print(f"Approval file: {output_path}")
    print(f"Expires: {approval_data['expires_at']}")
    print()
    print("Next steps:")
    print(f"  1. Review approval file: {output_path}")
    print(f"  2. Execute cleanup:")
    print(f"     python scripts/storage/scan_and_report.py --dir {report_data['scan_dir']} --execute --approval-file {output_path}")
    print("=" * 70)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Generate approval artifacts from storage scan report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate approval from scan report
  python scripts/storage/generate_approval.py \\
      --report report.json \\
      --operator "John Doe" \\
      --out approval.json

  # Custom expiry (14 days instead of default 7)
  python scripts/storage/generate_approval.py \\
      --report report.json \\
      --operator "Jane Smith" \\
      --out approval.json \\
      --expiry-days 14

  # Full workflow:
  # 1. Scan
  python scripts/storage/scan_and_report.py --dir C:/target --report-out report.json

  # 2. Review report.json (manual step)

  # 3. Generate approval
  python scripts/storage/generate_approval.py --report report.json --operator "Operator Name" --out approval.json

  # 4. Execute cleanup
  python scripts/storage/scan_and_report.py --dir C:/target --execute --approval-file approval.json
        """
    )

    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Path to scan report JSON file (input)"
    )
    parser.add_argument(
        "--operator",
        type=str,
        required=True,
        help="Name of operator approving cleanup (for audit trail)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Path to write approval JSON file (output)"
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=Path("approval_audit.log"),
        help="Path to audit log file (default: approval_audit.log)"
    )
    parser.add_argument(
        "--expiry-days",
        type=int,
        default=7,
        help="Days until approval expires (default: 7)"
    )

    args = parser.parse_args()

    # Validation
    if args.expiry_days < 1:
        parser.error("--expiry-days must be >= 1")

    if not args.operator.strip():
        parser.error("--operator cannot be empty")

    # Generate approval artifacts
    exit_code = generate_approval_artifacts(
        report_path=args.report,
        operator_name=args.operator.strip(),
        output_path=args.out,
        audit_log_path=args.audit_log,
        expiry_days=args.expiry_days
    )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
