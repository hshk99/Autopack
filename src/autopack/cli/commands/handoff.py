"""CLI command for generating handoff bundles from run directories.

Provides the `autopack handoff` command to generate deterministic,
reproducible handoff bundles for diagnostics and analysis.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

logger = logging.getLogger(__name__)


@click.command("handoff")
@click.argument(
    "run_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging output",
)
def handoff_command(run_dir: Path, verbose: bool) -> None:
    """Generate handoff bundle from a run directory.

    Creates a deterministic handoff/ folder containing:
    - index.json: Manifest of artifacts with metadata
    - summary.md: High-signal narrative of run execution
    - excerpts/: Tailed/snippets of key artifacts

    Example:
        autopack handoff .autonomous_runs/my-run-20251220

    Args:
        run_dir: Path to .autonomous_runs/<run_id>/ directory
        verbose: Enable verbose logging
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        click.echo(f"Generating handoff bundle for: {run_dir}")
        click.echo()

        # Generate bundle
        handoff_dir = generate_handoff_bundle(run_dir)

        # Report success
        click.echo()
        click.secho("✓ Handoff bundle generated successfully", fg="green", bold=True)
        click.echo()
        click.echo(f"Location: {handoff_dir}")
        click.echo()
        click.echo("Contents:")
        click.echo(f"  - {handoff_dir / 'index.json'} (artifact manifest)")
        click.echo(f"  - {handoff_dir / 'summary.md'} (high-signal narrative)")
        click.echo(f"  - {handoff_dir / 'excerpts'}/ (tailed/snippets)")
        click.echo()
        click.echo("Next steps:")
        click.echo("  1. Review summary.md for overview")
        click.echo("  2. Check excerpts/ for quick previews")
        click.echo("  3. Examine full artifacts as needed")

    except ValueError as e:
        click.secho(f"✗ Error: {e}", fg="red", bold=True, err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during handoff bundle generation")
        click.secho(f"✗ Unexpected error: {e}", fg="red", bold=True, err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register handoff command with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(handoff_command)
