#!/usr/bin/env python3
"""
Corrective Cleanup V2 - Implements PROPOSED_CLEANUP_STRUCTURE_V2.md

This script fixes the structural issues identified in WORKSPACE_ISSUES_ANALYSIS.md
and implements the corrected organization principles.

Integrates with Autopack's tidy system for reusability.

NOTE: Some files in .autonomous_runs/ are intentional and should NOT be moved:
  - file-organizer-phase2-run.json: Run configuration file
  - tidy_semantic_cache.json: Tidy system cache file
These are working files for the autonomous run system, not archives.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict
import re

REPO_ROOT = Path(__file__).parent.parent


def git_checkpoint(message: str) -> bool:
    """Create a git checkpoint commit."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True, capture_output=True)
        result = subprocess.run(["git", "commit", "-m", message], cwd=REPO_ROOT, check=True, capture_output=True)
        print(f"\n[GIT] Created checkpoint: {message}")
        return True
    except subprocess.CalledProcessError:
        print(f"\n[GIT] No changes to commit")
        return False


def safe_move(src: Path, dest: Path) -> bool:
    """Safely move file or folder."""
    if not src.exists():
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        if src.is_file() and dest.is_file():
            return False  # Skip duplicate
        elif src.is_dir() and dest.is_dir():
            # Merge folders
            for item in src.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(src)
                    dest_file = dest / rel_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    if not dest_file.exists():
                        shutil.move(str(item), str(dest_file))
            shutil.rmtree(src)
            return True

    shutil.move(str(src), str(dest))
    return True


def safe_delete(path: Path) -> bool:
    """Safely delete file or folder."""
    if not path.exists():
        return False

    if path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
    return True


# ============================================================================
# PHASE 1: Root Directory Cleanup
# ============================================================================

def phase1_root_cleanup(dry_run: bool = True) -> None:
    """Consolidate ALL truth source files to docs/ folder."""
    print("\n" + "=" * 80)
    print("PHASE 1: ROOT DIRECTORY CLEANUP - CONSOLIDATE TO docs/")
    print("=" * 80)

    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # 1.1 Move truth source .md files to docs/
    truth_md_files = [
        "WORKSPACE_ORGANIZATION_SPEC.md",
        "WHATS_LEFT_TO_BUILD.md",
        "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"
    ]

    moved_md = 0

    print("\n[1.1] Moving truth source .md files to docs/")
    for md_file in truth_md_files:
        src = REPO_ROOT / md_file
        if src.exists():
            dest = docs_dir / md_file
            print(f"  {md_file} -> docs/")
            if not dry_run:
                safe_move(src, dest)
                moved_md += 1

    # 1.2 Move ruleset/config .json files to docs/
    ruleset_files = [
        "project_ruleset_Autopack.json",
        "project_issue_backlog.json",
        "autopack_phase_plan.json"
    ]

    moved_rulesets = 0

    print("\n[1.2] Moving ruleset/config .json files to docs/")
    for ruleset_file in ruleset_files:
        src = REPO_ROOT / ruleset_file
        if src.exists():
            dest = docs_dir / ruleset_file
            print(f"  {ruleset_file} -> docs/")
            if not dry_run:
                safe_move(src, dest)
                moved_rulesets += 1

    # 1.3 Move API specifications to docs/api/
    api_specs = ["openapi.json"]
    api_dir = REPO_ROOT / "docs" / "api"
    moved_apis = 0

    print("\n[1.3] Moving API specifications to docs/api/")
    for api_file in api_specs:
        src = REPO_ROOT / api_file
        if src.exists():
            dest = api_dir / api_file
            print(f"  {api_file} -> docs/api/")
            if not dry_run:
                safe_move(src, dest)
                moved_apis += 1

    # 1.4 Move diagnostic data to archive/diagnostics/
    diag_files = [
        "test_run.json",
        "builder_fullfile_failure_latest.json"
    ]

    diag_dir = REPO_ROOT / "archive" / "diagnostics"
    moved_diags = 0

    print("\n[1.4] Moving diagnostic data to archive/diagnostics/")
    for diag_file in diag_files:
        src = REPO_ROOT / diag_file
        if src.exists():
            dest = diag_dir / diag_file
            print(f"  {diag_file} -> archive/diagnostics/")
            if not dry_run:
                safe_move(src, dest)
                moved_diags += 1

    # 1.5 Archive obsolete documentation files
    docs_to_archive = {
        "RUN_COMMAND.txt": "archive/docs/",
        "STRUCTURE_VERIFICATION_FINAL.md": "archive/reports/",
        # Cleanup-related documentation (from this cleanup process)
        "CLEANUP_V2_SUMMARY.md": "archive/reports/",
        "CONSOLIDATION_TO_DOCS_SUMMARY.md": "archive/reports/",
        "DOCS_CONSOLIDATION_COMPLETE.md": "archive/reports/",
        "FILE_RELOCATION_MAP.md": "archive/reports/",
        "IMPLEMENTATION_PLAN_CLEANUP_V2.md": "archive/reports/",
        "WORKSPACE_ISSUES_ANALYSIS.md": "archive/reports/",
        "PROPOSED_CLEANUP_STRUCTURE_V2.md": "archive/reports/",
    }

    moved_archive_docs = 0

    print("\n[1.5] Archiving obsolete documentation files")
    for doc_file, dest_folder in docs_to_archive.items():
        src = REPO_ROOT / doc_file
        if src.exists():
            dest = REPO_ROOT / dest_folder / doc_file
            print(f"  {doc_file} -> {dest_folder}")
            if not dry_run:
                safe_move(src, dest)
                moved_archive_docs += 1

    print(f"\n[PHASE 1] Summary:")
    print(f"  - Moved {moved_md} truth source .md files to docs/")
    print(f"  - Moved {moved_rulesets} ruleset .json files to docs/")
    print(f"  - Moved {moved_apis} API specs to docs/api/")
    print(f"  - Moved {moved_diags} diagnostic files to archive/")
    print(f"  - Archived {moved_archive_docs} obsolete docs")
    print(f"  NOTE: Root README.md stays as quick-start (will link to docs/README.md)")


