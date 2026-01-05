"""Tests for BUILD-146 P12 A/B test results persistence.

Verifies that A/B test results are stored correctly with strict validity checks.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, Run, Phase, PhaseState, RunState, ABTestResult


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


def create_test_run(session, run_id: str, commit_sha: str, model_hash: str, tokens: int = 1000):
    """Helper to create a test run.

    Note: commit_sha and model_hash are stored in ABTestResult, not Run model.
    """
    run = Run(
        id=run_id,
        state=RunState.DONE_SUCCESS,
        tokens_used=tokens,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    return run


def create_test_phase(session, run_id: str, phase_id: str, state: PhaseState, phase_index: int = 1):
    """Helper to create a test phase."""
    # Get tier to use its integer ID
    from autopack.models import Tier

    tier = session.query(Tier).filter(Tier.run_id == run_id).first()

    phase = Phase(
        phase_id=phase_id,
        run_id=run_id,
        state=state,
        tier_id=tier.id if tier else 1,
        phase_index=phase_index,
        name=f"Test Phase {phase_id}",
    )
    session.add(phase)
    session.flush()
    return phase


def test_ab_test_result_creation(test_session):
    """Test creating an A/B test result."""
    # Create control and treatment runs
    control = create_test_run(test_session, "control-run", "abc123", "hash1", tokens=5000)
    treatment = create_test_run(test_session, "treatment-run", "abc123", "hash1", tokens=4500)

    # Create A/B test result (commit SHA and model hash stored here, not in Run)
    result = ABTestResult(
        test_id="test-1",
        control_run_id=control.id,
        treatment_run_id=treatment.id,
        control_commit_sha="abc123",  # Stored in ABTestResult
        treatment_commit_sha="abc123",
        control_model_hash="hash1",  # Stored in ABTestResult
        treatment_model_hash="hash1",
        is_valid=True,
        validity_errors=None,
        token_delta=-500,  # Treatment saved 500 tokens
        control_total_tokens=5000,
        treatment_total_tokens=4500,
    )

    test_session.add(result)
    test_session.commit()

    # Verify persisted
    retrieved = test_session.query(ABTestResult).filter(ABTestResult.test_id == "test-1").first()
    assert retrieved is not None
    assert retrieved.control_run_id == "control-run"
    assert retrieved.treatment_run_id == "treatment-run"
    assert retrieved.is_valid is True
    assert retrieved.token_delta == -500


def test_ab_test_result_invalid_comparison(test_session):
    """Test that mismatched commit SHAs are marked as invalid."""
    # Create runs (commit SHAs stored in ABTestResult)
    control = create_test_run(test_session, "control-run", "abc123", "hash1", tokens=5000)
    treatment = create_test_run(test_session, "treatment-run", "def456", "hash1", tokens=4500)

    # Create A/B test result (marked as invalid due to SHA mismatch)
    result = ABTestResult(
        test_id="test-invalid",
        control_run_id=control.id,
        treatment_run_id=treatment.id,
        control_commit_sha="abc123",  # Different SHAs
        treatment_commit_sha="def456",
        control_model_hash="hash1",
        treatment_model_hash="hash1",
        is_valid=False,  # INVALID because commit SHAs don't match
        validity_errors=["ERROR: Commit SHA mismatch - control=abc123, treatment=def456"],
        token_delta=-500,
        control_total_tokens=5000,
        treatment_total_tokens=4500,
    )

    test_session.add(result)
    test_session.commit()

    # Verify persisted as invalid
    retrieved = (
        test_session.query(ABTestResult).filter(ABTestResult.test_id == "test-invalid").first()
    )
    assert retrieved is not None
    assert retrieved.is_valid is False
    assert len(retrieved.validity_errors) > 0
    assert "Commit SHA mismatch" in retrieved.validity_errors[0]


def test_ab_test_result_model_hash_mismatch(test_session):
    """Test that mismatched model hashes are marked as invalid."""
    # Create runs
    control = create_test_run(test_session, "control-run", "abc123", "hash1", tokens=5000)
    treatment = create_test_run(test_session, "treatment-run", "abc123", "hash2", tokens=4500)

    # Create A/B test result (marked as invalid due to hash mismatch)
    result = ABTestResult(
        test_id="test-model-mismatch",
        control_run_id=control.id,
        treatment_run_id=treatment.id,
        control_commit_sha="abc123",
        treatment_commit_sha="abc123",
        control_model_hash="hash1",  # Different hashes
        treatment_model_hash="hash2",
        is_valid=False,  # INVALID because model hashes don't match
        validity_errors=["ERROR: Model hash mismatch - control=hash1, treatment=hash2"],
        token_delta=-500,
        control_total_tokens=5000,
        treatment_total_tokens=4500,
    )

    test_session.add(result)
    test_session.commit()

    # Verify persisted as invalid
    retrieved = (
        test_session.query(ABTestResult)
        .filter(ABTestResult.test_id == "test-model-mismatch")
        .first()
    )
    assert retrieved is not None
    assert retrieved.is_valid is False
    assert "Model hash mismatch" in retrieved.validity_errors[0]


def test_ab_test_result_with_phase_metrics(test_session):
    """Test A/B result with phase-level metrics."""
    from autopack.models import Tier

    # Create control and treatment runs
    control = create_test_run(test_session, "control-run", "abc123", "hash1", tokens=5000)
    treatment = create_test_run(test_session, "treatment-run", "abc123", "hash1", tokens=4500)

    # Create tiers for phases
    tier_control = Tier(
        tier_id="tier-1",
        run_id=control.id,
        tier_index=1,
        name="Test Tier",
        description="Test tier for control",
    )
    test_session.add(tier_control)

    tier_treatment = Tier(
        tier_id="tier-1",
        run_id=treatment.id,
        tier_index=1,
        name="Test Tier",
        description="Test tier for treatment",
    )
    test_session.add(tier_treatment)
    test_session.flush()

    # Create phases
    create_test_phase(test_session, control.id, "phase-1", PhaseState.COMPLETE, phase_index=1)
    create_test_phase(test_session, control.id, "phase-2", PhaseState.COMPLETE, phase_index=2)
    create_test_phase(test_session, control.id, "phase-3", PhaseState.FAILED, phase_index=3)

    create_test_phase(test_session, treatment.id, "phase-1", PhaseState.COMPLETE, phase_index=1)
    create_test_phase(test_session, treatment.id, "phase-2", PhaseState.COMPLETE, phase_index=2)
    create_test_phase(test_session, treatment.id, "phase-3", PhaseState.COMPLETE, phase_index=3)

    test_session.commit()

    # Create A/B test result with phase metrics
    result = ABTestResult(
        test_id="test-with-phases",
        control_run_id=control.id,
        treatment_run_id=treatment.id,
        control_commit_sha="abc123",
        treatment_commit_sha="abc123",
        control_model_hash="hash1",
        treatment_model_hash="hash1",
        is_valid=True,
        validity_errors=None,
        token_delta=-500,
        control_total_tokens=5000,
        treatment_total_tokens=4500,
        control_total_phases=3,
        control_phases_complete=2,
        control_phases_failed=1,
        treatment_total_phases=3,
        treatment_phases_complete=3,
        treatment_phases_failed=0,
        success_rate_delta=33.3,  # Treatment had better success rate
    )

    test_session.add(result)
    test_session.commit()

    # Verify phase metrics
    retrieved = (
        test_session.query(ABTestResult).filter(ABTestResult.test_id == "test-with-phases").first()
    )
    assert retrieved.control_phases_complete == 2
    assert retrieved.control_phases_failed == 1
    assert retrieved.treatment_phases_complete == 3
    assert retrieved.treatment_phases_failed == 0
    assert retrieved.success_rate_delta == pytest.approx(33.3)


def test_ab_test_result_query_by_validity(test_session):
    """Test querying A/B results by validity status."""
    # Create valid result
    control1 = create_test_run(test_session, "control-1", "abc123", "hash1")
    treatment1 = create_test_run(test_session, "treatment-1", "abc123", "hash1")
    result1 = ABTestResult(
        test_id="valid-test",
        control_run_id=control1.id,
        treatment_run_id=treatment1.id,
        control_commit_sha="abc123",
        treatment_commit_sha="abc123",
        control_model_hash="hash1",
        treatment_model_hash="hash1",
        is_valid=True,
    )
    test_session.add(result1)

    # Create invalid result
    control2 = create_test_run(test_session, "control-2", "abc123", "hash1")
    treatment2 = create_test_run(test_session, "treatment-2", "def456", "hash1")
    result2 = ABTestResult(
        test_id="invalid-test",
        control_run_id=control2.id,
        treatment_run_id=treatment2.id,
        control_commit_sha="abc123",
        treatment_commit_sha="def456",
        control_model_hash="hash1",
        treatment_model_hash="hash1",
        is_valid=False,
        validity_errors=["Commit mismatch"],
    )
    test_session.add(result2)

    test_session.commit()

    # Query only valid results
    valid_results = test_session.query(ABTestResult).filter(ABTestResult.is_valid).all()
    assert len(valid_results) == 1
    assert valid_results[0].test_id == "valid-test"

    # Query only invalid results
    invalid_results = test_session.query(ABTestResult).filter(ABTestResult.is_valid == False).all()
    assert len(invalid_results) == 1
    assert invalid_results[0].test_id == "invalid-test"


def test_ab_test_result_indexes(test_engine):
    """Test that indexes are created for A/B test results."""
    from sqlalchemy import inspect

    inspector = inspect(test_engine)
    indexes = inspector.get_indexes("ab_test_results")

    # Should have index on test_id
    index_names = [idx["name"] for idx in indexes]
    index_columns = [idx["column_names"] for idx in indexes]

    # At minimum, should have index on test_id (from model definition)
    # Note: SQLite auto-creates index for primary key
    assert (
        any("test_id" in cols for cols in index_columns)
        or "ix_ab_test_results_test_id" in index_names
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
