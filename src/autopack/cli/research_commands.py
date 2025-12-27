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
from typing import Any, Dict, List, Optional

import click

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.syntax import Syntax
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from ..phases.research_phase import (
        ResearchPhaseManager,
        ResearchPriority,
        ResearchQuery,
        ResearchStatus,
    )
    from ..autonomous.research_hooks import ResearchHooks, ResearchTriggerConfig
    from ..integrations.build_history_integrator import BuildHistoryIntegrator
    RESEARCH_AVAILABLE = True
except ImportError:
    RESEARCH_AVAILABLE = False

logger = logging.getLogger(__name__)


@click.group(name="research")
def research_cli():
    """Research system commands."""
    if not RESEARCH_AVAILABLE:
        click.echo("Error: Research system not available", err=True)
        raise click.Abort()


@research_cli.command(name="start")
@click.argument("description")
@click.option(
    "--category",
    default="GENERAL",
    help="Task category for research",
)
@click.option(
    "--priority",
    type=click.Choice(["low", "medium", "high", "critical"]),
    default="medium",
    help="Research priority",
)
@click.option(
    "--query",
    multiple=True,
    help="Additional research queries (can be specified multiple times)",
)
@click.option(
    "--auto",
    is_flag=True,
    help="Auto-generate queries from description",
)
def start_research(
    description: str,
    category: str,
    priority: str,
    query: tuple,
    auto: bool,
):
    """Start a new research session."""
    console = Console() if RICH_AVAILABLE else None
    
    try:
        manager = ResearchPhaseManager()
        
        # Build queries
        queries = []
        
        if auto:
            # Auto-generate queries
            queries.extend([
                ResearchQuery(
                    query_text=f"Best practices for {category}: {description}",
                ),
                ResearchQuery(
                    query_text=f"Common issues when {description}",
                ),
                ResearchQuery(
                    query_text=f"Implementation approaches for {description}",
                ),
            ])
        
        # Add custom queries
        for q in query:
            queries.append(ResearchQuery(query_text=q))
        
        if not queries:
            click.echo("Error: No queries specified. Use --auto or --query", err=True)
            raise click.Abort()
        
        # Create phase
        phase = manager.create_phase(
            title=f"Research: {description[:50]}",
            description=description,
            queries=queries,
            priority=ResearchPriority[priority.upper()],
            metadata={"category": category},
        )
        
        if console:
            console.print(Panel(
                f"[green]Research phase created: {phase.phase_id}[/green]\n\n"
                f"Title: {phase.title}\n"
                f"Priority: {phase.priority.value}\n"
                f"Queries: {len(phase.queries)}",
                title="Research Started",
            ))
        else:
            click.echo(f"Research phase created: {phase.phase_id}")
            click.echo(f"Title: {phase.title}")
            click.echo(f"Priority: {phase.priority.value}")
            click.echo(f"Queries: {len(phase.queries)}")
        
    except Exception as e:
        click.echo(f"Error starting research: {e}", err=True)
        raise click.Abort()


@research_cli.command(name="status")
@click.argument("phase_id", required=False)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show all phases",
)
@click.option(
    "--filter-status",
    type=click.Choice(["pending", "in_progress", "completed", "failed", "cancelled"]),
    help="Filter by status",
)
def check_status(phase_id: Optional[str], show_all: bool, filter_status: Optional[str]):
    """Check research phase status."""
    console = Console() if RICH_AVAILABLE else None
    
    try:
        manager = ResearchPhaseManager()
        
        if phase_id:
            # Show specific phase
            phase = manager.get_phase(phase_id)
            if not phase:
                click.echo(f"Phase not found: {phase_id}", err=True)
                raise click.Abort()
            
            _display_phase_details(phase, console)
        
        else:
            # List phases
            status_filter = ResearchStatus[filter_status.upper()] if filter_status else None
            phases = manager.list_phases(status=status_filter)
            
            if not phases:
                click.echo("No research phases found")
                return
            
            if not show_all:
                phases = phases[:10]  # Limit to 10 most recent
            
            _display_phase_list(phases, console)
    
    except Exception as e:
        click.echo(f"Error checking status: {e}", err=True)
        raise click.Abort()


@research_cli.command(name="export")
@click.argument("phase_id")
@click.option(
    "--output",
    type=click.Path(),
    help="Output file path (default: stdout)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    help="Output format",
)
def export_results(phase_id: str, output: Optional[str], output_format: str):
    """Export research results."""
    try:
        manager = ResearchPhaseManager()
        phase = manager.get_phase(phase_id)
        
        if not phase:
            click.echo(f"Phase not found: {phase_id}", err=True)
            raise click.Abort()
        
        if output_format == "json":
            content = json.dumps(phase.to_dict(), indent=2)
        else:
            content = _format_as_markdown(phase)
        
        if output:
            Path(output).write_text(content)
            click.echo(f"Results exported to: {output}")
        else:
            click.echo(content)
    
    except Exception as e:
        click.echo(f"Error exporting results: {e}", err=True)
        raise click.Abort()


