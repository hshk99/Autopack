"""
Create a test run for FileOrganizer Phase 2 - Test Suite Fixes

This tests Autopack's ability to:
1. Fix dependency conflicts
2. Update configuration files
3. Ensure all tests pass
4. Work with an existing codebase
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
RUN_ID = f"fileorg-test-suite-fix-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

# Test phase based on WHATS_LEFT_TO_BUILD.md Task 1
PHASES = [
    {
        "phase_id": "fileorg-p2-test-fixes",
        "phase_index": 0,
        "tier_id": "tier-1",
        "name": "Fix FileOrganizer Test Suite",
        "description": """Fix test suite dependency conflicts in the FileOrganizer project.

Current Issue:
- 12 test files exist but have dependency conflicts
- httpx/starlette version issues preventing tests from running
- requirements.txt needs version compatibility fixes

Tasks:
1. Analyze requirements.txt and identify conflicting dependencies
2. Research compatible versions of httpx, starlette, fastapi, and pytest
3. Update requirements.txt with compatible version pins
4. Ensure pytest.ini has proper configuration
5. Run pytest to verify all 12 test files pass
6. Document any breaking changes or necessary test updates

Project Location: .autonomous_runs/file-organizer-app-v1/
Target Files:
- backend/requirements.txt (update dependency versions)
- backend/pytest.ini (ensure proper config)
- backend/tests/*.py (fix if needed)

Acceptance Criteria:
- All 12 test files passing with pytest
- No dependency conflict errors
- requirements.txt has compatible version pins
- pytest.ini properly configured

This is a real codebase test - validate that Autopack can fix dependency issues in an existing project.""",
        "task_category": "core_backend_high",
        "complexity": "low",
        "builder_mode": None,
        "scope": {
            "paths": [
                ".autonomous_runs/file-organizer-app-v1/backend/requirements.txt",
                ".autonomous_runs/file-organizer-app-v1/backend/pytest.ini"
            ],
            "read_only_context": [
                ".autonomous_runs/file-organizer-app-v1/backend/tests/",
                ".autonomous_runs/file-organizer-app-v1/backend/app/"
            ]
        }
    }
]

TIERS = [
    {
        "tier_id": "tier-1",
        "tier_index": 0,
        "name": "FileOrganizer Test Suite Fix",
        "description": "Fix dependency conflicts and get test suite passing"
    }
]


def create_run():
    """Create test run for FileOrganizer test suite fixes"""

    payload = {
        "run": {
            "run_id": RUN_ID,
            "run_type": "project_build",  # Not autopack_maintenance - external project
            "safety_profile": "normal",
            "run_scope": "single_tier",
            "token_cap": 50000,  # Estimated 8k, giving 6x buffer
            "max_phases": 1,
            "max_duration_minutes": 30
        },
        "tiers": TIERS,
        "phases": PHASES
    }

    print(f"[INFO] Creating FileOrganizer test run: {RUN_ID}")
    print(f"[INFO] Total phases: {len(PHASES)}")
    print()
    print("[INFO] This run will test Autopack's ability to:")
    print("  - Fix dependency conflicts in an existing codebase")
    print("  - Update configuration files (requirements.txt, pytest.ini)")
    print("  - Work with external projects (not autopack/ itself)")
    print("  - Validate test suite functionality")
    print()
    print(f"[INFO] Target: .autonomous_runs/file-organizer-app-v1/backend/")
    print()

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    elif os.getenv("AUTOPACK_API_KEY"):
        headers["X-API-Key"] = os.getenv("AUTOPACK_API_KEY")

    try:
        response = requests.post(
            f"{API_URL}/runs/start",
            json=payload,
            headers=headers if headers else None,
            timeout=30
        )

        if response.status_code != 201:
            print(f"[ERROR] Response: {response.status_code}")
            print(f"[ERROR] Body: {response.text}")
            sys.exit(1)

        result = response.json()
        print(f"[SUCCESS] Run created: {RUN_ID}")
        print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}")
        print()
        print("[OK] Ready to execute autonomous run:")
        print(f"  cd C:\\dev\\Autopack && PYTHONPATH=src python src/autopack/autonomous_executor.py --run-id {RUN_ID} --run-type project_build --verbose")
        print()
        return result

    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Cannot connect to API at {API_URL}")
        print("[INFO] Make sure the API server is running:")
        print("  python -m uvicorn autopack.main:app --reload --port 8000")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to create run: {e}")
        sys.exit(1)


if __name__ == "__main__":
    create_run()
