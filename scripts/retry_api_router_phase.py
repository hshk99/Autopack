"""Retry research-api-router phase after research-examples-and-docs fix"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path.cwd() / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
import yaml

init_db()
db = SessionLocal()

# Create run
run = Run(
    id="retry-api-router-v1",
    state=RunState.PHASE_QUEUEING,
    safety_profile="normal",
    run_scope="multi_tier",
    token_cap=500_000,
    max_phases=1,
    max_duration_minutes=120,
    tokens_used=0,
    ci_runs_used=0,
    minor_issues_count=0,
    major_issues_count=0,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)
db.add(run)

# Create tier
tier = Tier(
    tier_id="api-router-retry-tier",
    run_id="retry-api-router-v1",
    tier_index=0,
    name="API Router Retry",
    description="Retry research-api-router after examples phase success",
    state=TierState.PENDING,
    tokens_used=0,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)
db.add(tier)
db.flush()  # Get auto-generated id

# Load requirements
req_path = Path("requirements/research_followup/followup4-research-api-router.yaml")
with open(req_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Create phase
phase = Phase(
    phase_id=config["phase_id"],
    run_id="retry-api-router-v1",
    tier_id=tier.id,  # Use integer FK
    phase_index=0,
    name=config["phase_id"],
    description=config["description"].strip(),
    state=PhaseState.QUEUED,
    task_category="IMPLEMENT_FEATURE",
    complexity="MEDIUM",
    builder_mode="BUILD",
    scope={
        "chunk_number": config.get("chunk_number", "followup-4"),
        "deliverables": config.get("deliverables", {}),
        "features": config.get("features", []),
        "validation": config.get("validation", {}),
        "goals": config.get("goals", []),
    },
    tokens_used=0,
    builder_attempts=0,
    auditor_attempts=0,
    retry_attempt=0,
    created_at=datetime.now(timezone.utc),
    updated_at=datetime.now(timezone.utc),
)
db.add(phase)

db.commit()
print(f"Created retry-api-router-v1 run with {phase.phase_id} phase")
db.close()
