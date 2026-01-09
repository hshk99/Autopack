#!/usr/bin/env python3
"""
End-to-end backlog maintenance runner (propose-first, no apply).

Steps:
1) Parse backlog markdown (e.g., consolidated_debug.md) into a maintenance plan.
2) Run diagnostics over each plan item (no apply), storing artifacts under
   .autonomous_runs/<run_id>/diagnostics.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from autopack.backlog_maintenance import (
    backlog_items_to_phases,
    parse_backlog_markdown,
    write_plan,
    create_git_checkpoint,
    parse_patch_stats,
)
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.maintenance_auditor import AuditorInput, AuditorDecision, TestResult, evaluate as audit_evaluate
from autopack.memory import MemoryService
from autopack.governed_apply import GovernedApplyPath
from autopack.maintenance_runner import run_tests


def is_major_change(item, patch_path, auditor_decision):
    """
    Detect if this backlog item represents a major architectural change.

    Returns:
        (is_major: bool, rationale: str)
    """
    major_keywords = [
        "database", "migration", "postgresql", "qdrant", "vector", "memory",
        "architecture", "framework", "integration", "api", "authentication",
        "refactor", "redesign", "restructure"
    ]

    # Check item context for major keywords
    item_context = (item.summary or "").lower()
    if any(kw in item_context for kw in major_keywords):
        return True, f"Architectural change detected in context: {item.summary[:100]}"

    # Check if patch is large (>200 lines = significant change)
    if patch_path and patch_path.exists():
        lines = len(patch_path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if lines > 200:
            return True, f"Large patch ({lines} lines) indicates major change"

    # Check if auditor flagged as major
    if any("major" in str(r).lower() for r in auditor_decision.reasons):
        return True, "Auditor flagged as major change"

    return False, ""


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
    parser.add_argument("--test-cmd", action="append", default=[], help="Targeted test command(s) to run per item")
    parser.add_argument("--log-major-changes", action="store_true", help="Log major changes to PlanChange table for context awareness")
    parser.add_argument("--project-id", type=str, default="file-organizer-app-v1", help="Project ID for PlanChange logging")
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

    # Initialize MemoryService with proper configuration to ensure collections are created
    try:
        import yaml
        config_path = Path("config/memory.yaml")
        config = {}
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}

        use_qdrant = config.get("use_qdrant", False)
        memory = MemoryService(enabled=True, use_qdrant=use_qdrant)
        print(f"[Memory] Initialized with backend={memory.backend}")
    except Exception as e:
        print(f"[Memory] Failed to initialize: {e}")
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

    # Run workspace tests once before processing items (efficiency optimization)
    workspace_test_results = []
    test_output_cache = {}  # hash -> full test output
    if args.test_cmd:
        print(f"[Tests] Running workspace tests once: {args.test_cmd}")
        workspace_test_results = run_tests(args.test_cmd, workspace=workspace)
        # Cache test outputs by hash
        for test in workspace_test_results:
            test_dict = test.__dict__
            test_json = json.dumps(test_dict, sort_keys=True)
            test_hash = hashlib.sha256(test_json.encode()).hexdigest()[:12]
            test_output_cache[test_hash] = test_dict
        print(f"[Tests] Cached {len(test_output_cache)} unique test outputs")

    summaries = []
    for item in items:
        print(f"[Diagnostics] {item.id}: {item.title}")
        outcome = agent.run_diagnostics(
            failure_class="maintenance",
            context={"phase_id": item.id, "description": item.title, "backlog_summary": item.summary},
            phase_id=item.id,
            mode="maintenance",
        )
        patch_path = None
        if args.patch_dir:
            candidate = args.patch_dir / f"{item.id}.patch"
            if candidate.exists():
                patch_path = candidate

        # Parse patch stats if available, otherwise None (not empty DiffStats)
        diff_stats = None
        if patch_path:
            raw = patch_path.read_text(encoding="utf-8", errors="ignore")
            diff_stats = parse_patch_stats(raw)
            print(f"[Patch] Parsed {item.id}: {len(diff_stats.files_changed)} files, +{diff_stats.lines_added}/-{diff_stats.lines_deleted} lines")

        # Use workspace test results (run once, not per-item)
        test_results = workspace_test_results

        auditor_input = AuditorInput(
            allowed_paths=default_allowed,
            protected_paths=protected_paths,
            diff=diff_stats,
            tests=[TestResult(name=t.name, status=t.status) for t in test_results],
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
            except Exception as e:
                print(f"[Memory] Failed to write decision log for {item.id}: {e}")

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

        # Detect and log major changes to database
        if args.log_major_changes and verdict == "approve":
            is_major, major_rationale = is_major_change(item, patch_path, decision)
            if is_major:
                try:
                    from autopack.models import PlanChange
                    from autopack.database import SessionLocal
                    from datetime import datetime, timezone

                    session = SessionLocal()
                    plan_change = PlanChange(
                        run_id=run_id,
                        phase_id=item.id,
                        project_id=args.project_id,
                        timestamp=datetime.now(timezone.utc),
                        author="backlog_maintenance",
                        summary=f"Backlog item: {item.title}",
                        rationale=major_rationale,
                        status="active",
                    )
                    session.add(plan_change)
                    session.commit()
                    print(f"[PlanChange] Logged major change for {item.id}")
                    session.close()
                except Exception as e:
                    print(f"[PlanChange] Failed to log for {item.id}: {e}")

        # Store test result hashes instead of full outputs (deduplication)
        test_hashes = []
        for test in test_results:
            test_dict = test.__dict__
            test_json = json.dumps(test_dict, sort_keys=True)
            test_hash = hashlib.sha256(test_json.encode()).hexdigest()[:12]
            test_hashes.append(test_hash)

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
                "test_hashes": test_hashes,  # Reference to cache instead of full output
            }
        )

    diag_dir = Path(".autonomous_runs") / run_id / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)

    # Write test output cache separately (deduplication)
    if test_output_cache:
        cache_path = diag_dir / "test_output_cache.json"
        cache_path.write_text(json.dumps(test_output_cache, indent=2), encoding="utf-8")
        print(f"[Tests] Test output cache -> {cache_path} ({len(test_output_cache)} unique outputs)")

    summary_path = diag_dir / "backlog_diagnostics_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"[OK] Diagnostics summaries -> {summary_path}")


if __name__ == "__main__":
    main()