# ============================================================================
# PHASE 2: Archive Restructuring
# ============================================================================

def phase2_archive_restructuring(dry_run: bool = True) -> None:
    """Eliminate archive/src, group runs, flatten nesting."""
    print("\n" + "=" * 80)
    print("PHASE 2: ARCHIVE RESTRUCTURING")
    print("=" * 80)

    # 2.1 Eliminate archive/src/
    archive_src = REPO_ROOT / "archive" / "src"

    print("\n[2.1] Handling archive/src/")
    if archive_src.exists():
        # Check if files exist in current src/
        current_src = REPO_ROOT / "src" / "autopack" / "diagnostics"

        if current_src.exists():
            print("  diagnostics/ exists in current src/ - archiving old version")
            superseded = REPO_ROOT / "archive" / "superseded" / "diagnostics_v1"
            print(f"  archive/src/autopack/diagnostics/ -> archive/superseded/diagnostics_v1/")
            if not dry_run:
                safe_move(archive_src / "autopack" / "diagnostics", superseded)
                # Remove empty folders
                safe_delete(archive_src)
        else:
            print("  diagnostics/ NOT in current src/ - appears obsolete")
            print("  DECISION NEEDED: Review files before deleting")
            print(f"  Files: {list(archive_src.rglob('*.py'))[:5]}")
    else:
        print("  [SKIP] archive/src/ does not exist")

    # 2.2 Group runs by project
    runs_dir = REPO_ROOT / "archive" / "diagnostics" / "runs"

    print("\n[2.2] Grouping runs by project")
    if runs_dir.exists():
        # Create project folders
        autopack_runs = runs_dir / "Autopack"
        fileorg_runs = runs_dir / "file-organizer"
        unknown_runs = runs_dir / "unknown"

        if not dry_run:
            autopack_runs.mkdir(exist_ok=True)
            fileorg_runs.mkdir(exist_ok=True)
            unknown_runs.mkdir(exist_ok=True)

        # Move fileorg-* runs
        moved_fileorg = 0
        for item in runs_dir.iterdir():
            if item.is_dir() and item.name.startswith("fileorg-"):
                dest = fileorg_runs / item.name
                print(f"  {item.name} -> file-organizer/")
                if not dry_run:
                    safe_move(item, dest)
                    moved_fileorg += 1

        print(f"  Moved {moved_fileorg} file-organizer runs")

        # Handle nested project folders
        print("\n  [2.2.1] Flattening nested folders")
        for nested_folder in ["archive", "file-organizer-app-v1"]:
            nested_path = runs_dir / nested_folder
            if nested_path.exists() and nested_path.is_dir():
                print(f"    Flattening runs/{nested_folder}/")
                # Move contents to appropriate location
                if not dry_run:
                    for item in nested_path.iterdir():
                        if item.is_dir():
                            # Try to classify
                            if "fileorg" in item.name.lower():
                                dest = fileorg_runs / item.name
                            else:
                                dest = unknown_runs / item.name
                            safe_move(item, dest)
                    safe_delete(nested_path)

        # Flatten Autopack excessive nesting
        autopack_nested = runs_dir / "Autopack" / ".autonomous_runs"
        if autopack_nested.exists():
            print(f"    Flattening Autopack/.autonomous_runs/ nesting")
            if not dry_run:
                # Extract runs to Autopack/ level
                for item in autopack_nested.rglob("*"):
                    if item.is_dir() and "unknowns" in item.name:
                        dest = autopack_runs / "unknowns"
                        safe_move(item, dest)
                safe_delete(autopack_nested)

    # 2.3 Flatten superseded nested structures
    print("\n[2.3] Flattening superseded nested structures")

    superseded_dir = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive" / "superseded"
    if superseded_dir.exists():
        nested_autonomous = superseded_dir / ".autonomous_runs"
        if nested_autonomous.exists():
            print(f"  Found nested .autonomous_runs/ inside superseded/")
            if not dry_run:
                # Flatten contents up to superseded level
                for item in nested_autonomous.rglob("*"):
                    if item.is_file():
                        # Calculate relative path from nested_autonomous
                        rel_path = item.relative_to(nested_autonomous)
                        dest = superseded_dir / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        print(f"    Flattening: {rel_path}")
                        safe_move(item, dest)
                # Remove now-empty nested structure
                safe_delete(nested_autonomous)
                print(f"  [OK] Flattened and removed nested .autonomous_runs/")
            else:
                print(f"  [DRY-RUN] Would flatten nested .autonomous_runs/")

        # Also flatten any nested archive/ folders
        nested_archive = superseded_dir / "archive"
        if nested_archive.exists():
            print(f"  Found nested archive/ inside superseded/")
            if not dry_run:
                for item in nested_archive.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(nested_archive)
                        dest = superseded_dir / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        print(f"    Flattening: {rel_path}")
                        safe_move(item, dest)
                safe_delete(nested_archive)
                print(f"  [OK] Flattened and removed nested archive/")
            else:
                print(f"  [DRY-RUN] Would flatten nested archive/")
    else:
        print("  [SKIP] superseded/ does not exist")

    # 2.4 Rename diagnostic data folder
    autopack_data = REPO_ROOT / "archive" / "diagnostics" / "autopack_data"
    data_folder = REPO_ROOT / "archive" / "diagnostics" / "data"

    print("\n[2.4] Renaming diagnostic data folder")
    if autopack_data.exists() and not data_folder.exists():
        print(f"  autopack_data/ -> data/")
        if not dry_run:
            autopack_data.rename(data_folder)
    else:
        print("  [SKIP] Already renamed or doesn't exist")

    print(f"\n[PHASE 2] Complete")


