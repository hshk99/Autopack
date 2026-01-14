"""Create a fresh Autopack run to test self-troubleshoot capability for backend tests."""

import sqlite3
import uuid
from datetime import datetime

db_path = "autopack.db"
run_id = f"fileorg-backend-fixes-v4-{datetime.now().strftime('%Y%m%d')}"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Create the run with all required fields
cursor.execute(
    """
    INSERT OR REPLACE INTO runs (id, state, created_at, updated_at, safety_profile, run_scope,
                                  token_cap, max_phases, max_duration_minutes, tokens_used,
                                  ci_runs_used, minor_issues_count, major_issues_count,
                                  promotion_eligible_to_main, debt_status)
    VALUES (?, 'queued', ?, ?, 'standard', 'patch', 500000, 10, 120, 0, 0, 0, 0, 0, 'none')
""",
    (run_id, datetime.now().isoformat(), datetime.now().isoformat()),
)

# Phase definitions - let Autopack fix the backend test issues
phases = [
    (
        "Phase 1: Analyze Backend Test Failures",
        """
Analyze the backend test collection errors and failures.

Run: PYTHONPATH=src python -m pytest tests/backend/ -v --tb=short

Identify all issues causing:
1. Collection errors (import failures, missing modules)
2. Test failures (assertion errors, type errors)

Create a summary of all issues found.
""",
    ),
    (
        "Phase 2: Fix Import and Configuration Issues",
        """
Fix any import errors and configuration issues in the backend tests.

Common issues to check:
- Missing __init__.py files
- Incorrect import paths
- Missing dependencies in test environment
- Configuration not being loaded properly

Apply fixes and verify tests can be collected.
""",
    ),
    (
        "Phase 3: Fix Pydantic Configuration",
        """
Fix any Pydantic-related configuration issues:
- Add 'extra = "ignore"' to Settings classes if needed
- Fix model_config issues
- Ensure proper validation settings

Run tests after fixes to verify.
""",
    ),
    (
        "Phase 4: Fix Database Configuration",
        """
Fix any database configuration issues:
- Ensure SQLite compatibility (no pool_size for SQLite)
- Fix reserved attribute names (e.g., 'metadata' in SQLAlchemy)
- Ensure proper session handling in tests

Run tests after fixes to verify.
""",
    ),
    (
        "Phase 5: Fix Authentication Module",
        """
Fix any issues in the authentication module:
- Missing dependencies (python-jose, passlib, email-validator)
- Incorrect password hashing setup
- JWT token configuration issues

Run tests after fixes to verify.
""",
    ),
    (
        "Phase 6: Fix Remaining Test Failures",
        """
Fix any remaining test failures not addressed in previous phases.

Run full backend test suite and address each failure:
PYTHONPATH=src python -m pytest tests/backend/ -v --tb=short

Ensure all tests pass.
""",
    ),
    (
        "Phase 7: Final Validation",
        """
Run the complete backend test suite and verify all tests pass:
PYTHONPATH=src python -m pytest tests/backend/ -v --tb=line

Expected outcome: All tests should pass with no errors.
If any failures remain, document them clearly.
""",
    ),
]

for i, (name, desc) in enumerate(phases, 1):
    phase_id = str(uuid.uuid4())
    # id is INTEGER auto-increment, don't set it
    cursor.execute(
        """
        INSERT INTO phases (phase_id, run_id, tier_id, phase_index, name, description, state,
                           task_category, complexity, builder_mode, max_builder_attempts,
                           max_auditor_attempts, incident_token_cap, builder_attempts,
                           auditor_attempts, tokens_used, minor_issues_count, major_issues_count,
                           issue_state, quality_level, quality_blocked, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, 'queued', 'bug_fix', 'medium', 'standard', 3, 2, 50000,
                0, 0, 0, 0, 0, 'none', 'standard', 0, ?, ?)
    """,
        (
            phase_id,
            run_id,
            i,
            name,
            desc.strip(),
            datetime.now().isoformat(),
            datetime.now().isoformat(),
        ),
    )

conn.commit()
conn.close()

print(f"Created run: {run_id}")
print(f"Phases: {len(phases)}")
print("\nTo execute:")
print(f"  PYTHONPATH=src python src/autopack/autonomous_executor.py --run-id {run_id}")
