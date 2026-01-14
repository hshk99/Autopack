"""
Create BUILD-130 autonomous run: Schema Validation & Prevention Infrastructure

Implements GPT-5.2's recommended prevention-first architecture.
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "autopack.db"

# BUILD-130 Plan: Schema Validation & Prevention (Phase 0-1)
BUILD_130_PLAN = {
    "run_id": "build130-schema-validation-prevention",
    "display_name": "BUILD-130: Schema Validation & Prevention Infrastructure",
    "goal": (
        "Implement GPT-5.2's prevention-first architecture to eliminate schema drift failures. "
        "Phase 0-1: Circuit breaker for deterministic failures + schema validator with break-glass repair tool. "
        "Reference: docs/BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md. "
        "This is a self-improvement build enabling autonomous execution (similar to BUILD-126 quality_gate.py)."
    ),
    "phases": [
        {
            "phase_id": "build130-phase0-circuit-breaker",
            "display_name": "Phase 0: Circuit Breaker (Fail-Fast)",
            "goal": (
                "Implement error classification system to prevent infinite retry loops on deterministic failures. "
                "Create ErrorClassifier that distinguishes transient (retry) vs deterministic (fail-fast) errors. "
                "Key rule: Never retry a request that fails deterministically with the same inputs. "
                "Success criteria: Executor stops retrying on 500 enum validation errors, logs remediation."
            ),
            "complexity": "medium",
            "task_category": "backend",
            "scope": {
                "deliverables": [
                    "src/autopack/error_classifier.py",
                    "src/autopack/autonomous_executor.py modifications (integrate circuit breaker)",
                    "tests/test_circuit_breaker.py",
                    "docs/DEBUG_JOURNAL.md update (circuit breaker entry)",
                ],
                "protected_paths": ["src/autopack/models.py", "src/backend/", "src/frontend/"],
                "read_only_context": [
                    "docs/BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md",
                    "docs/BUILD-127-129_ROOT_CAUSE_ANALYSIS_FOR_GPT52.md",
                    "src/autopack/error_recovery.py",
                    "src/autopack/autonomous_executor.py (lines 1040-1060)",
                ],
            },
        },
        {
            "phase_id": "build130-phase1-schema-validator",
            "display_name": "Phase 1: Schema Validator + Break-Glass Repair",
            "goal": (
                "Implement three-part schema validation system: "
                "(1) Startup validator checking database state vs code enums, "
                "(2) Break-glass repair tool using raw SQL to bypass ORM enum mapping, "
                "(3) Integration into executor startup (fail-fast if schema invalid). "
                "Reference: BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md Part 1A-1D. "
                "Success criteria: Executor detects invalid enum values on startup, provides repair SQL, prevents 500 errors."
            ),
            "complexity": "high",
            "task_category": "backend",
            "scope": {
                "deliverables": [
                    "src/autopack/schema_validator.py",
                    "src/autopack/break_glass_repair.py",
                    "scripts/break_glass_repair.py (CLI tool)",
                    "src/autopack/autonomous_executor.py modifications (startup validation)",
                    "tests/test_schema_validator.py",
                    "tests/test_break_glass_repair.py",
                ],
                "protected_paths": ["src/autopack/models.py", "src/backend/", "src/frontend/"],
                "read_only_context": [
                    "docs/BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md",
                    "src/autopack/models.py (RunState, PhaseState, TierState enums)",
                    "src/autopack/database.py",
                    "src/autopack/config.py",
                ],
            },
            "dependencies": ["build130-phase0-circuit-breaker"],
        },
    ],
}


def main():
    """Create BUILD-130 run in database."""
    print("=" * 80)
    print("BUILD-130: Schema Validation & Prevention Infrastructure")
    print("=" * 80)
    print()
    print("Goal: Implement GPT-5.2's prevention-first architecture")
    print()
    print(f"Phases: {len(BUILD_130_PLAN['phases'])}")
    for i, phase in enumerate(BUILD_130_PLAN["phases"], 1):
        print(f"  Phase {i}: {phase['display_name']}")
        print(f"    Complexity: {phase['complexity']}")
        print(f"    Deliverables: {len(phase['scope']['deliverables'])}")
        if "dependencies" in phase:
            print(f"    Dependencies: {phase['dependencies']}")
    print()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create run with all required fields
        run_id = BUILD_130_PLAN["run_id"]
        now = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO runs (
                id, state, created_at, updated_at,
                safety_profile, run_scope, token_cap, max_phases, max_duration_minutes,
                tokens_used, ci_runs_used, minor_issues_count, major_issues_count,
                promotion_eligible_to_main, debt_status, goal_anchor
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                run_id,
                "RUN_CREATED",  # Use valid enum value (not READY)
                now,
                now,
                "normal",
                "multi_phase",
                500000,
                25,
                180,
                0,
                0,
                0,
                0,
                "false",
                "none",
                BUILD_130_PLAN["goal"][:500],
            ),
        )

        # Create phases
        for idx, phase in enumerate(BUILD_130_PLAN["phases"]):
            # Build scope JSON with goal inside
            scope = {
                "goal": phase["goal"],
                "deliverables": phase["scope"]["deliverables"],
                "protected_paths": phase["scope"]["protected_paths"],
                "read_only_context": phase["scope"]["read_only_context"],
            }

            if "dependencies" in phase:
                scope["dependencies"] = phase["dependencies"]

            cursor.execute(
                """
                INSERT OR REPLACE INTO phases (
                    phase_id, run_id, tier_id, phase_index, name, description, state,
                    task_category, complexity, builder_mode, tokens_used, minor_issues_count,
                    major_issues_count, issue_state, quality_blocked, created_at, updated_at,
                    builder_attempts, auditor_attempts, retry_attempt, revision_epoch,
                    escalation_level, scope
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    phase["phase_id"],
                    run_id,
                    191,  # Use same tier_id as BUILD-127
                    idx,
                    phase["display_name"],
                    phase["goal"][:500],
                    "QUEUED",  # Use valid enum value
                    phase["task_category"],
                    phase["complexity"],
                    "BUILD",
                    0,
                    0,
                    0,
                    "no_issues",
                    0,
                    now,
                    now,
                    0,
                    0,
                    0,
                    0,
                    0,
                    json.dumps(scope),
                ),
            )

        conn.commit()

        print("✅ BUILD-130 run created successfully")
        print()
        print(f"Run ID: {run_id}")
        print(f"Phases: {len(BUILD_130_PLAN['phases'])}")
        print()
        print("Next steps:")
        print("1. Start autonomous executor for BUILD-130")
        print("2. Monitor BUILD-112/113/114 stability during execution")
        print("3. Verify prevention infrastructure works as expected")
        print()
        print("Run command:")
        print(
            f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL='sqlite:///autopack.db' python -m autopack.autonomous_executor --run-id {run_id}"
        )

    except Exception as e:
        print(f"❌ Error creating run: {e}")
        import traceback

        traceback.print_exc()
        conn.rollback()
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
