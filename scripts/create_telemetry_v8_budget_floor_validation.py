"""
Create telemetry-collection-v8-budget-floors validation run (5 phases).

BUILD-142: Validate category-aware base budget floors reduce waste without truncation.

Target validation:
- 3 docs/low phases (expect base=4096 instead of 8192, waste ~1.2x instead of 2.4x)
- 2 tests/low phases (expect base=6144 instead of 8192, waste ~1.5x instead of 10x)

PATCH-SAFE DESIGN:
- ALL deliverables are NEW FILES under examples/telemetry_v8_*/
- No modifications to existing docs/ or tests/ directories

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/create_telemetry_v8_budget_floor_validation.py
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to prevent silent fallback
if not os.environ.get("DATABASE_URL"):
    print("[telemetry_v8_seed] ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (PowerShell):", file=sys.stderr)
    print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v5.db'", file=sys.stderr)
    print("  python scripts/create_telemetry_v8_budget_floor_validation.py", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
from datetime import datetime, timezone
import json

def create_telemetry_v8_run():
    """Create telemetry-collection-v8-budget-floors validation run (5 phases, patch-safe)."""

    # Initialize database
    print("Initializing database...")
    init_db()

    session = SessionLocal()

    try:
        # Create run
        run = Run(
            id="telemetry-collection-v8-budget-floors",
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            goal_anchor=json.dumps({
                "goal": (
                    "V8: Validate BUILD-142 category-aware base budget floors. "
                    "5 phases (3 docs/low, 2 tests/low) to confirm zero truncations "
                    "and budget waste reduction. PATCH-SAFE: all new files."
                ),
                "purpose": "telemetry_v8_budget_floor_validation",
                "target_validation": [
                    "docs/low: base=4096 (was 8192), expect waste ~1.2x (was 2.4x)",
                    "tests/low: base=6144 (was 8192), expect waste ~1.5x (was 10x)",
                    "Zero truncations (safety validation)"
                ],
                "patch_safety": [
                    "All deliverables are new files",
                    "Files created under examples/telemetry_v8_docs/ and examples/telemetry_v8_tests/",
                    "No modifications to existing directories"
                ]
            })
        )
        session.add(run)
        session.flush()
        print(f"✅ Created run: {run.id}")

        # Create single tier
        tier = Tier(
            tier_id="telemetry-v8-T1",
            run_id=run.id,
            tier_index=1,
            name="telemetry-v8-tier1",
            description="Single tier for v8 budget floor validation phases",
            state=TierState.IN_PROGRESS,
            created_at=datetime.now(timezone.utc)
        )
        session.add(tier)
        session.flush()
        print(f"✅ Created tier 1")

        # === DOCS/LOW PHASES (3) ===
        docs_low_phases = [
            {
                "phase_id": "telemetry-v8-d1-quickstart-simple",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8_docs/quickstart_simple.md"],
                "goal": (
                    "Create new file examples/telemetry_v8_docs/quickstart_simple.md (≤150 lines). "
                    "Write a simple quickstart guide with 3-4 bullet points: install, configure, run first command. "
                    "Minimal context (≤5 files). Keep it brief and direct."
                ),
            },
            {
                "phase_id": "telemetry-v8-d2-faq-brief",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8_docs/faq_brief.md"],
                "goal": (
                    "Create new file examples/telemetry_v8_docs/faq_brief.md (≤120 lines). "
                    "List 5-6 common FAQs in bullet format with brief answers (2-3 sentences each). "
                    "Minimal context (≤4 files)."
                ),
            },
            {
                "phase_id": "telemetry-v8-d3-glossary",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8_docs/glossary.md"],
                "goal": (
                    "Create new file examples/telemetry_v8_docs/glossary.md (≤100 lines). "
                    "Define 8-10 key terms used in the project (Phase, Tier, Run, Builder, Auditor, etc.). "
                    "One sentence per definition. Minimal context (≤3 files)."
                ),
            },
        ]

        # === TESTS/LOW PHASES (2) ===
        tests_low_phases = [
            {
                "phase_id": "telemetry-v8-t1-simple-unit-test",
                "category": "tests",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8_tests/test_simple_utils.py"],
                "goal": (
                    "Create new file examples/telemetry_v8_tests/test_simple_utils.py. "
                    "Write 2-3 simple unit tests for a utility function (e.g., string formatting, path normalization). "
                    "Use pytest. Keep it minimal (≤80 lines total). Load minimal context (≤3 files)."
                ),
            },
            {
                "phase_id": "telemetry-v8-t2-enum-validation-test",
                "category": "tests",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8_tests/test_enum_validation.py"],
                "goal": (
                    "Create new file examples/telemetry_v8_tests/test_enum_validation.py. "
                    "Write 2-3 simple tests validating enum values (e.g., PhaseState, RunState). "
                    "Use pytest. Keep it minimal (≤70 lines total). Load minimal context (models.py only)."
                ),
            },
        ]

        # Combine all phases
        all_phases = docs_low_phases + tests_low_phases

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
        print(f"\n✅ Successfully created telemetry-collection-v8-budget-floors with 5 phases")
        print(f"   - docs/low: 3 phases (expect base=4096 each)")
        print(f"   - tests/low: 2 phases (expect base=6144 each)")
        print(f"\nDrain with:")
        print(f"  python scripts/drain_queued_phases.py --run-id telemetry-collection-v8-budget-floors \\")
        print(f"    --batch-size 10 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance")

    except Exception as e:
        session.rollback()
        print(f"❌ Error creating run: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_telemetry_v8_run()
