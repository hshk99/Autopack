"""Tests for ROAD-I: Regression Protection."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autopack.telemetry.regression_protector import (
    IssueFix,
    IssueType,
    RegressionProtector,
    RegressionSeverity,
)


@pytest.fixture
def temp_storage():
    """Create temporary storage file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        yield f.name
    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def protector(temp_storage):
    """Create regression protector with temporary storage."""
    return RegressionProtector(
        storage_path=temp_storage, regression_threshold=0.15, lookback_window_days=90
    )


@pytest.fixture
def token_fix():
    """Sample fix for token usage issue."""
    return IssueFix(
        issue_id="COST_phase_build_1",
        issue_type=IssueType.COST_SINK,
        phase_id="phase_build",
        description="Reduced token usage by optimizing prompts",
        fix_timestamp=datetime.now() - timedelta(days=10),
        commit_sha="abc123def",
        fix_pr_number=100,
        baseline_metric_value=5000.0,
        improved_metric_value=3000.0,
        fix_context={"optimization": "prompt_compression"},
    )


@pytest.fixture
def failure_fix():
    """Sample fix for failure issue."""
    return IssueFix(
        issue_id="FAIL_phase_test_1",
        issue_type=IssueType.FAILURE_MODE,
        phase_id="phase_test",
        description="Fixed timeout errors in test phase",
        fix_timestamp=datetime.now() - timedelta(days=5),
        commit_sha="xyz789",
        baseline_metric_value=15.0,
        improved_metric_value=2.0,
    )


def test_protector_initialization(temp_storage):
    """Test RegressionProtector initialization."""
    protector = RegressionProtector(
        storage_path=temp_storage,
        regression_threshold=0.20,
        lookback_window_days=60,
        min_samples_for_detection=5,
    )

    assert protector.regression_threshold == 0.20
    assert protector.lookback_window_days == 60
    assert protector.min_samples_for_detection == 5
    assert len(protector.fixes) == 0
    assert len(protector.regressions) == 0


def test_record_fix(protector, token_fix):
    """Test recording a fix."""
    protector.record_fix(token_fix)

    assert len(protector.fixes) == 1
    assert "COST_phase_build_1" in protector.fixes
    assert protector.fixes["COST_phase_build_1"].description == token_fix.description


def test_record_multiple_fixes(protector, token_fix, failure_fix):
    """Test recording multiple fixes."""
    protector.record_fix(token_fix)
    protector.record_fix(failure_fix)

    assert len(protector.fixes) == 2
    assert "COST_phase_build_1" in protector.fixes
    assert "FAIL_phase_test_1" in protector.fixes


def test_no_regression_when_metrics_stable(protector, token_fix):
    """Test that no regression is detected when metrics are stable."""
    protector.record_fix(token_fix)

    # Metrics still good (close to improved value)
    current_metrics = {"phase_build": {"token_usage": 3100.0}}

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 0


def test_detect_critical_regression(protector, token_fix):
    """Test detection of critical regression (back to baseline)."""
    protector.record_fix(token_fix)

    # Metrics regressed to baseline level
    current_metrics = {"phase_build": {"token_usage": 4900.0}}

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 1

    regression = regressions[0]
    assert regression.severity == RegressionSeverity.CRITICAL
    assert regression.original_fix.issue_id == "COST_phase_build_1"
    assert regression.current_metric_value == 4900.0
    assert regression.confidence > 0.8


def test_detect_high_regression(protector, token_fix):
    """Test detection of high severity regression."""
    protector.record_fix(token_fix)

    # Metrics degraded significantly (>50% from improved)
    current_metrics = {"phase_build": {"token_usage": 4600.0}}  # 53% degradation

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 1

    regression = regressions[0]
    assert regression.severity == RegressionSeverity.HIGH
    assert len(regression.evidence) > 0
    assert len(regression.recommendations) > 0


def test_detect_medium_regression(protector, token_fix):
    """Test detection of medium severity regression."""
    protector.record_fix(token_fix)

    # Metrics degraded moderately (25-50% from improved)
    current_metrics = {"phase_build": {"token_usage": 3900.0}}  # 30% degradation

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 1

    regression = regressions[0]
    assert regression.severity == RegressionSeverity.MEDIUM


def test_detect_low_regression(protector, token_fix):
    """Test detection of low severity regression."""
    protector.record_fix(token_fix)

    # Metrics degraded slightly (15-25% from improved)
    current_metrics = {"phase_build": {"token_usage": 3500.0}}  # 16.7% degradation

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 1

    regression = regressions[0]
    assert regression.severity == RegressionSeverity.LOW


def test_regression_evidence_includes_context(protector, token_fix):
    """Test that regression evidence includes helpful context."""
    protector.record_fix(token_fix)

    current_metrics = {"phase_build": {"token_usage": 4500.0}}
    regressions = protector.check_for_regressions(current_metrics)

    regression = regressions[0]
    evidence_text = " ".join(regression.evidence)

    assert "degraded" in evidence_text.lower()
    assert "5000" in evidence_text  # Baseline value formatted as integer
    assert "3000" in evidence_text  # Improved value formatted as integer
    assert token_fix.commit_sha in evidence_text


