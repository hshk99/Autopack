"""Unit tests for database models"""


from autopack.models import Phase, PhaseState, Run, RunState, Tier, TierState


def test_run_creation(db_session):
    """Test creating a Run record"""
    run = Run(
        id="test-run-001",
        state=RunState.RUN_CREATED,
        safety_profile="normal",
        run_scope="multi_tier",
    )
    db_session.add(run)
    db_session.commit()

    retrieved = db_session.query(Run).filter(Run.id == "test-run-001").first()
    assert retrieved is not None
    assert retrieved.state == RunState.RUN_CREATED
    assert retrieved.safety_profile == "normal"
    assert retrieved.tokens_used == 0
    assert retrieved.minor_issues_count == 0


def test_tier_creation(db_session):
    """Test creating a Tier record"""
    run = Run(id="test-run-002", state=RunState.RUN_CREATED)
    db_session.add(run)
    db_session.commit()

    tier = Tier(
        tier_id="T1",
        run_id=run.id,
        tier_index=0,
        name="Foundation",
        description="Core setup",
        state=TierState.PENDING,
    )
    db_session.add(tier)
    db_session.commit()

    retrieved = db_session.query(Tier).filter(Tier.tier_id == "T1").first()
    assert retrieved is not None
    assert retrieved.name == "Foundation"
    assert retrieved.state == TierState.PENDING
    assert retrieved.cleanliness == "clean"


def test_phase_creation(db_session):
    """Test creating a Phase record"""
    run = Run(id="test-run-003", state=RunState.RUN_CREATED)
    db_session.add(run)
    db_session.flush()

    tier = Tier(tier_id="T1", run_id=run.id, tier_index=0, name="Foundation")
    db_session.add(tier)
    db_session.flush()

    phase = Phase(
        phase_id="F1.1",
        run_id=run.id,
        tier_id=tier.id,
        phase_index=0,
        name="Setup DB",
        task_category="schema_change",
        complexity="medium",
        state=PhaseState.QUEUED,
    )
    db_session.add(phase)
    db_session.commit()

    retrieved = db_session.query(Phase).filter(Phase.phase_id == "F1.1").first()
    assert retrieved is not None
    assert retrieved.name == "Setup DB"
    assert retrieved.task_category == "schema_change"
    assert retrieved.complexity == "medium"
    assert retrieved.state == PhaseState.QUEUED
    assert retrieved.builder_attempts == 0


def test_run_tier_relationship(db_session):
    """Test relationship between Run and Tiers"""
    run = Run(id="test-run-004", state=RunState.RUN_CREATED)
    db_session.add(run)
    db_session.flush()

    tier1 = Tier(tier_id="T1", run_id=run.id, tier_index=0, name="Tier 1")
    tier2 = Tier(tier_id="T2", run_id=run.id, tier_index=1, name="Tier 2")
    db_session.add_all([tier1, tier2])
    db_session.commit()

    retrieved = db_session.query(Run).filter(Run.id == "test-run-004").first()
    assert len(retrieved.tiers) == 2
    assert retrieved.tiers[0].tier_id == "T1"
    assert retrieved.tiers[1].tier_id == "T2"


def test_tier_phase_relationship(db_session):
    """Test relationship between Tier and Phases"""
    run = Run(id="test-run-005", state=RunState.RUN_CREATED)
    db_session.add(run)
    db_session.flush()

    tier = Tier(tier_id="T1", run_id=run.id, tier_index=0, name="Tier 1")
    db_session.add(tier)
    db_session.flush()

    phase1 = Phase(phase_id="F1.1", run_id=run.id, tier_id=tier.id, phase_index=0, name="Phase 1")
    phase2 = Phase(phase_id="F1.2", run_id=run.id, tier_id=tier.id, phase_index=1, name="Phase 2")
    db_session.add_all([phase1, phase2])
    db_session.commit()

    retrieved = db_session.query(Tier).filter(Tier.tier_id == "T1").first()
    assert len(retrieved.phases) == 2
    assert retrieved.phases[0].phase_id == "F1.1"
    assert retrieved.phases[1].phase_id == "F1.2"


def test_cascade_delete(db_session):
    """Test that deleting a run cascades to tiers and phases"""
    run = Run(id="test-run-006", state=RunState.RUN_CREATED)
    db_session.add(run)
    db_session.flush()

    tier = Tier(tier_id="T1", run_id=run.id, tier_index=0, name="Tier 1")
    db_session.add(tier)
    db_session.flush()

    phase = Phase(phase_id="F1.1", run_id=run.id, tier_id=tier.id, phase_index=0, name="Phase 1")
    db_session.add(phase)
    db_session.commit()

    # Delete the run
    db_session.delete(run)
    db_session.commit()

    # Verify cascade
    assert db_session.query(Tier).filter(Tier.tier_id == "T1").first() is None
    assert db_session.query(Phase).filter(Phase.phase_id == "F1.1").first() is None
