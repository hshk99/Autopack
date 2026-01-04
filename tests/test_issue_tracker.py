"""Unit tests for issue tracking system (Chunk B)"""


import pytest

from autopack.issue_tracker import IssueTracker


@pytest.fixture
def issue_tracker(tmp_path):
    """Create an IssueTracker instance with temp directory"""
    tracker = IssueTracker(run_id="test-run-001", project_id="TestProject", base_dir=tmp_path)
    return tracker


def test_phase_issue_creation(issue_tracker, tmp_path):
    """Test creating and loading phase issue file"""
    # Record an issue
    phase_file, run_index, backlog = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="test_failure__missing_assert",
        severity="minor",
        source="test",
        category="test_failure",
        task_category="feature_scaffolding",
        complexity="low",
        evidence_refs=["tests/test_foo.py::test_bar"],
    )

    # Verify phase file was created
    assert phase_file.phase_id == "F1.1"
    assert phase_file.tier_id == "T1"
    assert len(phase_file.issues) == 1
    assert phase_file.minor_issue_count == 1
    assert phase_file.major_issue_count == 0
    assert phase_file.issue_state == "has_minor_issues"

    # Verify file exists on disk
    path = issue_tracker.get_phase_issue_path(0, "F1.1")
    assert path.exists()

    # Reload and verify
    reloaded = issue_tracker.load_phase_issues(0, "F1.1")
    assert len(reloaded.issues) == 1
    assert reloaded.issues[0].issue_key == "test_failure__missing_assert"


def test_issue_deduplication_in_phase(issue_tracker):
    """Test that same issue in same phase increments occurrence count"""
    # Record same issue twice
    phase_file1, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="duplicate_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    phase_file2, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="duplicate_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Should still have only 1 distinct issue
    assert len(phase_file2.issues) == 1
    assert phase_file2.issues[0].occurrence_count == 2
    assert phase_file2.minor_issue_count == 1  # Distinct count, not occurrences


def test_run_issue_index(issue_tracker):
    """Test run-level issue index tracks issues across phases"""
    # Record issue in phase 0
    _, run_index1, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="cross_phase_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Record same issue in phase 1
    _, run_index2, _ = issue_tracker.record_issue(
        phase_index=1,
        phase_id="F1.2",
        tier_id="T1",
        issue_key="cross_phase_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Verify de-duplication
    assert "cross_phase_issue" in run_index2.issues_by_key
    entry = run_index2.issues_by_key["cross_phase_issue"]
    assert entry.first_phase_index == 0
    assert entry.last_phase_index == 1
    assert entry.occurrence_count == 2
    assert "F1.1" in entry.seen_in_phases
    assert "F1.2" in entry.seen_in_phases


def test_run_issue_index_multiple_tiers(issue_tracker):
    """Test run index tracks issues across tiers"""
    # Issue in tier 1
    _, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="multi_tier_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Same issue in tier 2
    _, run_index, _ = issue_tracker.record_issue(
        phase_index=1,
        phase_id="F2.1",
        tier_id="T2",
        issue_key="multi_tier_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    entry = run_index.issues_by_key["multi_tier_issue"]
    assert "T1" in entry.seen_in_tiers
    assert "T2" in entry.seen_in_tiers


def test_project_backlog_aging(issue_tracker, tmp_path):
    """Test project backlog tracks aging across runs"""
    # Record issue
    _, _, backlog1 = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="aging_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Verify initial state
    assert "aging_issue" in backlog1.issues_by_key
    entry = backlog1.issues_by_key["aging_issue"]
    assert entry.age_in_runs == 1
    assert entry.age_in_tiers == 1
    assert entry.status == "open"

    # Simulate another run with same issue (use same tmp_path for isolation)
    tracker2 = IssueTracker(run_id="test-run-002", project_id="TestProject", base_dir=tmp_path)
    _, _, backlog2 = tracker2.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="aging_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Verify aging incremented
    entry2 = backlog2.issues_by_key["aging_issue"]
    assert entry2.age_in_runs == 2
    assert entry2.age_in_tiers == 2


def test_aging_triggers_needs_cleanup(tmp_path):
    """Test that aged issues get marked as needs_cleanup"""
    issue_key = "old_minor_issue"

    # Simulate 3 runs with same minor issue (threshold is 3)
    for run_num in range(1, 4):
        tracker = IssueTracker(run_id=f"test-run-{run_num:03d}", project_id="TestProject", base_dir=tmp_path)
        _, _, backlog = tracker.record_issue(
            phase_index=0,
            phase_id="F1.1",
            tier_id="T1",
            issue_key=issue_key,
            severity="minor",
            source="test",
            category="test_failure",
        )

    # After 3 runs, should be marked for cleanup
    entry = backlog.issues_by_key[issue_key]
    assert entry.age_in_runs == 3
    assert entry.status == "needs_cleanup"


def test_major_issue_doesnt_age(issue_tracker):
    """Test that major issues are not subject to aging rules"""
    _, _, backlog = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="major_issue",
        severity="major",
        source="test",
        category="schema_contract_change",
    )

    # Major issues don't get aging status changes
    entry = backlog.issues_by_key["major_issue"]
    assert entry.base_severity == "major"
    assert entry.status == "open"  # Not needs_cleanup


def test_phase_issue_state(issue_tracker):
    """Test phase issue state is correctly set"""
    # No issues
    phase_file0 = issue_tracker.load_phase_issues(0, "F1.1")
    assert phase_file0.issue_state == "no_issues"

    # Minor issue
    phase_file1, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="minor_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )
    assert phase_file1.issue_state == "has_minor_issues"

    # Major issue (should override)
    phase_file2, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="major_issue",
        severity="major",
        source="test",
        category="schema_contract_change",
    )
    assert phase_file2.issue_state == "has_major_issues"


def test_issue_evidence_refs(issue_tracker):
    """Test that evidence references are stored"""
    evidence = ["tests/test_foo.py::test_bar", "tests/test_baz.py::test_qux"]

    phase_file, _, _ = issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="issue_with_evidence",
        severity="minor",
        source="test",
        category="test_failure",
        evidence_refs=evidence,
    )

    issue = phase_file.issues[0]
    assert issue.evidence_refs == evidence


def test_multiple_issues_in_phase(issue_tracker):
    """Test multiple distinct issues in same phase"""
    # Record 3 different issues
    for i in range(3):
        issue_tracker.record_issue(
            phase_index=0,
            phase_id="F1.1",
            tier_id="T1",
            issue_key=f"issue_{i}",
            severity="minor",
            source="test",
            category="test_failure",
        )

    phase_file = issue_tracker.load_phase_issues(0, "F1.1")
    assert len(phase_file.issues) == 3
    assert phase_file.minor_issue_count == 3


def test_project_backlog_persistence(issue_tracker, tmp_path):
    """Test project backlog persists across tracker instances"""
    # Record issue with first tracker
    issue_tracker.record_issue(
        phase_index=0,
        phase_id="F1.1",
        tier_id="T1",
        issue_key="persistent_issue",
        severity="minor",
        source="test",
        category="test_failure",
    )

    # Create new tracker instance with same base_dir
    tracker2 = IssueTracker(run_id="test-run-002", project_id="TestProject", base_dir=tmp_path)

    # Load backlog - should contain issue from first tracker
    backlog = tracker2.load_project_backlog()
    assert "persistent_issue" in backlog.issues_by_key
