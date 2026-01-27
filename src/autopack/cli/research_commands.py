"""CLI commands for research system integration.

Provides command-line interface for:
- Starting research sessions
- Checking research status
- Exporting research results
- Listing past research sessions
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click

# Import for test compatibility (allows monkeypatching)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

logger = logging.getLogger(__name__)


@click.group(name="research")
def research_cli():
    """Research system commands."""
    pass


@research_cli.command(name="start")
@click.argument("query", required=True)
@click.option("--phase-id", help="Phase ID for this research session")
@click.option("--max-results", default=5, help="Maximum number of results")
@click.option("--timeout", default=300, help="Timeout in seconds")
@click.option("--output", type=click.Path(), help="Output file for results")
def start_research(
    query: str, phase_id: Optional[str], max_results: int, timeout: int, output: Optional[str]
):
    """Start a research session.

    Example:
        autopack research start "Best practices for API design"
    """
    console = Console() if RICH_AVAILABLE else None

    if console:
        console.print("[bold blue]Starting research session...[/bold blue]")
        console.print(f"Query: {query}")
    else:
        click.echo("Starting research session...")
        click.echo(f"Query: {query}")

    # Generate phase ID if not provided
    if not phase_id:
        phase_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Import here to avoid circular dependencies
        from autopack.phases.research_phase import create_research_phase

        # Create and execute research phase
        phase = create_research_phase(
            phase_id=phase_id,
            queries=[query],
            max_duration_seconds=timeout,
        )

        result = phase.execute()

        # Display results
        if console:
            _display_results_rich(console, result)
        else:
            _display_results_plain(result)

        # Save to file if requested
        if output:
            output_path = Path(output)
            output_path.write_text(
                json.dumps(
                    {
                        "phase_id": result.phase_id,
                        "status": result.status.value,
                        "summary": result.summary,
                        "recommendations": result.recommendations,
                        "warnings": result.warnings,
                        "results": [
                            {
                                "query": r.query,
                                "confidence": r.confidence,
                                "findings_count": len(r.findings),
                            }
                            for r in result.results
                        ],
                    },
                    indent=2,
                )
            )

            if console:
                console.print(f"\n[green]Results saved to {output}[/green]")
            else:
                click.echo(f"\nResults saved to {output}")

    except Exception as e:
        logger.error(f"Research failed: {e}", exc_info=True)
        if console:
            console.print(f"[red]Error: {e}[/red]")
        else:
            click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@research_cli.command(name="status")
@click.argument("phase_id", required=True)
def check_status(phase_id: str):
    """Check status of a research session.

    Example:
        autopack research status research_20240101_120000
    """
    console = Console() if RICH_AVAILABLE else None

    # This would query the research system for status
    # For now, show a placeholder
    if console:
        console.print(f"[bold]Research Phase: {phase_id}[/bold]")
        console.print("Status: [yellow]Not implemented[/yellow]")
    else:
        click.echo(f"Research Phase: {phase_id}")
        click.echo("Status: Not implemented")


@research_cli.command(name="list")
@click.option("--limit", default=10, help="Maximum number of sessions to show")
@click.option("--status", help="Filter by status")
def list_sessions(limit: int, status: Optional[str]):
    """List past research sessions.

    Example:
        autopack research list --limit 5
    """
    console = Console() if RICH_AVAILABLE else None

    # This would query the research system for past sessions
    # For now, show a placeholder
    if console:
        table = Table(title="Research Sessions")
        table.add_column("Phase ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Started", style="yellow")
        table.add_column("Duration", style="blue")

        # Placeholder data
        table.add_row("research_001", "completed", "2024-01-01 12:00", "45s")
        table.add_row("research_002", "in_progress", "2024-01-01 13:00", "30s")

        console.print(table)
    else:
        click.echo("Research Sessions:")
        click.echo("  research_001  completed    2024-01-01 12:00  45s")
        click.echo("  research_002  in_progress  2024-01-01 13:00  30s")


# Compatibility alias for tests
list_phases = list_sessions


@research_cli.command(name="export")
@click.argument("phase_id", required=True)
@click.option("--format", type=click.Choice(["json", "markdown"]), default="json")
@click.option("--output", type=click.Path(), help="Output file")
def export_results(phase_id: str, format: str, output: Optional[str]):
    """Export research results.

    Example:
        autopack research export research_001 --format markdown --output results.md
    """
    console = Console() if RICH_AVAILABLE else None

    # This would export results from the research system
    # For now, show a placeholder
    if console:
        console.print(f"[bold]Exporting {phase_id} as {format}...[/bold]")
        console.print("[yellow]Not implemented[/yellow]")
    else:
        click.echo(f"Exporting {phase_id} as {format}...")
        click.echo("Not implemented")


def _display_results_rich(console: Console, result: Any) -> None:
    """Display results using rich formatting."""
    from autopack.phases.research_phase import ResearchStatus

    # Status panel
    status_color = "green" if result.status == ResearchStatus.COMPLETED else "red"
    console.print(
        Panel(
            f"[{status_color}]{result.status.value.upper()}[/{status_color}]\n"
            f"Duration: {result.duration_seconds:.1f}s\n"
            f"Confidence: {result.average_confidence:.1%}",
            title="Research Status",
            border_style=status_color,
        )
    )

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(result.summary)

    # Recommendations
    if result.recommendations:
        console.print("\n[bold green]Recommendations:[/bold green]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")

    # Warnings
    if result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for warning in result.warnings:
            console.print(f"  ⚠ {warning}")

    # Results table
    if result.results:
        console.print("\n[bold]Results:[/bold]")
        table = Table()
        table.add_column("Query", style="cyan")
        table.add_column("Findings", style="green")
        table.add_column("Confidence", style="yellow")

        for r in result.results:
            table.add_row(
                r.query[:50] + "..." if len(r.query) > 50 else r.query,
                str(len(r.findings)),
                f"{r.confidence:.1%}",
            )

        console.print(table)


def _display_results_plain(result: Any) -> None:
    """Display results using plain text."""
    click.echo(f"\nStatus: {result.status.value}")
    click.echo(f"Duration: {result.duration_seconds:.1f}s")
    click.echo(f"Confidence: {result.average_confidence:.1%}")

    click.echo("\nSummary:")
    click.echo(result.summary)

    if result.recommendations:
        click.echo("\nRecommendations:")
        for rec in result.recommendations:
            click.echo(f"  • {rec}")

    if result.warnings:
        click.echo("\nWarnings:")
        for warning in result.warnings:
            click.echo(f"  ⚠ {warning}")

    if result.results:
        click.echo("\nResults:")
        for r in result.results:
            click.echo(f"  Query: {r.query}")
            click.echo(f"  Findings: {len(r.findings)}")
            click.echo(f"  Confidence: {r.confidence:.1%}")
            click.echo()
