#!/usr/bin/env python3
"""
Unified Tidy Directory - Reusable Manual Tidy Function for Autopack

This is the user-facing entry point for tidying any directory within Autopack.
Combines documentation consolidation + optional archive restructuring.

Usage:
    # Docs only (consolidate .md files)
    python scripts/tidy/unified_tidy_directory.py archive --docs-only --dry-run

    # Full cleanup (docs + scripts + logs)
    python scripts/tidy/unified_tidy_directory.py archive --full --dry-run

    # Interactive mode (prompts for confirmation)
    python scripts/tidy/unified_tidy_directory.py archive --interactive

Features:
    - Recursively processes all .md files in target directory and subdirectories
    - Categorizes into BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS
    - Chronologically sorts entries (most recent first)
    - Optional: Organize ALL file types (.py, .log, .json, .yaml, .txt, .csv, .sql, etc.)
    - Optional: Move scripts to superseded/
    - Optional: Centralize log files
    - Optional: Archive data files
    - Optional: Remove empty directories

Author: Autopack Team
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from consolidate_docs_directory import main as consolidate_docs_main
from phase2_archive_cleanup import Phase2ArchiveCleanup
from enhanced_file_cleanup import EnhancedFileCleanup

# Add project root for Autopack imports
REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT / "src"))


class UnifiedTidyDirectory:
    """Unified interface for tidying any directory in Autopack workspace"""

    def __init__(
        self,
        target_directory: str,
        docs_only: bool = True,
        full_cleanup: bool = False,
        interactive: bool = False,
        dry_run: bool = True,
    ):
        self.target_directory = target_directory
        self.docs_only = docs_only
        self.full_cleanup = full_cleanup
        self.interactive = interactive
        self.dry_run = dry_run

        # Resolve paths - CWD-aware for multi-project support
        cwd = Path.cwd()
        if str(cwd).startswith(str(REPO_ROOT)):
            # Running from within Autopack repo - use CWD as project root
            self.project_dir = cwd
            self.target_path = cwd / target_directory
        else:
            # Running from outside - use REPO_ROOT
            self.project_dir = REPO_ROOT
            self.target_path = REPO_ROOT / target_directory

    def run(self):
        """Execute unified tidy workflow"""
        print("=" * 80)
        print("AUTOPACK MANUAL TIDY FUNCTION")
        print("=" * 80)
        print(f"Target Directory: {self.target_directory}")
        print(f"Mode: {'DRY-RUN (preview only)' if self.dry_run else 'EXECUTE (making changes)'}")
        print(f"Scope: {'DOCS ONLY (.md files)' if self.docs_only else 'FULL CLEANUP (all file types: .md, .py, .log, .json, .yaml, .txt, .csv, .sql, etc.)'}")
        print("=" * 80)
        print()

        # Validate directory exists
        if not self.target_path.exists():
            print(f"❌ Directory not found: {self.target_path}")
            return 1

        # Phase 1: Documentation Consolidation (always runs)
        print("[PHASE 1] Documentation Consolidation")
        print("-" * 80)
        result = self._run_phase1_docs_consolidation()
        if result != 0:
            print(f"❌ Phase 1 failed with code {result}")
            return result

        # Phase 2: Archive Restructuring (optional)
        if self.full_cleanup:
            print()
            print("[PHASE 2] Archive Restructuring")
            print("-" * 80)

            if self.interactive:
                response = input("\nProceed with Phase 2 (scripts/logs cleanup)? [y/N]: ")
                if response.lower() != 'y':
                    print("Phase 2 skipped by user.")
                    return 0

            result = self._run_phase2_restructuring()
            if result != 0:
                print(f"❌ Phase 2 failed with code {result}")
                return result

        # Summary
        print()
        print("=" * 80)
        print("TIDY COMPLETE")
        print("=" * 80)
        if self.docs_only:
            print("✅ Documentation (.md files) consolidated into SOT files")
            print()
            print("Next steps:")
            print("1. Review docs/BUILD_HISTORY.md, docs/DEBUG_LOG.md, docs/ARCHITECTURE_DECISIONS.md")
            print("2. Run with --full to organize ALL file types (.py, .log, .json, .yaml, .txt, .csv, .sql) (optional)")
        else:
            print("✅ All file types organized:")
            print("  - .md files → consolidated to SOT files")
            print("  - .py files → scripts/superseded/")
            print("  - .log files → archive/diagnostics/logs/")
            print("  - .json/.yaml files → config/legacy/ or docs/schemas/")
            print("  - .csv/.xlsx files → data/archive/")
            print("  - .sql files → archive/sql/")
            print()
            print("Next steps:")
            print("1. Review organized file structure")
            print("2. Check for any files requiring manual review")
            print("3. Commit changes to git")

        print("=" * 80)

        return 0

    def _run_phase1_docs_consolidation(self) -> int:
        """Run Phase 1: Documentation consolidation"""
        # Import the consolidator
        from consolidate_docs_v2 import DocumentConsolidator

        try:
            consolidator = DocumentConsolidator(self.project_dir, dry_run=self.dry_run)
            consolidator.archive_dir = self.target_path
            consolidator.consolidate()

            print()
            print("✅ Phase 1 complete: Documentation consolidated")
            return 0

        except Exception as e:
            print(f"❌ Phase 1 error: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def _run_phase2_restructuring(self) -> int:
        """Run Phase 2: Enhanced file cleanup (all file types)"""
        try:
            # Use enhanced cleanup that handles ALL file types
            cleanup = EnhancedFileCleanup(self.target_directory, dry_run=self.dry_run)
            cleanup.run()

            print()
            print("✅ Phase 2 complete: All file types organized")
            return 0

        except Exception as e:
            print(f"❌ Phase 2 error: {e}")
            import traceback
            traceback.print_exc()
            return 1


def main():
    parser = argparse.ArgumentParser(
        description="Unified manual tidy function for any Autopack directory",
        epilog="""
Examples:
  # Consolidate docs only (safe, reversible)
  python scripts/tidy/unified_tidy_directory.py archive --docs-only --dry-run
  python scripts/tidy/unified_tidy_directory.py archive --docs-only

  # Full cleanup (docs + scripts + logs)
  python scripts/tidy/unified_tidy_directory.py archive --full --dry-run
  python scripts/tidy/unified_tidy_directory.py archive --full

  # Interactive mode (prompts before Phase 2)
  python scripts/tidy/unified_tidy_directory.py archive --interactive

  # Other directories
  python scripts/tidy/unified_tidy_directory.py .autonomous_runs/my-project --docs-only
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "directory",
        help="Directory to tidy (relative to project root, e.g., 'archive' or '.autonomous_runs/project')"
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--docs-only",
        action="store_true",
        default=True,
        help="Consolidate documentation only (default)"
    )
    mode_group.add_argument(
        "--full",
        action="store_true",
        help="Full cleanup: docs + scripts + logs + empty dirs"
    )

    # Execution mode
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing (recommended first run)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute changes (opposite of --dry-run)"
    )

    # Interactive mode
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for confirmation before each phase"
    )

    args = parser.parse_args()

    # Determine execution mode
    dry_run = not args.execute if args.execute else True  # Default to dry-run for safety

    # Create and run unified tidy
    tidy = UnifiedTidyDirectory(
        target_directory=args.directory,
        docs_only=args.docs_only,
        full_cleanup=args.full,
        interactive=args.interactive,
        dry_run=dry_run,
    )

    return tidy.run()


if __name__ == "__main__":
    sys.exit(main())
