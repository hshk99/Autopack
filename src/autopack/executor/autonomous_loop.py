"""Autonomous execution loop for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles the main autonomous execution loop that processes backlog phases.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from autopack.config import settings
from autopack.archive_consolidator import log_build_event
from autopack.database import ensure_session_healthy, SESSION_HEALTH_CHECK_INTERVAL
from autopack.memory import extract_goal_from_description
from autopack.memory.context_injector import ContextInjector
from autopack.learned_rules import promote_hints_to_rules
from autopack.telemetry.analyzer import TelemetryAnalyzer
from autopack.autonomous.budgeting import (
    BudgetExhaustedError,
    is_budget_exhausted,
    get_budget_remaining_pct,
)

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class SOTDriftError(Exception):
    """Raised when SOT drift is detected and drift_blocks_execution is enabled."""

    pass


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
        self.poll_interval = 0.5  # Base polling interval
        self.idle_backoff_multiplier = 2.0  # Backoff when idle
        self.max_idle_sleep = 5.0  # Maximum sleep time when idle
        self._last_session_health_check = time.time()  # Track last health check
        self._telemetry_analyzer: Optional[TelemetryAnalyzer] = None

    def _get_telemetry_analyzer(self) -> Optional[TelemetryAnalyzer]:
        """Get or create the telemetry analyzer instance.

        Returns:
            TelemetryAnalyzer instance if database session is available, None otherwise.
        """
        if self._telemetry_analyzer is None:
            if hasattr(self.executor, "db_session") and self.executor.db_session:
                # IMP-ARCH-015: Pass memory_service to enable telemetry -> memory bridge
                memory_service = getattr(self.executor, "memory_service", None)
                self._telemetry_analyzer = TelemetryAnalyzer(
                    self.executor.db_session,
                    memory_service=memory_service,
                )
        return self._telemetry_analyzer

    def _get_telemetry_adjustments(self, phase_type: Optional[str]) -> Dict:
        """Get telemetry-driven adjustments for phase execution.

        Queries the telemetry analyzer for recommendations and returns
        adjustments to apply to the phase execution.

        Args:
            phase_type: The type of phase being executed

        Returns:
            Dictionary of adjustments to pass to execute_phase:
            - context_reduction_factor: Factor to reduce context by (e.g., 0.7 for 30% reduction)
            - model_downgrade: Target model to use instead (e.g., "sonnet", "haiku")
            - timeout_increase_factor: Factor to increase timeout by (e.g., 1.5 for 50% increase)
        """
        adjustments: Dict = {}

        if not phase_type:
            return adjustments

        analyzer = self._get_telemetry_analyzer()
        if not analyzer:
            return adjustments

        try:
            recommendations = analyzer.get_recommendations_for_phase(phase_type)
        except Exception as e:
            logger.warning(f"[Telemetry] Failed to get recommendations for {phase_type}: {e}")
            return adjustments

        # Model downgrade hierarchy: opus -> sonnet -> haiku
        model_hierarchy = ["opus", "sonnet", "haiku"]

        for rec in recommendations:
            severity = rec.get("severity")
            action = rec.get("action")
            reason = rec.get("reason", "")
            metric_value = rec.get("metric_value")

            if severity == "CRITICAL":
                # Apply mitigations for CRITICAL recommendations
                if action == "reduce_context_size":
                    adjustments["context_reduction_factor"] = 0.7  # Reduce by 30%
                    logger.warning(
                        f"[Telemetry] CRITICAL: Reducing context size by 30% for {phase_type}. "
                        f"Reason: {reason}"
                    )
                elif action == "switch_to_smaller_model":
                    # Downgrade model: opus -> sonnet -> haiku
                    current_model = getattr(settings, "default_model", "opus").lower()
                    current_idx = -1
                    for i, model in enumerate(model_hierarchy):
                        if model in current_model:
                            current_idx = i
                            break
                    if current_idx >= 0 and current_idx < len(model_hierarchy) - 1:
                        adjustments["model_downgrade"] = model_hierarchy[current_idx + 1]
                        logger.warning(
                            f"[Telemetry] CRITICAL: Downgrading model to {adjustments['model_downgrade']} "
                            f"for {phase_type}. Reason: {reason}"
                        )
                elif action == "increase_timeout":
                    adjustments["timeout_increase_factor"] = 1.5  # Increase by 50%
                    logger.warning(
                        f"[Telemetry] CRITICAL: Increasing timeout by 50% for {phase_type}. "
                        f"Reason: {reason}"
                    )
            elif severity == "HIGH":
                # Log HIGH recommendations for informational tracking only
                logger.info(
                    f"[Telemetry] HIGH: {action} recommended for {phase_type}. "
                    f"Reason: {reason} (metric: {metric_value})"
                )

        return adjustments

    def _get_memory_context(self, phase_type: str, goal: str) -> str:
        """Retrieve memory context for builder injection.

        Queries vector memory for historical context (past errors, successful strategies,
        doctor hints) related to the phase and injects it into the builder prompt.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
            goal: Phase goal/description

        Returns:
            Formatted context string for prompt injection, or empty string if memory disabled
        """
        # Get project ID for memory queries
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        try:
            injector = ContextInjector()
            injection = injector.get_context_for_phase(
                phase_type=phase_type,
                current_goal=goal,
                project_id=project_id,
                max_tokens=500,
            )

            if injection.total_token_estimate > 0:
                logger.info(
                    f"[IMP-ARCH-002] Injecting {injection.total_token_estimate} tokens of memory context "
                    f"({len(injection.past_errors)} errors, "
                    f"{len(injection.successful_strategies)} strategies, "
                    f"{len(injection.doctor_hints)} hints, "
                    f"{len(injection.relevant_insights)} insights)"
                )

            return injector.format_for_prompt(injection)
        except Exception as e:
            logger.warning(f"[IMP-ARCH-002] Failed to retrieve memory context: {e}")
            return ""

    def _get_improvement_task_context(self) -> str:
        """Get improvement tasks as context for phase execution (IMP-ARCH-019).

        Formats loaded improvement tasks into a context string that guides
        the Builder to address self-improvement opportunities.

        Returns:
            Formatted context string, or empty string if no tasks
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return ""

        # Format tasks for injection
        lines = ["## Self-Improvement Tasks (from previous runs)"]
        lines.append("The following improvement opportunities were identified from telemetry:")
        lines.append("")

        for i, task in enumerate(improvement_tasks[:5], 1):  # Limit to 5 tasks
            priority = task.get("priority", "medium")
            title = task.get("title", "Unknown task")
            description = task.get("description", "")[:200]  # Truncate long descriptions
            files = task.get("suggested_files", [])

            lines.append(f"### {i}. [{priority.upper()}] {title}")
            if description:
                lines.append(f"{description}")
            if files:
                lines.append(f"Suggested files: {', '.join(files[:3])}")
            lines.append("")

        lines.append("Consider addressing these issues if relevant to the current phase.")

        context = "\n".join(lines)
        logger.info(
            f"[IMP-ARCH-019] Injecting {len(improvement_tasks)} improvement tasks into phase context"
        )
        return context

    def _mark_improvement_tasks_completed(self) -> None:
        """Mark improvement tasks as completed after successful run (IMP-ARCH-019).

        Called when run finishes with no failed phases, indicating the improvement
        tasks were successfully addressed.
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            generator = AutonomousTaskGenerator()
            completed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    if generator.mark_task_status(
                        task_id, "completed", executed_in_run_id=self.executor.run_id
                    ):
                        completed_count += 1

            if completed_count > 0:
                logger.info(
                    f"[IMP-ARCH-019] Marked {completed_count} improvement tasks as completed"
                )

        except Exception as e:
            logger.warning(f"[IMP-ARCH-019] Failed to mark tasks completed: {e}")

    def _adaptive_sleep(self, is_idle: bool = False, base_interval: Optional[float] = None):
        """Sleep with adaptive backoff when idle to reduce CPU usage.

        Args:
            is_idle: If True, apply backoff multiplier to reduce CPU usage when no phases available
            base_interval: Override base interval for this sleep (defaults to self.poll_interval)
        """
        interval = base_interval if base_interval is not None else self.poll_interval
        if is_idle:
            # Apply backoff multiplier and cap at max_idle_sleep
            sleep_time = min(interval * self.idle_backoff_multiplier, self.max_idle_sleep)
        else:
            sleep_time = interval
        # NOTE: time.sleep() intentional - autonomous loop runs in sync context
        time.sleep(sleep_time)
        return sleep_time

    def _log_db_pool_health(self) -> None:
        """Log database pool health to telemetry (IMP-DB-001).

        Monitors connection pool for:
        - Pool exhaustion (high utilization)
        - Connection leaks (long-held connections)
        - Hot code paths (frequent connections)
        """
        from autopack.database import get_pool_health

        if not settings.db_pool_monitoring_enabled:
            return

        try:
            pool_health = get_pool_health()

            # Log high utilization warning
            if pool_health.utilization_pct > 80:
                logger.warning(
                    f"[IMP-DB-001] Database pool utilization high: {pool_health.utilization_pct:.1f}% "
                    f"({pool_health.checked_out}/{pool_health.pool_size})"
                )

            # Log potential leaks
            if pool_health.potential_leaks:
                logger.warning(
                    f"[IMP-DB-001] Detected {len(pool_health.potential_leaks)} potential connection leaks. "
                    f"Longest checkout: {pool_health.longest_checkout_sec:.1f}s"
                )

            # Debug logging for monitoring
            logger.debug(
                f"[IMP-DB-001] Pool health - "
                f"Size: {pool_health.pool_size}, "
                f"CheckedOut: {pool_health.checked_out}, "
                f"Overflow: {pool_health.overflow}, "
                f"Utilization: {pool_health.utilization_pct:.1f}%"
            )
        except Exception as e:
            logger.warning(f"[IMP-DB-001] Failed to collect pool health metrics: {e}")

    def run(
        self,
        poll_interval: float = 0.5,
        max_iterations: Optional[int] = None,
        stop_on_first_failure: bool = False,
    ):
        """Run autonomous execution loop.

        Args:
            poll_interval: Seconds to wait between polling for next phase (default: 0.5s, reduced from 1.0s for better performance)
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

    def _load_improvement_tasks(self) -> List[dict]:
        """Load pending improvement tasks from previous runs (IMP-ARCH-012).

        Part of the self-improvement feedback loop:
        - Tasks are generated from telemetry insights (IMP-ARCH-009)
        - Tasks are persisted to database (IMP-ARCH-011)
        - This method retrieves pending tasks for execution

        Returns:
            List of task dicts compatible with phase planning
        """
        # Check if task generation is enabled
        if not getattr(settings, "task_generation_enabled", False):
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            generator = AutonomousTaskGenerator()
            max_tasks = getattr(settings, "task_generation_max_tasks_per_run", 5)
            pending_tasks = generator.get_pending_tasks(status="pending", limit=max_tasks)

            if not pending_tasks:
                logger.debug("[IMP-ARCH-012] No pending improvement tasks found")
                return []

            # Convert to planning-compatible format
            task_items = []
            for task in pending_tasks:
                task_items.append(
                    {
                        "task_id": task.task_id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "suggested_files": task.suggested_files,
                        "source": "self_improvement",
                        "estimated_effort": task.estimated_effort,
                    }
                )
                # Mark as in_progress
                generator.mark_task_status(
                    task.task_id, "in_progress", executed_in_run_id=self.executor.run_id
                )

            logger.info(f"[IMP-ARCH-012] Loaded {len(task_items)} improvement tasks for this run")
            return task_items

        except Exception as e:
            logger.warning(f"[IMP-ARCH-012] Failed to load improvement tasks: {e}")
            return []

    def _initialize_intention_loop(self):
        """Initialize intention-first loop for the run."""
        from autopack.autonomous.executor_wiring import initialize_intention_first_loop
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        # IMP-ARCH-012: Load pending improvement tasks from self-improvement loop
        improvement_tasks = self._load_improvement_tasks()
        if improvement_tasks:
            # Store improvement tasks for injection into phase planning
            self.executor._improvement_tasks = improvement_tasks
        else:
            self.executor._improvement_tasks = []

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
        self, poll_interval: float, max_iterations: Optional[int], stop_on_first_failure: bool
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

            # Periodic database session health check (prevents stale connections in long runs)
            current_time = time.time()
            if current_time - self._last_session_health_check >= SESSION_HEALTH_CHECK_INTERVAL:
                if hasattr(self.executor, "db_session") and self.executor.db_session:
                    ensure_session_healthy(self.executor.db_session)
                    self._last_session_health_check = current_time
                    logger.debug("[SessionHealth] Periodic session health check completed")

            # Check iteration limit
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations}), stopping")
                stop_reason = "max_iterations"
                break

            iteration += 1

            # IMP-DB-001: Log database pool health at start of each iteration
            self._log_db_pool_health()

            # Fetch run status
            logger.info(f"Iteration {iteration}: Fetching run status...")
            try:
                run_data = self.executor.get_run_status()
            except Exception as e:
                logger.error(f"Failed to fetch run status: {e}")
                logger.info(f"Waiting {poll_interval}s before retry...")
                self._adaptive_sleep(is_idle=True, base_interval=poll_interval)
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

            # IMP-SOT-001: Check SOT drift at runtime during autonomous execution
            try:
                self._check_sot_drift()
            except SOTDriftError as e:
                logger.critical(f"[IMP-SOT-001] {str(e)}")
                stop_reason = "sot_drift_detected"
                raise

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
            phase_type = next_phase.get("phase_type")
            logger.info(f"[BUILD-041] Next phase: {phase_id}")

            # IMP-COST-001: Check budget exhaustion BEFORE phase execution
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)
            token_cap = settings.run_token_cap
            if is_budget_exhausted(token_cap, tokens_used):
                budget_remaining = get_budget_remaining_pct(token_cap, tokens_used)
                error_msg = (
                    f"Run aborted: token budget exhausted ({tokens_used}/{token_cap} tokens used). "
                    f"Budget remaining: {budget_remaining:.1%}. "
                    f"Increase run_token_cap in config or review phase efficiency."
                )
                logger.critical(f"[BUDGET_EXHAUSTED] {error_msg}")
                stop_reason = "budget_exhausted"
                raise BudgetExhaustedError(error_msg)

            # Log budget status before each phase
            budget_pct = get_budget_remaining_pct(token_cap, tokens_used) * 100
            logger.info(
                f"Phase {phase_id}: Budget remaining {budget_pct:.1f}% ({tokens_used}/{token_cap} tokens)"
            )

            # Telemetry-driven phase adjustments (IMP-TEL-002)
            phase_adjustments = self._get_telemetry_adjustments(phase_type)

            # IMP-ARCH-002: Retrieve memory context for builder injection
            phase_goal = next_phase.get("description", "")
            memory_context = self._get_memory_context(phase_type, phase_goal)
            if memory_context:
                phase_adjustments["memory_context"] = memory_context

            # IMP-ARCH-019: Inject improvement tasks into phase context
            improvement_context = self._get_improvement_task_context()
            if improvement_context:
                existing_context = phase_adjustments.get("memory_context", "")
                phase_adjustments["memory_context"] = (
                    existing_context + "\n\n" + improvement_context
                    if existing_context
                    else improvement_context
                )

            # Execute phase (with any telemetry-driven adjustments and memory context)
            success, status = self.executor.execute_phase(next_phase, **phase_adjustments)

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
                phases_executed += 1
                # Reset failure count on success
                self.executor._phase_failure_counts[phase_id] = 0

                # IMP-AUTOPILOT-001: Periodic autopilot invocation after successful phases
                if (
                    hasattr(self.executor, "autopilot")
                    and self.executor.autopilot
                    and hasattr(self.executor, "_autopilot_phase_count")
                    and isinstance(self.executor._autopilot_phase_count, int)
                ):
                    self.executor._autopilot_phase_count += 1
                    if (
                        self.executor._autopilot_phase_count % settings.autopilot_gap_scan_frequency
                        == 0
                    ):
                        logger.info(
                            f"[IMP-AUTOPILOT-001] Invoking autopilot after {self.executor._autopilot_phase_count} phases"
                        )
                        try:
                            self._invoke_autopilot_session()
                        except Exception as e:
                            logger.warning(
                                f"[IMP-AUTOPILOT-001] Autopilot session failed (non-blocking): {e}"
                            )
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
                self._adaptive_sleep(is_idle=False, base_interval=poll_interval)

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
            # IMP-ARCH-001: Persist telemetry insights to memory after run completion
            try:
                self._persist_telemetry_insights()
            except Exception as e:
                logger.warning(f"Failed to persist telemetry insights: {e}")

            # IMP-ARCH-009: Generate improvement tasks from telemetry for self-improvement loop
            try:
                self._generate_improvement_tasks()
            except Exception as e:
                logger.warning(f"Failed to generate improvement tasks: {e}")

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

            # IMP-ARCH-019: Mark improvement tasks as completed when run finishes successfully
            if phases_failed == 0:
                try:
                    self._mark_improvement_tasks_completed()
                except Exception as e:
                    logger.warning(f"Failed to mark improvement tasks as completed: {e}")

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

    def _check_sot_drift(self) -> None:
        """Check for SOT drift at runtime.

        Implements IMP-SOT-001: Runtime validation that SOT documents (BUILD_HISTORY, DEBUG_LOG)
        remain consistent throughout autonomous execution. Detects drift early to prevent
        accumulation of stale documentation.

        Raises:
            SOTDriftError: If drift is detected and sot_drift_blocks_execution is enabled
        """
        # Import here to avoid circular imports
        from autopack.gaps.doc_drift import SOTDriftDetector

        # Check if runtime enforcement is enabled
        if not settings.sot_runtime_enforcement_enabled:
            return

        # Get project root (use executor's root if available)
        project_root = getattr(self.executor, "project_root", ".")

        # Run quick SOT consistency check
        detector = SOTDriftDetector(project_root=project_root)
        is_consistent, issues = detector.quick_check()

        if not is_consistent:
            issue_msg = "\n  - ".join(issues)
            warning_msg = f"SOT drift detected:\n  - {issue_msg}"
            logger.warning(f"[IMP-SOT-001] {warning_msg}")

            # Check if drift blocks execution
            if settings.sot_drift_blocks_execution:
                raise SOTDriftError(f"SOT drift blocking execution: {issues}")

    def _invoke_autopilot_session(self):
        """Invoke autopilot to scan for gaps and execute approved improvements.

        IMP-AUTOPILOT-001: Periodic autopilot invocation during autonomous execution.
        Runs gap scanning, proposes improvements, and executes auto-approved actions.
        """
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        logger.info("[IMP-AUTOPILOT-001] Starting autopilot gap scan session...")

        # Load intention anchor for this run (provides constraints for autopilot)
        try:
            intention_anchor = IntentionAnchorStorage.load_anchor(self.executor.run_id)
            if intention_anchor is None:
                logger.warning(
                    f"[IMP-AUTOPILOT-001] No intention anchor found for run {self.executor.run_id}, "
                    f"using cached anchor or defaults"
                )
                # Fall back to cached anchor if available
                intention_anchor = getattr(self.executor, "_intention_anchor", None)
        except Exception as e:
            logger.warning(f"[IMP-AUTOPILOT-001] Failed to load intention anchor: {e}")
            intention_anchor = getattr(self.executor, "_intention_anchor", None)

        # Run autopilot session (gap scanning + proposal generation)
        try:
            proposals = self.executor.autopilot.run_session(
                intention_anchor=intention_anchor,
                max_proposals=settings.autopilot_max_proposals_per_session,
            )
            logger.info(
                f"[IMP-AUTOPILOT-001] Autopilot generated {len(proposals)} improvement proposals"
            )
        except Exception as e:
            logger.error(f"[IMP-AUTOPILOT-001] Autopilot session failed: {e}")
            return

        # Filter for auto-approved proposals
        auto_approved = [p for p in proposals if p.get("auto_approved", False)]
        if not auto_approved:
            logger.info(
                "[IMP-AUTOPILOT-001] No auto-approved proposals. "
                f"{len(proposals)} proposals require manual approval (see IMP-AUTOPILOT-002)."
            )
            return

        logger.info(
            f"[IMP-AUTOPILOT-001] Executing {len(auto_approved)} auto-approved improvement proposals"
        )

        # Execute auto-approved proposals
        for i, proposal in enumerate(auto_approved, 1):
            proposal_id = proposal.get("proposal_id", f"autopilot-{i}")
            gap_type = proposal.get("gap_type", "unknown")
            description = proposal.get("description", "No description")

            logger.info(
                f"[IMP-AUTOPILOT-001] [{i}/{len(auto_approved)}] Executing proposal {proposal_id}: "
                f"{gap_type} - {description[:80]}"
            )

            try:
                # Execute proposal through autopilot controller
                self.executor.autopilot.execute_proposal(proposal)
                logger.info(f"[IMP-AUTOPILOT-001] ✅ Proposal {proposal_id} executed successfully")
            except Exception as e:
                logger.warning(
                    f"[IMP-AUTOPILOT-001] ⚠️ Proposal {proposal_id} execution failed: {e}"
                )
                # Continue with next proposal (non-blocking)

        logger.info("[IMP-AUTOPILOT-001] Autopilot session completed")

    def _persist_telemetry_insights(self) -> None:
        """Analyze and persist telemetry insights to memory after run completion.

        Implements IMP-ARCH-001: Wire Telemetry Analyzer to Memory Service.
        Closes the ROAD-B feedback loop by persisting ranked issues to vector memory
        for retrieval in future runs.
        """
        analyzer = self._get_telemetry_analyzer()
        if not analyzer:
            logger.debug("[IMP-ARCH-001] No telemetry analyzer available")
            return

        try:
            # Analyze telemetry from the run and aggregate issues
            ranked_issues = analyzer.aggregate_telemetry(window_days=7)
            logger.info(
                f"[IMP-ARCH-001] Analyzed telemetry: "
                f"{len(ranked_issues.get('top_cost_sinks', []))} cost sinks, "
                f"{len(ranked_issues.get('top_failure_modes', []))} failure modes, "
                f"{len(ranked_issues.get('top_retry_causes', []))} retry causes"
            )
        except Exception as e:
            logger.warning(f"[IMP-ARCH-001] Failed to analyze telemetry: {e}")
            return

    def _generate_improvement_tasks(self) -> list:
        """Generate improvement tasks from telemetry (ROAD-C).

        Implements IMP-ARCH-004: Autonomous Task Generator.
        Converts telemetry insights into improvement tasks for self-improvement feedback loop.

        Returns:
            List of GeneratedTask objects
        """
        try:
            from autopack.roadc import AutonomousTaskGenerator
            from autopack.config import settings as config_settings
        except ImportError:
            logger.debug("[IMP-ARCH-004] ROAD-C module not available")
            return []

        # Load task generation configuration
        try:
            # Try to load from settings if available
            task_gen_config = getattr(config_settings, "task_generation", {})
            if not task_gen_config:
                task_gen_config = {"enabled": False}
        except Exception:
            task_gen_config = {"enabled": False}

        if not task_gen_config.get("enabled", False):
            logger.debug("[IMP-ARCH-004] Task generation not enabled")
            return []

        try:
            generator = AutonomousTaskGenerator()
            result = generator.generate_tasks(
                max_tasks=task_gen_config.get("max_tasks_per_run", 10),
                min_confidence=task_gen_config.get("min_confidence", 0.7),
            )

            logger.info(
                f"[IMP-ARCH-004] Generated {len(result.tasks_generated)} tasks "
                f"from {result.insights_processed} insights "
                f"({result.generation_time_ms:.0f}ms)"
            )

            # IMP-ARCH-014: Persist generated tasks to database
            if result.tasks_generated:
                try:
                    run_id = getattr(self.executor, "run_id", None)
                    persisted_count = generator.persist_tasks(result.tasks_generated, run_id)
                    logger.info(f"[IMP-ARCH-014] Persisted {persisted_count} tasks to database")
                except Exception as persist_err:
                    logger.warning(f"[IMP-ARCH-014] Failed to persist tasks: {persist_err}")

            return result.tasks_generated
        except Exception as e:
            logger.warning(f"[IMP-ARCH-004] Failed to generate improvement tasks: {e}")
            return []
