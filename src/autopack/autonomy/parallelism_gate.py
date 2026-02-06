"""Parallelism policy gate enforcer - blocks parallel execution unless explicitly allowed.

Per IMPLEMENTATION_PLAN_PIVOT_INTENTIONS_AUTONOMY_PARALLELISM.md Phase 5:
- If IntentionAnchorV2.parallelism_policy.allowed != true, block parallel execution
- Ensures safe multi-run execution without workspace contamination

This gate is checked before spawning parallel runs to prevent:
- Git state corruption
- Workspace artifact pollution
- Run-to-run interference

IMP-AUTO-002: Extended to support scope-based parallel phase execution:
- Phases with non-overlapping file scopes can execute concurrently
- Scope overlap detection prevents file conflicts between parallel phases
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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
        if not self.anchor or not hasattr(self.anchor, 'pivot_intentions') or not self.anchor.pivot_intentions:
            raise ParallelismPolicyViolation(
                "Intention anchor or pivot_intentions not available. "
                "Add parallelism_isolation with allowed=true to enable parallel execution."
            )

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
        if not self.anchor or not hasattr(self.anchor, 'pivot_intentions') or not self.anchor.pivot_intentions:
            return 1

        if not self.anchor.pivot_intentions.parallelism_isolation:
            return 1

        policy = self.anchor.pivot_intentions.parallelism_isolation
        if not policy or not policy.allowed:
            return 1

        return getattr(policy, 'max_concurrent_runs', 1)

    def is_parallel_allowed(self) -> bool:
        """Check if parallel execution is allowed (non-raising).

        Returns:
            True if parallel execution is allowed, False otherwise
        """
        if not self.anchor or not hasattr(self.anchor, 'pivot_intentions') or not self.anchor.pivot_intentions:
            return False

        parallelism_isolation = self.anchor.pivot_intentions.parallelism_isolation
        if not parallelism_isolation:
            return False

        return getattr(parallelism_isolation, 'allowed', False)


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


# =============================================================================
# IMP-AUTO-002: Scope-based parallel phase execution support
# =============================================================================


def extract_phase_scope_paths(phase: Dict) -> Set[str]:
    """Extract normalized file paths from a phase's scope configuration.

    Args:
        phase: Phase specification dict with optional 'scope' field

    Returns:
        Set of normalized path strings from the phase scope
    """
    scope = phase.get("scope", {})
    paths: Set[str] = set()

    # Extract paths from scope.paths (modifiable files)
    for path in scope.get("paths", []):
        if isinstance(path, str):
            paths.add(_normalize_scope_path(path))

    # Extract paths from scope.read_only_context
    for entry in scope.get("read_only_context", []):
        if isinstance(entry, str):
            paths.add(_normalize_scope_path(entry))
        elif isinstance(entry, dict) and "path" in entry:
            paths.add(_normalize_scope_path(entry["path"]))

    return paths


def _normalize_scope_path(path: str) -> str:
    """Normalize a scope path for comparison.

    Args:
        path: Raw path string

    Returns:
        Normalized path (forward slashes, no leading ./)
    """
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _get_path_components(path: str) -> List[str]:
    """Get path components for prefix matching.

    Args:
        path: Normalized path string

    Returns:
        List of path components
    """
    return [p for p in path.split("/") if p]


def check_scope_overlap(paths_a: Set[str], paths_b: Set[str]) -> Tuple[bool, Set[str]]:
    """Check if two sets of scope paths overlap.

    Two scopes overlap if:
    1. They share any identical paths
    2. One path is a prefix of another (directory contains file or subdirectory)

    Args:
        paths_a: First set of normalized scope paths
        paths_b: Second set of normalized scope paths

    Returns:
        Tuple of (has_overlap: bool, overlapping_paths: Set[str])
    """
    overlapping: Set[str] = set()

    # Check for identical paths
    identical = paths_a & paths_b
    overlapping.update(identical)

    # Check for prefix overlaps (directory containment)
    for path_a in paths_a:
        components_a = _get_path_components(path_a)
        for path_b in paths_b:
            components_b = _get_path_components(path_b)

            # Check if path_a is a prefix of path_b or vice versa
            min_len = min(len(components_a), len(components_b))
            if min_len > 0:
                # Check if shorter path is a prefix of longer path
                if components_a[:min_len] == components_b[:min_len]:
                    # One path contains or equals the other
                    overlapping.add(path_a if len(components_a) <= len(components_b) else path_b)

    has_overlap = len(overlapping) > 0
    return has_overlap, overlapping


def check_phases_can_run_parallel(phase_a: Dict, phase_b: Dict) -> Tuple[bool, Optional[str]]:
    """Check if two phases can safely run in parallel based on scope overlap.

    Args:
        phase_a: First phase specification
        phase_b: Second phase specification

    Returns:
        Tuple of (can_run_parallel: bool, reason: Optional[str])
        - If can_run_parallel is True, reason is None
        - If can_run_parallel is False, reason explains why
    """
    # Extract scope paths from both phases
    paths_a = extract_phase_scope_paths(phase_a)
    paths_b = extract_phase_scope_paths(phase_b)

    phase_id_a = phase_a.get("phase_id", "unknown")
    phase_id_b = phase_b.get("phase_id", "unknown")

    # If either phase has no scope defined, assume they could overlap (conservative)
    if not paths_a:
        return False, f"Phase {phase_id_a} has no scope defined - cannot verify isolation"
    if not paths_b:
        return False, f"Phase {phase_id_b} has no scope defined - cannot verify isolation"

    # Check for scope overlap
    has_overlap, overlapping_paths = check_scope_overlap(paths_a, paths_b)

    if has_overlap:
        overlap_sample = list(overlapping_paths)[:3]
        return False, (
            f"Scope overlap detected between phases {phase_id_a} and {phase_id_b}: {overlap_sample}"
        )

    return True, None


def find_parallel_execution_groups(phases: List[Dict], max_group_size: int = 2) -> List[List[Dict]]:
    """Group phases that can safely execute in parallel based on scope isolation.

    Uses a greedy algorithm to form groups of phases with non-overlapping scopes.

    Args:
        phases: List of phase specifications
        max_group_size: Maximum number of phases per parallel group

    Returns:
        List of phase groups, where each group contains phases that can run in parallel
    """
    if not phases:
        return []

    groups: List[List[Dict]] = []
    remaining = list(phases)

    while remaining:
        # Start a new group with the first remaining phase
        current_group = [remaining.pop(0)]
        current_group_paths = extract_phase_scope_paths(current_group[0])

        # Try to add more phases to the group
        i = 0
        while i < len(remaining) and len(current_group) < max_group_size:
            candidate = remaining[i]
            candidate_paths = extract_phase_scope_paths(candidate)

            # Check if candidate overlaps with any phase in current group
            has_overlap, _ = check_scope_overlap(current_group_paths, candidate_paths)

            if not has_overlap:
                # Add to group
                current_group.append(remaining.pop(i))
                current_group_paths.update(candidate_paths)
            else:
                i += 1

        groups.append(current_group)

    return groups


class ScopeBasedParallelismChecker:
    """Checks phase scopes to determine safe parallel execution.

    IMP-AUTO-002: Enables concurrent phase execution when file scopes don't overlap.

    Attributes:
        policy_gate: Optional ParallelismPolicyGate for policy-level checks
    """

    def __init__(self, policy_gate: Optional[ParallelismPolicyGate] = None):
        """Initialize scope-based parallelism checker.

        Args:
            policy_gate: Optional ParallelismPolicyGate for policy-level validation
        """
        self.policy_gate = policy_gate

    def can_execute_parallel(self, phases: List[Dict]) -> Tuple[bool, Optional[str]]:
        """Check if a list of phases can execute in parallel.

        Validates both policy-level permissions and scope-level isolation.

        Args:
            phases: List of phase specifications to check

        Returns:
            Tuple of (can_parallel: bool, reason: Optional[str])
        """
        if len(phases) < 2:
            return False, "Need at least 2 phases for parallel execution"

        # Check policy-level parallelism (if gate provided)
        if self.policy_gate:
            if not self.policy_gate.is_parallel_allowed():
                return False, "Parallelism not allowed by intention anchor policy"

            max_concurrent = self.policy_gate.get_max_concurrent_runs()
            if len(phases) > max_concurrent:
                return False, (
                    f"Requested {len(phases)} parallel phases exceeds "
                    f"max_concurrent_runs={max_concurrent}"
                )

        # Check all pairwise scope overlaps
        for i, phase_a in enumerate(phases):
            for phase_b in phases[i + 1 :]:
                can_parallel, reason = check_phases_can_run_parallel(phase_a, phase_b)
                if not can_parallel:
                    return False, reason

        return True, None

    def get_parallel_groups(
        self, queued_phases: List[Dict], max_group_size: Optional[int] = None
    ) -> List[List[Dict]]:
        """Group queued phases into parallel execution groups.

        Args:
            queued_phases: List of QUEUED phase specifications
            max_group_size: Max phases per group (defaults to policy limit or 2)

        Returns:
            List of phase groups for parallel execution
        """
        if not queued_phases:
            return []

        # Determine max group size from policy or default
        if max_group_size is None:
            if self.policy_gate and self.policy_gate.is_parallel_allowed():
                max_group_size = self.policy_gate.get_max_concurrent_runs()
            else:
                max_group_size = 1

        # If parallelism not allowed, return single-phase groups
        if max_group_size <= 1:
            return [[phase] for phase in queued_phases]

        return find_parallel_execution_groups(queued_phases, max_group_size)

    def log_parallel_opportunity(self, phases: List[Dict]) -> None:
        """Log information about parallel execution opportunity.

        Args:
            phases: Phases being considered for parallel execution
        """
        if len(phases) < 2:
            return

        can_parallel, reason = self.can_execute_parallel(phases)
        phase_ids = [p.get("phase_id", "unknown") for p in phases]

        if can_parallel:
            logger.info(f"[IMP-AUTO-002] Parallel execution possible for phases: {phase_ids}")
        else:
            logger.debug(
                f"[IMP-AUTO-002] Sequential execution required for phases {phase_ids}: {reason}"
            )
