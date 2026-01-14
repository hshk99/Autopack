"""
Seed Lovable Integration Phase 0 (Foundation) in the database.
"""

from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

RUN_ID = "lovable-p0-foundation"


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
            max_phases=5,
            max_duration_minutes=240,
            goal_anchor="Lovable Integration Phase 0: Foundation & Governance",
        )
        session.add(run)
        session.flush()
        print(f"[OK] Created run: {RUN_ID}")

        # Create tier
        tier = Tier(
            tier_id="lovable-p0-tier",
            run_id=RUN_ID,
            name="Phase 0: Foundation",
            tier_index=0,
            description="Foundation infrastructure for Lovable integration",
        )
        session.add(tier)
        session.flush()
        tier_db_id = tier.id

        # Define phases
        phases = [
            {
                "id": "lovable-p0.1-protected-path",
                "name": "Protected-Path Strategy",
                "desc": "Implement governance model for src/autopack/ self-modification",
                "category": "refactoring",
                "complexity": "low",
                "deliverables": [
                    "src/autopack/lovable/__init__.py",
                    "src/autopack/governed_apply.py",
                    ".autonomous_runs/lovable-integration-v1/GOVERNANCE.md",
                    "tests/test_lovable_governance.py",
                ],
            },
            {
                "id": "lovable-p0.2-semantic-embeddings",
                "name": "Semantic Embedding Backend",
                "desc": "Add sentence-transformers for semantic file search",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/memory/embeddings.py",
                    "requirements-lovable.txt",
                    "tests/test_semantic_embeddings.py",
                ],
            },
            {
                "id": "lovable-p0.3-browser-telemetry",
                "name": "Browser Telemetry Ingestion",
                "desc": "Implement browser error/HMR telemetry ingestion for Phase 2",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/lovable/browser_telemetry.py",
                    "src/autopack/main.py",
                    "scripts/ingest_browser_telemetry.py",
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
            print(f"[OK] Phase {idx}: {pd['id']} ({len(pd['deliverables'])} deliverables)")

        session.commit()
        print(
            f'\n✅ Lovable Phase 0 seeded! Run: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor --run-id {RUN_ID}'
        )
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
