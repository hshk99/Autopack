"""Create Autopack Run to Validate Escalation Systems - V2

Tests the updated escalation system with retry loop.
"""

import requests
import sys
from datetime import datetime

API_URL = "http://localhost:8000"
RUN_ID = f"escalation-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

TASKS = [
    # Phase 1: Low complexity - should succeed with cheap model
    {
        "phase_id": "low-easy-task",
        "name": "Easy Low Complexity Task",
        "description": """Add a simple docstring to the top of src/autopack/config.py.

Add this docstring after any existing imports:
'''Configuration module for Autopack settings - test task'''

This is a trivial task that should succeed with the cheapest model on attempt 0.
""",
        "tier_id": "T1-Test",
        "tier_index": 0,
        "phase_index": 0,
        "category": "docs",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },

    # Phase 2: Intentionally tricky task - tests model escalation
    {
        "phase_id": "low-tricky-task",
        "name": "Tricky Task (Test Model Escalation)",
        "description": """This task tests model escalation within a complexity tier.

TASK: Create a function in src/autopack/utils.py called `calculate_retry_delay`.

Requirements:
1. Takes parameters: attempt_index (int), base_delay (float = 1.0), max_delay (float = 60.0)
2. Implements exponential backoff with jitter
3. Formula: min(max_delay, base_delay * (2 ** attempt_index) + random_jitter)
4. Random jitter should be between 0 and 1 second
5. Include type hints and docstring

This task is labeled LOW complexity but may need model escalation after failures.
The retry loop should try multiple times with progressively better models.
""",
        "tier_id": "T1-Test",
        "tier_index": 0,
        "phase_index": 1,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_medium"
    },

    # Phase 3: Medium complexity
    {
        "phase_id": "medium-task",
        "name": "Medium Complexity Task",
        "description": """Create a simple helper function.

TASK: Add a function to src/autopack/utils.py called `format_token_count`.

Takes an integer token_count and returns a formatted string:
- If < 1000: return as-is (e.g., "500 tokens")
- If >= 1000: return with K suffix (e.g., "1.5K tokens")  
- If >= 1000000: return with M suffix (e.g., "2.3M tokens")

Include type hints.
""",
        "tier_id": "T2-Features",
        "tier_index": 1,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_medium"
    },
]


def create_run():
    """Create run with validation tasks"""
    # Group tasks by tier
    tiers = {}
    for task in TASKS:
        tier_id = task["tier_id"]
        if tier_id not in tiers:
            tiers[tier_id] = {
                "tier_id": tier_id,
                "tier_index": task["tier_index"],
                "name": tier_id.split("-")[1],
                "description": f"Tier {task['tier_index'] + 1}: {tier_id}",
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

    # Flatten for API
    all_phases = []
    tier_list = []
    for tier in sorted(tiers.values(), key=lambda t: t["tier_index"]):
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
            "token_cap": 50000,
            "max_phases": 10,
            "max_duration_minutes": 30
        },
        "tiers": tier_list,
        "phases": all_phases
    }

    print(f"[INFO] Creating validation run: {RUN_ID}")
    print(f"[INFO] Total tasks: {len(TASKS)}")
    print()

    response = requests.post(
        f"{API_URL}/runs/start",
        json=payload
    )

    if response.status_code != 201:
        print(f"[ERROR] Response: {response.status_code}")
        print(f"[ERROR] Body: {response.text}")

    response.raise_for_status()

    print(f"[SUCCESS] Run created: {RUN_ID}")
    return RUN_ID


if __name__ == "__main__":
    try:
        run_id = create_run()
        print(f"\n[OK] Ready to execute: python src/autopack/autonomous_executor.py --run-id {run_id}")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        sys.exit(1)
