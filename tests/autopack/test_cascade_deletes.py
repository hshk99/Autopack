"""Test CASCADE delete behavior on foreign keys.

This test suite verifies that deleting a Run automatically deletes
all associated child records (phases, telemetry events, etc.) through
CASCADE constraints on foreign keys.

Implements IMP-069: Add CASCADE Delete on Foreign Keys
"""

import pytest

from src.autopack.models import (
    Run,
    Phase,
    Tier,
    TierState,
    TokenEstimationV2Event,
    TokenBudgetEscalationEvent,
    SOTRetrievalEvent,
    GovernanceRequest,
    ABTestResult,
)


@pytest.fixture
def db_session():
    """Provide a database session for testing."""
    from sqlalchemy.exc import IntegrityError, ProgrammingError
    from src.autopack.database import SessionLocal, Base, engine

    # Create tables - handle race condition when parallel workers try to create
    # PostgreSQL ENUM types simultaneously (e.g., 'runstate' enum)
    try:
        Base.metadata.create_all(bind=engine)
    except (IntegrityError, ProgrammingError) as e:
        # Ignore "duplicate key value violates unique constraint" errors for
        # PostgreSQL type creation - this happens when parallel test workers
        # race to create the same ENUM type. The type already exists, so we
        # can safely continue.
        error_msg = str(e).lower()
        if "pg_type_typname_nsp_index" in error_msg or "already exists" in error_msg:
            pass  # Type already created by another worker, safe to continue
        else:
            raise

    # Enable foreign key constraints for SQLite (required for CASCADE deletes)
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=ON"))
            conn.commit()

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class TestCascadeDeletePhases:
    """Test CASCADE delete for Phase records when parent Run is deleted."""

    def test_cascade_delete_phases_when_run_deleted(self, db_session):
        """Verify phases are deleted when parent run is deleted."""
        # Setup: Create a run with associated tier and phases
        run = Run(id="test-run-cascade-phases")
        tier = Tier(
            tier_id="T1",
            run_id=run.id,
            tier_index=0,
            name="Test Tier",
            state=TierState.PENDING,
        )

        db_session.add_all([run, tier])
        db_session.flush()  # Ensure tier.id is generated

        phase1 = Phase(
            phase_id="phase-1",
            run_id=run.id,
            tier_id=tier.id,
            phase_index=0,
            name="Phase 1",
        )
        phase2 = Phase(
            phase_id="phase-2",
            run_id=run.id,
            tier_id=tier.id,
            phase_index=1,
            name="Phase 2",
        )

        db_session.add_all([phase1, phase2])
        db_session.commit()

        # Verify phases exist
        assert db_session.query(Phase).filter_by(run_id=run.id).count() == 2

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Phases should be CASCADE deleted
        assert db_session.query(Phase).filter_by(run_id=run.id).count() == 0

    def test_cascade_delete_tiers_when_run_deleted(self, db_session):
        """Verify tiers are deleted when parent run is deleted."""
        # Setup: Create a run with associated tiers
        run = Run(id="test-run-cascade-tiers")
        tier1 = Tier(
            tier_id="T1", run_id=run.id, tier_index=0, name="Tier 1", state=TierState.PENDING
        )
        tier2 = Tier(
            tier_id="T2", run_id=run.id, tier_index=1, name="Tier 2", state=TierState.PENDING
        )

        db_session.add_all([run, tier1, tier2])
        db_session.commit()

        # Verify tiers exist
        assert db_session.query(Tier).filter_by(run_id=run.id).count() == 2

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Tiers should be CASCADE deleted
        assert db_session.query(Tier).filter_by(run_id=run.id).count() == 0


