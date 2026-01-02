"""BUILD-145: .autonomous_runs/ Cleanup Logic

Handles intelligent cleanup of .autonomous_runs/ directory:
- Orphaned executor.log files (not in run directories)
- Duplicate baseline archives
- Historical run directories (keep last N per project)
- Empty directories

Preserves:
- Active run directories (detected via file timestamps)
- Project SOT structures (.autonomous_runs/{project}/docs/)
- Runtime workspaces (.autonomous_runs/autopack)
"""

import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Tuple, Set
import logging

logger = logging.getLogger(__name__)


def is_runtime_workspace(dirpath: Path) -> bool:
    """
    Check if directory is a runtime workspace (e.g., .autonomous_runs/autopack).

    Runtime workspaces should not be cleaned up or treated as project SOT roots.

    Args:
        dirpath: Directory path to check

    Returns:
        True if directory is a runtime workspace
    """
    # Protected runtime workspace directories
    runtime_workspaces = {
        "autopack",              # Main runtime workspace
        "_shared",               # Shared runtime resources
        "baselines",             # Test baseline cache
        "batch_drain_sessions",  # Batch drain runtime workspace
        "checkpoints",           # Git checkpoint storage
        ".locks",                # Lock files
        "tidy_checkpoints",      # Tidy checkpoint storage
    }

    return dirpath.name in runtime_workspaces


def is_project_directory(dirpath: Path) -> bool:
    """
    Check if directory is a project SOT root.

    Project directories have docs/ or archive/ subdirectories.

    Args:
        dirpath: Directory path to check

    Returns:
        True if directory is a project
    """
    # Runtime workspaces are not project directories
    if is_runtime_workspace(dirpath):
        return False

    # Check for SOT markers
    has_docs = (dirpath / "docs").exists()
    has_archive = (dirpath / "archive").exists()

    return has_docs or has_archive


def is_run_directory(dirpath: Path) -> bool:
    """
    Check if directory is a run directory.

    Run directories typically have names like:
    - {run_id} (no timestamp)
    - {run_id}-{timestamp}
    - Contains run artifacts (rollback.log, executor.log, etc.)

    NOTE: Run directories may ALSO have docs/archive structure (from SOT repair),
    but name-based patterns take priority over structure detection.

    Args:
        dirpath: Directory path to check

    Returns:
        True if directory is a run directory
    """
    # Skip runtime workspaces (these are never runs)
    if is_runtime_workspace(dirpath):
        return False

    # Check for run artifact markers
    has_rollback_log = (dirpath / "rollback.log").exists()
    has_executor_log = (dirpath / "executor.log").exists()
    has_errors_dir = (dirpath / "errors").exists()

    # Matches run directory patterns (prioritize name patterns)
    name_lower = dirpath.name.lower()
    looks_like_run = (
        has_rollback_log or
        has_executor_log or
        has_errors_dir or
        "build" in name_lower or
        "telemetry" in name_lower or
        "test-" in name_lower or
        "autopack-" in name_lower or       # autopack-diagnostics-parity-*, autopack-onephase-*, etc.
        "research-" in name_lower or       # research-system-v*, research-build113-test
        "retry-" in name_lower or          # retry-api-router-*, retry-examples-*
        "diagnostics-" in name_lower or    # diagnostics-parity-phases-*
        "lovable-" in name_lower or        # lovable-integration-*, lovable-p0-*, etc.
        "p10-" in name_lower or            # p10-validation-test
        name_lower == "start" or           # start/
        name_lower == "errors" or          # errors/
        name_lower == "logs" or            # logs/
        name_lower.startswith("run-")      # run-001, run-002
    )

    return looks_like_run


def get_directory_age(dirpath: Path) -> timedelta:
    """
    Get age of directory based on most recent file modification time.

    Args:
        dirpath: Directory path

    Returns:
        Age as timedelta
    """
    try:
        # Find most recent file in directory tree
        most_recent = 0.0
        for item in dirpath.rglob("*"):
            if item.is_file():
                mtime = item.stat().st_mtime
                most_recent = max(most_recent, mtime)

        if most_recent == 0.0:
            # Empty directory - use directory mtime
            most_recent = dirpath.stat().st_mtime

        age = datetime.now() - datetime.fromtimestamp(most_recent)
        return age
    except Exception as e:
        logger.warning(f"[CLEANUP] Failed to get age for {dirpath}: {e}")
        return timedelta(days=0)


