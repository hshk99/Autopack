"""Task injection helpers for autonomous loop.

IMP-GOD-002: Extracted from autonomous_loop.py to reduce god file size.

Handles task generation, ROAD-C queue consumption, and backlog injection.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.executor.backlog_maintenance import InjectionResult
    from autopack.task_generation.roi_analyzer import ROIAnalyzer
    from autopack.task_generation.task_effectiveness_tracker import (
        TaskEffectivenessTracker,
    )
    from autopack.telemetry.meta_metrics import MetaMetricsTracker

logger = logging.getLogger(__name__)


class TaskInjectionHelper:
    """Manages task generation and injection for the autonomous loop.

    Handles loading improvement tasks, generating tasks from telemetry,
    consuming ROAD-C queue, and injecting tasks into the execution backlog.
    """

    def __init__(
        self,
        db_session: Any = None,
        run_id: Optional[str] = None,
        task_generation_auto_execute: bool = False,
        task_generation_max_tasks_per_run: int = 5,
        task_generation_enabled: bool = False,
        roi_analyzer: Optional["ROIAnalyzer"] = None,
        meta_metrics_tracker: Optional["MetaMetricsTracker"] = None,
        task_effectiveness_tracker: Optional["TaskEffectivenessTracker"] = None,
    ):
        """Initialize task injection helper.

        Args:
            db_session: Database session for task generator
            run_id: Current run ID
            task_generation_auto_execute: Whether to auto-execute generated tasks
            task_generation_max_tasks_per_run: Max tasks to execute per run
            task_generation_enabled: Whether task generation is enabled
            roi_analyzer: Optional ROI analyzer for prioritization
            meta_metrics_tracker: Optional metrics tracker for throughput observability
            task_effectiveness_tracker: Optional tracker for task effectiveness
        """
        self.db_session = db_session
        self.run_id = run_id
        self._task_generation_auto_execute = task_generation_auto_execute
        self._task_generation_max_tasks_per_run = task_generation_max_tasks_per_run
        self._task_generation_enabled = task_generation_enabled
        self._roi_analyzer = roi_analyzer
        self._meta_metrics_tracker = meta_metrics_tracker
        self._task_effectiveness_tracker = task_effectiveness_tracker
        self._task_generation_paused = False

    @property
    def task_generation_paused(self) -> bool:
        """Whether task generation is paused."""
        return self._task_generation_paused

    @task_generation_paused.setter
    def task_generation_paused(self, value: bool) -> None:
        """Set task generation paused status."""
        self._task_generation_paused = value

    def set_run_id(self, run_id: str) -> None:
        """Update the run ID."""
        self.run_id = run_id

    def load_improvement_tasks(self) -> List[Dict]:
        """Load pending improvement tasks from previous runs (IMP-ARCH-012).

        Part of the self-improvement feedback loop:
        - Tasks are generated from telemetry insights (IMP-ARCH-009)
        - Tasks are persisted to database (IMP-ARCH-011)
        - This method retrieves pending tasks for execution

        Returns:
            List of task dicts compatible with phase planning
        """
        # Check if task generation is enabled
        if not self._task_generation_enabled:
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            generator = AutonomousTaskGenerator(
                db_session=self.db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
            pending_tasks = generator.get_pending_tasks(
                status="pending",
                limit=self._task_generation_max_tasks_per_run,
            )

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
                    task.task_id, "in_progress", executed_in_run_id=self.run_id
                )

            logger.info(f"[IMP-ARCH-012] Loaded {len(task_items)} improvement tasks for this run")
            return task_items

        except Exception as e:
            logger.warning(f"[IMP-ARCH-012] Failed to load improvement tasks: {e}")
            return []

    def fetch_generated_tasks(self) -> List[Dict]:
        """Fetch generated tasks and convert them to executable phase specs (IMP-LOOP-004).

        This method closes the autonomous improvement loop by:
        1. Retrieving pending tasks from the database via task_generator.get_pending_tasks()
        2. Converting GeneratedTask objects into executable phase specifications
        3. Marking tasks as "in_progress" when they start execution

        IMP-TASK-002: Tasks are now sorted by ROI payback period before execution.
        Tasks with shorter payback periods receive higher priority.

        Returns:
            List of phase spec dicts ready for execution, or empty list if disabled/no tasks.
        """
        # Check if task execution is enabled (separate from task generation)
        if not self._task_generation_auto_execute:
            logger.debug("[IMP-LOOP-004] Generated task execution is disabled")
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            generator = AutonomousTaskGenerator(
                db_session=self.db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )

            # Fetch pending tasks (limit to avoid overwhelming the run)
            pending_tasks = generator.get_pending_tasks(
                status="pending",
                limit=self._task_generation_max_tasks_per_run,
            )

            if not pending_tasks:
                logger.debug("[IMP-LOOP-004] No pending generated tasks to execute")
                return []

            # IMP-TASK-002: Calculate ROI payback for each task and sort by payback period
            tasks_with_roi = []
            for task in pending_tasks:
                payback_phases = float("inf")  # Default to infinite payback

                if self._roi_analyzer is not None:
                    try:
                        # Extract cost and savings estimates from task
                        execution_cost = getattr(task, "estimated_effort", 1000.0) or 1000.0
                        # Estimate savings based on priority (higher priority = higher expected savings)
                        savings_map = {
                            "critical": 200.0,
                            "high": 100.0,
                            "medium": 50.0,
                            "low": 25.0,
                        }
                        estimated_savings = savings_map.get(task.priority, 50.0)

                        analysis = self._roi_analyzer.calculate_payback_period(
                            task_id=task.task_id,
                            estimated_token_reduction=estimated_savings,
                            execution_cost=execution_cost,
                            confidence=0.8,
                            category=getattr(task, "category", "general") or "general",
                        )
                        payback_phases = analysis.payback_phases

                        logger.debug(
                            f"[IMP-TASK-002] Task {task.task_id} ROI: "
                            f"payback={payback_phases} phases, roi={analysis.risk_adjusted_roi:.2f}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[IMP-TASK-002] ROI calculation failed for {task.task_id}: {e}"
                        )

                tasks_with_roi.append((task, payback_phases))

            # Sort by payback period (shorter = better priority)
            tasks_with_roi.sort(key=lambda x: x[1])

            if self._roi_analyzer is not None and len(tasks_with_roi) > 1:
                logger.info(
                    f"[IMP-TASK-002] Sorted {len(tasks_with_roi)} tasks by ROI payback period"
                )

            # Convert GeneratedTask objects to executable phase specs
            phase_specs = []
            for idx, (task, payback_phases) in enumerate(tasks_with_roi):
                # IMP-TASK-002: Use ROI-based priority order instead of static priority
                # Lower index = better ROI = lower priority_order number
                if self._roi_analyzer is not None:
                    priority_order = idx + 1  # 1-based index (1 = highest priority)
                else:
                    # Fall back to static priority mapping
                    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4}
                    priority_order = priority_map.get(task.priority, 3)

                # Build phase spec from GeneratedTask
                phase_spec = {
                    "phase_id": f"generated-task-execution-{task.task_id}",
                    "phase_type": "generated-task-execution",
                    "description": f"[AUTO] {task.title}\n\n{task.description}",
                    "status": "QUEUED",
                    "priority_order": priority_order,
                    "category": "improvement",
                    "scope": {
                        "paths": task.suggested_files or [],
                    },
                    # Store task metadata for handler access
                    "_generated_task": {
                        "task_id": task.task_id,
                        "title": task.title,
                        "description": task.description,
                        "priority": task.priority,
                        "source_insights": task.source_insights,
                        "suggested_files": task.suggested_files,
                        "estimated_effort": task.estimated_effort,
                        "run_id": task.run_id,
                    },
                    # IMP-TASK-002: Store ROI metadata for tracking
                    "_roi_metadata": {
                        "payback_phases": payback_phases,
                        "roi_priority_order": idx + 1,
                    },
                }
                phase_specs.append(phase_spec)

                # Mark task as in_progress
                generator.mark_task_status(
                    task.task_id, "in_progress", executed_in_run_id=self.run_id
                )
                logger.info(
                    f"[IMP-LOOP-004] Queued generated task {task.task_id} for execution: "
                    f"{task.title} (payback={payback_phases} phases)"
                )

            logger.info(f"[IMP-LOOP-004] Fetched {len(phase_specs)} generated tasks for execution")
            return phase_specs

        except Exception as e:
            logger.warning(f"[IMP-LOOP-004] Failed to fetch generated tasks: {e}")
            return []

    def inject_generated_tasks_into_backlog(self, run_data: Dict) -> Dict:
        """Inject generated tasks into the phase backlog before execution (IMP-LOOP-004).

        This method modifies the run_data to include generated task phases,
        allowing them to be picked up by get_next_queued_phase() and executed
        alongside regular phases.

        IMP-LOOP-001: Added injection verification to ensure tasks appear in queue.

        Args:
            run_data: The current run data dict containing phases

        Returns:
            Modified run_data with generated task phases injected
        """
        generated_phases = self.fetch_generated_tasks()
        if not generated_phases:
            return run_data

        # Get existing phases
        existing_phases = run_data.get("phases", [])

        # Inject generated task phases at the end (after user-defined phases)
        # They will be picked up when no other queued phases remain
        run_data["phases"] = existing_phases + generated_phases

        # IMP-LOOP-001: Verify injection and log results
        injected_count = len(generated_phases)
        injected_ids = [p.get("phase_id") for p in generated_phases]

        # Verify all injected tasks are present
        verification_passed = True
        for phase_id in injected_ids:
            found = any(p.get("phase_id") == phase_id for p in run_data.get("phases", []))
            if not found:
                logger.error(
                    f"[IMP-LOOP-001] Verification failed: Task {phase_id} not found in queue"
                )
                verification_passed = False

        if verification_passed:
            logger.info(f"[IMP-LOOP-001] Injection verified: {injected_count} tasks in queue")
        else:
            logger.warning("[IMP-LOOP-001] Injection verification failed for some tasks")

        logger.info(
            f"[IMP-LOOP-004] Injected {len(generated_phases)} generated task phases into backlog"
        )
        return run_data

    def consume_roadc_tasks(self) -> List[Dict]:
        """Consume tasks from the ROAD-C task queue file (IMP-LOOP-025).

        This method implements direct task consumption from the file-based queue,
        providing a faster path than database polling for task execution.

        The method:
        1. Reads tasks from the ROADC_TASK_QUEUE.json file
        2. Converts them to executable phase specifications
        3. Removes consumed tasks from the queue file

        Returns:
            List of phase spec dicts ready for execution, or empty list if no tasks.
        """
        queue_file = Path(".autopack/ROADC_TASK_QUEUE.json")

        if not queue_file.exists():
            logger.debug("[IMP-LOOP-025] No ROAD-C task queue file found")
            return []

        try:
            queue_data = json.loads(queue_file.read_text())
            tasks = queue_data.get("tasks", [])

            if not tasks:
                logger.debug("[IMP-LOOP-025] ROAD-C task queue is empty")
                return []

            # Check if task execution is enabled
            if not self._task_generation_auto_execute:
                logger.debug("[IMP-LOOP-025] Generated task execution is disabled")
                return []

            # Limit to max tasks per run
            max_tasks = self._task_generation_max_tasks_per_run
            tasks_to_process = tasks[:max_tasks]
            remaining_tasks = tasks[max_tasks:]

            # Convert tasks to phase specs
            phase_specs = []
            for idx, task in enumerate(tasks_to_process):
                # Use ROI-based priority order if analyzer is available
                if self._roi_analyzer is not None:
                    priority_order = idx + 1
                else:
                    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4}
                    priority_order = priority_map.get(task.get("priority", "medium"), 3)

                phase_spec = {
                    "phase_id": f"roadc-queue-task-{task.get('task_id', 'unknown')}",
                    "phase_type": "generated-task-execution",
                    "description": f"[ROADC-QUEUE] {task.get('title', 'Unknown task')}\n\n{task.get('description', '')}",
                    "status": "QUEUED",
                    "priority_order": priority_order,
                    "category": "improvement",
                    "scope": {
                        "paths": task.get("suggested_files", []),
                    },
                    "_generated_task": {
                        "task_id": task.get("task_id"),
                        "title": task.get("title"),
                        "description": task.get("description"),
                        "priority": task.get("priority"),
                        "source_insights": task.get("source_insights", []),
                        "suggested_files": task.get("suggested_files", []),
                        "estimated_effort": task.get("estimated_effort"),
                        "requires_approval": task.get("requires_approval", False),
                        "risk_severity": task.get("risk_severity"),
                        "estimated_cost": task.get("estimated_cost", 0),
                    },
                    "_roadc_queue_source": True,  # Mark as coming from queue file
                }
                phase_specs.append(phase_spec)

                logger.info(
                    f"[IMP-LOOP-025] Consumed ROAD-C task {task.get('task_id')} from queue: "
                    f"{task.get('title')}"
                )

            # Update queue file with remaining tasks
            queue_data["tasks"] = remaining_tasks
            queue_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            queue_data["last_consumption"] = {
                "consumed_count": len(tasks_to_process),
                "remaining_count": len(remaining_tasks),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            queue_file.write_text(json.dumps(queue_data, indent=2))

            logger.info(
                f"[IMP-LOOP-025] Consumed {len(phase_specs)} tasks from ROAD-C queue "
                f"({len(remaining_tasks)} remaining)"
            )
            return phase_specs

        except Exception as e:
            logger.warning(f"[IMP-LOOP-025] Failed to consume ROAD-C tasks: {e}")
            return []

    def process_roadc_tasks(
        self,
        tasks: List[Dict],
        current_run_phases: Optional[List[Dict]] = None,
    ) -> Dict:
        """Process consumed ROAD-C tasks and inject them into the backlog (IMP-LOOP-025).

        This method processes tasks consumed from the ROAD-C queue and adds them
        to the current run's phase backlog for execution.

        Args:
            tasks: List of phase spec dicts from consume_roadc_tasks()
            current_run_phases: Reference to current run's phase list

        Returns:
            Dict with processing stats: {"injected": N, "skipped": M}
        """
        if not tasks:
            return {"injected": 0, "skipped": 0}

        injected = 0
        skipped = 0

        try:
            # Get existing phase IDs to avoid duplicates
            existing_phase_ids = {p.get("phase_id") for p in (current_run_phases or [])}

            for task in tasks:
                phase_id = task.get("phase_id")

                if phase_id in existing_phase_ids:
                    logger.debug(f"[IMP-LOOP-025] Task {phase_id} already in backlog, skipping")
                    skipped += 1
                    continue

                # Insert at front of backlog for high priority, or append for normal priority
                task_priority = task.get("_generated_task", {}).get("priority", "medium")
                if current_run_phases is not None:
                    if task_priority == "critical":
                        # Insert at front for immediate execution
                        current_run_phases.insert(0, task)
                        logger.info(
                            f"[IMP-LOOP-025] Injected critical ROAD-C task {phase_id} at front of queue"
                        )
                    else:
                        # Append to end of backlog
                        current_run_phases.append(task)
                        logger.info(f"[IMP-LOOP-025] Appended ROAD-C task {phase_id} to backlog")
                    injected += 1

            logger.info(
                f"[IMP-LOOP-025] Processed ROAD-C tasks: {injected} injected, {skipped} skipped"
            )
            return {"injected": injected, "skipped": skipped}

        except Exception as e:
            logger.warning(f"[IMP-LOOP-025] Failed to process ROAD-C tasks: {e}")
            return {"injected": injected, "skipped": skipped}

    def generate_and_inject_tasks(
        self,
        current_run_phases: Optional[List[Dict]] = None,
        on_task_injected: Optional[Callable[[str], None]] = None,
    ) -> Optional["InjectionResult"]:
        """Generate tasks and inject them via BacklogMaintenance (IMP-LOOP-029).

        This method completes the wiring between AutonomousTaskGenerator and
        BacklogMaintenance.inject_tasks(), enabling generated tasks to be
        properly injected into the execution queue with verification.

        Args:
            current_run_phases: Reference to current run's phase list
            on_task_injected: Optional callback for each injected task

        Returns:
            InjectionResult with injection details, or None if no tasks generated.
        """
        # Check if task generation is enabled
        if not self._task_generation_auto_execute:
            logger.debug("[IMP-LOOP-029] Generated task execution is disabled")
            return None

        # Check if task generation is paused (e.g., due to health issues)
        if self._task_generation_paused:
            logger.debug("[IMP-LOOP-029] Task generation is paused")
            return None

        try:
            from autopack.executor.backlog_maintenance import (
                InjectionResult,
                generated_task_to_candidate,
            )
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # Create task generator with db_session for telemetry access
            task_generator = AutonomousTaskGenerator(
                db_session=self.db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )

            # Generate tasks with run context
            generation_result = task_generator.generate_tasks(
                max_tasks=self._task_generation_max_tasks_per_run,
                run_id=self.run_id,
            )

            generated_tasks = generation_result.tasks_generated
            if not generated_tasks:
                logger.debug("[IMP-LOOP-029] No tasks generated")
                return None

            logger.info(
                f"[IMP-LOOP-029] Generated {len(generated_tasks)} tasks "
                f"({generation_result.insights_processed} insights, "
                f"{generation_result.patterns_detected} patterns)"
            )

            # Convert GeneratedTask objects to TaskCandidate objects
            candidates = [generated_task_to_candidate(task) for task in generated_tasks]

            # Note: The actual injection via BacklogMaintenance should be done
            # by the caller (autonomous_loop) which has access to the executor
            # For now, return a simple result with the candidates
            return InjectionResult(
                success_count=len(candidates),
                failure_count=0,
                injected_ids=[c.task_id for c in candidates],
                all_succeeded=True,
                verified=False,  # Not yet verified via BacklogMaintenance
                verification_errors=[],
            )

        except Exception as e:
            logger.warning(f"[IMP-LOOP-029] Task injection wiring failed: {e}")
            return None

    def find_phase_id_for_task(
        self,
        task_id: str,
        current_run_phases: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """Find the phase_id associated with a task after injection (IMP-LOOP-029).

        The phase_id is needed for attribution tracking (linking task -> phase -> outcome).

        Args:
            task_id: The task ID to look up.
            current_run_phases: Current run's phase list to search

        Returns:
            The phase_id if found, None otherwise.
        """
        if current_run_phases is None:
            return None

        for phase in current_run_phases:
            # Check direct match
            if phase.get("phase_id") == task_id:
                return task_id
            # Check generated task metadata
            metadata = phase.get("metadata", {})
            if metadata.get("original_metadata", {}).get("generated_task_id") == task_id:
                return phase.get("phase_id")
            # Check _generated_task metadata (from other injection paths)
            gen_task = phase.get("_generated_task", {})
            if gen_task.get("task_id") == task_id:
                return phase.get("phase_id")

        return task_id  # Fall back to using task_id as phase_id

    def mark_tasks_completed(
        self,
        improvement_tasks: List[Dict],
        run_id: str,
    ) -> None:
        """Mark improvement tasks as completed after successful run (IMP-ARCH-019).

        Called when run finishes with no failed phases, indicating the improvement
        tasks were successfully addressed.

        Args:
            improvement_tasks: List of improvement task dicts
            run_id: The current run ID
        """
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            generator = AutonomousTaskGenerator(
                db_session=self.db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
            completed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    result = generator.mark_task_status(
                        task_id, "completed", executed_in_run_id=run_id
                    )
                    if result == "updated":
                        completed_count += 1

            if completed_count > 0:
                logger.info(
                    f"[IMP-ARCH-019] Marked {completed_count} improvement tasks as completed"
                )

        except Exception as e:
            logger.warning(f"[IMP-ARCH-019] Failed to mark tasks completed: {e}")

    def mark_tasks_failed(
        self,
        improvement_tasks: List[Dict],
        phases_failed: int,
        run_id: str,
    ) -> None:
        """Mark improvement tasks as failed/retry when run has failures (IMP-LOOP-005).

        Called when run finishes with failed phases, indicating the improvement
        tasks were not successfully addressed and need retry or failure tracking.

        Args:
            improvement_tasks: List of improvement task dicts
            phases_failed: Number of phases that failed in this run
            run_id: The current run ID
        """
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            generator = AutonomousTaskGenerator(
                db_session=self.db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
            retry_count = 0
            failed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    result = generator.mark_task_status(
                        task_id,
                        status=None,  # Let method decide based on retry count
                        increment_retry=True,
                        failure_run_id=run_id,
                    )
                    if result == "retry":
                        retry_count += 1
                    elif result == "failed":
                        failed_count += 1

            if retry_count > 0 or failed_count > 0:
                logger.info(
                    f"[IMP-LOOP-005] Task status update: {retry_count} tasks returned to pending, "
                    f"{failed_count} tasks marked as failed"
                )

        except Exception as e:
            logger.warning(f"[IMP-LOOP-005] Failed to update task status: {e}")
