"""IMP-AUTOPILOT-002: CLI for autopilot approval workflow.

Provides command-line interface for reviewing and approving autopilot proposals.

Usage:
    python -m autopack.autonomy.approval_cli list --run-id <run_id>
    python -m autopack.autonomy.approval_cli approve --run-id <run_id> --action-id <id>
    python -m autopack.autonomy.approval_cli reject --run-id <run_id> --action-id <id>
    python -m autopack.autonomy.approval_cli bulk-approve --run-id <run_id> --all
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .approval_service import ApprovalService

console = Console()


def list_pending_approvals(
    run_id: str, project_id: str, workspace_root: Path, include_blocked: bool = False
) -> None:
    """List pending approval requests.

    Args:
        run_id: Run identifier
        project_id: Project identifier
        workspace_root: Workspace root directory
        include_blocked: If True, include blocked actions
    """
    service = ApprovalService(run_id, project_id, workspace_root)
    pending = service.get_pending_approvals(include_blocked=include_blocked)
    stats = service.get_statistics()

    if not pending:
        console.print("[green]✓[/green] No pending approval requests")
        console.print(
            f"\nStatistics: {stats['approved']} approved, {stats['rejected']} rejected, "
            f"{stats['deferred']} deferred"
        )
        return

    # Display statistics panel
    stats_text = Text()
    stats_text.append(f"Pending: {stats['pending']} ", style="bold yellow")
    stats_text.append(f"(Requires approval: {stats['requires_approval']}, ", style="dim")
    stats_text.append(f"Blocked: {stats['blocked']})\n", style="dim")
    stats_text.append(f"Approved: {stats['approved']} ", style="bold green")
    stats_text.append(f"Rejected: {stats['rejected']} ", style="bold red")
    stats_text.append(f"Deferred: {stats['deferred']}", style="bold blue")

    console.print(
        Panel(stats_text, title=f"[bold]Approval Queue for Run: {run_id}[/bold]", expand=False)
    )
    console.print()

    # Display pending approvals table
    table = Table(title="Pending Approval Requests", show_header=True, header_style="bold magenta")
    table.add_column("Action ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="yellow")
    table.add_column("Type", style="blue")
    table.add_column("Reason", style="white")
    table.add_column("Session", style="dim")

    for approval in pending:
        status_color = "red" if approval.approval_status == "blocked" else "yellow"
        table.add_row(
            approval.action_id[:16],
            f"[{status_color}]{approval.approval_status}[/{status_color}]",
            approval.action_type or "unknown",
            approval.reason[:60] + ("..." if len(approval.reason) > 60 else ""),
            approval.session_id[:12],
        )

    console.print(table)

    # Display helpful commands
    console.print("\n[dim]Commands:[/dim]")
    console.print(
        "  Approve action:  [cyan]approval_cli approve --run-id <id> --action-id <action_id>[/cyan]"
    )
    console.print(
        "  Reject action:   [cyan]approval_cli reject --run-id <id> --action-id <action_id>[/cyan]"
    )
    console.print("  Approve all:     [cyan]approval_cli bulk-approve --run-id <id> --all[/cyan]")


def approve_action(
    run_id: str,
    project_id: str,
    workspace_root: Path,
    action_id: str,
    decided_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Approve a pending action.

    Args:
        run_id: Run identifier
        project_id: Project identifier
        workspace_root: Workspace root directory
        action_id: Action ID to approve
        decided_by: Optional approver identifier
        notes: Optional approval notes
    """
    service = ApprovalService(run_id, project_id, workspace_root)

    if service.record_decision(action_id, "approve", decided_by, notes):
        console.print(f"[green]✓[/green] Approved action: {action_id}")
        if notes:
            console.print(f"  Notes: {notes}")
    else:
        console.print(f"[red]✗[/red] Action not found: {action_id}", style="red")
        sys.exit(1)


