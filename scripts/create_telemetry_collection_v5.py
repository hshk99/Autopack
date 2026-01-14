"""
Create Telemetry Collection Run v5

Creates a 25-phase autonomous run with achievable phases designed to produce
successful Builder executions for token estimation telemetry collection.

Strategy:
- Simple, self-contained utility functions (no external dependencies)
- Clear, achievable goals
- Mix of complexity levels (low/medium)
- Mix of deliverable counts (1-3 files)
- Mix of categories (implementation/tests/docs)
- Stable, non-truncated outputs

Goal: Collect ≥20 successful telemetry samples (success=True, non-truncated)

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/create_telemetry_collection_v5.py

Then drain with:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        TELEMETRY_DB_ENABLED=1 AUTOPACK_SKIP_CI=1 \
        python scripts/batch_drain_controller.py --run-id telemetry-collection-v5 --batch-size 25
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
        "  DATABASE_URL='sqlite:///./telemetry_seed_v5.db' python scripts/create_telemetry_collection_v5.py",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, TierState, PhaseState

RUN_ID = "telemetry-collection-v5"
TIER_ID = "T1"

# 25 simple, achievable phases (per user specification)
PHASES = [
    # ===== IMPLEMENTATION (15 phases) =====
    # Phase 1: String utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p1-string-utils",
        "name": "String utility module",
        "description": "Create string utility module with capitalize_words, reverse_string, snake_to_camel, truncate functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/string_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 0,
    },
    # Phase 2: Number utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p2-number-utils",
        "name": "Number utility module",
        "description": "Create number utility module with is_even, is_prime, gcd, lcm functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/number_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 1,
    },
    # Phase 3: List utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p3-list-utils",
        "name": "List utility module",
        "description": "Create list utility module with chunk, flatten, unique, rotate functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/list_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 2,
    },
    # Phase 4: Dict utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p4-dict-utils",
        "name": "Dict utility module",
        "description": "Create dict utility module with merge, get_nested, filter_keys, invert functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/dict_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 3,
    },
    # Phase 5: Date utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p5-date-utils",
        "name": "Date utility module",
        "description": "Create date utility module with format_date, parse_date, add_days, diff_days, is_weekend functions using datetime",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/date_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 4,
    },
    # Phase 6: Path utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p6-path-utils",
        "name": "Path utility module",
        "description": "Create path utility module with join_paths, get_extension, change_extension, is_subpath functions using pathlib",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/path_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 5,
    },
    # Phase 7: Textwrap utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p7-textwrap-utils",
        "name": "Textwrap utility module",
        "description": "Create textwrap utility module with wrap_text, indent_text, dedent_text, fill_text functions using textwrap",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/textwrap_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 6,
    },
    # Phase 8: IO utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p8-io-utils",
        "name": "IO utility module",
        "description": "Create IO utility module with read_file, write_file, read_lines, write_lines safe helpers (no network)",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/io_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 7,
    },
    # Phase 9: JSON utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p9-json-utils",
        "name": "JSON utility module",
        "description": "Create JSON utility module with load_json, save_json, pretty_print, validate_json functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/json_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 8,
    },
    # Phase 10: CSV utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p10-csv-utils",
        "name": "CSV utility module",
        "description": "Create CSV utility module with read_csv, write_csv, to_dicts, from_dicts functions using csv module",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/csv_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 9,
    },
    # Phase 11: INI utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p11-ini-utils",
        "name": "INI utility module",
        "description": "Create INI utility module with read_ini, write_ini, get_value, set_value functions using configparser",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/ini_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 10,
    },
    # Phase 12: Logging utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-p12-logging-utils",
        "name": "Logging utility module",
        "description": "Create logging utility module with setup_logger, log_to_file, get_logger functions using logging module",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/logging_utils.py"],
        },
        "complexity": "low",
        "task_category": "implementation",
        "phase_index": 11,
    },
    # Phase 13: Validation utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p13-validation-utils",
        "name": "Validation utility module",
        "description": "Create validation utility module with is_email, is_url, is_int, is_float, validate_range functions",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/validation_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 12,
    },
    # Phase 14: Retry utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-p14-retry-utils",
        "name": "Retry utility module",
        "description": "Create retry utility module with retry_on_exception, exponential_backoff logic (pure logic, no HTTP)",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/retry_utils.py"],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 13,
    },
    # Phase 15: CLI demo (medium, 2 files)
    {
        "phase_id": "telemetry-v5-p15-cli-demo",
        "name": "CLI demo module",
        "description": "Create CLI demo module with argparse-based demo and package __init__.py",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": [
                "examples/telemetry_utils_v5/cli.py",
                "examples/telemetry_utils_v5/__init__.py",
            ],
        },
        "complexity": "medium",
        "task_category": "implementation",
        "phase_index": 14,
    },
    # ===== TESTS (7 phases) =====
    # Phase 16: Test string utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-t1-test-string-utils",
        "name": "String utils tests",
        "description": "Create pytest tests for string_utils module with 10-15 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/string_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_string_utils.py"],
        },
        "complexity": "low",
        "task_category": "tests",
        "phase_index": 15,
    },
    # Phase 17: Test number utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-t2-test-number-utils",
        "name": "Number utils tests",
        "description": "Create pytest tests for number_utils module with 10-15 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/number_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_number_utils.py"],
        },
        "complexity": "low",
        "task_category": "tests",
        "phase_index": 16,
    },
    # Phase 18: Test list utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-t3-test-list-utils",
        "name": "List utils tests",
        "description": "Create pytest tests for list_utils module with 10-15 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/list_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_list_utils.py"],
        },
        "complexity": "low",
        "task_category": "tests",
        "phase_index": 17,
    },
    # Phase 19: Test dict utils (low, 1 file)
    {
        "phase_id": "telemetry-v5-t4-test-dict-utils",
        "name": "Dict utils tests",
        "description": "Create pytest tests for dict_utils module with 10-15 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/dict_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_dict_utils.py"],
        },
        "complexity": "low",
        "task_category": "tests",
        "phase_index": 18,
    },
    # Phase 20: Test date utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-t5-test-date-utils",
        "name": "Date utils tests",
        "description": "Create pytest tests for date_utils module with 15-20 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/date_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_date_utils.py"],
        },
        "complexity": "medium",
        "task_category": "tests",
        "phase_index": 19,
    },
    # Phase 21: Test IO utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-t6-test-io-utils",
        "name": "IO utils tests",
        "description": "Create pytest tests for io_utils module with 15-20 test cases using tmpdir fixture",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": ["examples/telemetry_utils_v5/io_utils.py"],
            "deliverables": ["examples/telemetry_utils_v5/test_io_utils.py"],
        },
        "complexity": "medium",
        "task_category": "tests",
        "phase_index": 20,
    },
    # Phase 22: Test serialization utils (medium, 1 file)
    {
        "phase_id": "telemetry-v5-t7-test-json-csv-utils",
        "name": "Serialization utils tests",
        "description": "Create pytest tests for json_utils and csv_utils modules with 15-20 test cases",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [
                "examples/telemetry_utils_v5/json_utils.py",
                "examples/telemetry_utils_v5/csv_utils.py",
            ],
            "deliverables": ["examples/telemetry_utils_v5/test_serialization_utils.py"],
        },
        "complexity": "medium",
        "task_category": "tests",
        "phase_index": 21,
    },
    # ===== DOCS (3 phases) =====
    # Phase 23: README (low, 1 file)
    {
        "phase_id": "telemetry-v5-d1-readme",
        "name": "README documentation",
        "description": "Create README.md with overview, installation, and quick examples",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [
                "examples/telemetry_utils_v5/string_utils.py",
                "examples/telemetry_utils_v5/number_utils.py",
                "examples/telemetry_utils_v5/list_utils.py",
            ],
            "deliverables": ["examples/telemetry_utils_v5/README.md"],
        },
        "complexity": "low",
        "task_category": "docs",
        "phase_index": 22,
    },
    # Phase 24: Usage examples (low, 1 file)
    {
        "phase_id": "telemetry-v5-d2-usage-examples",
        "name": "Usage examples documentation",
        "description": "Create USAGE.md with detailed examples for each utility module",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [
                "examples/telemetry_utils_v5/string_utils.py",
                "examples/telemetry_utils_v5/dict_utils.py",
                "examples/telemetry_utils_v5/json_utils.py",
            ],
            "deliverables": ["examples/telemetry_utils_v5/USAGE.md"],
        },
        "complexity": "low",
        "task_category": "docs",
        "phase_index": 23,
    },
    # Phase 25: Design notes (low, 1 file)
    {
        "phase_id": "telemetry-v5-d3-design-notes",
        "name": "Design notes documentation",
        "description": "Create DESIGN.md with architecture decisions and design patterns used",
        "scope": {
            "paths": ["examples/telemetry_utils_v5/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils_v5/DESIGN.md"],
        },
        "complexity": "low",
        "task_category": "docs",
        "phase_index": 24,
    },
]


def create_run():
    """Create the telemetry collection run v5 via direct database access."""

    session = SessionLocal()

    try:
        # Check if run exists
        existing_run = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing_run:
            print(f"[ERROR] Run {RUN_ID} already exists")
            print("        To recreate, first delete with:")
            db_url = os.environ.get("DATABASE_URL", "sqlite:///./telemetry_seed_v5.db")
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
            token_cap=1000000,  # 1M tokens for 25 phases
            max_phases=30,
            max_duration_minutes=240,
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {RUN_ID}")

        # Create tier (required for phases)
        tier = Tier(
            tier_id=TIER_ID,
            run_id=RUN_ID,
            tier_index=0,
            name="Telemetry Collection Tier v5",
            description="Stable utility implementations for telemetry collection (25 phases)",
            state=TierState.PENDING,
            token_cap=1000000,
            ci_run_cap=30,
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
                f"  [{phase_def['phase_index']+1:2d}] {phase_def['phase_id']:40s} ({phase_def['complexity']:6s} {phase_def['task_category']})"
            )

        session.commit()

        print(f"\n{'='*75}")
        print("TELEMETRY COLLECTION RUN V5 CREATED")
        print(f"{'='*75}")
        print(f"Run ID: {RUN_ID}")
        print(f"Total phases: {len(PHASES)}")
        print("\nPhase breakdown:")
        print("  Implementation: 15 phases (7 low, 8 medium complexity)")
        print("  Tests: 7 phases (4 low, 3 medium complexity)")
        print("  Docs: 3 phases (3 low complexity)")
        print("\nDeliverable counts:")
        print("  1 file: 24 phases")
        print("  2 files: 1 phase")
        print("\nExpected telemetry samples: ≥20 successful Builder executions")
        print("\nTo drain all phases in batch:")
        db_url = os.environ.get("DATABASE_URL", "sqlite:///./telemetry_seed_v5.db")
        print(f'  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="{db_url}" \\')
        print("      TELEMETRY_DB_ENABLED=1 AUTOPACK_SKIP_CI=1 \\")
        print(
            f"      python scripts/batch_drain_controller.py --run-id {RUN_ID} --batch-size 25 --phase-timeout-seconds 900 --max-total-minutes 120"
        )
        print("\nTo analyze telemetry:")
        print(f'  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="{db_url}" \\')
        print("      python scripts/analyze_token_telemetry_v3.py --success-only")
        print(f"{'='*75}\n")

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
