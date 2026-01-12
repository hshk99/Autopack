#!/usr/bin/env python3
"""
Special-purpose baseline updater for PR #132 (api-router-split).

This script handles the specific case where code was refactored from main.py
to multiple router files, causing CodeQL fingerprints to change even though
the actual security findings are unchanged.

Usage:
    python scripts/security/update_baseline_for_refactor.py --check
    python scripts/security/update_baseline_for_refactor.py --update

Rationale:
    PR #132 moved ~3200 lines from src/autopack/main.py to:
    - src/autopack/api/routes/*.py (9 router files)
    - src/autopack/api/app.py
    - src/autopack/api/deps.py

    The same log-injection, stack-trace-exposure, and other findings
    still exist, but with different fingerprints due to file relocation.

    This is NOT a security regression - it's a refactoring artifact.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Set

BASELINE_PATH = Path("security/baselines/codeql.python.json")

# Files affected by the refactor (from git show 99c9f035 --stat)
MOVED_FROM = "src/autopack/main.py"
MOVED_TO = [
    "src/autopack/api/app.py",
    "src/autopack/api/deps.py",
    "src/autopack/api/routes/approvals.py",
    "src/autopack/api/routes/artifacts.py",
    "src/autopack/api/routes/dashboard.py",
    "src/autopack/api/routes/files.py",
    "src/autopack/api/routes/governance.py",
    "src/autopack/api/routes/health.py",
    "src/autopack/api/routes/phases.py",
    "src/autopack/api/routes/runs.py",
    "src/autopack/api/routes/storage.py",
]

def load_baseline() -> List[Dict[str, Any]]:
    """Load current baseline."""
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def check_refactor_impact():
    """Check which findings in baseline are from files affected by refactor."""
    baseline = load_baseline()

    main_py_findings = [f for f in baseline if f["artifactUri"] == MOVED_FROM]

    print(f"Current baseline: {len(baseline)} total findings")
    print(f"Findings in {MOVED_FROM}: {len(main_py_findings)}")
    print(f"\nBreakdown by ruleId:")

    rule_counts: Dict[str, int] = {}
    for finding in main_py_findings:
        rule_id = finding.get("ruleId", "unknown")
        rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

    for rule_id, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {rule_id}: {count}")

    print(f"\nThese findings likely moved to router files during refactor.")
    print(f"Expected new finding count after refactor: ~{len(baseline)} (similar total)")

def update_baseline_note():
    """
    Print instructions for manual baseline update.

    We can't automatically update the baseline without running CodeQL,
    but we can document the expected change pattern.
    """
    print("\n" + "="*70)
    print("BASELINE UPDATE REQUIRED")
    print("="*70)
    print("\nThis is a special case (code refactor, not vulnerability change).")
    print("The diff gate is failing because fingerprints changed due to file moves.")
    print("\nRecommended approach:")
    print("1. Manually confirm no new vulnerabilities were introduced")
    print("2. Update baseline using one of these methods:")
    print("\n   Option A: Accept current scan as new baseline (recommended for refactors)")
    print("   - Wait for CodeQL scan to complete on PR branch")
    print("   - Download SARIF from GitHub Security tab")
    print("   - Run: python scripts/security/update_baseline.py --codeql <sarif> --write")
    print("\n   Option B: Add baseline update exception to diff gate")
    print("   - Document in SECURITY_LOG.md why baseline is being updated")
    print("   - Commit updated baseline with SECBASE entry")
    print("\nNext steps:")
    print("  python scripts/security/update_baseline.py --codeql <path-to-sarif> --write")
    print("="*70)

def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check refactor impact")
    parser.add_argument("--update", action="store_true", help="Show update instructions")

    args = parser.parse_args()

    if args.check or (not args.check and not args.update):
        check_refactor_impact()

    if args.update or (not args.check and not args.update):
        update_baseline_note()

if __name__ == "__main__":
    main()
