#!/usr/bin/env python3
"""Create a simple verification test to check if the OpenAI Builder fixes work"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autopack.db_setup import init_db, SessionLocal
from autopack.models import Run, Tier, Phase
from datetime import datetime, timezone

def create_verification_run():
    """Create a minimal test run to verify fixes"""

    print("[INFO] Initializing database...")
    init_db()

    session = SessionLocal()
    try:
        # Create run
        run = Run(
            run_id="fix-verification-20251129",
            safety_profile="standard",
            run_scope="feature_backlog",
            token_cap=50000,
            max_phases=2,
            max_duration_minutes=60,
            created_at=datetime.now(timezone.utc)
        )
        session.add(run)
        session.flush()

        print(f"[OK] Created run: {run.run_id}")

        # Create tier
        tier = Tier(
            run_id=run.run_id,
            tier_id="verify-tier1",
            tier_index=0,
            name="Verification Tier",
            description="Test tier to verify OpenAI Builder fixes"
        )
        session.add(tier)
        session.flush()

        print(f"[OK] Created tier: {tier.tier_id}")

        # Create test phases
        phases = [
            Phase(
                run_id=run.run_id,
                tier_id=tier.tier_id,
                phase_id="verify-phase-1",
                phase_index=0,
                name="Test Phase 1",
                description="Add a simple hello_world.py file with a function that prints 'Hello World'",
                task_category="backend",
                complexity="low",
                builder_mode="tweak_light",
                status="QUEUED"
            ),
            Phase(
                run_id=run.run_id,
                tier_id=tier.tier_id,
                phase_id="verify-phase-2",
                phase_index=1,
                name="Test Phase 2",
                description="Add a README.md file explaining the hello_world.py script",
                task_category="documentation",
                complexity="low",
                builder_mode="tweak_light",
                status="QUEUED"
            )
        ]

        for phase in phases:
            session.add(phase)
            print(f"[OK] Created phase: {phase.phase_id} - {phase.description}")

        session.commit()
        print(f"\n[SUCCESS] Created test run: {run.run_id} with {len(phases)} phases")
        print("\nRun autonomous executor with:")
        print(f"python src/autopack/autonomous_executor.py --run-id {run.run_id} --max-iterations 2")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] Failed to create test run: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    create_verification_run()
