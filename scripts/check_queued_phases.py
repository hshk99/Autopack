"""
Check for runs with queued phases available for telemetry collection.
"""
from autopack.database import SessionLocal
from autopack.models import Run, Phase, PhaseState

def main():
    session = SessionLocal()
    try:
        runs = session.query(Run).all()

        print("All Runs with Phase Status:")
        print("=" * 80)

        total_queued = 0
        queued_runs = []

        for run in runs:
            phases = session.query(Phase).filter(Phase.run_id == run.id).all()
            if not phases:
                continue

            queued = sum(1 for p in phases if p.state == PhaseState.QUEUED)
            completed = sum(1 for p in phases if p.state == PhaseState.COMPLETE)
            failed = sum(1 for p in phases if p.state == PhaseState.FAILED)

            if queued > 0:
                total_queued += queued
                queued_runs.append((run.id, queued, len(phases)))

            print(f"{run.id}")
            print(f"  State: {run.state}")
            print(f"  Phases: {len(phases)} total (Queued: {queued}, Completed: {completed}, Failed: {failed})")
            print()

        print("=" * 80)
        print("\nSummary:")
        print(f"Total runs with queued phases: {len(queued_runs)}")
        print(f"Total queued phases available: {total_queued}")

        if queued_runs:
            print("\nRuns ready for execution:")
            for run_id, queued_count, total in queued_runs:
                print(f"  - {run_id}: {queued_count}/{total} phases queued")

    finally:
        session.close()

if __name__ == "__main__":
    main()