# ============================================================================
# PHASE 3: .autonomous_runs Cleanup
# ============================================================================

def phase3_autonomous_runs_cleanup(dry_run: bool = True) -> None:
    """Rename checkpoints, add truth sources, handle Autopack folder."""
    print("\n" + "=" * 80)
    print("PHASE 3: .AUTONOMOUS_RUNS CLEANUP")
    print("=" * 80)

    autonomous_root = REPO_ROOT / ".autonomous_runs"

    # 3.1 Rename checkpoints to tidy_checkpoints
    checkpoints = autonomous_root / "checkpoints"
    tidy_checkpoints = autonomous_root / "tidy_checkpoints"

    print("\n[3.1] Renaming checkpoints folder")
    if checkpoints.exists() and not tidy_checkpoints.exists():
        print(f"  checkpoints/ -> tidy_checkpoints/")
        if not dry_run:
            checkpoints.rename(tidy_checkpoints)
            print("  NOTE: May need to update tidy_workspace.py references")
    else:
        print("  [SKIP] Already renamed or doesn't exist")

    # 3.2 Consolidate file-organizer truth sources to docs/
    fileorg_project = autonomous_root / "file-organizer-app-v1"
    fileorg_docs = fileorg_project / "docs"

    print("\n[3.2] Consolidating file-organizer truth sources to docs/")
    if fileorg_project.exists():
        # Ensure docs/ exists
        if not dry_run:
            fileorg_docs.mkdir(parents=True, exist_ok=True)

        # Move README.md from project root to docs/ (comprehensive version)
        project_readme = fileorg_project / "README.md"
        docs_readme = fileorg_docs / "README.md"

        if project_readme.exists() and not docs_readme.exists():
            print(f"  Moving README.md from project root to docs/ (comprehensive)")
            if not dry_run:
                safe_move(project_readme, docs_readme)
        elif project_readme.exists() and docs_readme.exists():
            print(f"  README.md exists in both locations - keeping docs/ version")
            if not dry_run:
                # Archive the project root one
                (fileorg_project / "archive" / "superseded").mkdir(parents=True, exist_ok=True)
                safe_move(project_readme, fileorg_project / "archive" / "superseded" / "README_OLD.md")

        # Move WHATS_LEFT_TO_BUILD.md from project root to docs/
        project_roadmap = fileorg_project / "WHATS_LEFT_TO_BUILD.md"
        docs_roadmap = fileorg_docs / "WHATS_LEFT_TO_BUILD.md"

        if project_roadmap.exists() and not docs_roadmap.exists():
            print(f"  Moving WHATS_LEFT_TO_BUILD.md from project root to docs/")
            if not dry_run:
                safe_move(project_roadmap, docs_roadmap)
        elif project_roadmap.exists() and docs_roadmap.exists():
            print(f"  WHATS_LEFT_TO_BUILD.md exists in both locations - keeping docs/ version")
            if not dry_run:
                (fileorg_project / "archive" / "superseded").mkdir(parents=True, exist_ok=True)
                safe_move(project_roadmap, fileorg_project / "archive" / "superseded" / "WHATS_LEFT_TO_BUILD_OLD.md")

        # Create quick-start README.md at project root
        project_readme_quickstart = fileorg_project / "README.md"
        if not project_readme_quickstart.exists():
            print(f"  Creating quick-start README.md at project root")
            if not dry_run:
                project_readme_quickstart.write_text("""# FileOrganizer

AI-powered document organization system for immigration visa packs.

## Quick Start

For comprehensive documentation, see [docs/README.md](docs/README.md).

## Key Documentation

- **[Setup & Usage](docs/README.md)** - Full project documentation
- **[Roadmap](docs/WHATS_LEFT_TO_BUILD.md)** - Current development status
- **[Rules](docs/project_learned_rules.json)** - Project learned rules

## Project Structure

- `src/` - Source code
- `scripts/` - Utility scripts
- `packs/` - Document packs
- `docs/` - All documentation (truth sources)
- `archive/` - Historical files

## Development

See [docs/README.md](docs/README.md) for development setup and contributing guidelines.
""")

        # Move all SOT files from project root to docs/
        fileorg_sot_files = {
            "project_learned_rules.json": "Project learned rules",
            "autopack_phase_plan.json": "Phase plan",
            "plan_maintenance.json": "Maintenance plan",
            "plan_maintenance_clean.json": "Clean maintenance plan",
            "plan_task7.json": "Task 7 plan",
            "rules_updated.json": "Updated rules",
        }

        moved_fileorg_sot = 0
        for sot_file, description in fileorg_sot_files.items():
            src = fileorg_project / sot_file
            dest = fileorg_docs / sot_file

            if dest.exists():
                print(f"  [OK] {sot_file} already in docs/")
            elif src.exists():
                print(f"  Moving {sot_file} to docs/ ({description})")
                if not dry_run:
                    safe_move(src, dest)
                    moved_fileorg_sot += 1
            else:
                print(f"  [SKIP] {sot_file} not found ({description})")

        if moved_fileorg_sot > 0:
            print(f"  Moved {moved_fileorg_sot} SOT files to file-organizer docs/")

        # Replace outdated docs/README.md with proper comprehensive README
        docs_readme_old = fileorg_docs / "README.md"
        if docs_readme_old.exists():
            content = docs_readme_old.read_text(encoding="utf-8")
            if "Unsorted Inbox" in content or len(content) < 1000:
                print(f"  Replacing outdated docs/README.md with comprehensive version")
                if not dry_run:
                    docs_readme_old.write_text("""# FileOrganizer - Complete Documentation

AI-powered document organization system for immigration visa packs.

## Overview

FileOrganizer automatically processes, classifies, and organizes immigration documentation using AI-powered analysis. It handles multiple visa types and maintains structured pack organization.

## Features

- **Intelligent Classification**: Automatically categorizes documents by type
- **Multi-Visa Support**: Handles various visa application types
- **Pack Management**: Organizes documents into structured packs
- **AI-Powered Analysis**: Uses LLM for document understanding
- **Batch Processing**: Efficiently handles multiple documents

## Project Structure

```
file-organizer-app-v1/
├── src/                    # Source code
├── scripts/                # Utility scripts
├── packs/                  # Document packs
├── docs/                   # All documentation (YOU ARE HERE)
│   ├── README.md          # This file
│   ├── WHATS_LEFT_TO_BUILD.md
│   ├── ARCHITECTURE.md
│   ├── project_learned_rules.json
│   └── *.json             # Phase plans and configurations
└── archive/               # Historical files and runs
```

## Getting Started

[Setup instructions to be added]

## Documentation Files

- **[WHATS_LEFT_TO_BUILD.md](WHATS_LEFT_TO_BUILD.md)** - Current development roadmap
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture
- **project_learned_rules.json** - Project-specific rules and patterns
- **autopack_phase_plan.json** - Autopack execution phases

## Development

[Development guidelines to be added]

## Related Projects

This is a subproject within the Autopack framework workspace.
""", encoding="utf-8")

        # Create ARCHITECTURE.md stub if it doesn't exist
        arch = fileorg_docs / "ARCHITECTURE.md"
        if not arch.exists():
            print(f"  Creating ARCHITECTURE.md stub")
            if not dry_run:
                arch.write_text("""# FileOrganizer Architecture

## Overview

FileOrganizer is an AI-powered document organization system for immigration visa packs.

## Components

### 1. Pack Compiler
[To be documented]

### 2. Classification System
[To be documented]

### 3. Backend API
[To be documented]

## Data Flow

[To be documented]
""")
    else:
        print("  [SKIP] file-organizer-app-v1 project not found")

    # 3.3 Handle Autopack folder
    autopack_folder = autonomous_root / "Autopack"

    print("\n[3.3] Handling Autopack folder")
    if autopack_folder.exists():
        # Check if it only has archive/
        contents = list(autopack_folder.iterdir())
        if len(contents) == 1 and contents[0].name == "archive":
            print(f"  Autopack/ only has archive/ - merging to main archive")
            if not dry_run:
                # Move archive contents to main archive
                autopack_archive = contents[0]
                main_archive = REPO_ROOT / "archive"
                for item in autopack_archive.iterdir():
                    # Merge with main archive structure
                    dest = main_archive / item.name
                    safe_move(item, dest)
                # Delete empty Autopack folder
                safe_delete(autopack_folder)
        else:
            print(f"  Autopack/ has active content - adding README.md")
            readme = autopack_folder / "README.md"
            if not readme.exists() and not dry_run:
                readme.write_text("""# Autopack Autonomous Runs

This folder contains autonomous execution runs for Autopack self-improvement.

## Purpose

Autopack uses this folder for self-directed development and improvements.

## Structure

- `archive/` - Historical runs and outputs
""")

    print(f"\n[PHASE 3] Complete")