def find_orphaned_files(autonomous_runs: Path) -> List[Path]:
    """
    Find orphaned files (not in run/project directories).

    Includes:
    - Log files (*.log)
    - JSON files (*.json, *.jsonl)
    - Other orphaned artifacts at .autonomous_runs/ root

    Excludes:
    - Files in subdirectories (they belong to run/project directories)

    Args:
        autonomous_runs: Path to .autonomous_runs directory

    Returns:
        List of orphaned file paths
    """
    orphaned_files = []

    # Patterns for orphaned files at root
    orphaned_patterns = [
        "*.log",           # All log files (api_server.log, build*.log, tidy_*.log, etc.)
        "*.json",          # All JSON files (baseline.json, retry.json, verify_report_*.json)
        "*.jsonl",         # JSONL files (telemetry_counts.jsonl)
    ]

    # Find all orphaned files directly under .autonomous_runs/ (not in subdirectories)
    for pattern in orphaned_patterns:
        for filepath in autonomous_runs.glob(pattern):
            if filepath.is_file():
                orphaned_files.append(filepath)

    return orphaned_files


def find_duplicate_baseline_archives(autonomous_runs: Path) -> List[Path]:
    """
    Find duplicate baseline archives (keep only most recent per prefix).

    Args:
        autonomous_runs: Path to .autonomous_runs directory

    Returns:
        List of duplicate archive paths to delete
    """
    duplicates = []

    # Find all baseline archives
    baseline_archives = list(autonomous_runs.glob("baselines_*.zip"))

    if len(baseline_archives) <= 1:
        return duplicates

    # Sort by modification time (newest first)
    baseline_archives.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Keep only the most recent one
    duplicates = baseline_archives[1:]

    return duplicates


def find_old_run_directories(
    autonomous_runs: Path,
    keep_last_n: int = 10,
    min_age_days: int = 7
) -> List[Path]:
    """
    Find old run directories to archive/delete.

    Keeps last N runs per project, and preserves runs younger than min_age_days.

    Args:
        autonomous_runs: Path to .autonomous_runs directory
        keep_last_n: Number of runs to keep per project (default: 10)
        min_age_days: Minimum age in days before considering for cleanup (default: 7)

    Returns:
        List of old run directory paths
    """
    old_runs = []

    # Group run directories by prefix (e.g., "build", "telemetry-collection")
    run_groups = {}

    for item in autonomous_runs.iterdir():
        if not item.is_dir():
            continue

        # Skip runtime workspaces (but NOT project directories, since runs can have docs/archive)
        if is_runtime_workspace(item):
            continue

        # Check if it's a run directory
        if not is_run_directory(item):
            continue

        # Extract run prefix (everything before first digit or timestamp)
        name = item.name
        prefix = name.split("-")[0] if "-" in name else name

        if prefix not in run_groups:
            run_groups[prefix] = []
        run_groups[prefix].append(item)

    # For each group, keep last N runs
    for prefix, runs in run_groups.items():
        # Sort by modification time (newest first)
        runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        # Mark old runs for deletion (beyond keep_last_n)
        for i, run_dir in enumerate(runs):
            # Skip if within keep_last_n
            if i < keep_last_n:
                continue

            # Check age
            age = get_directory_age(run_dir)
            if age.days >= min_age_days:
                old_runs.append(run_dir)

    return old_runs


def find_empty_directories(autonomous_runs: Path) -> List[Path]:
    """
    Find empty directories (no files, no subdirectories).

    Args:
        autonomous_runs: Path to .autonomous_runs directory

    Returns:
        List of empty directory paths
    """
    empty_dirs = []

    for item in autonomous_runs.rglob("*"):
        if not item.is_dir():
            continue

        # Check if directory is empty
        try:
            if not any(item.iterdir()):
                empty_dirs.append(item)
        except PermissionError:
            logger.warning(f"[CLEANUP] Permission denied: {item}")
            continue

    return empty_dirs


