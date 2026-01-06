"""CLI command for autopilot execution (BUILD-179).

Provides the `autopack autopilot run` command as a thin wrapper around
the autonomy.api library module, and the `autopack autopilot supervise`
command for parallel execution via the supervisor module.
"""

import json
import logging
import sys
from pathlib import Path

import click

from autopack.autonomy.api import run_autopilot
from .supervisor import supervise_command

logger = logging.getLogger(__name__)


@click.group("autopilot")
def autopilot_group() -> None:
    """Autopilot commands (autonomous execution)."""
    pass


# Register supervise command under autopilot group
autopilot_group.add_command(supervise_command)


@autopilot_group.command("run")
@click.option(
    "--run-id",
    required=True,
    help="Run identifier",
)
@click.option(
    "--project-id",
    required=True,
    help="Project identifier",
)
@click.option(
    "--enable",
    is_flag=True,
    help="REQUIRED: Explicitly enable autopilot execution (default: OFF)",
)
@click.option(
    "--write",
    is_flag=True,
    help="Write autopilot session to run-local artifact (default: report only)",
)
@click.option(
    "--workspace",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace root directory (default: current directory)",
)
@click.option(
    "--anchor-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to intention anchor v2 JSON (optional, auto-detects if not provided)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def run_command(
    run_id: str,
    project_id: str,
    enable: bool,
    write: bool,
    workspace: Path | None,
    anchor_path: Path | None,
    verbose: bool,
) -> None:
    """Run autopilot session (single run).

    Executes autonomous actions based on the intention anchor and plan.
    By default, autopilot is DISABLED (safe-by-default). You must pass
    --enable to actually execute actions.

    Examples:

        # Dry-run (disabled, shows what would happen):
        autopack autopilot run --run-id test-run-001 --project-id autopack

        # Enable autopilot and execute auto-approved actions:
        autopack autopilot run --run-id test-run-001 --project-id autopack --enable --write
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Show warning if not enabled
    if not enable:
        click.secho(
            "[Autopilot] WARNING: Autopilot is DISABLED by default.",
            fg="yellow",
            err=True,
        )
        click.echo(
            "[Autopilot] This is a dry-run. No actions will be executed.",
            err=True,
        )
        click.echo(
            "[Autopilot] Use --enable to explicitly enable autonomous execution.",
            err=True,
        )
        click.echo("", err=True)

    try:
        result = run_autopilot(
            run_id=run_id,
            project_id=project_id,
            workspace_root=workspace,
            anchor_path=anchor_path,
            enabled=enable,
            write_artifact=write,
        )

        # Print summary to stderr
        click.echo(
            f"[Autopilot] Session {result.session.session_id}: {result.status}",
            err=True,
        )

        if result.session.execution_summary:
            summary = result.session.execution_summary
            click.echo(
                f"[Autopilot] Executed {summary.executed_actions}/{summary.total_actions} actions "
                f"({summary.successful_actions} successful, {summary.failed_actions} failed)",
                err=True,
            )

        if result.approval_requests_count > 0:
            click.echo(
                f"[Autopilot] {result.approval_requests_count} action(s) require approval",
                err=True,
            )

        if result.artifact_path:
            click.echo(f"[Autopilot] Wrote session: {result.artifact_path}", err=True)

        # Print JSON to stdout
        click.echo(json.dumps(result.session.to_json_dict(), indent=2, ensure_ascii=False))

    except FileNotFoundError as e:
        click.secho(f"[Autopilot] ERROR: {e}", fg="red", err=True)
        sys.exit(1)
    except RuntimeError as e:
        # Expected errors (e.g., autopilot disabled)
        click.secho(f"[Autopilot] ERROR: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Autopilot failed")
        click.secho(f"[Autopilot] ERROR: {e}", fg="red", err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register autopilot command group with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(autopilot_group)
