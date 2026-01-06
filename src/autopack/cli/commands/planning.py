"""CLI command for plan proposal (BUILD-179).

Provides the `autopack plan propose` command as a thin wrapper around
the planning.api library module.
"""

import json
import logging
import sys
from pathlib import Path

import click

from autopack.planning.api import propose_plan_from_files

logger = logging.getLogger(__name__)


@click.group("plan")
def plan_group() -> None:
    """Planning commands."""
    pass


@plan_group.command("propose")
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
    "--write",
    is_flag=True,
    help="Write plan proposal to run-local artifact (default: report only)",
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
    "--gap-report-path",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to gap report v1 JSON (optional, auto-detects if not provided)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def propose_command(
    run_id: str,
    project_id: str,
    write: bool,
    workspace: Path | None,
    anchor_path: Path | None,
    gap_report_path: Path | None,
    verbose: bool,
) -> None:
    """Propose plan from anchor and gap report.

    Takes an intention anchor and gap report as inputs, and generates
    a plan proposal with actions mapped to gaps, governance checks,
    and approval status.

    Examples:

        # Report only (prints to stdout):
        autopack plan propose --run-id test-run-001 --project-id autopack

        # Write to run-local artifact:
        autopack plan propose --run-id test-run-001 --project-id autopack --write
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        result = propose_plan_from_files(
            run_id=run_id,
            project_id=project_id,
            workspace_root=workspace,
            anchor_path=anchor_path,
            gap_report_path=gap_report_path,
            write_artifact=write,
        )

        # Print summary to stderr
        click.echo(
            f"[Plan Proposer] Generated {result.total_actions} actions "
            f"({result.auto_approved_count} auto-approved, "
            f"{result.requires_approval_count} require approval, "
            f"{result.blocked_count} blocked)",
            err=True,
        )

        if result.artifact_path:
            click.echo(
                f"[Plan Proposer] Wrote plan proposal: {result.artifact_path}",
                err=True,
            )

        # Print JSON to stdout
        click.echo(json.dumps(result.proposal.to_json_dict(), indent=2, ensure_ascii=False))

    except FileNotFoundError as e:
        click.secho(f"[Plan Proposer] ERROR: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Plan proposer failed")
        click.secho(f"[Plan Proposer] ERROR: {e}", fg="red", err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register plan command group with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(plan_group)
