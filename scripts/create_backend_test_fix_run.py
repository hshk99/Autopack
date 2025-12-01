"""
Create Autopack Run for File-Organizer Backend Test Fixes

Creates a run to fix the 4 backend test collection errors:
1. Pydantic Settings issue - needs extra="ignore"
2. Missing python-magic dependency
3. Missing celery dependency
4. Settings validation errors
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "fileorg-backend-tests-fix-20251130"

# Tasks to fix backend test issues
TASKS = [
    {
        "phase_id": "backend-config-fix",
        "name": "Fix Backend Settings Configuration",
        "description": """Fix src/backend/config.py to allow extra fields from .env file.

The Settings class needs `extra = "ignore"` in its Config to allow extra environment
variables from .env without validation errors. Currently getting:
- Extra inputs are not permitted for: openai_api_key, anthropic_api_key, autopack_api_key, etc.

Update the Settings class Config to match src/autopack/config.py pattern.""",
        "tier_id": "T1-Config",
        "tier_index": 0,
        "phase_index": 0,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },
    {
        "phase_id": "backend-requirements-fix",
        "name": "Add Missing Dependencies",
        "description": """Add missing dependencies to src/backend/requirements.txt:

1. python-magic-bin (for Windows) or python-magic - Used by src/backend/services/file_validator.py
2. celery - Used by src/backend/services/task_queue.py
3. redis - Celery backend

Also update the main requirements.txt if needed.""",
        "tier_id": "T1-Config",
        "tier_index": 0,
        "phase_index": 1,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },
    {
        "phase_id": "backend-test-isolation",
        "name": "Fix Backend Test Isolation",
        "description": """Ensure backend tests can run in isolation:

1. Check tests/backend/ test files for proper test database setup
2. Add conftest.py if missing with proper fixtures
3. Ensure tests don't depend on external services (mock Redis/Celery if needed)
4. Add TESTING environment variable checks where appropriate""",
        "tier_id": "T2-Tests",
        "tier_index": 1,
        "phase_index": 0,
        "category": "testing",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    }
]

def create_run():
    """Create run with all tasks"""
    # Group tasks by tier
    tiers = {}
    for task in TASKS:
        tier_id = task["tier_id"]
        if tier_id not in tiers:
            tiers[tier_id] = {
                "tier_id": tier_id,
                "tier_index": task["tier_index"],
                "name": tier_id.split("-")[1],
                "description": f"Tier {task['tier_index'] + 1}",
                "phases": []
            }
        tiers[tier_id]["phases"].append({
            "phase_id": task["phase_id"],
            "phase_index": task["phase_index"],
            "tier_id": tier_id,
            "name": task["name"],
            "description": task["description"],
            "task_category": task["category"],
            "complexity": task["complexity"],
            "builder_mode": task["builder_mode"]
        })

    # Flatten phases for API
    all_phases = []
    tier_list = []
    for tier in tiers.values():
        all_phases.extend(tier["phases"])
        tier_list.append({
            "tier_id": tier["tier_id"],
            "tier_index": tier["tier_index"],
            "name": tier["name"],
            "description": tier.get("description")
        })

    payload = {
        "run": {
            "run_id": RUN_ID,
            "safety_profile": "standard",
            "run_scope": "multi_tier",
            "token_cap": 100000,
            "max_phases": 5,
            "max_duration_minutes": 60
        },
        "tiers": tier_list,
        "phases": all_phases
    }

    print(f"[INFO] Creating run: {RUN_ID}")
    print(f"[INFO] Total tasks: {len(TASKS)}")
    print(f"[INFO] Total tiers: {len(tiers)}")

    response = requests.post(
        f"{API_URL}/runs/start",
        json=payload
    )

    if response.status_code != 201:
        print(f"[ERROR] Response: {response.status_code}")
        print(f"[ERROR] Body: {response.text}")

    response.raise_for_status()

    print(f"[SUCCESS] Run created: {RUN_ID}")
    print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}")
    return response.json()


if __name__ == "__main__":
    try:
        result = create_run()
        print("\n[OK] Ready to execute autonomous run:")
        print(f"  python src/autopack/autonomous_executor.py --run-id {RUN_ID}")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to create run: {e}")
        sys.exit(1)
