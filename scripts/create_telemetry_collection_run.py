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
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ["DATABASE_URL"] = "sqlite:///autopack.db"

from autopack.database import SessionLocal
from autopack.models import Run, Phase, RunState, PhaseState

RUN_ID = "telemetry-collection-v4"

# 10 simple, achievable phases
PHASES = [
    # Phase 1: String utility (low complexity, 1 file)
    {
        "phase_id": "telemetry-p1-string-util",
        "goal": "Create a string utility module with capitalize_words and reverse_string functions",
        "deliverables": ["examples/telemetry_utils/string_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "low",
        "category": "implementation",
        "priority": 1
    },

    # Phase 2: Number utility (low complexity, 1 file)
    {
        "phase_id": "telemetry-p2-number-util",
        "goal": "Create a number utility module with is_even, is_prime, and factorial functions",
        "deliverables": ["examples/telemetry_utils/number_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "low",
        "category": "implementation",
        "priority": 2
    },

    # Phase 3: List utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p3-list-util",
        "goal": "Create a list utility module with chunk, flatten, unique, and group_by functions",
        "deliverables": ["examples/telemetry_utils/list_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "medium",
        "category": "implementation",
        "priority": 3
    },

    # Phase 4: Date utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p4-date-util",
        "goal": "Create a date utility module with format_date, parse_date, add_days, and diff_days functions using Python datetime module",
        "deliverables": ["examples/telemetry_utils/date_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "medium",
        "category": "implementation",
        "priority": 4
    },

    # Phase 5: Dict utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p5-dict-util",
        "goal": "Create a dict utility module with deep_merge, get_nested, set_nested, and filter_keys functions",
        "deliverables": ["examples/telemetry_utils/dict_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "medium",
        "category": "implementation",
        "priority": 5
    },

    # Phase 6: String utility tests (medium complexity, 2 files)
    {
        "phase_id": "telemetry-p6-string-tests",
        "goal": "Create comprehensive tests for string_helper module with fixtures",
        "deliverables": [
            "examples/telemetry_utils/test_string_helper.py",
            "examples/telemetry_utils/conftest.py"
        ],
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": ["examples/telemetry_utils/string_helper.py"]
        },
        "complexity": "medium",
        "category": "tests",
        "priority": 6
    },

    # Phase 7: Number utility tests (low complexity, 1 file)
    {
        "phase_id": "telemetry-p7-number-tests",
        "goal": "Create comprehensive tests for number_helper module",
        "deliverables": ["examples/telemetry_utils/test_number_helper.py"],
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/number_helper.py",
                "examples/telemetry_utils/conftest.py"
            ]
        },
        "complexity": "low",
        "category": "tests",
        "priority": 7
    },

    # Phase 8: List utility tests (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p8-list-tests",
        "goal": "Create comprehensive tests for list_helper module",
        "deliverables": ["examples/telemetry_utils/test_list_helper.py"],
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/list_helper.py",
                "examples/telemetry_utils/conftest.py"
            ]
        },
        "complexity": "medium",
        "category": "tests",
        "priority": 8
    },

    # Phase 9: README documentation (low complexity, 1 file)
    {
        "phase_id": "telemetry-p9-readme",
        "goal": "Create README.md for telemetry_utils with usage examples",
        "deliverables": ["examples/telemetry_utils/README.md"],
        "scope": {
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [
                "examples/telemetry_utils/string_helper.py",
                "examples/telemetry_utils/number_helper.py",
                "examples/telemetry_utils/list_helper.py"
            ]
        },
        "complexity": "low",
        "category": "docs",
        "priority": 9
    },

    # Phase 10: File utility (medium complexity, 1 file)
    {
        "phase_id": "telemetry-p10-file-util",
        "goal": "Create a file utility module with read_json, write_json, read_lines, and write_lines functions",
        "deliverables": ["examples/telemetry_utils/file_helper.py"],
        "scope": {"paths": ["examples/telemetry_utils/"], "read_only_context": []},
        "complexity": "medium",
        "category": "implementation",
        "priority": 10
    }
]

def create_run():
    """Create the telemetry collection run via direct database access."""

    session = SessionLocal()

    try:
        # Check if run exists
        existing = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing:
            print(f"[ERROR] Run {RUN_ID} already exists")
            sys.exit(1)

        # Create run
        run = Run(
            id=RUN_ID,
            state=RunState.QUEUED,
            token_cap=500000,  # 500k tokens should be plenty for 10 simple phases
            max_phases=15,
            max_duration_minutes=60
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {RUN_ID}")

        # Create phases
        print(f"\nCreating {len(PHASES)} phases...")
        for phase_def in PHASES:
            phase = Phase(
                run_id=RUN_ID,
                phase_id=phase_def["phase_id"],
                state=PhaseState.QUEUED,
                goal=phase_def["goal"],
                deliverables=phase_def["deliverables"],
                scope=phase_def["scope"],
                complexity=phase_def["complexity"],
                priority=phase_def["priority"],
                metadata={"telemetry": True, "category": phase_def["category"]}
            )
            session.add(phase)
            print(f"[OK] Created phase: {phase_def['phase_id']}")

        session.commit()

        print(f"\nSummary:")
        print(f"- Total phases: {len(PHASES)}")
        print(f"- Implementation: 6 phases (3 low, 3 medium complexity)")
        print(f"- Tests: 3 phases (1 low, 2 medium complexity)")
        print(f"- Docs: 1 phase (low complexity)")
        print(f"\nDeliverable counts:")
        print(f"- 1 file: 9 phases")
        print(f"- 2 files: 1 phase")
        print(f"\nExpected telemetry samples: 10+ successful Builder executions")
        print(f"\nTo run:")
        print(f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    create_run()
