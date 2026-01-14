#!/usr/bin/env python3
"""
Create a run via API and emit its local output directory using routing helpers.

This wraps the run creation request and prints the suggested local paths for outputs.
It does not move files itself; use these paths when launching the executor or writing logs/artifacts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import requests

from tidy_workspace import route_run_output, classify_project
from scripts.run_output_paths import derive_family  # reuse helper


def main():
    parser = argparse.ArgumentParser(description="Create run with routed output path")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--run-id", required=True, help="Run id")
    parser.add_argument("--project", dest="project_hint", help="Project hint (default auto-detect)")
    parser.add_argument("--family", help="Run family; if omitted, derived from run-id")
    parser.add_argument("--payload", required=True, help="Path to JSON payload for the run start")
    parser.add_argument("--archived", action="store_true", help="Suggest archived path")
    args = parser.parse_args()

    project = classify_project(args.project_hint)
    family = args.family or derive_family(args.run_id)
    out_dir = route_run_output(project, family, args.run_id, archived=args.archived)

    payload_path = Path(args.payload)
    if not payload_path.exists():
        print(f"[ERROR] Payload file not found: {payload_path}")
        sys.exit(1)

    import json

    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    # inject run_id into payload if not present
    if "run" in payload and "run_id" not in payload["run"]:
        payload["run"]["run_id"] = args.run_id

    print(f"[INFO] Creating run {args.run_id} (project={project}, family={family})")
    resp = requests.post(f"{args.api_url}/runs/start", json=payload)
    if resp.status_code != 201:
        print(f"[ERROR] API status: {resp.status_code}")
        print(resp.text)
        resp.raise_for_status()

    print(f"[SUCCESS] Run created: {args.run_id}")
    print(f"[INFO] Suggested local output dir: {out_dir}")
    print("[INFO] Launch executor with this run-id using that output dir for artifacts/logs.")


if __name__ == "__main__":
    main()
