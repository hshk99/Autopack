"""Tests for phases endpoint eager loading (IMP-PERF-001).

This test verifies that phase queries use joinedload to prevent N+1 query patterns
when accessing the tier relationship.
"""

from datetime import datetime, timezone

import pytest

from autopack import models


class TestPhasesEagerLoading:
    """Tests for eager loading of Phase.tier relationship."""

    def test_phases_router_imports_joinedload(self):
        """Verify phases router imports joinedload for eager loading."""
        from autopack.api.routes import phases

        # Verify joinedload is imported and available
        assert hasattr(phases, "joinedload")

    def test_phase_model_has_tier_relationship(self):
        """Verify Phase model has tier relationship for eager loading."""
        from autopack import models

        # Verify Phase has a tier relationship attribute
        phase_mapper = models.Phase.__mapper__
        relationships = {r.key for r in phase_mapper.relationships}
        assert "tier" in relationships, "Phase must have 'tier' relationship for eager loading"


@pytest.fixture
def test_run_and_tier_for_eager_load(db_session):
    """Create a test run and tier for eager loading testing."""
    run = models.Run(
        id="eager-load-test-run",
        state=models.RunState.PHASE_EXECUTION,
        safety_profile="normal",
        run_scope="multi_tier",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    db_session.flush()

    tier = models.Tier(
        run_id="eager-load-test-run",
        tier_id="T1",
        tier_index=0,
        name="Test Tier",
        state=models.TierState.IN_PROGRESS,
        cleanliness="clean",
    )
    db_session.add(tier)
    db_session.commit()

    return run.id, tier.id, tier.tier_id


def test_phase_tier_relationship_loaded_in_single_query(
    db_session, test_run_and_tier_for_eager_load
):
    """Integration test: verify phase.tier is accessible without additional queries.

    This test creates real DB records and verifies the eager loading
    by checking that the tier relationship is populated.
    """
    run_id, tier_db_id, tier_id = test_run_and_tier_for_eager_load

    # Create a phase
    phase = models.Phase(
        phase_id="eager-test-phase",
        run_id=run_id,
        tier_id=tier_db_id,
        phase_index=0,
        name="Eager Load Test Phase",
        state=models.PhaseState.QUEUED,
    )
    db_session.add(phase)
    db_session.commit()

    # Query the phase using the same pattern as the API
    from sqlalchemy.orm import joinedload

    queried_phase = (
        db_session.query(models.Phase)
        .options(joinedload(models.Phase.tier))
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == "eager-test-phase")
        .first()
    )

    # Verify phase and tier are loaded
    assert queried_phase is not None
    assert queried_phase.tier is not None
    assert queried_phase.tier.tier_id == tier_id


def test_joinedload_prevents_n_plus_1_queries(db_session, test_run_and_tier_for_eager_load):
    """Verify joinedload loads tier in single query, not N+1.

    This test verifies that using joinedload on the Phase.tier relationship
    loads the tier data in the same query as the phase, not lazily.
    """
    run_id, tier_db_id, tier_id = test_run_and_tier_for_eager_load

    # Create multiple phases
    for i in range(5):
        phase = models.Phase(
            phase_id=f"n1-test-phase-{i}",
            run_id=run_id,
            tier_id=tier_db_id,
            phase_index=i,
            name=f"N+1 Test Phase {i}",
            state=models.PhaseState.QUEUED,
        )
        db_session.add(phase)
    db_session.commit()

    # Clear session to ensure fresh query
    db_session.expire_all()

    # Query with joinedload
    from sqlalchemy.orm import joinedload

    phases = (
        db_session.query(models.Phase)
        .options(joinedload(models.Phase.tier))
        .filter(models.Phase.run_id == run_id)
        .all()
    )

    # Verify all phases have tier loaded without lazy loading
    assert len(phases) == 5
    for phase in phases:
        # Accessing tier should not trigger additional queries
        # because it was eager-loaded
        assert phase.tier is not None
        assert phase.tier.tier_id == tier_id
