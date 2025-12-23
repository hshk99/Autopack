"""
Create a simple single-phase run to test telemetry collection.
"""
from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "telemetry-test-single"

def main():
    session = SessionLocal()
    try:
        # Delete existing
        existing_run = session.query(Run).filter(Run.id == RUN_ID).first()
        if existing_run:
            session.query(Phase).filter(Phase.run_id == RUN_ID).delete()
            session.query(Tier).filter(Tier.run_id == RUN_ID).delete()
            session.delete(existing_run)
            session.commit()

        # Create Run
        run = Run(
            id=RUN_ID,
            state=RunState.QUEUED,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=100000,
            max_phases=1,
            max_duration_minutes=60,
            goal_anchor="Simple telemetry collection test"
        )
        session.add(run)
        session.flush()

        # Create tier
        tier = Tier(
            tier_id="telemetry-test-tier",
            run_id=RUN_ID,
            name="Test",
            tier_index=0,
            description="Simple telemetry test"
        )
        session.add(tier)
        session.flush()

        # Create a simple documentation phase (safe, non-protected path)
        scope = {
            "deliverables": [
                "docs/examples/SIMPLE_EXAMPLE.md",
                "docs/examples/ADVANCED_EXAMPLE.md",
                "docs/examples/FAQ.md"
            ],
            "paths": [],
            "read_only_context": []
        }

        phase = Phase(
            phase_id="telemetry-test-phase-1",
            run_id=RUN_ID,
            tier_id=tier.id,
            phase_index=1,
            name="Create Example Documentation",
            description="Create simple example documentation files",
            scope=scope,
            state=PhaseState.QUEUED,
            task_category="documentation",
            complexity="low"
        )
        session.add(phase)
        session.commit()

        print(f"✅ Simple telemetry test run created!")
        print(f"Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID} 2>&1 | tee telemetry_test.log")
        print(f"Then: grep 'TokenEstimationV2' telemetry_test.log")

    finally:
        session.close()

if __name__ == "__main__":
    main()
