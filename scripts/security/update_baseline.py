#!/usr/bin/env python3
"""
Security Baseline Update Tool

Purpose: Explicitly update committed security baselines from SARIF scans.

Design Principles:
- **Explicit only** (never runs automatically; requires --write flag)
- **Deterministic** (sorted JSON, stable output)
- **Reviewable** (baselines are committed, diffs visible in PRs)

Usage:
    # Dry run (show what would be updated)
    python scripts/security/update_baseline.py \\
      --trivy-fs trivy-fs.sarif \\
      --trivy-image trivy-image.sarif \\
      --codeql codeql-results.sarif

    # Write baselines (requires explicit --write flag)
    python scripts/security/update_baseline.py \\
      --trivy-fs trivy-fs.sarif \\
      --trivy-image trivy-image.sarif \\
      --codeql codeql-results.sarif \\
      --write

Next Steps After Update:
    1. Review diff: git diff security/baselines/
    2. Document change in docs/SECURITY_LOG.md
    3. Commit: git add security/baselines/ docs/SECURITY_LOG.md
    4. Push for review
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any

# Import normalize_sarif from same directory
sys.path.insert(0, str(Path(__file__).parent))
from normalize_sarif import normalize_sarif_file


BASELINES_DIR = Path(__file__).parent.parent.parent / "security" / "baselines"
BASELINE_FILES = {
    "trivy-fs": BASELINES_DIR / "trivy-fs.high.json",
    "trivy-image": BASELINES_DIR / "trivy-image.high.json",
    "codeql": BASELINES_DIR / "codeql.python.json",
}


def write_baseline(baseline_path: Path, findings: List[Dict[str, Any]]) -> None:
    """
    Write normalized findings to baseline file (sorted, deterministic).

    Args:
        baseline_path: Output file path
        findings: List of normalized finding dictionaries
    """
    # Ensure directory exists
    baseline_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort findings for deterministic output
    sorted_findings = sorted(findings, key=lambda x: json.dumps(x, sort_keys=True))

    # Write with stable formatting
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(sorted_findings, f, indent=2, sort_keys=True)
        f.write("\n")  # Trailing newline for git-friendly diffs


def load_baseline(baseline_path: Path) -> List[Dict[str, Any]]:
    """Load existing baseline (or empty list if not found)."""
    if not baseline_path.exists():
        return []

    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_baselines(
    old: List[Dict[str, Any]], new: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare old vs new baselines and return diff summary.

    Returns:
        Dict with keys: added, removed, unchanged, total_old, total_new
    """
    old_set = set(json.dumps(f, sort_keys=True) for f in old)
    new_set = set(json.dumps(f, sort_keys=True) for f in new)

    added = new_set - old_set
    removed = old_set - new_set
    unchanged = old_set & new_set

    return {
        "added": len(added),
        "removed": len(removed),
        "unchanged": len(unchanged),
        "total_old": len(old),
        "total_new": len(new),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Update security baselines from SARIF scans (explicit only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # SARIF inputs (optional, update only provided ones)
    parser.add_argument(
        "--trivy-fs",
        type=Path,
        help="Trivy filesystem SARIF file (for trivy-fs.high.json)",
    )
    parser.add_argument(
        "--trivy-image",
        type=Path,
        help="Trivy container image SARIF file (for trivy-image.high.json)",
    )
    parser.add_argument(
        "--codeql",
        type=Path,
        help="CodeQL SARIF file (for codeql.python.json)",
    )

    # Write control
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write baselines (dry run if omitted)",
    )

    args = parser.parse_args()

    # Validate: at least one SARIF input required
    if not any([args.trivy_fs, args.trivy_image, args.codeql]):
        parser.error("At least one SARIF input (--trivy-fs, --trivy-image, --codeql) required")

    # Process each provided baseline
    updates = {}
    baseline_mapping = {
        "trivy-fs": (args.trivy_fs, "trivy"),
        "trivy-image": (args.trivy_image, "trivy"),
        "codeql": (args.codeql, "codeql"),
    }

    for baseline_key, (sarif_path, tool_name) in baseline_mapping.items():
        if sarif_path is None:
            continue  # Skip if not provided

        if not sarif_path.exists():
            print(f"Error: SARIF file not found: {sarif_path}", file=sys.stderr)
            sys.exit(1)

        baseline_path = BASELINE_FILES[baseline_key]
        old_baseline = load_baseline(baseline_path)
        new_baseline = normalize_sarif_file(sarif_path, tool_name)

        diff = compare_baselines(old_baseline, new_baseline)
        updates[baseline_key] = {
            "path": baseline_path,
            "findings": new_baseline,
            "diff": diff,
        }

    # Print summary
    print("=" * 70)
    print("Security Baseline Update Summary")
    print("=" * 70)

    for baseline_key, update_info in updates.items():
        diff = update_info["diff"]
        print(f"\n{baseline_key.upper()}: {update_info['path']}")
        print(f"  Old: {diff['total_old']} findings")
        print(f"  New: {diff['total_new']} findings")
        print(f"  Added: {diff['added']} | Removed: {diff['removed']} | Unchanged: {diff['unchanged']}")

        if diff["added"] > 0 or diff["removed"] > 0:
            print("  [!]️  Baseline will change!")
        else:
            print("  [OK] No changes (baseline stable)")

    print("\n" + "=" * 70)

    # Write baselines if --write flag provided
    if args.write:
        print("\n🔧 Writing baselines...")
        for baseline_key, update_info in updates.items():
            write_baseline(update_info["path"], update_info["findings"])
            print(f"  [OK] Written: {update_info['path']}")

        print("\n[OK] Baselines updated successfully!")
        print("\nNext steps:")
        print("  1. Review diff: git diff security/baselines/")
        print("  2. Document change in docs/SECURITY_LOG.md")
        print("  3. Commit: git add security/baselines/ docs/SECURITY_LOG.md")
    else:
        print("\n[!]️  DRY RUN (use --write to apply changes)")
        print("  No files were modified.")

    print("\n" + "=" * 70)

    # Exit with status based on whether baselines would change
    # (useful for CI drift detection in the future)
    has_changes = any(
        u["diff"]["added"] > 0 or u["diff"]["removed"] > 0
        for u in updates.values()
    )

    if has_changes:
        return 1  # Changes detected (drift)
    else:
        return 0  # No changes (stable)


if __name__ == "__main__":
    sys.exit(main())
