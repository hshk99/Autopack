#!/usr/bin/env python3
"""
Directory-Specific Documentation Consolidation

Usage:
    python consolidate_docs_directory.py --directory archive/research --dry-run
    python consolidate_docs_directory.py --directory archive/research
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import from consolidate_docs_v2
sys.path.insert(0, str(Path(__file__).parent))
from consolidate_docs_v2 import DocumentConsolidator, REPO_ROOT


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate documentation for a specific directory"
    )
    parser.add_argument(
        "--directory", required=True, help="Directory to consolidate (relative to project root)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--project", default="Autopack", help="Project directory name")
    args = parser.parse_args()

    # Resolve paths
    project_dir = (
        REPO_ROOT if args.project == "Autopack" else REPO_ROOT / ".autonomous_runs" / args.project
    )
    target_dir = project_dir / args.directory

    if not target_dir.exists():
        print(f"❌ Directory not found: {target_dir}")
        return 1

    print(f"\n{'='*80}")
    print("DIRECTORY-SPECIFIC CONSOLIDATION")
    print(f"{'='*80}")
    print(f"Project: {project_dir.name}")
    print(f"Target Directory: {args.directory}")
    print(f"Dry Run: {args.dry_run}")
    print(f"{'='*80}\n")

    # Create consolidator with directory filter
    consolidator = DocumentConsolidator(project_dir, dry_run=args.dry_run)

    # Override archive_dir to only include target directory
    consolidator.archive_dir = target_dir
    consolidator.directory_specific_mode = (
        True  # Only process files in this directory, not recursively
    )

    # Run consolidation
    try:
        consolidator.consolidate()
        print(f"\n{'='*80}")
        print("DIRECTORY CONSOLIDATION COMPLETE")
        print(f"{'='*80}\n")
        return 0
    except Exception as e:
        print(f"\n❌ Error during consolidation: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
