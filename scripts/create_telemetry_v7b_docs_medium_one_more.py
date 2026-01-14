"""
Create telemetry-collection-v7b: 1 docs/medium phase to reach min-samples=5.

BUILD-141 Part 10b: Close docs/medium gap (4→5 samples).

PATCH-SAFE DESIGN:
- Deliverable is a NEW FILE under examples/telemetry_v7_docs/
- Goal includes "create new file" instruction to avoid edit-mode
- No modifications to existing docs/ directory

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/create_telemetry_v7b_docs_medium_one_more.py
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to prevent silent fallback
if not os.environ.get("DATABASE_URL"):
    print("[telemetry_v7b_seed] ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (PowerShell):", file=sys.stderr)
    print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v5.db'", file=sys.stderr)
    print("  python scripts/create_telemetry_v7b_docs_medium_one_more.py", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
from datetime import datetime, timezone
import json


def create_telemetry_v7b_run():
    """Create telemetry-collection-v7b: 1 docs/medium phase (patch-safe)."""

    # Initialize database
    print("Initializing database...")
    init_db()

    session = SessionLocal()

    try:
        # Create run
        run = Run(
            id="telemetry-collection-v7b",
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            goal_anchor=json.dumps(
                {
                    "goal": (
                        "V7b: Single docs/medium phase to close min-samples gap (4→5). "
                        "PATCH-SAFE: deliverable is NEW FILE under examples/telemetry_v7_docs/ "
                        "to avoid PATCH_FAILED errors."
                    ),
                    "purpose": "telemetry_v7b_docs_medium_sampling",
                    "target_groups": ["docs/medium"],
                    "v7_status": "docs/medium n=4, need 1 more to reach min-samples=5",
                    "patch_safety": [
                        "Deliverable is a new file (no edits to existing files)",
                        "File created under examples/telemetry_v7_docs/",
                        "Goal includes explicit 'create new file' instruction",
                    ],
                }
            ),
        )
        session.add(run)
        session.flush()
        print(f"✅ Created run: {run.id}")

        # Create single tier
        tier = Tier(
            tier_id="telemetry-v7b-T1",
            run_id=run.id,
            tier_index=1,
            name="telemetry-v7b-tier1",
            description="Single tier for v7b patch-safe docs/medium sampling",
            state=TierState.IN_PROGRESS,
            created_at=datetime.now(timezone.utc),
        )
        session.add(tier)
        session.flush()
        print("✅ Created tier 1")

        # Single docs/medium phase
        phase = Phase(
            run_id=run.id,
            tier_id=tier.id,
            phase_id="telemetry-v7b-d1-error-recovery-guide",
            phase_index=1,
            name="telemetry-v7b-d1-error-recovery-guide",
            description=(
                "Create new file examples/telemetry_v7_docs/error_recovery_guide.md (≤250 lines). "
                "Document error recovery strategies: retry logic, fallback patterns, error categorization. "
                "Use bullet-point style. Include 1-2 code examples from existing error handling. "
                "Load minimal context (≤8 files from src/autopack/)."
            ),
            state=PhaseState.QUEUED,
            task_category="docs",
            complexity="medium",
            scope=json.dumps(
                {
                    "deliverables": ["examples/telemetry_v7_docs/error_recovery_guide.md"],
                }
            ),
            created_at=datetime.now(timezone.utc),
        )
        session.add(phase)
        print("  [01] telemetry-v7b-d1-error-recovery-guide (docs/medium, 1 deliverable)")

        session.commit()
        print("\n✅ Successfully created telemetry-collection-v7b with 1 phase")
        print("   - docs/medium: 1 phase")
        print("\nDrain with:")
        print("  python scripts/drain_queued_phases.py --run-id telemetry-collection-v7b \\")
        print(
            "    --batch-size 5 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance"
        )

    except Exception as e:
        session.rollback()
        print(f"❌ Error creating run: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_telemetry_v7b_run()
