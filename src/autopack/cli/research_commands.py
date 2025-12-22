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
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from autopack.research.orchestrator import ResearchOrchestrator
from autopack.research.models.research_intent import ResearchIntent
from autopack.research.models.enums import ResearchPriority
from autopack.database import SessionLocal

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="research")
def research_group():
    """Research system commands."""
    pass


@research_group.command(name="start")
@click.argument("query", type=str)
@click.option(
    "--priority",
    type=click.Choice(["low", "medium", "high", "critical"], case_sensitive=False),
    default="medium",
    help="Research priority level",
)
@click.option(
    "--max-iterations",
    type=int,
    default=5,
    help="Maximum research iterations",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output file for research results (JSON)",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose output",
)
def research_start(
    query: str,
    priority: str,
    max_iterations: int,
    output: Optional[str],
    verbose: bool,
):
    """Start a new research session.

    QUERY: Research question or topic to investigate
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    console.print(Panel.fit(
        f"[bold cyan]Starting Research Session[/bold cyan]\n\n"
        f"Query: {query}\n"
        f"Priority: {priority.upper()}\n"
        f"Max Iterations: {max_iterations}",
        border_style="cyan"
    ))

    try:
        project_root = Path.cwd()
        db_session = SessionLocal()

        orchestrator = ResearchOrchestrator(
            project_root=project_root,
            db_session=db_session,
            max_iterations=max_iterations,
        )

        # Create research intent
        intent = ResearchIntent(
            query=query,
            priority=ResearchPriority[priority.upper()],
            context={"cli_initiated": True},
        )

        # Execute research with progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Conducting research...", total=None)
            session = orchestrator.conduct_research(intent)
            progress.update(task, completed=True)

        # Display results
        console.print("\n[bold green]✓ Research Complete[/bold green]\n")
        console.print(f"Session ID: [cyan]{session.session_id}[/cyan]")
        console.print(f"Evidence Collected: [yellow]{len(session.evidence)}[/yellow]")
        console.print(f"Insights Generated: [yellow]{len(session.insights)}[/yellow]")
        console.print(f"Quality Score: [yellow]{session.quality_score:.2f}[/yellow]")

        # Export if requested
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(session.to_dict(), indent=2),
                encoding="utf-8"
            )
            console.print(f"\n[green]Results exported to:[/green] {output_path}")

        db_session.close()

    except Exception as e:
        console.print(f"[bold red]✗ Research failed:[/bold red] {e}")
        logger.exception("Research session failed")
        raise click.Abort()


@research_group.command(name="status")
@click.argument("session_id", type=str)
@click.option(
    "--verbose",
    is_flag=True,
    help="Show detailed status information",
)
def research_status(session_id: str, verbose: bool):
    """Check status of a research session.

    SESSION_ID: ID of the research session to check
    """
    try:
        project_root = Path.cwd()
        research_dir = project_root / ".autonomous_runs" / "research"
        session_file = research_dir / f"{session_id}.json"

        if not session_file.exists():
            console.print(f"[red]Session not found:[/red] {session_id}")
            raise click.Abort()

        session_data = json.loads(session_file.read_text(encoding="utf-8"))

        # Display status
        console.print(Panel.fit(
            f"[bold cyan]Research Session Status[/bold cyan]\n\n"
            f"Session ID: {session_id}\n"
            f"State: {session_data.get('state', 'unknown')}\n"
            f"Created: {session_data.get('created_at', 'unknown')}\n"
            f"Updated: {session_data.get('updated_at', 'unknown')}",
            border_style="cyan"
        ))

        if verbose:
            # Show goals
            goals = session_data.get("goals", [])
            if goals:
                console.print("\n[bold]Research Goals:[/bold]")
                for goal in goals:
                    status_icon = "✓" if goal.get("status") == "achieved" else "○"
                    console.print(f"  {status_icon} {goal.get('description', 'N/A')}")

            # Show evidence summary
            evidence = session_data.get("evidence", [])
            if evidence:
                console.print(f"\n[bold]Evidence:[/bold] {len(evidence)} items collected")

            # Show insights
            insights = session_data.get("insights", [])
            if insights:
                console.print(f"\n[bold]Insights:[/bold] {len(insights)} generated")

    except Exception as e:
        console.print(f"[bold red]✗ Failed to get status:[/bold red] {e}")
        logger.exception("Failed to get research status")
        raise click.Abort()


@research_group.command(name="export")
@click.argument("session_id", type=str)
@click.argument("output_path", type=click.Path())
@click.option(
    "--format",
    type=click.Choice(["json", "markdown"], case_sensitive=False),
    default="json",
    help="Export format",
)
def research_export(session_id: str, output_path: str, format: str):
    """Export research session results.

    SESSION_ID: ID of the research session to export
    OUTPUT_PATH: Path to write exported results
    """
    try:
        project_root = Path.cwd()
        research_dir = project_root / ".autonomous_runs" / "research"
        session_file = research_dir / f"{session_id}.json"

        if not session_file.exists():
            console.print(f"[red]Session not found:[/red] {session_id}")
            raise click.Abort()

        session_data = json.loads(session_file.read_text(encoding="utf-8"))
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            output.write_text(
                json.dumps(session_data, indent=2),
                encoding="utf-8"
            )
        elif format == "markdown":
            # Generate markdown report
            md_content = _generate_markdown_report(session_data)
            output.write_text(md_content, encoding="utf-8")

        console.print(f"[green]✓ Exported to:[/green] {output}")

    except Exception as e:
        console.print(f"[bold red]✗ Export failed:[/bold red] {e}")
        logger.exception("Failed to export research session")
        raise click.Abort()


@research_group.command(name="list")
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of sessions to list",
)
@click.option(
    "--state",
    type=str,
    help="Filter by session state",
)
def research_list(limit: int, state: Optional[str]):
    """List recent research sessions."""
    try:
        project_root = Path.cwd()
        research_dir = project_root / ".autonomous_runs" / "research"

        if not research_dir.exists():
            console.print("[yellow]No research sessions found[/yellow]")
            return

        # Find all session files
        session_files = sorted(
            research_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        if not session_files:
            console.print("[yellow]No research sessions found[/yellow]")
            return

        # Create table
        table = Table(title="Research Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("State", style="yellow")
        table.add_column("Evidence", justify="right")
        table.add_column("Insights", justify="right")
        table.add_column("Quality", justify="right")
        table.add_column("Created", style="dim")

        for session_file in session_files:
            session_data = json.loads(session_file.read_text(encoding="utf-8"))
            session_state = session_data.get("state", "unknown")

            # Apply state filter
            if state and session_state != state:
                continue

            table.add_row(
                session_data.get("session_id", "unknown"),
                session_state,
                str(len(session_data.get("evidence", []))),
                str(len(session_data.get("insights", []))),
                f"{session_data.get('quality_score', 0.0):.2f}",
                session_data.get("created_at", "unknown")[:19],
            )

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]✗ Failed to list sessions:[/bold red] {e}")
        logger.exception("Failed to list research sessions")
        raise click.Abort()


def _generate_markdown_report(session_data: dict) -> str:
    """Generate markdown report from session data."""
    lines = [
        f"# Research Session: {session_data.get('session_id', 'Unknown')}",
        "",
        f"**State**: {session_data.get('state', 'unknown')}",
        f"**Created**: {session_data.get('created_at', 'unknown')}",
        f"**Quality Score**: {session_data.get('quality_score', 0.0):.2f}",
        "",
        "## Research Goals",
        "",
    ]

    for goal in session_data.get("goals", []):
        status = "✓" if goal.get("status") == "achieved" else "○"
        lines.append(f"- {status} {goal.get('description', 'N/A')}")

    lines.extend([
        "",
        "## Evidence Collected",
        "",
    ])

    for evidence in session_data.get("evidence", []):
        lines.append(f"### {evidence.get('source_type', 'unknown')}")
        lines.append(f"**Relevance**: {evidence.get('relevance_score', 0.0):.2f}")
        lines.append(f"**Confidence**: {evidence.get('confidence', 0.0):.2f}")
        lines.append("")
        lines.append(evidence.get("content", "N/A")[:200] + "...")
        lines.append("")

    lines.extend([
        "## Insights",
        "",
    ])

    for insight in session_data.get("insights", []):
        lines.append(f"### {insight.get('insight_type', 'unknown')}")
        lines.append(f"**Confidence**: {insight.get('confidence', 0.0):.2f}")
        lines.append("")
        lines.append(insight.get("description", "N/A"))
        if insight.get("recommendation"):
            lines.append("")
            lines.append(f"**Recommendation**: {insight.get('recommendation')}")
        lines.append("")

    return "\n".join(lines)