def test_regression_recommendations_actionable(protector, token_fix):
    """Test that regression recommendations are actionable."""
    protector.record_fix(token_fix)

    current_metrics = {"phase_build": {"token_usage": 4500.0}}
    regressions = protector.check_for_regressions(current_metrics)

    regression = regressions[0]
    recs_text = " ".join(regression.recommendations).lower()

    assert "investigate" in recs_text or "review" in recs_text or "revert" in recs_text
    assert token_fix.commit_sha in " ".join(regression.recommendations)
    assert "a-b validation" in recs_text


def test_no_regression_for_old_fixes(protector, token_fix):
    """Test that old fixes outside lookback window are not checked."""
    # Make fix very old (beyond lookback window)
    old_fix = IssueFix(
        issue_id="COST_old_phase_1",
        issue_type=IssueType.COST_SINK,
        phase_id="phase_old",
        description="Old fix",
        fix_timestamp=datetime.now() - timedelta(days=100),  # Older than 90-day window
        baseline_metric_value=1000.0,
        improved_metric_value=500.0,
    )

    protector.record_fix(old_fix)

    # Metrics regressed significantly
    current_metrics = {"phase_old": {"token_usage": 950.0}}

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 0  # Old fix ignored


def test_multiple_regressions_detected(protector, token_fix, failure_fix):
    """Test detecting multiple regressions at once."""
    protector.record_fix(token_fix)
    protector.record_fix(failure_fix)

    current_metrics = {
        "phase_build": {"token_usage": 4500.0},  # Regressed
        "phase_test": {"failure_count": 12.0},  # Regressed
    }

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 2

    regression_ids = {r.original_fix.issue_id for r in regressions}
    assert "COST_phase_build_1" in regression_ids
    assert "FAIL_phase_test_1" in regression_ids


def test_fix_stability_report_all_stable(protector, token_fix, failure_fix):
    """Test fix stability report when all fixes are stable."""
    protector.record_fix(token_fix)
    protector.record_fix(failure_fix)

    # No regressions
    current_metrics = {
        "phase_build": {"token_usage": 3000.0},
        "phase_test": {"failure_count": 2.0},
    }
    protector.check_for_regressions(current_metrics)

    report = protector.get_fix_stability_report()

    assert report.total_fixes == 2
    assert report.stable_fixes == 2
    assert report.regressed_fixes == 0
    assert report.stability_rate == 1.0


def test_fix_stability_report_with_regressions(protector, token_fix, failure_fix):
    """Test fix stability report with some regressions."""
    protector.record_fix(token_fix)
    protector.record_fix(failure_fix)

    # One regressed, one stable
    current_metrics = {
        "phase_build": {"token_usage": 4500.0},  # Regressed
        "phase_test": {"failure_count": 2.0},  # Stable
    }
    protector.check_for_regressions(current_metrics)

    report = protector.get_fix_stability_report()

    assert report.total_fixes == 2
    assert report.stable_fixes == 1
    assert report.regressed_fixes == 1
    assert report.stability_rate == 0.5


def test_fix_stability_report_identifies_unstable_phases(protector):
    """Test that stability report identifies most unstable phases."""
    # Create multiple fixes and regressions for same phase
    for i in range(3):
        fix = IssueFix(
            issue_id=f"COST_phase_build_{i}",
            issue_type=IssueType.COST_SINK,
            phase_id="phase_build",
            description=f"Fix {i}",
            fix_timestamp=datetime.now() - timedelta(days=i + 1),
            baseline_metric_value=5000.0,
            improved_metric_value=3000.0,
        )
        protector.record_fix(fix)

    # All regressed
    current_metrics = {"phase_build": {"token_usage": 4500.0}}
    protector.check_for_regressions(current_metrics)

    report = protector.get_fix_stability_report()

    assert "phase_build" in report.most_unstable_phases
    assert len(report.recommendations) > 0


def test_clear_old_fixes(protector):
    """Test clearing old fix records."""
    # Add old fix
    old_fix = IssueFix(
        issue_id="OLD_FIX",
        issue_type=IssueType.COST_SINK,
        phase_id="phase_old",
        description="Old fix to be cleared",
        fix_timestamp=datetime.now() - timedelta(days=200),
        baseline_metric_value=1000.0,
        improved_metric_value=500.0,
    )
    protector.record_fix(old_fix)

    # Add recent fix
    recent_fix = IssueFix(
        issue_id="RECENT_FIX",
        issue_type=IssueType.COST_SINK,
        phase_id="phase_recent",
        description="Recent fix to be kept",
        fix_timestamp=datetime.now() - timedelta(days=10),
        baseline_metric_value=1000.0,
        improved_metric_value=500.0,
    )
    protector.record_fix(recent_fix)

    assert len(protector.fixes) == 2

    # Clear fixes older than 180 days
    cleared_count = protector.clear_old_fixes(days=180)

    assert cleared_count == 1
    assert len(protector.fixes) == 1
    assert "RECENT_FIX" in protector.fixes
    assert "OLD_FIX" not in protector.fixes


