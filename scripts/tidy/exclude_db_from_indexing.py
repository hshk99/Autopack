#!/usr/bin/env python3
"""
Exclude database files from Windows Search indexing.

This script adds the FILE_ATTRIBUTE_NOT_CONTENT_INDEXED attribute to
database files to prevent Windows Search Indexer from locking them.

Usage:
    python scripts/tidy/exclude_db_from_indexing.py [--pattern PATTERN]

Options:
    --pattern PATTERN    Glob pattern for database files (default: *.db)
    --dry-run           Show what would be done without making changes
"""

import argparse
import subprocess
import sys
from pathlib import Path


def exclude_from_indexing(file_path: Path, dry_run: bool = False) -> bool:
    """
    Exclude a file from Windows Search indexing using attrib command.

    Args:
        file_path: Path to file to exclude
        dry_run: If True, only show what would be done

    Returns:
        True if successful, False otherwise
    """
    if not file_path.exists():
        print(f"[SKIP] {file_path} does not exist")
        return False

    if dry_run:
        print(f"[DRY-RUN] Would exclude from indexing: {file_path}")
        return True

    try:
        # Use attrib +N to set "not content indexed" attribute
        subprocess.run(["attrib", "+N", str(file_path)], check=True, capture_output=True, text=True)
        print(f"[EXCLUDED] {file_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to exclude {file_path}: {e.stderr}")
        return False
    except FileNotFoundError:
        print("[ERROR] 'attrib' command not found (Windows only)")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Exclude database files from Windows Search indexing"
    )
    parser.add_argument(
        "--pattern", default="*.db", help="Glob pattern for database files (default: *.db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    # Find all matching database files in repo root
    repo_root = Path(__file__).parent.parent.parent
    db_files = list(repo_root.glob(args.pattern))

    if not db_files:
        print(f"No files matching pattern '{args.pattern}' found")
        return 0

    print(f"Found {len(db_files)} database files")
    print()

    excluded_count = 0
    for db_file in sorted(db_files):
        if exclude_from_indexing(db_file, dry_run=args.dry_run):
            excluded_count += 1

    print()
    print(f"[SUMMARY] Excluded {excluded_count}/{len(db_files)} files from indexing")

    if args.dry_run:
        print("[DRY-RUN] Re-run without --dry-run to apply changes")

    return 0 if excluded_count == len(db_files) else 1


if __name__ == "__main__":
    sys.exit(main())
