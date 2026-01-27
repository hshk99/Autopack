"""Tests for telemetry analyzer (ROAD-B)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, PhaseOutcomeEvent
from autopack.telemetry.analyzer import RankedIssue, TelemetryAnalyzer


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
    """Database populated with test telemetry data."""
    now = datetime.now(timezone.utc)

    # Cost sinks: phases with high token usage
    events = [
        # Phase 1: High token consumer (50k tokens total)
        PhaseOutcomeEvent(
            run_id="run-001",
            phase_id="phase-expensive",
            phase_type="code_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=25000,
            duration_seconds=120.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=1),
        ),
        PhaseOutcomeEvent(
            run_id="run-002",
            phase_id="phase-expensive",
            phase_type="code_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=25000,
            duration_seconds=115.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=2),
        ),
        # Phase 2: Medium token consumer (20k tokens total)
        PhaseOutcomeEvent(
            run_id="run-003",
            phase_id="phase-medium",
            phase_type="test_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=10000,
            duration_seconds=60.0,
            model_used="claude-3-5-haiku",
            timestamp=now - timedelta(hours=3),
        ),
        PhaseOutcomeEvent(
            run_id="run-004",
            phase_id="phase-medium",
            phase_type="test_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=10000,
            duration_seconds=55.0,
            model_used="claude-3-5-haiku",
            timestamp=now - timedelta(hours=4),
        ),
        # Failure modes: phases that fail frequently
        PhaseOutcomeEvent(
            run_id="run-005",
            phase_id="phase-flaky",
            phase_type="code_generation",
            phase_outcome="FAILED",
            stop_reason="max_tokens",
            tokens_used=8000,
            duration_seconds=30.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=5),
        ),
        PhaseOutcomeEvent(
            run_id="run-006",
            phase_id="phase-flaky",
            phase_type="code_generation",
            phase_outcome="FAILED",
            stop_reason="max_tokens",
            tokens_used=8000,
            duration_seconds=32.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=6),
        ),
        PhaseOutcomeEvent(
            run_id="run-007",
            phase_id="phase-flaky",
            phase_type="code_generation",
            phase_outcome="FAILED",
            stop_reason="max_tokens",
            tokens_used=8000,
            duration_seconds=28.0,
            model_used="claude-3-5-sonnet",
            timestamp=now - timedelta(hours=7),
        ),
        # Retry causes: phases with multiple attempts
        PhaseOutcomeEvent(
            run_id="run-008",
            phase_id="phase-retry",
            phase_type="test_generation",
            phase_outcome="FAILED",
            stop_reason="rate_limit",
            tokens_used=5000,
            duration_seconds=20.0,
            model_used="claude-3-5-haiku",
            timestamp=now - timedelta(hours=8),
        ),
        PhaseOutcomeEvent(
            run_id="run-008",
            phase_id="phase-retry",
            phase_type="test_generation",
            phase_outcome="FAILED",
            stop_reason="rate_limit",
            tokens_used=5000,
            duration_seconds=22.0,
            model_used="claude-3-5-haiku",
            timestamp=now - timedelta(hours=8, minutes=5),
        ),
        PhaseOutcomeEvent(
            run_id="run-008",
            phase_id="phase-retry",
            phase_type="test_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=5000,
            duration_seconds=25.0,
            model_used="claude-3-5-haiku",
            timestamp=now - timedelta(hours=8, minutes=10),
        ),
        # Old events (outside window)
        PhaseOutcomeEvent(
            run_id="run-old",
            phase_id="phase-old",
            phase_type="code_generation",
            phase_outcome="SUCCESS",
            stop_reason="completed",
            tokens_used=100000,
            duration_seconds=300.0,
            model_used="claude-3-opus",
            timestamp=now - timedelta(days=30),
        ),
    ]

    for event in events:
        db_session.add(event)

    db_session.commit()
    return db_session


def test_analyzer_initialization(db_session):
    """Test TelemetryAnalyzer initialization."""
    analyzer = TelemetryAnalyzer(db_session)
    assert analyzer.db == db_session


def test_find_cost_sinks(populated_db):
    """Test finding top cost sinks."""
    analyzer = TelemetryAnalyzer(populated_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    cost_sinks = analyzer._find_cost_sinks(cutoff)

    # Should have at least 2 phases
    assert len(cost_sinks) >= 2

    # Top cost sink should be phase-expensive (50k tokens)
    top_sink = cost_sinks[0]
    assert top_sink.rank == 1
    assert top_sink.issue_type == "cost_sink"
    assert top_sink.phase_id == "phase-expensive"
    assert top_sink.metric_value == 50000
    assert top_sink.details["avg_tokens"] == 25000
    assert top_sink.details["count"] == 2

    # Find phase-medium in the results (20k tokens)
    phase_ids = [sink.phase_id for sink in cost_sinks]
    assert "phase-medium" in phase_ids
    medium_sink = next(sink for sink in cost_sinks if sink.phase_id == "phase-medium")
    assert medium_sink.metric_value == 20000


def test_find_failure_modes(populated_db):
    """Test finding top failure modes."""
    analyzer = TelemetryAnalyzer(populated_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    failure_modes = analyzer._find_failure_modes(cutoff)

    # Should have at least 2 failure modes (flaky, retry)
    assert len(failure_modes) >= 2

    # Top failure should be phase-flaky (3 failures)
    top_failure = failure_modes[0]
    assert top_failure.rank == 1
    assert top_failure.issue_type == "failure_mode"
    assert top_failure.phase_id == "phase-flaky"
    assert top_failure.metric_value == 3
    assert top_failure.details["outcome"] == "FAILED"
    assert top_failure.details["stop_reason"] == "max_tokens"


def test_find_retry_causes(populated_db):
    """Test finding top retry causes."""
    analyzer = TelemetryAnalyzer(populated_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    retry_causes = analyzer._find_retry_causes(cutoff)

    # Should have at least 1 retry cause
    assert len(retry_causes) >= 1

    # Find phase-retry with rate_limit stop_reason (2 attempts with same stop_reason)
    # Note: The query groups by stop_reason, so successes and failures are separate groups
    phase_ids = [retry.phase_id for retry in retry_causes]
    assert "phase-retry" in phase_ids
    retry_issue = next(
        retry
        for retry in retry_causes
        if retry.phase_id == "phase-retry" and retry.details["stop_reason"] == "rate_limit"
    )
    assert retry_issue.issue_type == "retry_cause"
    # 2 failures with rate_limit stop_reason
    assert retry_issue.metric_value == 2
    assert retry_issue.details["retry_count"] == 2


def test_compute_phase_type_stats(populated_db):
    """Test computing phase type statistics for ROAD-L."""
    analyzer = TelemetryAnalyzer(populated_db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    stats = analyzer._compute_phase_type_stats(cutoff)

    # Should have stats for code_generation and test_generation
    assert len(stats) >= 2

    # Check code_generation:claude-3-5-sonnet stats
    key = "code_generation:claude-3-5-sonnet"
    assert key in stats
    code_gen_stats = stats[key]
    # 2 successes + 3 failures = 5 total, 2/5 = 0.4 success rate
    assert code_gen_stats["success_rate"] == pytest.approx(0.4, rel=0.01)
    assert code_gen_stats["sample_count"] >= 5

    # Check test_generation:claude-3-5-haiku stats
    key = "test_generation:claude-3-5-haiku"
    assert key in stats
    test_gen_stats = stats[key]
    # 3 successes (2 from medium + 1 from retry) + 2 failures = 5 total, 3/5 = 0.6
    assert test_gen_stats["success_rate"] == pytest.approx(0.6, rel=0.01)
    assert test_gen_stats["sample_count"] >= 5


def test_aggregate_telemetry(populated_db):
    """Test full telemetry aggregation."""
    analyzer = TelemetryAnalyzer(populated_db)

    issues = analyzer.aggregate_telemetry(window_days=7)

    # Should have all categories
    assert "top_cost_sinks" in issues
    assert "top_failure_modes" in issues
    assert "top_retry_causes" in issues
    assert "phase_type_stats" in issues

    # Each category should have data
    assert len(issues["top_cost_sinks"]) > 0
    assert len(issues["top_failure_modes"]) > 0
    assert len(issues["top_retry_causes"]) > 0
    assert len(issues["phase_type_stats"]) > 0


def test_aggregate_telemetry_respects_window(populated_db):
    """Test that aggregation respects the time window."""
    analyzer = TelemetryAnalyzer(populated_db)

    # Analyze only last 1 day (should exclude 30-day-old event)
    issues = analyzer.aggregate_telemetry(window_days=1)

    # Old phase with 100k tokens should not appear
    cost_sinks = issues["top_cost_sinks"]
    old_phase_ids = [sink.phase_id for sink in cost_sinks if sink.phase_id == "phase-old"]
    assert len(old_phase_ids) == 0


def test_write_ranked_issues(populated_db, tmp_path):
    """Test writing ranked issues to file."""
    analyzer = TelemetryAnalyzer(populated_db)
    issues = analyzer.aggregate_telemetry(window_days=7)

    output_path = tmp_path / "ranked_issues.md"
    analyzer.write_ranked_issues(issues, output_path)

    # Verify file was created
    assert output_path.exists()

    # Verify content
    content = output_path.read_text()
    assert "# Telemetry Analysis - Ranked Issues" in content
    assert "## Top Cost Sinks" in content
    assert "## Top Failure Modes" in content
    assert "## Top Retry Causes" in content
    assert "## Phase Type Statistics (for ROAD-L)" in content

    # Verify specific data appears
    assert "phase-expensive" in content
    assert "phase-flaky" in content
    assert "50,000" in content  # Total tokens for phase-expensive


def test_empty_database(db_session, tmp_path):
    """Test analyzer behavior with empty database."""
    analyzer = TelemetryAnalyzer(db_session)
    issues = analyzer.aggregate_telemetry(window_days=7)

    # Should have empty lists
    assert len(issues["top_cost_sinks"]) == 0
    assert len(issues["top_failure_modes"]) == 0
    assert len(issues["top_retry_causes"]) == 0
    assert len(issues["phase_type_stats"]) == 0

    # Should still write report without errors
    output_path = tmp_path / "empty_report.md"
    analyzer.write_ranked_issues(issues, output_path)

    assert output_path.exists()
    content = output_path.read_text()
    assert "No cost sinks found" in content
    assert "No failure modes found" in content
    assert "No retry patterns found" in content


def test_ranked_issue_dataclass():
    """Test RankedIssue dataclass."""
    issue = RankedIssue(
        rank=1,
        issue_type="cost_sink",
        phase_id="test-phase",
        phase_type="code_generation",
        metric_value=50000.0,
        details={"avg_tokens": 25000, "count": 2},
    )

    assert issue.rank == 1
    assert issue.issue_type == "cost_sink"
    assert issue.phase_id == "test-phase"
    assert issue.phase_type == "code_generation"
    assert issue.metric_value == 50000.0
    assert issue.details["avg_tokens"] == 25000


def test_telemetry_to_memory_mandatory_logs_warning_on_disable_attempt(
    db_session, monkeypatch, caplog
):
    """Test IMP-LOOP-010: Telemetry-to-memory persistence logs warning when env var tries to disable."""
    import logging

    # Set env var to try to disable
    monkeypatch.setenv("AUTOPACK_TELEMETRY_TO_MEMORY_ENABLED", "false")

    with caplog.at_level(logging.WARNING):
        analyzer = TelemetryAnalyzer(db_session)

    # Feature should remain enabled despite env var
    assert analyzer._telemetry_to_memory_enabled is True

    # Warning should be logged
    assert any(
        "IMP-LOOP-010" in record.message and "false" in record.message for record in caplog.records
    )


def test_telemetry_to_memory_enabled_by_default(db_session, monkeypatch):
    """Test that telemetry-to-memory is enabled by default without warning."""
    # Ensure env var is not set
    monkeypatch.delenv("AUTOPACK_TELEMETRY_TO_MEMORY_ENABLED", raising=False)

    analyzer = TelemetryAnalyzer(db_session)

    # Feature should be enabled
    assert analyzer._telemetry_to_memory_enabled is True


def test_telemetry_to_memory_no_warning_when_explicitly_enabled(db_session, monkeypatch, caplog):
    """Test that no warning is logged when env var explicitly enables the feature."""
    import logging

    # Explicitly enable via env var
    monkeypatch.setenv("AUTOPACK_TELEMETRY_TO_MEMORY_ENABLED", "true")

    with caplog.at_level(logging.WARNING):
        analyzer = TelemetryAnalyzer(db_session)

    # Feature should be enabled
    assert analyzer._telemetry_to_memory_enabled is True

    # No IMP-LOOP-010 warning should be logged
    assert not any("IMP-LOOP-010" in record.message for record in caplog.records)
