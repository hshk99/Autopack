#!/usr/bin/env python3
"""
Unified Tidy Up - Complete Workspace Organization

This is the main entrypoint for "tidy up" that matches README expectations.
It orchestrates all phases of workspace organization:

1. Root routing - stray files in repo root -> archive/* or scripts/*
2. Docs hygiene - enforce docs/ is truth sources only, not an inbox
3. Archive consolidation - archive -> SOT ledgers; mark processed as superseded
4. .autonomous_runs cleanup - if enabled
5. Verification - assert structure matches WORKSPACE_ORGANIZATION_SPEC.md
6. SOT re-index handoff - mark SOT as dirty for executor to re-index

Usage:
    # Dry run (default) - preview what would be changed
    python scripts/tidy/tidy_up.py

    # Execute changes with checkpoints
    python scripts/tidy/tidy_up.py --execute

    # Reduce docs to SOT-only (aggressive cleanup)
    python scripts/tidy/tidy_up.py --execute --docs-reduce-to-sot

    # Scope to specific project
    python scripts/tidy/tidy_up.py --execute --project autopack

Category: MANUAL ONLY
Triggers: Explicit user command
Excludes: Automatic maintenance, test runs
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import hashlib
import difflib
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

# Ensure sibling imports work
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Import autonomous_runs cleaner and pending queue
from autonomous_runs_cleaner import cleanup_autonomous_runs
from pending_moves import PendingMovesQueue, retry_pending_moves, format_actionable_report_markdown
sys.path.insert(0, str(REPO_ROOT / "src"))

# ---------------------------------------------------------------------------
# Configuration from WORKSPACE_ORGANIZATION_SPEC.md
# ---------------------------------------------------------------------------

# Root allowed files (configuration, build artifacts, etc.)
ROOT_ALLOWED_FILES = {
    ".gitignore", ".dockerignore", ".eslintrc.cjs", ".env",
    "README.md", "LICENSE", "pyproject.toml", "package.json",
    "tsconfig.json", "docker-compose.yml", "Dockerfile",
    "requirements.txt", "poetry.lock", "package-lock.json", "yarn.lock",
    ".coverage", ".coverage.json",
    # Common repo-root config files used by this repo
    "docker-compose.dev.yml",
    "pytest.ini",
    "requirements-dev.txt",
    "Makefile",
    "nginx.conf",
    "index.html",
    # Database - only active development database allowed
    "autopack.db",  # Primary development database (active)
}

ROOT_ALLOWED_PATTERNS = {
    # NOTE: "*.db" pattern REMOVED - only autopack.db allowed (see ROOT_ALLOWED_FILES)
    # This enables automatic cleanup of historical/test databases
    "Dockerfile*",
    "docker-compose*.yml",
    "requirements*.txt",
    "tsconfig*.json",
    "vite.config.*",
    # Optional: allow a scoped tidy config file at root if used
    "tidy_scope.yaml",
}

ROOT_ALLOWED_DIRS = {
    ".git", ".github", ".pytest_cache", ".autopack", ".claude",
    ".autonomous_runs", "__pycache__", "node_modules",
    "src", "tests", "scripts", "docs", "archive", "backend", "frontend",
    "config", "venv", ".venv", "dist", "build",
}

# Docs SOT 6-file structure
DOCS_SOT_FILES = {
    "PROJECT_INDEX.json",
    "BUILD_HISTORY.md",
    "DEBUG_LOG.md",
    "ARCHITECTURE_DECISIONS.md",
    "FUTURE_PLAN.md",
    "LEARNED_RULES.json",
}

# Additional allowed files in docs/
DOCS_ALLOWED_FILES = {
    # Core documentation files
    "INDEX.md",
    "CHANGELOG.md",
    "WORKSPACE_ORGANIZATION_SPEC.md",
    "ARCHITECTURE.md",
    "QUICKSTART.md",
    "CONTRIBUTING.md",
    # Canonical guides (truth sources)
    "DEPLOYMENT.md",
    "GOVERNANCE.md",
    "TROUBLESHOOTING.md",
    "TESTING_GUIDE.md",
    "CONFIG_GUIDE.md",
    "AUTHENTICATION.md",
    "ERROR_HANDLING.md",
    "TELEMETRY_GUIDE.md",
    "TELEMETRY_COLLECTION_GUIDE.md",
    "TIDY_SYSTEM_USAGE.md",
    "PARALLEL_RUNS.md",
    "PHASE_LIFECYCLE.md",
    "MODEL_INTELLIGENCE_SYSTEM.md",
    # Additional specific files that are canonical
    "API_BASICS.md",
    "DOCKER_DEPLOYMENT_GUIDE.md",
    "phase_spec_schema.md",
    "stage2_structured_edits.md",
    "circuit_breaker_usage.md",
    "telemetry_utils_api.md",
}

DOCS_ALLOWED_PATTERNS = {
    "CURSOR_PROMPT_*.md",
    "IMPLEMENTATION_PLAN_*.md",
    "PRODUCTION_*.md",
    "SOT_*.md",
    "IMPROVEMENTS_*.md",
    "IMPLEMENTATION_SUMMARY_*.md",
    "RUNBOOK_*.md",
    "*_GUIDE.md",
    "CANONICAL_*.md",
    "*_SYSTEM.md",
    "TELEMETRY_*.md",  # Keep for backwards compat
}

# Allowed subdirectories in docs/
DOCS_ALLOWED_SUBDIRS = {
    "guides", "cli", "cursor", "examples", "api", "autopack", "research", "reports"
}

# Archive required buckets
ARCHIVE_REQUIRED_BUCKETS = {
    "plans", "reports", "research", "prompts", "diagnostics", "scripts",
    "superseded", "unsorted"
}

# ---------------------------------------------------------------------------
# Repair helpers (safe, minimal) - create missing SOT files + buckets
# ---------------------------------------------------------------------------

def _write_file_if_missing(path: Path, content: str, dry_run: bool, verbose: bool = False) -> bool:
    """
    Create a file with the provided content if it doesn't exist.
    Returns True if a change would be made (or was made).
    """
    if path.exists():
        return False
    if dry_run:
        print(f"[REPAIR][DRY-RUN] Would create file: {path}")
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if verbose:
        print(f"[REPAIR] Created file: {path}")
    return True


def _ensure_dirs_exist(paths: List[Path], dry_run: bool, verbose: bool = False) -> bool:
    """
    Ensure directories exist.
    Returns True if any change would be made (or was made).
    """
    changed = False
    for p in paths:
        if p.exists():
            continue
        changed = True
        if dry_run:
            print(f"[REPAIR][DRY-RUN] Would create directory: {p}/")
        else:
            p.mkdir(parents=True, exist_ok=True)
            if verbose:
                print(f"[REPAIR] Created directory: {p}/")
    return changed


def repair_project_workspace(
    repo_root: Path,
    project_id: str,
    dry_run: bool = True,
    verbose: bool = False,
) -> bool:
    """
    Repair a project workspace under .autonomous_runs/<project_id>/ by ensuring:
    - required SOT files exist under docs/
    - required archive buckets exist under archive/
    Returns True if any changes would be made (or were made).
    """
    project_root = repo_root / ".autonomous_runs" / project_id
    if not project_root.exists():
        print(f"[REPAIR][SKIP] Project does not exist: {project_root}")
        return False

    # Skip runtime workspace semantics (explicitly not a project SOT root)
    if project_id == "autopack":
        print("[REPAIR][SKIP] .autonomous_runs/autopack is a runtime workspace (not a project SOT root)")
        return False

    changed = False
    project_docs = project_root / "docs"
    project_archive = project_root / "archive"

    changed |= _ensure_dirs_exist([project_docs, project_archive], dry_run=dry_run, verbose=verbose)
    changed |= _ensure_dirs_exist(
        [project_archive / bucket for bucket in ARCHIVE_REQUIRED_BUCKETS],
        dry_run=dry_run,
        verbose=verbose,
    )

    # Minimal SOT templates (append-only ledgers; keep unopinionated)
    sot_templates = {
        "BUILD_HISTORY.md": (
            f"# {project_id} — BUILD_HISTORY\n\n"
            f"**Project**: {project_id}\n"
            f"**Purpose**: Append-only build/implementation ledger for this project’s SOT.\n\n"
            "---\n\n"
            "## Notes\n"
            "- Created by `tidy_up.py --repair` to satisfy the 6-file SOT structure.\n"
            "- Tidy may append summaries here during consolidation.\n"
        ),
        "DEBUG_LOG.md": (
            f"# {project_id} — DEBUG_LOG\n\n"
            f"**Project**: {project_id}\n"
            f"**Purpose**: Append-only troubleshooting ledger for this project’s SOT.\n\n"
            "---\n\n"
            "## Notes\n"
            "- Prefer entries with: Symptom → Root cause → Fix → Verification.\n"
        ),
        "ARCHITECTURE_DECISIONS.md": (
            f"# {project_id} — ARCHITECTURE_DECISIONS\n\n"
            f"**Project**: {project_id}\n"
            f"**Purpose**: Append-only architecture decision record (ADR-style) for this project’s SOT.\n\n"
            "---\n\n"
            "## Notes\n"
            "- Suggested entry format: Decision → Options → Rationale → Consequences.\n"
        ),
        "FUTURE_PLAN.md": (
            f"# {project_id} — FUTURE_PLAN\n\n"
            f"**Project**: {project_id}\n"
            f"**Purpose**: Roadmap/backlog for this project (manual, human-maintained).\n\n"
            "---\n\n"
            "## Backlog\n"
            "- (add items)\n"
        ),
        "PROJECT_INDEX.json": (
            json.dumps(
                {
                    "project_id": project_id,
                    "generated_by": "tidy_up.py --repair",
                    "notes": "Fill in with setup/structure/API quick reference for fast AI navigation.",
                },
                indent=2,
            )
            + "\n"
        ),
        "LEARNED_RULES.json": json.dumps({"rules": []}, indent=2) + "\n",
    }

    for fname in DOCS_SOT_FILES:
        path = project_docs / fname
        if fname in sot_templates:
            changed |= _write_file_if_missing(path, sot_templates[fname], dry_run=dry_run, verbose=verbose)
        else:
            # Fallback: create empty placeholder if something changes in DOCS_SOT_FILES set later
            changed |= _write_file_if_missing(path, "", dry_run=dry_run, verbose=verbose)

    return changed


def classify_root_directory(dirpath: Path, repo_root: Path) -> Optional[str]:
    """
    Classify where a root directory should be routed.

    Returns destination path relative to repo_root, or None to skip.
    """
    name = dirpath.name

    # Check if directory is in allowed list
    if name in ROOT_ALLOWED_DIRS:
        return None  # Already allowed, don't route

    # Special cases with content inspection

    # fileorganizer/ - This is the file-organizer-app-v1 project
    if name == "fileorganizer":
        # This should become a proper project under .autonomous_runs/
        # Handled by migrate_fileorganizer_to_project() separately
        return "MIGRATE_TO_PROJECT"

    # backend/ - Check contents
    if name == "backend":
        # If contains only test files, move to tests/backend
        # Otherwise move to scripts/backend
        py_files = list(dirpath.glob("*.py"))
        if py_files and all(f.name.startswith("test_") for f in py_files):
            return "tests/backend"
        return "scripts/backend"

    # code/ - Research/experimental code
    if name == "code":
        return "archive/experiments/research_code"

    # logs/ - Runtime logs
    if name == "logs":
        return "archive/diagnostics/logs/autopack"

    # migrations/ - Database migration scripts
    if name == "migrations":
        return "scripts/migrations"

    # reports/ - Build/analysis reports
    if name == "reports":
        return "archive/reports"

    # research_tracer/ - Research experiment
    if name == "research_tracer":
        return "archive/experiments/research_tracer"

    # tracer_bullet/ - Proof of concept
    if name == "tracer_bullet":
        return "archive/experiments/tracer_bullet"

    # examples/ - Example projects
    if name == "examples":
        # Could be docs/examples or .autonomous_runs/examples depending on contents
        # Check if contains runnable projects or just documentation
        has_src = (dirpath / "src").exists()
        has_package = (dirpath / "package.json").exists() or (dirpath / "pyproject.toml").exists()

        if has_src or has_package:
            return ".autonomous_runs/examples"
        return "docs/examples"

    # Default: unknown directory, move to archive for manual review
    return f"archive/misc/root_directories/{name}"


def migrate_fileorganizer_to_project(
    repo_root: Path,
    dry_run: bool = True,
    verbose: bool = False
) -> bool:
    """
    Migrate fileorganizer/ root directory to proper project structure.

    Creates .autonomous_runs/file-organizer-app-v1/ with:
    - src/fileorganizer/ (moved from root fileorganizer/)
    - docs/ with 6-file SOT structure
    - archive/ with required buckets

    Returns True if migration needed/performed.
    """
    fileorg_root = repo_root / "fileorganizer"
    if not fileorg_root.exists():
        if verbose:
            print("[MIGRATE-FILEORG][SKIP] fileorganizer/ does not exist at root")
        return False

    project_root = repo_root / ".autonomous_runs" / "file-organizer-app-v1"
    project_src = project_root / "src" / "fileorganizer"
    project_docs = project_root / "docs"
    project_archive = project_root / "archive"

    print(f"[MIGRATE-FILEORG] Found fileorganizer/ at root → migrating to {project_root.relative_to(repo_root)}")

    changed = False

    # Create project structure
    if not dry_run:
        project_src.parent.mkdir(parents=True, exist_ok=True)
        project_docs.mkdir(parents=True, exist_ok=True)
        project_archive.mkdir(parents=True, exist_ok=True)
        print(f"  CREATED {project_src.parent.relative_to(repo_root)}/")
        print(f"  CREATED {project_docs.relative_to(repo_root)}/")
        print(f"  CREATED {project_archive.relative_to(repo_root)}/")
    else:
        print(f"  [DRY-RUN] Would create {project_src.parent.relative_to(repo_root)}/")
        print(f"  [DRY-RUN] Would create {project_docs.relative_to(repo_root)}/")
        print(f"  [DRY-RUN] Would create {project_archive.relative_to(repo_root)}/")

    # Move fileorganizer/ to src/fileorganizer/
    if not dry_run:
        if project_src.exists():
            print(f"  [WARNING] Destination {project_src.relative_to(repo_root)} already exists, skipping move")
        else:
            fileorg_root.rename(project_src)
            print(f"  MOVED fileorganizer/ → {project_src.relative_to(repo_root)}/")
    else:
        print(f"  [DRY-RUN] Would move fileorganizer/ → {project_src.relative_to(repo_root)}/")

    changed = True

    # Create SOT files using existing repair logic
    changed |= repair_project_workspace(
        repo_root,
        "file-organizer-app-v1",
        dry_run=dry_run,
        verbose=verbose
    )

    return changed


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def matches_pattern(filename: str, pattern: str) -> bool:
    """Check if filename matches a wildcard pattern."""
    # Use stdlib glob matching (safer and supports ?, [], etc.)
    return fnmatch.fnmatchcase(filename, pattern)


def is_root_file_allowed(filename: str) -> bool:
    """Check if a file is allowed at repo root."""
    if filename in ROOT_ALLOWED_FILES:
        return True
    for pattern in ROOT_ALLOWED_PATTERNS:
        if matches_pattern(filename, pattern):
            return True
    return False


def is_docs_file_allowed(filename: str) -> bool:
    """Check if a file is allowed in docs/."""
    if filename in DOCS_SOT_FILES or filename in DOCS_ALLOWED_FILES:
        return True
    for pattern in DOCS_ALLOWED_PATTERNS:
        if matches_pattern(filename, pattern):
            return True
    return False


def classify_database_file(filepath: Path) -> str:
    """
    Classify database files for intelligent routing.

    Returns destination path relative to archive/data/databases/
    """
    name = filepath.name.lower()

    # Active development database - should never be routed
    if name == "autopack.db":
        raise ValueError(f"Active database {filepath.name} should not be routed")

    # Telemetry seed databases
    if "telemetry_seed" in name:
        if "debug" in name:
            return "archive/data/databases/telemetry_seeds/debug"
        elif "final" in name or "green" in name:
            return "archive/data/databases/telemetry_seeds/final"
        elif "fullrun" in name or "pilot" in name or any(f"v{c}.db" in name for c in "23456789"):
            return "archive/data/databases/telemetry_seeds"
        else:
            return "archive/data/databases/telemetry_seeds"

    # Autopack legacy/backup databases
    if name.startswith("autopack_"):
        if "legacy" in name:
            return "archive/data/databases/legacy"
        elif "telemetry" in name:
            return "archive/data/databases/telemetry_seeds"
        else:
            return "archive/data/databases/backups"

    # Debug/mismatch snapshots
    if "mismatch" in name or "debug" in name:
        return "archive/data/databases/debug_snapshots"

    # Test databases
    if name.startswith("test"):
        # All test databases go to test_artifacts
        return "archive/data/databases/test_artifacts"

    # Unknown database - conservative routing
    return "archive/data/databases/misc"


def classify_root_file(filepath: Path) -> str:
    """Classify where a root file should be routed."""
    name = filepath.name
    suffix = filepath.suffix.lower()

    # Database files - use specialized classifier
    if suffix == ".db":
        return classify_database_file(filepath)

    # Python scripts
    if suffix == ".py":
        if name.startswith("test_"):
            return "scripts/test"
        elif any(kw in name.lower() for kw in ["backend", "api", "database", "fastapi"]):
            return "scripts/backend"
        elif any(kw in name.lower() for kw in ["frontend", "ui", "react", "component"]):
            return "scripts/frontend"
        elif any(kw in name.lower() for kw in ["temp", "tmp", "scratch", "probe"]):
            return "scripts/temp"
        else:
            return "scripts/utility"

    # Markdown files
    elif suffix == ".md":
        name_upper = name.upper()
        if any(kw in name_upper for kw in ["BUILD-", "BUILD_"]):
            return "archive/reports"
        elif any(kw in name_upper for kw in ["DBG-", "DEBUG_", "DIAGNOSTIC_"]):
            return "archive/diagnostics"
        elif any(kw in name_upper for kw in ["PLAN", "PHASE"]):
            return "archive/plans"
        elif any(kw in name_upper for kw in ["PROMPT_", "DELEGATION_"]):
            return "archive/prompts"
        elif any(kw in name_upper for kw in ["RESEARCH_", "ANALYSIS_", "INVESTIGATION_"]):
            return "archive/research"
        elif any(kw in name_upper for kw in ["REPORT_", "SUMMARY_", "CONSOLIDATED_"]):
            return "archive/reports"
        else:
            return "archive/unsorted"

    # Log files
    elif suffix == ".log":
        return "archive/diagnostics/logs"

    # JSON files
    elif suffix == ".json":
        if any(kw in name.lower() for kw in ["plan", "phase"]):
            return "archive/plans"
        elif any(kw in name.lower() for kw in ["error", "failure", "diagnostic"]):
            return "archive/diagnostics"
        else:
            return "archive/unsorted"

    # Shell scripts
    elif suffix in {".sh", ".bat", ".ps1"}:
        return "scripts/utility"

    # SQL files
    elif suffix == ".sql":
        return "scripts/utility"

    # Config files
    elif suffix in {".yaml", ".yml", ".toml"}:
        return "archive/plans"

    # Default
    else:
        return "archive/unsorted"


def classify_docs_file(filepath: Path) -> str:
    """Classify where a non-SOT docs file should be archived."""
    name = filepath.name
    name_upper = name.upper()

    if any(kw in name_upper for kw in ["BUILD-", "BUILD_"]):
        return "archive/reports"
    elif any(kw in name_upper for kw in ["DBG-", "DEBUG_", "DIAGNOSTIC_"]):
        return "archive/diagnostics"
    elif any(kw in name_upper for kw in ["PROMPT_", "DELEGATION_"]):
        return "archive/prompts"
    elif any(kw in name_upper for kw in ["REPORT_", "SUMMARY_", "ANALYSIS_"]):
        return "archive/reports"
    elif any(kw in name_upper for kw in ["PLAN"]):
        return "archive/plans"
    else:
        return "archive/unsorted"


def mark_sot_dirty(project_id: str, repo_root: Path, dry_run: bool = True) -> None:
    """
    Mark SOT index as dirty so executor knows to re-index.
    Phase 1.5: Design A (dirty-flag + fast no-op)
    """
    if project_id == "autopack":
        marker_path = repo_root / ".autonomous_runs" / "sot_index_dirty_autopack.json"
    else:
        marker_path = repo_root / ".autonomous_runs" / project_id / ".autonomous_runs" / "sot_index_dirty.json"

    marker_data = {
        "dirty": True,
        "timestamp": datetime.now().isoformat(),
        "reason": "tidy_up modified SOT files",
    }

    if not dry_run:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps(marker_data, indent=2), encoding="utf-8")
        print(f"[SOT-REINDEX] Marked {project_id} SOT as dirty: {marker_path}")
    else:
        print(f"[SOT-REINDEX] [DRY-RUN] Would mark {project_id} SOT as dirty: {marker_path}")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def generate_root_sot_duplicate_report(
    repo_root: Path,
    docs_dir: Path,
    output_path: Path,
    max_diff_lines: int = 200,
    dry_run: bool = True,
) -> bool:
    """
    Generate a report about root-level duplicates of SOT files (root vs docs/).
    Returns True if any divergent duplicates were found.
    """
    findings = []
    divergent = False

    for fname in sorted(DOCS_SOT_FILES):
        root_path = repo_root / fname
        docs_path = docs_dir / fname

        if not root_path.exists():
            continue

        entry: Dict[str, object] = {
            "file": fname,
            "root_path": str(root_path),
            "docs_path": str(docs_path),
            "status": "unknown",
        }

        if not docs_path.exists():
            entry["status"] = "docs_missing"
            divergent = True
            findings.append(entry)
            continue

        try:
            root_bytes = root_path.read_bytes()
            docs_bytes = docs_path.read_bytes()
        except Exception as e:
            entry["status"] = "read_error"
            entry["error"] = str(e)
            divergent = True
            findings.append(entry)
            continue

        entry["root_sha256"] = _sha256_bytes(root_bytes)
        entry["docs_sha256"] = _sha256_bytes(docs_bytes)
        entry["root_size_bytes"] = len(root_bytes)
        entry["docs_size_bytes"] = len(docs_bytes)

        if root_bytes == docs_bytes:
            entry["status"] = "identical"
            findings.append(entry)
            continue

        entry["status"] = "divergent"
        divergent = True

        # Provide a small, truncated unified diff for convenience.
        try:
            root_text = root_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            docs_text = docs_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            udiff = list(
                difflib.unified_diff(
                    root_text,
                    docs_text,
                    fromfile=f"root/{fname}",
                    tofile=f"docs/{fname}",
                    lineterm="",
                )
            )
            if len(udiff) > max_diff_lines:
                udiff = udiff[:max_diff_lines] + ["(diff truncated)"]
            entry["unified_diff"] = "\n".join(udiff)
        except Exception as e:
            entry["diff_error"] = str(e)

        findings.append(entry)

    report = {
        "timestamp": datetime.now().isoformat(),
        "repo_root": str(repo_root),
        "docs_dir": str(docs_dir),
        "divergent_found": divergent,
        "findings": findings,
        "next_steps": [
            "For each divergent file: merge unique content into docs/ version, then delete the root copy.",
            "Suggested commands:",
            "  - git diff --no-index BUILD_HISTORY.md docs/BUILD_HISTORY.md",
            "  - git diff --no-index DEBUG_LOG.md docs/DEBUG_LOG.md",
        ],
    }

    # Render markdown
    md_lines: List[str] = []
    md_lines.append("# Root SOT Duplicate Report")
    md_lines.append("")
    md_lines.append(f"**Timestamp**: {report['timestamp']}")
    md_lines.append(f"**Repo root**: `{repo_root}`")
    md_lines.append(f"**Docs dir**: `{docs_dir}`")
    md_lines.append(f"**Divergent duplicates found**: {'YES' if divergent else 'NO'}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    if not findings:
        md_lines.append("No root-level SOT duplicates found.")
    else:
        for f in findings:
            md_lines.append(f"## {f['file']}")
            md_lines.append("")
            md_lines.append(f"- **status**: {f.get('status')}")
            if "root_sha256" in f:
                md_lines.append(f"- **root_sha256**: `{f.get('root_sha256')}`")
                md_lines.append(f"- **docs_sha256**: `{f.get('docs_sha256')}`")
                md_lines.append(f"- **root_size_bytes**: `{f.get('root_size_bytes')}`")
                md_lines.append(f"- **docs_size_bytes**: `{f.get('docs_size_bytes')}`")
            if f.get("status") == "divergent":
                md_lines.append("")
                md_lines.append("Suggested merge commands:")
                md_lines.append(f"- `git diff --no-index {f['file']} docs/{f['file']}`")
                md_lines.append("")
                if f.get("unified_diff"):
                    md_lines.append("Truncated unified diff (root -> docs):")
                    md_lines.append("")
                    md_lines.append("```")
                    md_lines.append(str(f["unified_diff"]))
                    md_lines.append("```")
            md_lines.append("")

    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## Next steps")
    md_lines.extend([f"- {s}" for s in report["next_steps"]])  # type: ignore[arg-type]
    md_lines.append("")

    output_path = output_path.resolve()
    json_path = output_path.with_suffix(".json")
    md_path = output_path.with_suffix(".md")

    if dry_run:
        print(f"[SOT-DUPS][DRY-RUN] Would write report JSON: {json_path}")
        print(f"[SOT-DUPS][DRY-RUN] Would write report MD:   {md_path}")
        return divergent

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[SOT-DUPS] Wrote report JSON: {json_path}")
    print(f"[SOT-DUPS] Wrote report MD:   {md_path}")
    return divergent


# ---------------------------------------------------------------------------
# Phase 1: Root Routing
# ---------------------------------------------------------------------------

def route_root_files(repo_root: Path, dry_run: bool = True, verbose: bool = False) -> Tuple[List[Tuple[Path, Path]], List[Path]]:
    """
    Route stray files from repo root to appropriate locations.
    Returns (moves, blocked_files) where:
    - moves: list of (source, destination) tuples
    - blocked_files: list of SOT files that differ from docs/ and need manual resolution
    """
    print("\n=== Phase 1: Root Routing ===")
    moves = []
    blocked_files = []

    for item in repo_root.iterdir():
        # Skip allowed directories
        if item.is_dir() and item.name in ROOT_ALLOWED_DIRS:
            continue

        # Skip allowed files
        if item.is_file() and is_root_file_allowed(item.name):
            continue

        # Route files
        if item.is_file():
            # Safety: never auto-move canonical SOT filenames if they appear at repo root.
            # These indicate drift/duplication and may contain unique content vs docs/.
            if item.name in DOCS_SOT_FILES:
                docs_copy = repo_root / "docs" / item.name
                if not docs_copy.exists():
                    print(
                        f"[ROOT-ROUTE][BLOCK] Canonical SOT file exists at root but docs copy is missing: {item.name}. "
                        f"Manual resolution required."
                    )
                    continue
                try:
                    root_bytes = item.read_bytes()
                    docs_bytes = docs_copy.read_bytes()
                except Exception as e:
                    print(
                        f"[ROOT-ROUTE][BLOCK] Failed to compare root vs docs SOT file for {item.name}: {e}. "
                        f"Manual resolution required."
                    )
                    continue

                if root_bytes != docs_bytes:
                    print(
                        f"[ROOT-ROUTE][BLOCK] Canonical SOT file differs between root and docs/: {item.name}. "
                        f"Manual merge required before tidy can proceed safely."
                    )
                    blocked_files.append(item)
                    continue

                # If byte-identical, we can safely relocate the root duplicate into archive/superseded for auditability.
                bucket = "archive/superseded/root_sot_duplicates"
                dest = repo_root / bucket / item.name
                moves.append((item, dest))
                if verbose or dry_run:
                    print(f"[ROOT-ROUTE] {item.name} (duplicate, identical) -> {bucket}/")
                continue

            bucket = classify_root_file(item)
            dest = repo_root / bucket / item.name

            # Avoid duplicate nesting
            if dest.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = repo_root / bucket / f"{item.stem}_{timestamp}{item.suffix}"

            moves.append((item, dest))
            if verbose or dry_run:
                print(f"[ROOT-ROUTE] {item.name} -> {bucket}/")

        # Route directories
        elif item.is_dir() and item.name not in ROOT_ALLOWED_DIRS:
            destination = classify_root_directory(item, repo_root)

            # None means directory is allowed (skip)
            if destination is None:
                continue

            # Special migration case for fileorganizer
            if destination == "MIGRATE_TO_PROJECT":
                # This is handled in Phase 0 migration
                if verbose:
                    print(f"[ROOT-ROUTE] {item.name}/ -> (handled by Phase 0 migration)")
                continue

            # Standard routing
            dest = repo_root / destination
            dest.mkdir(parents=True, exist_ok=True)

            dest_final = dest / item.name

            # Avoid duplicate nesting
            if dest_final.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_final = dest / f"{item.name}_{timestamp}"

            moves.append((item, dest_final))
            if verbose or dry_run:
                print(f"[ROOT-ROUTE] {item.name}/ -> {destination}/")

    if not moves:
        print("[ROOT-ROUTE] No files to route from root")

    return moves, blocked_files


# ---------------------------------------------------------------------------
# Phase 2: Docs Hygiene
# ---------------------------------------------------------------------------

def check_docs_hygiene(
    docs_dir: Path,
    reduce_to_sot: bool = False,
    dry_run: bool = True,
    verbose: bool = False
) -> Tuple[List[Tuple[Path, Path]], List[str]]:
    """
    Check docs/ hygiene and optionally reduce to SOT-only.
    Returns (moves, violations).
    """
    print("\n=== Phase 2: Docs Hygiene ===")
    moves = []
    violations = []

    if not docs_dir.exists():
        print(f"[WARN] Docs directory does not exist: {docs_dir}")
        return moves, violations

    # Check SOT files presence
    missing_sot = []
    for sot_file in DOCS_SOT_FILES:
        if not (docs_dir / sot_file).exists():
            missing_sot.append(sot_file)

    if missing_sot:
        violations.append(f"Missing SOT files: {', '.join(missing_sot)}")

    # Check files in docs/
    for item in docs_dir.iterdir():
        if item.is_file():
            if not is_docs_file_allowed(item.name):
                if reduce_to_sot:
                    # Move to archive
                    bucket = classify_docs_file(item)
                    dest = docs_dir.parent / bucket / item.name

                    # Avoid duplicates
                    if dest.exists():
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        dest = dest.parent / f"{item.stem}_{timestamp}{item.suffix}"

                    moves.append((item, dest))
                    if verbose or dry_run:
                        print(f"[DOCS-REDUCE] {item.name} -> {bucket}/")
                else:
                    violations.append(f"Non-SOT file in docs/: {item.name}")

        elif item.is_dir():
            if item.name not in DOCS_ALLOWED_SUBDIRS:
                violations.append(f"Disallowed subdirectory in docs/: {item.name}/")

    if not moves and not violations:
        print("[DOCS-HYGIENE] docs/ is clean")
    elif violations and not reduce_to_sot:
        print(f"[DOCS-HYGIENE] Found {len(violations)} violations (use --docs-reduce-to-sot to fix)")

    return moves, violations


# ---------------------------------------------------------------------------
# Phase 3: Archive Consolidation
# ---------------------------------------------------------------------------

def consolidate_archive(
    repo_root: Path,
    roots: List[str],
    semantic_model: str,
    db_overrides: Dict[str, str],
    purge: bool,
    dry_run: bool = True,
    verbose: bool = False
) -> bool:
    """
    Run archive consolidation via tidy_workspace.py for each root.
    Returns True if successful.
    """
    print("\n=== Phase 3: Archive Consolidation ===")

    for root in roots:
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "tidy" / "tidy_workspace.py"),
            "--root", root,
            "--semantic",
            "--semantic-model", semantic_model,
            "--semantic-max-files", "200",
            "--prune",
            "--age-days", "30",
        ]

        if not dry_run:
            cmd.append("--apply-semantic")
            cmd.append("--execute")
        else:
            cmd.append("--dry-run")

        if verbose:
            cmd.append("--verbose")

        dsn = db_overrides.get(root)
        if dsn:
            cmd.extend(["--database-url", dsn])

        if purge:
            cmd.append("--purge")

        print(f"[ARCHIVE-CONSOLIDATE] Processing root: {root}")
        try:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[ERROR] Archive consolidation failed for {root}")
                print(result.stderr)
                return False
        except Exception as e:
            print(f"[ERROR] Failed to run archive consolidation for {root}: {e}")
            return False

    print("[ARCHIVE-CONSOLIDATE] Complete")
    return True


# ---------------------------------------------------------------------------
# Phase 4: Verification
# ---------------------------------------------------------------------------

def verify_structure(repo_root: Path, docs_dir: Path) -> Tuple[bool, List[str]]:
    """
    Verify workspace structure matches WORKSPACE_ORGANIZATION_SPEC.md.
    Returns (is_valid, errors).
    """
    print("\n=== Phase 4: Verification ===")
    errors = []

    # Check SOT files exist
    for sot_file in DOCS_SOT_FILES:
        if not (docs_dir / sot_file).exists():
            errors.append(f"Missing SOT file: docs/{sot_file}")

    # Check archive buckets exist
    archive_dir = repo_root / "archive"
    if archive_dir.exists():
        for bucket in ARCHIVE_REQUIRED_BUCKETS:
            bucket_path = archive_dir / bucket
            if not bucket_path.exists():
                # Create missing buckets
                bucket_path.mkdir(parents=True, exist_ok=True)
                print(f"[VERIFY] Created missing archive bucket: archive/{bucket}/")
    else:
        errors.append("Missing archive/ directory")

    # Check for disallowed root files
    # Load pending queue to check if disallowed files are already queued for retry
    pending_srcs: Set[str] = set()
    queue_path = repo_root / ".autonomous_runs" / "tidy_pending_moves.json"

    if queue_path.exists():
        try:
            queue_data = json.loads(queue_path.read_text(encoding="utf-8"))
            for item_data in queue_data.get("items", []):
                if item_data.get("status") in {"pending", "failed"}:
                    src = item_data.get("src")
                    if src:
                        # Normalize path separators for comparison
                        pending_srcs.add(src.replace("\\", "/"))
        except Exception:
            # If queue is malformed, proceed with normal verification
            pass

    for item in repo_root.iterdir():
        if item.is_file() and not is_root_file_allowed(item.name):
            # Check if this file is already queued for retry (first-run resilience)
            if item.name in pending_srcs or str(item.name).replace("\\", "/") in pending_srcs:
                # Queued files are warnings, not errors - they'll be retried on next run
                continue
            errors.append(f"Disallowed file at root: {item.name}")

    if errors:
        print(f"[VERIFY] Found {len(errors)} structural errors")
        for error in errors:
            print(f"  - {error}")
        return False, errors
    else:
        print("[VERIFY] Structure is valid")
        return True, []


# ---------------------------------------------------------------------------
# Main Orchestration
# ---------------------------------------------------------------------------

def execute_moves(
    moves: List[Tuple[Path, Path]],
    dry_run: bool = True,
    pending_queue: Optional[PendingMovesQueue] = None
) -> Tuple[int, int]:
    """
    Execute file moves, queueing locked files for retry.

    Args:
        moves: List of (src, dest) tuples
        dry_run: If True, only simulate moves
        pending_queue: Optional queue for recording failed moves

    Returns:
        Tuple of (succeeded_count, failed_count)
    """
    if not moves:
        return 0, 0

    succeeded = 0
    failed = 0
    failed_moves = []

    for src, dest in moves:
        if dry_run:
            print(f"[DRY-RUN] Would move: {src} -> {dest}")
            succeeded += 1
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                print(f"[MOVED] {src} -> {dest}")
                succeeded += 1
            except PermissionError as e:
                # Classify permission errors more precisely
                reason = "locked"
                if hasattr(e, 'winerror'):
                    # WinError 32 = file locked by another process
                    # WinError 5 = access denied (permissions)
                    if e.winerror == 5:
                        reason = "permission"
                elif hasattr(e, 'errno'):
                    # EACCES = permission denied
                    # EPERM = operation not permitted
                    import errno
                    if e.errno in (errno.EACCES, errno.EPERM):
                        reason = "permission"

                print(f"[SKIPPED] {src} ({reason})")
                failed += 1
                failed_moves.append((src, dest, e))

                # Queue for retry if queue is available
                if pending_queue:
                    try:
                        size = src.stat().st_size if src.exists() else None
                    except Exception:
                        size = None

                    pending_queue.enqueue(
                        src=src,
                        dest=dest,
                        action="move",
                        reason=reason,
                        error_info=e,
                        bytes_estimate=size,
                        tags=["tidy_move"]
                    )
            except FileExistsError as e:
                # Destination already exists (collision)
                print(f"[SKIPPED] {src} (destination exists: {dest})")
                failed += 1
                failed_moves.append((src, dest, e))

                if pending_queue:
                    try:
                        size = src.stat().st_size if src.exists() else None
                    except Exception:
                        size = None

                    pending_queue.enqueue(
                        src=src,
                        dest=dest,
                        action="move",
                        reason="dest_exists",
                        error_info=e,
                        bytes_estimate=size,
                        tags=["tidy_move"]
                    )
            except Exception as e:
                # Other errors (not permission-related)
                print(f"[ERROR] Failed to move {src}: {e}")
                failed += 1
                failed_moves.append((src, dest, e))

                # Queue for retry (might be transient)
                if pending_queue:
                    pending_queue.enqueue(
                        src=src,
                        dest=dest,
                        action="move",
                        reason="unknown",
                        error_info=e,
                        tags=["tidy_move"]
                    )

    if failed_moves and not dry_run:
        print(f"\n[WARNING] {len(failed_moves)} files could not be moved:")
        for src, dest, err in failed_moves:
            print(f"  {src} -> {dest}")
            print(f"    Error: {err}")

        if pending_queue:
            print(f"\n[QUEUE] Failed moves have been queued for retry on next tidy run")

    return succeeded, failed


def main():
    parser = argparse.ArgumentParser(
        description="Unified workspace tidy - matches README expectations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Execution mode
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run only (default)")
    parser.add_argument("--execute", action="store_true",
                        help="Execute moves/consolidation (overrides --dry-run)")
    parser.add_argument("--first-run", action="store_true",
                        help="First-run bootstrap mode (equivalent to --execute --repair --docs-reduce-to-sot)")

    # Scope
    parser.add_argument("--project", default="autopack",
                        help="Project scope (default: autopack)")
    parser.add_argument("--scope", nargs="+",
                        help="Additional roots to tidy (overrides tidy_scope.yaml)")

    # Docs hygiene
    parser.add_argument("--docs-reduce-to-sot", action="store_true",
                        help="Reduce docs/ to SOT-only (move non-SOT files to archive)")

    # Repair mode
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Repair missing required directories/files (SOT ledgers + archive buckets). Safe, dry-run by default.",
    )
    parser.add_argument(
        "--repair-only",
        action="store_true",
        help="Run repair step only, then exit (skips routing/consolidation/verification).",
    )
    parser.add_argument(
        "--repair-projects",
        nargs="*",
        help="Project IDs under .autonomous_runs/ to repair (default: all detected project dirs except runtime workspaces).",
    )
    parser.add_argument(
        "--report-root-sot-duplicates",
        action="store_true",
        help="Generate a report for root-level SOT duplicates (root vs docs/) to aid manual merge.",
    )
    parser.add_argument(
        "--report-root-sot-duplicates-only",
        action="store_true",
        help="Generate the root SOT duplicate report and exit (no routing/consolidation).",
    )
    parser.add_argument(
        "--report-root-sot-duplicates-out",
        type=Path,
        default=Path("archive/diagnostics/root_sot_duplicates_report"),
        help="Output path (without extension) for the root SOT duplicate report (default: archive/diagnostics/root_sot_duplicates_report).",
    )

    # Checkpoints
    parser.add_argument("--checkpoint", action="store_true", default=True,
                        help="Create checkpoint zip before changes (default: true)")
    parser.add_argument("--no-checkpoint", action="store_false", dest="checkpoint",
                        help="Skip checkpoint creation")
    parser.add_argument("--git-checkpoint", action="store_true",
                        help="Create git commits before/after changes")

    # Other options
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--profile", action="store_true",
                        help="Enable profiling with timing and memory usage per phase")
    parser.add_argument("--skip-archive-consolidation", action="store_true",
                        help="Skip Phase 3 (archive consolidation)")

    # Queue reporting
    parser.add_argument("--queue-report", action="store_true",
                        help="Generate actionable report for pending queue (top items + next actions)")
    parser.add_argument("--queue-report-top-n", type=int, default=10,
                        help="Number of top items to show in queue report (default: 10)")
    parser.add_argument("--queue-report-format", choices=["json", "markdown", "both"], default="both",
                        help="Output format for queue report (default: both)")
    parser.add_argument("--queue-report-output", type=Path,
                        default=Path("archive/diagnostics/queue_report"),
                        help="Output path (without extension) for queue report (default: archive/diagnostics/queue_report)")

    args = parser.parse_args()

    # Apply --first-run shortcuts
    if args.first_run:
        args.execute = True
        args.repair = True
        args.docs_reduce_to_sot = True
        print("[FIRST-RUN] Bootstrap mode enabled (execute + repair + docs-reduce-to-sot)")

    # Resolve execution mode
    dry_run = not args.execute

    # Resolve repo root and docs dir
    repo_root = REPO_ROOT
    if args.project == "autopack":
        docs_dir = repo_root / "docs"
    else:
        docs_dir = repo_root / ".autonomous_runs" / args.project / "docs"

    print("=" * 70)
    print("UNIFIED TIDY UP - Complete Workspace Organization")
    print("=" * 70)
    print(f"Project: {args.project}")
    print(f"Docs dir: {docs_dir}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Docs reduce to SOT: {args.docs_reduce_to_sot}")
    print(f"Repair: {args.repair}")
    print(f"Report root SOT duplicates: {args.report_root_sot_duplicates}")
    print("=" * 70)

    # Initialize pending moves queue
    queue_file = repo_root / ".autonomous_runs" / "tidy_pending_moves.json"
    pending_queue = PendingMovesQueue(
        queue_file=queue_file,
        workspace_root=repo_root,
        queue_id="autopack-root"
    )
    pending_queue.load()

    # Phase -1: Retry pending moves from previous runs
    print("\n" + "=" * 70)
    print("Phase -1: Retry Pending Moves from Previous Runs")
    print("=" * 70)

    retried, retry_succeeded, retry_failed = retry_pending_moves(
        queue=pending_queue,
        dry_run=dry_run,
        verbose=args.verbose
    )

    if retried > 0:
        print(f"[QUEUE-RETRY] Retried: {retried}, Succeeded: {retry_succeeded}, Failed: {retry_failed}")
        if retry_succeeded > 0:
            print(f"[QUEUE-RETRY] Successfully completed {retry_succeeded} previously locked moves")

        # Save updated queue
        if not dry_run:
            pending_queue.save()
    else:
        print("[QUEUE-RETRY] No pending moves to retry")
    print()

    # Optional report step (safe)
    if args.report_root_sot_duplicates:
        print("\n=== Report: Root SOT duplicates (root vs docs/) ===")
        output_base = repo_root / args.report_root_sot_duplicates_out
        generate_root_sot_duplicate_report(
            repo_root=repo_root,
            docs_dir=docs_dir,
            output_path=output_base,
            dry_run=dry_run,
        )
        if args.report_root_sot_duplicates_only:
            print("\n[SOT-DUPS] Done (report-only mode).")
            return 0

    # Optional repair step (safe)
    if args.repair:
        print("\n=== Repair: Ensure required SOT + archive structure ===")
        changed_any = False

        # Autopack root project: ensure archive buckets exist (docs SOT should already exist)
        changed_any |= _ensure_dirs_exist(
            [repo_root / "archive" / bucket for bucket in ARCHIVE_REQUIRED_BUCKETS],
            dry_run=dry_run,
            verbose=args.verbose,
        )

        # Project workspaces
        projects_root = repo_root / ".autonomous_runs"
        if projects_root.exists():
            if args.repair_projects is not None and len(args.repair_projects) > 0:
                project_ids = args.repair_projects
            else:
                # Conservative default: treat as "project" only if it already looks like one
                # (has docs/ or archive/). This avoids creating SOT skeletons for run/caches.
                known_projects = {"file-organizer-app-v1"}
                project_ids = []
                for p in projects_root.iterdir():
                    if not p.is_dir() or p.name.startswith(".") or p.name == "autopack":
                        continue
                    if p.name in known_projects or (p / "docs").exists() or (p / "archive").exists():
                        project_ids.append(p.name)
            for pid in project_ids:
                changed_any |= repair_project_workspace(repo_root, pid, dry_run=dry_run, verbose=args.verbose)

        if not changed_any:
            print("[REPAIR] No missing required structure detected")

        if args.repair_only:
            print("\n[REPAIR] Done (repair-only mode).")
            return 0

    # Load tidy scope
    scope_file = repo_root / "tidy_scope.yaml"
    if scope_file.exists() and not args.scope:
        try:
            import yaml  # type: ignore
        except ImportError:
            print("[WARN] tidy_scope.yaml exists but PyYAML is not installed; using default roots. Install with: pip install pyyaml")
            data = {}
        else:
            data = yaml.safe_load(scope_file.read_text(encoding="utf-8")) or {}

        roots = data.get("roots") or [".autonomous_runs/file-organizer-app-v1", ".autonomous_runs", "archive"]
        db_overrides = data.get("db_overrides") or {}
        purge = data.get("purge", False)
    else:
        roots = args.scope or [".autonomous_runs/file-organizer-app-v1", ".autonomous_runs", "archive"]
        db_overrides = {}
        purge = False

    # Resolve semantic model
    try:
        from autopack.model_registry import get_tool_model
        semantic_model = get_tool_model("tidy_semantic", default="glm-4.7") or "glm-4.7"
    except Exception:
        semantic_model = "glm-4.7"

    # Git checkpoint before
    if args.git_checkpoint and not dry_run:
        print("\n[GIT-CHECKPOINT] Creating pre-tidy commit...")
        subprocess.run(["git", "add", "-A"], cwd=repo_root)
        subprocess.run(
            ["git", "commit", "-m", f"chore: pre-tidy checkpoint ({datetime.now().isoformat()})"],
            cwd=repo_root
        )

    # Phase 0: Special migrations (fileorganizer → file-organizer-app-v1)
    print("\n" + "=" * 70)
    print("Phase 0: Special Project Migrations")
    print("=" * 70)
    migrate_fileorganizer_to_project(repo_root, dry_run=dry_run, verbose=args.verbose)

    # Phase 0.5: .autonomous_runs cleanup (run early so it can't be blocked by unrelated routing issues)
    # BUILD-154: Ensure first tidy execution always cleans .autonomous_runs even if later phases encounter errors/locks.
    print("\n" + "=" * 70)
    print("Phase 0.5: .autonomous_runs/ Cleanup (Early)")
    print("=" * 70)

    phase_start = time.perf_counter()
    try:
        cleanup_autonomous_runs(
            repo_root=repo_root,
            dry_run=dry_run,
            verbose=args.verbose,
            profile=args.profile,
            keep_last_n_runs=3,  # Keep only last 3 runs (archive older telemetry runs)
            min_age_days=0  # Allow cleanup based on "keep last N" policy only
        )
    except Exception as e:
        # Never crash tidy on autonomous_runs cleanup; it's best-effort and should not block SOT routing/consolidation.
        print(f"[WARN] .autonomous_runs cleanup failed (continuing): {e}")
    finally:
        if args.profile:
            elapsed = time.perf_counter() - phase_start
            print(f"[PROFILE] Phase 0.5 completed in {elapsed:.2f}s")

    # Phase 1: Root routing
    print("\n" + "=" * 70)
    print("Phase 1: Root Directory Cleanup")
    print("=" * 70)
    root_moves, blocked_sot_files = route_root_files(repo_root, dry_run, args.verbose)

    # Task B: Fail fast in execute mode if blocked SOT files exist
    if blocked_sot_files and not dry_run:
        print("\n" + "=" * 70)
        print("ERROR: Cannot proceed - divergent SOT files require manual resolution")
        print("=" * 70)
        print("\nThe following SOT files exist at both root and docs/ with different content:")
        for blocked_file in blocked_sot_files:
            print(f"  - {blocked_file.name}")
        print("\nTo resolve:")
        print("  1. Compare: diff {0} docs/{0}".format(blocked_sot_files[0].name if blocked_sot_files else "FILE"))
        print("  2. Merge unique content from root into docs/ version")
        print("  3. Delete root version")
        print("  4. Commit: git add -A && git commit -m 'fix: merge duplicate SOT files'")
        print("  5. Re-run: python scripts/tidy/tidy_up.py --execute")
        print("\nTidy execution ABORTED to prevent data loss.")
        print("=" * 70)
        return 1

    # Phase 2: Docs hygiene
    docs_moves, docs_violations = check_docs_hygiene(
        docs_dir, args.docs_reduce_to_sot, dry_run, args.verbose
    )

    # Execute moves from Phase 1 & 2
    all_moves = root_moves + docs_moves
    move_succeeded = 0
    move_failed = 0
    if all_moves:
        print(f"\n[SUMMARY] Total files to move: {len(all_moves)}")
        move_succeeded, move_failed = execute_moves(all_moves, dry_run, pending_queue)

    # Phase 2.5 retained for readability, but work is performed in Phase 0.5 (early) for lock resilience.
    print("\n" + "=" * 70)
    print("Phase 2.5: .autonomous_runs/ Cleanup (Already Performed Early)")
    print("=" * 70)

    # Phase 3: Archive consolidation
    # Task C: Capture SOT file hashes BEFORE consolidation
    sot_files_before = {}
    if not args.skip_archive_consolidation and not dry_run:
        for sot_file_name in DOCS_SOT_FILES:
            sot_path = docs_dir / sot_file_name
            if sot_path.exists():
                sot_files_before[sot_file_name] = sot_path.read_bytes()

    ran_archive_consolidation = False
    if not args.skip_archive_consolidation:
        ran_archive_consolidation = True
        success = consolidate_archive(
            repo_root, roots, semantic_model, db_overrides, purge, dry_run, args.verbose
        )
        if not success and not dry_run:
            print("[ERROR] Archive consolidation failed, aborting")
            return 1
    else:
        print("\n=== Phase 3: Archive Consolidation (SKIPPED) ===")

    # Phase 4: Verification
    is_valid, verify_errors = verify_structure(repo_root, docs_dir)

    # Phase 5: SOT re-index handoff (Phase 1.5)
    # If we performed any action that could change SOT content, mark it dirty so the executor can refresh indexing.
    if not dry_run:
        sot_modified_by_move = any(
            str(dest).startswith(str(docs_dir)) and dest.name in DOCS_SOT_FILES
            for _, dest in all_moves
        )

        # Task C: Check if archive consolidation actually changed SOT files
        sot_modified_by_consolidation = False
        if ran_archive_consolidation and sot_files_before:
            for sot_file_name in DOCS_SOT_FILES:
                sot_path = docs_dir / sot_file_name
                if sot_path.exists():
                    current_content = sot_path.read_bytes()
                    previous_content = sot_files_before.get(sot_file_name)
                    if previous_content != current_content:
                        sot_modified_by_consolidation = True
                        break
                elif sot_file_name in sot_files_before:
                    # File was deleted
                    sot_modified_by_consolidation = True
                    break

        # Only mark dirty if SOT actually changed
        if sot_modified_by_move or docs_moves or sot_modified_by_consolidation:
            mark_sot_dirty(args.project, repo_root, dry_run=False)

    # Git checkpoint after
    if args.git_checkpoint and not dry_run:
        print("\n[GIT-CHECKPOINT] Creating post-tidy commit...")
        subprocess.run(["git", "add", "-A"], cwd=repo_root)
        subprocess.run(
            ["git", "commit", "-m", f"chore: post-tidy checkpoint ({datetime.now().isoformat()})"],
            cwd=repo_root
        )

    # Final summary
    # Save queue and print summary
    if not dry_run:
        # Clean up old succeeded/abandoned items (30-day retention)
        # This prevents unbounded queue growth
        pending_queue.cleanup_old_items(max_age_days=30)

        # Clean up succeeded items from this run
        pending_queue.cleanup_succeeded()

        # Save final state
        pending_queue.save()

    # Print queue summary
    queue_summary = pending_queue.get_summary()
    if queue_summary["total"] > 0:
        print("\n" + "=" * 70)
        print("PENDING MOVES QUEUE SUMMARY")
        print("=" * 70)
        print(f"Total items in queue: {queue_summary['total']}")
        print(f"  Pending (awaiting retry): {queue_summary['pending']}")
        print(f"  Succeeded (this run): {queue_summary['succeeded']}")
        print(f"  Abandoned (max attempts): {queue_summary['abandoned']}")
        print(f"  Needs manual (escalated): {queue_summary.get('needs_manual', 0)}")
        print(f"  Eligible for next run: {queue_summary['eligible_now']}")
        print()
        print(f"Queue file: {queue_file}")
        print()

        if queue_summary.get("needs_manual", 0) > 0:
            print(f"[ACTION REQUIRED] {queue_summary['needs_manual']} items need manual resolution:")
            print("  - dest_exists: Destination file collision - requires manual decision")
            print("  - permission: Access denied - check file/folder permissions")
            print("  - See queue report for details")
            print()

        if queue_summary["pending"] > 0 and not dry_run:
            print("[INFO] Locked files will be retried automatically on next tidy run")
            print("[INFO] After reboot or closing locking processes, run:")
            print("       python scripts/tidy/tidy_up.py --execute")
            print()

    # Generate actionable queue report if requested or if there are pending items
    if (args.queue_report or queue_summary["pending"] > 0) and queue_summary["total"] > 0:
        print("\n" + "=" * 70)
        print("QUEUE ACTIONABLE REPORT")
        print("=" * 70)

        # Generate report
        actionable_report = pending_queue.get_actionable_report(top_n=args.queue_report_top_n)

        # Print summary to console
        print(f"Total pending: {actionable_report['summary']['total_pending']} items")
        print(f"Total size estimate: {actionable_report['summary']['total_bytes_estimate'] / 1024 / 1024:.2f} MB")
        print(f"Eligible now: {actionable_report['summary']['eligible_now']} items")
        print()

        if actionable_report["top_items"]:
            print(f"Top {len(actionable_report['top_items'])} items by priority:")
            for item in actionable_report["top_items"][:5]:  # Show top 5 in console
                print(f"  [{item['priority_score']}] {item['src']} ({item['attempt_count']} attempts, {item['age_days']} days old)")
            if len(actionable_report["top_items"]) > 5:
                print(f"  ... and {len(actionable_report['top_items']) - 5} more")
            print()

        if actionable_report["suggested_actions"]:
            print("Suggested next actions:")
            for action in actionable_report["suggested_actions"]:
                priority_marker = "[HIGH]" if action["priority"] == "high" else "[MED]"
                print(f"  {priority_marker} {action['description']}")
            print()

        # Save reports if requested
        if args.queue_report:
            output_base = repo_root / args.queue_report_output
            output_base.parent.mkdir(parents=True, exist_ok=True)

            if args.queue_report_format in ["json", "both"]:
                json_path = output_base.with_suffix(".json")
                json_path.write_text(json.dumps(actionable_report, indent=2), encoding="utf-8")
                print(f"[QUEUE-REPORT] JSON report written to: {json_path}")

            if args.queue_report_format in ["markdown", "both"]:
                md_path = output_base.with_suffix(".md")
                md_content = format_actionable_report_markdown(actionable_report)
                md_path.write_text(md_content, encoding="utf-8")
                print(f"[QUEUE-REPORT] Markdown report written to: {md_path}")

            print()

    print("\n" + "=" * 70)
    print("TIDY UP COMPLETE")
    print("=" * 70)
    print(f"Root files routed: {len(root_moves)}")
    print(f"Docs files moved: {len(docs_moves)}")
    print(f"Docs violations: {len(docs_violations)}")
    print(f"Structure valid: {is_valid}")

    if dry_run:
        print("\nDRY-RUN MODE - No changes were made")
        print("   Run with --execute to apply changes")
    else:
        print("\nChanges applied successfully")
        if move_failed > 0:
            print(f"Note: {move_failed} files were queued for retry due to locks")

    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
