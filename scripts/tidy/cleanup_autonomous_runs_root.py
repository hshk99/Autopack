#!/usr/bin/env python3
"""
Cleanup Script for .autonomous_runs Root Directory

Organizes loose files and folders at .autonomous_runs/ root level by:
1. Moving loose run directories to their project's runs/ folder
2. Moving log files to appropriate project diagnostics
3. Moving JSON plan files to project archives
4. Protecting essential directories and files

Protected Items:
- autopack/ (project structure)
- file-organizer-app-v1/ (project structure)
- _shared/ (shared runtime state)
- .locks/ (run lock files)
- tidy_checkpoints/ (tidy process checkpoints)
- README.md (documentation)
- STRUCTURE.md (documentation)
- api_server.log (active API server log)

Usage:
    python scripts/tidy/cleanup_autonomous_runs_root.py --dry-run
    python scripts/tidy/cleanup_autonomous_runs_root.py --execute
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent
AUTONOMOUS_RUNS = REPO_ROOT / ".autonomous_runs"


class RootCleanup:
    """Cleanup loose files and folders at .autonomous_runs root"""

    # Protected items that should NEVER be moved or deleted
    PROTECTED_DIRS = {
        "autopack",
        "file-organizer-app-v1",
        "_shared",
        ".locks",
        "tidy_checkpoints",
    }

    PROTECTED_FILES = {
        "README.md",
        "STRUCTURE.md",
        "api_server.log",  # Active API server log
    }

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.moved_count = 0
        self.skipped_count = 0
        self.actions = []  # Track all actions for summary

    def detect_project(self, name: str) -> str:
        """
        Detect which project a file/folder belongs to

        Args:
            name: File or folder name

        Returns:
            Project ID: "autopack" or "file-organizer-app-v1"
        """
        name_lower = name.lower()

        # File-organizer patterns
        if any(
            pattern in name_lower
            for pattern in ["fileorg", "file-org", "immigration", "visa", "evidence"]
        ):
            return "file-organizer-app-v1"

        # Autopack patterns (default)
        return "autopack"

    def analyze_run_directory(self, run_dir: Path) -> Optional[str]:
        """
        Analyze a run directory to determine if it's complete or just a stub

        Args:
            run_dir: Path to run directory

        Returns:
            "complete" if it has substantial content, "stub" if only phase_plan.json, None if should skip
        """
        if not run_dir.is_dir():
            return None

        files = list(run_dir.rglob("*"))
        files = [f for f in files if f.is_file()]

        if not files:
            return "stub"

        # Check if it's just phase_plan.json
        if len(files) == 1 and files[0].name == "phase_plan.json":
            return "stub"

        # Has substantial content
        return "complete"

    def move_run_directory(self, run_dir: Path, project_id: str) -> bool:
        """
        Move a run directory to the appropriate project's runs/ folder

        Args:
            run_dir: Path to run directory to move
            project_id: Target project ID

        Returns:
            True if moved, False if skipped
        """
        run_type = self.analyze_run_directory(run_dir)

        if run_type is None:
            return False

        # Destination: .autonomous_runs/{project}/runs/{run_name}/
        dest_dir = AUTONOMOUS_RUNS / project_id / "runs" / run_dir.name

        # Check if destination already exists
        if dest_dir.exists():
            # Check if destination is more complete
            dest_type = self.analyze_run_directory(dest_dir)

            if dest_type == "complete":
                # Destination is complete, source is stub or duplicate - remove source
                action = f"🗑️  DELETE (duplicate): {run_dir.relative_to(REPO_ROOT)} (complete version exists at {dest_dir.relative_to(REPO_ROOT)})"
                print(f"   {action}")
                self.actions.append(action)

                if not self.dry_run:
                    shutil.rmtree(run_dir)

                self.moved_count += 1
                return True
            elif run_type == "complete" and dest_type == "stub":
                # Source is complete, destination is stub - replace destination
                action = f"📦 REPLACE: {run_dir.relative_to(REPO_ROOT)} → {dest_dir.relative_to(REPO_ROOT)} (replacing stub)"
                print(f"   {action}")
                self.actions.append(action)

                if not self.dry_run:
                    shutil.rmtree(dest_dir)
                    shutil.move(str(run_dir), str(dest_dir))

                self.moved_count += 1
                return True
            else:
                # Both stub or same type - skip
                action = f"⏭️  SKIP: {run_dir.relative_to(REPO_ROOT)} (duplicate exists)"
                print(f"   {action}")
                self.actions.append(action)
                self.skipped_count += 1
                return False

        # No conflict, move it
        action = f"📦 MOVE: {run_dir.relative_to(REPO_ROOT)} → {dest_dir.relative_to(REPO_ROOT)}"
        print(f"   {action}")
        self.actions.append(action)

        if not self.dry_run:
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(run_dir), str(dest_dir))

        self.moved_count += 1
        return True

    def move_log_file(self, log_file: Path, project_id: str) -> bool:
        """
        Move a log file to project's archive/diagnostics/

        Args:
            log_file: Path to log file
            project_id: Target project ID

        Returns:
            True if moved, False if skipped
        """
        # Destination: .autonomous_runs/{project}/archive/diagnostics/
        dest_dir = AUTONOMOUS_RUNS / project_id / "archive" / "diagnostics"
        dest_file = dest_dir / log_file.name

        # Check if destination already exists
        if dest_file.exists():
            action = f"⏭️  SKIP: {log_file.relative_to(REPO_ROOT)} (already exists in diagnostics)"
            print(f"   {action}")
            self.actions.append(action)
            self.skipped_count += 1
            return False

        action = f"📦 MOVE: {log_file.relative_to(REPO_ROOT)} → {dest_file.relative_to(REPO_ROOT)}"
        print(f"   {action}")
        self.actions.append(action)

        if not self.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(log_file), str(dest_file))

        self.moved_count += 1
        return True

    def move_json_file(self, json_file: Path, project_id: str) -> bool:
        """
        Move a JSON plan file to project's archive/plans/

        Args:
            json_file: Path to JSON file
            project_id: Target project ID

        Returns:
            True if moved, False if skipped
        """
        # Destination: .autonomous_runs/{project}/archive/plans/
        dest_dir = AUTONOMOUS_RUNS / project_id / "archive" / "plans"
        dest_file = dest_dir / json_file.name

        # Check if destination already exists
        if dest_file.exists():
            action = f"⏭️  SKIP: {json_file.relative_to(REPO_ROOT)} (already exists in plans)"
            print(f"   {action}")
            self.actions.append(action)
            self.skipped_count += 1
            return False

        action = f"📦 MOVE: {json_file.relative_to(REPO_ROOT)} → {dest_file.relative_to(REPO_ROOT)}"
        print(f"   {action}")
        self.actions.append(action)

        if not self.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(json_file), str(dest_file))

        self.moved_count += 1
        return True

    def cleanup(self):
        """Execute the cleanup process"""
        print("=" * 80)
        print(".autonomous_runs ROOT CLEANUP")
        print("=" * 80)
        print(f"Mode: {'DRY-RUN (preview only)' if self.dry_run else 'EXECUTE'}")
        print("=" * 80)
        print()

        if not AUTONOMOUS_RUNS.exists():
            print(f"❌ Error: {AUTONOMOUS_RUNS} does not exist")
            return 1

        # Scan root directory
        items = list(AUTONOMOUS_RUNS.iterdir())

        # Separate items by type
        loose_dirs = []
        loose_log_files = []
        loose_json_files = []
        protected_items = []

        for item in items:
            # Skip hidden files/dirs (except .locks)
            if item.name.startswith(".") and item.name != ".locks":
                continue

            # Check if protected
            if item.name in self.PROTECTED_DIRS or item.name in self.PROTECTED_FILES:
                protected_items.append(item)
                continue

            if item.is_dir():
                loose_dirs.append(item)
            elif item.suffix == ".log":
                loose_log_files.append(item)
            elif item.suffix == ".json":
                loose_json_files.append(item)

        # Report what we found
        print("📊 Analysis:")
        print(f"   Protected items: {len(protected_items)}")
        print(f"   Loose run directories: {len(loose_dirs)}")
        print(f"   Loose log files: {len(loose_log_files)}")
        print(f"   Loose JSON files: {len(loose_json_files)}")
        print()

        if len(protected_items) > 0:
            print("🔒 Protected (will not touch):")
            for item in sorted(protected_items):
                print(f"   ✅ {item.name}")
            print()

        # Process loose run directories
        if loose_dirs:
            print("📁 Processing loose run directories:")
            for run_dir in sorted(loose_dirs):
                project_id = self.detect_project(run_dir.name)
                print(f"\n   {run_dir.name} → {project_id}")
                self.move_run_directory(run_dir, project_id)
            print()

        # Process loose log files
        if loose_log_files:
            print("📄 Processing loose log files:")
            for log_file in sorted(loose_log_files):
                project_id = self.detect_project(log_file.name)
                print(f"\n   {log_file.name} → {project_id}")
                self.move_log_file(log_file, project_id)
            print()

        # Process loose JSON files
        if loose_json_files:
            print("📄 Processing loose JSON files:")
            for json_file in sorted(loose_json_files):
                project_id = self.detect_project(json_file.name)
                print(f"\n   {json_file.name} → {project_id}")
                self.move_json_file(json_file, project_id)
            print()

        # Summary
        print("=" * 80)
        print("CLEANUP SUMMARY")
        print("=" * 80)
        print(f"   Items moved: {self.moved_count}")
        print(f"   Items skipped: {self.skipped_count}")
        print(f"   Protected items: {len(protected_items)}")
        print()

        if self.dry_run:
            print("🔍 This was a dry-run. No changes were made.")
            print("   Run with --execute to apply these changes.")
        else:
            print("✅ Cleanup complete!")

        print("=" * 80)

        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup .autonomous_runs root directory",
        epilog="""
Examples:
  # Preview what would be cleaned up
  python scripts/tidy/cleanup_autonomous_runs_root.py --dry-run

  # Execute cleanup
  python scripts/tidy/cleanup_autonomous_runs_root.py --execute

Protected items (never moved):
  - autopack/ (project structure)
  - file-organizer-app-v1/ (project structure)
  - _shared/ (shared runtime state)
  - .locks/ (run lock files)
  - tidy_checkpoints/ (tidy checkpoints)
  - README.md (documentation)
  - STRUCTURE.md (documentation)
  - api_server.log (active API log)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute

    cleanup = RootCleanup(dry_run=dry_run)
    return cleanup.cleanup()


if __name__ == "__main__":
    sys.exit(main())
