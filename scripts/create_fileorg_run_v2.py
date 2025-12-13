"""
Create FileOrganizer Phase 2 Run (v2 - with error recovery)

Creates a fresh run from FUTURE_PLAN.md with all 9 tasks
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "fileorg-phase2-beta-20251201"

# 9 tasks from FUTURE_PLAN.md
TASKS = [
    {
        "phase_id": "fileorg-p2-test-fixes",
        "name": "Test Suite Fixes",
        "description": "Fix failing backend tests in test_pack_routes.py and test_classify_routes.py. Ensure all API endpoint tests pass with proper mocking and test data.",
        "tier_id": "T1-HighPriority",
        "tier_index": 0,
        "phase_index": 0,
        "category": "testing",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },
    {
        "phase_id": "fileorg-p2-frontend-build",
        "name": "Frontend Build System",
        "description": "Set up frontend build system with Vite/Webpack for React app. Configure dev server, production build, and static asset handling.",
        "tier_id": "T1-HighPriority",
        "tier_index": 0,
        "phase_index": 1,
        "category": "frontend",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },
    {
        "phase_id": "fileorg-p2-docker",
        "name": "Docker Deployment",
        "description": "Create Dockerfile and docker-compose.yml for containerized deployment. Include backend FastAPI service, frontend static serving, and PostgreSQL database.",
        "tier_id": "T2-Infrastructure",
        "tier_index": 1,
        "phase_index": 0,
        "category": "deployment",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-country-uk",
        "name": "UK Pack Templates",
        "description": "Create UK-specific document classification pack with categories: HMRC Tax Returns, NHS Records, Driving Licence, Passport, Bank Statements, Utility Bills. Include UK date formats and postal codes.",
        "tier_id": "T3-CountryPacks",
        "tier_index": 2,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-country-canada",
        "name": "Canada Pack Templates",
        "description": "Create Canada-specific document classification pack with categories: CRA Tax Forms, Health Card, Driver's License, Passport, Bank Statements, Hydro/Utility Bills. Include Canadian date formats and postal codes.",
        "tier_id": "T3-CountryPacks",
        "tier_index": 2,
        "phase_index": 1,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-country-australia",
        "name": "Australia Pack Templates",
        "description": "Create Australia-specific document classification pack with categories: ATO Tax Returns, Medicare Card, Driver's License, Passport, Bank Statements, Utility Bills. Include Australian date formats and postcodes.",
        "tier_id": "T3-CountryPacks",
        "tier_index": 2,
        "phase_index": 2,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-search",
        "name": "Advanced Search & Filtering",
        "description": "Implement advanced search API endpoint with filters for: date range, document type, confidence score, pack name, and full-text search on extracted text. Return paginated results.",
        "tier_id": "T4-Features",
        "tier_index": 3,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-batch-upload",
        "name": "Batch Upload & Processing",
        "description": "Create batch upload API endpoint that accepts multiple files, queues them for processing, and returns job IDs. Implement background task queue for parallel OCR and classification.",
        "tier_id": "T4-Features",
        "tier_index": 3,
        "phase_index": 1,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },
    {
        "phase_id": "fileorg-p2-auth",
        "name": "User Authentication",
        "description": "Implement user authentication with JWT tokens. Create login/logout endpoints, password hashing with bcrypt, and middleware to protect routes. Add user registration endpoint.",
        "tier_id": "T4-Features",
        "tier_index": 3,
        "phase_index": 2,
        "category": "backend",
        "complexity": "high",
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

    # Flatten phases for API (expects separate flat arrays)
    all_phases = []
    tier_list = []
    for tier in tiers.values():
        # Extract phases from tier
        all_phases.extend(tier["phases"])
        # Create tier without nested phases
        tier_list.append({
            "tier_id": tier["tier_id"],
            "tier_index": tier["tier_index"],
            "name": tier["name"],
            "description": tier.get("description")
        })

    # Create run payload
    payload = {
        "run": {
            "run_id": RUN_ID,
            "safety_profile": "standard",
            "run_scope": "multi_tier",
            "token_cap": 200000,
            "max_phases": 9,
            "max_duration_minutes": 600
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
