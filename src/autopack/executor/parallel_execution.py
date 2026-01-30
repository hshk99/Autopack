"""Parallel phase execution support for autonomous loop.

IMP-GOD-002: Extracted from autonomous_loop.py to reduce god file size.

IMP-AUTO-002: Supports parallel phase execution when file scopes don't overlap.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor
    from autopack.autonomy.parallelism_gate import ScopeBasedParallelismChecker

logger = logging.getLogger(__name__)


class ParallelExecutionHelper:
    """Manages parallel phase execution for the autonomous loop.

    IMP-AUTO-002: Extended to support parallel phase execution when file scopes
    don't overlap.
    """

    def __init__(
        self,
        executor: "AutonomousExecutor",
        parallel_execution_enabled: bool = False,
        max_parallel_phases: int = 2,
    ):
        """Initialize parallel execution helper.

        Args:
            executor: Reference to the AutonomousExecutor.
            parallel_execution_enabled: Whether parallel execution is enabled.
            max_parallel_phases: Maximum number of phases to run in parallel.
        """
        self.executor = executor
        self._parallelism_checker: Optional["ScopeBasedParallelismChecker"] = None
        self._parallel_execution_enabled = parallel_execution_enabled
        self._max_parallel_phases = max_parallel_phases
        self._parallel_phases_executed = 0
        self._parallel_phases_skipped = 0

    @property
    def parallel_execution_enabled(self) -> bool:
        """Whether parallel execution is enabled."""
        return self._parallel_execution_enabled

    @property
    def max_parallel_phases(self) -> int:
        """Maximum number of phases to run in parallel."""
        return self._max_parallel_phases

    @property
    def parallel_phases_executed(self) -> int:
        """Count of phases executed in parallel."""
        return self._parallel_phases_executed

    @property
    def parallel_phases_skipped(self) -> int:
        """Count of phases that couldn't be parallelized."""
        return self._parallel_phases_skipped

    def get_stats(self) -> Dict[str, Any]:
        """Get parallel execution statistics.

        Returns:
            Dictionary with parallel execution stats.
        """
        return {
            "enabled": self._parallel_execution_enabled,
            "max_parallel_phases": self._max_parallel_phases,
            "parallel_phases_executed": self._parallel_phases_executed,
            "parallel_phases_skipped": self._parallel_phases_skipped,
        }

    def initialize_parallelism_checker(self) -> None:
        """Initialize the scope-based parallelism checker.

        IMP-AUTO-002: Creates the parallelism checker with policy gate from
        the executor's intention anchor (if available).
        """
        from autopack.autonomy.parallelism_gate import (
            ParallelismPolicyGate,
            ScopeBasedParallelismChecker,
        )

        if not self._parallel_execution_enabled:
            logger.debug("[IMP-AUTO-002] Parallel execution disabled by configuration")
            return

        # Get policy gate from intention anchor if available
        policy_gate: Optional[ParallelismPolicyGate] = None
        intention_anchor_v2 = getattr(self.executor, "_intention_anchor_v2", None)

        if intention_anchor_v2 is not None:
            try:
                policy_gate = ParallelismPolicyGate(intention_anchor_v2)
                if policy_gate.is_parallel_allowed():
                    logger.info(
                        f"[IMP-AUTO-002] Parallelism allowed by intention anchor "
                        f"(max_concurrent={policy_gate.get_max_concurrent_runs()})"
                    )
                else:
                    logger.info("[IMP-AUTO-002] Parallelism not allowed by intention anchor policy")
            except Exception as e:
                logger.warning(f"[IMP-AUTO-002] Failed to create parallelism policy gate: {e}")

        self._parallelism_checker = ScopeBasedParallelismChecker(policy_gate)
        logger.info(
            f"[IMP-AUTO-002] Parallelism checker initialized "
            f"(max_parallel_phases={self._max_parallel_phases})"
        )

    def get_queued_phases_for_parallel_check(self, run_data: Dict) -> List[Dict]:
        """Get QUEUED phases suitable for parallel execution check.

        Args:
            run_data: Current run data from API

        Returns:
            List of QUEUED phases
        """
        phases = run_data.get("phases", [])
        queued_phases = []

        for phase in phases:
            status = phase.get("status", "").upper()
            if status == "QUEUED":
                queued_phases.append(phase)

        return queued_phases

    def execute_phases_parallel(
        self, phases: List[Dict], phase_adjustments_map: Dict[str, Dict]
    ) -> List[Tuple[Dict, bool, str]]:
        """Execute multiple phases in parallel using ThreadPoolExecutor.

        IMP-AUTO-002: Executes phases with non-overlapping scopes concurrently.

        Args:
            phases: List of phases to execute in parallel
            phase_adjustments_map: Map of phase_id -> adjustments dict

        Returns:
            List of (phase, success, status) tuples for each executed phase
        """
        results: List[Tuple[Dict, bool, str]] = []

        if len(phases) == 1:
            # Single phase - execute directly
            phase = phases[0]
            adjustments = phase_adjustments_map.get(phase.get("phase_id", ""), {})
            success, status = self.executor.execute_phase(phase, **adjustments)
            return [(phase, success, status)]

        # IMP-REL-015: Cap thread pool size to prevent thread exhaustion
        max_workers = min(len(phases), os.cpu_count() or 4, 10)
        logger.info(
            f"[IMP-AUTO-002] Executing {len(phases)} phases in parallel "
            f"(max_workers={max_workers}): "
            f"{[p.get('phase_id', 'unknown') for p in phases]}"
        )

        # Use ThreadPoolExecutor for parallel execution
        # Note: Using threads (not processes) to share executor state
        with ThreadPoolExecutor(max_workers=max_workers) as pool_executor:
            # Submit all phases for execution
            future_to_phase = {}
            for phase in phases:
                phase_id = phase.get("phase_id", "unknown")
                adjustments = phase_adjustments_map.get(phase_id, {})

                future = pool_executor.submit(
                    self._execute_single_phase_thread_safe,
                    phase,
                    adjustments,
                )
                future_to_phase[future] = phase

            # Collect results as they complete
            for future in as_completed(future_to_phase):
                phase = future_to_phase[future]
                phase_id = phase.get("phase_id", "unknown")

                try:
                    success, status = future.result()
                    results.append((phase, success, status))
                    logger.info(
                        f"[IMP-AUTO-002] Parallel phase {phase_id} completed: "
                        f"success={success}, status={status}"
                    )
                except Exception as e:
                    logger.error(f"[IMP-AUTO-002] Parallel phase {phase_id} failed with error: {e}")
                    results.append((phase, False, f"PARALLEL_EXECUTION_ERROR: {e}"))

        self._parallel_phases_executed += len(phases)
        return results

    def _execute_single_phase_thread_safe(self, phase: Dict, adjustments: Dict) -> Tuple[bool, str]:
        """Execute a single phase in a thread-safe manner.

        IMP-AUTO-002: Wrapper for execute_phase to handle thread-safety concerns.

        Args:
            phase: Phase specification
            adjustments: Telemetry-driven adjustments

        Returns:
            Tuple of (success, status)
        """
        phase_id = phase.get("phase_id", "unknown")

        try:
            # Execute via the executor
            # Note: The executor's execute_phase method handles its own locking
            success, status = self.executor.execute_phase(phase, **adjustments)
            return success, status
        except Exception as e:
            logger.error(f"[IMP-AUTO-002] Thread execution error for phase {phase_id}: {e}")
            return False, f"THREAD_ERROR: {str(e)}"

    def try_parallel_execution(
        self,
        run_data: Dict,
        next_phase: Dict,
        get_adjustments_callback: Callable[[Dict], Dict],
    ) -> Optional[Tuple[List[Tuple[Dict, bool, str]], int]]:
        """Attempt to find and execute phases in parallel.

        IMP-AUTO-002: Checks if there are additional phases that can run in parallel
        with the next_phase based on scope isolation.

        Args:
            run_data: Current run data
            next_phase: The primary phase to execute
            get_adjustments_callback: Callback to get phase adjustments
                (takes phase dict, returns adjustments dict)

        Returns:
            If parallel execution occurred: (results, phases_count)
            If sequential execution needed: None
        """
        if not self._parallel_execution_enabled or self._parallelism_checker is None:
            return None

        # Get all queued phases
        queued_phases = self.get_queued_phases_for_parallel_check(run_data)

        if len(queued_phases) < 2:
            return None

        # Put next_phase first, then find compatible phases
        next_phase_id = next_phase.get("phase_id")
        other_phases = [p for p in queued_phases if p.get("phase_id") != next_phase_id]

        if not other_phases:
            return None

        # Find phases that can run in parallel with next_phase
        parallel_group = [next_phase]

        for candidate in other_phases:
            if len(parallel_group) >= self._max_parallel_phases:
                break

            can_parallel, reason = self._parallelism_checker.can_execute_parallel(
                parallel_group + [candidate]
            )

            if can_parallel:
                parallel_group.append(candidate)
            else:
                logger.debug(
                    f"[IMP-AUTO-002] Cannot add phase {candidate.get('phase_id')} "
                    f"to parallel group: {reason}"
                )

        if len(parallel_group) < 2:
            self._parallel_phases_skipped += 1
            return None

        # Prepare adjustments for all phases in the group
        phase_adjustments_map: Dict[str, Dict] = {}
        for phase in parallel_group:
            phase_id = phase.get("phase_id", "unknown")
            adjustments = get_adjustments_callback(phase)
            phase_adjustments_map[phase_id] = adjustments

        # Execute phases in parallel
        results = self.execute_phases_parallel(parallel_group, phase_adjustments_map)
        return results, len(parallel_group)