def archive_old_autopack_runs(
    repo_root: Path,
    autonomous_runs: Path,
    keep_last_n: int = 10,
    dry_run: bool = True
) -> int:
    """
    Archive old Autopack run directories to archive/runs/.

    Keeps the last N runs at .autonomous_runs/ root, moves older runs to archive/runs/.

    Args:
        repo_root: Repository root path
        autonomous_runs: Path to .autonomous_runs directory
        keep_last_n: Number of runs to keep (default: 10)
        dry_run: If True, only preview changes (default: True)

    Returns:
        Number of runs archived
    """
    autopack_archive_runs = repo_root / "archive" / "runs"
    archived_count = 0

    # Known project workspace directories (these should NOT be archived)
    known_project_workspaces = {
        "file-organizer-app-v1",
        "storage-optimizer",
    }

    # Find all Autopack run directories at .autonomous_runs/ root
    autopack_run_dirs = []
    for item in autonomous_runs.iterdir():
        if not item.is_dir():
            continue

        # Skip runtime workspaces
        if is_runtime_workspace(item):
            continue

        # Skip known project workspaces (explicit whitelist)
        if item.name in known_project_workspaces:
            continue

        # CRITICAL: Prioritize name-based run detection over structure detection
        # Run directories may have docs/archive from SOT repair, but should still be archived
        if is_run_directory(item):
            autopack_run_dirs.append(item)

    if not autopack_run_dirs:
        return 0

    # Sort by modification time (newest first) to keep last N
    autopack_run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Determine which runs to archive (beyond keep_last_n)
    runs_to_archive = autopack_run_dirs[keep_last_n:]

    if not runs_to_archive:
        return 0

    print(f"[RUN-ARCHIVAL] Found {len(runs_to_archive)} old Autopack run directories to archive (keeping last {keep_last_n}):")
    print()

    for run_dir in sorted(runs_to_archive, key=lambda p: p.name):
        dest_dir = autopack_archive_runs / run_dir.name
        rel_src = run_dir.relative_to(repo_root)
        rel_dest = dest_dir.relative_to(repo_root)

        print(f"  MOVE {rel_src}/ → {rel_dest}/")

        if not dry_run:
            try:
                # Create destination parent directory
                autopack_archive_runs.mkdir(parents=True, exist_ok=True)

                # Move the run directory
                shutil.move(str(run_dir), str(dest_dir))
                archived_count += 1
            except Exception as e:
                logger.warning(f"[RUN-ARCHIVAL] Failed to archive {run_dir}: {e}")

    print()
    print(f"[RUN-ARCHIVAL-SUMMARY] Archived {archived_count}/{len(runs_to_archive)} run directories to archive/runs/")
    print()

    return archived_count


