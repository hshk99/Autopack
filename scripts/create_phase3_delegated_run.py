"""
Create Phase 3 Delegated Tasks Run

These are the tasks from IMPLEMENTATION_PLAN.md that can be delegated to Autopack
(as opposed to MANUAL tasks that required Claude Code implementation).

Tests recent improvements:
- GLM-4.5 + Gemini 2.5 Pro model routing
- Model escalation on phase failure
- Mid-run re-planning
- Self-healing recovery
- Doctor LLM invocation
- Run-level health budget
- CI flow (pytest) after patch application
"""

import os
import requests
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")
RUN_ID = f"phase3-delegated-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

# Phase 3 delegated tasks from IMPLEMENTATION_PLAN.md
TASKS = [
    {
        "phase_id": "phase3-config-loading",
        "name": "Config Loading from models.yaml",
        "description": """Load Doctor configuration from config/models.yaml instead of hardcoded constants.

Tasks:
1. Create DoctorConfig dataclass in error_recovery.py with fields:
   - cheap_model: str
   - strong_model: str
   - min_confidence_for_cheap: float
   - health_budget_near_limit_ratio: float
   - max_builder_attempts_before_complex: int
   - high_risk_categories: List[str]
   - low_risk_categories: List[str]
   - allow_execute_fix_global: bool
   - max_execute_fix_per_phase: int
   - allowed_fix_types: List[str]

2. Add load_doctor_config() function that:
   - Reads config/models.yaml
   - Extracts doctor_models section
   - Returns DoctorConfig instance with defaults for missing keys

3. Replace hardcoded constants in error_recovery.py:
   - CHEAP_DOCTOR_MODEL -> config.cheap_model
   - STRONG_DOCTOR_MODEL -> config.strong_model
   - etc.

4. Add config validation on module import (check required keys exist)

Files to modify:
- src/autopack/error_recovery.py""",
        "tier_id": "T1-Config",
        "tier_index": 0,
        "phase_index": 0,
        "category": "backend",
        "complexity": "low",
        "builder_mode": "tweak_light",
    },
    {
        "phase_id": "phase3-doctor-tests",
        "name": "Doctor Unit Tests",
        "description": """Write comprehensive unit tests for Doctor routing logic.

Create tests/test_doctor_routing.py with:

1. test_is_complex_failure():
   - Single category, 1 attempt, healthy budget -> False
   - 2+ error categories -> True
   - 2+ patch errors -> True
   - Many attempts (>=4) -> True
   - Health ratio >= 0.8 -> True
   - Prior escalated action -> True

2. test_choose_doctor_model():
   - Health ratio >= 0.8 always returns strong model
   - Routine failure returns cheap model
   - Complex failure returns strong model

3. test_should_escalate_doctor_model():
   - Cheap model + low confidence + attempts >= 2 -> True
   - Strong model -> False (already escalated)
   - High confidence -> False

4. test_doctor_context_summary():
   - Verify DoctorContextSummary.from_context() creates correct summary
   - Verify to_dict() produces expected JSON

Files to create:
- tests/test_doctor_routing.py""",
        "tier_id": "T1-Config",
        "tier_index": 0,
        "phase_index": 1,
        "category": "tests",
        "complexity": "low",
        "builder_mode": "scaffolding_heavy",
    },
    {
        "phase_id": "phase3-branch-rollback",
        "name": "Branch-Based Rollback",
        "description": """Implement git rollback for Doctor's rollback_run action.

Tasks:
1. Create src/autopack/git_rollback.py with:
   - create_rollback_point(run_id: str) -> str: Creates branch autopack/pre-run-{run_id}, returns branch name
   - rollback_to_point(run_id: str) -> bool: Hard reset to pre-run branch, returns success
   - cleanup_rollback_point(run_id: str) -> bool: Delete pre-run branch after successful run

2. Integrate into autonomous_executor.py:
   - Call create_rollback_point() at run start
   - On rollback_run Doctor action, call rollback_to_point()
   - On successful run completion, call cleanup_rollback_point()

3. Handle edge cases:
   - Uncommitted changes (stash or warn)
   - Branch already exists (force overwrite with warning)
   - Rollback branch not found (graceful failure)

Files to create:
- src/autopack/git_rollback.py

Files to modify:
- src/autopack/autonomous_executor.py""",
        "tier_id": "T2-Hardening",
        "tier_index": 1,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
    },
    {
        "phase_id": "phase3-t0t1-checks",
        "name": "T0/T1 Advanced Health Checks",
        "description": """Implement comprehensive pre-run validation.

Tasks:
1. Create src/autopack/health_checks.py with:

T0 Checks (quick, always run):
- check_api_keys(): Verify OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY present
- check_database(): SQLite file exists and writable
- check_workspace(): Workspace path exists and is git repo
- check_config(): models.yaml and pricing.yaml exist and parseable

T1 Checks (longer, configurable):
- check_test_suite(): Run pytest --collect-only to verify tests exist
- check_dependencies(): pip check for missing packages
- check_git_clean(): No uncommitted changes
- check_git_remote(): Branch is up to date with remote

2. Create HealthCheckResult dataclass:
   - check_name: str
   - passed: bool
   - message: str
   - duration_ms: int

3. Add run_health_checks(tier: Literal["t0", "t1"]) -> List[HealthCheckResult]

4. Integrate into autonomous_executor.py:
   - Run T0 checks at executor startup
   - Optionally run T1 checks if configured

Files to create:
- src/autopack/health_checks.py

Files to modify:
- src/autopack/autonomous_executor.py""",
        "tier_id": "T2-Hardening",
        "tier_index": 1,
        "phase_index": 1,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
    },
    {
        "phase_id": "phase3-dashboard-metrics",
        "name": "Dashboard Metrics Aggregation",
        "description": """Add Doctor usage tracking to dashboard.

Tasks:
1. Extend usage_recorder.py to track Doctor calls:
   - doctor_calls_total: int
   - doctor_cheap_calls: int
   - doctor_strong_calls: int
   - doctor_escalations: int
   - doctor_actions: Dict[str, int] (count per action type)

2. Add to UsageRecord dataclass:
   - doctor_model: Optional[str]
   - doctor_action: Optional[str]
   - is_doctor_call: bool

3. Create dashboard API endpoint GET /api/doctor-stats:
   - Total Doctor calls this run
   - Cheap vs strong model ratio
   - Action distribution (pie chart data)
   - Escalation frequency

4. Update dashboard frontend (if exists) to show Doctor metrics

Files to modify:
- src/autopack/usage_recorder.py
- src/autopack/main.py (add endpoint)
- src/autopack/dashboard/ (if exists)""",
        "tier_id": "T3-Observability",
        "tier_index": 2,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
    },
    {
        "phase_id": "phase3-discovery-promotion",
        "name": "Discovery Promotion Pipeline",
        "description": """Implement learned rules promotion from discovery to permanent rule.

The promotion pipeline stages:
1. NEW: Fix discovered during troubleshooting
2. APPLIED: Fix was attempted
3. CANDIDATE_RULE: Same pattern seen in >= 3 runs within 30 days
4. RULE: Confirmed via recurrence, no regressions, human approved

Tasks:
1. Extend learned_rules.py with:
   - DiscoveryStage enum: NEW, APPLIED, CANDIDATE_RULE, RULE
   - add stage field to LearnedRule dataclass
   - promote_rule(rule_id: str) -> bool: Move to next stage
   - get_candidates_for_promotion() -> List[LearnedRule]: Rules ready for review

2. Add promotion criteria checking:
   - count_rule_applications(rule_id: str, days: int) -> int
   - check_rule_regressions(rule_id: str) -> bool
   - is_promotion_eligible(rule: LearnedRule) -> Tuple[bool, str]

3. Load config from models.yaml discovery_promotion section:
   - min_runs_for_candidate: 3
   - window_days: 30
   - min_severity_for_candidate: medium
   - require_human_approval: true

Files to modify:
- src/autopack/learned_rules.py
- config/models.yaml (validate existing structure)""",
        "tier_id": "T3-Observability",
        "tier_index": 2,
        "phase_index": 1,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
    },
]


