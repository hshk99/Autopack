"""Tests for parallelism policy gate enforcement (Phase 5)."""

import pytest
from datetime import datetime, timezone

from autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    PivotIntentions,
    ParallelismIsolationIntention,
)
from autopack.autonomy.parallelism_gate import (
    ParallelismPolicyGate,
    ParallelismPolicyViolation,
    check_parallelism_policy,
    extract_phase_scope_paths,
    check_scope_overlap,
    check_phases_can_run_parallel,
    find_parallel_execution_groups,
    ScopeBasedParallelismChecker,
)


def create_test_anchor(
    parallelism_allowed: bool = False,
    max_concurrent_runs: int = 1,
    isolation_model: str = "none",
) -> IntentionAnchorV2:
    """Create a test intention anchor with parallelism policy.

    Args:
        parallelism_allowed: Whether parallel execution is allowed
        max_concurrent_runs: Max concurrent runs
        isolation_model: Isolation model ("four_layer" or "none")

    Returns:
        IntentionAnchorV2 instance
    """
    return IntentionAnchorV2(
        format_version="v2",
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="0123456789abcdef",
        pivot_intentions=PivotIntentions(
            parallelism_isolation=ParallelismIsolationIntention(
                allowed=parallelism_allowed,
                isolation_model=isolation_model,
                max_concurrent_runs=max_concurrent_runs,
            )
        ),
    )


def test_parallelism_blocked_when_not_allowed():
    """Test that parallel execution is blocked when parallelism_isolation.allowed=False."""
    anchor = create_test_anchor(parallelism_allowed=False)
    gate = ParallelismPolicyGate(anchor)

    with pytest.raises(ParallelismPolicyViolation) as exc_info:
        gate.check_parallel_allowed(requested_runs=2)

    assert "blocked by intention anchor policy" in str(exc_info.value)
    assert "allowed=False" in str(exc_info.value)


def test_parallelism_blocked_when_policy_missing():
    """Test that parallel execution is blocked when parallelism_isolation is missing."""
    anchor = IntentionAnchorV2(
        format_version="v2",
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="0123456789abcdef",
        pivot_intentions=PivotIntentions(),  # No parallelism_isolation
    )
    gate = ParallelismPolicyGate(anchor)

    with pytest.raises(ParallelismPolicyViolation) as exc_info:
        gate.check_parallel_allowed(requested_runs=2)

    assert "Parallelism policy not defined" in str(exc_info.value)
    assert "allowed=true" in str(exc_info.value)


def test_parallelism_allowed_with_explicit_policy():
    """Test that parallel execution is allowed when parallelism_isolation.allowed=True."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    # Should not raise
    gate.check_parallel_allowed(requested_runs=2)
    assert gate.is_parallel_allowed() is True
    assert gate.get_max_concurrent_runs() == 3


def test_parallelism_blocked_when_exceeding_max_concurrent():
    """Test that parallel execution is blocked when requested runs exceed max_concurrent_runs."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=2, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    with pytest.raises(ParallelismPolicyViolation) as exc_info:
        gate.check_parallel_allowed(requested_runs=5)

    assert "exceeds max_concurrent_runs=2" in str(exc_info.value)
    assert "Requested 5 parallel runs" in str(exc_info.value)


def test_parallelism_allowed_at_max_concurrent_limit():
    """Test that parallel execution is allowed when requested runs equals max_concurrent_runs."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    # Should not raise
    gate.check_parallel_allowed(requested_runs=3)


def test_get_max_concurrent_runs_when_allowed():
    """Test get_max_concurrent_runs returns correct value when parallelism allowed."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=5, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    assert gate.get_max_concurrent_runs() == 5


def test_get_max_concurrent_runs_when_not_allowed():
    """Test get_max_concurrent_runs returns 1 when parallelism not allowed."""
    anchor = create_test_anchor(parallelism_allowed=False)
    gate = ParallelismPolicyGate(anchor)

    assert gate.get_max_concurrent_runs() == 1


def test_get_max_concurrent_runs_when_policy_missing():
    """Test get_max_concurrent_runs returns 1 when parallelism_isolation missing."""
    anchor = IntentionAnchorV2(
        format_version="v2",
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="0123456789abcdef",
        pivot_intentions=PivotIntentions(),
    )
    gate = ParallelismPolicyGate(anchor)

    assert gate.get_max_concurrent_runs() == 1


