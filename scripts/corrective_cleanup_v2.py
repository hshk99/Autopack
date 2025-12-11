#!/usr/bin/env python3
"""
Corrective Cleanup V2 - Implements PROPOSED_CLEANUP_STRUCTURE_V2.md

This script fixes the structural issues identified in WORKSPACE_ISSUES_ANALYSIS.md
and implements the corrected organization principles.

Integrates with Autopack's tidy system for reusability.
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
    """Move config files, API specs, and diagnostic data from root."""
    print("\n" + "=" * 80)
    print("PHASE 1: ROOT DIRECTORY CLEANUP")
    print("=" * 80)

    # 1.1 Move configuration files to config/
    config_files = [
        "project_ruleset_Autopack.json",
        "project_issue_backlog.json",
        "autopack_phase_plan.json"
    ]

    config_dir = REPO_ROOT / "config"
    moved_configs = 0

    print("\n[1.1] Moving configuration files to config/")
    for config_file in config_files:
        src = REPO_ROOT / config_file
        if src.exists():
            dest = config_dir / config_file
            print(f"  {config_file} -> config/")
            if not dry_run:
                safe_move(src, dest)
                moved_configs += 1

    # 1.2 Move API specifications to docs/api/
    api_specs = ["openapi.json"]
    api_dir = REPO_ROOT / "docs" / "api"
    moved_apis = 0

    print("\n[1.2] Moving API specifications to docs/api/")
    for api_file in api_specs:
        src = REPO_ROOT / api_file
        if src.exists():
            dest = api_dir / api_file
            print(f"  {api_file} -> docs/api/")
            if not dry_run:
                safe_move(src, dest)
                moved_apis += 1

    # 1.3 Move diagnostic data to archive/diagnostics/
    diag_files = [
        "test_run.json",
        "builder_fullfile_failure_latest.json"
    ]

    diag_dir = REPO_ROOT / "archive" / "diagnostics"
    moved_diags = 0

    print("\n[1.3] Moving diagnostic data to archive/diagnostics/")
    for diag_file in diag_files:
        src = REPO_ROOT / diag_file
        if src.exists():
            dest = diag_dir / diag_file
            print(f"  {diag_file} -> archive/diagnostics/")
            if not dry_run:
                safe_move(src, dest)
                moved_diags += 1

    # 1.4 Archive documentation files
    docs_to_archive = {
        "RUN_COMMAND.txt": "archive/docs/",
        "STRUCTURE_VERIFICATION_FINAL.md": "archive/reports/",
        "WORKSPACE_ISSUES_ANALYSIS.md": "archive/analysis/",
        "IMPLEMENTATION_PLAN_CLEANUP_V2.md": "archive/plans/",
        "PROPOSED_CLEANUP_STRUCTURE_V2.md": "archive/analysis/"
    }

    moved_docs = 0

    print("\n[1.4] Archiving documentation files")
    for doc_file, dest_folder in docs_to_archive.items():
        src = REPO_ROOT / doc_file
        if src.exists():
            dest = REPO_ROOT / dest_folder / doc_file
            print(f"  {doc_file} -> {dest_folder}")
            if not dry_run:
                safe_move(src, dest)
                moved_docs += 1

    print(f"\n[PHASE 1] Summary:")
    print(f"  - Moved {moved_configs} config files")
    print(f"  - Moved {moved_apis} API specs")
    print(f"  - Moved {moved_diags} diagnostic files")
    print(f"  - Archived {moved_docs} documentation files")


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

    # 2.3 Rename diagnostic data folder
    autopack_data = REPO_ROOT / "archive" / "diagnostics" / "autopack_data"
    data_folder = REPO_ROOT / "archive" / "diagnostics" / "data"

    print("\n[2.3] Renaming diagnostic data folder")
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

    # 3.2 Add truth sources to file-organizer-app-v1/docs/
    fileorg_docs = autonomous_root / "file-organizer-app-v1" / "docs"

    print("\n[3.2] Adding truth sources to file-organizer docs/")
    if fileorg_docs.exists():
        # Create README.md
        readme = fileorg_docs / "README.md"
        if not readme.exists():
            print(f"  Creating README.md")
            if not dry_run:
                readme.write_text("""# FileOrganizer - Documentation

This folder contains documentation for the FileOrganizer project.

## Contents

- [Architecture](ARCHITECTURE.md) - System architecture and design
- [Guides](guides/) - How-to guides and tutorials
- [Research](research/) - Research and analysis documents

## Quick Start

See guides/ for setup and usage instructions.

## Project Status

