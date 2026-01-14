#!/usr/bin/env python3
"""
Create a minimal test run directly in database to verify API works.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState


def create_test_run():
    """Create a simple test run."""

    run_id = "api-test-minimal"

    session = SessionLocal()
    try:
        # Check if run already exists
        existing = session.query(Run).filter(Run.id == run_id).first()
        if existing:
            print(f"✅ Run already exists: {run_id}")
            return 0

        # Create run
        run = Run(
            id=run_id, state=RunState.RUN_CREATED, safety_profile="normal", run_scope="single_tier"
        )
        session.add(run)
        session.flush()

        # Create a tier
        tier = Tier(
            tier_id="test-tier",
            run_id=run_id,
            tier_index=0,
            name="Test Tier",
            description="Simple test tier",
            state=TierState.PENDING,
        )
        session.add(tier)
        session.flush()

        # Create a phase
        phase = Phase(
            phase_id="test-phase",
            run_id=run_id,
            tier_id=tier.id,
            phase_index=0,
            name="Test Phase",
            description="Simple test phase to verify API works",
            state=PhaseState.QUEUED,
            task_category="test",
            complexity="low",
        )
        session.add(phase)

        session.commit()
        print(f"✅ Created test run: {run_id}")
        print(f"   Tier: {tier.tier_id}")
        print(f"   Phase: {phase.phase_id}")
        print("\n🧪 Test the API:")
        print(f"   curl http://localhost:8000/runs/{run_id}")
        return 0

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(create_test_run())
