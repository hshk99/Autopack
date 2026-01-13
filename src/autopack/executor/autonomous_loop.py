"""Autonomous execution loop for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles the main autonomous execution loop that processes backlog phases.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from autopack.config import settings
from autopack.archive_consolidator import log_build_event
from autopack.memory import extract_goal_from_description
from autopack.learned_rules import promote_hints_to_rules

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class AutonomousLoop:
    """Main autonomous execution loop.

    Responsibilities:
    1. Process backlog phases sequentially
    2. Handle phase execution orchestration
    3. Monitor execution health
    4. Handle loop termination conditions
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def run(
        self,
        poll_interval: int = 10,
        max_iterations: Optional[int] = None,
        stop_on_first_failure: bool = False,
    ):
        """Run autonomous execution loop.

        Args:
            poll_interval: Seconds to wait between polling for next phase
            max_iterations: Maximum number of phases to execute (None = unlimited)
            stop_on_first_failure: If True, stop immediately when any phase fails

        Returns:
            Execution statistics dictionary
        """
        logger.info("Starting autonomous execution loop...")
        logger.info(f"Poll interval: {poll_interval}s")
        if max_iterations:
            logger.info(f"Max iterations: {max_iterations}")

        # Ensure API server is running (auto-start if needed)
        if not self.executor._ensure_api_server_running():
            logger.error("Cannot proceed without API server. Exiting.")
            return

        # P0: Sanity check - verify run exists in API database before proceeding
        # This detects DB identity mismatch (API using different DB than expected)
        self._verify_run_exists()

        # Initialize infrastructure
        self.executor._init_infrastructure()

        # Initialize intention-first loop
        self._initialize_intention_loop()

        # Main execution loop
        stats = self._execute_loop(poll_interval, max_iterations, stop_on_first_failure)

        # Handle cleanup and finalization
        self._finalize_execution(stats)

    def _verify_run_exists(self):
        """Verify that the run exists in the API database."""
        from autopack.supervisor.api_client import SupervisorApiHttpError

        try:
            self.executor.api_client.get_run(self.executor.run_id, timeout=10)
            logger.info(f"✅ Run '{self.executor.run_id}' verified in API database")
        except SupervisorApiHttpError as e:
            if e.status_code == 404:
                logger.error("=" * 70)
                logger.error("[DB_MISMATCH] RUN NOT FOUND IN API DATABASE")
                logger.error("=" * 70)
                logger.error(f"API server is healthy but run '{self.executor.run_id}' not found")
                logger.error("This indicates database identity mismatch:")
                logger.error(
                    f"  - Executor DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}"
                )
                logger.error("  - API server may be using different database")
                logger.error("")
                logger.error("Recommended fixes:")
                logger.error("  1. Verify DATABASE_URL is set correctly before starting executor")
                logger.error("  2. Verify run was seeded in the correct database")
                logger.error("  3. Check API server logs for actual DATABASE_URL used")
                logger.error("  4. Use absolute paths for SQLite (not relative)")
                logger.error("=" * 70)
                raise RuntimeError(
                    f"Run '{self.executor.run_id}' not found in API database. "
                    f"Database identity mismatch detected. "
                    f"Cannot proceed - would cause 404 errors on every API call."
                )
            else:
                # Non-404 error
                logger.warning(f"Could not verify run existence (non-404 error): {e}")
                # Continue anyway - might be transient API error
        except Exception as e:
            logger.warning(f"Could not verify run existence: {e}")
            # Continue anyway - don't block execution on sanity check failure

    def _initialize_intention_loop(self):
        """Initialize intention-first loop for the run."""
        from autopack.autonomous.executor_wiring import initialize_intention_first_loop
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        # Load intention anchor for this run
        try:
            intention_anchor = IntentionAnchorStorage.load_anchor(self.executor.run_id)
            if intention_anchor is None:
                logger.warning(
                    f"[IntentionFirst] No intention anchor found for run {self.executor.run_id}, using defaults"
                )
                # Create minimal default anchor if none exists
                from autopack.intention_anchor.models import (
                    IntentionAnchor,
                    IntentionConstraints,
                    IntentionBudgets,
                )
                from datetime import datetime, timezone

                intention_anchor = IntentionAnchor(
                    anchor_id=f"default-{self.executor.run_id}",
                    run_id=self.executor.run_id,
                    project_id="default",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    version=1,
                    north_star="Execute run according to phase specifications",
                    success_criteria=["All phases complete successfully"],
                    constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
                    budgets=IntentionBudgets(
                        max_context_chars=settings.run_token_cap * 4,  # Rough char estimate
                        max_sot_chars=500_000,
                    ),
                )
            logger.info(
                f"[IntentionFirst] Loaded intention anchor: {intention_anchor.anchor_id} (v{intention_anchor.version})"
            )

            # Initialize the intention-first loop with routing snapshot + state tracking
            wiring = initialize_intention_first_loop(
                run_id=self.executor.run_id,
                project_id=intention_anchor.project_id,
                intention_anchor=intention_anchor,
            )
            logger.info(
                f"[IntentionFirst] Initialized loop with routing snapshot: {wiring.run_state.routing_snapshot.snapshot_id}"
            )
            # Store wiring state as instance variable for phase execution
            self.executor._intention_wiring = wiring
            self.executor._intention_anchor = intention_anchor
        except Exception as e:
            logger.warning(
                f"[IntentionFirst] Failed to initialize intention-first loop: {e}, continuing without it"
            )
            self.executor._intention_wiring = None
            self.executor._intention_anchor = None

    def _execute_loop(
        self, poll_interval: int, max_iterations: Optional[int], stop_on_first_failure: bool
    ) -> Dict:
        """Execute the main autonomous loop.

        Returns:
            Dictionary with execution statistics
        """
        iteration = 0
        phases_executed = 0
        phases_failed = 0
        stop_signal_file = Path(".autonomous_runs/.stop_executor")
        stop_reason: str | None = None

        while True:
            # Check for stop signal (from monitor script)
            if stop_signal_file.exists():
                signal_content = stop_signal_file.read_text().strip()
                if signal_content.startswith(f"stop:{self.executor.run_id}"):
                    logger.critical(f"[STOP_SIGNAL] Stop signal detected: {signal_content}")
                    logger.info("Stopping execution as requested by monitor")
                    stop_signal_file.unlink()  # Remove signal file
                    stop_reason = "stop_signal"
                    break

            # Check iteration limit
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations}), stopping")
                stop_reason = "max_iterations"
                break

            iteration += 1

            # Fetch run status
            logger.info(f"Iteration {iteration}: Fetching run status...")
            try:
                run_data = self.executor.get_run_status()
            except Exception as e:
                logger.error(f"Failed to fetch run status: {e}")
                logger.info(f"Waiting {poll_interval}s before retry...")
                time.sleep(poll_interval)
                continue

            # Auto-fix queued phases (normalize deliverables/scope, tune CI timeouts) before selection.
            try:
                self.executor._autofix_queued_phases(run_data)
            except Exception as e:
                logger.warning(f"[AutoFix] Failed to auto-fix queued phases (non-blocking): {e}")

            # NEW: Initialize goal anchor on first iteration (for drift detection)
            if iteration == 1 and not hasattr(self.executor, "_run_goal_anchor"):
                # Try to get goal_anchor from run data, or extract from first phase
                goal_anchor = run_data.get("goal_anchor")
                if not goal_anchor:
                    # Fall back to extracting from run description or first phase description
                    run_description = run_data.get("description", "")
                    if run_description:
                        goal_anchor = extract_goal_from_description(run_description)
                    else:
                        # Try first phase
                        phases = run_data.get("phases", [])
                        if phases:
                            first_phase_desc = phases[0].get("description", "")
                            goal_anchor = extract_goal_from_description(first_phase_desc)
                if goal_anchor:
                    self.executor._run_goal_anchor = goal_anchor
                    logger.info(f"[GoalAnchor] Initialized: {goal_anchor[:100]}...")

            # Phase 1.6-1.7: Detect and reset stale EXECUTING phases
            try:
                self.executor._detect_and_reset_stale_phases(run_data)
            except Exception as e:
                logger.warning(f"Stale phase detection failed: {e}")
                # Continue even if stale detection fails

            # BUILD-115: Use API-based phase selection instead of obsolete database queries
            next_phase = self.executor.get_next_queued_phase(run_data)

            if not next_phase:
                logger.info("No more executable phases, execution complete")
                stop_reason = "no_more_executable_phases"
                break

            phase_id = next_phase.get("phase_id")
            logger.info(f"[BUILD-041] Next phase: {phase_id}")

            # Execute phase
            success, status = self.executor.execute_phase(next_phase)

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
                phases_executed += 1
                # Reset failure count on success
                self.executor._phase_failure_counts[phase_id] = 0
            else:
                logger.warning(f"Phase {phase_id} finished with status: {status}")
                phases_failed += 1

                # NEW: Stop on first failure if requested (saves token usage)
                if stop_on_first_failure:
                    logger.critical(
                        f"[STOP_ON_FAILURE] Phase {phase_id} failed with status: {status}. "
                        f"Stopping execution to save token usage."
                    )
                    logger.info(
                        f"Total phases executed: {phases_executed}, failed: {phases_failed}"
                    )
                    stop_reason = "stop_on_first_failure"
                    break

            # Wait before next iteration
            if max_iterations is None or iteration < max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                time.sleep(poll_interval)

        logger.info("Autonomous execution loop finished")

        return {
            "iteration": iteration,
            "phases_executed": phases_executed,
            "phases_failed": phases_failed,
            "stop_reason": stop_reason,
        }

    def _finalize_execution(self, stats: Dict):
        """Finalize execution and handle cleanup.

        Args:
            stats: Execution statistics dictionary
        """
        iteration = stats["iteration"]
        phases_executed = stats["phases_executed"]
        phases_failed = stats["phases_failed"]
        stop_reason = stats["stop_reason"]

        # IMPORTANT: Only finalize a run when there are no executable phases remaining.
        # If we stop due to max-iterations/stop-signal/stop-on-failure, the run should remain resumable
        # (i.e., do NOT force it into a DONE_* state).
        if stop_reason == "no_more_executable_phases":
            # Log run completion summary to CONSOLIDATED_BUILD.md
            try:
                log_build_event(
                    event_type="RUN_COMPLETE",
                    description=f"Run {self.executor.run_id} completed. Phases: {phases_executed} successful, {phases_failed} failed. Total iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.executor.run_id}",
                        f"Successful: {phases_executed}",
                        f"Failed: {phases_failed}",
                    ],
                    project_slug=self.executor._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run completion: {e}")

            # Best-effort fallback: ensure run_summary.md reflects terminal state even if API-side hook fails
            # Here we are truly finalizing the run (no executable phases remaining),
            # so allow mutating run.state to a terminal DONE_* state if needed.
            self.executor._best_effort_write_run_summary(
                phases_failed=phases_failed, allow_run_state_mutation=True
            )

            # Learning Pipeline: Promote hints to persistent rules (Stage 0B)
            try:
                project_id = self.executor._get_project_slug()
                promoted_count = promote_hints_to_rules(self.executor.run_id, project_id)
                if promoted_count > 0:
                    logger.info(
                        f"Learning Pipeline: Promoted {promoted_count} hints to persistent project rules"
                    )
                    # Mark that rules have changed for future planning updates
                    self.executor._mark_rules_updated(project_id, promoted_count)
                else:
                    logger.info(
                        "Learning Pipeline: No hints qualified for promotion (need 2+ occurrences)"
                    )
            except Exception as e:
                logger.warning(f"Failed to promote hints to rules: {e}")
        else:
            # Non-terminal stop: keep the run resumable.
            # Still log a lightweight event for visibility.
            try:
                log_build_event(
                    event_type="RUN_PAUSED",
                    description=f"Run {self.executor.run_id} paused (reason={stop_reason}). Iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.executor.run_id}",
                        f"Reason: {stop_reason}",
                        f"Iterations: {iteration}",
                    ],
                    project_slug=self.executor._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run pause: {e}")
