"""CLI command for supervised parallel execution (BUILD-179).

Provides the `autopack autopilot supervise` command as a thin wrapper around
the supervisor.api library module. This enforces parallelism policy gates.
"""

import logging
import sys
from pathlib import Path
from typing import List

import click

from autopack.supervisor.api import (
    run_parallel_supervised,
    list_worktrees,
    cleanup_worktrees,
    SupervisorResult,
)
from autopack.supervisor.parallel_run_supervisor import SupervisorError
from autopack.autonomy.parallelism_gate import ParallelismPolicyViolation
from autopack.config import settings

logger = logging.getLogger(__name__)


@click.command("supervise")
@click.option(
    "--run-ids",
    required=False,
    help="Comma-separated list of run IDs to execute (e.g., 'run1,run2,run3')",
)
@click.option(
    "--anchor-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    required=False,
    help="Path to IntentionAnchorV2 JSON (REQUIRED for parallel execution)",
)
@click.option(
    "--workers",
    type=int,
    default=3,
    help="Maximum number of concurrent workers (default: 3)",
)
@click.option(
    "--database-url",
    type=str,
    default=None,
    help="Database URL (default: from settings). Postgres recommended for parallel runs.",
)
@click.option(
    "--per-run-sqlite",
    is_flag=True,
    help="Use per-run SQLite databases instead of shared Postgres (limits aggregation)",
)
@click.option(
    "--source-repo",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Source git repository path (default: current directory)",
)
@click.option(
    "--autonomous-runs-dir",
    type=str,
    default=None,
    help="Override autonomous runs directory (default: from settings)",
)
@click.option(
    "--list-worktrees",
    "list_wt",
    is_flag=True,
    help="List all existing worktrees and exit",
)
@click.option(
    "--cleanup",
    is_flag=True,
    help="Remove all managed worktrees and exit",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def supervise_command(
    run_ids: str | None,
    anchor_path: Path | None,
    workers: int,
    database_url: str | None,
    per_run_sqlite: bool,
    source_repo: Path | None,
    autonomous_runs_dir: str | None,
    list_wt: bool,
    cleanup: bool,
    verbose: bool,
) -> None:
    """Supervised parallel execution of multiple runs.

    Orchestrates parallel autonomous runs with policy enforcement.
    Parallel execution is BLOCKED unless an IntentionAnchorV2 with
    parallelism_isolation.allowed=true is provided.

    Safety guarantees:
    - Each run gets its own git worktree (no cross-run git contamination)
    - Workspace leases prevent concurrent access to same directory
    - Parallelism policy enforced via IntentionAnchorV2

    Examples:

        # Run 3 workers concurrently with Postgres:
        autopack autopilot supervise \\
            --run-ids run1,run2,run3 \\
            --anchor-path anchor.json \\
            --workers 3 \\
            --database-url postgresql://autopack:autopack@localhost:5432/autopack

        # Run 2 workers with per-run SQLite:
        autopack autopilot supervise \\
            --run-ids run1,run2 \\
            --anchor-path anchor.json \\
            --workers 2 \\
            --per-run-sqlite

        # List existing worktrees:
        autopack autopilot supervise --list-worktrees

        # Cleanup all worktrees:
        autopack autopilot supervise --cleanup
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handle utility commands
    if list_wt:
        worktrees = list_worktrees(source_repo)
        click.echo(f"\nFound {len(worktrees)} worktrees:")
        for wt in worktrees:
            path = wt.get("path", "unknown")
            branch = wt.get("branch", "(detached)")
            commit = wt.get("commit", "unknown")[:8]
            click.echo(f"  {path}")
            click.echo(f"    Branch: {branch}")
            click.echo(f"    Commit: {commit}")
        return

    if cleanup:
        wt_base = None
        if autonomous_runs_dir:
            wt_base = Path(autonomous_runs_dir) / "workspaces"
        count = cleanup_worktrees(source_repo, wt_base)
        click.echo(f"Cleaned up {count} worktrees")
        return

    # Execution mode requires run-ids and anchor-path
    if not run_ids:
        click.secho(
            "[Supervisor] ERROR: --run-ids required for execution mode "
            "(or use --list-worktrees / --cleanup)",
            fg="red",
            err=True,
        )
        sys.exit(1)

    if not anchor_path:
        click.secho(
            "[Supervisor] ERROR: --anchor-path required for parallel execution.",
            fg="red",
            err=True,
        )
        click.echo(
            "[Supervisor] Parallel runs require an IntentionAnchorV2 with "
            "parallelism_isolation.allowed=true.",
            err=True,
        )
        sys.exit(1)

    # Parse run IDs
    run_id_list: List[str] = [rid.strip() for rid in run_ids.split(",")]

    try:
        result = run_parallel_supervised(
            run_ids=run_id_list,
            anchor_path=anchor_path,
            source_repo=source_repo,
            database_url=database_url,
            autonomous_runs_dir=autonomous_runs_dir,
            per_run_sqlite=per_run_sqlite,
            max_workers=workers,
        )

        # Print summary
        click.echo("")
        click.echo("=" * 80)
        click.echo("EXECUTION SUMMARY")
        click.echo("=" * 80)

        for run_id, run_result in result.run_results.items():
            if run_result.success:
                click.secho(f"{run_id}: SUCCESS", fg="green")
            else:
                click.secho(f"{run_id}: FAILED", fg="red")
                if run_result.error:
                    click.echo(f"  Error: {run_result.error}")
            if run_result.workspace:
                click.echo(f"  Workspace: {run_result.workspace}")

        click.echo("")
        click.echo(
            f"Total: {result.successful_runs}/{result.total_runs} successful"
        )

        if not result.all_successful:
            sys.exit(1)

    except ParallelismPolicyViolation as e:
        click.secho(
            f"[Supervisor] PARALLELISM BLOCKED: {e}",
            fg="red",
            bold=True,
            err=True,
        )
        click.echo(
            "[Supervisor] Parallel execution requires an IntentionAnchorV2 "
            "with parallelism_isolation.allowed=true.",
            err=True,
        )
        sys.exit(1)

    except SupervisorError as e:
        click.secho(f"[Supervisor] ERROR: {e}", fg="red", err=True)
        sys.exit(1)

    except FileNotFoundError as e:
        click.secho(f"[Supervisor] ERROR: {e}", fg="red", err=True)
        sys.exit(1)

    except Exception as e:
        logger.exception("Supervisor failed")
        click.secho(f"[Supervisor] ERROR: {e}", fg="red", err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register supervise command with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(supervise_command)
