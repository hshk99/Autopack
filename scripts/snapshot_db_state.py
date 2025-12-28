"""Snapshot current database state for telemetry collection planning."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from collections import Counter

def main():
    session = SessionLocal()

    try:
        # Overall counts
        all_phases = session.query(Phase).all()
        state_counts = Counter([p.state for p in all_phases])

        print("=" * 60)
        print("DATABASE STATE SNAPSHOT")
        print("=" * 60)
        print(f"\nTotal phases: {len(all_phases)}")
        print("\nPhase counts by state:")
        for state in PhaseState:
            count = state_counts.get(state, 0)
            print(f"  {state.value:12s}: {count:4d}")

        # Queued phases detail
        queued_phases = session.query(Phase).filter(Phase.state == PhaseState.QUEUED).all()
        print(f"\n{'='*60}")
        print(f"QUEUED PHASES ({len(queued_phases)} total)")
        print("="*60)

        if queued_phases:
            runs_with_queued = {}
            for p in queued_phases:
                if p.run_id not in runs_with_queued:
                    runs_with_queued[p.run_id] = []
                runs_with_queued[p.run_id].append(p.phase_id)

            for run_id, phase_ids in runs_with_queued.items():
                # Count other states in this run
                failed_count = session.query(Phase).filter(
                    Phase.run_id == run_id,
                    Phase.state == PhaseState.FAILED
                ).count()
                complete_count = session.query(Phase).filter(
                    Phase.run_id == run_id,
                    Phase.state == PhaseState.COMPLETE
                ).count()

                print(f"\nRun: {run_id}")
                print(f"  QUEUED phases: {len(phase_ids)}")
                for pid in phase_ids:
                    print(f"    - {pid}")
                print(f"  FAILED: {failed_count}, COMPLETE: {complete_count}")

        # Failed phases by run
        failed_phases = session.query(Phase).filter(Phase.state == PhaseState.FAILED).all()
        print(f"\n{'='*60}")
        print(f"FAILED PHASES ({len(failed_phases)} total)")
        print("="*60)

        runs_with_failed = {}
        for p in failed_phases:
            if p.run_id not in runs_with_failed:
                runs_with_failed[p.run_id] = 0
            runs_with_failed[p.run_id] += 1

        # Sort by count
        sorted_runs = sorted(runs_with_failed.items(), key=lambda x: x[1], reverse=True)
        print(f"\nFailed phases by run (top 20):")
        for run_id, count in sorted_runs[:20]:
            # Check if this run has queued phases
            has_queued = run_id in ([p.run_id for p in queued_phases] if queued_phases else [])
            marker = " [HAS QUEUED]" if has_queued else ""
            print(f"  {run_id:50s}: {count:3d} failed{marker}")

        print(f"\n{'='*60}")
        print("RECOMMENDATIONS")
        print("="*60)

        if queued_phases:
            print("\n1. Drain QUEUED phases first to avoid skip_runs_with_queued trap")
            print("   Command: python scripts/drain_queued_phases.py")

        print("\n2. Then drain FAILED phases with strict stop conditions")
        print("   Command: python scripts/batch_drain_controller.py \\")
        print("     --batch-size 30 \\")
        print("     --max-attempts-per-phase 1 \\")
        print("     --max-fingerprint-repeats 2 \\")
        print("     --max-timeouts-per-run 1 \\")
        print("     --max-consecutive-zero-yield 10")

        if any(run_id.startswith('research-system') for run_id in runs_with_failed):
            print("\n3. Research-system runs present - CI collection fixes should help")
            print("   Consider removing --skip-run-prefix research-system")

    finally:
        session.close()

if __name__ == "__main__":
    main()
