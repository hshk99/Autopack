#!/usr/bin/env python3
"""
End-to-end backlog maintenance runner (propose-first, no apply).

Steps:
1) Parse backlog markdown (e.g., consolidated_debug.md) into a maintenance plan.
2) Run diagnostics over each plan item (no apply), storing artifacts under
   .autonomous_runs/<run_id>/diagnostics.
"""

import argparse
import time
from pathlib import Path

from autopack.backlog_maintenance import (
    backlog_items_to_phases,
    parse_backlog_markdown,
    write_plan,
    create_git_checkpoint,
)
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.memory import MemoryService


def main():
    parser = argparse.ArgumentParser(description="Run propose-first backlog maintenance diagnostics.")
    parser.add_argument("--backlog", type=Path, required=True, help="Path to backlog markdown (e.g., consolidated_debug.md)")
    parser.add_argument("--run-id", type=str, default=None, help="Run ID for diagnostics artifacts")
    parser.add_argument("--allowed-path", action="append", default=[], help="Allowed path prefix to scope patches")
    parser.add_argument("--max-items", type=int, default=10, help="Max backlog items to include")
    parser.add_argument("--max-commands", type=int, default=20, help="Per-item command budget")
    parser.add_argument("--max-seconds", type=int, default=600, help="Per-item time budget (seconds)")
    parser.add_argument("--workspace", type=Path, default=Path("."), help="Workspace root")
    parser.add_argument("--checkpoint", action="store_true", help="Create a git checkpoint before running diagnostics")
    args = parser.parse_args()

    run_id = args.run_id or f"backlog-maintenance-{int(time.time())}"
    workspace = args.workspace.resolve()

    items = parse_backlog_markdown(args.backlog, max_items=args.max_items)
    plan = backlog_items_to_phases(
        items,
        default_allowed_paths=args.allowed_path or [],
        max_commands=args.max_commands,
        max_seconds=args.max_seconds,
    )

    plan_path = Path(".autonomous_runs") / run_id / "backlog_plan.json"
    write_plan(plan, plan_path)
    print(f"[Plan] wrote {plan_path} with {len(items)} items")

    try:
        memory = MemoryService()
    except Exception:
        memory = None

    agent = DiagnosticsAgent(
        run_id=run_id,
        workspace=workspace,
        memory_service=memory,
        decision_logger=None,
        diagnostics_dir=Path(".autonomous_runs") / run_id / "diagnostics",
        max_probes=6,
        max_seconds=args.max_seconds,
    )

    checkpoint_hash = None
    if args.checkpoint:
        ok, checkpoint_hash = create_git_checkpoint(workspace, message=f"[Autopack] Backlog checkpoint {run_id}")
        if ok:
            print(f"[Checkpoint] Created at {checkpoint_hash}")
        else:
            print(f"[Checkpoint] Failed: {checkpoint_hash}")

    summaries = []
    for item in items:
        print(f"[Diagnostics] {item.id}: {item.title}")
        outcome = agent.run_diagnostics(
            failure_class="maintenance",
            context={"phase_id": item.id, "description": item.title, "backlog_summary": item.summary},
            phase_id=item.id,
        )
        if memory and memory.enabled:
            try:
                memory.write_decision_log(
                    trigger="backlog_maintenance",
                    choice=f"diagnostics:{item.id}",
                    rationale=outcome.ledger_summary,
                    project_id=run_id,
                    run_id=run_id,
                    phase_id=item.id,
                )
            except Exception:
                pass
        summaries.append(
            {
                "phase_id": item.id,
                "ledger": outcome.ledger_summary,
                "artifacts": outcome.artifacts,
                "budget_exhausted": outcome.budget_exhausted,
                "checkpoint": checkpoint_hash if args.checkpoint else None,
            }
        )

    diag_dir = Path(".autonomous_runs") / run_id / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    summary_path = diag_dir / "backlog_diagnostics_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"[OK] Diagnostics summaries -> {summary_path}")


if __name__ == "__main__":
    main()

