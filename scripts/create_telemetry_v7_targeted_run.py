"""
Create telemetry-collection-v7 tiny targeted run (6 phases).

BUILD-141 Part 10 Option C: Patch-safe V7 sampling to close remaining weak groups.
- docs/medium: 2→5 (need 3 more)
- tests/low: 4→5 (need 1 more)
- tests/medium: 3→5 (need 2 more)

PATCH-SAFE DESIGN:
- ALL deliverables are NEW FILES under examples/telemetry_v7_*/
- Goals include "create new file" instruction to avoid edit-mode
- No modifications to existing docs/ or tests/ directories

Total: 6 phases (3 docs/medium, 1 tests/low, 2 tests/medium)

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/create_telemetry_v7_targeted_run.py
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to prevent silent fallback
if not os.environ.get("DATABASE_URL"):
    print("[telemetry_v7_seed] ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (PowerShell):", file=sys.stderr)
    print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v5.db'", file=sys.stderr)
    print("  python scripts/create_telemetry_v7_targeted_run.py", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
from datetime import datetime, timezone
import json

def create_telemetry_v7_run():
    """Create telemetry-collection-v7 tiny targeted run (6 phases, patch-safe)."""

    # Initialize database
    print("Initializing database...")
    init_db()

    session = SessionLocal()

    try:
        # Create run
        run = Run(
            id="telemetry-collection-v7",
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            goal_anchor=json.dumps({
                "goal": (
                    "Tiny targeted v7 sampling (6 phases) to close weak groups from v5+v6. "
                    "Focus: docs/medium (2→5), tests/low (4→5), tests/medium (3→5). "
                    "PATCH-SAFE: all deliverables are NEW FILES under examples/telemetry_v7_*/ "
                    "to avoid PATCH_FAILED errors."
                ),
                "purpose": "telemetry_v7_patch_safe_targeted",
                "target_groups": ["docs/medium", "tests/low", "tests/medium"],
                "v6_gaps": {
                    "docs/medium": "n=2, need 3 more to reach min-samples=5",
                    "tests/low": "n=4, need 1 more",
                    "tests/medium": "n=3, need 2 more"
                },
                "patch_safety": [
                    "All deliverables are new files (no edits to existing files)",
                    "Files created under examples/telemetry_v7_docs/ and examples/telemetry_v7_tests/",
                    "Goals include explicit 'create new file' instruction"
                ]
            })
        )
        session.add(run)
        session.flush()
        print(f"✅ Created run: {run.id}")

        # Create single tier
        tier = Tier(
            tier_id="telemetry-v7-T1",
            run_id=run.id,
            tier_index=1,
            name="telemetry-v7-tier1",
            description="Single tier for all v7 patch-safe telemetry sampling phases",
            state=TierState.IN_PROGRESS,
            created_at=datetime.now(timezone.utc)
        )
        session.add(tier)
        session.flush()
        print("✅ Created tier 1")

        # === DOCS/MEDIUM PHASES (3) ===
        docs_medium_phases = [
            {
                "phase_id": "telemetry-v7-d1-api-reference",
                "category": "docs",
                "complexity": "medium",
                "deliverables": ["examples/telemetry_v7_docs/api_reference.md"],
                "goal": (
                    "Create new file examples/telemetry_v7_docs/api_reference.md (≤300 lines). "
                    "Document the Phase Executor API: key classes (PhaseExecutor, PhaseOrchestrator), "
                    "main methods, parameters, return types. Include 2-3 code examples. "
                    "Load minimal context (8-10 files max from src/autopack/)."
                ),
            },
            {
                "phase_id": "telemetry-v7-d2-token-estimation-guide",
                "category": "docs",
                "complexity": "medium",
                "deliverables": ["examples/telemetry_v7_docs/token_estimation_guide.md"],
                "goal": (
                    "Create new file examples/telemetry_v7_docs/token_estimation_guide.md (≤350 lines). "
                    "Explain TokenEstimationV2: how it works, PHASE_OVERHEAD, TOKEN_WEIGHTS, "
                    "budget selection logic. Include 1 real example from token_estimator.py. "
                    "Load minimal context (6-8 files from src/autopack/)."
                ),
            },
            {
                "phase_id": "telemetry-v7-d3-model-selection-guide",
                "category": "docs",
                "complexity": "medium",
                "deliverables": ["examples/telemetry_v7_docs/model_selection_guide.md"],
                "goal": (
                    "Create new file examples/telemetry_v7_docs/model_selection_guide.md (≤300 lines). "
                    "Document ModelSelector: tier-based selection, escalation logic, fallback strategies. "
                    "Include decision flowchart (text-based) and 2 examples. "
                    "Load minimal context (6-8 files)."
                ),
            },
        ]

        # === TESTS/LOW PHASE (1) ===
        tests_low_phases = [
            {
                "phase_id": "telemetry-v7-t1-phase-state-transitions",
                "category": "tests",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v7_tests/test_phase_state_transitions.py"],
                "goal": (
                    "Create new file examples/telemetry_v7_tests/test_phase_state_transitions.py. "
                    "Write 3-4 unit tests for Phase model state transitions (QUEUED→EXECUTING→COMPLETE, "
                    "QUEUED→FAILED). Use pytest. Include docstrings. Keep it simple (≤100 lines total). "
                    "Load minimal context (models.py, 1-2 test examples)."
                ),
            },
        ]

        # === TESTS/MEDIUM PHASES (2) ===
        tests_medium_phases = [
            {
                "phase_id": "telemetry-v7-t2-token-estimator-edge-cases",
                "category": "tests",
                "complexity": "medium",
                "deliverables": ["examples/telemetry_v7_tests/test_token_estimator_edge_cases.py"],
                "goal": (
                    "Create new file examples/telemetry_v7_tests/test_token_estimator_edge_cases.py. "
                    "Write 5-6 pytest tests for TokenEstimator edge cases: zero deliverables, "
                    "huge deliverable counts (100+), missing category/complexity, budget cap at 64K. "
                    "Include fixtures and parametrize. Target ~150-200 lines. "
                    "Load minimal context (token_estimator.py, 1-2 existing test files)."
                ),
            },
            {
                "phase_id": "telemetry-v7-t3-model-selector-fallback",
                "category": "tests",
                "complexity": "medium",
                "deliverables": ["examples/telemetry_v7_tests/test_model_selector_fallback.py"],
                "goal": (
                    "Create new file examples/telemetry_v7_tests/test_model_selector_fallback.py. "
                    "Write 5-7 pytest tests for ModelSelector fallback logic: tier escalation, "
                    "model unavailable scenarios, fallback to cheaper model. "
                    "Use mocks/fixtures. Target ~180-220 lines. "
                    "Load minimal context (model_selector.py, existing selector tests)."
                ),
            },
        ]

        # Combine all phases
        all_phases = docs_medium_phases + tests_low_phases + tests_medium_phases

        # Create phases
        for idx, phase_def in enumerate(all_phases, 1):
            phase = Phase(
                run_id=run.id,
                tier_id=tier.id,
                phase_id=phase_def["phase_id"],
                phase_index=idx,
                name=phase_def["phase_id"],
                description=phase_def["goal"],
                state=PhaseState.QUEUED,
                task_category=phase_def["category"],
                complexity=phase_def["complexity"],
                scope=json.dumps({
                    "deliverables": phase_def["deliverables"],
                }),
                created_at=datetime.now(timezone.utc)
            )
            session.add(phase)
            print(f"  [{idx:02d}] {phase_def['phase_id']} ({phase_def['category']}/{phase_def['complexity']}, {len(phase_def['deliverables'])} deliverable(s))")

        session.commit()
        print("\n✅ Successfully created telemetry-collection-v7 with 6 phases")
        print("   - docs/medium: 3 phases")
        print("   - tests/low: 1 phase")
        print("   - tests/medium: 2 phases")
        print("\nDrain with:")
        print("  python scripts/drain_queued_phases.py --run-id telemetry-collection-v7 \\")
        print("    --batch-size 10 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance")

    except Exception as e:
        session.rollback()
        print(f"❌ Error creating run: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_telemetry_v7_run()