def create_run():
    """Create run with all delegated Phase 3 tasks"""
    # Group tasks by tier
    tiers = {}
    for task in TASKS:
        tier_id = task["tier_id"]
        if tier_id not in tiers:
            tiers[tier_id] = {
                "tier_id": tier_id,
                "tier_index": task["tier_index"],
                "name": tier_id.split("-")[1],
                "description": f"Phase 3 Tier {task['tier_index'] + 1}",
                "phases": [],
            }
        tiers[tier_id]["phases"].append(
            {
                "phase_id": task["phase_id"],
                "phase_index": task["phase_index"],
                "tier_id": tier_id,
                "name": task["name"],
                "description": task["description"],
                "task_category": task["category"],
                "complexity": task["complexity"],
                "builder_mode": task["builder_mode"],
            }
        )

    # Flatten for API
    all_phases = []
    tier_list = []
    for tier in tiers.values():
        all_phases.extend(tier["phases"])
        tier_list.append(
            {
                "tier_id": tier["tier_id"],
                "tier_index": tier["tier_index"],
                "name": tier["name"],
                "description": tier.get("description"),
            }
        )

    # Create run payload
    # NOTE: run_type="autopack_maintenance" allows patches to modify src/autopack/
    # This is required for Phase 3 tasks that modify Autopack's own codebase
    payload = {
        "run": {
            "run_id": RUN_ID,
            "run_type": "autopack_maintenance",  # Unlock src/autopack/ for modification
            "safety_profile": "standard",
            "run_scope": "multi_tier",
            "token_cap": 300000,
            "max_phases": len(TASKS),
            "max_duration_minutes": 720,
        },
        "tiers": tier_list,
        "phases": all_phases,
    }

    print(f"[INFO] Creating Phase 3 delegated run: {RUN_ID}")
    print(f"[INFO] Total tasks: {len(TASKS)}")
    print(f"[INFO] Total tiers: {len(tiers)}")
    print()
    print("[INFO] Tasks to execute:")
    for task in TASKS:
        print(f"  - {task['name']} ({task['complexity']})")
    print()

    headers = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    response = requests.post(
        f"{API_URL}/runs/start",
        json=payload,
        headers=headers,
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
        print()
        print("[OK] Ready to execute autonomous run:")
        print(
            f"  PYTHONPATH=src python src/autopack/autonomous_executor.py --run-id {RUN_ID} --run-type autopack_maintenance"
        )
        print()
        print("[INFO] NOTE: --run-type autopack_maintenance is required to modify src/autopack/")
        print()
        print("[INFO] This run will test recent improvements:")
        print("  - GLM-4.7 model routing")
        print("  - Model escalation on phase failure")
        print("  - Mid-run re-planning detection")
        print("  - Self-healing recovery")
        print("  - Doctor LLM invocation")
        print("  - Run-level health budget")
        print("  - CI flow (pytest) after patch application")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Failed to create run: {e}")
        sys.exit(1)
