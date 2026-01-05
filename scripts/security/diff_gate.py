#!/usr/bin/env python3
"""
Security Diff Gate (CI Enforcement)

Purpose: Fail CI only on new security findings (regression detection), not on pre-existing debt.

Design Principle:
- "Fail on new" (block regressions)
- "Pass on old" (track debt separately in SECURITY_BURNDOWN.md)

Usage (CI):
    # Normalize current scan
    python scripts/security/normalize_sarif.py trivy-fs.sarif > current.json

    # Run diff gate
    python scripts/security/diff_gate.py \\
      --baseline security/baselines/trivy-fs.high.json \\
      --current current.json \\
      --name "Trivy Filesystem"

    # Exit codes:
    #   0 = No new findings (CI green)
    #   1 = New findings detected (CI red)
    #   2 = Script error (missing files, etc.)

Usage (Local):
    # Check if local changes introduce new findings
    trivy fs --format sarif --severity CRITICAL,HIGH . > scan.sarif
    python scripts/security/normalize_sarif.py scan.sarif > current.json
    python scripts/security/diff_gate.py \\
      --baseline security/baselines/trivy-fs.high.json \\
      --current current.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Set


def load_findings(json_path: Path) -> List[Dict[str, Any]]:
    """Load normalized findings from JSON file."""
    if not json_path.exists():
        print(f"Error: File not found: {json_path}", file=sys.stderr)
        sys.exit(2)

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def findings_to_set(findings: List[Dict[str, Any]]) -> Set[str]:
    """Convert findings list to set of JSON strings (for set operations)."""
    return set(json.dumps(f, sort_keys=True) for f in findings)


def set_to_findings(finding_set: Set[str]) -> List[Dict[str, Any]]:
    """Convert set of JSON strings back to findings list (sorted)."""
    findings = [json.loads(f) for f in finding_set]
    findings.sort(key=lambda x: json.dumps(x, sort_keys=True))
    return findings


def print_finding_summary(finding: Dict[str, Any]) -> str:
    """Format a finding for human-readable output."""
    tool = finding.get("tool", "unknown")
    rule_id = finding.get("ruleId", "unknown")
    artifact = finding.get("artifactUri", "unknown")
    line = finding.get("startLine", "?")

    return f"  - [{tool}] {rule_id} in {artifact}:{line}"


def main():
    parser = argparse.ArgumentParser(
        description="Security diff gate: fail on new findings only",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Baseline findings JSON (committed)",
    )
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Current findings JSON (from recent scan)",
    )
    parser.add_argument(
        "--name",
        default="Security Scan",
        help="Scanner name for output (e.g., 'Trivy Filesystem')",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed new finding list (not just count)",
    )

    args = parser.parse_args()

    # Load findings
    baseline_findings = load_findings(args.baseline)
    current_findings = load_findings(args.current)

    # Convert to sets for diff
    baseline_set = findings_to_set(baseline_findings)
    current_set = findings_to_set(current_findings)

    # Compute diff
    new_findings_set = current_set - baseline_set
    resolved_findings_set = baseline_set - current_set
    unchanged_findings_set = baseline_set & current_set

    new_findings = set_to_findings(new_findings_set)
    resolved_findings = set_to_findings(resolved_findings_set)

    # Print summary
    print("=" * 70)
    print(f"{args.name} - Diff Gate Summary")
    print("=" * 70)
    print(f"Baseline:  {len(baseline_findings)} findings")
    print(f"Current:   {len(current_findings)} findings")
    print(f"New:       {len(new_findings)} findings")
    print(f"Resolved:  {len(resolved_findings)} findings")
    print(f"Unchanged: {len(unchanged_findings_set)} findings")
    print("=" * 70)

    # Show new findings (verbose or if blocking)
    if new_findings:
        print("\n🚨 NEW FINDINGS DETECTED (CI will fail):\n")
        if args.verbose or len(new_findings) <= 10:
            for finding in new_findings[:20]:  # Cap at 20 for readability
                print(print_finding_summary(finding))
            if len(new_findings) > 20:
                print(f"  ... and {len(new_findings) - 20} more")
        else:
            print(f"  {len(new_findings)} new findings detected.")
            print("  Use --verbose to see details, or check SARIF in GitHub Security tab.")

        print("\n" + "=" * 70)
        print("❌ DIFF GATE: FAILED (new findings present)")
        print("=" * 70)
        print("\nNext steps:")
        print("  1. Review findings in GitHub Security tab (SARIF upload)")
        print("  2. Fix vulnerabilities OR document exception in docs/SECURITY_EXCEPTIONS.md")
        print("  3. Re-run CI after fix")
        print("\n" + "=" * 70)
        return 1  # Fail CI

    # Show resolved findings (info only, not blocking)
    if resolved_findings:
        print("\n✅ RESOLVED FINDINGS (good news!):\n")
        if args.verbose or len(resolved_findings) <= 10:
            for finding in resolved_findings[:20]:
                print(print_finding_summary(finding))
            if len(resolved_findings) > 20:
                print(f"  ... and {len(resolved_findings) - 20} more")
        else:
            print(f"  {len(resolved_findings)} findings resolved since baseline.")

    # No new findings → pass
    print("\n" + "=" * 70)
    print("✅ DIFF GATE: PASSED (no new findings)")
    print("=" * 70)

    if len(baseline_findings) > 0:
        print(f"\nNote: {len(baseline_findings)} pre-existing findings tracked in SECURITY_BURNDOWN.md")

    print("\n" + "=" * 70)
    return 0  # Pass CI


if __name__ == "__main__":
    sys.exit(main())
