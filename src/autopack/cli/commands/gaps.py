"""CLI command for gap scanning (BUILD-179).

Provides the `autopack gaps scan` command as a thin wrapper around
the gaps.api library module.
"""

import json
import logging
import sys
from pathlib import Path

import click

from autopack.gaps.api import scan_gaps

logger = logging.getLogger(__name__)


@click.group("gaps")
def gaps_group() -> None:
    """Gap detection commands."""
    pass


@gaps_group.command("scan")
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
    help="Write gap report to run-local artifact (default: report only)",
)
@click.option(
    "--workspace",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Workspace root directory (default: current directory)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def scan_command(
    run_id: str,
    project_id: str,
    write: bool,
    workspace: Path | None,
    verbose: bool,
) -> None:
    """Scan workspace for gaps (deterministic).

    Scans the workspace for documentation drift, configuration issues,
    protected path violations, and other gaps that may require attention.

    Examples:

        # Report only (prints to stdout):
        autopack gaps scan --run-id test-run-001 --project-id autopack

        # Write to run-local artifact:
        autopack gaps scan --run-id test-run-001 --project-id autopack --write
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        result = scan_gaps(
            run_id=run_id,
            project_id=project_id,
            workspace_root=workspace,
            write_artifact=write,
        )

        # Print summary to stderr (so stdout is clean JSON)
        click.echo(
            f"[Gap Scanner] Found {result.total_gaps} gaps "
            f"({result.report.summary.autopilot_blockers} blockers)",
            err=True,
        )

        if result.artifact_path:
            click.echo(
                f"[Gap Scanner] Wrote gap report: {result.artifact_path}",
                err=True,
            )

        # Print JSON to stdout
        click.echo(json.dumps(result.report.to_json_dict(), indent=2, ensure_ascii=False))

    except ValueError as e:
        click.secho(f"[Gap Scanner] ERROR: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Gap scanner failed")
        click.secho(f"[Gap Scanner] ERROR: {e}", fg="red", err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register gaps command group with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(gaps_group)
