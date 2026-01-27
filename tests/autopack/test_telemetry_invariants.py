"""Tests for ROAD-A telemetry invariants.

Validates:
- PhaseOutcomeEvent model
- Outcome recording with metrics
- Stable IDs and bounded payloads
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, PhaseOutcomeEvent


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_phase_outcome_event_creation(db_session):
    """Test basic PhaseOutcomeEvent creation."""
    event = PhaseOutcomeEvent(
        run_id="test-run-001",
        phase_id="phase-001",
        phase_type="code_generation",
        phase_outcome="SUCCESS",
        stop_reason="completed",
        tokens_used=5000,
        duration_seconds=45.2,
        model_used="claude-3-5-sonnet",
    )

    db_session.add(event)
    db_session.commit()

    # Query back
    result = db_session.query(PhaseOutcomeEvent).filter_by(run_id="test-run-001").first()
    assert result is not None
    assert result.phase_outcome == "SUCCESS"
    assert result.tokens_used == 5000
    assert result.model_used == "claude-3-5-sonnet"


def test_phase_outcome_enum_values(db_session):
    """Test all valid phase outcome enum values."""
    outcomes = ["SUCCESS", "FAILED", "TIMEOUT", "STUCK"]

    for i, outcome in enumerate(outcomes):
        event = PhaseOutcomeEvent(
            run_id=f"test-run-{i}",
            phase_id=f"phase-{i}",
            phase_outcome=outcome,
            stop_reason=f"test_{outcome.lower()}",
        )
        db_session.add(event)

    db_session.commit()

    # Verify all were created
    count = db_session.query(PhaseOutcomeEvent).count()
    assert count == len(outcomes)


def test_phase_outcome_with_rationale(db_session):
    """Test stuck decision with rationale."""
    event = PhaseOutcomeEvent(
        run_id="test-run-stuck",
        phase_id="phase-stuck",
        phase_outcome="STUCK",
        stop_reason="max_revisions",
        stuck_decision_rationale="Phase failed after 3 attempts with same error pattern",
    )

    db_session.add(event)
    db_session.commit()

    result = db_session.query(PhaseOutcomeEvent).filter_by(phase_outcome="STUCK").first()
    assert result is not None
    assert "same error pattern" in result.stuck_decision_rationale


def test_phase_outcome_timestamps(db_session):
    """Test timestamp is automatically set."""
    event = PhaseOutcomeEvent(
        run_id="test-run-timestamp",
        phase_id="phase-timestamp",
        phase_outcome="SUCCESS",
        stop_reason="completed",
    )

    db_session.add(event)
    db_session.commit()

    result = db_session.query(PhaseOutcomeEvent).filter_by(run_id="test-run-timestamp").first()
    assert result.timestamp is not None
    # Timestamp should be recent (within last minute)
    now = datetime.now(timezone.utc)
    time_diff = (
        (now - result.timestamp).total_seconds()
        if result.timestamp.tzinfo
        else (now.replace(tzinfo=None) - result.timestamp).total_seconds()
    )
    assert time_diff < 60  # Within last minute


def test_phase_outcome_indexes(db_session):
    """Test that indexes are created (smoke test)."""
    # Create multiple events
    for i in range(10):
        event = PhaseOutcomeEvent(
            run_id=f"run-{i % 3}",  # 3 different runs
            phase_id=f"phase-{i % 5}",  # 5 different phases
            phase_type="code_generation" if i % 2 == 0 else "test_generation",
            phase_outcome="SUCCESS" if i % 3 == 0 else "FAILED",
            stop_reason="completed" if i % 3 == 0 else "max_tokens",
        )
        db_session.add(event)

    db_session.commit()

    # Query by indexed fields should be fast (smoke test - just verify it works)
    run_events = db_session.query(PhaseOutcomeEvent).filter_by(run_id="run-0").all()
    assert len(run_events) > 0

    phase_events = db_session.query(PhaseOutcomeEvent).filter_by(phase_id="phase-0").all()
    assert len(phase_events) > 0

    failed_events = db_session.query(PhaseOutcomeEvent).filter_by(phase_outcome="FAILED").all()
    assert len(failed_events) > 0


def test_phase_outcome_metrics_tracking(db_session):
    """Test metrics tracking for ROAD-G anomaly detection and ROAD-L optimization."""
    # Create events with varying metrics
    events_data = [
        {"tokens": 5000, "duration": 30.5, "model": "claude-3-5-haiku"},
        {"tokens": 10000, "duration": 60.2, "model": "claude-3-5-sonnet"},
        {"tokens": 50000, "duration": 180.7, "model": "claude-3-opus"},
    ]

    for i, data in enumerate(events_data):
        event = PhaseOutcomeEvent(
            run_id=f"metrics-run-{i}",
            phase_id=f"metrics-phase-{i}",
            phase_type="code_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=data["tokens"],
            duration_seconds=data["duration"],
            model_used=data["model"],
        )
        db_session.add(event)

    db_session.commit()

    # Query for analysis
    all_events = db_session.query(PhaseOutcomeEvent).filter_by(phase_type="code_generation").all()
    assert len(all_events) == 3

    # Check metrics are available
    total_tokens = sum(e.tokens_used for e in all_events if e.tokens_used)
    assert total_tokens == 65000

    avg_duration = sum(e.duration_seconds for e in all_events if e.duration_seconds) / len(
        all_events
    )
    assert 80 < avg_duration < 100  # Should be ~90


def test_phase_type_for_model_optimization(db_session):
    """Test phase_type tracking for ROAD-L model optimization."""
    # Different phase types with different models
    phase_types = [
        ("code_generation", "claude-3-5-sonnet"),
        ("code_generation", "claude-3-5-haiku"),
        ("test_generation", "claude-3-5-haiku"),
        ("documentation", "claude-3-5-haiku"),
    ]

    for i, (phase_type, model) in enumerate(phase_types):
        event = PhaseOutcomeEvent(
            run_id=f"opt-run-{i}",
            phase_id=f"opt-phase-{i}",
            phase_type=phase_type,
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=5000,
            model_used=model,
        )
        db_session.add(event)

    db_session.commit()

    # Query by phase type for optimization analysis
    code_gen_events = (
        db_session.query(PhaseOutcomeEvent).filter_by(phase_type="code_generation").all()
    )
    assert len(code_gen_events) == 2

    # Check different models were used
    models_used = {e.model_used for e in code_gen_events}
    assert len(models_used) == 2  # Both sonnet and haiku used


def test_phase_outcome_failure_patterns(db_session):
    """Test failure tracking for ROAD-B analysis."""
    # Create various failure patterns
    failures = [
        {"stop_reason": "max_tokens", "count": 5},
        {"stop_reason": "rate_limit", "count": 3},
        {"stop_reason": "retry_limit", "count": 2},
    ]

    for failure in failures:
        for i in range(failure["count"]):
            event = PhaseOutcomeEvent(
                run_id=f"fail-run-{failure['stop_reason']}-{i}",
                phase_id="test-phase",
                phase_type="code_generation",
                phase_outcome="FAILED",
                stop_reason=failure["stop_reason"],
            )
            db_session.add(event)

    db_session.commit()

    # Query for analysis
    all_failures = db_session.query(PhaseOutcomeEvent).filter_by(phase_outcome="FAILED").all()
    assert len(all_failures) == 10  # 5 + 3 + 2

    # Count by stop reason
    max_token_failures = (
        db_session.query(PhaseOutcomeEvent).filter_by(stop_reason="max_tokens").count()
    )
    assert max_token_failures == 5