class TestCascadeDeleteTelemetry:
    """Test CASCADE delete for telemetry events when parent Run is deleted."""

    def test_cascade_delete_token_estimation_events(self, db_session):
        """Verify TokenEstimationV2Event records are deleted when run is deleted."""
        # Setup
        run = Run(id="test-run-telemetry-estimation")
        tier = Tier(
            tier_id="T1",
            run_id=run.id,
            tier_index=0,
            name="Test Tier",
            state=TierState.PENDING,
        )

        db_session.add_all([run, tier])
        db_session.flush()

        phase = Phase(
            phase_id="phase-1",
            run_id=run.id,
            tier_id=tier.id,
            phase_index=0,
            name="Test Phase",
        )

        db_session.add(phase)
        db_session.flush()

        event1 = TokenEstimationV2Event(
            run_id=run.id,
            phase_id=phase.phase_id,
            category="test",
            complexity="low",
            deliverable_count=1,
            deliverables_json="[]",
            predicted_output_tokens=100,
            actual_output_tokens=95,
            selected_budget=200,
            success=True,
            model="claude-3",
        )
        event2 = TokenEstimationV2Event(
            run_id=run.id,
            phase_id=phase.phase_id,
            category="test",
            complexity="high",
            deliverable_count=2,
            deliverables_json="[]",
            predicted_output_tokens=200,
            actual_output_tokens=180,
            selected_budget=400,
            success=True,
            model="claude-3",
        )

        db_session.add_all([event1, event2])
        db_session.commit()

        # Verify events exist
        assert db_session.query(TokenEstimationV2Event).filter_by(run_id=run.id).count() == 2

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Events should be CASCADE deleted
        assert db_session.query(TokenEstimationV2Event).filter_by(run_id=run.id).count() == 0

    def test_cascade_delete_token_budget_escalation_events(self, db_session):
        """Verify TokenBudgetEscalationEvent records are deleted when run is deleted."""
        # Setup
        run = Run(id="test-run-budget-escalation")
        tier = Tier(
            tier_id="T1",
            run_id=run.id,
            tier_index=0,
            name="Test Tier",
            state=TierState.PENDING,
        )

        db_session.add_all([run, tier])
        db_session.flush()

        phase = Phase(
            phase_id="phase-1",
            run_id=run.id,
            tier_id=tier.id,
            phase_index=0,
            name="Test Phase",
        )

        db_session.add(phase)
        db_session.flush()

        event = TokenBudgetEscalationEvent(
            run_id=run.id,
            phase_id=phase.phase_id,
            attempt_index=1,
            reason="truncation",
            escalation_factor=1.5,
            base_value=1000,
            base_source="estimation",
            retry_max_tokens=1500,
        )

        db_session.add(event)
        db_session.commit()

        # Verify event exists
        assert db_session.query(TokenBudgetEscalationEvent).filter_by(run_id=run.id).count() == 1

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Event should be CASCADE deleted
        assert db_session.query(TokenBudgetEscalationEvent).filter_by(run_id=run.id).count() == 0

    def test_cascade_delete_sot_retrieval_events(self, db_session):
        """Verify SOTRetrievalEvent records are deleted when run is deleted."""
        # Setup
        run = Run(id="test-run-sot-retrieval")
        tier = Tier(
            tier_id="T1",
            run_id=run.id,
            tier_index=0,
            name="Test Tier",
            state=TierState.PENDING,
        )

        db_session.add_all([run, tier])
        db_session.flush()

        phase = Phase(
            phase_id="phase-1",
            run_id=run.id,
            tier_id=tier.id,
            phase_index=0,
            name="Test Phase",
        )

        db_session.add(phase)
        db_session.flush()

        event = SOTRetrievalEvent(
            run_id=run.id,
            phase_id=phase.phase_id,
            include_sot=True,
            max_context_chars=10000,
            sot_budget_chars=2000,
            sot_chunks_retrieved=5,
            sot_chars_raw=1500,
            total_context_chars=8000,
            sot_chars_formatted=1400,
            budget_utilization_pct=80.0,
            sot_truncated=False,
            retrieval_enabled=True,
        )

        db_session.add(event)
        db_session.commit()

        # Verify event exists
        assert db_session.query(SOTRetrievalEvent).filter_by(run_id=run.id).count() == 1

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Event should be CASCADE deleted
        assert db_session.query(SOTRetrievalEvent).filter_by(run_id=run.id).count() == 0


class TestCascadeDeleteGovernance:
    """Test CASCADE delete for governance records when parent Run is deleted."""

    def test_cascade_delete_governance_requests(self, db_session):
        """Verify GovernanceRequest records are deleted when run is deleted."""
        # Setup
        run = Run(id="test-run-governance")

        db_session.add(run)
        db_session.flush()

        request = GovernanceRequest(
            request_id="gov-req-1",
            run_id=run.id,
            phase_id="phase-1",
            requested_paths="/src/protected",
        )

        db_session.add(request)
        db_session.commit()

        # Verify request exists
        assert db_session.query(GovernanceRequest).filter_by(run_id=run.id).count() == 1

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: Request should be CASCADE deleted
        assert db_session.query(GovernanceRequest).filter_by(run_id=run.id).count() == 0


