"""
Create telemetry-collection-v8b validation run to test BUILD-142 override fix.

Tests the conditional 16384 override fix with 3 docs/low phases.

Expected results:
- docs/low phases should use selected_budget=4096 (not 16384)
- Zero truncations
- Budget waste ~1.2x (down from 34.9x in V8)

PATCH-SAFE DESIGN:
- ALL deliverables are NEW FILES under examples/telemetry_v8b_docs/
- No modifications to existing directories

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/create_telemetry_v8b_override_fix_validation.py
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to prevent silent fallback
if not os.environ.get("DATABASE_URL"):
    print("[telemetry_v8b_seed] ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (PowerShell):", file=sys.stderr)
    print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v5.db'", file=sys.stderr)
    print("  python scripts/create_telemetry_v8b_override_fix_validation.py", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
from datetime import datetime, timezone
import json

def create_telemetry_v8b_run():
    """Create telemetry-collection-v8b validation run (3 docs/low phases, patch-safe)."""

    # Initialize database
    print("Initializing database...")
    init_db()

    session = SessionLocal()

    try:
        # Create run
        run = Run(
            id="telemetry-collection-v8b-override-fix",
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            goal_anchor=json.dumps({
                "goal": (
                    "V8b: Validate BUILD-142 conditional override fix. "
                    "3 docs/low phases to confirm category-aware budgets (4096) are preserved, "
                    "not overridden to 16384. PATCH-SAFE: all new files."
                ),
                "purpose": "telemetry_v8b_override_fix_validation",
                "target_validation": [
                    "docs/low: selected_budget=4096 (not 16384 override)",
                    "Zero truncations (safety validation)",
                    "Budget waste ~1.2x (was 34.9x in V8 pre-fix)"
                ],
                "build_142_fix": [
                    "Conditional override: skip 16384 floor for docs-like categories",
                    "Telemetry semantics: selected_budget records estimator intent",
                    "Safety preserved: non-docs categories still get 16384 floor"
                ],
                "patch_safety": [
                    "All deliverables are new files",
                    "Files created under examples/telemetry_v8b_docs/",
                    "No modifications to existing directories"
                ]
            })
        )
        session.add(run)
        session.flush()
        print(f"✅ Created run: {run.id}")

        # Create single tier
        tier = Tier(
            tier_id="telemetry-v8b-T1",
            run_id=run.id,
            tier_index=1,
            name="telemetry-v8b-tier1",
            description="Single tier for v8b override fix validation",
            state=TierState.IN_PROGRESS,
            created_at=datetime.now(timezone.utc)
        )
        session.add(tier)
        session.flush()
        print("✅ Created tier 1")

        # === DOCS/LOW PHASES (3) ===
        docs_low_phases = [
            {
                "phase_id": "telemetry-v8b-d1-installation-steps",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8b_docs/installation_steps.md"],
                "goal": (
                    "Create new file examples/telemetry_v8b_docs/installation_steps.md (≤120 lines). "
                    "Write simple installation steps: prerequisites, install command, verify installation. "
                    "Use numbered list format. Minimal context (≤3 files)."
                ),
            },
            {
                "phase_id": "telemetry-v8b-d2-configuration-basics",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8b_docs/configuration_basics.md"],
                "goal": (
                    "Create new file examples/telemetry_v8b_docs/configuration_basics.md (≤150 lines). "
                    "Document basic configuration options: 4-5 key settings with brief descriptions. "
                    "Include 1 example config snippet. Minimal context (≤4 files)."
                ),
            },
            {
                "phase_id": "telemetry-v8b-d3-troubleshooting-tips",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["examples/telemetry_v8b_docs/troubleshooting_tips.md"],
                "goal": (
                    "Create new file examples/telemetry_v8b_docs/troubleshooting_tips.md (≤130 lines). "
                    "List 5-6 common issues with solutions. Use Q&A format. "
                    "Keep solutions brief (2-3 sentences each). Minimal context (≤3 files)."
                ),
            },
        ]

        # Create phases
        for idx, phase_def in enumerate(docs_low_phases, 1):
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
        print("\n✅ Successfully created telemetry-collection-v8b-override-fix with 3 phases")
        print("   - docs/low: 3 phases (expect selected_budget=4096 each)")
        print("\nDrain with:")
        print("  python scripts/drain_queued_phases.py --run-id telemetry-collection-v8b-override-fix \\")
        print("    --batch-size 10 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance")

    except Exception as e:
        session.rollback()
        print(f"❌ Error creating run: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_telemetry_v8b_run()
