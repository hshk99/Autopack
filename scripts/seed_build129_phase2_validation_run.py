"""
Seed BUILD-129 Phase 2 Validation Run.

Validates updated TokenEstimator coefficients (8x increase).
"""

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "build129-p2-validation"


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
            token_cap=300000,
            max_phases=6,
            max_duration_minutes=180,
            goal_anchor="BUILD-129 Phase 2: Validate Updated Token Estimator Coefficients",
        )
        session.add(run)
        session.flush()
        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="build129-p2-tier",
            run_id=RUN_ID,
            name="Phase 2 Validation",
            tier_index=0,
            description="Validate updated TokenEstimator coefficients",
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id

        # Define validation phases with varied characteristics
        phases = [
            {
                "id": "build129-p2-val-1",
                "name": "2-File Implementation (Medium)",
                "desc": "Test 2-deliverable implementation phase - baseline case",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/validation/test_phase1.py",
                    "tests/validation/test_test_phase1.py",
                ],
            },
            {
                "id": "build129-p2-val-2",
                "name": "3-File Refactoring (Low)",
                "desc": "Test 3-deliverable refactoring with deliverables scaling (0.7x)",
                "category": "refactoring",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/validation/refactor_module.py",
                    "src/autopack/validation/helper.py",
                    "tests/validation/test_refactor.py",
                ],
            },
            {
                "id": "build129-p2-val-3",
                "name": "2-File Configuration (Low)",
                "desc": "Test configuration category with low complexity",
                "category": "configuration",
                "complexity": "low",
                "deliverables": [".build129_test_config.yaml", "validation_settings.json"],
            },
            {
                "id": "build129-p2-val-4",
                "name": "4-File Testing Suite (Medium)",
                "desc": "Test 4-deliverable testing phase with deliverables scaling (0.7x)",
                "category": "testing",
                "complexity": "medium",
                "deliverables": [
                    "tests/validation/test_suite_a.py",
                    "tests/validation/test_suite_b.py",
                    "tests/validation/test_suite_c.py",
                    "tests/validation/fixtures.py",
                ],
            },
            {
                "id": "build129-p2-val-5",
                "name": "2-File Implementation (High)",
                "desc": "Test high complexity multiplier (1.3x)",
                "category": "implementation",
                "complexity": "high",
                "deliverables": [
                    "src/autopack/validation/complex_algorithm.py",
                    "tests/validation/test_complex_algorithm.py",
                ],
            },
        ]

        for idx, pd in enumerate(phases, 1):
            scope = {"deliverables": pd["deliverables"], "paths": [], "read_only_context": []}
            phase = Phase(
                phase_id=pd["id"],
                run_id=RUN_ID,
                tier_id=tier_db_id,
                phase_index=idx,
                name=pd["name"],
                description=pd["desc"],
                scope=scope,
                state=PhaseState.QUEUED,
                task_category=pd["category"],
                complexity=pd["complexity"],
            )
            session.add(phase)
            print(
                f"[OK] Phase {idx}: {pd['id']} ({len(pd['deliverables'])} deliverables, {pd['category']}/{pd['complexity']})"
            )

        session.commit()
        print("\n✅ BUILD-129 Phase 2 validation run seeded!")
        print(
            f'Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor --run-id {RUN_ID}'
        )
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
