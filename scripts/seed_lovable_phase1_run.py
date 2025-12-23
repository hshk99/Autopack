"""
Seed Lovable Integration Phase 1 (Core Precision) in the database.
"""

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "lovable-p1-core-precision"

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
            goal_anchor="Lovable Integration Phase 1: Core Precision"
        )
        session.add(run)
        session.flush()
        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="lovable-p1-tier",
            run_id=RUN_ID,
            name="Phase 1: Core Precision",
            tier_index=0,
            description="Core precision patterns for Lovable integration"
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id

        # Define phases - based on phase documentation
        phases = [
            {
                "id": "lovable-p1.1-agentic-file-search",
                "name": "Agentic File Search",
                "desc": "Semantic file search with confidence scoring for 95% hallucination reduction",
                "category": "implementation",
                "complexity": "high",
                "deliverables": [
                    "src/autopack/file_manifest/agentic_search.py",
                    "tests/autopack/file_manifest/test_agentic_search.py"
                ]
            },
            {
                "id": "lovable-p1.2-intelligent-file-selection",
                "name": "Intelligent File Selection",
                "desc": "60-80% token reduction by selecting only essential files for LLM context",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/file_manifest/intelligent_selector.py",
                    "tests/autopack/file_manifest/test_intelligent_selector.py"
                ]
            },
            {
                "id": "lovable-p1.3-build-validation",
                "name": "Build Validation Pipeline",
                "desc": "Validate patches before application for 95% patch success rate",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/validation/build_validator.py",
                    "tests/autopack/validation/test_build_validator.py"
                ]
            },
            {
                "id": "lovable-p1.4-dynamic-retry-delays",
                "name": "Dynamic Retry Delays",
                "desc": "Error-aware backoff for API rate limits and transient failures",
                "category": "implementation",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/error_handling/dynamic_retry.py",
                    "tests/autopack/error_handling/test_dynamic_retry.py"
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
        print(f"\n✅ Lovable Phase 1 seeded! Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {RUN_ID}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
