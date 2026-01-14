"""
Create a run for FileOrganizer Phase 2 - Docker Deployment

This exercises Autopack's ability to:
1. Author Dockerfile / docker-compose assets
2. Wire multi-container configs (backend + postgres + worker)
3. Generate deploy scripts and docs
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
RUN_ID = f"fileorg-docker-build-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

PHASES = [
    {
        "phase_id": "fileorg-p2-docker",
        "phase_index": 0,
        "tier_id": "tier-docker",
        "name": "Docker Deployment",
        "description": """Create Docker deployment configuration per FUTURE_PLAN.md Task 3.

Goals:
- Backend Dockerfile (Python 3.11 + dependencies)
- docker-compose.yml orchestrating backend + database + optional worker
- .dockerignore to keep images slim
- deploy.sh helper for local/prod runs
- Update DEPLOYMENT_GUIDE.md with instructions
- Validate `docker compose up --build` locally

Project Location: .autonomous_runs/file-organizer-app-v1/
Target Files:
- fileorganizer/backend/Dockerfile
- fileorganizer/docker-compose.yml
- fileorganizer/.dockerignore
- fileorganizer/deploy.sh
- fileorganizer/DEPLOYMENT_GUIDE.md

Acceptance Criteria:
- `docker compose build` succeeds without missing dependencies
- Backend container starts and exposes API on configured port
- Database service reachable via compose
- deploy.sh documents ENV and common commands
- DEPLOYMENT_GUIDE.md explains build/run, env vars, troubleshooting
""",
        "task_category": "deployment",
        "complexity": "medium",
        "builder_mode": "build_system",
        "scope": {
            "paths": [
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/Dockerfile",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/docker-compose.yml",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/.dockerignore",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/deploy.sh",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/DEPLOYMENT_GUIDE.md",
            ],
            "read_only_context": [
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/app/",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend/requirements.txt",
                ".autonomous_runs/file-organizer-app-v1/fileorganizer/README.md",
            ],
        },
        "ci": {
            "type": "pytest",
            "workdir": ".autonomous_runs/file-organizer-app-v1/fileorganizer/backend",
            "paths": ["tests"],
            "args": ["-vv"],
            "env": {"PYTHONPATH": ".", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            "timeout_seconds": 600,
            "log_name": "backend_pytest.log",
            "success_message": "Backend pytest suite passed",
            "failure_message": "Backend pytest suite failed",
        },
    }
]

TIERS = [
    {
        "tier_id": "tier-docker",
        "tier_index": 0,
        "name": "Docker Deployment",
        "description": "Produce container + compose assets for FileOrganizer",
    }
]


def create_run():
    """Create run for FileOrganizer Docker deployment task"""

    payload = {
        "run": {
            "run_id": RUN_ID,
            "run_type": "project_build",
            "safety_profile": "normal",
            "run_scope": "single_tier",
            "token_cap": 70000,
            "max_phases": 1,
            "max_duration_minutes": 60,
        },
        "tiers": TIERS,
        "phases": PHASES,
    }

    print(f"[INFO] Creating FileOrganizer docker run: {RUN_ID}")
    print(f"[INFO] Total phases: {len(PHASES)}\n")
    print("[INFO] This run will test Autopack's ability to:")
    print("  - Build container images + compose stack")
    print("  - Generate deployment documentation/scripts")
    print("  - Respect scope-limited file edits\n")
    print("[INFO] Target: .autonomous_runs/file-organizer-app-v1/fileorganizer/\n")

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
        print(
            "[INFO] Make sure the API server is running:\n  python -m uvicorn autopack.main:app --reload --port 8000"
        )
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Failed to create run: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    create_run()
