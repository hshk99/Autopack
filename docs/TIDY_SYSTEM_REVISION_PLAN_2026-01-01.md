# Tidy System Revision Plan - 2026-01-01

**Date**: 2026-01-01T23:50:00Z
**Context**: Pre-tidy gap analysis complete, BUILD-150 archive nesting fixed
**Purpose**: Revise Autopack tidy system to address all identified gaps automatically
**Approach**: Make tidy system self-sufficient to handle all cleanup scenarios

---

## Executive Summary

Instead of manually fixing workspace issues, we'll enhance the tidy system to automatically handle:
1. Database file archival (24 historical `.db` files)
2. Misplaced directory routing (10 directories including `fileorganizer/`)
3. `.autonomous_runs/` cleanup (orphaned logs, historical runs)
4. Project structure repair (`file-organizer-app-v1` SOT setup)
5. Prevention mechanisms (logging config, allowlist fixes)

**Deliverables**:
- Updated `scripts/tidy/tidy_up.py` with enhanced routing logic
- Updated `scripts/tidy/verify_workspace_structure.py` with aligned validation
- New `scripts/tidy/database_organizer.py` for database-specific cleanup
- New `scripts/tidy/autonomous_runs_cleaner.py` for `.autonomous_runs/` hygiene
- Updated `docs/WORKSPACE_ORGANIZATION_SPEC.md` with clear policies
- Test run to validate all changes work correctly

---

## Phase 1: Fix Allowlists and Routing Rules

### 1.1 Database File Policy (CRITICAL)

**File**: `scripts/tidy/tidy_up.py`

**Current Problem**: Line 74 allows `"*.db"` pattern, preventing any database cleanup.

**Fix**:
```python
# Lines 58-71: ROOT_ALLOWED_FILES
ROOT_ALLOWED_FILES = {
    ".gitignore", ".dockerignore", ".eslintrc.cjs", ".env",
    "README.md", "LICENSE", "pyproject.toml", "package.json",
    "tsconfig.json", "docker-compose.yml", "Dockerfile",
    "requirements.txt", "poetry.lock", "package-lock.json", "yarn.lock",
    ".coverage", ".coverage.json",
    "docker-compose.dev.yml",
    "pytest.ini",
    "requirements-dev.txt",
    "Makefile",
    "nginx.conf",
    "index.html",
    "autopack.db",  # ← ADD: Primary development database (active)
}

# Lines 73-82: ROOT_ALLOWED_PATTERNS
ROOT_ALLOWED_PATTERNS = {
    # REMOVE: "*.db",  # ← DELETE THIS LINE (was too permissive)
    "Dockerfile*",
    "docker-compose*.yml",
    "requirements*.txt",
    "tsconfig*.json",
    "vite.config.*",
    "tidy_scope.yaml",
}
```

**Rationale**: This makes all `.db` files except `autopack.db` subject to routing rules, enabling automatic cleanup.

### 1.2 Enhanced Database Classifier

**File**: `scripts/tidy/tidy_up.py`

**Add new function** after `classify_root_file()` at ~line 360:

```python
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
        elif "fullrun" in name or "pilot" in name or any(c.isdigit() and name.endswith(f"v{c}.db") for c in "23456789"):
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
        # test.db with no other qualifier is likely orphaned - suggest deletion
        if name == "test.db":
            return "DELETE_ORPHANED"  # Special marker for dry-run review
        return "archive/data/databases/test_artifacts"

    # Unknown database - conservative routing
    return "archive/data/databases/misc"


def route_database_file(filepath: Path, repo_root: Path, dry_run: bool = True) -> Tuple[Optional[Path], str]:
    """
    Route a database file to appropriate archive location.

    Returns:
        (destination_path, action) where action is "MOVE", "DELETE", or "SKIP"
    """
    if filepath.name == "autopack.db":
        return (None, "SKIP")  # Active database, never route

    try:
        dest_subpath = classify_database_file(filepath)

        if dest_subpath == "DELETE_ORPHANED":
            return (None, "DELETE")

        dest = repo_root / dest_subpath / filepath.name
        return (dest, "MOVE")

    except Exception as e:
        print(f"[DB-ROUTE][ERROR] Failed to classify {filepath.name}: {e}")
        return (None, "SKIP")
```

