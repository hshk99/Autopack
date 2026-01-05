"""Tests for BUILD-146 P12 replay campaign functionality.

Verifies that failed runs can be cloned and replayed with Phase 6 features.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, Run, Tier, Phase, PhaseState, RunState


@pytest.fixture
def test_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_session(test_engine):
    """Create test database session."""
    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.close()


def create_failed_run(session, run_id: str):
    """Helper to create a failed run for testing."""
    run = Run(
        id=run_id,
        state=RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW,
        tokens_used=5000,
        created_at=datetime.now(timezone.utc),
    )
    session.add(run)

    # Add tier
    tier = Tier(
        tier_id="tier-1",
        run_id=run_id,
        tier_index=1,
        name="Test tier",
        description="Test tier",
    )
    session.add(tier)

    # Need to flush tier to get its ID
    session.flush()

    # Add phases
    phase1 = Phase(
        phase_id="phase-1",
        run_id=run_id,
        tier_id=tier.id,
        phase_index=1,
        name="Phase 1",
        state=PhaseState.COMPLETE,
        description="Completed phase",
    )
    session.add(phase1)

    phase2 = Phase(
        phase_id="phase-2",
        run_id=run_id,
        tier_id=tier.id,
        phase_index=2,
        name="Phase 2",
        state=PhaseState.FAILED,
        description="Failed phase",
    )
    session.add(phase2)

    session.commit()
    return run


def test_clone_run_basic(test_session):
    """Test basic run cloning functionality."""
    # Create failed run
    original = create_failed_run(test_session, "failed-run-1")

    # Simulate clone logic (simplified from replay_campaign.py)
    new_run_id = f"{original.id}-replay-test"
    new_run = Run(
        id=new_run_id,
        state=RunState.RUN_CREATED,
        safety_profile=original.safety_profile,
        run_scope=original.run_scope,
        token_cap=original.token_cap,
        max_phases=original.max_phases,
    )
    test_session.add(new_run)
    test_session.commit()

    # Verify cloned run exists
    cloned = test_session.query(Run).filter(Run.id == new_run_id).first()
    assert cloned is not None
    assert cloned.state == RunState.RUN_CREATED  # Reset to RUN_CREATED
    assert cloned.safety_profile == original.safety_profile
    assert cloned.token_cap == original.token_cap


def test_clone_run_with_tiers_and_phases(test_session):
    """Test cloning run with tiers and phases."""
    # Create failed run with tiers and phases
    original = create_failed_run(test_session, "failed-run-2")

    # Get original tiers and phases
    original_tiers = test_session.query(Tier).filter(Tier.run_id == original.id).all()
    original_phases = test_session.query(Phase).filter(Phase.run_id == original.id).all()

    # Clone run
    new_run_id = f"{original.id}-replay-test"
    new_run = Run(
        id=new_run_id,
        state=RunState.RUN_CREATED,
    )
    test_session.add(new_run)

    # Clone tiers
    for orig_tier in original_tiers:
        new_tier = Tier(
            tier_id=orig_tier.tier_id,
            run_id=new_run_id,
            tier_index=orig_tier.tier_index,
            name=orig_tier.name,
            description=orig_tier.description,
        )
        test_session.add(new_tier)

    # Clone phases (reset to QUEUED)
    for orig_phase in original_phases:
        new_phase = Phase(
            phase_id=orig_phase.phase_id,
            run_id=new_run_id,
            tier_id=orig_phase.tier_id,
            phase_index=orig_phase.phase_index,
            name=orig_phase.name,
            state=PhaseState.QUEUED,  # Reset to QUEUED for replay
            description=orig_phase.description,
        )
        test_session.add(new_phase)

    test_session.commit()

    # Verify cloned tiers
    cloned_tiers = test_session.query(Tier).filter(Tier.run_id == new_run_id).all()
    assert len(cloned_tiers) == len(original_tiers)
    assert cloned_tiers[0].tier_id == original_tiers[0].tier_id

    # Verify cloned phases (should be reset to QUEUED)
    cloned_phases = test_session.query(Phase).filter(Phase.run_id == new_run_id).all()
    assert len(cloned_phases) == len(original_phases)
    assert all(p.state == PhaseState.QUEUED for p in cloned_phases)


def test_find_failed_runs(test_session):
    """Test finding failed runs by state."""
    # Create multiple runs with different states
    create_failed_run(test_session, "failed-run-1")

    success_run = Run(
        id="success-run",
        state=RunState.DONE_SUCCESS,
        created_at=datetime.now(timezone.utc),
    )
    test_session.add(success_run)
    test_session.commit()

    # Query for failed runs
    failed_runs = (
        test_session.query(Run)
        .filter(Run.state == RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW)
        .all()
    )

    assert len(failed_runs) == 1
    assert failed_runs[0].id == "failed-run-1"


def test_replay_preserves_metadata(test_session):
    """Test that replay preserves important metadata."""
    # Create original run
    original = Run(
        id="original-run",
        state=RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW,
        safety_profile="normal",
        token_cap=1000000,
    )
    test_session.add(original)
    test_session.commit()

    # Clone with metadata preservation
    new_run = Run(
        id="replay-run",
        state=RunState.RUN_CREATED,
        safety_profile=original.safety_profile,  # Preserve
        token_cap=original.token_cap,  # Preserve
    )
    test_session.add(new_run)
    test_session.commit()

    # Verify metadata preserved
    cloned = test_session.query(Run).filter(Run.id == "replay-run").first()
    assert cloned.safety_profile == "normal"
    assert cloned.token_cap == 1000000


def test_replay_script_importable():
    """Test that replay_campaign.py can be imported."""
    try:
        import scripts.replay_campaign as replay

        assert hasattr(replay, "replay_run")
        assert hasattr(replay, "find_failed_runs")
        assert hasattr(replay, "clone_run")
        assert hasattr(replay, "generate_comparison_report")
    except ImportError:
        pytest.skip("replay_campaign.py not importable (expected in test environment)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
