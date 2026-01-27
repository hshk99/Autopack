"""Tests for telemetry-driven model performance tracker (ROAD-L)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, PhaseOutcomeEvent
from autopack.telemetry.model_performance_tracker import (
    ModelPerformance,
    TelemetryDrivenModelOptimizer,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def populated_db(db_session):
    """Database populated with model performance telemetry."""
    now = datetime.now(timezone.utc)

    events = [
        # Haiku performing well on test_generation (20 successes, 0 failures)
        *[
            PhaseOutcomeEvent(
                run_id=f"run-haiku-{i:03d}",
                phase_id=f"phase-test-{i:03d}",
                phase_type="test_generation",
                phase_outcome="SUCCESS",
                stop_reason="completed",
                tokens_used=5000,
                duration_seconds=10.0,
                model_used="claude-3-5-haiku",
                timestamp=now - timedelta(hours=i),
            )
            for i in range(20)
        ],
        # Sonnet performing poorly on code_generation (5 success, 15 failures)
        *[
            PhaseOutcomeEvent(
                run_id=f"run-sonnet-fail-{i:03d}",
                phase_id=f"phase-code-fail-{i:03d}",
                phase_type="code_generation",
                phase_outcome="FAILED",
                stop_reason="max_tokens",
                tokens_used=8000,
                duration_seconds=15.0,
                model_used="claude-3-5-sonnet",
                timestamp=now - timedelta(hours=i),
            )
            for i in range(15)
        ],
        *[
            PhaseOutcomeEvent(
                run_id=f"run-sonnet-success-{i:03d}",
                phase_id=f"phase-code-success-{i:03d}",
                phase_type="code_generation",
                phase_outcome="SUCCESS",
                stop_reason="completed",
                tokens_used=8000,
                duration_seconds=15.0,
                model_used="claude-3-5-sonnet",
                timestamp=now - timedelta(hours=i + 15),
            )
            for i in range(5)
        ],
        # Opus performing well on code_generation (25 successes)
        *[
            PhaseOutcomeEvent(
                run_id=f"run-opus-{i:03d}",
                phase_id=f"phase-code-opus-{i:03d}",
                phase_type="code_generation",
                phase_outcome="SUCCESS",
                stop_reason="completed",
                tokens_used=12000,
                duration_seconds=20.0,
                model_used="claude-3-opus",
                timestamp=now - timedelta(hours=i + 30),
            )
            for i in range(25)
        ],
        # Sonnet performing very well on refactoring (30 successes, 1 failure)
        *[
            PhaseOutcomeEvent(
                run_id=f"run-sonnet-refactor-{i:03d}",
                phase_id=f"phase-refactor-{i:03d}",
                phase_type="refactoring",
                phase_outcome="SUCCESS",
                stop_reason="completed",
                tokens_used=7000,
                duration_seconds=12.0,
                model_used="claude-3-5-sonnet",
                timestamp=now - timedelta(hours=i + 60),
            )
            for i in range(30)
        ],
        PhaseOutcomeEvent(
            run_id="run-sonnet-refactor-fail",
            phase_id="phase-refactor-fail",
            phase_type="refactoring",
            phase_outcome="FAILED",
            stop_reason="timeout",
            tokens_used=7000,
            duration_seconds=12.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=90),
        ),
    ]

    for event in events:
        db_session.add(event)

    db_session.commit()
    return db_session


def test_optimizer_initialization():
    """Test TelemetryDrivenModelOptimizer initialization."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    optimizer = TelemetryDrivenModelOptimizer(
        db_session=session,
        min_samples=15,
        downgrade_success_threshold=0.90,
        escalation_failure_threshold=0.20,
        lookback_days=14,
    )

    assert optimizer.min_samples == 15
    assert optimizer.downgrade_success_threshold == 0.90
    assert optimizer.escalation_failure_threshold == 0.20
    assert optimizer.lookback_days == 14
    assert optimizer._performance_cache == {}

    session.close()


def test_get_performance_stats_empty(db_session):
    """Test getting performance stats from empty database."""
    optimizer = TelemetryDrivenModelOptimizer(db_session)

    stats = optimizer.get_performance_stats("nonexistent_phase")

    assert len(stats) == 0


def test_get_performance_stats_with_data(populated_db):
    """Test getting performance stats with populated data."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db)

    # Get stats for test_generation
    stats = optimizer.get_performance_stats("test_generation")

    assert len(stats) >= 1
    assert "test_generation:claude-3-5-haiku" in stats

    haiku_stats = stats["test_generation:claude-3-5-haiku"]
    assert haiku_stats.model_id == "claude-3-5-haiku"
    assert haiku_stats.phase_type == "test_generation"
    assert haiku_stats.success_rate == 1.0  # 100% success
    assert haiku_stats.sample_count == 20


def test_suggest_model_insufficient_data(populated_db):
    """Test that optimizer requires minimum samples before suggesting changes."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db, min_samples=50)

    # Even though haiku has 100% success, we need 50 samples
    model, reason = optimizer.suggest_model(
        phase_type="test_generation",
        current_model="claude-3-5-haiku",
        complexity="medium",
    )

    # Should keep current model (insufficient samples)
    assert model == "claude-3-5-haiku"
    assert reason is None


