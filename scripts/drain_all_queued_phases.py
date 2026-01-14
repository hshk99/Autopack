"""
Drain All QUEUED Phases for a Run

Sequentially drains all QUEUED phases for a given run using drain_one_phase.py.
This is useful for initial telemetry collection runs where all phases start as QUEUED.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///telemetry_seed_v5.db" \
        TELEMETRY_DB_ENABLED=1 AUTOPACK_SKIP_CI=1 \
        python scripts/drain_all_queued_phases.py --run-id telemetry-collection-v5
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Require DATABASE_URL
if not os.environ.get("DATABASE_URL"):
    print("[ERROR] DATABASE_URL must be set", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState


def main():
    parser = argparse.ArgumentParser(description="Drain all QUEUED phases for a run")
    parser.add_argument("--run-id", required=True, help="Run ID")
    parser.add_argument(
        "--phase-timeout", type=int, default=900, help="Timeout per phase in seconds (default: 900)"
    )
    args = parser.parse_args()

    # Get all QUEUED phases
    session = SessionLocal()
    try:
        phases = (
            session.query(Phase)
            .filter(Phase.run_id == args.run_id, Phase.state == PhaseState.QUEUED)
            .order_by(Phase.phase_index)
            .all()
        )

        if not phases:
            print(f"[INFO] No QUEUED phases found for run {args.run_id}")
            return 0

        print(f"[INFO] Found {len(phases)} QUEUED phases for run {args.run_id}")
        print(f"[INFO] Phase timeout: {args.phase_timeout}s")
        print()

        start_time = datetime.now()
        success_count = 0
        failure_count = 0
        timeout_count = 0

        for i, phase in enumerate(phases, 1):
            print(f"{'=' * 80}")
            print(f"[{i}/{len(phases)}] Draining: {phase.phase_id}")
            print(f"{'=' * 80}")

            # Run drain_one_phase
            env = os.environ.copy()
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/drain_one_phase.py",
                    "--run-id",
                    args.run_id,
                    "--phase-id",
                    phase.phase_id,
                    "--force",
                    "--no-dual-auditor",
                ],
                env=env,
                timeout=args.phase_timeout,
                capture_output=False,
            )

            if result.returncode == 0:
                print(f"[{i}/{len(phases)}] ✅ {phase.phase_id} completed successfully")
                success_count += 1
            else:
                print(
                    f"[{i}/{len(phases)}] ❌ {phase.phase_id} failed with exit code {result.returncode}"
                )
                failure_count += 1

            print()

    except subprocess.TimeoutExpired:
        print(f"[{i}/{len(phases)}] ⏱️ {phase.phase_id} timed out after {args.phase_timeout}s")
        timeout_count += 1
        print()

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
        return 1

    finally:
        session.close()

    # Print summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"{'=' * 80}")
    print("BATCH DRAIN SUMMARY")
    print(f"{'=' * 80}")
    print(f"Run ID: {args.run_id}")
    print(f"Total phases: {len(phases)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failure_count}")
    print(f"Timed out: {timeout_count}")
    print(f"Elapsed time: {elapsed:.1f}s ({elapsed / 60:.1f}m)")
    print(f"{'=' * 80}")

    return 0 if failure_count == 0 and timeout_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