# ============================================================================
# PHASE 4: Documentation Creation
# ============================================================================

def phase4_restore_documentation(dry_run: bool = True) -> None:
    """Restore truth source documentation files that were archived.

    This includes:
    - Autopack documentation files (DEPLOYMENT_GUIDE.md, etc.)
    - Auto-generated CONSOLIDATED_*.md files
    - Auto-generated ARCHIVE_INDEX.md
    - file-organizer project truth sources
    - Ruleset files (already at root - just verify)
    """
    print("\n" + "=" * 80)
    print("PHASE 4: RESTORE TRUTH SOURCE DOCUMENTATION")
    print("=" * 80)

    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    restored = 0
    missing = []

    # ========================================================================
    # SECTION 4.1: Autopack Documentation Files
    # ========================================================================
    print("\n[4.1] Autopack Documentation - Restoring archived truth sources")

    # Map of docs to restore: destination -> source location
    autopack_docs_to_restore = {
        "DEPLOYMENT_GUIDE.md": REPO_ROOT / "archive" / "reports" / "DEPLOYMENT_GUIDE.md",
        # SETUP_GUIDE.md already exists in docs/
    }

    for doc_name, source_path in autopack_docs_to_restore.items():
        dest_path = docs_dir / doc_name

        if dest_path.exists():
            print(f"  [SKIP] {doc_name} already in docs/")
            continue

        if source_path.exists():
            print(f"  {doc_name} <- archive/{source_path.relative_to(REPO_ROOT / 'archive')}")
            if not dry_run:
                safe_move(source_path, dest_path)
                restored += 1
        else:
            print(f"  [NOT FOUND] {doc_name} - searching for alternatives...")
            missing.append(doc_name)

    # ========================================================================
    # SECTION 4.2: CONSOLIDATED_*.md Files - Move to docs/
    # ========================================================================
    print("\n[4.2] CONSOLIDATED_*.md Files - Moving to docs/ for easy access")
    print("  Note: These are frequently-referenced living documents")
    print("        Moving from archive/reports/ and archive/research/ to docs/")

    # Map source locations in archive subdirs -> docs/
    consolidated_sources = {
        "CONSOLIDATED_CORRESPONDENCE.md": REPO_ROOT / "archive" / "reports" / "CONSOLIDATED_CORRESPONDENCE.md",
        "CONSOLIDATED_MISC.md": REPO_ROOT / "archive" / "reports" / "CONSOLIDATED_MISC.md",
        "CONSOLIDATED_REFERENCE.md": REPO_ROOT / "archive" / "reports" / "CONSOLIDATED_REFERENCE.md",
        "CONSOLIDATED_RESEARCH.md": REPO_ROOT / "archive" / "research" / "CONSOLIDATED_RESEARCH.md",
        "CONSOLIDATED_STRATEGY.md": REPO_ROOT / "archive" / "research" / "CONSOLIDATED_STRATEGY.md",
        "CONSOLIDATED_DEBUG.md": REPO_ROOT / "archive" / "diagnostics" / "docs" / "CONSOLIDATED_DEBUG.md",
    }

    moved_consolidated = 0
    for consolidated_name, source_path in consolidated_sources.items():
        dest_path = docs_dir / consolidated_name

        if dest_path.exists():
            print(f"  [SKIP] {consolidated_name} already in docs/")
            continue

        if source_path.exists():
            print(f"  {consolidated_name} <- {source_path.relative_to(REPO_ROOT)}")
            if not dry_run:
                safe_move(source_path, dest_path)
                moved_consolidated += 1
        else:
            print(f"  [NOT FOUND] {consolidated_name} at {source_path.relative_to(REPO_ROOT)}")
            print(f"              (will be auto-generated on next consolidate run)")

    print(f"  Moved {moved_consolidated} CONSOLIDATED_*.md files to docs/")

    # Move file-organizer CONSOLIDATED files to project docs/
    print("\n  File-organizer CONSOLIDATED files - Moving to project docs/:")
    fo_project_dir = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
    fo_docs_dir = fo_project_dir / "docs"
    fo_archive_dir = fo_project_dir / "archive"

    fo_consolidated_sources = {
        "CONSOLIDATED_DEBUG.md": [
            fo_archive_dir / "reports" / "CONSOLIDATED_DEBUG.md",
            fo_archive_dir / "CONSOLIDATED_DEBUG.md",
        ],
        "CONSOLIDATED_RESEARCH.md": [
            fo_archive_dir / "research" / "CONSOLIDATED_RESEARCH.md",
            fo_archive_dir / "CONSOLIDATED_RESEARCH.md",
        ],
        "CONSOLIDATED_REFERENCE.md": [
            fo_archive_dir / "reports" / "CONSOLIDATED_REFERENCE.md",
            fo_archive_dir / "CONSOLIDATED_REFERENCE.md",
        ],
    }

    moved_fo_consolidated = 0
    for name, possible_sources in fo_consolidated_sources.items():
        dest = fo_docs_dir / name

        if dest.exists():
            print(f"  [OK] {name} already in docs/")
            continue

        # Try each possible source location
        found = False
        for source_path in possible_sources:
            if source_path.exists():
                print(f"  {name} -> file-organizer-app-v1/docs/")
                if not dry_run:
                    safe_move(source_path, dest)
                    moved_fo_consolidated += 1
                found = True
                break

        if not found:
            print(f"  [SKIP] {name} not found (will be auto-generated)")

    if moved_fo_consolidated > 0:
        print(f"  Moved {moved_fo_consolidated} CONSOLIDATED files to file-organizer docs/")

    # ========================================================================
    # SECTION 4.3: ARCHIVE_INDEX.md (Auto-Generated)
    # ========================================================================
    print("\n[4.3] ARCHIVE_INDEX.md - Verifying auto-generated index")

    archive_index_path = REPO_ROOT / "archive" / "reports" / "ARCHIVE_INDEX.md"
    if archive_index_path.exists():
        print(f"  [OK] ARCHIVE_INDEX.md exists at archive/reports/")
        print(f"       (Auto-generated by scripts/consolidate_docs.py)")
    else:
        print(f"  [MISSING] ARCHIVE_INDEX.md (will be created on next consolidate_docs.py run)")

    # ========================================================================
    # SECTION 4.4: Ruleset/Config Files (Will be moved in Phase 1)
    # ========================================================================
    print("\n[4.4] Ruleset & Config Files - Status check")
    print("  Note: These are auto-updated by various Autopack scripts")
    print("        Phase 1 will move them from root to docs/")

    ruleset_files = {
        "project_ruleset_Autopack.json": "Project-wide rules (auto-updated)",
        "project_issue_backlog.json": "Issue backlog (auto-updated)",
        "autopack_phase_plan.json": "Phase plan (auto-updated)",
    }

    for ruleset_name, description in ruleset_files.items():
        docs_path = docs_dir / ruleset_name
        root_path = REPO_ROOT / ruleset_name

        if docs_path.exists():
            print(f"  [OK] {ruleset_name} in docs/ - {description}")
        elif root_path.exists():
            print(f"  [PENDING] {ruleset_name} at root - will be moved to docs/ in Phase 1")
        else:
            print(f"  [MISSING] {ruleset_name} - {description}")

    # ========================================================================
    # SECTION 4.5: file-organizer Truth Sources
    # ========================================================================
    print("\n[4.5] File-Organizer Project - Verifying truth sources")

    fo_project_dir = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
    fo_docs_dir = fo_project_dir / "docs"

    # Check README.md (already exists)
    fo_readme = fo_project_dir / "README.md"
    if fo_readme.exists():
        print(f"  [OK] README.md exists at .autonomous_runs/file-organizer-app-v1/")
    else:
        print(f"  [MISSING] README.md (should exist)")

    # Check for ARCHITECTURE.md in docs/ or archive
    fo_architecture = fo_docs_dir / "ARCHITECTURE.md"
    if fo_architecture.exists():
        print(f"  [OK] ARCHITECTURE.md exists in docs/")
    else:
        # Search archive for it
        print(f"  [NOT FOUND] ARCHITECTURE.md in docs/ - searching archive...")
        # (Could search here if needed, but likely doesn't exist)
        print(f"  [MISSING] ARCHITECTURE.md (may never have been created)")

    # Check WHATS_LEFT_TO_BUILD.md
    fo_roadmap = fo_project_dir / "WHATS_LEFT_TO_BUILD.md"
    if fo_roadmap.exists():
        print(f"  [OK] WHATS_LEFT_TO_BUILD.md exists")
    else:
        print(f"  [MISSING] WHATS_LEFT_TO_BUILD.md")

    # ========================================================================
    # SECTION 4.6: Summary
    # ========================================================================
    print("\n[4.6] Documentation status summary")

    autopack_docs_status = {
        "SETUP_GUIDE.md": (docs_dir / "SETUP_GUIDE.md").exists(),
        "DEPLOYMENT_GUIDE.md": (docs_dir / "DEPLOYMENT_GUIDE.md").exists(),
        "ARCHITECTURE.md": (docs_dir / "ARCHITECTURE.md").exists(),
        "API_REFERENCE.md": (docs_dir / "API_REFERENCE.md").exists(),
        "CONTRIBUTING.md": (docs_dir / "CONTRIBUTING.md").exists(),
    }

    print("\n  Autopack docs/ status:")
    for doc_name, exists in autopack_docs_status.items():
        status = "[OK]" if exists else "[MISSING]"
        note = "" if exists else " (may never have existed)"
        print(f"    {status} {doc_name}{note}")

    print(f"\n[PHASE 4] Restored {restored} truth source files from archive")
    if missing:
        print(f"  Note: {len(missing)} files not found in archive (may never have existed)")


