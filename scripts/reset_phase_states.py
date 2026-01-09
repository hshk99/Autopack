"""
Reset phases from EXECUTING to QUEUED

Fixes the issue where phases are stuck in EXECUTING state and can't be processed by the autonomous executor
"""

import sys
import os

# Add src to path so we can import from autopack
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState

def reset_phases(run_id: str):
    """Reset all EXECUTING phases to QUEUED for a given run"""
    db = SessionLocal()
    try:
        # Find all EXECUTING phases for this run
        phases = db.query(Phase).join(Phase.tier).filter(
            Phase.state == PhaseState.EXECUTING
        ).all()

        # Filter by run_id
        reset_count = 0
        for phase in phases:
            if phase.tier.run_id == run_id:
                print(f"[INFO] Resetting phase {phase.phase_id} from EXECUTING to QUEUED")
                phase.state = PhaseState.QUEUED
                reset_count += 1

        db.commit()
        print(f"\n[SUCCESS] Reset {reset_count} phases to QUEUED state")
        return reset_count

    except Exception as e:
        print(f"[ERROR] Failed to reset phases: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reset_phase_states.py <run_id>")
        sys.exit(1)

    run_id = sys.argv[1]
    print(f"\n[INFO] Resetting EXECUTING phases to QUEUED for run: {run_id}\n")

    count = reset_phases(run_id)
    if count > 0:
        print(f"\n[OK] Run {run_id} is now ready for execution")
        sys.exit(0)
    else:
        print("\n[WARNING] No phases were reset (either no EXECUTING phases found, or run doesn't exist)")
        sys.exit(1)
