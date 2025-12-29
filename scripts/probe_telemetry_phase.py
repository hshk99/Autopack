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
import subprocess
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


def count_telemetry_rows(db) -> tuple[int, int]:
    """Count rows in both telemetry tables.

    Returns:
        (token_estimation_v2_events_count, llm_usage_events_count)
    """
    try:
        # Count token_estimation_v2_events (the main telemetry table for calibration)
        result_v2 = db.execute(text("SELECT COUNT(*) FROM token_estimation_v2_events"))
        count_v2 = result_v2.scalar() or 0

        # Also count llm_usage_events for completeness
        result_usage = db.execute(text("SELECT COUNT(*) FROM llm_usage_events"))
        count_usage = result_usage.scalar() or 0

        return count_v2, count_usage
    except Exception as e:
        print(f"[PROBE] Warning: Could not count telemetry rows: {e}", file=sys.stderr)
        return -1, -1


def main() -> int:
    p = argparse.ArgumentParser(description="Probe single telemetry phase for go/no-go test")
    p.add_argument("--run-id", required=True, help="Run ID (e.g., telemetry-collection-v4)")
    p.add_argument("--phase-id", required=True, help="Phase ID (e.g., telemetry-p1-string-util)")
    args = p.parse_args()

    # GUARDRAIL: Only set AUTOPACK_SKIP_CI for telemetry runs
    is_telemetry_run = args.run_id.startswith("telemetry-collection-")

    print(f"[PROBE] Phase: {args.phase_id}")
    print(f"[PROBE] DATABASE_URL: {os.environ.get('DATABASE_URL')}")
    print(f"[PROBE] TELEMETRY_DB_ENABLED: {os.environ.get('TELEMETRY_DB_ENABLED')}")
    if is_telemetry_run:
        print(f"[PROBE] AUTOPACK_SKIP_CI: 1 (telemetry seeding mode - bypasses CI checks)")
    else:
        print(f"[PROBE] AUTOPACK_SKIP_CI: not set (non-telemetry run - normal CI checks)")
    print()

    # Count telemetry rows before drain
    db = SessionLocal()
    try:
        v2_before, usage_before = count_telemetry_rows(db)
        print(f"[PROBE] DB telemetry rows (before):")
        print(f"[PROBE]   - token_estimation_v2_events: {v2_before}")
        print(f"[PROBE]   - llm_usage_events: {usage_before}")

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

    # Run drain_one_phase with subprocess.run for reliable exit code handling
    print(f"[PROBE] Running drain_one_phase...")
    print()

    # BUILD-141 Part 8: Set AUTOPACK_SKIP_CI=1 for telemetry seeding ONLY
    # This bypasses CI checks to avoid blocking on unrelated test import errors
    # GUARDRAIL: Only set this for telemetry runs (run_id starts with 'telemetry-collection-')
    env = os.environ.copy()
    if is_telemetry_run:
        env.setdefault("AUTOPACK_SKIP_CI", "1")

    # T5: Use subprocess.run instead of os.system for reliable Windows exit codes
    result = subprocess.run(
        [
            sys.executable,  # Use same Python interpreter
            "scripts/drain_one_phase.py",
            "--run-id", args.run_id,
            "--phase-id", args.phase_id,
            "--force",
            "--no-dual-auditor"
        ],
        env=env,  # Pass environment with AUTOPACK_SKIP_CI=1
    )

    print()
    print(f"[PROBE] Drain exit code: {result.returncode}")

    # Count telemetry rows after drain
    db = SessionLocal()
    try:
        v2_after, usage_after = count_telemetry_rows(db)
        v2_delta = v2_after - v2_before if v2_before >= 0 and v2_after >= 0 else -1
        usage_delta = usage_after - usage_before if usage_before >= 0 and usage_after >= 0 else -1

        print(f"[PROBE] DB telemetry rows (after):")
        print(f"[PROBE]   - token_estimation_v2_events: {v2_after}", end="")
        if v2_delta > 0:
            print(f" (INCREASED by {v2_delta} ✅)")
        elif v2_delta == 0:
            print(f" (NO INCREASE ❌)")
        else:
            print(f" (ERROR counting)")

        print(f"[PROBE]   - llm_usage_events: {usage_after}", end="")
        if usage_delta > 0:
            print(f" (INCREASED by {usage_delta} ✅)")
        elif usage_delta == 0:
            print(f" (NO INCREASE ❌)")
        else:
            print(f" (ERROR counting)")

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

        # T5: Deterministic empty-files detection
        # ONLY report "EMPTY" if we can confirm it from failure reason
        # Otherwise report "UNKNOWN" instead of falsely claiming "NOT EMPTY"
        failure_reason = phase.last_failure_reason or ""
        empty_files_confirmed = "empty files array" in failure_reason.lower()

        if empty_files_confirmed:
            print(f"[PROBE] Files array: EMPTY (confirmed) ❌")
            print(f"[PROBE] Failure reason: {failure_reason[:200]}")
        elif final_state == PhaseState.COMPLETE.value:
            # If phase completed, we can reasonably infer non-empty files
            print(f"[PROBE] Files array: NOT EMPTY (phase completed) ✅")
        else:
            # Phase failed but not due to empty files array - can't confirm either way
            print(f"[PROBE] Files array: UNKNOWN (phase failed, not due to empty files)")
            if failure_reason:
                print(f"[PROBE] Failure reason: {failure_reason[:200]}")

        # Verdict
        print()
        print(f"[PROBE] ========== VERDICT ==========")

        # Success requires: COMPLETE state + telemetry row increase + no empty-files error
        if final_state == PhaseState.COMPLETE.value and v2_delta > 0:
            print(f"[PROBE] ✅ SUCCESS - telemetry collection working")
            print(f"[PROBE] Go ahead with draining remaining phases")
            return 0
        elif empty_files_confirmed:
            print(f"[PROBE] ❌ FAILED - empty files array confirmed")
            print(f"[PROBE] DO NOT drain remaining phases - prompt fixes (T1) may not be working")
            return 1
        elif v2_delta == 0:
            print(f"[PROBE] ❌ FAILED - no token_estimation_v2_events collected")
            print(f"[PROBE] DO NOT drain remaining phases - check:")
            print(f"[PROBE]   1. TELEMETRY_DB_ENABLED=1 is set")
            print(f"[PROBE]   2. Telemetry validity guards (actual_output_tokens >= 50)")
            print(f"[PROBE]   3. Builder is producing output (check usage_delta={usage_delta})")
            return 1
        else:
            print(f"[PROBE] ❌ FAILED - phase did not complete successfully")
            print(f"[PROBE] Check logs and fix issues before draining remaining phases")
            if failure_reason:
                print(f"[PROBE] Failure reason: {failure_reason[:200]}")
            return 1

    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
