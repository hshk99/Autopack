#!/usr/bin/env python3
"""
Plan hardening phases for a new project.

Usage:
  python scripts/plan_hardening.py --project file-organizer-app-v1 --features auth,search,batch,frontend

This loads templates/hardening_phases.json and templates/phase_defaults.json,
filters phases whose "features" intersect the requested features, and writes
an autopack_phase_plan.json for the project (or updates an existing one).
"""

import argparse
import json
from pathlib import Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def merge_phases(existing, new_phases):
    existing_by_id = {p["id"]: p for p in existing}
    for phase in new_phases:
        existing_by_id[phase["id"]] = phase
    return list(existing_by_id.values())


def filter_phases(phases, features):
    if not features:
        return phases
    selected = []
    for p in phases:
        pf = set(p.get("features", []))
        if not pf or pf.intersection(features):
            selected.append(p)
    return selected


def apply_defaults(phases, defaults):
    default_builder = defaults.get("builder_mode_default")
    scope_threshold = defaults.get("scope_size_structured_threshold", 30)
    default_ci = defaults.get("ci", {})
    for p in phases:
        # Builder mode default
        if default_builder and p.get("builder_mode") is None:
            p["builder_mode"] = default_builder
        # CI defaults
        ci = p.get("ci", {})
        for k, v in default_ci.items():
            ci.setdefault(k, v)
        if ci:
            p["ci"] = ci
        # If scope has many paths, force structured_edit
        scope = p.get("scope", {})
        paths = scope.get("paths", [])
        if scope_threshold and len(paths) >= scope_threshold:
            p["builder_mode"] = "structured_edit"
    return phases


def main():
    parser = argparse.ArgumentParser(description="Plan hardening phases for a project.")
    parser.add_argument("--project", required=True, help="Project slug (used for output path).")
    parser.add_argument(
        "--features",
        default="",
        help="Comma-separated feature flags (e.g., auth,search,batch,frontend,deploy,docs)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output autopack_phase_plan.json path (default: .autonomous_runs/<project>/autopack_phase_plan.json)",
    )
    args = parser.parse_args()

    features = {f.strip() for f in args.features.split(",") if f.strip()}

    template_dir = Path("templates")
    phases_template = load_json(template_dir / "hardening_phases.json")["phases"]
    defaults = load_json(template_dir / "phase_defaults.json")

    selected = filter_phases(phases_template, features)
    selected = apply_defaults(selected, defaults)

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = Path(".autonomous_runs") / args.project / "autopack_phase_plan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        existing = load_json(out_path).get("phases", [])
    else:
        existing = []

    merged = merge_phases(existing, selected)
    out_path.write_text(json.dumps({"phases": merged}, indent=2), encoding="utf-8")
    print(f"Wrote {len(selected)} phases (merged total: {len(merged)}) to {out_path}")


if __name__ == "__main__":
    main()