### 1.3 Update `classify_root_file()` to Handle Databases

**File**: `scripts/tidy/tidy_up.py` at line ~320

**Add** after line 323 (suffix checks):

```python
def classify_root_file(filepath: Path) -> str:
    """Classify where a root file should be routed."""
    name = filepath.name
    suffix = filepath.suffix.lower()

    # Database files - use specialized classifier
    if suffix == ".db":
        db_route = classify_database_file(filepath)
        if db_route == "DELETE_ORPHANED":
            return "DELETE_ORPHANED"
        return db_route  # Return full path like "archive/data/databases/telemetry_seeds"

    # Python scripts
    if suffix == ".py":
        # ... existing logic ...
```

---

## Phase 2: Directory Routing Rules

### 2.1 Add Directory Classifier

**File**: `scripts/tidy/tidy_up.py`

**Add new function** after database routing functions:

```python
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
        # Need to create SOT structure
        return ".autonomous_runs/file-organizer-app-v1/src"

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

    # config/ - Framework configuration (explicitly allow)
    if name == "config":
        # This is actually allowed, update ROOT_ALLOWED_DIRS if needed
        return None  # Keep at root

    # Default: unknown directory, move to archive for manual review
    return f"archive/misc/root_directories/{name}"


def route_root_directory(dirpath: Path, repo_root: Path, dry_run: bool = True) -> Tuple[Optional[Path], str, Optional[str]]:
    """
    Route a root directory to appropriate location.

    Returns:
        (destination_path, action, note)
        action: "MOVE", "SKIP", "SPECIAL"
        note: Additional information for special handling
    """
    dest_subpath = classify_root_directory(dirpath, repo_root)

    if dest_subpath is None:
        return (None, "SKIP", "Allowed at root")

    dest = repo_root / dest_subpath

    # Special handling for fileorganizer -> file-organizer-app-v1
    if dirpath.name == "fileorganizer":
        return (dest, "SPECIAL", "Requires SOT structure creation")

    return (dest, "MOVE", None)
```

### 2.2 Add `config/` to Allowed Dirs (if not already)

**File**: `scripts/tidy/tidy_up.py` line 84-89

**Verify** `config` is in `ROOT_ALLOWED_DIRS`:

```python
ROOT_ALLOWED_DIRS = {
    ".git", ".github", ".pytest_cache", ".autopack", ".claude",
    ".autonomous_runs", "__pycache__", "node_modules",
    "src", "tests", "scripts", "docs", "archive", "backend", "frontend",
    "config",  # ← ADD if missing: Framework YAML configuration files
    "venv", ".venv", "dist", "build",
}
```

---

## Phase 3: `.autonomous_runs/` Cleanup Logic

### 3.1 Create Dedicated Cleaner Module

**New File**: `scripts/tidy/autonomous_runs_cleaner.py`

