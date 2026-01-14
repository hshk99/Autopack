"""Reset retry-api-router-v1 run and phase for clean retry after BUILD-096 fix"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path.cwd() / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState

init_db()
db = SessionLocal()

# Reset run state
run = db.query(Run).filter(Run.id == "retry-api-router-v1").first()
if run:
    run.state = RunState.PHASE_QUEUEING
    run.updated_at = datetime.now(timezone.utc)

# Reset phase state and counters
phase = db.query(Phase).filter(Phase.run_id == "retry-api-router-v1").first()
if phase:
    phase.state = PhaseState.QUEUED
    phase.retry_attempt = 0
    phase.builder_attempts = 0
    phase.auditor_attempts = 0
    phase.updated_at = datetime.now(timezone.utc)

    db.commit()
    print(
        f"Reset run {run.id} and phase {phase.phase_id}: state={phase.state}, retry_attempt={phase.retry_attempt}"
    )
else:
    print("Phase not found")

db.close()
