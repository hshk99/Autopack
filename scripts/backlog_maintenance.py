#!/usr/bin/env python3
"""
Generate a backlog maintenance plan from a curated markdown file.

By default this is propose-first: it only produces a phases JSON file
that can be reviewed or fed into a maintenance run; applying fixes
should still go through governed_apply and diagnostics.
"""

import argparse
from pathlib import Path

from autopack.backlog_maintenance import (
    backlog_items_to_phases,
    parse_backlog_markdown,
    write_plan,
)


def main():
    parser = argparse.ArgumentParser(description="Generate backlog maintenance plan")
    parser.add_argument("--backlog", type=Path, required=True, help="Path to backlog markdown (e.g., consolidated_debug.md)")
    parser.add_argument("--out", type=Path, default=Path(".autonomous_runs/backlog_plan.json"), help="Output plan path")
    parser.add_argument("--max-items", type=int, default=10, help="Max backlog items to include")
    parser.add_argument("--allowed-path", action="append", default=[], help="Allowed path prefix to scope patches")
    parser.add_argument("--max-commands", type=int, default=20, help="Per-phase command budget")
    parser.add_argument("--max-seconds", type=int, default=600, help="Per-phase time budget (sec)")
    args = parser.parse_args()

    items = parse_backlog_markdown(args.backlog, max_items=args.max_items)
    plan = backlog_items_to_phases(
        items,
        default_allowed_paths=args.allowed_path or [],
        max_commands=args.max_commands,
        max_seconds=args.max_seconds,
    )
    out_path = write_plan(plan, args.out)
    print(f"[OK] Backlog plan written to {out_path} with {len(items)} items")


if __name__ == "__main__":
    main()

