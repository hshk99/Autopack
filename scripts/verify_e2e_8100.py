#!/usr/bin/env python3
"""
E2E smoke probe against the Autopack API on port 8100.

Flow:
1) Load phases from a phase spec JSON file (docs/phase_spec_schema.md format).
2) POST /runs/start to create a run using a single tier.
3) Update the first phase to COMPLETE to verify write access.

Defaults:
- API URL: http://127.0.0.1:8100
- Plan: ./autopack_phase_plan.json

Exit codes:
- 0 on success
- 1 on validation or HTTP failures
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests


def load_phases(plan_path: Path) -> List[Dict[str, Any]]:
    """Load phases from a plan file and basic-validate required fields."""
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    with plan_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("Plan must contain a non-empty 'phases' list.")

    for idx, phase in enumerate(phases):
        missing = [k for k in ("id", "description", "task_category", "complexity") if k not in phase]
        if missing:
            raise ValueError(f"Phase index {idx} missing keys: {', '.join(missing)}")

    return phases


def build_run_payload(run_id: str, phases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Construct /runs/start payload using a single tier."""
    tier_id = "T1"
    tier = {
        "tier_id": tier_id,
        "tier_index": 0,
        "name": "Stability",
        "description": "Autopack maintenance smoke tier"
    }

    api_phases: List[Dict[str, Any]] = []
    for idx, phase in enumerate(phases):
        api_phases.append(
            {
                "phase_id": phase["id"],
                "phase_index": idx,
                "tier_id": tier_id,
                "name": phase["id"].replace("-", " ").title(),
                "description": phase["description"],
                "task_category": phase.get("task_category"),
                "complexity": phase.get("complexity"),
                "scope": phase.get("scope"),
            }
        )

    payload: Dict[str, Any] = {
        "run": {
            "run_id": run_id,
            "safety_profile": "normal",
            "run_scope": "multi_tier",
            "token_cap": 5000000,
            "max_phases": len(api_phases),
            "max_duration_minutes": 120,
        },
        "tiers": [tier],
        "phases": api_phases,
    }

    return payload


def post_json(url: str, payload: Dict[str, Any], api_key: str = None) -> requests.Response:
    """Issue a JSON POST with optional X-API-Key header."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    return requests.post(url, headers=headers, json=payload, timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description="Autopack E2E smoke on port 8100")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8100",
        help="Autopack API base URL (default: http://127.0.0.1:8100)",
    )
    parser.add_argument(
        "--plan",
        default="autopack_phase_plan.json",
        help="Path to phase plan JSON (default: autopack_phase_plan.json)",
    )
    parser.add_argument(
        "--run-id",
        default=f"smoke-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        help="Run ID to create (default: timestamped)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for X-API-Key header (default: AUTOPACK_API_KEY env or none)",
    )

    args = parser.parse_args()
    api_key = args.api_key or os.getenv("AUTOPACK_API_KEY")

    try:
        phases = load_phases(Path(args.plan))
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to load plan: {exc}")
        return 1

    payload = build_run_payload(args.run_id, phases)

    # Step 1: create run
    try:
        run_resp = post_json(f"{args.api_url}/runs/start", payload, api_key)
    except requests.RequestException as exc:
        print(f"[ERROR] Request to /runs/start failed: {exc}")
        return 1

    if run_resp.status_code != 201:
        print(f"[ERROR] /runs/start returned {run_resp.status_code}: {run_resp.text}")
        return 1

    run_data = run_resp.json()
    print(f"[OK] Run created: {run_data.get('id')}")

    # Step 2: update first phase to COMPLETE
    first_phase_id = payload["phases"][0]["phase_id"]
    status_payload = {
        "state": "COMPLETE",
        "builder_attempts": 0,
        "tokens_used": 0,
        "minor_issues_count": 0,
        "major_issues_count": 0,
        "quality_level": "ok",
        "quality_blocked": False,
    }

    try:
        status_resp = post_json(
            f"{args.api_url}/runs/{args.run_id}/phases/{first_phase_id}/update_status",
            status_payload,
            api_key,
        )
    except requests.RequestException as exc:
        print(f"[ERROR] Request to update phase failed: {exc}")
        return 1

    if status_resp.status_code != 200:
        print(f"[ERROR] Phase update returned {status_resp.status_code}: {status_resp.text}")
        return 1

    print(f"[OK] Phase {first_phase_id} marked COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())