```python
#!/usr/bin/env python3
"""
.autonomous_runs/ Directory Cleaner

Handles cleanup of .autonomous_runs/ including:
- Orphaned log files
- Completed/historical run directories
- Stale runtime artifacts
- Baseline cache maintenance

Part of tidy system Phase 3.
"""

from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import json


# Directories that should always exist (runtime infrastructure)
RUNTIME_DIRS = {
    "_shared",      # Shared resources
    "autopack",     # Autopack maintenance workspace
    "baselines",    # Test baseline cache
    "checkpoints",  # Git checkpoint storage
}


def is_historical_run_directory(run_dir: Path, days_threshold: int = 7) -> bool:
    """
    Determine if a run directory is historical (completed and old).

    Criteria:
    - More than `days_threshold` days old (mtime)
    - No recent modifications
    - Contains completion markers (run_summary.json with DONE state)
    """
    if not run_dir.is_dir():
        return False

    # Check modification time
    mtime = datetime.fromtimestamp(run_dir.stat().st_mtime)
    age_days = (datetime.now() - mtime).days

    if age_days < days_threshold:
        return False  # Too recent

    # Check for completion marker
    run_summary = run_dir / "run_summary.json"
    if run_summary.exists():
        try:
            data = json.loads(run_summary.read_text(encoding='utf-8'))
            state = data.get("state", "")
            # If run is in DONE_* state and old, it's historical
            if state.startswith("DONE_"):
                return True
        except Exception:
            pass  # If can't parse, treat as potentially active

    # Check if contains only old logs
    log_files = list(run_dir.glob("*.log"))
    if log_files:
        newest_log = max(log_files, key=lambda f: f.stat().st_mtime)
        newest_log_age = (datetime.now() - datetime.fromtimestamp(newest_log.stat().st_mtime)).days
        if newest_log_age > days_threshold:
            return True

    return False


def find_orphaned_logs(autonomous_runs_dir: Path) -> List[Path]:
    """Find orphaned .log files at .autonomous_runs/ root."""
    orphaned = []

    for item in autonomous_runs_dir.iterdir():
        if item.is_file() and item.suffix == ".log":
            orphaned.append(item)

    return orphaned


def find_orphaned_files(autonomous_runs_dir: Path) -> List[Path]:
    """Find orphaned files (non-logs) at .autonomous_runs/ root."""
    orphaned = []

    for item in autonomous_runs_dir.iterdir():
        if item.is_file() and item.name not in {"baseline.json"}:  # baseline.json might be legacy
            # Exclude runtime files
            if item.suffix not in {".log"}:  # .log handled separately
                orphaned.append(item)
        elif item.is_file() and item.name == "baseline.json":
            # Legacy baseline file, should be in baselines/ directory
            orphaned.append(item)

    return orphaned


def find_historical_runs(autonomous_runs_dir: Path, days_threshold: int = 7) -> List[Path]:
    """Find completed/historical run directories."""
    historical = []

    for item in autonomous_runs_dir.iterdir():
        if not item.is_dir():
            continue

        # Skip runtime infrastructure
        if item.name in RUNTIME_DIRS:
            continue

        # Skip active project workspaces (heuristic: has docs/ with SOT files)
        docs_dir = item / "docs"
        if docs_dir.exists() and (docs_dir / "BUILD_HISTORY.md").exists():
            continue  # Likely an active project workspace

        # Check if historical run
        if is_historical_run_directory(item, days_threshold):
            historical.append(item)

    return historical


def cleanup_autonomous_runs(
    repo_root: Path,
    dry_run: bool = True,
    days_threshold: int = 7,
    verbose: bool = False
) -> Tuple[List[str], int]:
    """
    Clean up .autonomous_runs/ directory.

    Returns:
        (actions_taken, files_affected)
    """
    autonomous_runs = repo_root / ".autonomous_runs"
    if not autonomous_runs.exists():
        return ([], 0)

    actions = []
    files_affected = 0
    archive_logs = repo_root / "archive" / "diagnostics" / "logs" / "autopack"
    archive_runs = repo_root / "archive" / "autonomous_runs"

    # 1. Find orphaned logs
    orphaned_logs = find_orphaned_logs(autonomous_runs)
    if orphaned_logs:
        actions.append(f"[ORPHANED-LOGS] Found {len(orphaned_logs)} orphaned .log files")
        for log_file in orphaned_logs:
            dest = archive_logs / log_file.name
            files_affected += 1
            if verbose:
                actions.append(f"  MOVE {log_file.name} → {dest.relative_to(repo_root)}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                log_file.rename(dest)

    # 2. Find orphaned files
    orphaned_files = find_orphaned_files(autonomous_runs)
    if orphaned_files:
        actions.append(f"[ORPHANED-FILES] Found {len(orphaned_files)} orphaned files")
        for orphan in orphaned_files:
            # Route based on type
            if orphan.name == "baseline.json":
                dest = autonomous_runs / "baselines" / "legacy_baseline.json"
            else:
                dest = archive_runs / "orphaned" / orphan.name

            files_affected += 1
            if verbose:
                actions.append(f"  MOVE {orphan.name} → {dest.relative_to(repo_root)}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                orphan.rename(dest)

    # 3. Find historical run directories
    historical_runs = find_historical_runs(autonomous_runs, days_threshold)
    if historical_runs:
        actions.append(f"[HISTORICAL-RUNS] Found {len(historical_runs)} historical run directories (>{days_threshold} days old)")
        for run_dir in historical_runs:
            dest = archive_runs / run_dir.name
            files_affected += sum(1 for _ in run_dir.rglob("*") if _.is_file())
            if verbose:
                actions.append(f"  MOVE {run_dir.name}/ → {dest.relative_to(repo_root)}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                run_dir.rename(dest)

    return (actions, files_affected)


if __name__ == "__main__":
    import sys
    repo = Path(__file__).resolve().parent.parent.parent

    dry_run = "--execute" not in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    mode = "[DRY-RUN]" if dry_run else "[EXECUTE]"
    print(f"\n{mode} .autonomous_runs/ Cleanup\n")

    actions, count = cleanup_autonomous_runs(repo, dry_run=dry_run, verbose=verbose)

    for action in actions:
        print(action)

    print(f"\nTotal files affected: {count}")
    if dry_run:
        print("\nRun with --execute to apply changes")
```

