#!/usr/bin/env python3
"""
Automated Research Consolidation - Post-Auditor Workflow

Automatically consolidates research files from reviewed/ subdirectories
into appropriate SOT files based on status.

Triggered by: scripts/plan_hardening.py (after Auditor review)

Workflow:
1. reviewed/implemented/ → docs/BUILD_HISTORY.md (IMPLEMENTED)
2. reviewed/deferred/ → docs/FUTURE_PLANS.md (PENDING_ACTIVE)
3. reviewed/rejected/ → docs/REJECTED_IDEAS.md (REJECTED)

Usage:
    python scripts/research/auto_consolidate_research.py --dry-run
    python scripts/research/auto_consolidate_research.py --execute
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add parent directory to path for imports
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "tidy"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from consolidate_docs_v2 import DocumentConsolidator


class AutoConsolidateResearch:
    """Automatically consolidate research files based on Auditor status"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.repo_root = REPO_ROOT
        self.research_dir = self.repo_root / "archive" / "research"

        # Source directories
        self.implemented_dir = self.research_dir / "reviewed" / "implemented"
        self.deferred_dir = self.research_dir / "reviewed" / "deferred"
        self.rejected_dir = self.research_dir / "reviewed" / "rejected"
        self.temp_dir = self.research_dir / "reviewed" / "temp"

        # Tracking
        self.consolidated_files: Dict[str, List[Path]] = {
            "implemented": [],
            "deferred": [],
            "rejected": [],
        }

    def run(self):
        """Execute automated consolidation"""
        print("=" * 80)
        print("AUTOMATED RESEARCH CONSOLIDATION")
        print("=" * 80)
        print(f"Mode: {'DRY-RUN (preview only)' if self.dry_run else 'EXECUTE (making changes)'}")
        print("=" * 80)
        print()

        # Consolidate each status category
        self._consolidate_implemented()
        self._consolidate_deferred()
        self._consolidate_rejected()

        # Summary
        self._print_summary()

        return 0

    def _consolidate_implemented(self):
        """Consolidate implemented research → docs/BUILD_HISTORY.md"""
        print("[1] Consolidating IMPLEMENTED research...")
        print("-" * 80)

        if not self.implemented_dir.exists() or not any(self.implemented_dir.iterdir()):
            print("    No implemented research to consolidate")
            return

        # Use DocumentConsolidator with override for IMPLEMENTED status
        try:
            consolidator = DocumentConsolidator(self.repo_root, dry_run=self.dry_run)
            consolidator.archive_dir = self.implemented_dir

            # Override status to IMPLEMENTED for all entries
            consolidator.force_status = "IMPLEMENTED"

            consolidator.consolidate()

            # Track files processed
            md_files = list(self.implemented_dir.rglob("*.md"))
            self.consolidated_files["implemented"] = md_files

            print(f"\n    ✅ Consolidated {len(md_files)} files → docs/BUILD_HISTORY.md")
            print("    Status: IMPLEMENTED")

        except Exception as e:
            print(f"    ❌ Error: {e}")
            import traceback

            traceback.print_exc()

    def _consolidate_deferred(self):
        """Consolidate deferred research → docs/FUTURE_PLANS.md"""
        print("\n[2] Consolidating DEFERRED research...")
        print("-" * 80)

        if not self.deferred_dir.exists() or not any(self.deferred_dir.iterdir()):
            print("    No deferred research to consolidate")
            return

        # Use DocumentConsolidator targeting FUTURE_PLANS.md
        try:
            consolidator = DocumentConsolidator(self.repo_root, dry_run=self.dry_run)
            consolidator.archive_dir = self.deferred_dir

            # Override status to PENDING_ACTIVE and route to ARCHITECTURE_DECISIONS
            # (FUTURE_PLANS.md will be created separately as strategic planning doc)
            consolidator.force_status = "PENDING_ACTIVE"
            consolidator.force_category = "decision"  # Route to ARCHITECTURE_DECISIONS

            consolidator.consolidate()

            # Track files processed
            md_files = list(self.deferred_dir.rglob("*.md"))
            self.consolidated_files["deferred"] = md_files

            print(f"\n    ✅ Consolidated {len(md_files)} files → docs/ARCHITECTURE_DECISIONS.md")
            print("    Status: PENDING_ACTIVE (deferred plans)")
            print(
                "    Note: Consider creating docs/FUTURE_PLANS.md for dedicated deferred tracking"
            )

        except Exception as e:
            print(f"    ❌ Error: {e}")
            import traceback

            traceback.print_exc()

    def _consolidate_rejected(self):
        """Consolidate rejected research → docs/REJECTED_IDEAS.md"""
        print("\n[3] Consolidating REJECTED research...")
        print("-" * 80)

        if not self.rejected_dir.exists() or not any(self.rejected_dir.iterdir()):
            print("    No rejected research to consolidate")
            return

        # Use DocumentConsolidator targeting ARCHITECTURE_DECISIONS with REJECTED status
        try:
            consolidator = DocumentConsolidator(self.repo_root, dry_run=self.dry_run)
            consolidator.archive_dir = self.rejected_dir

            # Override status to REJECTED and route to ARCHITECTURE_DECISIONS
            # (REJECTED_IDEAS.md will be created separately)
            consolidator.force_status = "REJECTED"
            consolidator.force_category = "decision"

            consolidator.consolidate()

            # Track files processed
            md_files = list(self.rejected_dir.rglob("*.md"))
            self.consolidated_files["rejected"] = md_files

            print(f"\n    ✅ Consolidated {len(md_files)} files → docs/ARCHITECTURE_DECISIONS.md")
            print("    Status: REJECTED (to prevent re-consideration)")
            print(
                "    Note: Consider creating docs/REJECTED_IDEAS.md for dedicated rejection tracking"
            )

        except Exception as e:
            print(f"    ❌ Error: {e}")
            import traceback

            traceback.print_exc()

    def _print_summary(self):
        """Print consolidation summary"""
        print("\n" + "=" * 80)
        print("CONSOLIDATION SUMMARY")
        print("=" * 80)
        print(
            f"Mode: {'DRY-RUN (no changes made)' if self.dry_run else 'EXECUTED (changes applied)'}"
        )
        print()

        total_files = sum(len(files) for files in self.consolidated_files.values())
        print(f"Total files consolidated: {total_files}")
        print()

        for status, files in self.consolidated_files.items():
            if files:
                print(f"{status.upper()}: {len(files)} files")

        print()

        if self.dry_run:
            print("Run with --execute to apply these changes.")
        else:
            print("✅ Research consolidation complete!")
            print()
            print("Next steps:")
            print("1. Review docs/BUILD_HISTORY.md for implemented features")
            print("2. Review docs/ARCHITECTURE_DECISIONS.md for deferred/rejected items")
            print("3. Consider creating dedicated docs/FUTURE_PLANS.md and docs/REJECTED_IDEAS.md")
            print("4. Archive or remove empty directories in archive/research/reviewed/")

        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Automated research consolidation after Auditor review",
        epilog="""
Examples:
  # Preview consolidation
  python scripts/research/auto_consolidate_research.py --dry-run

  # Execute consolidation
  python scripts/research/auto_consolidate_research.py --execute
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute if args.execute else True

    consolidator = AutoConsolidateResearch(dry_run=dry_run)
    return consolidator.run()


if __name__ == "__main__":
    sys.exit(main())
