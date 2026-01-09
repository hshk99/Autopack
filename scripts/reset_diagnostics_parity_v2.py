#!/usr/bin/env python3
"""Reset diagnostics-parity-v2 run after BUILD-098 fix"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, PhaseState, RunState

init_db()
db = SessionLocal()

try:
    # Reset run state
    run = db.query(Run).filter(Run.id == "autopack-diagnostics-parity-v2").first()
    if run:
        run.state = RunState.PHASE_QUEUEING

        # Reset all phases
        for phase in run.phases:
            phase.state = PhaseState.QUEUED
            phase.builder_attempts = 0
            phase.auditor_attempts = 0
            phase.retry_attempt = 0
            print(f"Reset phase: {phase.phase_id}")

        db.commit()
        print(f"\n✅ Run {run.id} reset successfully")
        print(f"   Phases reset: {len(run.phases)}")
    else:
        print("❌ Run not found")

except Exception as e:
    print(f"❌ Error: {e}")
    db.rollback()
finally:
    db.close()
