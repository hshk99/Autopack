"""
Create Autopack Run to Validate Escalation Systems

Tests both:
1. Phase failure escalation (3 consecutive failures -> skip phase)
2. Model escalation (cheap -> mid -> expensive based on attempts)
3. Complexity escalation (Low -> Medium -> High after failures)

This run includes:
- Low complexity phases (some designed to fail, triggering model escalation)
- Medium complexity phases
- High complexity phase (tests direct strong model usage)
- A phase that should succeed on first try
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "escalation-validation-20251130"

TASKS = [
    # Phase 1: Low complexity - should succeed with gpt-4o-mini
    {
        "phase_id": "low-success-simple",
        "name": "Simple Low Complexity Task",
        "description": """Add a simple comment to the top of src/autopack/config.py.

Add this comment on line 1:
# Configuration module for Autopack settings

This is a trivial task that should succeed with the cheapest model (gpt-4o-mini).
""",
        "tier_id": "T1-Validation",
        "tier_index": 0,
        "phase_index": 0,
        "category": "docs",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },

    # Phase 2: Low complexity - designed to need model escalation
    {
        "phase_id": "low-needs-escalation",
        "name": "Low Task Needing Model Escalation",
        "description": """Create a new utility function in src/autopack/utils.py.

Create a function called `format_phase_duration` that:
1. Takes start_time and end_time (both datetime objects)
2. Returns a human-readable string like "2h 30m 15s" or "45s"

Requirements:
- Handle edge cases (negative duration, None inputs)
- Include docstring with examples
- Add type hints

This task is labeled LOW complexity but may need a stronger model.
""",
        "tier_id": "T1-Validation",
        "tier_index": 0,
        "phase_index": 1,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_medium"
    },

    # Phase 3: Medium complexity
    {
        "phase_id": "medium-standard",
        "name": "Medium Complexity Standard Task",
        "description": """Add a new endpoint to src/autopack/main.py.

Create GET /api/escalation-stats endpoint that returns:
{
    "enabled": true/false (from config),
    "thresholds": {
        "low_to_medium": 2,
        "medium_to_high": 2
    },
    "max_attempts_per_phase": 5
}

Read values from config/models.yaml escalation settings.
This tests medium complexity model selection.
""",
        "tier_id": "T2-Features",
        "tier_index": 1,
        "phase_index": 0,
        "category": "feature_scaffolding",
        "complexity": "medium",
        "builder_mode": "scaffolding_medium"
    },

    # Phase 4: Intentionally impossible task - should fail and be skipped
    {
        "phase_id": "impossible-task",
        "name": "Impossible Task (Test Phase Skip)",
        "description": """This task is INTENTIONALLY IMPOSSIBLE to test phase failure escalation.

TASK: Modify the file `/nonexistent/path/impossible.py` to add quantum computing support.

This file does not exist and the task is nonsensical.
The executor should:
1. Fail on first attempt
2. Fail on second attempt
3. Fail on third attempt
4. ESCALATE: Mark phase as FAILED and skip to next phase

DO NOT attempt to create the file - this tests the escalation system.
""",
        "tier_id": "T2-Features",
        "tier_index": 1,
        "phase_index": 1,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },

    # Phase 5: High complexity (should use strong model directly)
    {
        "phase_id": "high-direct-strong",
        "name": "High Complexity Direct Strong Model",
        "description": """Refactor the error handling in src/autopack/autonomous_executor.py.

Add a new method `_handle_builder_error` that:
1. Categorizes errors (network, API, patch, validation)
2. Determines if error is retryable
3. Logs structured error info
4. Returns (should_retry: bool, error_category: str, details: dict)

This HIGH complexity task should use claude-sonnet-4-5 directly from the start.
""",
        "tier_id": "T3-Quality",
        "tier_index": 2,
        "phase_index": 0,
        "category": "core_backend_high",
        "complexity": "high",
        "builder_mode": "scaffolding_heavy"
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
            "token_cap": 50000,  # Small budget for validation
            "max_phases": 10,
            "max_duration_minutes": 30
        },
        "tiers": tier_list,
        "phases": all_phases
    }

    print(f"[INFO] Creating validation run: {RUN_ID}")
    print(f"[INFO] Total tasks: {len(TASKS)}")
    print(f"[INFO] Total tiers: {len(tiers)}")
    print()
    print("[INFO] Tasks:")
    for task in TASKS:
        print(f"  - {task['phase_id']} ({task['complexity']}): {task['name']}")
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
    print(f"[INFO] Run URL: {API_URL}/runs/{RUN_ID}")
    return response.json()


if __name__ == "__main__":
    try:
        result = create_run()
        print("\n[OK] Ready to execute validation run:")
        print(f"  python src/autopack/autonomous_executor.py --run-id {RUN_ID}")
        print()
        print("[INFO] Expected behavior:")
        print("  1. low-success-simple: Succeed with gpt-4o-mini (attempt 0)")
        print("  2. low-needs-escalation: May escalate to gpt-4o (attempt 2+)")
        print("  3. medium-standard: Use gpt-4o directly")
        print("  4. impossible-task: FAIL 3x then SKIP (phase escalation)")
        print("  5. high-direct-strong: Use claude-sonnet-4-5 directly")
        print()
        print("[INFO] Check logs/autopack/model_selections_*.jsonl for model choices")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to create run: {e}")
        sys.exit(1)
