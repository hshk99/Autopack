"""
Fix BUILD-130 phase scopes - remove descriptive text from deliverables and fix protected_paths.
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "autopack.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Phase 0: Circuit Breaker
        phase0_scope = {
            "goal": (
                "Implement error classification system to prevent infinite retry loops on deterministic failures. "
                "Create ErrorClassifier that distinguishes transient (retry) vs deterministic (fail-fast) errors. "
                "Key rule: Never retry a request that fails deterministically with the same inputs. "
                "Success criteria: Executor stops retrying on 500 enum validation errors, logs remediation."
            ),
            "deliverables": [
                "src/autopack/error_classifier.py",
                "src/autopack/autonomous_executor.py",
                "tests/test_circuit_breaker.py",
                "docs/DEBUG_JOURNAL.md"
            ],
            "protected_paths": [
                "src/autopack/models.py",
                "src/backend/",
                "src/frontend/"
            ],
            "read_only_context": [
                "docs/BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md",
                "docs/BUILD-127-129_ROOT_CAUSE_ANALYSIS_FOR_GPT52.md",
                "src/autopack/error_recovery.py"
            ]
        }

        cursor.execute("""
            UPDATE phases
            SET scope = ?, updated_at = ?
            WHERE phase_id = 'build130-phase0-circuit-breaker'
        """, (json.dumps(phase0_scope), datetime.now().isoformat()))

        print("✅ Updated Phase 0 scope")

        # Phase 1: Schema Validator
        phase1_scope = {
            "goal": (
                "Implement three-part schema validation system: "
                "(1) Startup validator checking database state vs code enums, "
                "(2) Break-glass repair tool using raw SQL to bypass ORM enum mapping, "
                "(3) Integration into executor startup (fail-fast if schema invalid). "
                "Reference: BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md Part 1A-1D. "
                "Success criteria: Executor detects invalid enum values on startup, provides repair SQL, prevents 500 errors."
            ),
            "deliverables": [
                "src/autopack/schema_validator.py",
                "src/autopack/break_glass_repair.py",
                "scripts/break_glass_repair.py",
                "src/autopack/autonomous_executor.py",
                "tests/test_schema_validator.py",
                "tests/test_break_glass_repair.py"
            ],
            "protected_paths": [
                "src/autopack/models.py",
                "src/backend/",
                "src/frontend/"
            ],
            "read_only_context": [
                "docs/BUILD-130_SCHEMA_VALIDATION_AND_PREVENTION.md",
                "src/autopack/models.py",
                "src/autopack/database.py",
                "src/autopack/config.py"
            ],
            "dependencies": ["build130-phase0-circuit-breaker"]
        }

        cursor.execute("""
            UPDATE phases
            SET scope = ?, updated_at = ?
            WHERE phase_id = 'build130-phase1-schema-validator'
        """, (json.dumps(phase1_scope), datetime.now().isoformat()))

        print("✅ Updated Phase 1 scope")

        # Reset phase states to QUEUED so executor can retry
        cursor.execute("""
            UPDATE phases
            SET state = 'QUEUED', builder_attempts = 0, updated_at = ?
            WHERE phase_id IN ('build130-phase0-circuit-breaker', 'build130-phase1-schema-validator')
        """, (datetime.now().isoformat(),))

        print("✅ Reset phases to QUEUED")

        conn.commit()
        print()
        print("BUILD-130 scope fixed successfully")
        print("Executor will pick up changes on next iteration")

    except Exception as e:
        print(f"❌ Error: {e}")
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
