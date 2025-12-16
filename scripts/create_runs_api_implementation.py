#!/usr/bin/env python3
"""
Create Autopack run to build complete Runs Management API.

This will enable autonomous executor to work properly by implementing
the missing /runs endpoints that are currently returning 404.

GOAL: Make Autopack truly autonomous and reusable for future projects.
"""
import os
import sys
import json
from pathlib import Path

# Since API doesn't work, we'll create the run directly in database
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState


def create_run_direct():
    """Create run directly in database since API doesn't exist yet."""

    run_id = "build-runs-management-api"

    # Note: Run.id is the primary key (not run_id, which is a synonym)
    # Create run with minimal required fields

    # Phases
    phases = [
        {
            "phase_id": "create_database_models",
            "phase_index": 0,
            "name": "Create Database Models",
            "description": """Create SQLAlchemy models for runs management.

CONTEXT:
- src/backend/database.py exists with Base and engine
- Need models for: AutonomousRun, Phase, Tier
- These models will back the /runs API

TASK:
Create src/backend/models/runs.py with:

1. AutonomousRun model:
   - id (primary key)
   - run_id (unique string, indexed)
   - goal (text)
   - status (enum: PENDING, RUNNING, PAUSED, COMPLETED, FAILED)
   - run_type (string)
   - context (JSON)
   - created_at (datetime)
   - updated_at (datetime)
   - completed_at (datetime, nullable)

2. Tier model:
   - id (primary key)
   - run_id (foreign key to AutonomousRun.run_id)
   - tier_id (string)
   - tier_index (integer)
   - name (string)
   - description (text)
   - status (enum: PENDING, IN_PROGRESS, COMPLETED, FAILED)

3. Phase model:
   - id (primary key)
   - run_id (foreign key to AutonomousRun.run_id)
   - tier_id (foreign key to Tier.tier_id)
   - phase_id (string)
   - phase_index (integer)
   - name (string)
   - description (text)
   - instructions (text, nullable)
   - category (string)
   - status (enum: PENDING, IN_PROGRESS, COMPLETED, FAILED, BLOCKED)
   - complexity (string, nullable)
   - builder_mode (string, nullable)
   - scope (JSON, nullable)
   - metadata (JSON, nullable)
   - retry_count (integer, default 0)
   - max_retries (integer, default 3)
   - started_at (datetime, nullable)
   - completed_at (datetime, nullable)

4. Update src/backend/models/__init__.py to export models

5. Create Alembic migration to create tables

ACCEPTANCE CRITERIA:
- Models defined with proper relationships
- All fields have correct types and constraints
- Migration script created
- Models import successfully

REFERENCE:
- src/backend/database.py (Base, engine)
- Similar patterns in existing models""",
            "category": "feature",
            "status": "PENDING",
            "complexity": "medium",
            "metadata": json.dumps({
                "estimated_tokens": 4000,
                "files_to_create": [
                    "src/backend/models/runs.py",
                    "src/backend/models/__init__.py"
                ]
            })
        },
        {
            "phase_id": "create_runs_api_router",
            "phase_index": 1,
            "name": "Create Runs API Router",
            "description": """Create FastAPI router for runs management endpoints.

CONTEXT:
- src/backend/main.py has app and includes routers
- Need full CRUD for runs, phases, tiers
- Autonomous executor expects specific endpoint structure

TASK:
Create src/backend/api/runs.py with these endpoints:

1. POST /runs
   - Create new run
   - Input: run_id, goal, context, run_type
   - Returns: created run object

2. GET /runs
   - List all runs
   - Query params: status (filter), limit, offset
   - Returns: list of runs

3. GET /runs/{run_id}
   - Get specific run details
   - Include phases and tiers
   - Returns: run with nested phases/tiers

4. PUT /runs/{run_id}
   - Update run status/metadata
   - Input: status, context updates
   - Returns: updated run

5. DELETE /runs/{run_id}
   - Soft delete run
   - Returns: success message

6. POST /runs/{run_id}/phases
   - Add phase to run
   - Input: phase details
   - Returns: created phase

7. GET /runs/{run_id}/phases
   - List phases for run
   - Returns: list of phases

8. PUT /runs/{run_id}/phases/{phase_id}
   - Update phase status
   - Input: status, metadata updates
   - Returns: updated phase

9. POST /runs/{run_id}/tiers
   - Add tier to run
   - Input: tier details
   - Returns: created tier

IMPLEMENTATION DETAILS:
- Use FastAPI dependency injection for DB session
- Proper error handling (404, 400, 500)
- Pydantic schemas for request/response validation
- Include proper status codes
- Add API documentation via docstrings

ACCEPTANCE CRITERIA:
- All endpoints implemented
- Proper error handling
- OpenAPI docs generated automatically
- Endpoints tested manually with curl

REFERENCE:
- src/backend/api/auth.py (example router)
- src/backend/api/search.py (example router)
- FastAPI dependency injection patterns""",
            "category": "feature",
            "status": "PENDING",
            "complexity": "high",
            "metadata": json.dumps({
                "estimated_tokens": 6000,
                "files_to_create": [
                    "src/backend/api/runs.py",
                    "src/backend/schemas/runs.py"
                ]
            })
        },
        {
            "phase_id": "integrate_runs_router",
            "phase_index": 2,
            "name": "Integrate Runs Router into Main App",
            "description": """Add runs router to main FastAPI application.

CONTEXT:
- src/backend/main.py currently only includes auth and search routers
- Need to add runs router

TASK:
Modify src/backend/main.py:

1. Import runs router:
   from .api.runs import router as runs_router

2. Include router:
   app.include_router(runs_router, prefix="/runs", tags=["runs"])

3. Verify API server restarts properly

ACCEPTANCE CRITERIA:
- Router imported and included
- API server starts without errors
- /docs shows runs endpoints
- GET /runs returns 200 (empty list is fine)

TESTING:
curl http://localhost:8000/runs
curl http://localhost:8000/docs""",
            "category": "integration",
            "status": "PENDING",
            "complexity": "low",
            "metadata": json.dumps({
                "estimated_tokens": 1500,
                "files_to_modify": ["src/backend/main.py"]
            })
        },
        {
            "phase_id": "test_api_with_autonomous_executor",
            "phase_index": 3,
            "name": "Test API with Autonomous Executor",
            "description": """Verify autonomous executor can use the new API.

CONTEXT:
- API is now implemented
- Need to verify autonomous executor integration
- Use simple test run to validate

TASK:
1. Create a simple test run via API:
   POST http://localhost:8000/runs
   Body: {
     "run_id": "api-test-simple",
     "goal": "Test run to verify API works",
     "context": {"test": true},
     "run_type": "test"
   }

2. Add a test phase:
   POST http://localhost:8000/runs/api-test-simple/phases
   Body: {
     "phase_id": "test_phase",
     "phase_index": 0,
     "name": "Test Phase",
     "description": "Simple test phase that does nothing",
     "category": "test",
     "status": "PENDING"
   }

3. Verify GET /runs/api-test-simple returns run with phase

4. Try starting autonomous executor (it should be able to fetch run):
   cd c:/dev/Autopack
   PYTHONUTF8=1 PYTHONPATH=src python -m autopack.autonomous_executor --run-id api-test-simple --poll-interval 5 --run-type test

   Let it run for 10 seconds, then kill it

5. Verify no 404 errors in executor output

ACCEPTANCE CRITERIA:
- Test run created via API
- Autonomous executor can fetch run status
- No 404 errors
- Executor can read phases

SUCCESS METRIC:
If executor runs without 404 errors, API is working!""",
            "category": "test",
            "status": "PENDING",
            "complexity": "medium",
            "metadata": json.dumps({
                "estimated_tokens": 3000,
                "validation": "no_404_errors_in_executor"
            })
        },
        {
            "phase_id": "create_restoration_runs_via_api",
            "phase_index": 4,
            "name": "Create Restoration Runs via API",
            "description": """Now that API works, create the restoration runs properly.

CONTEXT:
- API is working
- scripts/create_research_restoration_v2_run.py exists
- Can now create runs properly

TASK:
1. Execute existing creation script:
   cd c:/dev/Autopack
   PYTHONUTF8=1 python scripts/create_research_restoration_v2_run.py

2. Verify run was created:
   curl http://localhost:8000/runs/research-system-restore-and-evaluate-v2

3. Create v3 variant (copy script and modify for BUILD-040):
   - Copy script to create_research_restoration_v3_run.py
   - Change RUN_ID to "research-system-restore-and-evaluate-v3"
   - Update descriptions to mention BUILD-040
   - Execute script

4. Verify both runs exist in API

ACCEPTANCE CRITERIA:
- research-system-restore-and-evaluate-v2 exists in API
- research-system-restore-and-evaluate-v3 exists in API
- Both runs have phases
- GET /runs returns both runs

NEXT STEPS:
After this, restoration runs can be started with autonomous executor.""",
            "category": "execution",
            "status": "PENDING",
            "complexity": "low",
            "metadata": json.dumps({
                "estimated_tokens": 2000,
                "dependencies": ["test_api_with_autonomous_executor"]
            })
        },
        {
            "phase_id": "document_api_usage",
            "phase_index": 5,
            "name": "Document API Usage",
            "description": """Create documentation for using the Runs API.

CONTEXT:
- Runs API is now complete
- Future developers need to know how to use it

TASK:
Create docs/RUNS_API_GUIDE.md with:

1. **Overview**:
   - What the Runs API does
   - Why it's needed for autonomous executor

2. **Creating a Run**:
   - POST /runs example
   - Required fields explained
   - Context structure guidelines

3. **Adding Phases**:
   - POST /runs/{run_id}/phases example
   - Phase structure explained
   - Status lifecycle (PENDING → IN_PROGRESS → COMPLETED/FAILED)

4. **Adding Tiers**:
   - POST /runs/{run_id}/tiers example
   - Tier vs Phase distinction

5. **Running with Autonomous Executor**:
   - Command format
   - Environment variables needed
   - Monitoring run progress

6. **Troubleshooting**:
   - Common errors and fixes
   - How to check if API is running
   - How to verify run exists before starting executor

7. **Example Workflow**:
   - Complete example from creating run to completion
   - Use research restoration as case study

ACCEPTANCE CRITERIA:
- Documentation complete and clear
- Examples are copy-pasteable
- Troubleshooting section comprehensive

REFERENCE:
- This implementation as case study
- scripts/create_research_restoration_v2_run.py as example""",
            "category": "documentation",
            "status": "PENDING",
            "complexity": "low",
            "metadata": json.dumps({
                "estimated_tokens": 3000,
                "output_file": "docs/RUNS_API_GUIDE.md"
            })
        }
    ]

    # Create in database
    try:
        session = get_session()

        # Create run
        run = AutonomousRun(**run_data)
        session.add(run)
        session.flush()

        # Create phases
        for phase_data in phases:
            phase_data["run_id"] = run_id
            phase = Phase(**phase_data)
            session.add(phase)

        session.commit()
        print(f"✅ Created run directly in database: {run_id}")
        print(f"   Phases: {len(phases)}")
        print(f"\n🚀 Run created!")
        print(f"\nTo execute:")
        print(f"  cd c:/dev/Autopack")
        print(f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\" \\")
        print(f"  QDRANT_HOST=\"http://localhost:6333\" python -m autopack.autonomous_executor \\")
        print(f"  --run-id {run_id} --poll-interval 15 --run-type autopack_core_development")
        return 0

    except Exception as e:
        print(f"❌ Error creating run: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(create_run_direct())