---

## Phase 4: Project Structure Repair (fileorganizer → file-organizer-app-v1)

### 4.1 Add Project Migration Logic

**File**: `scripts/tidy/tidy_up.py`

**Add new function** after repair functions (~line 290):

```python
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
    else:
        print(f"  [DRY-RUN] Would create {project_src.parent}")
        print(f"  [DRY-RUN] Would create {project_docs}")
        print(f"  [DRY-RUN] Would create {project_archive}")

    # Move fileorganizer/ to src/fileorganizer/
    if not dry_run:
        if project_src.exists():
            print(f"  [WARNING] Destination {project_src} already exists, skipping move")
        else:
            fileorg_root.rename(project_src)
            print(f"  MOVED fileorganizer/ → {project_src.relative_to(repo_root)}")
    else:
        print(f"  [DRY-RUN] Would move fileorganizer/ → {project_src.relative_to(repo_root)}")

    changed = True

    # Create SOT files using existing repair logic
    changed |= repair_project_structure(
        repo_root,
        "file-organizer-app-v1",
        dry_run=dry_run,
        verbose=verbose
    )

    return changed
```

### 4.2 Integrate Migration into Main Tidy Flow

**File**: `scripts/tidy/tidy_up.py`

**Update `main()` function** to call migration before root routing:

```python
def main():
    # ... argparse setup ...

    print(f"\n{'='*80}")
    print(f"Autopack Tidy Up - Unified Workspace Organization")
    print(f"Mode: {'DRY-RUN (preview only)' if args.dry_run else 'EXECUTE (will modify files)'}")
    print(f"{'='*80}\n")

    # Phase 0: Special migrations (fileorganizer → file-organizer-app-v1)
    print("[PHASE 0] Special Project Migrations")
    print("-" * 80)
    migrate_fileorganizer_to_project(REPO_ROOT, dry_run=args.dry_run, verbose=args.verbose)
    print()

    # Phase 1: Root routing
    print("[PHASE 1] Root Directory Cleanup")
    # ... existing root routing logic ...
```

---

## Phase 5: Verifier Alignment

### 5.1 Update Verifier to Skip `autopack` SOT Validation

**File**: `scripts/tidy/verify_workspace_structure.py`

**Find project validation section** and add skip logic:

```python
def verify_project_structure(project_path: Path) -> List[str]:
    """Verify a project has required 6-file SOT structure."""
    warnings = []
    project_id = project_path.name

    # Skip SOT validation for runtime workspaces
    if project_id == "autopack":
        # .autonomous_runs/autopack is a runtime workspace, not a project SOT root
        return []  # No warnings

    docs_dir = project_path / "docs"
    if not docs_dir.exists():
        warnings.append(f"Project {project_id} missing docs/ directory")
        return warnings

    # ... rest of existing validation ...
```

### 5.2 Add Database-Specific Validation

**File**: `scripts/tidy/verify_workspace_structure.py`

**Add new validation function**:

```python
def verify_root_databases(repo_root: Path) -> List[str]:
    """Verify only autopack.db exists at root."""
    violations = []

    for item in repo_root.iterdir():
        if item.is_file() and item.suffix == ".db":
            if item.name != "autopack.db":
                violations.append(f"Unexpected database at root: {item.name} (should be archived)")

    return violations
```