# ============================================================================
# PHASE 5: Organize Cleanup Documentation & Scripts
# ============================================================================

def phase5_organize_cleanup_artifacts(dry_run: bool = True) -> None:
    """Group cleanup-related documentation and scripts for reusability."""
    print("\n" + "=" * 80)
    print("PHASE 5: ORGANIZE CLEANUP DOCUMENTATION & SCRIPTS")
    print("=" * 80)

    # 5.1 Group cleanup documentation in archive/tidy_v7/ (top level for easy access)
    print("\n[5.1] Grouping cleanup documentation in archive/tidy_v7/")

    tidy_docs_dir = REPO_ROOT / "archive" / "tidy_v7"
    if not dry_run:
        tidy_docs_dir.mkdir(parents=True, exist_ok=True)

    # Check both archive/reports/ and archive/reports/tidy_v7/ as possible sources
    cleanup_docs_sources = [
        REPO_ROOT / "archive" / "reports" / "tidy_v7",
        REPO_ROOT / "archive" / "reports",
    ]

    cleanup_doc_names = [
        "CLEANUP_V2_SUMMARY.md",
        "CONSOLIDATION_TO_DOCS_SUMMARY.md",
        "DOCS_CONSOLIDATION_COMPLETE.md",
        "FILE_RELOCATION_MAP.md",
        "IMPLEMENTATION_PLAN_CLEANUP_V2.md",
        "WORKSPACE_ISSUES_ANALYSIS.md",
        "PROPOSED_CLEANUP_STRUCTURE_V2.md",
    ]

    moved_cleanup_docs = 0
    for doc_name in cleanup_doc_names:
        dest = tidy_docs_dir / doc_name

        if dest.exists():
            print(f"  [SKIP] {doc_name} already in tidy_v7/")
            continue

        # Try to find the file in possible source locations
        found = False
        for source_dir in cleanup_docs_sources:
            src = source_dir / doc_name
            if src.exists():
                print(f"  {doc_name} -> archive/tidy_v7/")
                if not dry_run:
                    safe_move(src, dest)
                    moved_cleanup_docs += 1
                found = True
                break

        if not found:
            print(f"  [SKIP] {doc_name} not found")

    print(f"  Grouped {moved_cleanup_docs} cleanup documents")

    # 5.2 Group tidy/cleanup scripts
    print("\n[5.2] Grouping tidy/cleanup scripts in scripts/tidy/")

    tidy_scripts_dir = REPO_ROOT / "scripts" / "tidy"
    if not dry_run:
        tidy_scripts_dir.mkdir(parents=True, exist_ok=True)

    tidy_scripts = [
        "tidy_workspace.py",
        "tidy_docs.py",
        "tidy_logger.py",
        "run_tidy_all.py",
        "corrective_cleanup.py",
        "corrective_cleanup_v2.py",
        "comprehensive_cleanup.py",
    ]

    # Get the currently running script to avoid moving it while running
    current_script = Path(__file__).name

    moved_scripts = 0
    for script_name in tidy_scripts:
        src = REPO_ROOT / "scripts" / script_name
        dest = tidy_scripts_dir / script_name

        # Skip moving the currently running script
        if script_name == current_script:
            print(f"  [SKIP] {script_name} (currently running - move manually after)")
            continue

        if dest.exists():
            print(f"  [SKIP] {script_name} already in tidy/")
        elif src.exists():
            print(f"  {script_name} -> scripts/tidy/")
            if not dry_run:
                safe_move(src, dest)
                moved_scripts += 1
        else:
            print(f"  [SKIP] {script_name} not found")

    print(f"  Grouped {moved_scripts} tidy/cleanup scripts")

    print(f"\n[PHASE 5] Complete")


