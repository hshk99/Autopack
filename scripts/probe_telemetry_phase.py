"""
Telemetry Phase Probe - Quick Go/No-Go Test

Runs exactly one telemetry seeding phase and reports:
- Builder output token count
- Whether files array was empty
- Whether DB telemetry row count increased
- Go/No-Go verdict for continuing with full drain

This is the go/no-go gate before draining remaining 9 phases.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \
        TELEMETRY_DB_ENABLED=1 \
        python scripts/probe_telemetry_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util

Expected Output:
    [PROBE] Phase: telemetry-p1-string-util
    [PROBE] Builder output tokens: 826
    [PROBE] Files array: NOT EMPTY ✅
    [PROBE] DB telemetry rows (before): 0
    [PROBE] DB telemetry rows (after): 1 (INCREASED ✅)
    [PROBE] Verdict: SUCCESS - telemetry collection working
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Require DATABASE_URL to be explicitly set
if not os.environ.get("DATABASE_URL"):
    print("[ERROR] DATABASE_URL must be set", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage:", file=sys.stderr)
    print("  DATABASE_URL='sqlite:///autopack_telemetry_seed.db' TELEMETRY_DB_ENABLED=1 python scripts/probe_telemetry_phase.py ...", file=sys.stderr)
    print("", file=sys.stderr)
    sys.exit(1)

if not os.environ.get("TELEMETRY_DB_ENABLED"):
    print("[WARNING] TELEMETRY_DB_ENABLED not set - telemetry collection may not work", file=sys.stderr)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from sqlalchemy import text


def count_telemetry_rows(db) -> int:
    """Count rows in token_estimation_v2_events table."""
    try:
        result = db.execute(text("SELECT COUNT(*) FROM token_estimation_v2_events"))
        return result.scalar() or 0
    except Exception as e:
        print(f"[PROBE] Warning: Could not count telemetry rows: {e}", file=sys.stderr)
        return -1


def main() -> int:
    p = argparse.ArgumentParser(description="Probe single telemetry phase for go/no-go test")
    p.add_argument("--run-id", required=True, help="Run ID (e.g., telemetry-collection-v4)")
    p.add_argument("--phase-id", required=True, help="Phase ID (e.g., telemetry-p1-string-util)")
    args = p.parse_args()

    print(f"[PROBE] Phase: {args.phase_id}")
    print(f"[PROBE] DATABASE_URL: {os.environ.get('DATABASE_URL')}")
    print(f"[PROBE] TELEMETRY_DB_ENABLED: {os.environ.get('TELEMETRY_DB_ENABLED')}")
    print()

    # Count telemetry rows before drain
    db = SessionLocal()
    try:
        telemetry_before = count_telemetry_rows(db)
        print(f"[PROBE] DB telemetry rows (before): {telemetry_before}")

        # Check phase exists
        phase = (
            db.query(Phase)
            .filter(Phase.run_id == args.run_id, Phase.phase_id == args.phase_id)
            .first()
        )

        if not phase:
            print(f"[PROBE] ❌ Phase not found: {args.run_id} / {args.phase_id}", file=sys.stderr)
            return 1

    finally:
        db.close()

    # Run drain_one_phase
    print(f"[PROBE] Running drain_one_phase...")
    print()

    exit_code = os.system(
        f'python scripts/drain_one_phase.py --run-id {args.run_id} --phase-id {args.phase_id} '
        f'--force --no-dual-auditor'
    )

    print()
    print(f"[PROBE] Drain exit code: {exit_code}")

    # Count telemetry rows after drain
    db = SessionLocal()
    try:
        telemetry_after = count_telemetry_rows(db)
        telemetry_delta = telemetry_after - telemetry_before if telemetry_before >= 0 and telemetry_after >= 0 else -1

        print(f"[PROBE] DB telemetry rows (after): {telemetry_after}", end="")
        if telemetry_delta > 0:
            print(f" (INCREASED by {telemetry_delta} ✅)")
        elif telemetry_delta == 0:
            print(f" (NO INCREASE ❌)")
        else:
            print(f" (ERROR counting rows)")

        # Check phase final state
        phase = (
            db.query(Phase)
            .filter(Phase.run_id == args.run_id, Phase.phase_id == args.phase_id)
            .first()
        )

        if not phase:
            print(f"[PROBE] ❌ Phase not found after drain", file=sys.stderr)
            return 1

        final_state = phase.state.value if phase.state else "UNKNOWN"
        print(f"[PROBE] Phase final state: {final_state}")

        # Check if Builder returned empty files array (look at failure reason)
        failure_reason = phase.last_failure_reason or ""
        empty_files = "empty files array" in failure_reason.lower()

        if empty_files:
            print(f"[PROBE] Files array: EMPTY ❌")
            print(f"[PROBE] Failure reason: {failure_reason[:200]}")
        else:
            print(f"[PROBE] Files array: NOT EMPTY ✅")

        # Verdict
        print()
        print(f"[PROBE] ========== VERDICT ==========")

        if final_state == PhaseState.COMPLETE.value and telemetry_delta > 0 and not empty_files:
            print(f"[PROBE] ✅ SUCCESS - telemetry collection working")
            print(f"[PROBE] Go ahead with draining remaining phases")
            return 0
        elif empty_files:
            print(f"[PROBE] ❌ FAILED - empty files array, no telemetry collected")
            print(f"[PROBE] DO NOT drain remaining phases - fix prompt ambiguity first")
            return 1
        elif telemetry_delta == 0:
            print(f"[PROBE] ❌ FAILED - no telemetry collected (validity guard triggered?)")
            print(f"[PROBE] DO NOT drain remaining phases - check telemetry validity guards")
            return 1
        else:
            print(f"[PROBE] ❌ FAILED - phase did not complete successfully")
            print(f"[PROBE] Check logs and fix issues before draining remaining phases")
            return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