See [WHATS_LEFT_TO_BUILD.md](../WHATS_LEFT_TO_BUILD.md) for current roadmap.
""")

        # Create ARCHITECTURE.md (basic stub)
        arch = fileorg_docs / "ARCHITECTURE.md"
        if not arch.exists():
            print(f"  Creating ARCHITECTURE.md")
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

def phase4_documentation_creation(dry_run: bool = True) -> None:
    """Create active documentation in docs/."""
    print("\n" + "=" * 80)
    print("PHASE 4: DOCUMENTATION CREATION")
    print("=" * 80)

    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(exist_ok=True)

    docs_to_create = {
        "ARCHITECTURE.md": """# Autopack Architecture

## Overview

Autopack is an autonomous development system that uses AI to complete software development tasks.

## Core Components

### 1. Autonomous Executor
Orchestrates task execution with model selection and error handling.

### 2. Task Decomposition
Breaks down complex tasks into manageable phases.

### 3. Pack System
Reusable task templates for common development patterns.

### 4. Backlog Maintenance
Automatic issue tracking and prioritization.

## Data Flow

1. User provides task description
2. Task decomposer creates execution plan
3. Autonomous executor runs phases
4. Results captured and validated

## Directory Structure

See [WORKSPACE_ORGANIZATION_SPEC.md](../WORKSPACE_ORGANIZATION_SPEC.md)
""",
        "API_REFERENCE.md": """# Autopack API Reference

## OpenAPI Specification

See [openapi.json](api/openapi.json) for complete API specification.

## Key Endpoints

### Task Management
- `POST /tasks` - Create new task
- `GET /tasks/{id}` - Get task status
- `DELETE /tasks/{id}` - Cancel task

### Pack Management
- `GET /packs` - List available packs
- `POST /packs/{name}/execute` - Execute pack

### Execution
- `POST /execute` - Run autonomous execution
- `GET /runs/{id}` - Get run status

## Authentication

[To be documented]
""",
        "DEPLOYMENT_GUIDE.md": """# Autopack Deployment Guide

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ (for backlog persistence)
- Qdrant (optional, for semantic search)

## Installation

```bash
# Clone repository
git clone <repo-url>
cd Autopack

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\\Scripts\\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create `.env` file:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/autopack
QDRANT_HOST=http://localhost:6333
ANTHROPIC_API_KEY=your_key_here
```

## Running

```bash
# Start backend
uvicorn src.backend.main:app --reload

# Run autonomous executor
python -m autopack.autonomous_executor --task "your task"
```

## Docker Deployment

[To be documented]
""",
        "CONTRIBUTING.md": """# Contributing to Autopack

## Development Setup

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for initial setup.

## Code Style

- **Python:** Black formatter, 88 char line length
- **TypeScript:** Prettier, 2-space indents
- **Docstrings:** Google style

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_autonomous_executor.py

# With coverage
pytest --cov=src tests/
```

## Pull Requests

1. Create feature branch from `main`
2. Make changes with clear commit messages
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit PR with description

## Commit Messages

Use conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code restructuring
- `test:` Test changes
"""
    }

    created = 0
    for filename, content in docs_to_create.items():
        filepath = docs_dir / filename
        if not filepath.exists():
            print(f"  Creating {filename}")
            if not dry_run:
                filepath.write_text(content)
                created += 1
        else:
            print(f"  [SKIP] {filename} already exists")

    print(f"\n[PHASE 4] Created {created} documentation files")


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

    # Check 4: Config files moved
    root_configs = ["project_ruleset_Autopack.json", "project_issue_backlog.json",
                   "autopack_phase_plan.json"]
    loose_configs = [f for f in root_configs if (REPO_ROOT / f).exists()]
    if loose_configs:
        issues.append(f"[X] {len(loose_configs)} config files still at root: {', '.join(loose_configs)}")
    else:
        print("[OK] Config files moved to config/")

    # Check 5: Active docs exist
    docs_dir = REPO_ROOT / "docs"
    required_docs = ["ARCHITECTURE.md", "API_REFERENCE.md", "DEPLOYMENT_GUIDE.md", "CONTRIBUTING.md"]
    missing_docs = [d for d in required_docs if not (docs_dir / d).exists()]
    if missing_docs:
        warnings.append(f"[!] Missing docs: {', '.join(missing_docs)}")
    else:
        print("[OK] Active documentation present in docs/")

    # Check 6: file-organizer docs have truth sources
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

    phase4_documentation_creation(dry_run)
    if not dry_run:
        git_checkpoint("cleanup-v2: phase 4 - create documentation")

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
