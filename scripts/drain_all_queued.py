"""Drain all queued phases across all runs.

This is safer than draining FAILED phases when runs have QUEUED phases,
because it avoids the skip_runs_with_queued trap.

Usage:
    PYTHONUTF8=1 DATABASE_URL="sqlite:///autopack.db" TELEMETRY_DB_ENABLED=1 \\
    python scripts/drain_all_queued.py
"""
import os
import sys
import subprocess
from pathlib import Path

# Default DATABASE_URL
if not os.environ.get("DATABASE_URL"):
    _default_db_path = Path("autopack.db")
    if _default_db_path.exists():
        os.environ["DATABASE_URL"] = "sqlite:///autopack.db"
        print("[drain-all] DATABASE_URL not set; defaulting to sqlite:///autopack.db")

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState

def main():
    session = SessionLocal()

    try:
        # Find all runs with queued phases
        queued_phases = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()

        if not queued_phases:
            print("[drain-all] No queued phases found.")
            return 0

        runs_with_queued = {}
        for p in queued_phases:
            if p.run_id not in runs_with_queued:
                runs_with_queued[p.run_id] = []
            runs_with_queued[p.run_id].append(p.phase_id)

        print(f"[drain-all] Found {len(queued_phases)} queued phases across {len(runs_with_queued)} runs")
        print()

        for idx, (run_id, phase_ids) in enumerate(runs_with_queued.items(), 1):
            print(f"\n{'='*60}")
            print(f"[{idx}/{len(runs_with_queued)}] Draining run: {run_id}")
            print(f"  Queued phases: {len(phase_ids)}")
            for pid in phase_ids:
                print(f"    - {pid}")
            print("="*60)

            # Prepare environment
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["TELEMETRY_DB_ENABLED"] = "1"

            # Call drain_queued_phases.py for this specific run
            cmd = [
                sys.executable,
                "scripts/drain_queued_phases.py",
                "--run-id", run_id,
                "--batch-size", "10",  # Small batch for safety
                "--max-batches", "1",  # Only one batch per run for now
                "--no-dual-auditor",  # Reduce LLM calls
            ]

            print(f"\n[drain-all] Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, env=env, cwd=Path(__file__).parent.parent)

            if result.returncode != 0:
                print(f"\n[drain-all] WARNING: Batch for {run_id} returned code {result.returncode}")
                print("[drain-all] Continuing to next run...")
            else:
                print(f"\n[drain-all] Successfully processed {run_id}")

        print(f"\n{'='*60}")
        print("[drain-all] All queued phase batches completed")
        print("="*60)

        # Final snapshot
        remaining_queued = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).count()
        print(f"\nRemaining QUEUED phases: {remaining_queued}")

    finally:
        session.close()

if __name__ == "__main__":
    sys.exit(main())
