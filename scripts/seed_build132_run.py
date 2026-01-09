"""
Seed BUILD-132 Run Directly in Database

Creates BUILD-132: Coverage Delta Integration run with 4 phases.
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

RUN_ID = "build132-coverage-delta-integration"

def seed_run():
    """Seed BUILD-132 run in database."""

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
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=300000,
            max_phases=5,
            max_duration_minutes=180,
            goal_anchor="BUILD-132: Coverage Delta Integration for Quality Gate"
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {RUN_ID}")

        # Create tiers
        tiers_data = [
            {"tier_id": "T1-Setup", "tier_index": 0, "name": "Setup"},
            {"tier_id": "T2-Implementation", "tier_index": 1, "name": "Implementation"},
            {"tier_id": "T3-Documentation", "tier_index": 2, "name": "Documentation"}
        ]

        tier_db_ids = {}
        for tier_data in tiers_data:
            tier = Tier(
                tier_id=tier_data["tier_id"],
                run_id=RUN_ID,
                name=tier_data["name"],
                tier_index=tier_data["tier_index"]
            )
            session.add(tier)
            session.flush()
            tier_db_ids[tier_data["tier_id"]] = tier.id
            print(f"[OK] Created tier: {tier_data['tier_id']}")

        # Create phases
        phases_data = [
            {
                "phase_id": "build132-phase1-enable-coverage",
                "tier_id": "T1-Setup",
                "phase_index": 0,
                "name": "Enable Coverage Collection",
                "description": """Update pytest.ini to enable pytest-cov coverage collection.

Tasks:
1. Update pytest.ini to add coverage flags:
   --cov=src/autopack
   --cov-report=term-missing:skip-covered
   --cov-report=json:.coverage.json
   --cov-branch

2. Add .coverage.json and .coverage_baseline.json to .gitignore

Files to modify:
- pytest.ini
- .gitignore

DO NOT establish T0 baseline yet - that's Phase 4.""",
                "deliverables": ["pytest.ini", ".gitignore"],
                "task_category": "configuration",
                "complexity": "low"
            },
            {
                "phase_id": "build132-phase2-coverage-tracker",
                "tier_id": "T2-Implementation",
                "phase_index": 0,
                "name": "Create CoverageTracker Module",
                "description": """Create coverage delta calculation module with comprehensive tests.

Create src/autopack/coverage_tracker.py with:

1. CoverageTracker class:
   - __init__(workspace_root: Path)
   - get_baseline_coverage() -> Optional[float]
   - get_current_coverage() -> Optional[float]
   - _extract_coverage_percentage(coverage_data: Dict) -> float
   - calculate_delta() -> Tuple[float, Dict]

2. Convenience function:
   - calculate_coverage_delta(workspace_root: Path) -> float

Create tests/test_coverage_tracker.py with:
- test_calculate_delta_success (baseline 80%, current 85% -> delta +5%)
- test_calculate_delta_regression (baseline 90%, current 85% -> delta -5%)
- test_missing_baseline (returns 0.0 with error metadata)
- test_missing_current (returns 0.0 with error metadata)
- test_invalid_json (handles gracefully)
- test_convenience_function (calculate_coverage_delta works)

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 114-375 for complete code.

Files to create:
- src/autopack/coverage_tracker.py (~100 lines)
- tests/test_coverage_tracker.py (~150 lines)""",
                "deliverables": ["src/autopack/coverage_tracker.py", "tests/test_coverage_tracker.py"],
                "task_category": "implementation",
                "complexity": "medium"
            },
            {
                "phase_id": "build132-phase3-executor-integration",
                "tier_id": "T2-Implementation",
                "phase_index": 1,
                "name": "Integrate CoverageTracker with Executor",
                "description": """Replace hardcoded coverage_delta=0.0 with actual calculation.

Modify src/autopack/autonomous_executor.py:

1. Add import at top:
   from autopack.coverage_tracker import calculate_coverage_delta

2. Replace all 8 instances of hardcoded coverage_delta=0.0:
   Lines: 4536, 4556, 5167, 5179, 5716, 5728, 6055, 6067

   OLD:
   coverage_delta=0.0,  # TODO: Calculate actual coverage delta

   NEW:
   coverage_delta=calculate_coverage_delta(Path.cwd()) if ci_success else 0.0,

3. Add graceful fallback:
   - If coverage files missing, returns 0.0
   - Log warning but don't block execution
   - Quality Gate will simply not have coverage data

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 377-450

Files to modify:
- src/autopack/autonomous_executor.py (8 locations)""",
                "deliverables": ["src/autopack/autonomous_executor.py"],
                "task_category": "integration",
                "complexity": "medium"
            },
            {
                "phase_id": "build132-phase4-documentation",
                "tier_id": "T3-Documentation",
                "phase_index": 0,
                "name": "Documentation and Baseline Setup",
                "description": """Update documentation to reflect BUILD-132 completion.

Tasks:
1. Update BUILD_HISTORY.md:
   - Add BUILD-132 entry at top of chronological index
   - Status: COMPLETE
   - Summary: Coverage Delta Integration - replaces hardcoded 0.0 with pytest-cov tracking
   - Files: pytest.ini, coverage_tracker.py, test_coverage_tracker.py, autonomous_executor.py
   - Impact: Quality Gate can now detect coverage regressions

2. Update BUILD_LOG.md:
   - Add 2025-12-23 entry for BUILD-132
   - Document 4 phases completed
   - Note: T0 baseline establishment pending (run pytest with --cov)

3. Create docs/BUILD-132_IMPLEMENTATION_STATUS.md:
   - Document completion status
   - Usage instructions for establishing baseline
   - Quality Gate integration confirmed

Reference: docs/BUILD-132_COVERAGE_DELTA_INTEGRATION.md lines 452-550

Files to modify:
- BUILD_HISTORY.md
- BUILD_LOG.md

Files to create:
- docs/BUILD-132_IMPLEMENTATION_STATUS.md""",
                "deliverables": ["BUILD_HISTORY.md", "BUILD_LOG.md", "docs/BUILD-132_IMPLEMENTATION_STATUS.md"],
                "task_category": "docs",
                "complexity": "low"
            }
        ]

        for phase_data in phases_data:
            # Build scope with deliverables for token estimation
            scope_config = {
                "deliverables": phase_data.get("deliverables", []),
                "paths": [],
                "read_only_context": []
            }

            phase = Phase(
                phase_id=phase_data["phase_id"],
                run_id=RUN_ID,
                tier_id=tier_db_ids[phase_data["tier_id"]],
                phase_index=phase_data["phase_index"],
                name=phase_data["name"],
                description=phase_data["description"],
                scope=scope_config,
                state=PhaseState.QUEUED,
                task_category=phase_data["task_category"],
                complexity=phase_data["complexity"]
            )
            session.add(phase)
            print(f"[OK] Created phase: {phase_data['phase_id']} with {len(scope_config['deliverables'])} deliverables")

        session.commit()

        print("\n[SUCCESS] BUILD-132 run seeded successfully!")
        print("\nSummary:")
        print(f"- Run ID: {RUN_ID}")
        print(f"- Total phases: {len(phases_data)}")
        print(f"- Total tiers: {len(tiers_data)}")
        print("- Expected telemetry samples: 4+ successful Builder executions")
        print("\nTo execute:")
        print("  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" \\")
        print(f"    python -m autopack.autonomous_executor --run-id {RUN_ID}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    seed_run()
