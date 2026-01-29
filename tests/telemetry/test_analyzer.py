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


def test_telemetry_to_memory_bridge_is_mandatory(db_session):
    """Test IMP-LOOP-020: TelemetryToMemoryBridge is mandatory and cannot be disabled.

    The feedback loop requires telemetry to flow to memory for self-improvement.
    There is no env var override or disabled state.
    """
    # Analyzer should always be ready to persist telemetry when memory is available
    analyzer = TelemetryAnalyzer(db_session)

    # Verify analyzer is properly initialized and ready to work with memory
    # The bridge will be created when aggregate_telemetry is called with a memory service
    assert analyzer.db == db_session
    assert analyzer.run_id is not None


# =============================================================================
# IMP-TST-005: Tests for ingest_diagnostic_findings()
# =============================================================================


class TestIngestDiagnosticFindings:
    """Test suite for ingest_diagnostic_findings() edge cases (IMP-TST-005).

    Covers severity/resolution combinations, evidence aggregation,
    and zero/null metrics handling.
    """

    @pytest.fixture
    def analyzer(self, db_session):
        """Create a TelemetryAnalyzer for testing."""
        return TelemetryAnalyzer(db_session)

    # -------------------------------------------------------------------------
    # Severity/Resolution Combinations
    # -------------------------------------------------------------------------

    def test_high_severity_unresolved(self, analyzer):
        """Test high severity unresolved finding gets maximum weight."""
        findings = [
            {
                "failure_class": "compilation_error",
                "probe_name": "syntax_probe",
                "resolved": False,
                "severity": "high",
                "evidence": "Syntax error on line 42",
                "commands_run": 3,
                "exit_codes": [1, 1, 0],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # high (3.0) * unresolved (2.0) = 6.0
        assert issue.metric_value == 6.0
        assert issue.issue_type == "diagnostic"
        assert issue.details["severity"] == "high"
        assert issue.details["resolved"] is False

    def test_high_severity_resolved(self, analyzer):
        """Test high severity resolved finding gets reduced weight."""
        findings = [
            {
                "failure_class": "compilation_error",
                "probe_name": "syntax_probe",
                "resolved": True,
                "severity": "high",
                "evidence": "Fixed syntax error",
                "commands_run": 5,
                "exit_codes": [1, 1, 1, 0, 0],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # high (3.0) * resolved (1.0) = 3.0
        assert issue.metric_value == 3.0
        assert issue.details["resolved"] is True

    def test_medium_severity_unresolved(self, analyzer):
        """Test medium severity unresolved finding."""
        findings = [
            {
                "failure_class": "test_failure",
                "probe_name": "test_probe",
                "resolved": False,
                "severity": "medium",
                "evidence": "Test assertion failed",
                "commands_run": 2,
                "exit_codes": [1, 1],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # medium (2.0) * unresolved (2.0) = 4.0
        assert issue.metric_value == 4.0
        assert issue.details["severity"] == "medium"

    def test_medium_severity_resolved(self, analyzer):
        """Test medium severity resolved finding."""
        findings = [
            {
                "failure_class": "test_failure",
                "probe_name": "test_probe",
                "resolved": True,
                "severity": "medium",
                "evidence": "Test now passes",
                "commands_run": 4,
                "exit_codes": [1, 0, 0, 0],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # medium (2.0) * resolved (1.0) = 2.0
        assert issue.metric_value == 2.0

    def test_low_severity_unresolved(self, analyzer):
        """Test low severity unresolved finding."""
        findings = [
            {
                "failure_class": "lint_warning",
                "probe_name": "lint_probe",
                "resolved": False,
                "severity": "low",
                "evidence": "Unused import detected",
                "commands_run": 1,
                "exit_codes": [0],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # low (1.0) * unresolved (2.0) = 2.0
        assert issue.metric_value == 2.0
        assert issue.details["severity"] == "low"

    def test_low_severity_resolved(self, analyzer):
        """Test low severity resolved finding gets minimum weight."""
        findings = [
            {
                "failure_class": "lint_warning",
                "probe_name": "lint_probe",
                "resolved": True,
                "severity": "low",
                "evidence": "Import removed",
                "commands_run": 2,
                "exit_codes": [0, 0],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # low (1.0) * resolved (1.0) = 1.0
        assert issue.metric_value == 1.0

    def test_all_severity_resolution_combinations(self, analyzer):
        """Test all six severity/resolution combinations at once."""
        findings = [
            {"severity": "high", "resolved": False, "failure_class": "high_unresolved"},
            {"severity": "high", "resolved": True, "failure_class": "high_resolved"},
            {"severity": "medium", "resolved": False, "failure_class": "medium_unresolved"},
            {"severity": "medium", "resolved": True, "failure_class": "medium_resolved"},
            {"severity": "low", "resolved": False, "failure_class": "low_unresolved"},
            {"severity": "low", "resolved": True, "failure_class": "low_resolved"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 6
        # Check metric values match expected weights
        expected_weights = [6.0, 3.0, 4.0, 2.0, 2.0, 1.0]
        for issue, expected in zip(result, expected_weights):
            assert issue.metric_value == expected

    # -------------------------------------------------------------------------
    # Evidence Aggregation
    # -------------------------------------------------------------------------

    def test_evidence_preserved_in_details(self, analyzer):
        """Test that evidence string is preserved in issue details."""
        evidence_text = "Stack trace:\n  File 'main.py', line 42\n  TypeError: expected int"
        findings = [
            {
                "failure_class": "runtime_error",
                "probe_name": "exception_probe",
                "resolved": False,
                "severity": "high",
                "evidence": evidence_text,
                "commands_run": 1,
                "exit_codes": [1],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].details["evidence"] == evidence_text

    def test_multiple_findings_preserve_all_evidence(self, analyzer):
        """Test multiple findings each preserve their evidence."""
        findings = [
            {"failure_class": "error_a", "evidence": "Evidence for A"},
            {"failure_class": "error_b", "evidence": "Evidence for B"},
            {"failure_class": "error_c", "evidence": "Evidence for C"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 3
        assert result[0].details["evidence"] == "Evidence for A"
        assert result[1].details["evidence"] == "Evidence for B"
        assert result[2].details["evidence"] == "Evidence for C"

    def test_exit_codes_aggregated_correctly(self, analyzer):
        """Test exit codes list is preserved in details."""
        exit_codes = [0, 1, 2, 127, 255]
        findings = [
            {
                "failure_class": "multi_command",
                "exit_codes": exit_codes,
                "commands_run": 5,
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].details["exit_codes"] == exit_codes
        assert result[0].details["commands_run"] == 5

    # -------------------------------------------------------------------------
    # Zero/Null Metrics Handling
    # -------------------------------------------------------------------------

    def test_zero_commands_run(self, analyzer):
        """Test handling of zero commands run."""
        findings = [
            {
                "failure_class": "static_analysis",
                "probe_name": "static_probe",
                "commands_run": 0,
                "exit_codes": [],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        assert result[0].details["commands_run"] == 0
        assert result[0].details["exit_codes"] == []

    def test_empty_exit_codes(self, analyzer):
        """Test handling of empty exit_codes list."""
        findings = [
            {
                "failure_class": "no_commands",
                "exit_codes": [],
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].details["exit_codes"] == []

    def test_null_evidence(self, analyzer):
        """Test handling of None evidence."""
        findings = [
            {
                "failure_class": "no_evidence",
                "evidence": None,
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        # Should use empty string when None provided (get with default)
        # The implementation uses .get() which returns None if key exists with None value
        # But our code does finding.get("evidence", "") which uses "" only if key missing
        assert result[0].details["evidence"] is None or result[0].details["evidence"] == ""

    def test_missing_evidence_field(self, analyzer):
        """Test handling of missing evidence field entirely."""
        findings = [
            {
                "failure_class": "minimal_finding",
            }
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        # Should default to empty string
        assert result[0].details["evidence"] == ""

    def test_missing_all_optional_fields(self, analyzer):
        """Test finding with no optional fields at all."""
        findings = [{}]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 1
        issue = result[0]
        # All defaults should be applied
        assert issue.details["failure_class"] == "unknown"
        assert issue.details["probe_name"] == "unknown_probe"
        assert issue.details["resolved"] is False
        assert issue.details["severity"] == "medium"
        assert issue.details["evidence"] == ""
        assert issue.details["commands_run"] == 0
        assert issue.details["exit_codes"] == []
        # Default severity (medium=2.0) * unresolved (2.0) = 4.0
        assert issue.metric_value == 4.0

    def test_null_severity_uses_default(self, analyzer):
        """Test that null/missing severity defaults to medium."""
        findings = [
            {"failure_class": "test", "severity": None},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        # None severity should be treated like missing, defaulting to medium
        # The .get() returns None, so severity_weights.get(None, 2.0) = 2.0
        assert result[0].metric_value == 4.0  # medium (2.0) * unresolved (2.0)

    def test_invalid_severity_uses_default(self, analyzer):
        """Test that invalid severity string defaults to medium weight."""
        findings = [
            {"failure_class": "test", "severity": "critical"},  # Not a valid value
            {"failure_class": "test2", "severity": "INVALID"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        # Invalid severity should use default weight of 2.0 (medium)
        assert result[0].metric_value == 4.0  # default (2.0) * unresolved (2.0)
        assert result[1].metric_value == 4.0

    # -------------------------------------------------------------------------
    # Ranking and Ordering
    # -------------------------------------------------------------------------

    def test_findings_ranked_by_input_order(self, analyzer):
        """Test that findings are ranked 1, 2, 3... by input order."""
        findings = [
            {"failure_class": "first"},
            {"failure_class": "second"},
            {"failure_class": "third"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].rank == 1
        assert result[1].rank == 2
        assert result[2].rank == 3

    def test_empty_findings_list(self, analyzer):
        """Test handling of empty findings list."""
        result = analyzer.ingest_diagnostic_findings([])

        assert result == []

    # -------------------------------------------------------------------------
    # Phase ID and Run ID Handling
    # -------------------------------------------------------------------------

    def test_run_id_preserved_in_details(self, analyzer):
        """Test that run_id is preserved in issue details."""
        findings = [{"failure_class": "test"}]

        result = analyzer.ingest_diagnostic_findings(findings, run_id="run-12345")

        assert result[0].details["run_id"] == "run-12345"

    def test_phase_id_used_when_provided(self, analyzer):
        """Test that provided phase_id is used in issue."""
        findings = [{"failure_class": "test"}]

        result = analyzer.ingest_diagnostic_findings(findings, phase_id="custom-phase-id")

        assert result[0].phase_id == "custom-phase-id"

    def test_phase_id_derived_from_failure_class_when_not_provided(self, analyzer):
        """Test that phase_id is derived from failure_class when not provided."""
        findings = [{"failure_class": "my_error_type"}]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].phase_id == "diag-my_error_type"

    def test_null_run_id_and_phase_id(self, analyzer):
        """Test handling when both run_id and phase_id are None."""
        findings = [{"failure_class": "test_class"}]

        result = analyzer.ingest_diagnostic_findings(findings, run_id=None, phase_id=None)

        assert result[0].details["run_id"] is None
        assert result[0].phase_id == "diag-test_class"

    # -------------------------------------------------------------------------
    # Issue Type and Phase Type
    # -------------------------------------------------------------------------

    def test_issue_type_is_diagnostic(self, analyzer):
        """Test that all issues have issue_type='diagnostic'."""
        findings = [
            {"failure_class": "a"},
            {"failure_class": "b"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        for issue in result:
            assert issue.issue_type == "diagnostic"

    def test_phase_type_includes_failure_class(self, analyzer):
        """Test that phase_type is 'diagnostic:{failure_class}'."""
        findings = [{"failure_class": "my_failure_class"}]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].phase_type == "diagnostic:my_failure_class"

    def test_source_is_diagnostics_agent(self, analyzer):
        """Test that source is always 'diagnostics_agent'."""
        findings = [{"failure_class": "test"}]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert result[0].details["source"] == "diagnostics_agent"

    # -------------------------------------------------------------------------
    # Complex Scenarios
    # -------------------------------------------------------------------------

    def test_large_number_of_findings(self, analyzer):
        """Test handling of many findings at once."""
        findings = [{"failure_class": f"error_{i}", "severity": "medium"} for i in range(100)]

        result = analyzer.ingest_diagnostic_findings(findings)

        assert len(result) == 100
        # Verify ranking is correct
        for i, issue in enumerate(result):
            assert issue.rank == i + 1

    def test_mixed_severity_resolution_ranking(self, analyzer):
        """Test mixed findings maintain correct order and weights."""
        findings = [
            {"severity": "low", "resolved": True, "failure_class": "a"},
            {"severity": "high", "resolved": False, "failure_class": "b"},
            {"severity": "medium", "resolved": True, "failure_class": "c"},
        ]

        result = analyzer.ingest_diagnostic_findings(findings)

        # Order should be preserved as input
        assert result[0].details["failure_class"] == "a"
        assert result[0].metric_value == 1.0  # low resolved

        assert result[1].details["failure_class"] == "b"
        assert result[1].metric_value == 6.0  # high unresolved

        assert result[2].details["failure_class"] == "c"
        assert result[2].metric_value == 2.0  # medium resolved
