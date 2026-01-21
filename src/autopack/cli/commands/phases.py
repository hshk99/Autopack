"""Legacy CLI shim for phase-related commands.

DEPRECATION NOTICE:
This CLI module is a test shim and should NOT be used for production phase management.

For actual phase management:
- Use the Supervisor REST API endpoints at `/runs/{run_id}/phases/{phase_id}/*`
- See API documentation for available endpoints:
  - POST /runs/{run_id}/phases/{phase_id}/update_status
  - POST /runs/{run_id}/phases/{phase_id}/builder_result
  - POST /runs/{run_id}/phases/{phase_id}/auditor_result
  - POST /runs/{run_id}/phases/{phase_id}/record_issue

For interactive phase management:
- Use the Supervisor web UI (configured via FRONTEND_BASE_URL)
- Access dashboard endpoints for run/phase status visualization

This shim exists only for backwards compatibility with legacy tests.
"""

from __future__ import annotations

import click

# Guidance message for migration to supervisor-side API
MIGRATION_MESSAGE = """
⚠️  This is a test shim. For production phase management:

   → Supervisor REST API: POST /runs/{run_id}/phases/{phase_id}/update_status
   → Web UI: Access via FRONTEND_BASE_URL for interactive management
   → See docs/API.md for full endpoint documentation
"""


@click.group()
def cli() -> None:
    """Phase-related commands (legacy test shim).

    ⚠️  DEPRECATED: Use Supervisor REST API for production phase management.
    """
    pass


@cli.command("create-phase")
@click.option("--name", required=True, type=str)
@click.option("--description", required=True, type=str)
@click.option("--complexity", required=True, type=click.Choice(["low", "medium", "high"]))
def create_phase(name: str, description: str, complexity: str) -> None:
    """Create a phase (test shim).

    ⚠️  DEPRECATED: This command is for testing only.
    For production, use POST /runs/{run_id}/phases API endpoint.
    """
    # NOTE: `description` is unused here; it's present to match the CLI contract.
    click.echo(f"Phase '{name}' created with complexity '{complexity}'.")
    click.echo(MIGRATION_MESSAGE)


@cli.command("execute-phase")
@click.option("--phase-id", required=True, type=int)
def execute_phase(phase_id: int) -> None:
    """Execute a phase (test shim).

    ⚠️  DEPRECATED: This command is for testing only.
    For production, use POST /runs/{run_id}/phases/{phase_id}/update_status API endpoint.
    """
    click.echo(f"Executing phase with ID {phase_id}.")
    click.echo(MIGRATION_MESSAGE)


@cli.command("review-phase")
@click.option("--phase-id", required=True, type=int)
def review_phase(phase_id: int) -> None:
    """Review a phase (test shim).

    ⚠️  DEPRECATED: This command is for testing only.
    For production phase reviews, use the Supervisor web UI or API.
    """
    click.echo(f"Reviewing phase with ID {phase_id}.")
    click.echo(MIGRATION_MESSAGE)


@cli.command("phase-status")
@click.option("--phase-id", required=True, type=int)
def phase_status(phase_id: int) -> None:
    """Show phase status (test shim).

    ⚠️  DEPRECATED: This command is for testing only and returns mock data.
    For real phase status, use GET /runs/{run_id} or /dashboard/runs/{run_id}/status API endpoints.
    """
    click.echo(f"⚠️  Mock status for phase ID {phase_id}: In Progress (test data only)")
    click.echo(MIGRATION_MESSAGE)


if __name__ == "__main__":
    cli()
