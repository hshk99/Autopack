"""Intelligently restart incomplete autonomous phases.

Checks the status of BUILD-145 P1 phases and restarts only those that are
not in COMPLETE state. Skips phases that have already completed successfully.
"""
import sys
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, RunState, PhaseState

RUN_IDS = [
    "autopack-onephase-p11-observability-artifact-first",
    "autopack-onephase-p12-embedding-cache-and-cap",
    "autopack-onephase-p13-expand-artifact-substitution",
    "autopack-onephase-research-import-errors"
]

def get_phase_statuses():
    """Get current status of all phases."""
    session = SessionLocal()
    try:
        phases = session.query(Phase).filter(Phase.run_id.in_(RUN_IDS)).all()
        runs = session.query(Run).filter(Run.id.in_(RUN_IDS)).all()

        run_map = {r.id: r for r in runs}
        phase_info = []

        for p in phases:
            run = run_map.get(p.run_id)
            phase_info.append({
                "phase_id": p.phase_id,
                "run_id": p.run_id,
                "phase_state": p.state,
                "run_state": run.state if run else None,
                "tokens_used": p.tokens_used or 0
            })

        return phase_info
    finally:
        session.close()

def reset_incomplete_phases():
    """Reset incomplete phases to QUEUED state."""
    session = SessionLocal()
    try:
        # Find incomplete phases
        phases = session.query(Phase).filter(
            Phase.run_id.in_(RUN_IDS),
            Phase.state != PhaseState.COMPLETE
        ).all()

        incomplete_run_ids = [p.run_id for p in phases]

        if not incomplete_run_ids:
            print("✅ All phases already complete - nothing to restart")
            return []

        print(f"🔄 Found {len(incomplete_run_ids)} incomplete phases to restart:")
        for p in phases:
            print(f"  • {p.phase_id} ({p.run_id}): {p.state.value}")

        # Reset incomplete runs to QUEUED
        session.query(Run).filter(Run.id.in_(incomplete_run_ids)).update({
            Run.state: RunState.QUEUED,
            Run.started_at: None,
            Run.completed_at: None
        }, synchronize_session=False)

        # Reset incomplete phases to QUEUED
        for phase in phases:
            phase.state = PhaseState.QUEUED
            phase.builder_attempts = 0
            phase.auditor_attempts = 0
            phase.retry_attempt = 0
            phase.revision_epoch = 0

        session.commit()
        print("✅ Reset incomplete phases to QUEUED\n")

        return incomplete_run_ids

    except Exception as e:
        session.rollback()
        print(f"❌ Error resetting phases: {e}")
        return []
    finally:
        session.close()

def start_executor(run_id):
    """Start autonomous executor for a run in background."""
    cmd = [
        "python", "-m", "autopack.autonomous_executor",
        "--run-id", run_id
    ]

    env = {
        "PYTHONUTF8": "1",
        "PYTHONPATH": "src",
        "DATABASE_URL": "sqlite:///autopack.db"
    }

    print(f"🚀 Starting executor for {run_id}")

    # Start in background (detached process)
    process = subprocess.Popen(
        cmd,
        env={**subprocess.os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parent.parent
    )

    return process.pid

def main():
    """Main entry point."""
    print("=" * 70)
    print("BUILD-145 P1 Phase Restart Tool")
    print("=" * 70)
    print()

    # Check current status
    print("📊 Checking current phase status...\n")
    phase_statuses = get_phase_statuses()

    completed_count = sum(1 for p in phase_statuses if p["phase_state"] == PhaseState.COMPLETE)
    total_count = len(phase_statuses)

    print(f"Status: {completed_count}/{total_count} phases complete\n")

    for p in phase_statuses:
        state_emoji = "✅" if p["phase_state"] == PhaseState.COMPLETE else "❌"
        print(f"  {state_emoji} {p['phase_id']}: {p['phase_state'].value}")

    print()

    if completed_count == total_count:
        print("🎉 All phases complete - nothing to restart!")
        return

    # Reset and restart incomplete phases
    print(f"\n{'=' * 70}")
    print("Restarting Incomplete Phases")
    print("=" * 70)
    print()

    incomplete_run_ids = reset_incomplete_phases()

    if not incomplete_run_ids:
        return

    # Start executors
    print("Starting executors...\n")
    pids = []
    for run_id in incomplete_run_ids:
        pid = start_executor(run_id)
        pids.append((run_id, pid))

    print(f"\n✅ Started {len(pids)} executors:\n")
    for run_id, pid in pids:
        print(f"  • {run_id} (PID: {pid})")

    print(f"\n{'=' * 70}")
    print("Next Steps")
    print("=" * 70)
    print()
    print("1. Monitor progress:")
    print("   python scripts/monitor_four_phases.py")
    print()
    print("2. Start completion notification monitor:")
    print("   python scripts/monitor_and_notify_completion.py")
    print()
    print("3. Check executor logs in:")
    print("   .autonomous_runs/autopack/runs/<run-id>/")
    print()

if __name__ == "__main__":
    main()
