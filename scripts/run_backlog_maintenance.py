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
from autopack.maintenance_auditor import AuditorInput, AuditorDecision, DiffStats, TestResult, evaluate as audit_evaluate
from autopack.memory import MemoryService
from autopack.governed_apply import GovernedApplyPath


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
    parser.add_argument("--apply", action="store_true", help="Attempt apply using patches from --patch-dir if auditor approves")
    parser.add_argument("--patch-dir", type=Path, default=None, help="Directory containing patches named <item_id>.patch")
    parser.add_argument("--default-allowed-path", action="append", default=[], help="Additional default allowed path prefixes")
    parser.add_argument("--max-files", type=int, default=10, help="Max files allowed in a patch for auto-approval")
    parser.add_argument("--max-lines", type=int, default=500, help="Max lines added+deleted for auto-approval")
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

    default_allowed = args.allowed_path or []
    if args.default_allowed_path:
        default_allowed.extend(args.default_allowed_path)
    protected_paths = ["config/", ".autonomous_runs/", ".git/"]
    if not default_allowed:
        default_allowed = [
            "src/backend/",
            "src/frontend/",
            "Dockerfile",
            "docker-compose",
            "README",
            "docs/",
            "scripts/",
            "src/",
        ]

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
        patch_path = None
        if args.patch_dir:
            candidate = args.patch_dir / f"{item.id}.patch"
            if candidate.exists():
                patch_path = candidate

        diff_stats = DiffStats(files_changed=[], lines_added=0, lines_deleted=0)
        if patch_path:
            raw = patch_path.read_text(encoding="utf-8", errors="ignore")
            files = set()
            added = deleted = 0
            for line in raw.splitlines():
                if line.startswith("+++ b/"):
                    files.add(line[6:])
                elif line.startswith("--- a/"):
                    files.add(line[6:])
                elif line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deleted += 1
            diff_stats = DiffStats(files_changed=sorted(files), lines_added=added, lines_deleted=deleted)

        auditor_input = AuditorInput(
            allowed_paths=default_allowed,
            protected_paths=protected_paths,
            diff=diff_stats,
            tests=[],  # targeted tests not provided here
            failure_class="maintenance",
            item_context=item.summary.lower() if item.summary else "",
            diagnostics_summary=outcome.ledger_summary,
            max_files=args.max_files,
            max_lines=args.max_lines,
        )
        decision: AuditorDecision = audit_evaluate(auditor_input)
        verdict = decision.verdict
        print(f"[Auditor] {item.id}: verdict={verdict} reasons={decision.reasons}")

        if memory and memory.enabled:
            try:
                memory.write_decision_log(
                    trigger="backlog_maintenance",
                    choice=f"diagnostics:{item.id}",
                    rationale=outcome.ledger_summary,
                    project_id=run_id,
                    run_id=run_id,
                    phase_id=item.id,
                    alternatives="approve,require_human,reject",
                )
            except Exception:
                pass

        apply_result = None
        if args.apply and patch_path and verdict == "approve":
            if not args.checkpoint:
                print(f"[Apply] Skipped {item.id}: checkpoint required for apply")
            else:
                print(f"[Apply] Applying patch for {item.id} from {patch_path}")
                applier = GovernedApplyPath(
                    workspace=workspace,
                    allowed_paths=default_allowed,
                    protected_paths=protected_paths,
                    run_type="project_build",
                )
                success, err = applier.apply_patch(patch_path.read_text(encoding="utf-8", errors="ignore"))
                apply_result = {"success": success, "error": err}
                if success:
                    print(f"[Apply] Success for {item.id}")
                else:
                    print(f"[Apply] Failed for {item.id}: {err}")
        elif args.apply and not patch_path:
            print(f"[Apply] No patch found for {item.id}, skipping apply")
        elif args.apply and verdict != "approve":
            print(f"[Apply] Skipped {item.id}: auditor verdict {verdict}")

        summaries.append(
            {
                "phase_id": item.id,
                "ledger": outcome.ledger_summary,
                "artifacts": outcome.artifacts,
                "budget_exhausted": outcome.budget_exhausted,
                "checkpoint": checkpoint_hash if args.checkpoint else None,
                "auditor_verdict": verdict,
                "auditor_reasons": decision.reasons,
                "apply_result": apply_result,
                "patch_path": str(patch_path) if patch_path else None,
            }
        )

    diag_dir = Path(".autonomous_runs") / run_id / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    summary_path = diag_dir / "backlog_diagnostics_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"[OK] Diagnostics summaries -> {summary_path}")


if __name__ == "__main__":
    main()

