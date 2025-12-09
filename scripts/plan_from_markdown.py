#!/usr/bin/env python3
"""
Convert a markdown plan into phase specs JSON (phase_spec_schema-compatible).

Usage:
  python scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/file-organizer-app-v1/plan_generated.json
"""

import argparse
from pathlib import Path
import json

from autopack.plan_parser import parse_markdown_plan, phases_to_plan
from autopack.validators import validate_yaml_syntax  # placeholder to mirror import style


def main():
    parser = argparse.ArgumentParser(description="Generate phase specs from markdown plan")
    parser.add_argument("--in", dest="input_path", type=Path, required=True, help="Path to markdown plan")
    parser.add_argument("--out", dest="output_path", type=Path, required=True, help="Output JSON path for phases")
    parser.add_argument("--default-complexity", default="medium", help="Default complexity if not tagged")
    parser.add_argument("--default-category", default="feature", help="Default task_category if not tagged")
    args = parser.parse_args()

    phases = parse_markdown_plan(
        args.input_path,
        default_complexity=args.default_complexity,
        default_category=args.default_category,
    )
    plan = phases_to_plan(phases)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {len(phases)} phases to {args.output_path}")


if __name__ == "__main__":
    main()

