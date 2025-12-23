"""
Create BUILD-132: Coverage Delta Integration Run

Implements actual coverage delta calculation for Quality Gate by integrating
pytest-cov coverage tracking. Currently coverage_delta is hardcoded to 0.0.

4 Phases:
1. Enable coverage collection (update pytest.ini)
2. Create CoverageTracker module + tests
3. Integrate with executor (8 call sites)
4. Documentation and baseline setup

Expected telemetry samples: 4+ successful Builder executions
Estimated time: 2-3 hours
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "build132-coverage-delta-integration"

TASKS = [
    # Phase 1: Enable Coverage Collection
    {
        "phase_id": "build132-phase1-enable-coverage",
        "name": "Enable Coverage Collection",
        "description": """Update pytest.ini to enable pytest-cov coverage collection.

Tasks:
1. Update pytest.ini to add coverage flags:
   --cov=src/autopack
   --cov-report=term-missing:skip-covered
   --cov-report=json:.coverage.json
   --cov-branch

2. Add .coverage.json and .coverage_baseline.json to .gitignore

Files to modify:
- pytest.ini
- .gitignore

DO NOT establish T0 baseline yet - that's Phase 4.""",
        "tier_id": "T1-Setup",
        "tier_index": 0,
        "phase_index": 0,
        "category": "configuration",
        "complexity": "low",
        "builder_mode": "tweak_light"
    },

    # Phase 2: Create CoverageTracker Module
    {
        "phase_id": "build132-phase2-coverage-tracker",
        "name": "Create CoverageTracker Module",
        "description": """Create coverage delta calculation module with comprehensive tests.

Create src/autopack/coverage_tracker.py with:

1. CoverageTracker class:
   - __init__(workspace_root: Path)
   - get_baseline_coverage() -> Optional[float]
   - get_current_coverage() -> Optional[float]
   - _extract_coverage_percentage(coverage_data: Dict) -> float
   - calculate_delta() -> Tuple[float, Dict]

2. Convenience function:
   - calculate_coverage_delta(workspace_root: Path) -> float

Create tests/test_coverage_tracker.py with:
- test_calculate_delta_success (baseline 80%, current 85% -> delta +5%)
- test_calculate_delta_regression (baseline 90%, current 85% -> delta -5%)
- test_missing_baseline (returns 0.0 with error metadata)
- test_missing_current (returns 0.0 with error metadata)
- test_invalid_json (handles gracefully)
- test_convenience_function (calculate_coverage_delta works)

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 114-375 for complete code.

Files to create:
- src/autopack/coverage_tracker.py (~100 lines)
- tests/test_coverage_tracker.py (~150 lines)""",
        "tier_id": "T2-Implementation",
        "tier_index": 1,
        "phase_index": 0,
        "category": "implementation",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy"
    },

    # Phase 3: Integrate with Executor
    {
        "phase_id": "build132-phase3-executor-integration",
        "name": "Integrate CoverageTracker with Executor",
        "description": """Replace hardcoded coverage_delta=0.0 with actual calculation.

Modify src/autopack/autonomous_executor.py:

1. Add import at top:
   from autopack.coverage_tracker import calculate_coverage_delta

2. Replace all 8 instances of hardcoded coverage_delta=0.0:
   Lines: 4536, 4556, 5167, 5179, 5716, 5728, 6055, 6067

   OLD:
   coverage_delta=0.0,  # TODO: Calculate actual coverage delta

   NEW:
   coverage_delta=calculate_coverage_delta(Path.cwd()) if ci_success else 0.0,

3. Add graceful fallback:
   - If coverage files missing, returns 0.0
   - Log warning but don't block execution
   - Quality Gate will simply not have coverage data

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 377-450

Files to modify:
- src/autopack/autonomous_executor.py (8 locations)""",
        "tier_id": "T2-Implementation",
        "tier_index": 1,
        "phase_index": 1,
        "category": "integration",
        "complexity": "medium",
        "builder_mode": "tweak_medium"
    },

    # Phase 4: Documentation and Baseline
    {
        "phase_id": "build132-phase4-documentation",
        "name": "Documentation and Baseline Setup",
        "description": """Update documentation to reflect BUILD-132 completion.

Tasks:
1. Update BUILD_HISTORY.md:
   - Add BUILD-132 entry at top of chronological index
   - Status: COMPLETE
   - Summary: Coverage Delta Integration - replaces hardcoded 0.0 with pytest-cov tracking
   - Files: pytest.ini, coverage_tracker.py, test_coverage_tracker.py, autonomous_executor.py
   - Impact: Quality Gate can now detect coverage regressions

2. Update BUILD_LOG.md:
   - Add 2025-12-23 entry for BUILD-132
   - Document 4 phases completed
   - Note: T0 baseline establishment pending (run pytest with --cov)

3. Create docs/BUILD-132_IMPLEMENTATION_STATUS.md:
   - Document completion status
   - Usage instructions for establishing baseline
   - Quality Gate integration confirmed

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 452-550

Files to modify:
- BUILD_HISTORY.md
- BUILD_LOG.md

Files to create:
- docs/BUILD-132_IMPLEMENTATION_STATUS.md""",
        "tier_id": "T3-Documentation",
        "tier_index": 2,
        "phase_index": 0,
        "category": "docs",
        "complexity": "low",
        "builder_mode": "tweak_light"
    }
]


def create_run():
    """Create BUILD-132 run via API."""

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
            "safety_profile": "normal",
            "run_scope": "multi_tier",
            "token_cap": 300000,  # 300k tokens for 4 phases
            "max_phases": 5,
            "max_duration_minutes": 180  # 3 hours max
        },
        "tiers": tier_list,
        "phases": all_phases
    }

    print(f"[INFO] Creating BUILD-132: Coverage Delta Integration")
    print(f"[INFO] Total phases: {len(TASKS)}")
    print(f"[INFO] Total tiers: {len(tiers)}")
    print(f"[INFO] Expected telemetry samples: 4+ successful Builder executions")

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
        print("\n[OK] Ready to execute BUILD-132 autonomous run:")
        print(f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")
        print("\n[INFO] This will generate token estimation telemetry for each phase")
        print("[INFO] Telemetry will be logged to .autonomous_runs/{RUN_ID}/*.log")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to create run: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
