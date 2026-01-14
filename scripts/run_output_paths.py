#!/usr/bin/env python3
"""
Helper to suggest output directories for new runs, using tidy_workspace routing.

Usage:
    python scripts/run_output_paths.py --run-id fileorg-country-uk-20251205-132826
    python scripts/run_output_paths.py --run-id myrun --project my-project --family custom-family
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Reuse routing helpers from tidy_workspace
from tidy_workspace import route_run_output, route_new_doc, classify_project


def main():
    parser = argparse.ArgumentParser(description="Suggest output paths for runs and docs.")
    parser.add_argument(
        "--run-id", required=False, help="Run id (e.g., fileorg-country-uk-20251205-132826)"
    )
    parser.add_argument(
        "--family", help="Family prefix; if omitted, derived from run-id prefix before timestamp"
    )
    parser.add_argument(
        "--project", dest="project_hint", help="Project hint (default: auto-detect)"
    )
    parser.add_argument("--archived", action="store_true", help="Suggest archived path")
    parser.add_argument(
        "--doc-name", help="Optional doc name to route (e.g., IMPLEMENTATION_PLAN.md)"
    )
    parser.add_argument(
        "--doc-purpose", help="Optional doc purpose (plan/analysis/prompt/log/script/report)"
    )
    args = parser.parse_args()

    if args.run_id:
        family = args.family or derive_family(args.run_id)
        dest = route_run_output(args.project_hint, family, args.run_id, archived=args.archived)
        print(f"Run output path: {dest}")
    if args.doc_name:
        doc_dest = route_new_doc(
            args.doc_name,
            purpose=args.doc_purpose,
            project_hint=args.project_hint,
            archived=args.archived,
        )
        print(f"Doc path: {doc_dest}")


def derive_family(run_id: str) -> str:
    # Take prefix before last dash+digits block if present
    parts = run_id.split("-")
    if len(parts) >= 3 and parts[-1].isdigit():
        return "-".join(parts[:-1])
    return parts[0]


if __name__ == "__main__":
    main()
