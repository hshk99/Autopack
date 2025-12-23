"""
Seed Lovable Integration Phase 2 (Quality & UX) in the database.
"""

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "lovable-p2-quality-ux"

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
            token_cap=400000,
            max_phases=8,
            max_duration_minutes=360,
            goal_anchor="Lovable Integration Phase 2: Quality & UX"
        )
        session.add(run)
        session.flush()
        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="lovable-p2-tier",
            run_id=RUN_ID,
            name="Phase 2: Quality & UX",
            tier_index=0,
            description="Quality and user experience patterns for Lovable integration"
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id

        # Define phases - based on phase documentation
        phases = [
            {
                "id": "lovable-p2.1-package-detection",
                "name": "Automatic Package Detection",
                "desc": "70% reduction in import errors by detecting missing packages proactively",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/diagnostics/package_detector.py",
                    "tests/autopack/diagnostics/test_package_detector.py"
                ]
            },
            {
                "id": "lovable-p2.2-hmr-error-detection",
                "name": "HMR Error Detection",
                "desc": "Detect and respond to Hot Module Replacement errors from browser telemetry",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/lovable/hmr_error_detector.py",
                    "tests/autopack/lovable/test_hmr_error_detector.py"
                ]
            },
            {
                "id": "lovable-p2.3-missing-import-autofix",
                "name": "Missing Import Auto-fix",
                "desc": "Automatically fix missing import statements based on usage patterns",
                "category": "implementation",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/lovable/import_autofix.py",
                    "tests/autopack/lovable/test_import_autofix.py"
                ]
            },
            {
                "id": "lovable-p2.4-conversation-state",
                "name": "Conversation State Tracking",
                "desc": "Track conversation context across multiple builder invocations",
                "category": "refactoring",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/memory/conversation_state.py",
                    "tests/autopack/memory/test_conversation_state.py"
                ]
            },
            {
                "id": "lovable-p2.5-fallback-chain",
                "name": "Error Recovery Fallback Chain",
                "desc": "Multi-tier fallback strategy for error recovery",
                "category": "implementation",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/error_handling/fallback_chain.py",
                    "tests/autopack/error_handling/test_fallback_chain.py"
                ]
            }
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
                complexity=pd["complexity"]
            )
            session.add(phase)
            print(f"[OK] Phase {idx}: {pd['id']} ({len(pd['deliverables'])} deliverables)")

        session.commit()
        print(f"\n✅ Lovable Phase 2 seeded! Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
