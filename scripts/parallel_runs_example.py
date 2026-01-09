#!/usr/bin/env python3
"""Example: Running multiple Autopack runs in parallel.

This script demonstrates how to use the parallel runs capability
to execute multiple autonomous runs concurrently.

Requirements:
- Postgres database (recommended) OR use --per-run-sqlite
- Git 2.25+ for worktree support
- Python 3.9+

Example usage:
    # Run with Postgres
    python scripts/parallel_runs_example.py --use-postgres

    # Run with per-run SQLite
    python scripts/parallel_runs_example.py --use-sqlite

    # Custom configuration
    python scripts/parallel_runs_example.py \
        --runs-dir /tmp/parallel_test \
        --workers 4
"""

import argparse
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.config import settings
from autopack.workspace_manager import WorkspaceManager


def create_example_runs(db_url: str, count: int = 3) -> list[str]:
    """Create example run records in database.

    Args:
        db_url: Database connection URL
        count: Number of runs to create

    Returns:
        List of run IDs
    """
    print(f"\n📝 Creating {count} example runs...")

    run_ids = []
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for i in range(1, count + 1):
        run_id = f"parallel-example-{timestamp}-{i:02d}"
        run_ids.append(run_id)
        print(f"   {i}. {run_id}")

    # TODO: Insert runs into database using your run creation logic
    # For now, just return the IDs (assumes runs already exist or will be created)

    return run_ids


def run_parallel_example(
    workers: int = 3,
    use_postgres: bool = True,
    runs_dir: str = None,
    cleanup: bool = True
):
    """Run parallel execution example.

    Args:
        workers: Number of concurrent workers
        use_postgres: Use Postgres (True) or per-run SQLite (False)
        runs_dir: Custom autonomous runs directory
        cleanup: Cleanup worktrees after completion
    """
    print("=" * 80)
    print("PARALLEL RUNS EXAMPLE")
    print("=" * 80)

    # Configuration
    repo_path = Path.cwd()
    runs_dir = runs_dir or settings.autonomous_runs_dir

    if use_postgres:
        db_url = settings.database_url
        if not db_url.startswith("postgresql://"):
            print("⚠️  WARNING: Using non-Postgres database for parallel runs!")
            print("   This may cause concurrency issues.")
            print("   Recommendation: Use --use-sqlite for per-run databases")
            response = input("\nContinue anyway? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted.")
                return 1
    else:
        db_url = "sqlite:///per-run"  # Placeholder - supervisor will create per-run DBs

    print("\n📊 Configuration:")
    print(f"   Workers:       {workers}")
    print(f"   Database:      {'Postgres (shared)' if use_postgres else 'SQLite (per-run)'}")
    print(f"   Runs Dir:      {runs_dir}")
    print(f"   Repo:          {repo_path}")
    print(f"   Cleanup:       {cleanup}")

    # Create example run IDs
    run_ids = create_example_runs(db_url, count=workers)

    # Build supervisor command
    cmd = [
        sys.executable,
        str(repo_path / "scripts" / "autopack_supervisor.py"),
        "--run-ids", ",".join(run_ids),
        "--workers", str(workers),
        "--source-repo", str(repo_path),
        "--autonomous-runs-dir", runs_dir,
    ]

    if use_postgres:
        cmd.extend(["--database-url", db_url])
    else:
        cmd.append("--per-run-sqlite")

    print("\n🚀 Launching supervisor...")
    print(f"   Command: {' '.join(cmd)}")
    print()

    # Execute supervisor
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            env={**subprocess.os.environ, "PYTHONUTF8": "1"}
        )

        if result.returncode == 0:
            print("\n✅ All runs completed successfully!")
        else:
            print(f"\n❌ Some runs failed (exit code: {result.returncode})")

        # Show artifacts
        print("\n📁 Artifacts location:")
        for run_id in run_ids:
            run_dir = Path(runs_dir) / run_id
            if run_dir.exists():
                print(f"   {run_id}/")
                print("      ├── ci/         (test reports)")
                print("      ├── baselines/  (test baselines)")
                if not use_postgres:
                    print(f"      └── {run_id}.db  (SQLite database)")

        # Cleanup option
        if cleanup:
            print("\n🧹 Cleaning up worktrees...")
            cleanup_count = WorkspaceManager.cleanup_all_worktrees(
                repo=repo_path,
                worktree_base=Path(runs_dir) / "workspaces"
            )
            print(f"   Removed {cleanup_count} worktrees")

        return result.returncode

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Parallel runs example script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Execution mode
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--use-postgres",
        action="store_true",
        help="Use shared Postgres database (recommended for production)"
    )
    mode.add_argument(
        "--use-sqlite",
        action="store_true",
        help="Use per-run SQLite databases (no Postgres required)"
    )

    # Configuration
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of concurrent workers (default: 3)"
    )

    parser.add_argument(
        "--runs-dir",
        type=str,
        help="Custom autonomous runs directory (default: from settings)"
    )

    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Don't cleanup worktrees after completion (for debugging)"
    )

    args = parser.parse_args()

    # Run example
    return run_parallel_example(
        workers=args.workers,
        use_postgres=args.use_postgres,
        runs_dir=args.runs_dir,
        cleanup=not args.no_cleanup
    )


if __name__ == "__main__":
    sys.exit(main())
