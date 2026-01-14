"""
Create Telemetry Collection Run

Creates a simple autonomous run with achievable phases designed to produce
successful Builder executions for token estimation telemetry collection.

Strategy:
- Simple, self-contained utility functions (no external dependencies)
- Clear, achievable goals
- Mix of complexity levels (low/medium)
- Mix of deliverable counts (1 file / 2-5 files)
- Mix of categories (implementation/tests/docs)

Goal: Collect 10+ successful telemetry samples (success=True)

Usage:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \\
        python scripts/create_telemetry_collection_run.py

Then drain with:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack_telemetry_seed.db" \\
        TELEMETRY_DB_ENABLED=1 timeout 600 \\
        python scripts/drain_one_phase.py --run-id telemetry-collection-v4 --phase-id telemetry-p1-string-util
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to be explicitly set
if not os.environ.get("DATABASE_URL"):
    print("[ERROR] DATABASE_URL must be set", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage:", file=sys.stderr)
    print(
        "  DATABASE_URL='sqlite:///autopack_telemetry_seed.db' python scripts/create_telemetry_collection_run.py",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, TierState, PhaseState

RUN_ID = "telemetry-collection-v4"
TIER_ID = "T1"

# 10 simple, achievable phases
PHASES = [
    # Phase 1: String utility (low complexity, 1 file)
    {
        "phase_id": "telemetry-p1-string-util",
        "name": "String utility module",
        "description": "Create a string utility module with capitalize_words and reverse_string functions",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/string_helper.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 0,
    },
    # Phase 2: Number utility (low complexity, 1 file)
    {
        "phase_id": "telemetry-p2-number-util",
        "name": "Number utility module",
        "description": "Create a number utility module with is_even, is_prime, and factorial functions",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/number_helper.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 1,
    },
    # Phase 3: List utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p3-list-util",
        "name": "List utility module",
        "description": "Create a list utility module with chunk, flatten, unique, and group_by functions",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/list_helper.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 2,
    },
    # Phase 4: Date utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p4-date-util",
        "name": "Date utility module",
        "description": "Create a date utility module with format_date, parse_date, add_days, and diff_days functions using Python datetime module",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/date_helper.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 3,
    },
    # Phase 5: Dict utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p5-dict-util",
        "name": "Dict utility module",
        "description": "Create a dict utility module with deep_merge, get_nested, set_nested, and filter_keys functions",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/dict_helper.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 4,
    },
    # Phase 6: String utility tests (medium complexity, 2 files)
    {
        "phase_id": "telemetry-p6-string-tests",
        "name": "String helper tests",
        "description": "Create comprehensive tests for string_helper module with fixtures",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": ["examples/telemetry_utils/string_helper.py"],
            "deliverables": [
                "examples/telemetry_utils/test_string_helper.py",
                "examples/telemetry_utils/conftest.py",
            ],
        },
        "complexity": "medium",
        "task_category": "tests",
        "phase_index": 5,
    },
    # Phase 7: Number utility tests (low complexity, 1 file)
    {
        "phase_id": "telemetry-p7-number-tests",
        "name": "Number helper tests",
        "description": "Create comprehensive tests for number_helper module",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/number_helper.py",
                "examples/telemetry_utils/conftest.py",
            ],
            "deliverables": ["examples/telemetry_utils/test_number_helper.py"],
        },
        "complexity": "low",
        "task_category": "tests",
        "phase_index": 6,
    },
    # Phase 8: List utility tests (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p8-list-tests",
        "name": "List helper tests",
        "description": "Create comprehensive tests for list_helper module",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/list_helper.py",
                "examples/telemetry_utils/conftest.py",
            ],
            "deliverables": ["examples/telemetry_utils/test_list_helper.py"],
        },
        "complexity": "medium",
        "task_category": "tests",
        "phase_index": 7,
    },
    # Phase 9: README documentation (low complexity, 1 file)
    {
        "phase_id": "telemetry-p9-readme",
        "name": "Telemetry utils README",
        "description": "Create README.md for telemetry_utils with usage examples",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/string_helper.py",
                "examples/telemetry_utils/number_helper.py",
                "examples/telemetry_utils/list_helper.py",
            ],
            "deliverables": ["examples/telemetry_utils/README.md"],
        },
        "complexity": "low",
        "task_category": "docs",
        "phase_index": 8,
    },
    # Phase 10: File utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p10-file-util",
        "name": "File utility module",
        "description": "Create a file utility module with read_json, write_json, read_lines, and write_lines functions",
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/file_helper.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 9,
    },
]


def create_run():
    """Create the telemetry collection run via direct database access."""

    session = SessionLocal()

    try:
        # Check if run exists
        existing_run = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing_run:
            print(f"[ERROR] Run {RUN_ID} already exists")
            print("        To recreate, first delete with:")
            db_url = os.environ.get("DATABASE_URL", "sqlite:///autopack_telemetry_seed.db")
            print(f'        PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="{db_url}" python -c \\')
            print(
                '            "from autopack.database import SessionLocal; from autopack.models import Run; \\'
            )
            print(
                f"             s = SessionLocal(); s.query(Run).filter(Run.id == '{RUN_ID}').delete(); s.commit(); s.close()\""
            )
            sys.exit(1)

        # Create run
        run = Run(
            id=RUN_ID,
            state=RunState.RUN_CREATED,
            token_cap=500000,  # 500k tokens should be plenty for 10 simple phases
            max_phases=15,
            max_duration_minutes=120,
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {RUN_ID}")

        # Create tier (required for phases)
        tier = Tier(
            tier_id=TIER_ID,
            run_id=RUN_ID,
            tier_index=0,
            name="Telemetry Collection Tier",
            description="Simple utility implementations for telemetry collection",
            state=TierState.PENDING,
            token_cap=500000,
            ci_run_cap=20,
        )
        session.add(tier)
        session.flush()

        print(f"[OK] Created tier: {TIER_ID}")

        # Create phases
        print(f"\nCreating {len(PHASES)} phases...")
        for phase_def in PHASES:
            phase = Phase(
                run_id=RUN_ID,
                tier_id=tier.id,
                phase_id=phase_def["phase_id"],
                phase_index=phase_def["phase_index"],
                name=phase_def["name"],
                description=phase_def["description"],
                state=PhaseState.QUEUED,
                scope=phase_def["scope"],
                complexity=phase_def["complexity"],
                task_category=phase_def["task_category"],
                max_builder_attempts=3,
                max_auditor_attempts=2,
                incident_token_cap=50000,
            )
            session.add(phase)
            print(
                f"  [{phase_def['phase_index']+1:2d}] {phase_def['phase_id']:35s} ({phase_def['complexity']:6s} {phase_def['task_category']})"
            )

        session.commit()

        print(f"\n{'='*70}")
        print("TELEMETRY COLLECTION RUN CREATED")
        print(f"{'='*70}")
        print(f"Run ID: {RUN_ID}")
        print(f"Total phases: {len(PHASES)}")
        print("\nPhase breakdown:")
        print("  Implementation: 6 phases (3 low, 3 medium complexity)")
        print("  Tests: 3 phases (1 low, 2 medium complexity)")
        print("  Docs: 1 phase (low complexity)")
        print("\nDeliverable counts:")
        print("  1 file: 9 phases")
        print("  2 files: 1 phase")
        print("\nExpected telemetry samples: 10+ successful Builder executions")
        print("\nTo drain individual phases:")
        db_url = os.environ.get("DATABASE_URL", "sqlite:///autopack_telemetry_seed.db")
        print(f'  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="{db_url}" \\')
        print("      TELEMETRY_DB_ENABLED=1 timeout 600 \\")
        print(f"      python scripts/drain_one_phase.py --run-id {RUN_ID} --phase-id <phase_id>")
        print("\nOr drain all phases in batch:")
        print(f'  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="{db_url}" \\')
        print(f"      python scripts/batch_drain_controller.py --run-id {RUN_ID} --batch-size 10")
        print(f"{'='*70}\n")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_run()
