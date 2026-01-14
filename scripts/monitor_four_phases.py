"""Monitor execution of 4 autonomous phases"""

import time
from autopack.database import SessionLocal
from autopack.models import Run, Phase, PhaseState

RUN_IDS = [
    "autopack-onephase-p11-observability-artifact-first",
    "autopack-onephase-p12-embedding-cache-and-cap",
    "autopack-onephase-p13-expand-artifact-substitution",
    "autopack-onephase-research-import-errors",
]


def check_status():
    """Check current status of all runs"""
    session = SessionLocal()
    try:
        runs = session.query(Run).filter(Run.id.in_(RUN_IDS)).all()
        phases = session.query(Phase).filter(Phase.run_id.in_(RUN_IDS)).all()

        print("\n" + "=" * 70)
        print("Phase Execution Status")
        print("=" * 70)

        for run in runs:
            print(f"\n{run.id}")
            print(f"  Run State: {run.state.value}")
            if run.tokens_used:
                print(f"  Tokens Used: {run.tokens_used:,}")

            run_phases = [p for p in phases if p.run_id == run.id]
            for p in run_phases:
                print(f"    Phase {p.phase_id}: {p.state.value}")
                if p.tokens_used:
                    print(f"      Tokens: {p.tokens_used:,}")

        # Summary
        states = [p.state for p in phases]
        print("\n" + "=" * 70)
        print(f"Summary: {len(phases)} phases")
        print(f"  QUEUED: {states.count(PhaseState.QUEUED)}")
        print(f"  EXECUTING: {states.count(PhaseState.EXECUTING)}")
        print(f"  COMPLETE: {states.count(PhaseState.COMPLETE)}")
        print(f"  FAILED: {states.count(PhaseState.FAILED)}")
        print("=" * 70)

        all_done = all(s in [PhaseState.COMPLETE, PhaseState.FAILED] for s in states)
        return all_done

    finally:
        session.close()


if __name__ == "__main__":
    check_status()
