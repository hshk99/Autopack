#!/usr/bin/env python3
"""
Convert a markdown plan into phase specs JSON (phase_spec_schema-compatible).

Usage:
  python scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/file-organizer-app-v1/plan_generated.json
  # Merge into existing plan (plan JSON in docs/)
  python scripts/plan_from_markdown.py --in docs/PLAN.md --merge-base .autonomous_runs/autopack_phase_plan.json --allow-update --out .autonomous_runs/autopack_phase_plan.json
"""

import argparse
from pathlib import Path
import json

from autopack.plan_parser import parse_markdown_plan, phases_to_plan
from autopack.validators import validate_yaml_syntax  # placeholder to mirror import style
from autopack.plan_utils import merge_plans


def main():
    parser = argparse.ArgumentParser(description="Generate phase specs from markdown plan")
    parser.add_argument(
        "--in", dest="input_path", type=Path, required=True, help="Path to markdown plan"
    )
    parser.add_argument(
        "--out", dest="output_path", type=Path, required=True, help="Output JSON path for phases"
    )
    parser.add_argument(
        "--merge-base",
        dest="merge_base",
        type=Path,
        default=None,
        help="Existing plan JSON to merge into",
    )
    parser.add_argument(
        "--allow-update", action="store_true", help="Allow updating existing phase ids when merging"
    )
    parser.add_argument(
        "--default-complexity", default="medium", help="Default complexity if not tagged"
    )
    parser.add_argument(
        "--default-category", default="feature", help="Default task_category if not tagged"
    )
    args = parser.parse_args()

    phases = parse_markdown_plan(
        args.input_path,
        default_complexity=args.default_complexity,
        default_category=args.default_category,
    )
    plan = phases_to_plan(phases)

    # Merge if requested
    if args.merge_base and args.merge_base.exists():
        with open(args.merge_base, "r", encoding="utf-8") as f:
            base_plan = json.load(f)
        plan = merge_plans(base_plan, plan, allow_update=args.allow_update)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {len(phases)} phases to {args.output_path}")


if __name__ == "__main__":
    main()
