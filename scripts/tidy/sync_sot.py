#!/usr/bin/env python3
"""
Sync Source of Truth Files - Standalone Script

This script synchronizes all SOT files after any workspace changes,
whether made by Cursor, Autopack, or manual edits.

Usage:
  python scripts/tidy/sync_sot.py              # Full sync with cleanup
  python scripts/tidy/sync_sot.py --quick      # Only sync CONSOLIDATED_*.md
  python scripts/tidy/sync_sot.py --dry-run    # Show what would be updated

What this syncs:
  - CONSOLIDATED_*.md (via consolidate_docs.py)
  - ARCHIVE_INDEX.md (via consolidate_docs.py)
  - Verifies project_ruleset_Autopack.json in docs/
  - Verifies project_issue_backlog.json in docs/
  - Verifies autopack_phase_plan.json in docs/
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def sync_consolidated_files(dry_run: bool = False) -> bool:
    """Sync CONSOLIDATED_*.md and ARCHIVE_INDEX.md files."""
    print("\n=== Syncing CONSOLIDATED_*.md files ===")

    consolidate_script = REPO_ROOT / "scripts" / "consolidate_docs.py"
    if not consolidate_script.exists():
        print(f"[ERROR] {consolidate_script} not found")
        return False

    if dry_run:
        print(f"[DRY-RUN] Would run: python {consolidate_script}")
        return True

    print(f"Running: python {consolidate_script}")
    try:
        result = subprocess.run(
            ["python", str(consolidate_script)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print("[OK] CONSOLIDATED_*.md files updated")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            print(f"[ERROR] consolidate_docs.py returned {result.returncode}")
            if result.stderr:
                print(f"Error output:\n{result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("[ERROR] consolidate_docs.py timed out")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to run consolidate_docs.py: {e}")
        return False


def verify_sot_files() -> None:
    """Verify all SOT files are in correct locations."""
    print("\n=== Verifying SOT file locations ===")

    docs_dir = REPO_ROOT / "docs"
    sot_files = {
        "project_ruleset_Autopack.json": "Project-wide rules (auto-updated by Autopack)",
        "project_issue_backlog.json": "Issue backlog (auto-updated by issue_tracker.py)",
        "autopack_phase_plan.json": "Phase plan (auto-updated when planning occurs)",
        "CONSOLIDATED_CORRESPONDENCE.md": "Consolidated correspondence files",
        "CONSOLIDATED_DEBUG.md": "Consolidated debug/error info",
        "CONSOLIDATED_MISC.md": "Miscellaneous consolidated docs",
        "CONSOLIDATED_REFERENCE.md": "Reference documentation",
        "CONSOLIDATED_RESEARCH.md": "Research notes",
        "CONSOLIDATED_STRATEGY.md": "Strategic analysis",
    }

    all_present = True
    for file_name, description in sot_files.items():
        file_path = docs_dir / file_name
        if file_path.exists():
            print(f"  [OK] {file_name}")
        else:
            print(f"  [MISSING] {file_name} - {description}")
            all_present = False

    if all_present:
        print("\n[PASS] All SOT files present in docs/")
    else:
        print("\n[WARNING] Some SOT files missing - they will be created on next relevant event")


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize Source of Truth files after workspace changes"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick sync - only update CONSOLIDATED_*.md files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    parser.add_argument(
        "--full-cleanup",
        action="store_true",
        help="Run full corrective_cleanup_v2.py (includes all phases)"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("SOURCE OF TRUTH SYNCHRONIZATION")
    print("=" * 80)

    if args.full_cleanup:
        print("\n=== Running full cleanup (all phases) ===")
        cleanup_script = REPO_ROOT / "scripts" / "tidy" / "corrective_cleanup_v2.py"
        if cleanup_script.exists():
            cmd = ["python", str(cleanup_script)]
            if not args.dry_run:
                cmd.append("--execute")
            else:
                cmd.append("--dry-run")

            result = subprocess.run(cmd, cwd=REPO_ROOT)
            return result.returncode
        else:
            print(f"[ERROR] {cleanup_script} not found")
            return 1

    # Quick or default sync
    success = sync_consolidated_files(dry_run=args.dry_run)

    if not args.quick:
        verify_sot_files()

    print("\n" + "=" * 80)
    if success:
        print("SYNC COMPLETE")
        if not args.dry_run:
            print("\nSOT files synchronized. Remember to commit changes:")
            print("  git add -A")
            print('  git commit -m "sync: update SOT files"')
    else:
        print("SYNC FAILED - see errors above")
    print("=" * 80)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
