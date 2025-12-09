#!/usr/bin/env python3
"""
Run diagnostics-only pass over a backlog maintenance plan (propose-first).

For each phase in the plan JSON, this:
- Instantiates a DiagnosticsAgent
- Runs diagnostics with failure_class="maintenance"
- Writes a summary JSON to the diagnostics directory

No patches are applied; this is read-only evidence collection.
"""

import argparse
import json
import time
from pathlib import Path

from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.memory import MemoryService


def load_plan(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Plan not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Run diagnostics over a backlog maintenance plan (propose-first).")
    parser.add_argument("--plan", type=Path, required=True, help="Path to plan JSON from backlog_maintenance script")
    parser.add_argument("--run-id", type=str, default=None, help="Run ID to use for diagnostics artifacts")
    parser.add_argument("--workspace", type=Path, default=Path("."), help="Workspace root")
    parser.add_argument("--max-probes", type=int, default=6, help="Max probes per item")
    parser.add_argument("--max-seconds", type=int, default=300, help="Max seconds per item")
    args = parser.parse_args()

    plan = load_plan(args.plan)
    phases = plan.get("phases", [])
    run_id = args.run_id or f"backlog-maintenance-{int(time.time())}"
    workspace = args.workspace.resolve()

    memory = None
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
        max_probes=args.max_probes,
        max_seconds=args.max_seconds,
    )

    summaries = []
    for phase in phases:
        phase_id = phase.get("id")
        print(f"[Diagnostics] {phase_id}: {phase.get('description')}")
        outcome = agent.run_diagnostics(
            failure_class="maintenance",
            context={
                "phase_id": phase_id,
                "description": phase.get("description"),
                "backlog_summary": phase.get("metadata", {}).get("backlog_summary"),
            },
            phase_id=phase_id,
        )
        summaries.append(
            {
                "phase_id": phase_id,
                "failure_class": "maintenance",
                "ledger": outcome.ledger_summary,
                "artifacts": outcome.artifacts,
                "budget_exhausted": outcome.budget_exhausted,
            }
        )

    out_dir = Path(".autonomous_runs") / run_id / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "backlog_diagnostics_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"[OK] Diagnostics complete. Summary -> {summary_path}")


if __name__ == "__main__":
    main()

