"""
Telemetry Data Collection Script

Runs multiple autonomous executions to collect [TokenEstimation] telemetry data
for validating BUILD-129 Phase 1 TokenEstimator accuracy.

This script creates small, focused autonomous runs across different complexity
levels to gather diverse telemetry samples.

Usage:
    python scripts/collect_telemetry_data.py [--count N]
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, RunState, PhaseState
from autopack.autonomous_executor import AutonomousExecutor


# Small test runs with varying complexity for telemetry collection
TELEMETRY_TEST_RUNS = [
    {
        "run_id": "telemetry-simple-util",
        "goal": "Create a simple string utility function",
        "phases": [
            {
                "phase_id": "phase-0-util",
                "goal": "Create src/utils/string_helpers.py with capitalize_words function",
                "deliverables": ["src/utils/string_helpers.py"],
                "complexity": "low",
                "scope": {"paths": ["src/utils/"], "read_only_context": []}
            }
        ]
    },
    {
        "run_id": "telemetry-medium-validator",
        "goal": "Create a data validator module",
        "phases": [
            {
                "phase_id": "phase-0-validator",
                "goal": "Create src/utils/data_validator.py with email and phone validation",
                "deliverables": ["src/utils/data_validator.py"],
                "complexity": "medium",
                "scope": {"paths": ["src/utils/"], "read_only_context": []}
            }
        ]
    },
    {
        "run_id": "telemetry-config-parser",
        "goal": "Create a JSON config parser",
        "phases": [
            {
                "phase_id": "phase-0-config",
                "goal": "Create src/utils/config_parser.py that reads and validates JSON configs",
                "deliverables": ["src/utils/config_parser.py"],
                "complexity": "medium",
                "scope": {"paths": ["src/utils/"], "read_only_context": []}
            }
        ]
    },
    {
        "run_id": "telemetry-test-helper",
        "goal": "Create test fixture helpers",
        "phases": [
            {
                "phase_id": "phase-0-fixtures",
                "goal": "Create tests/fixtures/sample_data.py with test data generators",
                "deliverables": ["tests/fixtures/sample_data.py"],
                "complexity": "low",
                "scope": {"paths": ["tests/fixtures/"], "read_only_context": []}
            }
        ]
    },
    {
        "run_id": "telemetry-multi-file",
        "goal": "Create a simple cache module with tests",
        "phases": [
            {
                "phase_id": "phase-0-cache",
                "goal": "Create src/utils/cache.py with in-memory cache and tests/test_cache.py",
                "deliverables": [
                    "src/utils/cache.py",
                    "tests/test_cache.py"
                ],
                "complexity": "medium",
                "scope": {
                    "paths": ["src/utils/", "tests/"],
                    "read_only_context": []
                }
            }
        ]
    }
]


def create_telemetry_run(db_session, run_config: dict) -> Run:
    """Create a telemetry collection run in database.

    Args:
        db_session: Database session
        run_config: Run configuration dict

    Returns:
        Created Run instance
    """
    run = Run(
        run_id=run_config["run_id"],
        run_type="telemetry_collection",
        goal=run_config["goal"],
        status="pending",
        created_at=datetime.utcnow()
    )
    db_session.add(run)
    db_session.commit()

    # Create phases
    for phase_config in run_config["phases"]:
        phase = Phase(
            phase_id=phase_config["phase_id"],
            run_id=run.run_id,
            goal=phase_config["goal"],
            deliverables=json.dumps(phase_config["deliverables"]),
            status="pending",
            plan=json.dumps({
                "deliverables": phase_config["deliverables"],
                "complexity": phase_config["complexity"],
                "scope": phase_config["scope"]
            })
        )
        db_session.add(phase)

    db_session.commit()
    return run


def run_telemetry_collection(run_config: dict, workspace_root: Path):
    """Execute a single telemetry collection run.

    Args:
        run_config: Run configuration
        workspace_root: Project root directory
    """
    print(f"\n{'='*60}")
    print(f"Starting telemetry run: {run_config['run_id']}")
    print(f"Goal: {run_config['goal']}")
    print(f"{'='*60}\n")

    # Create run in database
    db = SessionLocal()
    try:
        run = create_telemetry_run(db, run_config)
        print(f"✓ Created run {run.run_id} in database")

        # Execute the run
        executor = AutonomousExecutor(
            run_id=run.run_id,
            workspace_root=workspace_root,
            db_session=db
        )

        result = executor.execute()

        print(f"\n{'='*60}")
        print(f"Completed: {run_config['run_id']}")
        print(f"Status: {result.get('status', 'unknown')}")
        print(f"{'='*60}\n")

        return result

    except Exception as e:
        print(f"Error in telemetry run {run_config['run_id']}: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Collect token estimation telemetry data"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of telemetry runs to execute (default: 5, max: 5)"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Workspace root directory"
    )

    args = parser.parse_args()

    # Limit to available runs
    count = min(args.count, len(TELEMETRY_TEST_RUNS))

    print(f"\n{'='*60}")
    print(f"TOKEN ESTIMATION TELEMETRY COLLECTION")
    print(f"{'='*60}")
    print(f"Running {count} telemetry collection runs")
    print(f"Workspace: {args.workspace}")
    print(f"\nObjective: Collect [TokenEstimation] data for BUILD-129 validation")
    print(f"Target: <30% mean error rate")
    print(f"{'='*60}\n")

    results = []
    for i, run_config in enumerate(TELEMETRY_TEST_RUNS[:count], 1):
        print(f"\n[{i}/{count}] Processing {run_config['run_id']}...")
        result = run_telemetry_collection(run_config, args.workspace)
        results.append({
            "run_id": run_config["run_id"],
            "result": result
        })

    # Summary
    print(f"\n{'='*60}")
    print(f"TELEMETRY COLLECTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total runs: {count}")

    successful = sum(1 for r in results if r["result"].get("status") == "completed")
    failed = count - successful

    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"\nNext steps:")
    print(f"1. Run analysis: python scripts/analyze_token_telemetry.py")
    print(f"2. Review error rates and tune if needed")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
