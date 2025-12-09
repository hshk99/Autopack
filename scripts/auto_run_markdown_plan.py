#!/usr/bin/env python3
"""
Convert a markdown plan to a phase spec and run maintenance mode automatically.

This is a thin wrapper around plan_from_markdown + executor backlog maintenance:
- Converts markdown to plan JSON
- Runs diagnostics/apply via AutonomousExecutor.run_backlog_maintenance

Defaults are conservative (checkpoint on, propose-first unless --apply/--auto-apply-low-risk).
"""

import argparse
import json
import os
from pathlib import Path

from autopack.plan_parser import parse_markdown_plan, phases_to_plan
from autopack.autonomous_executor import AutonomousExecutor


def main():
    parser = argparse.ArgumentParser(description="Auto-convert markdown plan and run maintenance mode")
    parser.add_argument("--plan-md", type=Path, required=True, help="Path to markdown plan")
    parser.add_argument("--run-id", type=str, required=True, help="Run ID for maintenance execution")
    parser.add_argument("--out-plan", type=Path, default=None, help="Output plan JSON (default: .autonomous_runs/<run-id>/plan_generated.json)")
    parser.add_argument("--patch-dir", type=Path, default=None, help="Directory containing patches named <phase_id>.patch")
    parser.add_argument("--apply", action="store_true", help="Attempt to apply patches if auditor approves (requires checkpoint)")
    parser.add_argument("--auto-apply-low-risk", action="store_true", help="Auto-apply only low-risk approved patches (in-scope, small diff, tests passing)")
    parser.add_argument("--test-cmd", action="append", default=[], help="Targeted test command(s) to run per item")
    parser.add_argument("--allowed-path", action="append", default=[], help="Allowed path prefixes for maintenance")
    parser.add_argument("--default-allowed-path", action="append", default=[], help="Additional default allowed paths")
    parser.add_argument("--max-files", type=int, default=10, help="Max files for auto-approval")
    parser.add_argument("--max-lines", type=int, default=500, help="Max lines added+deleted for auto-approval")
    parser.add_argument("--workspace", type=Path, default=Path("."), help="Workspace root")
    parser.add_argument("--api-url", default=os.getenv("AUTOPACK_API_URL", "http://localhost:8000"), help="Autopack API URL")
    parser.add_argument("--api-key", default=os.getenv("AUTOPACK_API_KEY"), help="Autopack API key (if required by executor)")
    args = parser.parse_args()

    run_id = args.run_id
    out_plan = args.out_plan or (Path(".autonomous_runs") / run_id / "plan_generated.json")

    # Convert markdown to plan JSON
    phases = parse_markdown_plan(args.plan_md)
    plan = phases_to_plan(phases)
    out_plan.parent.mkdir(parents=True, exist_ok=True)
    out_plan.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"[Plan] Wrote {len(phases)} phases to {out_plan}")

    # Run maintenance mode (diagnostics/apply gated)
    executor = AutonomousExecutor(
        run_id=run_id,
        api_url=args.api_url,
        api_key=args.api_key,
        workspace=args.workspace,
        use_dual_auditor=False,
        run_type="project_build",
    )

    executor.run_backlog_maintenance(
        plan_path=out_plan,
        patch_dir=args.patch_dir,
        apply=args.apply or args.auto_apply_low_risk,
        allowed_paths=args.allowed_path or args.default_allowed_path,
        checkpoint=True,
        test_commands=args.test_cmd,
        auto_apply_low_risk=args.auto_apply_low_risk,
        max_files=args.max_files,
        max_lines=args.max_lines,
    )
    print("[OK] Maintenance run complete")


if __name__ == "__main__":
    main()

