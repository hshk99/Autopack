"""
Create a run for FileOrganizer Phase 2 - Frontend Build System

This exercises Autopack's ability to:
1. Set up npm dependencies
2. Produce a production build
3. Package the Electron shell
4. Commit updated lockfiles/configs as needed
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API configuration
API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")

# Generate unique run ID
RUN_ID = f"fileorg-frontend-build-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

PHASES = [
    {
        "phase_id": "fileorg-p2-frontend-build",
        "phase_index": 0,
        "tier_id": "tier-frontend",
        "name": "Frontend Build System",
        "description": """Set up the FileOrganizer frontend build system per FUTURE_PLAN.md Task 2.

Goals:
- Install npm dependencies (node_modules not committed)
- Produce a production build (dist/)
- Package the Electron wrapper for desktop distribution
- Ensure package-lock.json is updated and committed

Project Location: .autonomous_runs/file-organizer-app-v1/
Target Files:
- fileorganizer/frontend/package.json
- fileorganizer/frontend/package-lock.json
- fileorganizer/frontend/vite.config.ts
- fileorganizer/frontend/electron/**
- fileorganizer/frontend/tsconfig*.json

Acceptance Criteria:
- `npm install` succeeds with no missing peer dependencies
- `npm run build` (Vite) succeeds and emits dist/
- Electron packaging script completes (document any manual signing steps)
- package-lock.json reflects latest dependency set
- Readme/build notes updated if commands change
""",
        "task_category": "frontend_build",
        "complexity": "medium",
        "builder_mode": "build_system",
        "scope": {
            "paths": [
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/package.json",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/package-lock.json",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/vite.config.ts",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/electron/",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/tsconfig.json",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/tsconfig.node.json",
            ],
            "read_only_context": [
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/src/",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/public/",
            ],
        },
    }
]

TIERS = [
    {
        "tier_id": "tier-frontend",
        "tier_index": 0,
        "name": "Frontend Build System",
        "description": "Set up npm/electron build flow for FileOrganizer",
    }
]


def create_run():
    """Create run for FileOrganizer frontend build system"""

    payload = {
        "run": {
            "run_id": RUN_ID,
            "run_type": "project_build",
            "safety_profile": "normal",
            "run_scope": "single_tier",
            "token_cap": 60000,
            "max_phases": 1,
            "max_duration_minutes": 45,
        },
        "tiers": TIERS,
        "phases": PHASES,
    }

    print(f"[INFO] Creating FileOrganizer frontend build run: {RUN_ID}")
    print(f"[INFO] Total phases: {len(PHASES)}\n")
    print("[INFO] This run will test Autopack's ability to:")
    print("  - Manage npm dependencies and lockfiles")
    print("  - Produce production-ready Vite builds")
    print("  - Package the Electron wrapper")
    print("  - Update build documentation as needed\n")
    print("[INFO] Target: .autonomous_runs/file-organizer-app-v1/fileorganizer/frontend/\n")

    headers = {}
    api_key = API_KEY or os.getenv("AUTOPACK_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.post(
            f"{API_URL}/runs/start",
            json=payload,
            headers=headers or None,
            timeout=30,
        )

        if response.status_code != 201:
            print(f"[ERROR] Response: {response.status_code}")
            print(f"[ERROR] Body: {response.text}")
            sys.exit(1)

        result = response.json()
        print(f"[SUCCESS] Run created: {RUN_ID}")
        print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}\n")
        print("[OK] Ready to execute autonomous run:")
        print(
            f"  PYTHONPATH=src python src/autopack/autonomous_executor.py "
            f"--run-id {RUN_ID} --run-type project_build --verbose  # (from repo root)"
        )
        print()
        return result

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot connect to API at {API_URL}")
        print("[INFO] Make sure the API server is running:\n  python -m uvicorn autopack.main:app --reload --port 8000")
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Failed to create run: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    create_run()

