"""
Create BUILD-129 run directly in database (SQL approach).
"""

import sqlite3
import json
from datetime import datetime

DB_PATH = "autopack.db"

# BUILD-129 Plan
BUILD_129_PLAN = {
    "run_id": "build129-token-budget-intelligence",
    "display_name": "BUILD-129: Token Budget Intelligence (Self-Improvement)",
    "goal": (
        "Implement GPT-5.2's 4-layer token budget policy to reduce truncation failures from 50% to 10% for multi-file phases. "
        "Reference: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md. "
        "This is a self-improvement build - Autopack implementing Autopack improvements (similar to BUILD-126 quality_gate.py). "
        "Key improvements: (1) Output-size predictor replacing file-count heuristic, "
        "(2) Continuation-based recovery to avoid wasted work on truncation, "
        "(3) NDJSON structured-edit format for truncation tolerance. "
        "Monitor BUILD-112/113/114 stability after each phase."
    ),
    "phases": [
        {
            "phase_id": "build129-phase1-output-size-predictor",
            "display_name": "Phase 1: Output-Size Predictor (Layer 1)",
            "goal": (
                "Replace file-count heuristic with deliverable-based token estimation. "
                "Create token_estimator.py module with estimate_output_tokens() function that predicts required tokens based on deliverable types: "
                "new files (~800 tokens), modifications (~300), tests (~600), docs (~200), config (~400). "
                "Integrate into anthropic_clients.py (line 160) and manifest_generator.py (_enhance_phase method). "
                "Reference implementation: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md Section 'Layer 1: Preflight Token Budget Selection'. "
                "Success criteria: BUILD-127 scenario estimated at 18k-22k tokens (vs 16k fixed before), all tests pass, no BUILD-112/113/114 regressions."
            ),
            "complexity": "medium",
            "task_category": "backend",
            "scope": json.dumps({
                "deliverables": [
                    "src/autopack/token_estimator.py",
                    "src/autopack/anthropic_clients.py modifications",
                    "src/autopack/manifest_generator.py modifications",
                    "tests/test_token_estimator.py",
                    "docs/BUILD-129_PHASE1_OUTPUT_SIZE_PREDICTOR.md"
                ],
                "protected_paths": [
                    "src/autopack/autonomous_executor.py",
                    "src/autopack/models.py",
                    "src/frontend/"
                ],
                "read_only_context": [
                    "docs/TOKEN_BUDGET_ANALYSIS_REVISED.md",
                    "docs/BUILD-129_SELF_IMPROVEMENT_PLAN.md",
                    "src/autopack/deliverables_validator.py"
                ]
            })
        }
    ]
}


def main():
    """Create BUILD-129 run in database."""
    print("Creating BUILD-129: Token Budget Intelligence")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Create run
        run_id = BUILD_129_PLAN["run_id"]
        cursor.execute("""
            INSERT OR REPLACE INTO runs (run_id, display_name, goal, state, created_at)
            VALUES (?, ?, ?, 'READY', ?)
        """, (run_id, BUILD_129_PLAN["display_name"], BUILD_129_PLAN["goal"], datetime.utcnow().isoformat()))

        # Create phases
        for idx, phase in enumerate(BUILD_129_PLAN["phases"]):
            cursor.execute("""
                INSERT OR REPLACE INTO phases (
                    phase_id, run_id, display_name, goal, state,
                    phase_index, complexity, task_category, scope
                )
                VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?, ?)
            """, (
                phase["phase_id"],
                run_id,
                phase["display_name"],
                phase["goal"],
                idx,
                phase["complexity"],
                phase["task_category"],
                phase["scope"]
            ))

        conn.commit()
        print(f"✅ Created run: {run_id}")
        print(f"✅ Created {len(BUILD_129_PLAN['phases'])} phase(s)")
        print()
        print("Start execution:")
        print(f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL='sqlite:///autopack.db' python -m autopack.autonomous_executor {run_id}")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
