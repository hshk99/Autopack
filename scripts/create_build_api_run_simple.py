#!/usr/bin/env python3
"""
Create run to complete the Runs Management API.

Minimal API bootstrap is complete (3 endpoints). Now Autopack will:
1. Add remaining CRUD endpoints (POST /runs, DELETE /runs, etc.)
2. Add list/search endpoints
3. Add comprehensive error handling
4. Add API documentation
5. Add tests
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState


def create_run():
    run_id = "build-complete-runs-api"

    session = SessionLocal()
    try:
        # Check if exists
        existing = session.query(Run).filter(Run.id == run_id).first()
        if existing:
            print(f"✅ Run already exists: {run_id}")
            return 0

        # Create run
        run = Run(
            id=run_id,
            state=RunState.RUN_CREATED,
            safety_profile="normal",
            run_scope="single_tier",
            goal_anchor="Complete Runs Management API with all CRUD operations"
        )
        session.add(run)
        session.flush()

        # Create tier
        tier = Tier(
            tier_id="api-completion",
            run_id=run_id,
            tier_index=0,
            name="API Completion",
            description="Add remaining endpoints to Runs API"
        )
        session.add(tier)
        session.flush()

        # Phase 1: Add POST /runs endpoint
        phase1 = Phase(
            phase_id="add_post_runs",
            run_id=run_id,
            tier_id=tier.id,
            phase_index=0,
            name="Add POST /runs Endpoint",
            description="""Add POST /runs endpoint to create new runs via API.

CONTEXT:
- Minimal API exists with GET /runs/{run_id} and update endpoints
- Need POST endpoint to create runs programmatically
- Currently runs must be created via direct database insertion

TASK:
Add to src/backend/api/runs.py:

1. Pydantic request schema:
   class CreateRunRequest(BaseModel):
       id: str  # run_id
       goal_anchor: Optional[str] = None
       safety_profile: str = "normal"
       run_scope: str = "multi_tier"

2. POST /runs endpoint:
   @router.post("")
   def create_run(request: CreateRunRequest, db: Session = Depends(get_db)):
       # Check if run exists
       # Create Run object
       # Return created run

ACCEPTANCE CRITERIA:
- POST /runs creates run in database
- Returns 409 if run_id already exists
- Returns created run JSON

TEST:
curl -X POST http://localhost:8000/runs \\
  -H "Content-Type: application/json" \\
  -d '{"id": "test-run", "goal_anchor": "Test goal"}'
""",
            state=PhaseState.QUEUED,
            task_category="feature",
            complexity="low",
            builder_mode="tweak_light"
        )
        session.add(phase1)

        # Phase 2: Add POST /runs/{run_id}/phases endpoint
        phase2 = Phase(
            phase_id="add_post_phases",
            run_id=run_id,
            tier_id=tier.id,
            phase_index=1,
            name="Add POST Phases Endpoint",
            description="""Add POST /runs/{run_id}/phases to create phases.

TASK:
Add to src/backend/api/runs.py:

1. Pydantic schema:
   class CreatePhaseRequest(BaseModel):
       phase_id: str
       tier_id: int  # Database tier ID (not tier_id string)
       phase_index: int
       name: str
       description: Optional[str] = None
       task_category: Optional[str] = None
       complexity: Optional[str] = None
       builder_mode: Optional[str] = None

2. POST /runs/{run_id}/phases endpoint:
   Create phase in database
   Return created phase

ACCEPTANCE CRITERIA:
- Creates phase linked to run
- Returns 404 if run not found
- Returns created phase JSON
""",
            state=PhaseState.QUEUED,
            task_category="feature",
            complexity="low",
            builder_mode="tweak_light"
        )
        session.add(phase2)

        # Phase 3: Add GET /runs list endpoint
        phase3 = Phase(
            phase_id="add_list_runs",
            run_id=run_id,
            tier_id=tier.id,
            phase_index=2,
            name="Add GET /runs List Endpoint",
            description="""Add GET /runs to list all runs.

TASK:
Add to src/backend/api/runs.py:

@router.get("")
def list_runs(
    limit: int = 50,
    offset: int = 0,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Run)
    if state:
        query = query.filter(Run.state == RunState(state))

    runs = query.offset(offset).limit(limit).all()

    return {
        "runs": [serialize_run(r) for r in runs],
        "total": query.count(),
        "limit": limit,
        "offset": offset
    }

ACCEPTANCE CRITERIA:
- Returns list of runs
- Supports pagination
- Supports state filter
""",
            state=PhaseState.QUEUED,
            task_category="feature",
            complexity="low",
            builder_mode="tweak_light"
        )
        session.add(phase3)

        # Phase 4: Add documentation
        phase4 = Phase(
            phase_id="add_api_docs",
            run_id=run_id,
            tier_id=tier.id,
            phase_index=3,
            name="Add API Documentation",
            description="""Document the Runs API for future users.

TASK:
Create docs/RUNS_API.md with:

1. Overview
2. Bootstrap Story (how minimal API was built to solve chicken-egg problem)
3. Endpoint Reference:
   - GET /runs - list runs
   - POST /runs - create run
   - GET /runs/{run_id} - get run details
   - PUT /runs/{run_id}/phases/{phase_id} - update phase
   - POST /runs/{run_id}/phases - create phase
   - POST /runs/{run_id}/phases/{phase_id}/builder_result - submit result
4. Example Workflow
5. Integration with Autonomous Executor

ACCEPTANCE CRITERIA:
- Documentation complete
- Examples are copy-pasteable
- Bootstrap story documented
""",
            state=PhaseState.QUEUED,
            task_category="documentation",
            complexity="low"
        )
        session.add(phase4)

        session.commit()
        print(f"✅ Created run: {run_id}")
        print("   Phases: 4")
        print("\n🚀 Start autonomous executor:")
        print("  cd c:/dev/Autopack")
        print("  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\" \\")
        print("  QDRANT_HOST=\"http://localhost:6333\" python -m autopack.autonomous_executor \\")
        print(f"  --run-id {run_id} --api-url http://localhost:8000 --poll-interval 15")
        return 0

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(create_run())
