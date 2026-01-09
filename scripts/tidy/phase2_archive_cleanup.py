#!/usr/bin/env python3
"""
Phase 2: Archive Cleanup - Scripts, Logs, and Directory Restructuring

This script runs AFTER documentation consolidation (Phase 1) to:
1. Move outdated scripts to scripts/superseded/
2. Centralize log files to archive/diagnostics/logs/
3. Remove empty directories
4. Create documentation for superseded scripts

Usage:
    python scripts/tidy/phase2_archive_cleanup.py --dry-run
    python scripts/tidy/phase2_archive_cleanup.py --execute
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

# Repository root
REPO_ROOT = Path(__file__).parent.parent.parent


class Phase2ArchiveCleanup:
    """Phase 2: Clean up scripts, logs, and restructure archive after doc consolidation"""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.archive_dir = REPO_ROOT / "archive"
        self.scripts_dir = REPO_ROOT / "scripts"
        self.superseded_dir = self.scripts_dir / "superseded"
        self.logs_dir = self.archive_dir / "diagnostics" / "logs"

        # Tracking
        self.scripts_moved = []
        self.logs_moved = []
        self.dirs_removed = []

    def run(self):
        """Execute Phase 2 cleanup"""
        print("=" * 80)
        print("PHASE 2: ARCHIVE CLEANUP")
        print("=" * 80)
        print(f"Mode: {'DRY-RUN (preview only)' if self.dry_run else 'EXECUTE (making changes)'}")
        print(f"Archive: {self.archive_dir}")
        print("=" * 80)
        print()

        # Step 1: Find and categorize scripts
        print("[1] Finding Python scripts in archive...")
        scripts_to_move = self._find_scripts_to_move()
        print(f"    Found {len(scripts_to_move)} scripts to move to superseded/")

        # Step 2: Move scripts to superseded
        if scripts_to_move:
            print("\n[2] Moving scripts to scripts/superseded/...")
            self._move_scripts_to_superseded(scripts_to_move)

        # Step 3: Find and centralize log files
        print("\n[3] Finding log files in archive...")
        log_files = self._find_log_files()
        print(f"    Found {len(log_files)} log files to centralize")

        if log_files:
            print("\n[4] Centralizing log files to archive/diagnostics/logs/...")
            self._centralize_logs(log_files)

        # Step 5: Remove empty directories
        print("\n[5] Finding empty directories...")
        empty_dirs = self._find_empty_directories()
        print(f"    Found {len(empty_dirs)} empty directories")

        if empty_dirs:
            print("\n[6] Removing empty directories...")
            self._remove_empty_directories(empty_dirs)

        # Step 7: Create superseded scripts documentation
        if self.scripts_moved:
            print("\n[7] Creating SUPERSEDED_SCRIPTS.md documentation...")
            self._create_superseded_docs()

        # Summary
        self._print_summary()

    def _find_scripts_to_move(self) -> List[Tuple[Path, str]]:
        """
        Find Python scripts in archive that should be moved to superseded.

        Returns list of (script_path, reason) tuples.
        """
        scripts = []

        # Directories to search (excluding tidy_v7 which is active)
        search_dirs = [
            self.archive_dir / "diagnostics",
            self.archive_dir / "plans",
            self.archive_dir / "reports",
            self.archive_dir / "analysis",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue

            for py_file in search_dir.rglob("*.py"):
                # Determine reason for superseding
                reason = self._classify_script_supersede_reason(py_file)
                if reason:
                    scripts.append((py_file, reason))

        return scripts

    def _classify_script_supersede_reason(self, script_path: Path) -> str:
        """Classify why a script is being superseded"""
        name_lower = script_path.name.lower()

        # Check filename patterns
        if "old_" in name_lower or "_old" in name_lower:
            return "Explicitly marked as old version"
        elif "comprehensive_cleanup" in name_lower:
            return "Replaced by consolidate_docs_v2.py + corrective_cleanup_v2.py"
        elif "tidy" in name_lower and script_path.parent != self.scripts_dir / "tidy":
            return "Superseded tidy script, replaced by scripts/tidy/ system"
        elif "cleanup" in name_lower and script_path.parent != self.scripts_dir / "tidy":
            return "Superseded cleanup script"
        elif script_path.parent == self.archive_dir / "diagnostics":
            return "Diagnostic/test script from old run, no longer needed"
        else:
            # Default: in archive, likely superseded
            return "Located in archive, superseded by current implementation"

    def _move_scripts_to_superseded(self, scripts: List[Tuple[Path, str]]):
        """Move scripts to scripts/superseded/ with subdirectory organization"""

        # Create superseded directory
        if not self.dry_run:
            self.superseded_dir.mkdir(parents=True, exist_ok=True)
        else:
            print(f"    [DRY-RUN] Would create {self.superseded_dir}")

        for script_path, reason in scripts:
            # Determine subdirectory based on origin
            if "tidy" in script_path.name.lower() or "cleanup" in script_path.name.lower():
                subdir = self.superseded_dir / "old_tidy_scripts"
            elif "diagnostic" in str(script_path.parent).lower():
                subdir = self.superseded_dir / "old_diagnostic_scripts"
            else:
                subdir = self.superseded_dir / "other"

            # Create subdirectory
            if not self.dry_run:
                subdir.mkdir(parents=True, exist_ok=True)

            # Move script
            dest_path = subdir / script_path.name

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {script_path.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
            else:
                shutil.move(str(script_path), str(dest_path))
                print(f"    [MOVED] {script_path.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}")

            self.scripts_moved.append((script_path, dest_path, reason))

    def _find_log_files(self) -> List[Path]:
        """Find all .log files in archive (excluding diagnostics/logs/)"""
        log_files = []

        for log_file in self.archive_dir.rglob("*.log"):
            # Skip if already in diagnostics/logs/
            if log_file.parent == self.logs_dir:
                continue

            log_files.append(log_file)

        return log_files

    def _centralize_logs(self, log_files: List[Path]):
        """Move all log files to archive/diagnostics/logs/"""

        # Create logs directory
        if not self.dry_run:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
        else:
            print(f"    [DRY-RUN] Would create {self.logs_dir}")

        for log_file in log_files:
            dest_path = self.logs_dir / log_file.name

            # Handle name conflicts
            if dest_path.exists():
                # Add parent directory name to disambiguate
                parent_name = log_file.parent.name
                dest_path = self.logs_dir / f"{parent_name}_{log_file.name}"

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {log_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
            else:
                shutil.move(str(log_file), str(dest_path))
                print(f"    [MOVED] {log_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}")

            self.logs_moved.append((log_file, dest_path))

    def _find_empty_directories(self) -> List[Path]:
        """Find empty directories in archive (excluding tidy_v7, prompts, diagnostics/logs)"""
        empty_dirs = []

        # Exclusions
        keep_dirs = {
            self.archive_dir / "tidy_v7",
            self.archive_dir / "prompts",
            self.archive_dir / "diagnostics" / "logs",
            self.archive_dir / "diagnostics" / "runs",
        }

        for dirpath in self.archive_dir.rglob("*"):
            if not dirpath.is_dir():
                continue

            # Skip excluded directories
            if any(dirpath == keep_dir or dirpath.is_relative_to(keep_dir) for keep_dir in keep_dirs):
                continue

            # Check if empty
            if not any(dirpath.iterdir()):
                empty_dirs.append(dirpath)

        # Sort by depth (deepest first) to remove children before parents
        empty_dirs.sort(key=lambda p: len(p.parts), reverse=True)

        return empty_dirs

    def _remove_empty_directories(self, empty_dirs: List[Path]):
        """Remove empty directories"""
        for dirpath in empty_dirs:
            if self.dry_run:
                print(f"    [DRY-RUN] Would remove: {dirpath.relative_to(REPO_ROOT)}")
            else:
                try:
                    dirpath.rmdir()
                    print(f"    [REMOVED] {dirpath.relative_to(REPO_ROOT)}")
                    self.dirs_removed.append(dirpath)
                except OSError as e:
                    print(f"    [SKIP] Could not remove {dirpath.relative_to(REPO_ROOT)}: {e}")

    def _create_superseded_docs(self):
        """Create SUPERSEDED_SCRIPTS.md documentation"""
        doc_path = self.superseded_dir / "README.md"

        content = f"""# Superseded Scripts - Historical Reference