# ============================================================================
# PHASE 6: Synchronize SOT Files
# ============================================================================

def phase6_synchronize_sot_files(dry_run: bool = True) -> None:
    """Synchronize all Source of Truth files after cleanup.

    Ensures all SOT files (docs/, DBs, CONSOLIDATED_*.md) are up-to-date
    regardless of who made changes (Cursor, Autopack, manual edits).
    """
    print("\n" + "=" * 80)
    print("PHASE 6: SYNCHRONIZE SOURCE OF TRUTH FILES")
    print("=" * 80)

    if dry_run:
        print("\n[DRY-RUN] Would synchronize SOT files:")
        print("  - Update CONSOLIDATED_*.md via consolidate_docs.py")
        print("  - Sync project_ruleset_Autopack.json")
        print("  - Sync project_issue_backlog.json")
        print("  - Update ARCHIVE_INDEX.md")
        print(f"\n[PHASE 6] Complete (dry-run)")
        return

    # 6.1 Update CONSOLIDATED_*.md files
    print("\n[6.1] Updating CONSOLIDATED_*.md files")

    consolidate_script = REPO_ROOT / "scripts" / "consolidate_docs.py"
    if consolidate_script.exists():
        print("  Running scripts/consolidate_docs.py...")
        try:
            result = subprocess.run(
                ["python", str(consolidate_script)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                print("  [OK] CONSOLIDATED_*.md files updated")
            else:
                print(f"  [WARNING] consolidate_docs.py returned {result.returncode}")
                if result.stderr:
                    print(f"  Error: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print("  [WARNING] consolidate_docs.py timed out")
        except Exception as e:
            print(f"  [WARNING] Failed to run consolidate_docs.py: {e}")
    else:
        print("  [SKIP] scripts/consolidate_docs.py not found")

    # 6.2 Sync ARCHIVE_INDEX.md
    print("\n[6.2] Updating ARCHIVE_INDEX.md")

    # The consolidate_docs.py script should handle this, but verify
    archive_index = REPO_ROOT / "archive" / "reports" / "ARCHIVE_INDEX.md"
    if archive_index.exists():
        print(f"  [OK] ARCHIVE_INDEX.md exists (updated by consolidate_docs.py)")
    else:
        print(f"  [SKIP] ARCHIVE_INDEX.md not found (will be created on next run)")

    # 6.3 Note about auto-updated files
    print("\n[6.3] Auto-updated SOT files status")
    print("  The following files are auto-updated by Autopack during runs:")

    auto_updated_files = {
        "docs/project_ruleset_Autopack.json": "Updated when rules change",
        "docs/project_issue_backlog.json": "Updated by issue_tracker.py",
        "docs/autopack_phase_plan.json": "Updated when planning occurs",
    }

    for file_path, description in auto_updated_files.items():
        full_path = REPO_ROOT / file_path
        if full_path.exists():
            print(f"  [OK] {file_path} - {description}")
        else:
            print(f"  [MISSING] {file_path} - {description}")

    print(f"\n[PHASE 6] Complete")
    print("  Note: SOT files are now synchronized. They will auto-update on:")
    print("    - Autopack runs (project_ruleset, issue_backlog, phase_plan)")
    print("    - Manual tidy runs (CONSOLIDATED_*.md, ARCHIVE_INDEX.md)")
    print("    - Any workspace changes (run this script to re-sync)")


# ============================================================================
# VALIDATION (V2)
# ============================================================================

def validate_v2_structure() -> Tuple[bool, List[str]]:
    """Validate against PROPOSED_CLEANUP_STRUCTURE_V2.md."""
    print("\n" + "=" * 80)
    print("VALIDATION: V2 STRUCTURE CHECK")
    print("=" * 80)

    issues = []
    warnings = []

    # Check 1: No archive/src/
    if (REPO_ROOT / "archive" / "src").exists():
        issues.append("[X] archive/src/ still exists (violates no-redundancy principle)")
    else:
        print("[OK] No archive/src/ folder")

    # Check 2: Runs grouped by project
    runs_dir = REPO_ROOT / "archive" / "diagnostics" / "runs"
    if runs_dir.exists():
        expected_projects = ["Autopack", "file-organizer", "unknown"]
        loose_runs = [d for d in runs_dir.iterdir()
                     if d.is_dir() and d.name not in expected_projects
                     and not d.name.startswith(".")]
        if loose_runs:
            issues.append(f"[X] {len(loose_runs)} ungrouped runs in diagnostics/runs/")
            for run in loose_runs[:5]:
                print(f"    - {run.name}")
        else:
            print("[OK] All runs grouped by project")

    # Check 3: Checkpoints renamed
    if (REPO_ROOT / ".autonomous_runs" / "checkpoints").exists():
        issues.append("[X] checkpoints/ not renamed to tidy_checkpoints/")
    else:
        print("[OK] checkpoints/ renamed or doesn't exist")

    # Check 4: Truth source .md files moved to docs/
    truth_md_files = ["WORKSPACE_ORGANIZATION_SPEC.md", "WHATS_LEFT_TO_BUILD.md",
                      "WHATS_LEFT_TO_BUILD_MAINTENANCE.md"]
    loose_md = [f for f in truth_md_files if (REPO_ROOT / f).exists()]
    if loose_md:
        issues.append(f"[X] {len(loose_md)} truth source .md files still at root: {', '.join(loose_md)}")
    else:
        print("[OK] Truth source .md files moved to docs/")

    # Check 5: Ruleset .json files moved to docs/
    docs_dir = REPO_ROOT / "docs"
    ruleset_files = ["project_ruleset_Autopack.json", "project_issue_backlog.json",
                    "autopack_phase_plan.json"]

    # Check if still at root (bad)
    loose_rulesets = [f for f in ruleset_files if (REPO_ROOT / f).exists()]
    if loose_rulesets:
        issues.append(f"[X] {len(loose_rulesets)} ruleset files still at root: {', '.join(loose_rulesets)}")

    # Check if in docs/ (good)
    rulesets_in_docs = [f for f in ruleset_files if (docs_dir / f).exists()]
    if len(rulesets_in_docs) == len(ruleset_files):
        print("[OK] All ruleset files moved to docs/")
    elif not loose_rulesets:  # Not at root and not in docs/ = missing
        missing_rulesets = [f for f in ruleset_files if not (docs_dir / f).exists()]
        warnings.append(f"[!] Missing ruleset files: {', '.join(missing_rulesets)}")

    # Check 6: ALL truth source documentation in docs/
    required_truth_sources = {
        "SETUP_GUIDE.md": "Setup/installation instructions",
        "WORKSPACE_ORGANIZATION_SPEC.md": "Workspace organization spec",
        "WHATS_LEFT_TO_BUILD.md": "Roadmap",
        "WHATS_LEFT_TO_BUILD_MAINTENANCE.md": "Maintenance roadmap",
    }

    nice_to_have = {
        "DEPLOYMENT_GUIDE.md": "Deployment guide",
        "ARCHITECTURE.md": "System architecture",
        "API_REFERENCE.md": "API documentation",
        "CONTRIBUTING.md": "Contribution guidelines",
    }

    missing_required = [d for d in required_truth_sources if not (docs_dir / d).exists()]
    if missing_required:
        issues.append(f"[X] Missing required docs in docs/: {', '.join(missing_required)}")
    else:
        print("[OK] All required truth sources present in docs/")

    missing_nice = [d for d in nice_to_have if not (docs_dir / d).exists()]
    if missing_nice:
        warnings.append(f"[!] Nice-to-have docs missing: {', '.join(missing_nice)}")

    # Check 7: file-organizer docs have truth sources
    fo_docs = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs"
    if fo_docs.exists():
        fo_required = ["README.md"]
        fo_missing = [d for d in fo_required if not (fo_docs / d).exists()]
        if fo_missing:
            warnings.append(f"[!] file-organizer docs missing: {', '.join(fo_missing)}")
        else:
            print("[OK] file-organizer docs have truth sources")

    # Check 7: Diagnostic data renamed
    if (REPO_ROOT / "archive" / "diagnostics" / "autopack_data").exists():
        warnings.append("[!] autopack_data/ not renamed to data/")
    else:
        print("[OK] Diagnostic data folder correct")

    # Check 8: API specs moved
    if (REPO_ROOT / "openapi.json").exists():
        warnings.append("[!] openapi.json still at root (should be in docs/api/)")
    else:
        print("[OK] API specs moved to docs/api/")

    # Summary
    print("\n" + "=" * 80)
    if issues or warnings:
        if issues:
            print("VALIDATION: [X] ISSUES FOUND")
            for issue in issues:
                print(f"  {issue}")
        if warnings:
            print("\nWARNINGS:")
            for warning in warnings:
                print(f"  {warning}")
        return False, issues + warnings
    else:
        print("VALIDATION: [OK] ALL CHECKS PASSED")
        print("=" * 80)
        print("\n[PASS] Workspace matches PROPOSED_CLEANUP_STRUCTURE_V2.md")
        return True, []


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run corrective cleanup V2."""
    parser = argparse.ArgumentParser(
        description="Corrective cleanup V2 - implements PROPOSED_CLEANUP_STRUCTURE_V2.md"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Show what would be done without making changes (default)")
    parser.add_argument("--execute", action="store_true",
                       help="Actually execute the cleanup")
    parser.add_argument("--validate-only", action="store_true",
                       help="Only run validation, no cleanup")

    args = parser.parse_args()
    dry_run = not args.execute

    if args.validate_only:
        passed, issues = validate_v2_structure()
        return 0 if passed else 1

    if dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN MODE - No changes will be made")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("EXECUTING CLEANUP V2")
        print("=" * 80)

    # Execute phases
    phase1_root_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 1 - organize root directory files")

    phase2_archive_restructuring(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 2 - restructure archive")

    phase3_autonomous_runs_cleanup(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 3 - clean .autonomous_runs")

    phase4_restore_documentation(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 4 - restore truth source documentation")

    phase5_organize_cleanup_artifacts(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 5 - organize cleanup documentation and scripts")

    phase6_synchronize_sot_files(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 6 - synchronize source of truth files")

    # Final validation
    validation_passed, issues = validate_v2_structure()

    if dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN COMPLETE")
        print("=" * 80)
        print("\nTo execute: python scripts/corrective_cleanup_v2.py --execute")
    else:
        print("\n" + "=" * 80)
        print("CLEANUP V2 COMPLETE")
        print("=" * 80)
        if validation_passed:
            print("\n[PASS] Workspace now matches PROPOSED_CLEANUP_STRUCTURE_V2.md")
        else:
            print("\n[!] Some issues remain - review output above")

    return 0 if validation_passed else 1


if __name__ == "__main__":
    exit(main())