def test_persistence_saves_and_loads_fixes(protector, token_fix, temp_storage):
    """Test that fixes are persisted to storage and loaded back."""
    protector.record_fix(token_fix)

    # Verify saved to disk
    assert Path(temp_storage).exists()

    # Create new protector instance with same storage
    new_protector = RegressionProtector(storage_path=temp_storage)

    # Should load the fix
    assert len(new_protector.fixes) == 1
    assert "COST_phase_build_1" in new_protector.fixes
    loaded_fix = new_protector.fixes["COST_phase_build_1"]
    assert loaded_fix.description == token_fix.description
    assert loaded_fix.commit_sha == token_fix.commit_sha


def test_persistence_saves_and_loads_regressions(protector, token_fix, temp_storage):
    """Test that regressions are persisted and loaded back."""
    protector.record_fix(token_fix)

    # Trigger regression
    current_metrics = {"phase_build": {"token_usage": 4500.0}}
    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 1

    # Create new protector instance
    new_protector = RegressionProtector(storage_path=temp_storage)

    # Should load both fix and regression
    assert len(new_protector.fixes) == 1
    assert len(new_protector.regressions) == 1

    loaded_regression = list(new_protector.regressions.values())[0]
    assert loaded_regression.severity == RegressionSeverity.HIGH
    assert loaded_regression.original_fix.issue_id == "COST_phase_build_1"


def test_metric_name_mapping():
    """Test that issue types map to correct metric names."""
    protector = RegressionProtector()

    assert protector._get_metric_name_for_issue_type(IssueType.COST_SINK) == "token_usage"
    assert protector._get_metric_name_for_issue_type(IssueType.FAILURE_MODE) == "failure_count"
    assert protector._get_metric_name_for_issue_type(IssueType.RETRY_CAUSE) == "retry_count"
    assert protector._get_metric_name_for_issue_type(IssueType.PERFORMANCE) == "duration_ms"
    assert protector._get_metric_name_for_issue_type(IssueType.QUALITY) == "quality_score"


def test_no_regression_when_phase_not_in_metrics(protector, token_fix):
    """Test that missing phase in metrics doesn't cause errors."""
    protector.record_fix(token_fix)

    # Metrics don't include phase_build
    current_metrics = {"other_phase": {"token_usage": 5000.0}}

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 0


def test_no_regression_when_metric_not_in_phase_metrics(protector, token_fix):
    """Test that missing metric in phase doesn't cause errors."""
    protector.record_fix(token_fix)

    # Phase exists but doesn't have token_usage metric
    current_metrics = {"phase_build": {"other_metric": 5000.0}}

    regressions = protector.check_for_regressions(current_metrics)
    assert len(regressions) == 0


def test_regression_with_pr_number_in_recommendations(protector):
    """Test that PR number is included in recommendations when available."""
    fix_with_pr = IssueFix(
        issue_id="FIX_WITH_PR",
        issue_type=IssueType.COST_SINK,
        phase_id="phase_x",
        description="Fix with PR",
        fix_timestamp=datetime.now() - timedelta(days=5),
        fix_pr_number=123,
        baseline_metric_value=1000.0,
        improved_metric_value=500.0,
    )
    protector.record_fix(fix_with_pr)

    current_metrics = {"phase_x": {"token_usage": 900.0}}
    regressions = protector.check_for_regressions(current_metrics)

    assert len(regressions) == 1
    recs_text = " ".join(regressions[0].recommendations)
    assert "#123" in recs_text or "123" in recs_text


def test_stability_report_recommendations_for_low_stability(protector):
    """Test that stability report includes recommendations when stability is low."""
    # Create multiple regressed fixes
    for i in range(5):
        fix = IssueFix(
            issue_id=f"FIX_{i}",
            issue_type=IssueType.COST_SINK,
            phase_id=f"phase_{i}",
            description=f"Fix {i}",
            fix_timestamp=datetime.now() - timedelta(days=i + 1),
            baseline_metric_value=1000.0,
            improved_metric_value=500.0,
        )
        protector.record_fix(fix)

    # Regress 4 out of 5 (80% regression rate, 20% stability)
    for i in range(4):
        current_metrics = {f"phase_{i}": {"token_usage": 900.0}}
        protector.check_for_regressions(current_metrics)

    report = protector.get_fix_stability_report()

    assert report.stability_rate < 0.7
    assert len(report.recommendations) > 0
    recs_text = " ".join(report.recommendations).lower()
    assert "stability" in recs_text or "quality" in recs_text or "testing" in recs_text
