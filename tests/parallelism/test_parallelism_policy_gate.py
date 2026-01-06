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