**Last Updated**: {datetime.now().strftime("%Y-%m-%d")}

This directory contains Python scripts that have been superseded by newer implementations.
They are preserved here for historical reference and understanding of system evolution.

---

## Scripts Moved to Superseded

"""

        # Group by subdirectory
        by_subdir = {}
        for old_path, new_path, reason in self.scripts_moved:
            subdir = new_path.parent.name
            if subdir not in by_subdir:
                by_subdir[subdir] = []
            by_subdir[subdir].append((old_path, new_path, reason))

        for subdir, scripts in by_subdir.items():
            content += f"\n### {subdir}/\n\n"

            for old_path, new_path, reason in scripts:
                content += f"**{new_path.name}**\n"
                content += f"- **Original Location**: `{old_path.relative_to(REPO_ROOT)}`\n"
                content += f"- **Reason Superseded**: {reason}\n"
                content += f"- **Date Archived**: {datetime.now().strftime('%Y-%m-%d')}\n"
                content += "\n"

        content += """
---

## Why Scripts Are Superseded

### Old Tidy Scripts
These scripts were early attempts at workspace organization that have been replaced by the comprehensive tidy system in `scripts/tidy/`.

**Replaced By**:
- `scripts/tidy/consolidate_docs_v2.py` - Documentation consolidation
- `scripts/tidy/corrective_cleanup_v2.py` - Workspace cleanup