def reject_action(
    run_id: str,
    project_id: str,
    workspace_root: Path,
    action_id: str,
    decided_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Reject a pending action.

    Args:
        run_id: Run identifier
        project_id: Project identifier
        workspace_root: Workspace root directory
        action_id: Action ID to reject
        decided_by: Optional approver identifier
        notes: Optional rejection notes
    """
    service = ApprovalService(run_id, project_id, workspace_root)

    if service.record_decision(action_id, "reject", decided_by, notes):
        console.print(f"[yellow]✓[/yellow] Rejected action: {action_id}")
        if notes:
            console.print(f"  Reason: {notes}")
    else:
        console.print(f"[red]✗[/red] Action not found: {action_id}", style="red")
        sys.exit(1)


def bulk_approve_actions(
    run_id: str,
    project_id: str,
    workspace_root: Path,
    approve_all: bool = False,
    action_ids: Optional[list] = None,
    decided_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Approve multiple actions at once.

    Args:
        run_id: Run identifier
        project_id: Project identifier
        workspace_root: Workspace root directory
        approve_all: If True, approve all pending actions
        action_ids: List of action IDs to approve (if not approve_all)
        decided_by: Optional approver identifier
        notes: Optional approval notes
    """
    service = ApprovalService(run_id, project_id, workspace_root)

    if approve_all:
        pending = service.get_pending_approvals(include_blocked=False)
        action_ids = [p.action_id for p in pending]

        if not action_ids:
            console.print("[yellow]No pending approvals to approve[/yellow]")
            return

        # Confirm bulk approval
        console.print(f"[yellow]⚠[/yellow]  About to approve {len(action_ids)} actions:")
        for action_id in action_ids[:5]:
            console.print(f"  - {action_id}")
        if len(action_ids) > 5:
            console.print(f"  ... and {len(action_ids) - 5} more")

        confirm = console.input("\n[bold]Proceed with bulk approval? (yes/no):[/bold] ")
        if confirm.lower() not in ["yes", "y"]:
            console.print("[yellow]Cancelled[/yellow]")
            return

    if not action_ids:
        console.print("[red]No action IDs provided[/red]")
        sys.exit(1)

    approved = service.bulk_approve(action_ids, decided_by, notes)
    console.print(f"[green]✓[/green] Bulk approved {approved}/{len(action_ids)} actions")


def bulk_reject_actions(
    run_id: str,
    project_id: str,
    workspace_root: Path,
    reject_all: bool = False,
    action_ids: Optional[list] = None,
    decided_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Reject multiple actions at once.

    Args:
        run_id: Run identifier
        project_id: Project identifier
        workspace_root: Workspace root directory
        reject_all: If True, reject all pending actions
        action_ids: List of action IDs to reject (if not reject_all)
        decided_by: Optional approver identifier
        notes: Optional rejection notes
    """
    service = ApprovalService(run_id, project_id, workspace_root)

    if reject_all:
        pending = service.get_pending_approvals(include_blocked=False)
        action_ids = [p.action_id for p in pending]

        if not action_ids:
            console.print("[yellow]No pending approvals to reject[/yellow]")
            return

    if not action_ids:
        console.print("[red]No action IDs provided[/red]")
        sys.exit(1)

    rejected = service.bulk_reject(action_ids, decided_by, notes)
    console.print(f"[yellow]✓[/yellow] Bulk rejected {rejected}/{len(action_ids)} actions")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="IMP-AUTOPILOT-002: Autopilot approval workflow CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="Run identifier",
    )
    parser.add_argument(
        "--project-id",
        default="autopack",
        help="Project identifier (default: autopack)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root directory (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Command")

    # List command
    list_parser = subparsers.add_parser("list", help="List pending approval requests")
    list_parser.add_argument(
        "--include-blocked",
        action="store_true",
        help="Include blocked actions in listing",
    )

    # Approve command
    approve_parser = subparsers.add_parser("approve", help="Approve a pending action")
    approve_parser.add_argument("--action-id", required=True, help="Action ID to approve")
    approve_parser.add_argument("--decided-by", help="Approver identifier")
    approve_parser.add_argument("--notes", help="Approval notes")

    # Reject command
    reject_parser = subparsers.add_parser("reject", help="Reject a pending action")
    reject_parser.add_argument("--action-id", required=True, help="Action ID to reject")
    reject_parser.add_argument("--decided-by", help="Approver identifier")
    reject_parser.add_argument("--notes", help="Rejection reason")

    # Bulk approve command
    bulk_approve_parser = subparsers.add_parser("bulk-approve", help="Approve multiple actions")
    bulk_approve_parser.add_argument(
        "--all",
        action="store_true",
        dest="approve_all",
        help="Approve all pending actions",
    )
    bulk_approve_parser.add_argument(
        "--action-ids",
        nargs="+",
        help="List of action IDs to approve",
    )
    bulk_approve_parser.add_argument("--decided-by", help="Approver identifier")
    bulk_approve_parser.add_argument("--notes", help="Approval notes")

    # Bulk reject command
    bulk_reject_parser = subparsers.add_parser("bulk-reject", help="Reject multiple actions")
    bulk_reject_parser.add_argument(
        "--all",
        action="store_true",
        dest="reject_all",
        help="Reject all pending actions",
    )
    bulk_reject_parser.add_argument(
        "--action-ids",
        nargs="+",
        help="List of action IDs to reject",
    )
    bulk_reject_parser.add_argument("--decided-by", help="Approver identifier")
    bulk_reject_parser.add_argument("--notes", help="Rejection reason")

    args = parser.parse_args()

    # Execute command
    workspace = args.workspace.resolve()

    if args.command == "list":
        list_pending_approvals(args.run_id, args.project_id, workspace, args.include_blocked)
    elif args.command == "approve":
        approve_action(
            args.run_id,
            args.project_id,
            workspace,
            args.action_id,
            args.decided_by,
            args.notes,
        )
    elif args.command == "reject":
        reject_action(
            args.run_id,
            args.project_id,
            workspace,
            args.action_id,
            args.decided_by,
            args.notes,
        )
    elif args.command == "bulk-approve":
        bulk_approve_actions(
            args.run_id,
            args.project_id,
            workspace,
            args.approve_all,
            args.action_ids,
            args.decided_by,
            args.notes,
        )
    elif args.command == "bulk-reject":
        bulk_reject_actions(
            args.run_id,
            args.project_id,
            workspace,
            args.reject_all,
            args.action_ids,
            args.decided_by,
            args.notes,
        )


if __name__ == "__main__":
    main()
