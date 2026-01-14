#!/usr/bin/env python3
"""
Enhanced File Cleanup - Multi-File-Type Tidy System

Handles ALL file types intelligently:
- .md → Consolidated to SOT files (handled by consolidate_docs_v2.py)
- .py → scripts/superseded/
- .log → archive/diagnostics/logs/
- .json/.yaml → Categorized by purpose
- .txt → Categorized by content
- .csv/.xlsx → data/archive/
- Other → Flagged for review

Usage:
    python scripts/tidy/enhanced_file_cleanup.py <directory> --dry-run
    python scripts/tidy/enhanced_file_cleanup.py <directory> --execute
"""

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent


class EnhancedFileCleanup:
    """Enhanced cleanup that handles ALL file types, not just .md"""

    def __init__(self, target_directory: str, dry_run: bool = True):
        self.target_directory = target_directory
        self.dry_run = dry_run
        self.target_path = REPO_ROOT / target_directory

        # Destination directories
        self.scripts_superseded = REPO_ROOT / "scripts" / "superseded"
        self.logs_dir = REPO_ROOT / "archive" / "diagnostics" / "logs"
        self.data_archive = REPO_ROOT / "data" / "archive"
        self.config_legacy = REPO_ROOT / "config" / "legacy"
        self.schemas_dir = REPO_ROOT / "docs" / "schemas"
        self.sql_archive = REPO_ROOT / "archive" / "sql"

        # Exclusion paths (never tidy these)
        self.exclusion_paths = [
            REPO_ROOT / "archive" / "tidy_v7",
            REPO_ROOT / "archive" / "prompts",
            REPO_ROOT
            / "archive"
            / "research"
            / "active",  # Active research awaiting Auditor review
        ]

        # Tracking
        self.files_moved: Dict[str, List[Tuple[Path, Path, str]]] = {
            "python": [],
            "logs": [],
            "json": [],
            "yaml": [],
            "txt": [],
            "data": [],
            "sql": [],
            "other": [],
        }

    def run(self):
        """Execute enhanced cleanup"""
        print("=" * 80)
        print("ENHANCED FILE CLEANUP - ALL FILE TYPES")
        print("=" * 80)
        print(f"Target Directory: {self.target_directory}")
        print(f"Mode: {'DRY-RUN (preview only)' if self.dry_run else 'EXECUTE (making changes)'}")
        print("=" * 80)
        print()

        if not self.target_path.exists():
            print(f"❌ Directory not found: {self.target_path}")
            return 1

        # Process each file type
        self._process_python_files()
        self._process_log_files()
        self._process_json_files()
        self._process_yaml_files()
        self._process_txt_files()
        self._process_data_files()
        self._process_sql_files()
        self._process_other_files()

        # Summary
        self._print_summary()

        return 0

    def _is_excluded(self, file_path: Path) -> bool:
        """Check if file is in excluded directory"""
        return any(
            file_path.is_relative_to(excluded)
            for excluded in self.exclusion_paths
            if excluded.exists()
        )

    def _process_python_files(self):
        """Process .py files"""
        print("[1] Processing Python files (.py)...")

        py_files = list(self.target_path.rglob("*.py"))

        # Filter out excluded paths
        py_files = [f for f in py_files if not self._is_excluded(f)]

        print(f"    Found {len(py_files)} Python files (after exclusions)")

        if not py_files:
            return

        for py_file in py_files:
            reason = self._classify_python_file(py_file)
            dest_path = self._get_python_destination(py_file)

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {py_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
                print(f"                  reason: {reason}")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(py_file), str(dest_path))
                print(
                    f"    [MOVED] {py_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["python"].append((py_file, dest_path, reason))

    def _classify_python_file(self, py_file: Path) -> str:
        """Determine why a Python file is being moved"""
        name_lower = py_file.name.lower()

        if "test" in name_lower:
            return "Test script - superseded"
        elif "cleanup" in name_lower or "tidy" in name_lower:
            return "Old cleanup/tidy script - superseded by scripts/tidy/ system"
        elif "diagnostic" in name_lower or "debug" in name_lower:
            return "Diagnostic script - no longer needed"
        elif "temp" in name_lower or "old" in name_lower:
            return "Temporary/old script"
        else:
            return "Script from archived directory - superseded"

    def _get_python_destination(self, py_file: Path) -> Path:
        """Determine destination for Python file"""
        name_lower = py_file.name.lower()

        if "test" in name_lower:
            return self.scripts_superseded / "old_tests" / py_file.name
        elif "cleanup" in name_lower or "tidy" in name_lower:
            return self.scripts_superseded / "old_tidy_scripts" / py_file.name
        elif "diagnostic" in name_lower or "debug" in name_lower:
            return self.scripts_superseded / "old_diagnostic_scripts" / py_file.name
        else:
            return self.scripts_superseded / "other" / py_file.name

    def _process_log_files(self):
        """Process .log files"""
        print("\n[2] Processing log files (.log)...")

        log_files = list(self.target_path.rglob("*.log"))
        log_files = [f for f in log_files if not self._is_excluded(f)]
        print(f"    Found {len(log_files)} log files (after exclusions)")

        if not log_files:
            return

        for log_file in log_files:
            dest_path = self.logs_dir / log_file.name

            # Handle name conflicts
            if dest_path.exists():
                parent_name = log_file.parent.name
                dest_path = self.logs_dir / f"{parent_name}_{log_file.name}"

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {log_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(log_file), str(dest_path))
                print(
                    f"    [MOVED] {log_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["logs"].append((log_file, dest_path, "Centralized log file"))

    def _process_json_files(self):
        """Process .json files"""
        print("\n[3] Processing JSON files (.json)...")

        json_files = list(self.target_path.rglob("*.json"))
        json_files = [f for f in json_files if not self._is_excluded(f)]
        print(f"    Found {len(json_files)} JSON files (after exclusions)")

        if not json_files:
            return

        for json_file in json_files:
            category, reason = self._classify_json_file(json_file)
            dest_path = self._get_json_destination(json_file, category)

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {json_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
                print(f"                category: {category} ({reason})")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(json_file), str(dest_path))
                print(
                    f"    [MOVED] {json_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["json"].append((json_file, dest_path, reason))

    def _classify_json_file(self, json_file: Path) -> Tuple[str, str]:
        """Classify JSON file by purpose"""
        name_lower = json_file.name.lower()

        # Check filename
        if "schema" in name_lower or "spec" in name_lower:
            return ("schema", "JSON schema/specification")
        elif "config" in name_lower or "settings" in name_lower:
            return ("config", "Configuration file")
        elif "package" in name_lower:
            return ("config", "Package configuration (package.json)")

        # Try to read content
        try:
            content = json_file.read_text(encoding="utf-8")
            data = json.loads(content)

            # Check structure
            if "$schema" in data or "properties" in data:
                return ("schema", "JSON schema file")
            elif isinstance(data, dict) and any(
                k in data for k in ["config", "settings", "options"]
            ):
                return ("config", "Configuration data")
            else:
                return ("data", "JSON data file")

        except Exception:
            return ("data", "JSON file (could not parse)")

    def _get_json_destination(self, json_file: Path, category: str) -> Path:
        """Get destination for JSON file"""
        if category == "schema":
            return self.schemas_dir / json_file.name
        elif category == "config":
            return self.config_legacy / json_file.name
        else:  # data
            return self.data_archive / "json" / json_file.name

    def _process_yaml_files(self):
        """Process .yaml/.yml files"""
        print("\n[4] Processing YAML files (.yaml, .yml)...")

        yaml_files = list(self.target_path.rglob("*.yaml")) + list(self.target_path.rglob("*.yml"))
        yaml_files = [f for f in yaml_files if not self._is_excluded(f)]
        print(f"    Found {len(yaml_files)} YAML files (after exclusions)")

        if not yaml_files:
            return

        for yaml_file in yaml_files:
            reason = self._classify_yaml_file(yaml_file)
            dest_path = self.config_legacy / yaml_file.name

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {yaml_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
                print(f"                  reason: {reason}")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(yaml_file), str(dest_path))
                print(
                    f"    [MOVED] {yaml_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["yaml"].append((yaml_file, dest_path, reason))

    def _classify_yaml_file(self, yaml_file: Path) -> str:
        """Classify YAML file"""
        name_lower = yaml_file.name.lower()

        if "config" in name_lower:
            return "Configuration file"
        elif "docker" in name_lower or "compose" in name_lower:
            return "Docker configuration"
        elif "github" in name_lower or "workflow" in name_lower:
            return "GitHub workflow/config"
        else:
            return "YAML configuration file"

    def _process_txt_files(self):
        """Process .txt files"""
        print("\n[5] Processing text files (.txt)...")

        txt_files = list(self.target_path.rglob("*.txt"))
        txt_files = [f for f in txt_files if not self._is_excluded(f)]
        print(f"    Found {len(txt_files)} text files (after exclusions)")

        if not txt_files:
            return

        for txt_file in txt_files:
            category, reason = self._classify_txt_file(txt_file)
            dest_path = self._get_txt_destination(txt_file, category)

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {txt_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
                print(f"                category: {category} ({reason})")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(txt_file), str(dest_path))
                print(
                    f"    [MOVED] {txt_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["txt"].append((txt_file, dest_path, reason))

    def _classify_txt_file(self, txt_file: Path) -> Tuple[str, str]:
        """Classify text file"""
        name_lower = txt_file.name.lower()

        if "log" in name_lower:
            return ("log", "Text log file")
        elif "note" in name_lower or "readme" in name_lower:
            return ("note", "Note/readme file")
        elif "requirements" in name_lower:
            return ("config", "Requirements file")
        else:
            # Check content
            try:
                content = txt_file.read_text(encoding="utf-8")
                if re.search(r"\d{4}-\d{2}-\d{2}.*ERROR|WARN|INFO", content):
                    return ("log", "Log-formatted text file")
                else:
                    return ("note", "Text note/documentation")
            except Exception:
                return ("note", "Text file")

    def _get_txt_destination(self, txt_file: Path, category: str) -> Path:
        """Get destination for text file"""
        if category == "log":
            return self.logs_dir / txt_file.name
        elif category == "config":
            return self.config_legacy / txt_file.name
        else:  # note
            return self.data_archive / "notes" / txt_file.name

    def _process_data_files(self):
        """Process data files (.csv, .xlsx, .xls, .parquet, etc.)"""
        print("\n[6] Processing data files (.csv, .xlsx, .parquet, etc.)...")

        extensions = ["*.csv", "*.xlsx", "*.xls", "*.parquet", "*.feather", "*.pkl", "*.pickle"]
        data_files = []
        for ext in extensions:
            data_files.extend(self.target_path.rglob(ext))

        data_files = [f for f in data_files if not self._is_excluded(f)]
        print(f"    Found {len(data_files)} data files (after exclusions)")

        if not data_files:
            return

        for data_file in data_files:
            dest_path = self.data_archive / data_file.suffix[1:] / data_file.name

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {data_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(data_file), str(dest_path))
                print(
                    f"    [MOVED] {data_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["data"].append((data_file, dest_path, f"{data_file.suffix} data file"))

    def _process_sql_files(self):
        """Process SQL files"""
        print("\n[7] Processing SQL files (.sql)...")

        sql_files = list(self.target_path.rglob("*.sql"))
        sql_files = [f for f in sql_files if not self._is_excluded(f)]
        print(f"    Found {len(sql_files)} SQL files (after exclusions)")

        if not sql_files:
            return

        for sql_file in sql_files:
            # Determine if it's a script or schema
            name_lower = sql_file.name.lower()
            if "schema" in name_lower or "migration" in name_lower:
                dest_path = self.sql_archive / "schemas" / sql_file.name
                reason = "SQL schema/migration"
            else:
                dest_path = self.sql_archive / "scripts" / sql_file.name
                reason = "SQL script"

            if self.dry_run:
                print(f"    [DRY-RUN] Would move: {sql_file.relative_to(REPO_ROOT)}")
                print(f"                      to: {dest_path.relative_to(REPO_ROOT)}")
                print(f"                  reason: {reason}")
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(sql_file), str(dest_path))
                print(
                    f"    [MOVED] {sql_file.relative_to(REPO_ROOT)} → {dest_path.relative_to(REPO_ROOT)}"
                )

            self.files_moved["sql"].append((sql_file, dest_path, reason))

    def _process_other_files(self):
        """Flag other file types for review"""
        print("\n[8] Scanning for other file types...")

        # Get all files
        all_files = list(self.target_path.rglob("*"))
        all_files = [f for f in all_files if f.is_file()]

        # Filter out excluded paths
        all_files = [f for f in all_files if not self._is_excluded(f)]

        # Known extensions we've handled
        handled_extensions = {
            ".md",
            ".py",
            ".log",
            ".json",
            ".yaml",
            ".yml",
            ".txt",
            ".csv",
            ".xlsx",
            ".xls",
            ".parquet",
            ".feather",
            ".pkl",
            ".pickle",
            ".sql",
        }

        # Find unhandled files
        other_files = [f for f in all_files if f.suffix.lower() not in handled_extensions]

        if other_files:
            print(f"    Found {len(other_files)} files with unhandled extensions:")
            for other_file in other_files:
                print(
                    f"    [REVIEW NEEDED] {other_file.relative_to(REPO_ROOT)} ({other_file.suffix or 'no extension'})"
                )
                self.files_moved["other"].append(
                    (other_file, None, f"Unhandled file type: {other_file.suffix}")
                )
        else:
            print("    No unhandled file types found")

    def _print_summary(self):
        """Print summary"""
        print("\n" + "=" * 80)
        print("ENHANCED CLEANUP SUMMARY")
        print("=" * 80)
        print(
            f"Mode: {'DRY-RUN (no changes made)' if self.dry_run else 'EXECUTED (changes applied)'}"
        )
        print()

        total_moved = sum(
            len(files) for category, files in self.files_moved.items() if category != "other"
        )
        print(f"Total files processed: {total_moved}")
        print()

        for category, files in self.files_moved.items():
            if files:
                print(f"{category.upper()}: {len(files)} files")

        if self.files_moved["other"]:
            print()
            print("⚠️  Files requiring manual review:")
            for file_path, _, reason in self.files_moved["other"]:
                print(f"  - {file_path.relative_to(REPO_ROOT)}: {reason}")

        print()
        if self.dry_run:
            print("Run with --execute to apply these changes.")
        else:
            print("✅ Enhanced cleanup complete!")

        print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Enhanced file cleanup for all file types")
    parser.add_argument("directory", help="Directory to clean (relative to project root)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without executing")
    parser.add_argument("--execute", action="store_true", help="Execute changes")
    args = parser.parse_args()

    dry_run = not args.execute if args.execute else True

    cleanup = EnhancedFileCleanup(args.directory, dry_run=dry_run)
    return cleanup.run()


if __name__ == "__main__":
    import sys

    sys.exit(main())
