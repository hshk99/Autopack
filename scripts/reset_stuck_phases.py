"""
Reset Stuck Phases for fileorg-phase2-beta

This script resets all phases that are stuck in EXECUTING state back to QUEUED
so that the autonomous executor can pick them up and execute them properly.
"""

import requests
import sys

import os

API_URL = "http://localhost:8000"
if len(sys.argv) > 1:
    RUN_ID = sys.argv[1]
else:
    RUN_ID = "fileorg-test-verification-2025-11-29"


def get_headers():
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("AUTOPACK_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def get_run_status():
    """Fetch run status from API"""
    response = requests.get(f"{API_URL}/runs/{RUN_ID}", headers=get_headers())
    response.raise_for_status()
    return response.json()


def reset_phase_to_queued(phase_id: str):
    """Reset a phase to QUEUED status"""
    response = requests.put(
        f"{API_URL}/runs/{RUN_ID}/phases/{phase_id}/status",
        json={"status": "QUEUED"},
        headers=get_headers(),
    )
    response.raise_for_status()
    return response.json()


def main():
    print(f"[INFO] Fetching run status for: {RUN_ID}")
    run = get_run_status()

    print(f"[INFO] Run state: {run['state']}")
    print(f"[INFO] Tokens used: {run['tokens_used']}")

    stuck_phases = []

    # Find all phases stuck in EXECUTING
    for tier in run.get("tiers", []):
        for phase in tier.get("phases", []):
            if phase["state"] == "EXECUTING":
                stuck_phases.append(phase)

    print(f"\n[INFO] Found {len(stuck_phases)} phases stuck in EXECUTING state")

    if not stuck_phases:
        print("[OK] No stuck phases found!")
        return 0

    print("\n[INFO] Resetting stuck phases to QUEUED...")
    for phase in stuck_phases:
        phase_id = phase["phase_id"]
        name = phase["name"]
        print(f"  - Resetting {phase_id}: {name}")
        try:
            reset_phase_to_queued(phase_id)
            print("    [OK] SUCCESS")
        except Exception as e:
            print(f"    [FAIL] FAILED: {e}")
            return 1

    print(f"\n[SUCCESS] Reset {len(stuck_phases)} phases to QUEUED")
    print("[INFO] You can now run the autonomous executor again:")
    print(f"  python src/autopack/autonomous_executor.py --run-id {RUN_ID}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