### Old Diagnostic Scripts
These scripts were used for one-time debugging or analysis and are no longer needed for regular operations.

---

## Should You Delete These?

**NO - Keep for Historical Reference**

These scripts document the evolution of the Autopack tidy system and may contain useful patterns or logic that inform future development.

If you need to understand:
- How workspace organization evolved
- Why certain approaches were abandoned
- What problems earlier scripts tried to solve

...these superseded scripts provide that context.

---

**Maintained By**: Autopack Tidy System
"""

        if self.dry_run:
            print(f"    [DRY-RUN] Would create: {doc_path.relative_to(REPO_ROOT)}")
            print(f"    [DRY-RUN] With {len(self.scripts_moved)} script entries")
        else:
            doc_path.write_text(content, encoding="utf-8")
            print(f"    [CREATED] {doc_path.relative_to(REPO_ROOT)} ({len(self.scripts_moved)} script entries)")

    def _print_summary(self):
        """Print summary of changes"""
        print("\n" + "=" * 80)
        print("PHASE 2 CLEANUP SUMMARY")
        print("=" * 80)
        print(f"Mode: {'DRY-RUN (no changes made)' if self.dry_run else 'EXECUTED (changes applied)'}")
        print()
        print(f"Scripts moved to superseded/: {len(self.scripts_moved)}")
        print(f"Log files centralized: {len(self.logs_moved)}")
        print(f"Empty directories removed: {len(self.dirs_removed)}")
        print()

        if self.dry_run:
            print("Run with --execute to apply these changes.")
        else:
            print("✅ Phase 2 cleanup complete!")
            print()
            print("Next steps:")
            print("1. Review scripts/superseded/README.md")
            print("2. Verify archive/ structure is clean")
            print("3. Commit changes to git")

        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Phase 2: Archive cleanup after documentation consolidation")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute changes (opposite of --dry-run)")
    args = parser.parse_args()

    # Determine dry-run mode
    dry_run = not args.execute if args.execute else True  # Default to dry-run for safety

    # Run cleanup
    cleanup = Phase2ArchiveCleanup(dry_run=dry_run)
    cleanup.run()


if __name__ == "__main__":
    main()
