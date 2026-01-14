"""Monitor Autopack run and stop executor on first failure

Usage:
    python scripts/monitor_and_stop.py <run-id>

This script:
1. Monitors the run status via API
2. Watches for phase failures
3. Can signal the executor to stop (via file-based signal)
"""

import sys
import time
import requests
import signal
import os
from pathlib import Path

API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
STOP_SIGNAL_FILE = Path(".autonomous_runs/.stop_executor")


def check_run_status(run_id: str):
    """Check current run status"""
    try:
        response = requests.get(f"{API_URL}/runs/{run_id}", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"[MONITOR] API error: {e}")
        return None


def monitor_run(run_id: str, check_interval: int = 5):
    """Monitor run and detect failures"""
    print(f"[MONITOR] Monitoring run: {run_id}")
    print(f"[MONITOR] Checking every {check_interval} seconds")
    print("[MONITOR] Press Ctrl+C to stop monitoring\n")

    last_phase_states = {}

    try:
        while True:
            run_data = check_run_status(run_id)
            if not run_data:
                time.sleep(check_interval)
                continue

            # Collect all phases
            all_phases = []
            for tier in run_data.get("tiers", []):
                all_phases.extend(tier.get("phases", []))

            # Check for failures
            failed_phases = [p for p in all_phases if p.get("state") == "FAILED"]
            executing_phases = [p for p in all_phases if p.get("state") == "EXECUTING"]
            queued_phases = [p for p in all_phases if p.get("state") == "QUEUED"]
            complete_phases = [p for p in all_phases if p.get("state") == "COMPLETE"]

            # Print status
            print(
                f"\r[MONITOR] Status: {len(complete_phases)} complete, {len(executing_phases)} executing, {len(queued_phases)} queued, {len(failed_phases)} failed",
                end="",
                flush=True,
            )

            # Check for new failures
            for phase in failed_phases:
                phase_id = phase.get("phase_id")
                if phase_id not in last_phase_states or last_phase_states[phase_id] != "FAILED":
                    print(f"\n[MONITOR] ⚠️  FAILURE DETECTED: {phase_id}")
                    print(f"[MONITOR] Phase name: {phase.get('name', 'N/A')}")
                    print(f"[MONITOR] State: {phase.get('state')}")

                    # Create stop signal file
                    STOP_SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
                    STOP_SIGNAL_FILE.write_text(f"stop:{run_id}:{phase_id}")
                    print(f"[MONITOR] Stop signal created: {STOP_SIGNAL_FILE}")
                    print("[MONITOR] Executor should stop on next check")
                    return True

            # Update last known states
            for phase in all_phases:
                phase_id = phase.get("phase_id")
                last_phase_states[phase_id] = phase.get("state")

            time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\n[MONITOR] Monitoring stopped by user")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/monitor_and_stop.py <run-id>")
        sys.exit(1)

    run_id = sys.argv[1]
    failure_detected = monitor_run(run_id)

    if failure_detected:
        print("\n[MONITOR] ✅ Failure detected and stop signal sent")
        sys.exit(0)
    else:
        print("\n[MONITOR] Monitoring stopped")
        sys.exit(0)
