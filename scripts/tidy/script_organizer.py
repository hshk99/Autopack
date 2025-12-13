#!/usr/bin/env python3
"""
Script Organizer - Automatically organize scattered scripts in Autopack

Moves scripts from various locations into organized scripts/ structure:
- Root scripts → scripts/archive/root_scripts/
- examples/ → scripts/examples/
- tasks/ → scripts/tasks/ or archive/tasks/
- patches/ → archive/patches/
- tests/ (non-pytest) → scripts/archive/test_scripts/

Leaves alone:
- scripts/ (already organized)
- tests/ (pytest test suites - these stay)
- src/ (source code, not scripts)
- config/ (configuration files)
- .autonomous_runs/ (sub-project workspaces)
"""

import sys
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime


class ScriptOrganizer:
    """Organizes scattered scripts into scripts/ directory"""

    def __init__(self, repo_root: Path, dry_run: bool = True):
        self.repo_root = repo_root
        self.dry_run = dry_run
        self.scripts_dir = repo_root / "scripts"
        self.archive_dir = repo_root / "archive"

        # Categorization rules
        self.script_patterns = {
            "root_scripts": {
                "source": repo_root,
                "patterns": ["*.py", "*.sh", "*.bat"],
                "max_depth": 1,
                "destination": self.scripts_dir / "archive" / "root_scripts",
                "description": "Scripts from repository root"
            },
            "root_reports": {
                "source": repo_root,
                "patterns": ["*.md"],
                "max_depth": 1,
                "destination": self.archive_dir / "reports",
                "description": "Reports and documentation from root (will be consolidated by tidy)"
            },
            "root_logs": {
                "source": repo_root,
                "patterns": ["*.log", "*.diff"],
                "max_depth": 1,
                "destination": self.archive_dir / "diagnostics",
                "description": "Log and debug files from root"
            },
            "root_config": {
                "source": repo_root,
                "patterns": ["*.yaml", "*.yml"],
                "max_depth": 1,
                "destination": repo_root / "config",
                "description": "Configuration files from root"
            },
            "examples": {
                "source": repo_root / "examples",
                "patterns": ["*"],
                "max_depth": 10,
                "destination": self.scripts_dir / "examples",
                "description": "Example scripts and usage demos"
            },
            "tasks": {
                "source": repo_root / "tasks",
                "patterns": ["*.yaml", "*.yml", "*.json"],
                "max_depth": 10,
                "destination": self.archive_dir / "tasks",
                "description": "Task configuration files"
            },
            "patches": {
                "source": repo_root / "patches",
                "patterns": ["*.patch", "*.diff"],
                "max_depth": 10,
                "destination": self.archive_dir / "patches",
                "description": "Git patches and diffs"
            },
        }

        # Files to exclude (these should stay where they are)
        self.exclude_files = {
            "setup.py",           # Package setup
            "manage.py",          # Django/Flask management
            "wsgi.py",            # WSGI entry point
            "asgi.py",            # ASGI entry point
            "__init__.py",        # Python package markers
            "conftest.py",        # Pytest configuration
            "README.md",          # Project README (stays at root)
            "docker-compose.yml", # Docker orchestration (stays at root)
            "docker-compose.dev.yml", # Docker dev config (stays at root)
        }

        # Directories to skip entirely
        self.exclude_dirs = {
            "scripts",            # Already organized
            "src",                # Source code
            "tests",              # Test suites (stay in place)
            "config",             # Configuration
            ".autonomous_runs",   # Sub-projects
            "archive",            # Already archived
            ".git",               # Git metadata
            "venv",               # Virtual environments
            "node_modules",       # Node dependencies
            "__pycache__",        # Python cache
        }

    def scan_scripts(self) -> List[Tuple[Path, str, Path]]:
        """
        Scan for scripts that need organizing.

        Returns:
            List of (source_path, category, destination_path) tuples
        """
        scripts_to_move = []

        for category, config in self.script_patterns.items():
            source_dir = config["source"]

            if not source_dir.exists():
                continue

            patterns = config["patterns"]
            max_depth = config["max_depth"]
            destination = config["destination"]

            # Find matching files
            for pattern in patterns:
                if max_depth == 1:
                    # Root level only
                    for file_path in source_dir.glob(pattern):
                        if file_path.is_file() and file_path.name not in self.exclude_files:
                            scripts_to_move.append((file_path, category, destination))
                else:
                    # Recursive search
                    for file_path in source_dir.rglob(pattern):
                        # Skip excluded directories
                        if any(excl in file_path.parts for excl in self.exclude_dirs):
                            continue

                        if file_path.is_file() and file_path.name not in self.exclude_files:
                            # Preserve subdirectory structure
                            rel_path = file_path.relative_to(source_dir)
                            dest_path = destination / rel_path.parent
                            scripts_to_move.append((file_path, category, dest_path))

        return scripts_to_move

    def organize(self) -> int:
        """
        Organize all scattered scripts.

        Returns:
            Number of files organized
        """
        scripts = self.scan_scripts()

        if not scripts:
            print("✅ No scattered scripts found - everything is organized!")
            return 0

        print(f"\n📋 Found {len(scripts)} script(s) to organize\n")

        # Group by category for display
        by_category = {}
        for src, cat, dest in scripts:
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((src, dest))

        # Display plan
        for category, files in by_category.items():
            config = self.script_patterns[category]
            print(f"📁 {config['description']} ({len(files)} files)")
            print(f"   → {config['destination']}")
            for src, dest in files[:5]:  # Show first 5
                print(f"      • {src.name}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more")
            print()

        if self.dry_run:
            print("🔍 DRY-RUN mode - no changes made")
            print("\nTo execute, run with --execute flag")
            return 0

        # Execute moves
        moved_count = 0
        for src_path, category, dest_dir in scripts:
            try:
                # Create destination directory
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Determine destination file path
                dest_file = dest_dir / src_path.name

                # Handle duplicates
                if dest_file.exists():
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = dest_file.stem
                    suffix = dest_file.suffix
                    dest_file = dest_dir / f"{stem}_{timestamp}{suffix}"

                # Move file
                src_path.rename(dest_file)
                print(f"✅ Moved: {src_path.name} → {dest_file.relative_to(self.repo_root)}")
                moved_count += 1

            except Exception as e:
                print(f"❌ Error moving {src_path}: {e}")

        # Clean up empty directories
        self._cleanup_empty_dirs()

        print(f"\n✅ Organized {moved_count} script(s)")
        return moved_count

    def _cleanup_empty_dirs(self):
        """Remove empty directories after moving files"""
        for category, config in self.script_patterns.items():
            source_dir = config["source"]

            if not source_dir.exists() or source_dir == self.repo_root:
                continue

            # Check if directory is empty (or only contains .gitkeep)
            try:
                contents = list(source_dir.iterdir())
                if not contents or (len(contents) == 1 and contents[0].name == ".gitkeep"):
                    if not self.dry_run:
                        source_dir.rmdir()
                        print(f"🗑️  Removed empty directory: {source_dir.relative_to(self.repo_root)}")
            except Exception:
                pass


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Organize scattered scripts in Autopack repository"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the organization (default is dry-run)"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent.parent,
        help="Repository root directory"
    )

    args = parser.parse_args()

    organizer = ScriptOrganizer(
        repo_root=args.repo_root,
        dry_run=not args.execute
    )

    organizer.organize()


if __name__ == "__main__":
    main()
