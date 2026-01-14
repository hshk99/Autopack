"""
DEPRECATED: This script has schema mismatches with current ORM models.

Use scripts/create_telemetry_collection_run.py instead.

The issues with this script:
1. Uses wrong Phase fields (status vs state, deliverables as JSON string vs scope dict)
2. Uses AutonomousExecutor incorrectly (not how phases are drained)
3. Does not create required Tier parent objects

For telemetry collection, use the updated workflow:
1. Create run: python scripts/create_telemetry_collection_run.py
2. Drain phases: python scripts/drain_queued_phases.py --run-id telemetry-collection-v4
"""

import sys


def main():
    print("=" * 70)
    print("DEPRECATED SCRIPT")
    print("=" * 70)
    print()
    print("This script (collect_telemetry_data.py) is deprecated due to schema mismatches.")
    print()
    print("Use the following instead:")
    print()
    print("1. Create telemetry collection run:")
    print('   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \\')
    print("       python scripts/create_telemetry_collection_run.py")
    print()
    print("2. Drain phases to collect telemetry:")
    print('   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \\')
    print("       TELEMETRY_DB_ENABLED=1 \\")
    print(
        "       python scripts/drain_queued_phases.py --run-id telemetry-collection-v4 --batch-size 5"
    )
    print()
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
