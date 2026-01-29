"""
Smoke test for create_telemetry_collection_run.py

Validates that the script creates a run with correct ORM schema.
"""

import os
import sys
from pathlib import Path

# Set DATABASE_URL before any imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest

from autopack.database import SessionLocal, engine
from autopack.models import (Base, Phase, PhaseState, Run, RunState, Tier,
                             TierState)


@pytest.fixture(scope="function")
def test_db():
    """Create a temporary test database."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_telemetry_run_schema_matches(test_db):
    """
    Smoke test: Verify telemetry run can be created with current ORM schema.

    This mimics what create_telemetry_collection_run.py does.
    """
    run_id = "test-telemetry-run"
    tier_id = "T1"

    # Create run (mimics script)
    run = Run(
        id=run_id,
        state=RunState.RUN_CREATED,
        token_cap=500000,
        max_phases=15,
        max_duration_minutes=120,
    )
    test_db.add(run)
    test_db.flush()

    # Create tier (required for phases)
    tier = Tier(
        tier_id=tier_id,
        run_id=run_id,
        tier_index=0,
        name="Test Telemetry Tier",
        description="Test tier for telemetry collection",
        state=TierState.PENDING,
        token_cap=500000,
        ci_run_cap=20,
    )
    test_db.add(tier)
    test_db.flush()

    # Create phase (mimics script)
    phase = Phase(
        run_id=run_id,
        tier_id=tier.id,
        phase_id="test-phase-1",
        phase_index=0,
        name="Test Phase",
        description="Test phase for telemetry",
        state=PhaseState.QUEUED,
        scope={
            "paths": ["examples/telemetry_utils/"],
            "read_only_context": [],
            "deliverables": ["examples/telemetry_utils/test.py"],
        },
        complexity="low",
        task_category="implementation",
        max_builder_attempts=3,
        max_auditor_attempts=2,
        incident_token_cap=50000,
    )
    test_db.add(phase)
    test_db.commit()

    # Verify everything was created correctly
    created_run = test_db.query(Run).filter(Run.id == run_id).first()
    assert created_run is not None
    assert created_run.state == RunState.RUN_CREATED
    assert created_run.token_cap == 500000

    created_tier = test_db.query(Tier).filter(Tier.run_id == run_id).first()
    assert created_tier is not None
    assert created_tier.tier_id == tier_id
    assert created_tier.state == TierState.PENDING

    created_phase = test_db.query(Phase).filter(Phase.run_id == run_id).first()
    assert created_phase is not None
    assert created_phase.phase_id == "test-phase-1"
    assert created_phase.state == PhaseState.QUEUED
    assert created_phase.complexity == "low"
    assert created_phase.task_category == "implementation"
    assert created_phase.scope["deliverables"] == ["examples/telemetry_utils/test.py"]

    # Verify relationship integrity
    assert created_phase.tier_id == created_tier.id
    assert created_tier.run_id == created_run.id


def test_multiple_phases_same_run(test_db):
    """Verify multiple phases can be created for the same run."""
    run_id = "test-multi-phase-run"

    run = Run(id=run_id, state=RunState.RUN_CREATED)
    test_db.add(run)
    test_db.flush()

    tier = Tier(tier_id="T1", run_id=run_id, tier_index=0, name="Test Tier", description="Test")
    test_db.add(tier)
    test_db.flush()

    # Create 3 phases
    for i in range(3):
        phase = Phase(
            run_id=run_id,
            tier_id=tier.id,
            phase_id=f"phase-{i}",
            phase_index=i,
            name=f"Phase {i}",
            state=PhaseState.QUEUED,
            complexity="low",
            task_category="implementation",
        )
        test_db.add(phase)

    test_db.commit()

    # Verify all phases were created
    phases = test_db.query(Phase).filter(Phase.run_id == run_id).all()
    assert len(phases) == 3
    assert {p.phase_id for p in phases} == {"phase-0", "phase-1", "phase-2"}
