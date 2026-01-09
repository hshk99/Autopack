"""
Seed BUILD-145 Run Directly in Database

Creates BUILD-145: Migration Runbook + Executor Rollback with 1 phase.
Bypasses API to seed database directly.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ["DATABASE_URL"] = "sqlite:///autopack.db"

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "autopack-onephase-build144-runbook-and-executor-rollback"

def seed_run():
    """Seed BUILD-145 run in database."""

    session = SessionLocal()

    try:
        # Check if run exists
        existing = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing:
            print(f"[ERROR] Run {RUN_ID} already exists")
            print("[INFO] Deleting existing run and recreating...")
            # Delete phases first
            session.query(Phase).filter(Phase.run_id == RUN_ID).delete()
            # Delete tiers
            session.query(Tier).filter(Tier.run_id == RUN_ID).delete()
            # Delete run
            session.query(Run).filter(Run.id == RUN_ID).delete()
            session.commit()
            print(f"[OK] Deleted existing run {RUN_ID}")

        # Create run
        run = Run(
            id=RUN_ID,
            state=RunState.QUEUED,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=350000,
            max_phases=1,
            max_duration_minutes=120,
            goal_anchor="BUILD-145: Migration Runbook + Executor Rollback (Ops + Safety Hardening)"
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="T1",
            run_id=RUN_ID,
            name="Ops + Safety Hardening",
            tier_index=0,
            description="Create BUILD-144 migration runbook and implement safe executor rollback via git savepoints/branch strategy."
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id
        print("[OK] Created tier: T1")

        # Create phase
        phase = Phase(
            phase_id="F1.build144-runbook-executor-rollback",
            run_id=RUN_ID,
            tier_id=tier_db_id,
            name="BUILD-144 runbook + executor rollback (deterministic, guarded)",
            phase_index=0,
            state=PhaseState.QUEUED,
            task_category="backend",
            complexity="medium",
            scope={
                "paths": [
                    "docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md",
                    "README.md",
                    "docs/BUILD_HISTORY.md",
                    "scripts/migrations/add_total_tokens_build144.py",
                    "src/autopack/autonomous_executor.py",
                    "src/autopack/governed_apply.py",
                    "src/autopack/file_layout.py",
                    "src/autopack/config.py",
                    "tests/autopack/test_executor_rollback.py",
                    "tests/autopack/test_build144_migration_runbook_smoke.py"
                ],
                "read_only_context": [
                    {
                        "path": "docs/guides/BUILD-142_MIGRATION_RUNBOOK.md",
                        "reason": "Use as format/quality reference for an operator-grade migration runbook (prereqs, steps, verification, rollback)."
                    },
                    {
                        "path": "docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md",
                        "reason": "Keep operational instructions consistent with existing env var patterns and workflows."
                    },
                    {
                        "path": "src/autopack/llm_service.py",
                        "reason": "Understand how total_tokens and split tokens are recorded; ensure rollback doesn't affect usage recording semantics."
                    }
                ],
                "acceptance_criteria": [
                    "Runbook exists at docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md and includes: prerequisites (backup), environment variables, how to run scripts/migrations/add_total_tokens_build144.py, verification commands (SQL + Python snippets), troubleshooting, and rollback guidance.",
                    "Runbook explicitly verifies: llm_usage_events has total_tokens (non-null), prompt_tokens/completion_tokens nullable, and dashboard totals use total_tokens (no under-reporting).",
                    "Executor rollback is implemented as an opt-in feature (config flag or env var) and does NOT run by default.",
                    "Rollback triggers on: patch apply failure OR post-apply validation failure (governed apply error) OR critical test/quality-gate failure (define clearly).",
                    "Rollback mechanism is deterministic and git-based: create a savepoint (tag or branch/commit hash) before apply; on failure, revert/reset to savepoint; log the savepoint id and rollback action.",
                    "Rollback never touches protected paths (.git/, .autonomous_runs/, autopack.db) other than using git commands to reset working tree safely.",
                    "Add targeted tests: (a) unit test for savepoint creation/rollback logic using a temp git repo (no network), (b) smoke test that runbook file exists and contains key headings/commands (lightweight string assertions).",
                    "All targeted tests pass."
                ],
                "test_cmd": "pytest -q tests/autopack/test_executor_rollback.py tests/autopack/test_build144_migration_runbook_smoke.py",
                "notes": [
                    "Prefer tag-based savepoints (e.g., save-before-{run_id}-{phase_id}-{timestamp}) OR commit-hash savepoints; ensure cleanup strategy (avoid tag explosion) is documented.",
                    "Rollback code must be robust on Windows (PowerShell-friendly paths) and should use subprocess with explicit args (no shell=True).",
                    "Keep rollback narrowly scoped to repo state reset; do not attempt DB rollback."
                ]
            },
            description="""Deliver two items:

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
- Keep rollback narrowly scoped to repo state reset (no DB rollback)"""
        )
        session.add(phase)
        session.commit()

        print("[OK] Created phase: F1.build144-runbook-executor-rollback")
        print(f"\n✅ Run {RUN_ID} seeded successfully!")
        print("\nNext steps:")
        print("1. Start the executor:")
        print(f"   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")
        print("\n2. Monitor progress:")
        print(f"   python scripts/monitor_run.py {RUN_ID}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] Failed to seed run: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    seed_run()
