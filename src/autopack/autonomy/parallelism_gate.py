"""Parallelism policy gate enforcer - blocks parallel execution unless explicitly allowed.

Per IMPLEMENTATION_PLAN_PIVOT_INTENTIONS_AUTONOMY_PARALLELISM.md Phase 5:
- If IntentionAnchorV2.parallelism_policy.allowed != true, block parallel execution
- Ensures safe multi-run execution without workspace contamination

This gate is checked before spawning parallel runs to prevent:
- Git state corruption
- Workspace artifact pollution
- Run-to-run interference
"""

import logging
from pathlib import Path

from ..intention_anchor.v2 import IntentionAnchorV2

logger = logging.getLogger(__name__)


class ParallelismPolicyViolation(Exception):
    """Raised when parallel execution is attempted but not allowed by intention anchor."""

    pass


class ParallelismPolicyGate:
    """Enforces parallelism policy from IntentionAnchorV2.

    Attributes:
        anchor: Intention anchor v2 with parallelism policy
    """

    def __init__(self, anchor: IntentionAnchorV2):
        """Initialize parallelism policy gate.

        Args:
            anchor: Intention anchor v2 with parallelism policy
        """
        self.anchor = anchor

    def check_parallel_allowed(self, requested_runs: int = 2) -> None:
        """Check if parallel execution is allowed.

        Args:
            requested_runs: Number of runs requested to execute in parallel (default: 2)

        Raises:
            ParallelismPolicyViolation: If parallel execution is not allowed
        """
        # Check if parallelism intention exists
        if not self.anchor.pivot_intentions.parallelism_isolation:
            raise ParallelismPolicyViolation(
                "Parallelism policy not defined in intention anchor. "
                "Add parallelism_isolation with allowed=true to enable parallel execution."
            )

        policy = self.anchor.pivot_intentions.parallelism_isolation

        # Check if parallelism is explicitly allowed
        if not policy.allowed:
            raise ParallelismPolicyViolation(
                f"Parallel execution is blocked by intention anchor policy "
                f"(parallelism_isolation.allowed={policy.allowed}). "
                "Set parallelism_isolation.allowed=true to enable parallel runs."
            )

        # Check if requested runs exceed max_concurrent_runs
        if requested_runs > policy.max_concurrent_runs:
            raise ParallelismPolicyViolation(
                f"Requested {requested_runs} parallel runs exceeds "
                f"max_concurrent_runs={policy.max_concurrent_runs} from intention anchor. "
                f"Reduce parallel runs or increase max_concurrent_runs in parallelism_isolation."
            )

        # Check isolation model
        if policy.isolation_model != "four_layer":
            logger.warning(
                f"[ParallelismGate] Parallelism allowed but isolation_model={policy.isolation_model}. "
                "Recommend using isolation_model='four_layer' for safe parallel execution."
            )

        logger.info(
            f"[ParallelismGate] Parallel execution allowed: "
            f"max_concurrent_runs={policy.max_concurrent_runs}, "
            f"isolation_model={policy.isolation_model}"
        )

    def get_max_concurrent_runs(self) -> int:
        """Get max concurrent runs from parallelism policy.

        Returns:
            Max concurrent runs allowed (default: 1 if parallelism not allowed)
        """
        if not self.anchor.pivot_intentions.parallelism_isolation:
            return 1

        policy = self.anchor.pivot_intentions.parallelism_isolation
        if not policy.allowed:
            return 1

        return policy.max_concurrent_runs

    def is_parallel_allowed(self) -> bool:
        """Check if parallel execution is allowed (non-raising).

        Returns:
            True if parallel execution is allowed, False otherwise
        """
        if not self.anchor.pivot_intentions.parallelism_isolation:
            return False

        return self.anchor.pivot_intentions.parallelism_isolation.allowed


def check_parallelism_policy(anchor: IntentionAnchorV2, requested_runs: int = 2) -> None:
    """Check parallelism policy and raise if not allowed (convenience function).

    Args:
        anchor: Intention anchor v2 with parallelism policy
        requested_runs: Number of runs requested to execute in parallel

    Raises:
        ParallelismPolicyViolation: If parallel execution is not allowed
    """
    gate = ParallelismPolicyGate(anchor)
    gate.check_parallel_allowed(requested_runs)


def load_and_check_parallelism_policy(
    anchor_path: Path, requested_runs: int = 2
) -> IntentionAnchorV2:
    """Load intention anchor and check parallelism policy (convenience function).

    Args:
        anchor_path: Path to intention anchor v2 JSON file
        requested_runs: Number of runs requested to execute in parallel

    Returns:
        Loaded intention anchor v2

    Raises:
        ParallelismPolicyViolation: If parallel execution is not allowed
        FileNotFoundError: If anchor file not found
    """
    anchor = IntentionAnchorV2.load_from_file(anchor_path)
    check_parallelism_policy(anchor, requested_runs)
    return anchor