class TestCascadeDeleteABTest:
    """Test CASCADE delete for A/B test results when runs are deleted."""

    def test_cascade_delete_ab_test_on_control_run_delete(self, db_session):
        """Verify ABTestResult is deleted when control run is deleted."""
        # Setup
        control_run = Run(id="test-run-control")
        treatment_run = Run(id="test-run-treatment")

        db_session.add_all([control_run, treatment_run])
        db_session.flush()

        ab_test = ABTestResult(
            test_id="test-1",
            control_run_id=control_run.id,
            treatment_run_id=treatment_run.id,
            control_commit_sha="abc123",
            treatment_commit_sha="def456",
            control_model_hash="model1",
            treatment_model_hash="model2",
        )

        db_session.add(ab_test)
        db_session.commit()

        # Verify test exists
        assert db_session.query(ABTestResult).filter_by(control_run_id=control_run.id).count() == 1

        # Action: Delete the control run
        db_session.delete(control_run)
        db_session.commit()

        # Verify: Test should be CASCADE deleted
        assert db_session.query(ABTestResult).filter_by(control_run_id=control_run.id).count() == 0

    def test_cascade_delete_ab_test_on_treatment_run_delete(self, db_session):
        """Verify ABTestResult is deleted when treatment run is deleted."""
        # Setup
        control_run = Run(id="test-run-control-2")
        treatment_run = Run(id="test-run-treatment-2")

        db_session.add_all([control_run, treatment_run])
        db_session.flush()

        ab_test = ABTestResult(
            test_id="test-2",
            control_run_id=control_run.id,
            treatment_run_id=treatment_run.id,
            control_commit_sha="abc123",
            treatment_commit_sha="def456",
            control_model_hash="model1",
            treatment_model_hash="model2",
        )

        db_session.add(ab_test)
        db_session.commit()

        # Verify test exists
        assert (
            db_session.query(ABTestResult).filter_by(treatment_run_id=treatment_run.id).count() == 1
        )

        # Action: Delete the treatment run
        db_session.delete(treatment_run)
        db_session.commit()

        # Verify: Test should be CASCADE deleted
        assert (
            db_session.query(ABTestResult).filter_by(treatment_run_id=treatment_run.id).count() == 0
        )


class TestCascadeDeleteComprehensive:
    """Test comprehensive CASCADE delete scenario with multiple record types."""

    def test_cascade_delete_entire_run_hierarchy(self, db_session):
        """Verify all child records are deleted when a run is deleted."""
        # Setup: Create a complex run hierarchy
        run = Run(id="test-run-comprehensive")

        # Create tiers
        tier1 = Tier(
            tier_id="T1",
            run_id=run.id,
            tier_index=0,
            name="Tier 1",
            state=TierState.PENDING,
        )
        tier2 = Tier(
            tier_id="T2",
            run_id=run.id,
            tier_index=1,
            name="Tier 2",
            state=TierState.PENDING,
        )

        db_session.add_all([run, tier1, tier2])
        db_session.flush()

        # Create phases
        phase1 = Phase(
            phase_id="phase-1",
            run_id=run.id,
            tier_id=tier1.id,
            phase_index=0,
            name="Phase 1",
        )
        phase2 = Phase(
            phase_id="phase-2",
            run_id=run.id,
            tier_id=tier2.id,
            phase_index=0,
            name="Phase 2",
        )

        db_session.add_all([phase1, phase2])
        db_session.flush()

        # Create telemetry events
        token_event = TokenEstimationV2Event(
            run_id=run.id,
            phase_id=phase1.phase_id,
            category="test",
            complexity="low",
            deliverable_count=1,
            deliverables_json="[]",
            predicted_output_tokens=100,
            actual_output_tokens=95,
            selected_budget=200,
            success=True,
            model="claude-3",
        )

        budget_event = TokenBudgetEscalationEvent(
            run_id=run.id,
            phase_id=phase2.phase_id,
            attempt_index=1,
            reason="truncation",
            escalation_factor=1.5,
            base_value=1000,
            base_source="estimation",
            retry_max_tokens=1500,
        )

        # Create governance request
        gov_request = GovernanceRequest(
            request_id="gov-req-comprehensive",
            run_id=run.id,
            phase_id="phase-1",
            requested_paths="/src",
        )

        db_session.add_all(
            [
                token_event,
                budget_event,
                gov_request,
            ]
        )
        db_session.commit()

        # Verify all records exist
        assert db_session.query(Tier).filter_by(run_id=run.id).count() == 2
        assert db_session.query(Phase).filter_by(run_id=run.id).count() == 2
        assert db_session.query(TokenEstimationV2Event).filter_by(run_id=run.id).count() == 1
        assert db_session.query(TokenBudgetEscalationEvent).filter_by(run_id=run.id).count() == 1
        assert db_session.query(GovernanceRequest).filter_by(run_id=run.id).count() == 1

        # Action: Delete the run
        db_session.delete(run)
        db_session.commit()

        # Verify: All child records should be CASCADE deleted
        assert db_session.query(Tier).filter_by(run_id=run.id).count() == 0
        assert db_session.query(Phase).filter_by(run_id=run.id).count() == 0
        assert db_session.query(TokenEstimationV2Event).filter_by(run_id=run.id).count() == 0
        assert db_session.query(TokenBudgetEscalationEvent).filter_by(run_id=run.id).count() == 0
        assert db_session.query(GovernanceRequest).filter_by(run_id=run.id).count() == 0
