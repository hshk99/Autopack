#!/usr/bin/env python3
"""
Autopack Documentation Organization Script

Automatically organizes documentation files according to the project's structure:
- Root: Only essential files (README.md, LEARNED_RULES_README.md)
- docs/: Implementation guides
- archive/: Historical reference documents

Also handles FileOrganizer project in .autonomous_runs/:
- Keeps essential planning docs at root
- Archives reference materials and prompts
- Organizes research in docs/research/

Usage:
    python scripts/tidy_docs.py [--dry-run] [--verbose] [--project PROJECT]
"""

import os
import shutil
import json
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime

# Configuration: Define where each type of file should go
AUTOPACK_RULES = {
    "root_essential": {
        "description": "Essential documentation that must stay at root",
        "files": [
            "README.md",
            "LEARNED_RULES_README.md",
        ],
        "patterns": [],
    },

    "docs_guides": {
        "description": "Implementation and technical guides",
        "location": "docs/",
        "patterns": [
            "*IMPLEMENTATION*.md",
            "*GUIDE*.md",
            "*ROUTING*.md",
            "*EFFICIENCY*.md",
        ],
        "keywords": [
            "implementation",
            "guide",
            "routing",
            "efficiency",
            "optimization",
        ],
    },

    "archive_historical": {
        "description": "Historical and reference documentation",
        "location": "archive/",
        "patterns": [
            "*COMPLETE*.md",
            "*HISTORY*.md",
            "*MILESTONE*.md",
            "*ASSESSMENT*.md",
            "*CORRESPONDENCE*.md",
            "*PROMPT*.md",
            "*FEATURES*.md",
            "*DEPLOYMENT*.md",
            "*SETUP*.md",
            "*QUICK_START*.md",
        ],
        "keywords": [
            "complete",
            "history",
            "milestone",
            "assessment",
            "correspondence",
            "gpt",
            "phase",
            "deployment",
            "setup",
            "quick_start",
        ],
    },

    "delete_obsolete": {
        "description": "Obsolete files to delete",
        "patterns": [
            "*.bak",
            "*_backup.md",
            "*_old.md",
            "*_temp.md",
        ],
        "keywords": [
            "backup",
            "old",
            "temp",
            "obsolete",
        ],
    },
}

FILEORGANIZER_RULES = {
    "root_essential": {
        "description": "Essential planning docs at FileOrganizer root",
        "files": [
            "README.md",
            "MASTER_BUILD_PLAN_FILEORGANIZER.md",
            "IMPLEMENTATION_KICKOFF_FILEORGANIZER.md",
            "CURSOR_REVISION_CHECKLIST.md",
        ],
        "patterns": [],
    },

    "docs_research": {
        "description": "Research documents in docs/research/",
        "location": "docs/research/",
        "patterns": [
            "*research*.md",
            "*implementation_plan*.md",
            "*_detailed_spec.md",
        ],
        "keywords": [
            "research",
            "implementation_plan",
            "detailed_spec",
        ],
    },

    "archive_reference": {
        "description": "Reference materials and historical prompts",
        "location": "archive/",
        "patterns": [
            "REF_*.md",
            "ref*.md",
            "*PROMPT*.md",
            "*MARKET_RESEARCH*.md",
            "*GPT_*.md",
            "*cursor_*.md",
            "fileorganizer_product_intent*.md",
            "*STRATEGIC_REVIEW*.md",
        ],
        "keywords": [
            "ref_",
            "ref1",
            "ref2",
            "prompt",
            "market_research",
            "gpt_",
            "cursor_",
            "strategic_review",
            "strategic_analysis",
        ],
    },

    "delete_obsolete": {
        "description": "Obsolete/duplicate files to delete",
        "patterns": [
            "*.bak",
            "*_backup.md",
            "*_old.md",
            "*_temp.md",
            "* - Copy.md",
            "README - Copy.md",
        ],
        "keywords": [
            " - copy",
            "backup",
            "old",
            "temp",
        ],
    },
}