@research_cli.command(name="analyze")
@click.option(
    "--category",
    help="Analyze specific task category",
)
@click.option(
    "--threshold",
    type=float,
    default=0.7,
    help="Success rate threshold for recommendations",
)
def analyze_history(category: Optional[str], threshold: float):
    """Analyze build history for research insights."""
    console = Console() if RICH_AVAILABLE else None
    
    try:
        integrator = BuildHistoryIntegrator()
        insights = integrator.extract_insights(
            task_category=category,
            force_refresh=True,
        )
        
        if console:
            # Display with rich formatting
            console.print("\n[bold]Build History Analysis[/bold]\n")
            
            # Success rates
            if insights.success_rate:
                table = Table(title="Success Rates by Category")
                table.add_column("Category", style="cyan")
                table.add_column("Success Rate", style="green")
                table.add_column("Status", style="yellow")
                
                for cat, rate in insights.success_rate.items():
                    status = "✓ Good" if rate >= threshold else "⚠ Low"
                    table.add_row(cat, f"{rate:.1%}", status)
                
                console.print(table)
                console.print()
            
            # Common issues
            if insights.common_issues:
                console.print("[bold]Common Issues:[/bold]")
                for issue in insights.common_issues:
                    console.print(f"  • {issue}")
                console.print()
            
            # Recommendations
            if insights.recommended_approaches:
                console.print("[bold]Recommendations:[/bold]")
                for rec in insights.recommended_approaches:
                    console.print(f"  • {rec}")
                console.print()
        
        else:
            # Plain text output
            click.echo("\nBuild History Analysis\n")
            
            if insights.success_rate:
                click.echo("Success Rates:")
                for cat, rate in insights.success_rate.items():
                    status = "Good" if rate >= threshold else "Low"
                    click.echo(f"  {cat}: {rate:.1%} ({status})")
                click.echo()
            
            if insights.common_issues:
                click.echo("Common Issues:")
                for issue in insights.common_issues:
                    click.echo(f"  - {issue}")
                click.echo()
            
            if insights.recommended_approaches:
                click.echo("Recommendations:")
                for rec in insights.recommended_approaches:
                    click.echo(f"  - {rec}")
                click.echo()
    
    except Exception as e:
        click.echo(f"Error analyzing history: {e}", err=True)
        raise click.Abort()


def _display_phase_details(phase, console):
    """Display detailed information about a phase."""
    if console:
        console.print(Panel(
            f"[bold]{phase.title}[/bold]\n\n"
            f"ID: {phase.phase_id}\n"
            f"Status: {phase.status.value}\n"
            f"Priority: {phase.priority.value}\n"
            f"Created: {phase.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Queries: {len(phase.queries)}\n"
            f"Results: {len(phase.results)}",
            title="Research Phase Details",
        ))
        
        if phase.results:
            console.print("\n[bold]Results:[/bold]\n")
            for i, result in enumerate(phase.results, 1):
                console.print(f"[cyan]{i}. {result.query.query_text}[/cyan]")
                console.print(f"   Summary: {result.summary[:100]}...")
                console.print(f"   Confidence: {result.confidence:.1%}")
                console.print(f"   Sources: {len(result.sources)}\n")
    else:
        click.echo(f"\nPhase: {phase.title}")
        click.echo(f"ID: {phase.phase_id}")
        click.echo(f"Status: {phase.status.value}")
        click.echo(f"Priority: {phase.priority.value}")
        click.echo(f"Created: {phase.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"Queries: {len(phase.queries)}")
        click.echo(f"Results: {len(phase.results)}")
        
        if phase.results:
            click.echo("\nResults:")
            for i, result in enumerate(phase.results, 1):
                click.echo(f"{i}. {result.query.query_text}")
                click.echo(f"   Summary: {result.summary[:100]}...")
                click.echo(f"   Confidence: {result.confidence:.1%}")
                click.echo(f"   Sources: {len(result.sources)}")


def _display_phase_list(phases, console):
    """Display a list of phases."""
    if console:
        table = Table(title="Research Phases")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Status", style="yellow")
        table.add_column("Priority", style="magenta")
        table.add_column("Created", style="green")
        
        for phase in phases:
            table.add_row(
                phase.phase_id,
                phase.title[:40],
                phase.status.value,
                phase.priority.value,
                phase.created_at.strftime("%Y-%m-%d %H:%M"),
            )
        
        console.print(table)
    else:
        click.echo("\nResearch Phases:\n")
        for phase in phases:
            click.echo(
                f"{phase.phase_id} | {phase.title[:40]} | "
                f"{phase.status.value} | {phase.priority.value} | "
                f"{phase.created_at.strftime('%Y-%m-%d %H:%M')}"
            )


def _format_as_markdown(phase) -> str:
    """Format phase as markdown."""
    lines = [
        f"# Research Phase: {phase.title}",
        "",
        f"**ID:** {phase.phase_id}",
        f"**Status:** {phase.status.value}",
        f"**Priority:** {phase.priority.value}",
        f"**Created:** {phase.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Description",
        "",
        phase.description,
        "",
        "## Queries",
        "",
    ]
    
    for i, query in enumerate(phase.queries, 1):
        lines.append(f"{i}. {query.query_text}")
    
    if phase.results:
        lines.extend(["", "## Results", ""])
        
        for i, result in enumerate(phase.results, 1):
            lines.extend([
                f"### Result {i}: {result.query.query_text}",
                "",
                f"**Confidence:** {result.confidence:.1%}",
                f"**Sources:** {len(result.sources)}",
                "",
                "**Summary:**",
                "",
                result.summary,
                "",
            ])
            
            if result.findings:
                lines.extend(["**Findings:**", ""])
                for finding in result.findings:
                    lines.append(f"- {finding.get('title', 'N/A')}")
                lines.append("")
    
    return "\n".join(lines)
