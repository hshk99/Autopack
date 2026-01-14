"""
BUILD-145: Migration Runbook + Executor Rollback

Creates a single-phase run to:
1. Write BUILD-144 migration runbook (operator-grade documentation)
2. Implement git-based executor rollback (opt-in, savepoint-based)

Phase: F1.build144-runbook-executor-rollback
"""

import requests
import sys

API_URL = "http://localhost:8000"
RUN_ID = "autopack-onephase-build144-runbook-and-executor-rollback"

TASKS = [
    {
        "phase_id": "F1.build144-runbook-executor-rollback",
        "name": "BUILD-144 runbook + executor rollback (deterministic, guarded)",
        "description": """Deliver two items:

(1) Operator-grade BUILD-144 migration runbook for total_tokens and nullable token splits:
   - File: docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md
   - Include: prerequisites (backup), environment variables, how to run scripts/migrations/add_total_tokens_build144.py
   - Include: verification commands (SQL + Python snippets), troubleshooting, rollback guidance
   - Verify: llm_usage_events has total_tokens (non-null), prompt_tokens/completion_tokens nullable
   - Verify: dashboard totals use total_tokens (no under-reporting)

(2) Implement deterministic, opt-in executor rollback for failed patch apply:
   - Opt-in feature (config flag or env var) - does NOT run by default
   - Triggers: patch apply failure OR post-apply validation failure OR critical test/quality-gate failure
   - Mechanism: git-based savepoint (tag or commit hash) before apply; on failure, revert/reset to savepoint
   - Protected paths: never touch .git/, .autonomous_runs/, autopack.db (except git commands)
   - Logging: log savepoint id and rollback action
   - Cleanup strategy: document to avoid tag explosion

Files to modify:
- docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md (NEW)
- README.md (reference runbook)
- docs/BUILD_HISTORY.md (BUILD-145 entry)
- src/autopack/autonomous_executor.py (rollback logic)
- src/autopack/governed_apply.py (savepoint integration)
- src/autopack/config.py (rollback config flag)
- tests/autopack/test_executor_rollback.py (NEW - unit test with temp git repo)
- tests/autopack/test_build144_migration_runbook_smoke.py (NEW - smoke test for runbook)

Read-only context:
- docs/guides/BUILD-142_MIGRATION_RUNBOOK.md (format reference)
- docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md (env var patterns)
- src/autopack/llm_service.py (usage recording semantics)

Test command: pytest -q tests/autopack/test_executor_rollback.py tests/autopack/test_build144_migration_runbook_smoke.py

Notes:
- Prefer tag-based savepoints: save-before-{run_id}-{phase_id}-{timestamp}
- Rollback must be Windows-robust (PowerShell-friendly, no shell=True)
- Keep rollback narrowly scoped to repo state reset (no DB rollback)""",
        "tier_id": "T1",
        "tier_index": 0,
        "phase_index": 0,
        "category": "backend",
        "complexity": "medium",
        "builder_mode": "default",
    }
]


def create_run():
    """Create the run via API"""
    print(f"\n=== Creating Run: {RUN_ID} ===\n")

    response = requests.post(
        f"{API_URL}/runs",
        json={
            "id": RUN_ID,
            "safety_profile": "normal",
            "run_scope": "multi_tier",
            "token_cap": 350000,
            "max_phases": 1,
            "max_duration_minutes": 120,
        },
    )

    if response.status_code != 200:
        print(f"❌ Failed to create run: {response.status_code}")
        print(response.text)
        return False

    print(f"✅ Created run: {RUN_ID}")

    # Create tier
    print("\n=== Creating Tier T1 ===\n")
    tier_response = requests.post(
        f"{API_URL}/runs/{RUN_ID}/tiers",
        json={
            "tier_id": "T1",
            "tier_index": 0,
            "name": "Ops + Safety Hardening",
            "description": "Create BUILD-144 migration runbook and implement safe executor rollback via git savepoints/branch strategy.",
        },
    )

    if tier_response.status_code != 200:
        print(f"❌ Failed to create tier: {tier_response.status_code}")
        print(tier_response.text)
        return False

    print("✅ Created tier T1")

    # Create phase
    print("\n=== Creating Phase F1 ===\n")
    for task in TASKS:
        phase_response = requests.post(f"{API_URL}/runs/{RUN_ID}/phases", json=task)

        if phase_response.status_code != 200:
            print(f"❌ Failed to create phase {task['phase_id']}: {phase_response.status_code}")
            print(phase_response.text)
            return False

        print(f"✅ Created phase: {task['phase_id']}")

    return True


if __name__ == "__main__":
    success = create_run()
    if success:
        print(f"\n✅ Run {RUN_ID} created successfully!")
        print("\nNext steps:")
        print("1. Start the executor:")
        print(
            f'   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor --run-id {RUN_ID}'
        )
        print("\n2. Monitor progress:")
        print(f"   python scripts/monitor_run.py {RUN_ID}")
    else:
        print("\n❌ Failed to create run")
        sys.exit(1)