def cleanup_autonomous_runs(
    repo_root: Path,
    dry_run: bool = True,
    verbose: bool = False,
    keep_last_n_runs: int = 10,
    min_age_days: int = 7
) -> Tuple[int, int]:
    """
    Clean up .autonomous_runs/ directory.

    Args:
        repo_root: Repository root path
        dry_run: If True, only preview changes (default: True)
        verbose: If True, show detailed output (default: False)
        keep_last_n_runs: Number of runs to keep per project (default: 10)
        min_age_days: Minimum age in days before cleanup (default: 7)

    Returns:
        Tuple of (files_deleted, dirs_deleted)
    """
    autonomous_runs = repo_root / ".autonomous_runs"

    if not autonomous_runs.exists():
        if verbose:
            print("[CLEANUP] .autonomous_runs/ does not exist, skipping")
        return 0, 0

    print(f"\n{'='*70}")
    print("Phase 3: .autonomous_runs/ Cleanup")
    print(f"{'='*70}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Keep last N runs: {keep_last_n_runs}")
    print(f"Minimum age for cleanup: {min_age_days} days")
    print()

    files_deleted = 0
    dirs_deleted = 0

    # Step 0: Archive old Autopack runs to archive/runs/ (keeps last 10 at .autonomous_runs/ root)
    archive_old_autopack_runs(repo_root, autonomous_runs, keep_last_n=keep_last_n_runs, dry_run=dry_run)

    # Step 1: Orphaned files (logs, JSON, etc.)
    orphaned_files = find_orphaned_files(autonomous_runs)
    if orphaned_files:
        print(f"[ORPHANED-FILES] Found {len(orphaned_files)} orphaned files:")

        # Route to archive/diagnostics/logs/autonomous_runs/
        archive_dest = repo_root / "archive" / "diagnostics" / "logs" / "autonomous_runs"

        for filepath in orphaned_files:
            rel_path = filepath.relative_to(repo_root)
            size_kb = filepath.stat().st_size / 1024

            # Determine destination based on file type
            if filepath.suffix in ['.log', '.jsonl']:
                dest_subdir = archive_dest
            elif filepath.suffix == '.json':
                # JSON reports/metadata go to diagnostics
                dest_subdir = archive_dest
            else:
                dest_subdir = archive_dest

            dest_file = dest_subdir / filepath.name

            print(f"  MOVE {rel_path} → archive/diagnostics/logs/autonomous_runs/{filepath.name} ({size_kb:.1f} KB)")

            if not dry_run:
                dest_subdir.mkdir(parents=True, exist_ok=True)

                # Handle duplicates with timestamp
                if dest_file.exists():
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = dest_file.stem
                    suffix = dest_file.suffix
                    dest_file = dest_subdir / f"{stem}_{timestamp}{suffix}"

                filepath.rename(dest_file)
                files_deleted += 1
        print()

    # Step 2: Duplicate baseline archives
    duplicate_archives = find_duplicate_baseline_archives(autonomous_runs)
    if duplicate_archives:
        print(f"[DUPLICATE-ARCHIVES] Found {len(duplicate_archives)} duplicate baseline archives:")
        for archive in duplicate_archives:
            rel_path = archive.relative_to(repo_root)
            size_mb = archive.stat().st_size / (1024 * 1024)
            print(f"  DELETE {rel_path} ({size_mb:.2f} MB)")
            if not dry_run:
                archive.unlink()
                files_deleted += 1
        print()

    # Step 3: Empty directories (run after archiving runs)
    empty_dirs = find_empty_directories(autonomous_runs)
    if empty_dirs:
        print(f"[EMPTY-DIRS] Found {len(empty_dirs)} empty directories:")
        for empty_dir in empty_dirs:
            rel_path = empty_dir.relative_to(repo_root)
            print(f"  DELETE {rel_path}/")
            if not dry_run:
                try:
                    empty_dir.rmdir()
                    dirs_deleted += 1
                except OSError as e:
                    logger.warning(f"[CLEANUP] Failed to delete {empty_dir}: {e}")
        print()

    # Summary
    print(f"[CLEANUP-SUMMARY] Files deleted: {files_deleted}, Directories deleted: {dirs_deleted}")

    return files_deleted, dirs_deleted


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Clean up .autonomous_runs/ directory"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run only (default)")
    parser.add_argument("--execute", action="store_true",
                        help="Execute cleanup (overrides --dry-run)")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output")
    parser.add_argument("--keep-last-n-runs", type=int, default=10,
                        help="Number of runs to keep per project (default: 10)")
    parser.add_argument("--min-age-days", type=int, default=7,
                        help="Minimum age in days before cleanup (default: 7)")

    args = parser.parse_args()

    # Resolve execution mode
    dry_run = not args.execute

    # Find repo root (assume script is in scripts/tidy/)
    repo_root = Path(__file__).parent.parent.parent

    cleanup_autonomous_runs(
        repo_root=repo_root,
        dry_run=dry_run,
        verbose=args.verbose,
        keep_last_n_runs=args.keep_last_n_runs,
        min_age_days=args.min_age_days
    )
