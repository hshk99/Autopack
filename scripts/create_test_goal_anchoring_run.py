"""
Create a test run to exercise the new Goal Anchoring and Validation features.

This run includes phases that will:
1. Test goal anchoring (phases that might trigger replanning)
2. Test validation logic (Python file modifications)
3. Test token soft caps (automatically)
"""

import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# API configuration
API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")

# Generate unique run ID
RUN_ID = f"test-goal-anchoring-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

# Test phases that will exercise the new features
PHASES = [
    {
        "phase_id": "test-1-simple-modification",
        "phase_index": 0,
        "tier_id": "tier-1",
        "name": "Simple Python File Modification",
        "description": "Add a simple utility function to src/autopack/config.py that returns the current config version. This will test symbol preservation validation.",
        "task_category": "core_backend_high",
        "complexity": "low",
        "builder_mode": None,
    },
    {
        "phase_id": "test-2-medium-complexity",
        "phase_index": 1,
        "tier_id": "tier-1",
        "name": "Medium Complexity Feature",
        "description": "Add a new helper function to src/autopack/llm_service.py that logs token usage statistics. This will test token soft caps and structural similarity validation.",
        "task_category": "core_backend_high",
        "complexity": "medium",
        "builder_mode": None,
    },
    {
        "phase_id": "test-3-potential-replan",
        "phase_index": 2,
        "tier_id": "tier-1",
        "name": "Feature That Might Trigger Replanning",
        "description": "Add comprehensive error handling to the goal anchoring system in autonomous_executor.py. This phase is designed to potentially trigger replanning to test goal anchoring telemetry.",
        "task_category": "core_backend_high",
        "complexity": "medium",
        "builder_mode": None,
    },
]

TIERS = [
    {
        "tier_id": "tier-1",
        "tier_index": 0,
        "name": "Test Tier",
        "description": "Test tier for Goal Anchoring and Validation features",
    }
]


def create_run():
    """Create test run with phases that exercise new features"""

    payload = {
        "run": {
            "run_id": RUN_ID,
            "run_type": "autopack_maintenance",  # Allow modification of src/autopack/
            "safety_profile": "normal",
            "run_scope": "single_tier",
            "token_cap": 500000,
            "max_phases": len(PHASES),
            "max_duration_minutes": 60,
        },
        "tiers": TIERS,
        "phases": PHASES,
    }

    print(f"[INFO] Creating test run: {RUN_ID}")
    print(f"[INFO] Total phases: {len(PHASES)}")
    print()
    print("[INFO] Phases to execute:")
    for phase in PHASES:
        print(f"  - {phase['name']} ({phase['complexity']})")
        print(f"    {phase['description'][:80]}...")
    print()
    print("[INFO] This run will test:")
    print("  - Goal Anchoring (original intent tracking, replan history)")
    print("  - Symbol Preservation Validation (Python AST checks)")
    print("  - Structural Similarity Validation (SequenceMatcher)")
    print("  - Token Soft Caps (advisory warnings)")
    print("  - Startup Validation (medium tier check)")
    print()

    headers = {}
    # API key is optional - if AUTOPACK_API_KEY env var is not set, API allows requests
    # If it is set, we need to provide it
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    elif os.getenv("AUTOPACK_API_KEY"):
        # API key is configured but not passed to script - use it
        headers["X-API-Key"] = os.getenv("AUTOPACK_API_KEY")

    try:
        response = requests.post(
            f"{API_URL}/runs/start", json=payload, headers=headers if headers else None, timeout=30
        )

        if response.status_code != 201:
            print(f"[ERROR] Response: {response.status_code}")
            print(f"[ERROR] Body: {response.text}")
            sys.exit(1)

        result = response.json()
        print(f"[SUCCESS] Run created: {RUN_ID}")
        print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}")
        print()
        print("[OK] Ready to execute autonomous run (from repo root):")
        print(
            f"  python src/autopack/autonomous_executor.py --run-id {RUN_ID} --run-type autopack_maintenance --stop-on-first-failure --verbose"
        )
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