**Integrate into main verification**:

```python
def main():
    # ... existing checks ...

    # Check for database violations
    db_violations = verify_root_databases(repo_root)
    if db_violations:
        print(f"\n[DATABASE VIOLATIONS] {len(db_violations)} issues:")
        for violation in db_violations:
            print(f"  ⚠️  {violation}")
        all_clean = False
```

---

## Phase 6: Update Workspace Organization Spec

### 6.1 Document New Policies

**File**: `docs/WORKSPACE_ORGANIZATION_SPEC.md`

**Add section** on database policy:

```markdown
## Database File Policy

### Allowed at Root
- `autopack.db` - Primary development database (active, frequently modified)

### Must Be Archived
All other `.db` files must reside in `archive/data/databases/` with categorization:

- `archive/data/databases/telemetry_seeds/` - Telemetry collection seed databases
  - `telemetry_seeds/debug/` - Debug/experimental seeds
  - `telemetry_seeds/final/` - Production-ready seeds
- `archive/data/databases/legacy/` - Superseded database versions (e.g., `autopack_legacy.db`)
- `archive/data/databases/backups/` - Database backups
- `archive/data/databases/debug_snapshots/` - Debug/mismatch snapshots
- `archive/data/databases/test_artifacts/` - Test databases
- `archive/data/databases/misc/` - Uncategorized historical databases

### Rationale
Database proliferation at root creates clutter and makes it difficult to identify the active development database. Historical and test databases belong in archive with clear categorization for future reference.
```

**Add section** on `config/` directory:

```markdown
## Framework Configuration Directory

### `config/` at Repository Root

The `config/` directory is **explicitly allowed** at repository root and contains framework-wide YAML configuration files:

- `models.yaml` - Model intelligence catalog
- `pricing.yaml` - API pricing configuration
- `diagnostics.yaml` - Diagnostics system configuration
- `memory.yaml` - Memory service configuration
- `project_types.yaml` - Project type definitions
- `stack_profiles.yaml` - Technology stack profiles
- `storage_policy.yaml` - Storage optimizer policies
- `tidy_scope.yaml` - Tidy system scope configuration
- `tools.yaml` - Tool definitions
- `feature_catalog.yaml` - Feature catalog
- `templates/` - Configuration templates

### Rationale
These configuration files are used by multiple framework components and belong at repository root for:
1. Easy discoverability
2. Centralized configuration management
3. Separation from source code (`src/`) and documentation (`docs/`)
```

**Update section** on `.autonomous_runs/autopack`:

```markdown
## `.autonomous_runs/autopack` - Runtime Workspace Semantics

**Type**: Runtime workspace (NOT a project SOT root)

**Purpose**:
- Workspace for Autopack self-maintenance runs
- Runtime artifact storage (diagnostics, logs, intermediate files)
- Does NOT require 6-file SOT structure

**Validation**:
- Tidy and verifier skip SOT validation for this directory
- Expected subdirectories: runtime-specific (diagnostics/, phases/, etc.)
- Should NOT be treated as a user project workspace

**Rationale**:
`.autonomous_runs/autopack` serves a different purpose than project workspaces like `.autonomous_runs/file-organizer-app-v1/`. Requiring full SOT structure creates unnecessary overhead for internal runtime operations.
```

---

## Phase 7: Integration and Testing Plan

### 7.1 Integration Checklist

**Updated Files**:
- [ ] `scripts/tidy/tidy_up.py` - Database/directory routing, fileorganizer migration
- [ ] `scripts/tidy/autonomous_runs_cleaner.py` - NEW: .autonomous_runs/ hygiene
- [ ] `scripts/tidy/verify_workspace_structure.py` - Autopack workspace skip, database validation
- [ ] `docs/WORKSPACE_ORGANIZATION_SPEC.md` - Updated policies

**New Archive Directories** (auto-created):
```
archive/data/databases/
├── telemetry_seeds/
│   ├── debug/
│   └── final/
├── legacy/
├── backups/
├── debug_snapshots/
├── test_artifacts/
└── misc/

archive/autonomous_runs/
└── orphaned/

archive/experiments/
├── research_code/
├── research_tracer/
└── tracer_bullet/
```