def test_downgrade_suggestion(populated_db):
    """Test downgrade suggestion when cheaper model performs well."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db, min_samples=20)

    # Sonnet has 96.8% success rate on refactoring (30/31)
    # Should suggest downgrade to haiku if haiku also performs well
    model, reason = optimizer.suggest_model(
        phase_type="refactoring",
        current_model="claude-3-5-sonnet",
        complexity="medium",
    )

    # With only sonnet data, can't downgrade yet
    assert model == "claude-3-5-sonnet"


def test_escalation_suggestion(populated_db):
    """Test escalation suggestion when failure rate is high."""
    optimizer = TelemetryDrivenModelOptimizer(
        populated_db, min_samples=15, escalation_failure_threshold=0.15
    )

    # Sonnet has 25% failure rate on code_generation (15 failures / 20 total)
    # Should suggest escalation to opus
    model, reason = optimizer.suggest_model(
        phase_type="code_generation",
        current_model="claude-3-5-sonnet",
        complexity="medium",
    )

    # Should escalate to opus (which has better success rate)
    assert model == "claude-3-opus"
    assert reason is not None
    assert "Escalating" in reason
    assert "success rate" in reason


def test_no_change_when_performing_well(populated_db):
    """Test that optimizer keeps model when it's performing well."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db, min_samples=20)

    # Haiku has 100% success on test_generation
    model, reason = optimizer.suggest_model(
        phase_type="test_generation",
        current_model="claude-3-5-haiku",
        complexity="medium",
    )

    # Should keep haiku (already optimal)
    assert model == "claude-3-5-haiku"
    assert reason is None


def test_model_cost_tiers():
    """Test model cost tier mappings."""
    assert TelemetryDrivenModelOptimizer.MODEL_COST_TIERS["claude-3-haiku"] == 1
    assert TelemetryDrivenModelOptimizer.MODEL_COST_TIERS["claude-3-5-haiku"] == 1
    assert TelemetryDrivenModelOptimizer.MODEL_COST_TIERS["claude-3-5-sonnet"] == 3
    assert TelemetryDrivenModelOptimizer.MODEL_COST_TIERS["claude-3-opus"] == 10


def test_cache_refresh(populated_db):
    """Test that cache is refreshed appropriately."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db)

    # First call should populate cache
    stats1 = optimizer.get_performance_stats("test_generation")
    assert optimizer._cache_timestamp is not None
    first_timestamp = optimizer._cache_timestamp

    # Immediate second call should use cache
    stats2 = optimizer.get_performance_stats("test_generation")
    assert optimizer._cache_timestamp == first_timestamp

    # Cache should be same
    assert stats1 == stats2


def test_find_better_model(populated_db):
    """Test finding better model when current one fails."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db, min_samples=15)

    stats = optimizer.get_performance_stats("code_generation")

    # Sonnet is failing, should find opus (higher tier, better success)
    better = optimizer._find_better_model("code_generation", "claude-3-5-sonnet", stats)

    assert better == "claude-3-opus"


def test_find_cheaper_model_none_available(populated_db):
    """Test finding cheaper model when none available."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db, min_samples=20)

    stats = optimizer.get_performance_stats("test_generation")

    # Haiku is already cheapest, can't downgrade further
    cheaper = optimizer._find_cheaper_model("test_generation", "claude-3-5-haiku", stats)

    assert cheaper is None


def test_model_performance_dataclass():
    """Test ModelPerformance dataclass creation."""
    perf = ModelPerformance(
        model_id="claude-3-5-sonnet",
        phase_type="code_generation",
        success_rate=0.85,
        avg_tokens=8000.0,
        avg_duration=15.5,
        sample_count=30,
        last_updated=datetime.now(timezone.utc),
    )

    assert perf.model_id == "claude-3-5-sonnet"
    assert perf.phase_type == "code_generation"
    assert perf.success_rate == 0.85
    assert perf.avg_tokens == 8000.0
    assert perf.avg_duration == 15.5
    assert perf.sample_count == 30
    assert isinstance(perf.last_updated, datetime)


def test_suggest_model_with_no_phase_type_stats(db_session):
    """Test suggest_model when phase_type has no historical data."""
    optimizer = TelemetryDrivenModelOptimizer(db_session)

    # No data for this phase type
    model, reason = optimizer.suggest_model(
        phase_type="unknown_phase",
        current_model="claude-3-5-sonnet",
        complexity="medium",
    )

    # Should keep current model
    assert model == "claude-3-5-sonnet"
    assert reason is None


def test_multiple_phase_types_tracked_separately(populated_db):
    """Test that different phase types are tracked independently."""
    optimizer = TelemetryDrivenModelOptimizer(populated_db)

    test_gen_stats = optimizer.get_performance_stats("test_generation")
    code_gen_stats = optimizer.get_performance_stats("code_generation")

    # Should have different stats
    assert len(test_gen_stats) > 0
    assert len(code_gen_stats) > 0

    # Phase types should be different
    for key, perf in test_gen_stats.items():
        assert perf.phase_type == "test_generation"

    for key, perf in code_gen_stats.items():
        assert perf.phase_type == "code_generation"
