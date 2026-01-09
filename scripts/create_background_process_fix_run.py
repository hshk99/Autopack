#!/usr/bin/env python3
"""
Create Autopack run to diagnose and fix background process issues.

PROBLEM ANALYSIS:
1. Three restoration runs are stuck in infinite retry loops (404 errors)
2. Runs are trying to fetch status from API but runs don't exist
3. API server is running but `/runs` endpoint returns 404
4. Root cause: Restoration runs were started before runs were created in API

SOLUTION:
Let Autopack autonomously:
1. Investigate API endpoint implementation
2. Create the missing runs in the database/API
3. Verify restoration can proceed
4. Document process improvements
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API configuration
API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")

RUN_ID = "fix-background-process-404-errors"


def main():
    if not API_KEY:
        print("Error: AUTOPACK_API_KEY not set in environment")
        return 1

    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

    # Create run
    run_payload = {
        "run_id": RUN_ID,
        "goal": "Diagnose and fix background restoration processes stuck with 404 errors",
        "context": {
            "project": "autopack_maintenance",
            "issue": "background_process_404_errors",
            "affected_runs": [
                "research-system-restore-and-evaluate-v2",
                "research-system-restore-and-evaluate-v3"
            ],
            "symptom": "Restoration runs stuck in infinite retry loops (404 errors)",
            "root_cause": "Runs started before being created in API/database"
        }
    }

    response = requests.post(f"{API_URL}/runs", json=run_payload, headers=headers)
    if response.status_code != 200:
        print(f"Error creating run: {response.status_code} - {response.text}")
        return 1

    print(f"✅ Created run: {RUN_ID}")

    # Define phases
    phases = [
        {
            "phase_id": "investigate_api_endpoints",
            "phase_index": 0,
            "tier_id": "tier-investigation",
            "name": "Investigate API Endpoints",
            "description": """Investigate why API `/runs` endpoint returns 404.

CONTEXT:
- API server is running on port 8000
- `/runs` endpoint returns {"detail": "Not Found"}
- Restoration runs can't fetch their status

TASK:
1. Find main API file (likely backend/main.py or src/autopack/api/main.py)
2. Check if `/runs` endpoint is implemented
3. Check if FastAPI app is properly configured
4. Identify why endpoint returns 404

ACCEPTANCE CRITERIA:
- Located API main file
- Identified missing or misconfigured endpoint
- Documented root cause of 404 error

DO NOT FIX YET - Just investigate and report findings.""",
            "category": "investigation",
            "status": "PENDING",
            "metadata": {
                "complexity": "low",
                "estimated_tokens": 2000,
                "files_to_check": [
                    "backend/main.py",
                    "src/autopack/api/main.py",
                    "src/autopack/api/routes.py"
                ]
            }
        },
        {
            "phase_id": "create_missing_runs",
            "phase_index": 1,
            "tier_id": "tier-fix",
            "name": "Create Missing Runs in Database",
            "description": """Create the missing restoration runs in the database/API.

CONTEXT:
- research-system-restore-and-evaluate-v2 doesn't exist in API
- research-system-restore-and-evaluate-v3 doesn't exist in API
- script exists: scripts/create_research_restoration_v2_run.py
- Need to execute script or create runs directly

TASK:
If API endpoints are working after Phase 1 investigation:
1. Execute scripts/create_research_restoration_v2_run.py to create v2 run
2. Create v3 run (similar to v2 but with BUILD-040 enhancements)

If API endpoints need fixing:
1. Document what needs to be fixed
2. Create runs via direct database insertion if possible

ACCEPTANCE CRITERIA:
- research-system-restore-and-evaluate-v2 run exists in API/database
- research-system-restore-and-evaluate-v3 run exists in API/database
- GET /runs/{run_id} returns valid response for both runs

REFERENCE:
- scripts/create_research_restoration_v2_run.py (template for run creation)
- See phases and tiers structure in that file""",
            "category": "fix",
            "status": "PENDING",
            "metadata": {
                "complexity": "medium",
                "estimated_tokens": 4000,
                "dependencies": ["investigate_api_endpoints"]
            }
        },
        {
            "phase_id": "restart_restoration_runs",
            "phase_index": 2,
            "tier_id": "tier-fix",
            "name": "Restart Restoration Processes",
            "description": """Restart the restoration runs now that they exist in the API.

CONTEXT:
- Background processes were killed to stop infinite retry loops
- Runs now exist in API/database
- Need to restart autonomous executor for both runs

TASK:
1. Start research-system-restore-and-evaluate-v2:
   cd c:/dev/Autopack && PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python -m autopack.autonomous_executor --run-id research-system-restore-and-evaluate-v2 --poll-interval 15 --run-type autopack_maintenance

2. Start research-system-restore-and-evaluate-v3:
   cd c:/dev/Autopack && PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python -m autopack.autonomous_executor --run-id research-system-restore-and-evaluate-v3 --poll-interval 15 --run-type autopack_maintenance

3. Monitor both for 30 seconds to verify no 404 errors

ACCEPTANCE CRITERIA:
- Both restoration runs started successfully
- No 404 errors in first 30 seconds
- Runs can fetch their status from API

EXPECTED OUTCOME:
- Restoration processes run successfully
- Research system components restored
- Phase 1 evaluation completes""",
            "category": "execution",
            "status": "PENDING",
            "metadata": {
                "complexity": "low",
                "estimated_tokens": 2000,
                "dependencies": ["create_missing_runs"]
            }
        },
        {
            "phase_id": "document_process_improvements",
            "phase_index": 3,
            "tier_id": "tier-documentation",
            "name": "Document Process Improvements",
            "description": """Document lessons learned and process improvements.

CONTEXT:
- Background processes failed due to missing API runs
- This could happen again in future

TASK:
Create docs/BACKGROUND_PROCESS_BEST_PRACTICES.md with:

1. **Root Cause Analysis**:
   - What went wrong (runs started before API creation)
   - Why it happened (manual process gap)

2. **Prevention Guidelines**:
   - ALWAYS create run via API before starting autonomous executor
   - Run creation scripts should be executed FIRST
   - Verify run exists before starting executor

3. **Troubleshooting Guide**:
   - How to detect stuck background processes
   - How to check if run exists in API
   - How to safely kill and restart processes

4. **Best Practices**:
   - Pre-flight checklist for starting restoration runs
   - Monitoring recommendations
   - Error recovery procedures

ACCEPTANCE CRITERIA:
- Documentation file created
- Clear guidelines for future run creation
- Troubleshooting guide comprehensive

REFERENCE:
- This issue as case study
- scripts/create_research_restoration_v2_run.py as example""",
            "category": "documentation",
            "status": "PENDING",
            "metadata": {
                "complexity": "low",
                "estimated_tokens": 3000
            }
        }
    ]

    # Create phases
    for phase in phases:
        response = requests.post(f"{API_URL}/runs/{RUN_ID}/phases", json=phase, headers=headers)
        if response.status_code != 200:
            print(f"Error creating phase {phase['phase_id']}: {response.status_code} - {response.text}")
            return 1
        print(f"  ✅ Created phase: {phase['phase_id']}")

    print("\n🚀 Run created successfully!")
    print(f"   Run ID: {RUN_ID}")
    print(f"   Phases: {len(phases)}")
    print("\nTo execute:")
    print(f"  cd c:/dev/Autopack && PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\" QDRANT_HOST=\"http://localhost:6333\" python -m autopack.autonomous_executor --run-id {RUN_ID} --poll-interval 15 --run-type autopack_maintenance")

    return 0


if __name__ == "__main__":
    sys.exit(main())