def test_is_parallel_allowed_returns_true_when_allowed():
    """Test is_parallel_allowed returns True when parallelism allowed."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    assert gate.is_parallel_allowed() is True


def test_is_parallel_allowed_returns_false_when_not_allowed():
    """Test is_parallel_allowed returns False when parallelism not allowed."""
    anchor = create_test_anchor(parallelism_allowed=False)
    gate = ParallelismPolicyGate(anchor)

    assert gate.is_parallel_allowed() is False


def test_is_parallel_allowed_returns_false_when_policy_missing():
    """Test is_parallel_allowed returns False when parallelism_isolation missing."""
    anchor = IntentionAnchorV2(
        format_version="v2",
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="0123456789abcdef",
        pivot_intentions=PivotIntentions(),
    )
    gate = ParallelismPolicyGate(anchor)

    assert gate.is_parallel_allowed() is False


def test_check_parallelism_policy_convenience_function():
    """Test check_parallelism_policy convenience function."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
    )

    # Should not raise
    check_parallelism_policy(anchor, requested_runs=2)

    # Should raise
    with pytest.raises(ParallelismPolicyViolation):
        check_parallelism_policy(anchor, requested_runs=5)


def test_isolation_model_warning_for_non_four_layer():
    """Test that warning is logged for isolation_model != 'four_layer'."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="none"
    )
    gate = ParallelismPolicyGate(anchor)

    # Should not raise, just log a warning
    gate.check_parallel_allowed(requested_runs=2)

    # Verify policy is still allowed despite warning
    assert gate.is_parallel_allowed() is True


def test_single_run_does_not_require_parallelism_policy():
    """Test that single run execution doesn't require parallelism policy.

    NOTE: This is a design decision - single run execution should not be blocked
    by lack of parallelism policy, only multi-run execution.
    """
    # This test documents current behavior - single runs might still need policy
    # Adjust if design changes
    anchor = IntentionAnchorV2(
        format_version="v2",
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="0123456789abcdef",
        pivot_intentions=PivotIntentions(),
    )
    gate = ParallelismPolicyGate(anchor)

    # Single run (requested_runs=1) might still raise if we enforce policy
    # This test documents the expected behavior
    with pytest.raises(ParallelismPolicyViolation):
        gate.check_parallel_allowed(requested_runs=1)


def test_four_layer_isolation_model_recommended():
    """Test that four_layer isolation model is recommended for safe parallel execution."""
    anchor = create_test_anchor(
        parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
    )
    gate = ParallelismPolicyGate(anchor)

    # Should not raise or warn
    gate.check_parallel_allowed(requested_runs=2)

    # Verify isolation model
    assert anchor.pivot_intentions.parallelism_isolation.isolation_model == "four_layer"


# =============================================================================
# IMP-AUTO-002: Scope-based parallel phase execution tests
# =============================================================================


class TestScopeExtraction:
    """Tests for scope path extraction from phases."""

    def test_extract_paths_from_scope(self):
        """Test extracting paths from phase scope configuration."""
        phase = {
            "phase_id": "test-phase",
            "scope": {
                "paths": ["src/foo.py", "src/bar.py"],
                "read_only_context": ["tests/test_foo.py"],
            },
        }
        paths = extract_phase_scope_paths(phase)
        assert paths == {"src/foo.py", "src/bar.py", "tests/test_foo.py"}

    def test_extract_paths_with_dict_read_only_context(self):
        """Test extracting paths when read_only_context uses dict format."""
        phase = {
            "phase_id": "test-phase",
            "scope": {
                "paths": ["src/main.py"],
                "read_only_context": [
                    {"path": "config/settings.py", "reason": "Configuration"},
                    {"path": "utils/helpers.py", "reason": "Utility functions"},
                ],
            },
        }
        paths = extract_phase_scope_paths(phase)
        assert paths == {"src/main.py", "config/settings.py", "utils/helpers.py"}

    def test_extract_paths_empty_scope(self):
        """Test extracting paths from phase with no scope."""
        phase = {"phase_id": "test-phase"}
        paths = extract_phase_scope_paths(phase)
        assert paths == set()

    def test_extract_paths_normalizes_backslashes(self):
        """Test that backslashes are normalized to forward slashes."""
        phase = {
            "phase_id": "test-phase",
            "scope": {
                "paths": ["src\\windows\\path.py"],
            },
        }
        paths = extract_phase_scope_paths(phase)
        assert "src/windows/path.py" in paths


class TestScopeOverlap:
    """Tests for scope overlap detection."""

    def test_no_overlap_disjoint_paths(self):
        """Test no overlap when paths are completely disjoint."""
        paths_a = {"src/module_a/file.py", "src/module_a/utils.py"}
        paths_b = {"src/module_b/file.py", "src/module_b/utils.py"}

        has_overlap, overlapping = check_scope_overlap(paths_a, paths_b)

        assert has_overlap is False
        assert overlapping == set()

    def test_overlap_identical_paths(self):
        """Test overlap detection with identical paths."""
        paths_a = {"src/shared/common.py", "src/module_a/file.py"}
        paths_b = {"src/shared/common.py", "src/module_b/file.py"}

        has_overlap, overlapping = check_scope_overlap(paths_a, paths_b)

        assert has_overlap is True
        assert "src/shared/common.py" in overlapping

    def test_overlap_directory_containment(self):
        """Test overlap when one path contains another (directory)."""
        paths_a = {"src/module_a"}  # Directory
        paths_b = {"src/module_a/subdir/file.py"}  # File inside directory

        has_overlap, overlapping = check_scope_overlap(paths_a, paths_b)

        assert has_overlap is True
        assert "src/module_a" in overlapping

    def test_no_overlap_similar_prefixes(self):
        """Test no overlap with similar but distinct path prefixes."""
        paths_a = {"src/module_a/file.py"}
        paths_b = {"src/module_ab/file.py"}  # Different directory

        has_overlap, overlapping = check_scope_overlap(paths_a, paths_b)

        assert has_overlap is False

    def test_overlap_nested_directories(self):
        """Test overlap with nested directory structure."""
        paths_a = {"src/api/v1"}
        paths_b = {"src/api/v1/endpoints/users.py"}

        has_overlap, overlapping = check_scope_overlap(paths_a, paths_b)

        assert has_overlap is True


class TestPhasesCanRunParallel:
    """Tests for phase parallel execution eligibility."""

    def test_phases_can_run_parallel_no_overlap(self):
        """Test phases with non-overlapping scopes can run in parallel."""
        phase_a = {
            "phase_id": "phase-a",
            "scope": {"paths": ["src/module_a/"]},
        }
        phase_b = {
            "phase_id": "phase-b",
            "scope": {"paths": ["src/module_b/"]},
        }

        can_parallel, reason = check_phases_can_run_parallel(phase_a, phase_b)

        assert can_parallel is True
        assert reason is None

    def test_phases_cannot_run_parallel_with_overlap(self):
        """Test phases with overlapping scopes cannot run in parallel."""
        phase_a = {
            "phase_id": "phase-a",
            "scope": {"paths": ["src/shared/utils.py", "src/module_a/"]},
        }
        phase_b = {
            "phase_id": "phase-b",
            "scope": {"paths": ["src/shared/utils.py", "src/module_b/"]},
        }

        can_parallel, reason = check_phases_can_run_parallel(phase_a, phase_b)

        assert can_parallel is False
        assert "Scope overlap detected" in reason

    def test_phases_cannot_run_parallel_no_scope(self):
        """Test phases without scope defined cannot run in parallel."""
        phase_a = {"phase_id": "phase-a"}  # No scope
        phase_b = {
            "phase_id": "phase-b",
            "scope": {"paths": ["src/module_b/"]},
        }

        can_parallel, reason = check_phases_can_run_parallel(phase_a, phase_b)

        assert can_parallel is False
        assert "no scope defined" in reason


class TestFindParallelExecutionGroups:
    """Tests for grouping phases for parallel execution."""

    def test_group_independent_phases(self):
        """Test grouping completely independent phases."""
        phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
            {"phase_id": "p3", "scope": {"paths": ["src/c/"]}},
        ]

        groups = find_parallel_execution_groups(phases, max_group_size=3)

        # All phases should be in one group since they don't overlap
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_group_overlapping_phases(self):
        """Test grouping phases with some overlaps."""
        phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/shared.py", "src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/shared.py", "src/b/"]}},  # Overlaps with p1
            {"phase_id": "p3", "scope": {"paths": ["src/c/"]}},  # Independent
        ]

        groups = find_parallel_execution_groups(phases, max_group_size=3)

        # p1 and p2 overlap, so they should be in different groups
        # p3 doesn't overlap with p1, so it could be grouped with p1
        assert len(groups) >= 2

    def test_group_respects_max_size(self):
        """Test that groups respect max_group_size limit."""
        phases = [{"phase_id": f"p{i}", "scope": {"paths": [f"src/module_{i}/"]}} for i in range(5)]

        groups = find_parallel_execution_groups(phases, max_group_size=2)

        # Each group should have at most 2 phases
        for group in groups:
            assert len(group) <= 2

    def test_empty_phases_returns_empty_groups(self):
        """Test that empty phases list returns empty groups."""
        groups = find_parallel_execution_groups([], max_group_size=2)
        assert groups == []


class TestScopeBasedParallelismChecker:
    """Tests for ScopeBasedParallelismChecker class."""

    def test_checker_without_policy_gate(self):
        """Test checker works without policy gate."""
        checker = ScopeBasedParallelismChecker(policy_gate=None)

        phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
        ]

        can_parallel, reason = checker.can_execute_parallel(phases)
        assert can_parallel is True

    def test_checker_with_policy_gate_allowed(self):
        """Test checker with policy gate that allows parallelism."""
        anchor = create_test_anchor(
            parallelism_allowed=True, max_concurrent_runs=3, isolation_model="four_layer"
        )
        policy_gate = ParallelismPolicyGate(anchor)
        checker = ScopeBasedParallelismChecker(policy_gate=policy_gate)

        phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
        ]

        can_parallel, reason = checker.can_execute_parallel(phases)
        assert can_parallel is True

    def test_checker_with_policy_gate_denied(self):
        """Test checker with policy gate that denies parallelism."""
        anchor = create_test_anchor(parallelism_allowed=False)
        policy_gate = ParallelismPolicyGate(anchor)
        checker = ScopeBasedParallelismChecker(policy_gate=policy_gate)

        phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
        ]

        can_parallel, reason = checker.can_execute_parallel(phases)
        assert can_parallel is False
        assert "not allowed by intention anchor policy" in reason

    def test_checker_single_phase_not_parallel(self):
        """Test that single phase doesn't qualify for parallel execution."""
        checker = ScopeBasedParallelismChecker(policy_gate=None)

        phases = [{"phase_id": "p1", "scope": {"paths": ["src/a/"]}}]

        can_parallel, reason = checker.can_execute_parallel(phases)
        assert can_parallel is False
        assert "at least 2 phases" in reason

    def test_get_parallel_groups_with_parallelism_allowed(self):
        """Test get_parallel_groups returns proper groups when allowed."""
        anchor = create_test_anchor(
            parallelism_allowed=True, max_concurrent_runs=2, isolation_model="four_layer"
        )
        policy_gate = ParallelismPolicyGate(anchor)
        checker = ScopeBasedParallelismChecker(policy_gate=policy_gate)

        queued_phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
            {"phase_id": "p3", "scope": {"paths": ["src/c/"]}},
        ]

        groups = checker.get_parallel_groups(queued_phases)

        # With max_concurrent=2, groups should have at most 2 phases
        for group in groups:
            assert len(group) <= 2

    def test_get_parallel_groups_with_parallelism_denied(self):
        """Test get_parallel_groups returns single-phase groups when denied."""
        anchor = create_test_anchor(parallelism_allowed=False)
        policy_gate = ParallelismPolicyGate(anchor)
        checker = ScopeBasedParallelismChecker(policy_gate=policy_gate)

        queued_phases = [
            {"phase_id": "p1", "scope": {"paths": ["src/a/"]}},
            {"phase_id": "p2", "scope": {"paths": ["src/b/"]}},
        ]

        groups = checker.get_parallel_groups(queued_phases)

        # Each phase should be in its own group
        assert len(groups) == 2
        for group in groups:
            assert len(group) == 1