class DocumentationOrganizer:
    def __init__(self, project_root: Path, rules_config: Dict, dry_run: bool = False, verbose: bool = False):
        self.project_root = project_root
        self.rules = rules_config
        self.dry_run = dry_run
        self.verbose = verbose
        self.actions = []

    def log(self, message: str, level: str = "INFO"):
        """Log messages if verbose is enabled"""
        if self.verbose or level == "ACTION":
            prefix = {
                "INFO": "[INFO] ",
                "ACTION": "[MOVE] ",
                "SKIP": "[SKIP] ",
                "DELETE": "[DELETE] ",
                "WARNING": "[WARNING] ",
            }.get(level, "")
            # Use ASCII-safe output for Windows compatibility
            print(f"{prefix}{message}")

    def matches_pattern(self, filename: str, patterns: List[str]) -> bool:
        """Check if filename matches any of the patterns"""
        from fnmatch import fnmatch
        return any(fnmatch(filename, pattern) for pattern in patterns)

    def contains_keyword(self, filename: str, keywords: List[str]) -> bool:
        """Check if filename contains any of the keywords (case-insensitive)"""
        filename_lower = filename.lower()
        return any(keyword.lower() in filename_lower for keyword in keywords)

    def categorize_file(self, filepath: Path) -> tuple[str, str]:
        """
        Categorize a markdown file based on rules.
        Returns: (category, reason)
        """
        filename = filepath.name

        # Check if it's an essential root file
        if filename in self.rules["root_essential"]["files"]:
            return ("root_essential", f"Essential root file: {filename}")

        # Check if it should be deleted
        rules = self.rules["delete_obsolete"]
        if self.matches_pattern(filename, rules.get("patterns", [])) or \
           self.contains_keyword(filename, rules.get("keywords", [])):
            return ("delete_obsolete", f"Obsolete file pattern/keyword matched")

        # Check for docs/ or docs/research/ based on available rules
        if "docs_guides" in self.rules:
            rules = self.rules["docs_guides"]
            if self.matches_pattern(filename, rules.get("patterns", [])) or \
               self.contains_keyword(filename, rules.get("keywords", [])):
                return ("docs_guides", f"Implementation guide pattern/keyword matched")

        if "docs_research" in self.rules:
            rules = self.rules["docs_research"]
            if self.matches_pattern(filename, rules.get("patterns", [])) or \
               self.contains_keyword(filename, rules.get("keywords", [])):
                return ("docs_research", f"Research document pattern/keyword matched")

        # Check for archive/ historical docs
        if "archive_historical" in self.rules:
            rules = self.rules["archive_historical"]
            if self.matches_pattern(filename, rules.get("patterns", [])) or \
               self.contains_keyword(filename, rules.get("keywords", [])):
                return ("archive_historical", f"Historical document pattern/keyword matched")

        if "archive_reference" in self.rules:
            rules = self.rules["archive_reference"]
            if self.matches_pattern(filename, rules.get("patterns", [])) or \
               self.contains_keyword(filename, rules.get("keywords", [])):
                return ("archive_reference", f"Reference material pattern/keyword matched")

        # Default: if unsure, move to archive
        return ("archive_reference" if "archive_reference" in self.rules else "archive_historical",
                "Default: move to archive for review")

    def find_all_markdown_files(self) -> List[Path]:
        """Find all markdown files in the project (excluding node_modules, .git, etc.)"""
        # For FileOrganizer projects, don't exclude .autonomous_runs
        # For Autopack root, exclude it
        is_fileorganizer = "file-organizer" in str(self.project_root).lower()

        exclude_dirs = {
            ".git", "node_modules", ".pytest_cache", "__pycache__",
            ".claude", "prompts", "integrations", "tests"
        }

        if not is_fileorganizer:
            exclude_dirs.add(".autonomous_runs")

        markdown_files = []

        for root, dirs, files in os.walk(self.project_root):
            # Exclude certain directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]

            for file in files:
                if file.endswith(".md"):
                    filepath = Path(root) / file
                    markdown_files.append(filepath)

        return markdown_files

    def organize(self) -> Dict:
        """
        Main organization logic.
        Returns a report of actions taken.
        """
        self.log("Starting documentation organization...", "INFO")
        self.log(f"Project root: {self.project_root}", "INFO")
        self.log(f"Dry run: {self.dry_run}", "INFO")

        # Find all markdown files
        all_md_files = self.find_all_markdown_files()
        self.log(f"Found {len(all_md_files)} markdown files", "INFO")

        # Categorize each file
        actions = {
            "keep_root": [],
            "move_to_docs": [],
            "move_to_docs_research": [],
            "move_to_archive": [],
            "delete": [],
            "no_action": [],
        }

        for filepath in all_md_files:
            relative_path = filepath.relative_to(self.project_root)
            category, reason = self.categorize_file(filepath)

            # Determine action based on category and current location
            if category == "root_essential":
                if filepath.parent == self.project_root:
                    actions["no_action"].append((filepath, "Already in correct location"))
                    self.log(f"SKIP: {relative_path} - Already at root", "SKIP")
                else:
                    # Move to root
                    actions["keep_root"].append((filepath, reason))
                    self.log(f"MOVE to root: {relative_path} - {reason}", "ACTION")

            elif category == "docs_guides":
                docs_dir = self.project_root / "docs"
                if filepath.parent == docs_dir:
                    actions["no_action"].append((filepath, "Already in docs/"))
                    self.log(f"SKIP: {relative_path} - Already in docs/", "SKIP")
                else:
                    actions["move_to_docs"].append((filepath, reason))
                    self.log(f"MOVE to docs/: {relative_path} - {reason}", "ACTION")

            elif category == "docs_research":
                docs_research_dir = self.project_root / "docs" / "research"
                if filepath.parent == docs_research_dir:
                    actions["no_action"].append((filepath, "Already in docs/research/"))
                    self.log(f"SKIP: {relative_path} - Already in docs/research/", "SKIP")
                else:
                    actions["move_to_docs_research"].append((filepath, reason))
                    self.log(f"MOVE to docs/research/: {relative_path} - {reason}", "ACTION")

            elif category == "archive_historical" or category == "archive_reference":
                archive_dir = self.project_root / "archive"
                if filepath.parent == archive_dir:
                    actions["no_action"].append((filepath, "Already in archive/"))
                    self.log(f"SKIP: {relative_path} - Already in archive/", "SKIP")
                else:
                    actions["move_to_archive"].append((filepath, reason))
                    self.log(f"MOVE to archive/: {relative_path} - {reason}", "ACTION")

            elif category == "delete_obsolete":
                actions["delete"].append((filepath, reason))
                self.log(f"DELETE: {relative_path} - {reason}", "DELETE")

        # Execute actions
        if not self.dry_run:
            self._execute_actions(actions)
        else:
            self.log("\n[DRY RUN] No files were actually moved or deleted", "WARNING")

        # Generate report
        report = self._generate_report(actions)
        return report

    def _execute_actions(self, actions: Dict):
        """Execute the file organization actions"""
        self.log("\nExecuting actions...", "INFO")

        # Ensure target directories exist
        (self.project_root / "docs").mkdir(exist_ok=True)
        (self.project_root / "docs" / "research").mkdir(parents=True, exist_ok=True)
        (self.project_root / "archive").mkdir(exist_ok=True)

        # Move to root
        for filepath, reason in actions["keep_root"]:
            target = self.project_root / filepath.name
            if filepath != target:
                shutil.move(str(filepath), str(target))
                self.log(f"Moved {filepath.name} to root", "ACTION")

        # Move to docs/
        for filepath, reason in actions["move_to_docs"]:
            target = self.project_root / "docs" / filepath.name
            if filepath != target:
                shutil.move(str(filepath), str(target))
                self.log(f"Moved {filepath.name} to docs/", "ACTION")

        # Move to docs/research/
        for filepath, reason in actions["move_to_docs_research"]:
            target = self.project_root / "docs" / "research" / filepath.name
            if filepath != target:
                shutil.move(str(filepath), str(target))
                self.log(f"Moved {filepath.name} to docs/research/", "ACTION")

        # Move to archive/
        for filepath, reason in actions["move_to_archive"]:
            target = self.project_root / "archive" / filepath.name
            if filepath != target:
                shutil.move(str(filepath), str(target))
                self.log(f"Moved {filepath.name} to archive/", "ACTION")

        # Delete obsolete files
        for filepath, reason in actions["delete"]:
            filepath.unlink()
            self.log(f"Deleted {filepath.name}", "DELETE")

        # Clean up empty directories
        self._cleanup_empty_dirs()

    def _cleanup_empty_dirs(self):
        """Remove empty directories (except essential ones)"""
        essential_dirs = {"docs", "archive", ".git", "src", "config", "scripts", "tests"}

        for root, dirs, files in os.walk(self.project_root, topdown=False):
            for dir_name in dirs:
                if dir_name in essential_dirs:
                    continue

                dir_path = Path(root) / dir_name
                try:
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        self.log(f"Removed empty directory: {dir_path.relative_to(self.project_root)}", "ACTION")
                except OSError:
                    pass  # Directory not empty or permission issue

    def _generate_report(self, actions: Dict) -> Dict:
        """Generate a summary report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "dry_run": self.dry_run,
            "summary": {
                "total_files": sum(len(v) for v in actions.values()),
                "kept_at_root": len(actions["keep_root"]),
                "moved_to_docs": len(actions["move_to_docs"]),
                "moved_to_docs_research": len(actions.get("move_to_docs_research", [])),
                "moved_to_archive": len(actions["move_to_archive"]),
                "deleted": len(actions["delete"]),
                "no_action": len(actions["no_action"]),
            },
            "actions": {
                key: [(str(f[0].relative_to(self.project_root)), f[1]) for f in files]
                for key, files in actions.items()
            },
        }

        return report


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Organize documentation files automatically for Autopack or FileOrganizer projects"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually moving/deleting files"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--report",
        type=str,
        help="Save JSON report to file"
    )
    parser.add_argument(
        "--project",
        type=str,
        choices=["autopack", "fileorganizer"],
        help="Specify project type (defaults to autopack if run from root, or detects from path)"
    )

    args = parser.parse_args()

    # Determine project root (script is in scripts/ subdirectory)
    script_dir = Path(__file__).parent.parent

    # Determine if we're working with FileOrganizer or Autopack
    if args.project == "fileorganizer":
        project_root = script_dir / ".autonomous_runs" / "file-organizer-app-v1"
        rules_config = FILEORGANIZER_RULES
        project_name = "FileOrganizer"
    else:
        # Default to Autopack root
        project_root = script_dir
        rules_config = AUTOPACK_RULES
        project_name = "Autopack"

    print(f"\nOrganizing {project_name} documentation in: {project_root}\n")

    # Run organizer
    organizer = DocumentationOrganizer(
        project_root=project_root,
        rules_config=rules_config,
        dry_run=args.dry_run,
        verbose=args.verbose
    )

    report = organizer.organize()

    # Print summary
    print("\n" + "="*60)
    print(f"{project_name.upper()} ORGANIZATION SUMMARY")
    print("="*60)
    for key, value in report["summary"].items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    print("="*60)

    if args.dry_run:
        print("\n[WARNING] This was a DRY RUN. Run without --dry-run to apply changes.")

    # Save report if requested
    if args.report:
        with open(args.report, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {args.report}")


if __name__ == "__main__":
    main()