### 7.2 Testing Strategy

**Step 1: Dry-Run Preview**
```bash
# Preview all changes
python scripts/tidy/tidy_up.py --verbose

# Preview .autonomous_runs/ cleanup separately
python scripts/tidy/autonomous_runs_cleaner.py --verbose
```

**Expected Output**:
- 24 database files → archive/data/databases/* (various categories)
- `fileorganizer/` → `.autonomous_runs/file-organizer-app-v1/src/fileorganizer/`
- SOT files created in `.autonomous_runs/file-organizer-app-v1/docs/`
- `backend/` → `tests/backend/` or `scripts/backend/`
- `code/` → `archive/experiments/research_code/`
- `logs/` → `archive/diagnostics/logs/autopack/`
- `migrations/` → `scripts/migrations/`
- `reports/` → `archive/reports/`
- `research_tracer/` → `archive/experiments/research_tracer/`
- `tracer_bullet/` → `archive/experiments/tracer_bullet/`
- `examples/` → `docs/examples/` or `.autonomous_runs/examples/`
- Orphaned logs in `.autonomous_runs/` → `archive/diagnostics/logs/autopack/`
- Historical run directories → `archive/autonomous_runs/`

**Step 2: Create Checkpoint**
```bash
git checkout -b tidy-revision-2026-01-01
git add -A
git commit -m "checkpoint: before tidy revision run"
```

**Step 3: Execute Tidy**
```bash
# Run main tidy
python scripts/tidy/tidy_up.py --execute --verbose

# Run .autonomous_runs/ cleanup
python scripts/tidy/autonomous_runs_cleaner.py --execute --verbose
```

**Step 4: Verify Results**
```bash
# Run verifier
python scripts/tidy/verify_workspace_structure.py

# Check root directory
ls -la c:/dev/Autopack/ | grep -E "\\.db|backend|code|fileorganizer|logs|migrations|reports|research|tracer|examples"

# Check .autonomous_runs/
ls c:/dev/Autopack/.autonomous_runs/ | grep -E "\\.log|build.*\\.log"

# Check file-organizer-app-v1 structure
ls -la c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1/
ls -la c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1/docs/

# Count databases at root (should be 1: autopack.db)
ls c:/dev/Autopack/*.db | wc -l
```

**Step 5: Review and Commit**
```bash
# Review changes
git status
git diff --stat

# Commit if clean
git add -A
git commit -m "chore: Tidy revision - database archival, project migration, directory cleanup

- Archived 24 historical .db files to archive/data/databases/
- Migrated fileorganizer/ → .autonomous_runs/file-organizer-app-v1/ with SOT structure
- Moved 10 misplaced root directories to appropriate locations
- Cleaned up .autonomous_runs/ orphaned logs and historical runs
- Updated allowlists and routing rules for future prevention
- Aligned verifier with runtime workspace semantics

Refs: PRE_TIDY_GAP_ANALYSIS_2026-01-01.md, TIDY_SYSTEM_REVISION_PLAN_2026-01-01.md"
```

### 7.3 Validation Criteria

**Success Metrics**:
- ✅ Root directory contains exactly 1 `.db` file (`autopack.db`)
- ✅ No `backend/`, `code/`, `fileorganizer/`, `logs/`, `migrations/`, `reports/`, `research_tracer/`, `tracer_bullet/` at root
- ✅ `config/` still at root (explicitly allowed)
- ✅ `.autonomous_runs/file-organizer-app-v1/` exists with 6-file SOT structure
- ✅ `.autonomous_runs/` contains no orphaned `.log` files at root
- ✅ Verifier runs clean (no database violations, no false autopack SOT warnings)
- ✅ All archived files have clear categorization and location

**Failure Recovery**:
```bash
# If something goes wrong, revert to checkpoint
git reset --hard HEAD~1
# Or restore from checkpoint branch
git checkout main
git reset --hard tidy-revision-2026-01-01
```

---

## Phase 8: Post-Tidy Enhancements (Future)

These enhancements improve prevention but are NOT blockers for the initial tidy run:

### 8.1 Centralized Logging Config (Phase E.3)

**New File**: `src/autopack/logging_config.py`

```python
"""Centralized logging configuration for Autopack scripts and services."""

import logging
from pathlib import Path
from typing import Optional


def get_default_log_dir(repo_root: Optional[Path] = None) -> Path:
    """Get default log directory for Autopack."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent

    return repo_root / "archive" / "diagnostics" / "logs" / "autopack"


def configure_logging(
    log_name: str,
    repo_root: Optional[Path] = None,
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Configure logging for Autopack scripts.

    Args:
        log_name: Base name for log file (e.g., "tidy", "executor")
        repo_root: Repository root (auto-detected if None)
        log_dir: Custom log directory (uses default if None)
        level: Logging level

    Returns:
        Configured logger instance
    """
    if log_dir is None:
        log_dir = get_default_log_dir(repo_root)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{log_name}.log"

    logger = logging.getLogger(log_name)
    logger.setLevel(level)

    # File handler (UTF-8, append mode)
    fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    fh.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
```

**Usage in scripts**:
```python
from autopack.logging_config import configure_logging

logger = configure_logging("tidy")
logger.info("Starting tidy operation...")
```

### 8.2 CI Workspace Validation (Phase E.5)

**File**: `.github/workflows/ci.yml`

**Add job** (non-blocking initially):

```yaml
workspace-structure:
  name: Verify Workspace Structure
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Run workspace verifier
      run: |
        python scripts/tidy/verify_workspace_structure.py || echo "::warning::Workspace structure violations detected"
      continue-on-error: true  # Non-blocking initially
```

### 8.3 Pre-Commit Hook Template (Phase E.5)

**New File**: `scripts/git-hooks/pre-commit-workspace-check`

```bash
#!/bin/bash
# Pre-commit hook: Prevent root clutter
# Install: cp scripts/git-hooks/pre-commit-workspace-check .git/hooks/pre-commit

REPO_ROOT=$(git rev-parse --show-toplevel)

# Check for new .db files (except autopack.db)
NEW_DBS=$(git diff --cached --name-only --diff-filter=A | grep -E '^\w+\.db$' | grep -v '^autopack\.db$')

if [ -n "$NEW_DBS" ]; then
    echo "❌ Pre-commit check failed: New .db files detected at root"
    echo "   Only autopack.db is allowed at repository root."
    echo ""
    echo "   Found:"
    echo "$NEW_DBS" | sed 's/^/     /'
    echo ""
    echo "   Please move to archive/data/databases/ instead."
    exit 1
fi

# Check for new .log files at root
NEW_LOGS=$(git diff --cached --name-only --diff-filter=A | grep -E '^\w+\.log$')

if [ -n "$NEW_LOGS" ]; then
    echo "❌ Pre-commit check failed: New .log files detected at root"
    echo "   Log files should go to archive/diagnostics/logs/"
    echo ""
    echo "   Found:"
    echo "$NEW_LOGS" | sed 's/^/     /'
    exit 1
fi

exit 0
```

---

## Summary

This revision plan makes the tidy system fully autonomous in handling:

1. ✅ **Database cleanup** - 24 historical databases → categorized archive
2. ✅ **Directory routing** - 10 misplaced directories → proper locations
3. ✅ **Project migration** - `fileorganizer/` → `.autonomous_runs/file-organizer-app-v1/` with SOT
4. ✅ **`.autonomous_runs/` hygiene** - Orphaned logs and historical runs → archive
5. ✅ **Verifier alignment** - Skip autopack workspace, validate databases
6. ✅ **Spec documentation** - Clear policies for databases, config, runtime workspaces

**Next Steps**:
1. Implement code changes (Phases 1-5)
2. Run dry-run preview (Phase 7 Step 1)
3. Review output carefully
4. Execute with checkpoint (Phase 7 Steps 2-3)
5. Verify results (Phase 7 Step 4)
6. Commit if clean (Phase 7 Step 5)

**Post-Tidy** (optional):
- Implement Phase 8 enhancements (logging, CI, hooks)
- Enable prevention mechanisms
