"""Autonomous execution loop for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles the main autonomous execution loop that processes backlog phases.

IMP-AUTO-002: Extended to support parallel phase execution when file scopes don't overlap.
IMP-MAINT-002: Modularized - CircuitBreaker extracted to circuit_breaker.py.
IMP-MAINT-002: FeedbackContextRetriever and TelemetryPersistenceManager extracted
              to feedback_context.py and telemetry_persistence.py respectively.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from autopack.archive_consolidator import log_build_event
from autopack.autonomous.budgeting import (
    BudgetExhaustedError,
    get_budget_remaining_pct,
    is_budget_exhausted,
)
from autopack.autonomy.parallelism_gate import ParallelismPolicyGate, ScopeBasedParallelismChecker
from autopack.config import settings
from autopack.database import SESSION_HEALTH_CHECK_INTERVAL, ensure_session_healthy
from autopack.executor.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
    SOTDriftError,
)
from autopack.executor.feedback_context import FeedbackContextRetriever
from autopack.executor.log_sanitizer import LogSanitizer
from autopack.executor.loop_telemetry_integration import LoopTelemetryIntegration
from autopack.executor.telemetry_persistence import TelemetryPersistenceManager
from autopack.feedback_pipeline import FeedbackPipeline
from autopack.generation.autonomous_wave_planner import AutonomousWavePlanner, WavePlan
from autopack.learned_rules import promote_hints_to_rules
from autopack.memory import extract_goal_from_description
from autopack.memory.context_injector import ContextInjector
from autopack.memory.maintenance import run_maintenance_if_due
from autopack.task_generation.roi_analyzer import ROIAnalyzer
from autopack.task_generation.task_effectiveness_tracker import TaskEffectivenessTracker
from autopack.telemetry.analyzer import CostRecommendation, TelemetryAnalyzer
from autopack.telemetry.anomaly_detector import TelemetryAnomalyDetector
from autopack.telemetry.meta_metrics import (
    FeedbackLoopHealth,
    GoalDriftDetector,
    MetaMetricsTracker,
    PipelineLatencyTracker,
    PipelineStage,
)
from autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor
    from autopack.executor.backlog_maintenance import InjectionResult

logger = logging.getLogger(__name__)

# IMP-REL-004: Default max iteration limit for the execution loop
# This prevelnts unbounded loops when max_iterations is not explicitly set
DEFAULT_MAX_ITERATIONS = 10000


class AutonomousLoop:
    """Main autonomous execution loop.

    Responsibilities:
    1. Process backlog phases sequentially or in parallel
    2. Handle phase execution orchestration
    3. Monitor execution health
    4. Handle loop termination conditions

    IMP-AUTO-002: Extended to support parallel phase execution when file scopes don't overlap.
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor
        self.poll_interval = 0.5  # Base polling interval
        self.idle_backoff_multiplier = 2.0  # Backoff when idle
        self.max_idle_sleep = 5.0  # Maximum sleep time when idle
        self._last_session_health_check = time.time()  # Track last health check
        self._telemetry_analyzer: Optional[TelemetryAnalyzer] = None

        # IMP-INT-002: TelemetryToMemoryBridge for persisting insights after aggregation
        self._telemetry_to_memory_bridge: Optional[TelemetryToMemoryBridge] = None

        # IMP-PERF-002: Context ceiling tracking
        # Prevents unbounded context injection across phases
        self._total_context_tokens = 0
        self._context_ceiling = settings.context_ceiling_tokens

        # IMP-LOOP-006: Circuit breaker for runaway execution protection
        # Tracks consecutive failures and trips when threshold exceeded
        self._circuit_breaker: Optional[CircuitBreaker] = None
        if settings.circuit_breaker_enabled:
            self._circuit_breaker = CircuitBreaker(
                failure_threshold=settings.circuit_breaker_failure_threshold,
                reset_timeout_seconds=settings.circuit_breaker_reset_timeout_seconds,
                half_open_max_calls=settings.circuit_breaker_half_open_max_calls,
            )
            logger.info(
                f"[IMP-LOOP-006] Circuit breaker initialized "
                f"(threshold={settings.circuit_breaker_failure_threshold}, "
                f"reset={settings.circuit_breaker_reset_timeout_seconds}s)"
            )

        # IMP-LOOP-006: Iteration counter for loop tracking
        self._iteration_count = 0
        self._total_phases_executed = 0
        self._total_phases_failed = 0

        # IMP-AUTO-002: Scope-based parallel execution support
        self._parallelism_checker: Optional[ScopeBasedParallelismChecker] = None
        self._parallel_execution_enabled = getattr(
            settings, "parallel_phase_execution_enabled", False
        )
        self._max_parallel_phases = getattr(settings, "max_parallel_phases", 2)
        self._parallel_phases_executed = 0
        self._parallel_phases_skipped = 0

        # IMP-LOOP-011: Feedback pipeline is MANDATORY for self-improvement loop
        self._feedback_pipeline: Optional[FeedbackPipeline] = None
        _settings_value = getattr(settings, "feedback_pipeline_enabled", True)
        if not _settings_value:
            logger.warning(
                "[IMP-LOOP-011] feedback_pipeline_enabled=False in settings. "
                "FeedbackPipeline is critical for the self-improvement loop. "
                "Override ignored - pipeline remains enabled."
            )
        self._feedback_pipeline_enabled = True  # Always enabled

        # IMP-INT-001: Telemetry aggregation tracking for self-improvement loop
        # Controls how often aggregate_telemetry() is called during execution
        self._telemetry_aggregation_interval = getattr(
            settings, "telemetry_aggregation_interval", 3
        )  # Aggregate every N phases
        self._phases_since_last_aggregation = 0

        # IMP-FBK-001: Task effectiveness tracker for closed-loop learning
        # Records task outcomes and feeds back to priority engine
        self._task_effectiveness_tracker: Optional[TaskEffectivenessTracker] = None
        self._task_effectiveness_enabled = getattr(
            settings, "task_effectiveness_tracking_enabled", True
        )

        # IMP-LOOP-017: Automated memory maintenance scheduling
        # Tracks last maintenance check to avoid repeated checks every iteration
        self._last_maintenance_check = 0.0  # Timestamp of last check
        self._maintenance_check_interval = getattr(
            settings,
            "maintenance_check_interval_seconds",
            300.0,  # Check every 5 minutes
        )
        self._auto_maintenance_enabled = getattr(settings, "auto_memory_maintenance_enabled", True)

        # IMP-MEM-011: Write-count based maintenance triggering
        # Triggers maintenance after N memory writes to prevent unbounded growth
        self._memory_write_count = 0  # Total memory writes since last maintenance
        self._maintenance_write_threshold = getattr(
            settings,
            "maintenance_write_threshold",
            100,  # Trigger after 100 writes
        )
        self._last_maintenance_write_count = 0  # Write count at last maintenance

        # IMP-FBK-002: Meta-metrics and anomaly detection for circuit breaker health checks
        # These enable holistic health assessment before circuit breaker reset
        self._meta_metrics_tracker: Optional[MetaMetricsTracker] = None
        self._anomaly_detector: Optional[TelemetryAnomalyDetector] = None
        self._meta_metrics_enabled = getattr(settings, "meta_metrics_health_check_enabled", True)

        # Initialize health providers and wire to circuit breaker
        if self._meta_metrics_enabled:
            self._meta_metrics_tracker = MetaMetricsTracker()
            self._anomaly_detector = TelemetryAnomalyDetector()
            logger.info("[IMP-FBK-002] Meta-metrics health check initialized for circuit breaker")

            # Wire health providers to circuit breaker
            if self._circuit_breaker is not None:
                health_threshold = getattr(settings, "circuit_breaker_health_threshold", 0.5)
                self._circuit_breaker.health_threshold = health_threshold
                self._circuit_breaker.set_health_providers(
                    meta_metrics_tracker=self._meta_metrics_tracker,
                    anomaly_detector=self._anomaly_detector,
                )
                logger.info(
                    f"[IMP-FBK-002] Circuit breaker health providers wired "
                    f"(threshold={health_threshold})"
                )

        # IMP-LOOP-003: Reference to current run's phases for same-run task injection
        # This is set during _execute_phases and allows high-priority generated tasks
        # to be injected into the current run's backlog for immediate execution
        self._current_run_phases: Optional[List[Dict]] = None

        # IMP-REL-001: Task generation pause flag for auto-remediation
        # When True, task generation is paused due to ATTENTION_REQUIRED health status
        self._task_generation_paused: bool = False

        # IMP-TELE-001: Pipeline latency tracker for loop cycle time measurement
        # Tracks timestamps across pipeline stages to diagnose bottlenecks
        self._latency_tracker: Optional[PipelineLatencyTracker] = None

        # IMP-LOOP-023: Goal drift detector for self-improvement alignment monitoring
        # Detects when generated tasks drift from stated improvement objectives
        self._goal_drift_detector: Optional[GoalDriftDetector] = None
        self._goal_drift_enabled = getattr(settings, "goal_drift_detection_enabled", True)
        self._goal_drift_threshold = getattr(settings, "goal_drift_threshold", 0.3)
        if self._goal_drift_enabled:
            self._goal_drift_detector = GoalDriftDetector(
                drift_threshold=self._goal_drift_threshold
            )
            logger.info(
                f"[IMP-LOOP-023] Goal drift detector initialized "
                f"(threshold={self._goal_drift_threshold})"
            )

        # IMP-TASK-002: ROI analyzer for economic prioritization of generated tasks
        # Tasks with shorter payback periods receive higher priority
        self._roi_analyzer: Optional[ROIAnalyzer] = None
        self._roi_prioritization_enabled = getattr(
            settings, "roi_task_prioritization_enabled", True
        )
        if self._roi_prioritization_enabled:
            self._roi_analyzer = ROIAnalyzer(
                effectiveness_tracker=self._task_effectiveness_tracker,
                phases_horizon=getattr(settings, "roi_phases_horizon", 100),
            )
            logger.info("[IMP-TASK-002] ROI analyzer initialized for task prioritization")

        # IMP-LOOP-027: Wave planner integration for parallel IMP wave execution
        # The wave planner groups IMPs into waves that can be executed in parallel
        # while respecting dependencies and file conflicts
        self._wave_planner: Optional[AutonomousWavePlanner] = None
        self._current_wave_plan: Optional[WavePlan] = None
        self._current_wave_number: int = 0
        self._wave_phases_loaded: Dict[int, List[Dict]] = {}  # wave_number -> loaded phases
        self._wave_phases_completed: Dict[int, List[str]] = {}  # wave_number -> completed phase_ids
        self._wave_planner_enabled = getattr(settings, "wave_planner_enabled", True)
        self._wave_plan_path: Optional[Path] = None

        # IMP-MAINT-002: Initialize helper classes for modularized functionality
        # FeedbackContextRetriever handles feedback pipeline context retrieval
        self._feedback_context_retriever = FeedbackContextRetriever(
            feedback_pipeline=self._feedback_pipeline,
            feedback_pipeline_enabled=self._feedback_pipeline_enabled,
        )

        # TelemetryPersistenceManager handles telemetry aggregation and persistence
        self._telemetry_persistence_manager = TelemetryPersistenceManager(
            db_session=getattr(executor, "db_session", None),
            memory_service=getattr(executor, "memory_service", None),
            aggregation_interval=self._telemetry_aggregation_interval,
            latency_tracker=self._latency_tracker,
            meta_metrics_tracker=self._meta_metrics_tracker,
        )

        # IMP-MAINT-004: LoopTelemetryIntegration handles circuit breaker health,
        # task effectiveness, anomaly detection, adjustments, and cost recommendations
        self._telemetry_integration = LoopTelemetryIntegration(
            circuit_breaker=self._circuit_breaker,
            meta_metrics_tracker=self._meta_metrics_tracker,
            anomaly_detector=self._anomaly_detector,
            meta_metrics_enabled=self._meta_metrics_enabled,
            task_effectiveness_enabled=self._task_effectiveness_enabled,
            get_telemetry_analyzer=self._get_telemetry_analyzer,
            emit_alert=self._emit_alert,
        )

    def get_loop_stats(self) -> Dict:
        """Get current loop statistics for monitoring (IMP-LOOP-006, IMP-AUTO-002).

        Returns:
            Dictionary with iteration count, phase counts, circuit breaker stats,
            and parallel execution stats.
        """
        stats = {
            "iteration_count": self._iteration_count,
            "total_phases_executed": self._total_phases_executed,
            "total_phases_failed": self._total_phases_failed,
            "context_tokens_used": self._total_context_tokens,
            "context_ceiling": self._context_ceiling,
        }

        if self._circuit_breaker is not None:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()

        # IMP-AUTO-002: Add parallel execution statistics
        stats["parallel_execution"] = {
            "enabled": self._parallel_execution_enabled,
            "max_parallel_phases": self._max_parallel_phases,
            "parallel_phases_executed": self._parallel_phases_executed,
            "parallel_phases_skipped": self._parallel_phases_skipped,
        }

        # IMP-LOOP-001: Add feedback pipeline statistics
        if self._feedback_pipeline is not None:
            stats["feedback_pipeline"] = self._feedback_pipeline.get_stats()
        else:
            stats["feedback_pipeline"] = {"enabled": self._feedback_pipeline_enabled}

        # IMP-FBK-001: Add task effectiveness statistics
        if self._task_effectiveness_tracker is not None:
            stats["task_effectiveness"] = self._task_effectiveness_tracker.get_summary()
        else:
            stats["task_effectiveness"] = {"enabled": self._task_effectiveness_enabled}

        # IMP-REL-001: Add task generation pause status
        stats["task_generation_paused"] = self._task_generation_paused

        # IMP-TELE-001: Add pipeline latency tracking statistics
        if self._latency_tracker is not None:
            stats["pipeline_latency"] = self._latency_tracker.to_dict()
        else:
            stats["pipeline_latency"] = {"enabled": False}

        # IMP-LOOP-027: Add wave planner statistics
        stats["wave_planner"] = {
            "enabled": self._wave_planner_enabled,
            "current_wave_number": self._current_wave_number,
            "total_waves": (len(self._current_wave_plan.waves) if self._current_wave_plan else 0),
            "waves_loaded": len(self._wave_phases_loaded),
            "waves_completed": sum(
                1
                for wave_num, completed in self._wave_phases_completed.items()
                if wave_num in self._wave_phases_loaded
                and len(completed) >= len(self._wave_phases_loaded.get(wave_num, []))
            ),
        }

        # IMP-LOOP-025: Add task generation throughput and wiring verification
        if self._meta_metrics_tracker is not None:
            try:
                throughput = self._meta_metrics_tracker.get_task_generation_throughput()
                wiring_status = self._meta_metrics_tracker.verify_execution_wiring()
                stats["task_generation_throughput"] = throughput.to_dict()
                stats["execution_wiring"] = wiring_status
            except Exception as e:
                logger.debug(f"[IMP-LOOP-025] Failed to get throughput stats: {e}")
                stats["task_generation_throughput"] = {"error": str(e)}
                stats["execution_wiring"] = {"error": str(e)}
        else:
            stats["task_generation_throughput"] = {"enabled": False}
            stats["execution_wiring"] = {"enabled": False}

        return stats

    def reset_circuit_breaker(self) -> bool:
        """Manually reset the circuit breaker (IMP-LOOP-006).

        Use with caution - typically the circuit should auto-reset via timeout.

        Returns:
            True if circuit breaker was reset, False if not enabled
        """
        if self._circuit_breaker is not None:
            self._circuit_breaker.reset()
            return True
        return False

    def queue_contains(self, task_id: str) -> bool:
        """Check if a task is present in the execution queue (IMP-LOOP-001).

        Searches the current phase list for a phase with the given ID.

        Args:
            task_id: The task/phase ID to search for.

        Returns:
            True if task is found in queue, False otherwise.
        """
        if self._current_run_phases is None:
            return False

        for phase in self._current_run_phases:
            if phase.get("phase_id") == task_id:
                return True

        return False

    def get_queued_task_ids(self) -> List[str]:
        """Get list of all queued task IDs (IMP-LOOP-001).

        Returns:
            List of phase_ids for phases with QUEUED status.
        """
        if self._current_run_phases is None:
            return []

        return [
            p.get("phase_id")
            for p in self._current_run_phases
            if p.get("status", "").upper() == "QUEUED" and p.get("phase_id")
        ]

    def get_injection_stats(self) -> Dict[str, int]:
        """Get statistics about injected tasks (IMP-LOOP-001).

        Returns:
            Dictionary with counts of total phases, queued phases,
            and generated (injected) tasks.
        """
        stats = {
            "total_phases": 0,
            "queued_count": 0,
            "generated_task_count": 0,
        }

        if self._current_run_phases is None:
            return stats

        stats["total_phases"] = len(self._current_run_phases)

        for phase in self._current_run_phases:
            if phase.get("status", "").upper() == "QUEUED":
                stats["queued_count"] += 1

            metadata = phase.get("metadata", {})
            if metadata.get("generated_task"):
                stats["generated_task_count"] += 1

        return stats

    # =========================================================================
    # IMP-LOOP-027: Wave Planner Integration
    # =========================================================================

    def _initialize_wave_planner(self, wave_plan_path: Optional[Path] = None) -> bool:
        """Initialize the wave planner with discovered IMPs or from a wave plan file.

        IMP-LOOP-027: Loads wave plan from file if provided, otherwise attempts
        to discover IMPs and generate a wave plan dynamically.

        Args:
            wave_plan_path: Optional path to an existing wave plan JSON file.

        Returns:
            True if wave planner was successfully initialized, False otherwise.
        """
        if not self._wave_planner_enabled:
            logger.info("[IMP-LOOP-027] Wave planner is disabled in settings")
            return False

        try:
            # Try to load from file first
            if wave_plan_path and wave_plan_path.exists():
                self._wave_plan_path = wave_plan_path
                import json

                plan_data = json.loads(wave_plan_path.read_text())

                # Reconstruct IMPs from wave plan file
                discovered_imps = []
                for wave_data in plan_data.get("waves", []):
                    for phase in wave_data.get("phases", []):
                        discovered_imps.append(
                            {
                                "imp_id": phase.get("imp_id"),
                                "title": phase.get("title", ""),
                                "files_affected": phase.get("files", []),
                                "dependencies": phase.get("dependencies", []),
                            }
                        )

                if discovered_imps:
                    self._wave_planner = AutonomousWavePlanner(discovered_imps)
                    self._current_wave_plan = self._wave_planner.plan_waves()
                    logger.info(
                        f"[IMP-LOOP-027] Wave planner loaded from {wave_plan_path}: "
                        f"{len(self._current_wave_plan.waves)} waves, "
                        f"{len(discovered_imps)} IMPs"
                    )
                    return True

            # Try default wave plan path
            default_path = Path(".autopack/AUTOPACK_WAVE_PLAN.json")
            if default_path.exists():
                return self._initialize_wave_planner(default_path)

            logger.debug("[IMP-LOOP-027] No wave plan file found, wave planner not initialized")
            return False

        except Exception as e:
            logger.warning(
                f"[IMP-LOOP-027] Failed to initialize wave planner: {LogSanitizer.sanitize_exception(e)}"
            )
            return False

    def _current_wave_complete(self) -> bool:
        """Check if all phases in the current wave are complete.

        IMP-LOOP-027: Compares completed phase IDs against loaded phase IDs
        for the current wave number.

        Returns:
            True if current wave is complete (or no wave is active), False otherwise.
        """
        if self._current_wave_number == 0:
            # No wave currently active
            return True

        if self._current_wave_plan is None:
            return True

        # Get phases loaded for current wave
        loaded_phases = self._wave_phases_loaded.get(self._current_wave_number, [])
        if not loaded_phases:
            return True

        # Get completed phase IDs for current wave
        completed_ids = set(self._wave_phases_completed.get(self._current_wave_number, []))

        # Check if all loaded phases are completed
        loaded_ids = {p.get("phase_id") for p in loaded_phases if p.get("phase_id")}

        is_complete = loaded_ids.issubset(completed_ids)

        if is_complete:
            logger.info(
                f"[IMP-LOOP-027] Wave {self._current_wave_number} complete: "
                f"{len(completed_ids)}/{len(loaded_ids)} phases"
            )

        return is_complete

    def _get_next_wave(self) -> Optional[Dict]:
        """Get the next wave from the wave plan.

        IMP-LOOP-027: Returns the next wave to execute after the current wave
        is complete.

        Returns:
            Wave data dictionary if next wave exists, None otherwise.
        """
        if self._current_wave_plan is None:
            return None

        next_wave_num = self._current_wave_number + 1

        if next_wave_num not in self._current_wave_plan.waves:
            logger.info(
                f"[IMP-LOOP-027] No more waves to execute (completed {self._current_wave_number} waves)"
            )
            return None

        imp_ids = self._current_wave_plan.waves[next_wave_num]

        wave_data = {
            "wave_number": next_wave_num,
            "imp_ids": imp_ids,
            "phases": [
                {
                    "imp_id": imp_id,
                    "title": self._wave_planner.imps.get(imp_id, {}).get("title", ""),
                    "files": self._wave_planner.imps.get(imp_id, {}).get("files_affected", []),
                    "dependencies": list(self._wave_planner.dependency_graph.get(imp_id, set())),
                }
                for imp_id in imp_ids
            ],
        }

        logger.info(
            f"[IMP-LOOP-027] Next wave: {next_wave_num} with {len(imp_ids)} IMPs: {imp_ids}"
        )

        return wave_data

    def _load_wave_phases(self, wave: Dict) -> int:
        """Load phases from a wave plan into the execution queue.

        IMP-LOOP-027: Converts wave IMP entries into executable phase specs
        and injects them into the current run's phase list.

        Args:
            wave: Wave data dictionary with wave_number, imp_ids, and phases.

        Returns:
            Number of phases successfully loaded into the queue.
        """
        if wave is None:
            return 0

        wave_number = wave.get("wave_number", 0)
        phases = wave.get("phases", [])

        if not phases:
            logger.warning(f"[IMP-LOOP-027] Wave {wave_number} has no phases to load")
            return 0

        loaded_phases = []
        for phase_data in phases:
            imp_id = phase_data.get("imp_id")
            if not imp_id:
                continue

            # Create executable phase spec
            phase_spec = {
                "phase_id": f"wave{wave_number}-{imp_id.lower().replace('-', '')}",
                "phase_type": "wave-imp-execution",
                "status": "QUEUED",
                "imp_id": imp_id,
                "title": phase_data.get("title", f"Execute {imp_id}"),
                "description": f"Wave {wave_number} execution of {imp_id}",
                "files_affected": phase_data.get("files", []),
                "dependencies": phase_data.get("dependencies", []),
                "metadata": {
                    "wave_number": wave_number,
                    "wave_planner_generated": True,
                    "imp_id": imp_id,
                },
            }

            loaded_phases.append(phase_spec)

        # Store loaded phases for wave completion tracking
        self._wave_phases_loaded[wave_number] = loaded_phases
        self._wave_phases_completed[wave_number] = []

        # Update current wave number
        self._current_wave_number = wave_number

        # Inject phases into the current run's phase list
        if self._current_run_phases is not None:
            # Insert wave phases at the front of the queue (high priority)
            for phase_spec in reversed(loaded_phases):
                self._current_run_phases.insert(0, phase_spec)

            logger.info(
                f"[IMP-LOOP-027] Loaded {len(loaded_phases)} phases from wave {wave_number} "
                f"into execution queue"
            )
        else:
            logger.warning("[IMP-LOOP-027] Cannot inject wave phases - no current run phases list")

        return len(loaded_phases)

    def _mark_wave_phase_complete(self, phase_id: str) -> None:
        """Mark a wave phase as complete for tracking.

        IMP-LOOP-027: Updates wave completion tracking when a phase finishes.

        Args:
            phase_id: The phase ID that completed.
        """
        if self._current_wave_number == 0:
            return

        completed_list = self._wave_phases_completed.get(self._current_wave_number, [])
        if phase_id not in completed_list:
            completed_list.append(phase_id)
            self._wave_phases_completed[self._current_wave_number] = completed_list

            loaded = len(self._wave_phases_loaded.get(self._current_wave_number, []))
            completed = len(completed_list)
            logger.debug(
                f"[IMP-LOOP-027] Wave {self._current_wave_number} progress: "
                f"{completed}/{loaded} phases complete"
            )

    def _check_and_load_next_wave(self) -> int:
        """Check if current wave is complete and load next wave if available.

        IMP-LOOP-027: Orchestrates wave transitions during the execution loop.

        Returns:
            Number of phases loaded from the next wave, or 0 if no wave transition.
        """
        if not self._wave_planner_enabled or self._wave_planner is None:
            return 0

        if not self._current_wave_complete():
            return 0

        next_wave = self._get_next_wave()
        if next_wave is None:
            return 0

        return self._load_wave_phases(next_wave)

    def _emit_alert(self, message: str) -> None:
        """Emit an alert for critical system events.

        IMP-REL-001: Logs critical events to the build log for visibility.
        Used when task generation is auto-paused due to degraded health.

        Args:
            message: The alert message to log
        """
        try:
            log_build_event(
                event_type="HEALTH_ALERT",
                description=message,
                deliverables=[
                    f"Run ID: {self.executor.run_id}",
                    f"Iteration: {self._iteration_count}",
                    f"Phases executed: {self._total_phases_executed}",
                    f"Phases failed: {self._total_phases_failed}",
                ],
                project_slug=self.executor._get_project_slug(),
            )
        except Exception as e:
            logger.warning(
                f"[IMP-REL-001] Failed to emit alert: {LogSanitizer.sanitize_exception(e)}"
            )

    def _queue_correction_tasks(
        self,
        corrective_tasks: List[Dict[str, Any]],
        generator: Any,
        run_id: str,
    ) -> None:
        """Queue corrective tasks for drift correction at front of execution queue.

        IMP-LOOP-028: When goal drift is detected, corrective tasks are generated
        and need to be queued for execution. This method inserts them at high
        priority to ensure drift is corrected before continuing normal execution.

        Args:
            corrective_tasks: List of corrective task dictionaries from realignment_action()
            generator: The task generator instance for persisting tasks
            run_id: The current run ID
        """
        if not corrective_tasks:
            return

        try:
            # Convert corrective task dicts to GeneratedTask objects if needed
            from autopack.roadc.task_generator import GeneratedTask

            generated_tasks = []
            for task_dict in corrective_tasks:
                task = GeneratedTask(
                    task_id=task_dict.get("task_id", f"drift_correction_{len(generated_tasks)}"),
                    title=task_dict.get("title", "Drift Correction Task"),
                    description=task_dict.get("description", ""),
                    priority=task_dict.get("priority", "high"),
                    source_insights=[task_dict.get("source", "goal_drift_detector")],
                    suggested_files=[],
                    estimated_effort="S",
                    metadata={
                        "type": task_dict.get("type", "drift_correction"),
                        "corrective_action": task_dict.get("corrective_action", {}),
                        "drift_score": task_dict.get("drift_score", 0.0),
                        "target_objective": task_dict.get("target_objective", ""),
                    },
                )
                generated_tasks.append(task)

            # Persist the corrective tasks with high priority
            if generated_tasks:
                persisted_count = generator.persist_tasks(generated_tasks, run_id)
                logger.info(
                    f"[IMP-LOOP-028] Persisted {persisted_count} corrective tasks for run {run_id}"
                )

                # Log the corrective action being taken
                log_build_event(
                    event_type="DRIFT_CORRECTION",
                    description=f"Generated {len(generated_tasks)} corrective tasks for goal drift",
                    deliverables=[
                        f"Run ID: {run_id}",
                        f"Corrective tasks: {[t.task_id for t in generated_tasks]}",
                    ],
                    project_slug=self.executor._get_project_slug(),
                )

        except Exception as e:
            logger.warning(
                f"[IMP-LOOP-028] Failed to queue corrective tasks: {LogSanitizer.sanitize_exception(e)}"
            )

    def _check_and_emit_sla_alerts(self, phase_id: str) -> None:
        """Check for pipeline SLA breaches and emit alerts.

        IMP-TEL-001: After phase completion, checks the pipeline latency tracker
        for any SLA breaches and emits alerts for visibility. This enables
        runtime enforcement of the 5-minute feedback loop SLA.

        Args:
            phase_id: ID of the phase that just completed
        """
        if self._latency_tracker is None:
            return

        try:
            # Check for any SLA breaches
            breaches = self._latency_tracker.check_sla_breaches()
            if not breaches:
                return

            # Get overall SLA status for logging
            sla_status = self._latency_tracker.get_sla_status()

            for breach in breaches:
                # Emit alert for each breach
                alert_message = (
                    f"[IMP-TEL-001] Pipeline SLA breach detected after phase {phase_id}: "
                    f"{breach.message} "
                    f"(level={breach.level}, actual={breach.actual_ms:.0f}ms, "
                    f"threshold={breach.threshold_ms:.0f}ms, "
                    f"breach_amount={breach.breach_amount_ms:.0f}ms)"
                )

                if breach.level == "critical":
                    logger.critical(alert_message)
                    self._emit_alert(
                        f"Critical pipeline SLA breach: {breach.message}. "
                        f"Actual latency: {breach.actual_ms / 1000:.1f}s, "
                        f"Threshold: {breach.threshold_ms / 1000:.1f}s"
                    )
                else:
                    logger.warning(alert_message)

            # Log overall pipeline latency status
            e2e_latency = self._latency_tracker.get_end_to_end_latency_ms()
            if e2e_latency is not None:
                logger.info(
                    f"[IMP-TEL-001] Pipeline latency summary: "
                    f"status={sla_status}, "
                    f"end_to_end={e2e_latency / 1000:.1f}s, "
                    f"breaches={len(breaches)}"
                )

        except Exception as e:
            # Non-fatal - SLA alerting failure should not block execution
            logger.warning(
                f"[IMP-TEL-001] Failed to check SLA breaches (non-fatal): {LogSanitizer.sanitize_exception(e)}"
            )

    # =========================================================================
    # IMP-AUTO-002: Parallel Phase Execution Support
    # =========================================================================

    def _initialize_parallelism_checker(self) -> None:
        """Initialize the scope-based parallelism checker.

        IMP-AUTO-002: Creates the parallelism checker with policy gate from
        the executor's intention anchor (if available).
        """
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
                logger.warning(
                    f"[IMP-AUTO-002] Failed to create parallelism policy gate: {LogSanitizer.sanitize_exception(e)}"
                )

        self._parallelism_checker = ScopeBasedParallelismChecker(policy_gate)
        logger.info(
            f"[IMP-AUTO-002] Parallelism checker initialized "
            f"(max_parallel_phases={self._max_parallel_phases})"
        )

    def _initialize_feedback_pipeline(self) -> None:
        """Initialize the unified feedback pipeline.

        IMP-LOOP-001: Creates the FeedbackPipeline for telemetry-memory-learning
        loop orchestration. Integrates with memory service and telemetry analyzer.
        """
        if not self._feedback_pipeline_enabled:
            logger.debug("[IMP-LOOP-001] Feedback pipeline disabled by configuration")
            return

        if self._feedback_pipeline is not None:
            logger.debug("[IMP-LOOP-001] Feedback pipeline already initialized")
            return

        # Get services from executor
        memory_service = getattr(self.executor, "memory_service", None)
        run_id = getattr(self.executor, "run_id", None)
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        # Initialize telemetry analyzer if not already present
        if self._telemetry_analyzer is None and hasattr(self.executor, "db_session"):
            try:
                self._telemetry_analyzer = TelemetryAnalyzer(
                    db_session=self.executor.db_session,
                    memory_service=memory_service,
                )
            except Exception as e:
                logger.warning(
                    f"[IMP-LOOP-001] Failed to initialize telemetry analyzer: {LogSanitizer.sanitize_exception(e)}"
                )

        # IMP-TELE-001: Create pipeline latency tracker for cycle time measurement
        self._latency_tracker = PipelineLatencyTracker(
            pipeline_id=f"{run_id or 'unknown'}_{project_id}",
        )
        logger.debug("[IMP-TELE-001] Pipeline latency tracker initialized")

        # Create feedback pipeline
        self._feedback_pipeline = FeedbackPipeline(
            memory_service=memory_service,
            telemetry_analyzer=self._telemetry_analyzer,
            learning_pipeline=getattr(self.executor, "learning_pipeline", None),
            latency_tracker=self._latency_tracker,
            run_id=run_id,
            project_id=project_id,
            enabled=True,
        )

        logger.info(
            f"[IMP-LOOP-001] FeedbackPipeline initialized "
            f"(run_id={run_id}, project_id={project_id}, latency_tracking=enabled)"
        )

        # IMP-LOOP-011: Emit loop health status for observability
        logger.info(
            "[IMP-LOOP-011] Self-improvement loop health: feedback_pipeline=ENABLED, "
            f"telemetry_analyzer={'ENABLED' if self._telemetry_analyzer else 'DISABLED'}, "
            f"memory_service={'ENABLED' if memory_service else 'DISABLED'}"
        )

    def _get_feedback_pipeline_context(self, phase_type: str, phase_goal: str) -> str:
        """Get enhanced context from feedback pipeline.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to retrieve context
        from previous executions, including insights, errors, and success patterns.

        IMP-MAINT-002: Delegates to FeedbackContextRetriever for modular implementation.

        Args:
            phase_type: Type of phase (e.g., 'build', 'test')
            phase_goal: Goal/description of the phase

        Returns:
            Formatted context string for prompt injection
        """
        # Ensure retriever has current feedback pipeline reference
        self._feedback_context_retriever.feedback_pipeline = self._feedback_pipeline
        return self._feedback_context_retriever.get_context_for_phase(
            phase_type=phase_type,
            phase_goal=phase_goal,
        )

    def _process_phase_with_feedback_pipeline(
        self,
        phase: Dict,
        success: bool,
        status: str,
        execution_start_time: float,
    ) -> None:
        """Process phase outcome through the feedback pipeline.

        IMP-LOOP-001: Uses the unified FeedbackPipeline to capture and persist
        phase execution feedback for the self-improvement loop.

        IMP-MAINT-002: Delegates to FeedbackContextRetriever for modular implementation.

        Args:
            phase: Phase dictionary with execution details
            success: Whether the phase executed successfully
            status: Final status string from execution
            execution_start_time: Unix timestamp when execution started
        """
        # Ensure retriever has current feedback pipeline reference
        self._feedback_context_retriever.feedback_pipeline = self._feedback_pipeline
        self._feedback_context_retriever.process_phase_outcome(
            phase=phase,
            success=success,
            status=status,
            execution_start_time=execution_start_time,
            executor=self.executor,
        )

    def _get_queued_phases_for_parallel_check(self, run_data: Dict) -> List[Dict]:
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

    def _execute_phases_parallel(
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
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all phases for execution
            future_to_phase = {}
            for phase in phases:
                phase_id = phase.get("phase_id", "unknown")
                adjustments = phase_adjustments_map.get(phase_id, {})

                future = executor.submit(
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
                    logger.error(
                        f"[IMP-AUTO-002] Parallel phase {phase_id} failed with error: {LogSanitizer.sanitize_exception(e)}"
                    )
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
            logger.error(
                f"[IMP-AUTO-002] Thread execution error for phase {phase_id}: {LogSanitizer.sanitize_exception(e)}"
            )
            return False, f"THREAD_ERROR: {str(e)}"

    def _try_parallel_execution(
        self, run_data: Dict, next_phase: Dict
    ) -> Optional[Tuple[List[Tuple[Dict, bool, str]], int]]:
        """Attempt to find and execute phases in parallel.

        IMP-AUTO-002: Checks if there are additional phases that can run in parallel
        with the next_phase based on scope isolation.

        Args:
            run_data: Current run data
            next_phase: The primary phase to execute

        Returns:
            If parallel execution occurred: (results, phases_count)
            If sequential execution needed: None
        """
        if not self._parallel_execution_enabled or self._parallelism_checker is None:
            return None

        # Get all queued phases
        queued_phases = self._get_queued_phases_for_parallel_check(run_data)

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
            phase_type = phase.get("phase_type")
            phase_goal = phase.get("description", "")

            # Get telemetry adjustments
            adjustments = self._get_telemetry_adjustments(phase_type)

            # Get memory context
            memory_context = self._get_memory_context(phase_type, phase_goal)
            improvement_context = self._get_improvement_task_context()

            combined_context = ""
            if memory_context:
                combined_context = memory_context
            if improvement_context:
                combined_context = (
                    combined_context + "\n\n" + improvement_context
                    if combined_context
                    else improvement_context
                )

            # IMP-LOOP-028: Warn when all context sources return empty (parallel path)
            if not combined_context.strip():
                logger.warning(
                    "All context sources returned empty - phase executing without historical guidance",
                    extra={
                        "phase": phase_id,
                        "memory_empty": not memory_context,
                        "improvement_empty": not improvement_context,
                    },
                )

            if combined_context:
                combined_context = self._inject_context_with_ceiling(combined_context)
                if combined_context:
                    adjustments["memory_context"] = combined_context

            phase_adjustments_map[phase_id] = adjustments

        # Execute phases in parallel
        results = self._execute_phases_parallel(parallel_group, phase_adjustments_map)
        return results, len(parallel_group)

    def _get_telemetry_analyzer(self) -> Optional[TelemetryAnalyzer]:
        """Get or create the telemetry analyzer instance.

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Returns:
            TelemetryAnalyzer instance if database session is available, None otherwise.
        """
        # Ensure manager has current session and memory service
        self._telemetry_persistence_manager.set_db_session(
            getattr(self.executor, "db_session", None)
        )
        self._telemetry_persistence_manager.set_memory_service(
            getattr(self.executor, "memory_service", None)
        )
        analyzer = self._telemetry_persistence_manager.get_telemetry_analyzer()
        # Keep local reference for backwards compatibility
        self._telemetry_analyzer = analyzer
        return analyzer

    def _get_telemetry_to_memory_bridge(self) -> Optional[TelemetryToMemoryBridge]:
        """Get or create the TelemetryToMemoryBridge instance.

        IMP-INT-002: Provides a bridge for persisting telemetry insights to memory
        after aggregation. The bridge is lazily initialized and reused.

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Returns:
            TelemetryToMemoryBridge instance if memory_service is available, None otherwise.
        """
        # Ensure manager has current memory service
        self._telemetry_persistence_manager.set_memory_service(
            getattr(self.executor, "memory_service", None)
        )
        bridge = self._telemetry_persistence_manager.get_telemetry_to_memory_bridge()
        # Keep local reference for backwards compatibility
        self._telemetry_to_memory_bridge = bridge
        return bridge

    def _flatten_ranked_issues_to_dicts(self, ranked_issues: Dict) -> list:
        """Convert ranked issues from aggregate_telemetry() to a flat list of dicts.

        IMP-INT-002: Converts RankedIssue objects to dictionaries suitable for
        TelemetryToMemoryBridge.persist_insights().

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.

        Returns:
            Flat list of dictionaries ready for bridge.persist_insights().
        """
        return self._telemetry_persistence_manager.flatten_ranked_issues_to_dicts(ranked_issues)

    def _persist_insights_to_memory(
        self, ranked_issues: Dict, context: str = "phase_telemetry"
    ) -> int:
        """Persist ranked issues to memory via TelemetryToMemoryBridge.

        IMP-INT-002: Invokes TelemetryToMemoryBridge.persist_insights() after
        telemetry aggregation to store insights in memory for future retrieval.

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of insights persisted, or 0 if persistence failed/skipped.
        """
        run_id = getattr(self.executor, "run_id", "unknown")
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        return self._telemetry_persistence_manager.persist_insights_to_memory(
            ranked_issues=ranked_issues,
            run_id=run_id,
            project_id=project_id,
            context=context,
        )

    def _generate_tasks_from_ranked_issues(
        self, ranked_issues: Dict, context: str = "phase_telemetry"
    ) -> int:
        """Generate improvement tasks from ranked issues and queue them for execution.

        IMP-INT-003: Wires ROADC TaskGenerator into executor loop. After telemetry
        insights are persisted to memory, this method generates improvement tasks
        from those same insights and persists them to the database for execution.

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of tasks generated and persisted, or 0 if generation failed/skipped.
        """
        run_id = getattr(self.executor, "run_id", None)

        return self._telemetry_persistence_manager.generate_tasks_from_ranked_issues(
            ranked_issues=ranked_issues,
            run_id=run_id,
            current_run_phases=self._current_run_phases,
            context=context,
        )

    def _aggregate_phase_telemetry(self, phase_id: str, force: bool = False) -> Optional[Dict]:
        """Aggregate telemetry after phase completion for self-improvement feedback.

        IMP-INT-001: Wires TelemetryAnalyzer.aggregate_telemetry() into the autonomous
        execution loop after phase completion. This enables the self-improvement
        architecture by ensuring telemetry insights are aggregated and persisted
        during execution, not just at the end of the run.

        IMP-MAINT-002: Delegates to TelemetryPersistenceManager for modular implementation.

        Args:
            phase_id: ID of the phase that just completed (for logging)
            force: If True, bypass throttling and aggregate immediately

        Returns:
            Dictionary of ranked issues from aggregate_telemetry(), or None if
            aggregation was skipped (throttled) or failed.
        """
        run_id = getattr(self.executor, "run_id", "unknown")
        project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()

        # Delegate to the persistence manager with a callback for health updates
        result = self._telemetry_persistence_manager.aggregate_phase_telemetry(
            phase_id=phase_id,
            run_id=run_id,
            project_id=project_id,
            current_run_phases=self._current_run_phases,
            health_callback=self._update_circuit_breaker_health,
            force=force,
        )

        # Sync the local counter with the manager's counter for backwards compatibility
        self._phases_since_last_aggregation = (
            self._telemetry_persistence_manager.phases_since_last_aggregation
        )

        return result

    def _get_task_effectiveness_tracker(self) -> Optional[TaskEffectivenessTracker]:
        """Get or create the TaskEffectivenessTracker instance.

        IMP-FBK-001: Lazy initialization of the task effectiveness tracker.
        Creates the tracker on first access if effectiveness tracking is enabled.

        Returns:
            TaskEffectivenessTracker instance, or None if tracking is disabled.
        """
        if not self._task_effectiveness_enabled:
            return None

        if self._task_effectiveness_tracker is None:
            try:
                # Try to get priority engine from executor for feedback integration
                priority_engine = getattr(self.executor, "_priority_engine", None)
                self._task_effectiveness_tracker = TaskEffectivenessTracker(
                    priority_engine=priority_engine
                )
                logger.info(
                    "[IMP-FBK-001] TaskEffectivenessTracker initialized "
                    f"(priority_engine={'enabled' if priority_engine else 'disabled'})"
                )
            except Exception as e:
                logger.warning(
                    f"[IMP-FBK-001] Failed to initialize TaskEffectivenessTracker: {LogSanitizer.sanitize_exception(e)}"
                )
                return None

        return self._task_effectiveness_tracker

    def _update_circuit_breaker_health(self, ranked_issues: Optional[Dict]) -> None:
        """Update circuit breaker with latest health report from meta-metrics.

        IMP-FBK-002: Generates a FeedbackLoopHealthReport from aggregated telemetry
        and updates the circuit breaker to enable health-aware state transitions.
        This prevents premature circuit reset when the system is still unhealthy.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            ranked_issues: Ranked issues from telemetry aggregation (used to build
                          telemetry data for health analysis)
        """
        # Sync phase stats with the integration module
        self._telemetry_integration.set_phase_stats(
            self._total_phases_executed, self._total_phases_failed
        )
        self._telemetry_integration.update_circuit_breaker_health(ranked_issues)
        # Sync task generation pause state back
        self._task_generation_paused = self._telemetry_integration.task_generation_paused

    def _build_telemetry_data_for_health(self, ranked_issues: Optional[Dict]) -> Dict:
        """Build telemetry data structure for meta-metrics health analysis.

        IMP-FBK-002: Converts ranked issues and loop statistics into the format
        expected by MetaMetricsTracker.analyze_feedback_loop_health().

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            ranked_issues: Ranked issues from telemetry aggregation

        Returns:
            Dictionary formatted for meta-metrics health analysis
        """
        # Sync phase stats with the integration module
        self._telemetry_integration.set_phase_stats(
            self._total_phases_executed, self._total_phases_failed
        )
        return self._telemetry_integration.build_telemetry_data_for_health(ranked_issues)

    def _update_task_effectiveness(
        self,
        phase_id: str,
        phase_type: Optional[str],
        success: bool,
        execution_time_seconds: float,
        tokens_used: int = 0,
    ) -> None:
        """Update task effectiveness tracking after phase completion.

        IMP-FBK-001: Records phase execution outcomes to the TaskEffectivenessTracker
        for closed-loop learning. This enables the priority engine to adjust task
        prioritization based on historical effectiveness.

        IMP-FBK-002: Also records outcomes to anomaly detector for pattern detection.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            phase_id: ID of the completed phase
            phase_type: Type of the phase (e.g., "build", "test")
            success: Whether the phase executed successfully
            execution_time_seconds: Time taken to execute the phase
            tokens_used: Number of tokens consumed during execution
        """
        # Ensure integration has the current effectiveness tracker
        self._telemetry_integration.set_task_effectiveness_tracker(
            self._get_task_effectiveness_tracker()
        )
        self._telemetry_integration.update_task_effectiveness(
            phase_id=phase_id,
            phase_type=phase_type,
            success=success,
            execution_time_seconds=execution_time_seconds,
            tokens_used=tokens_used,
        )

    def _record_phase_to_anomaly_detector(
        self,
        phase_id: str,
        phase_type: Optional[str],
        success: bool,
        tokens_used: int,
        duration_seconds: float,
    ) -> None:
        """Record phase outcome to anomaly detector for pattern detection.

        IMP-FBK-002: Records phase outcomes to TelemetryAnomalyDetector which
        tracks token spikes, failure rate breaches, and duration anomalies.
        These anomalies are used by the circuit breaker for health-aware
        state transitions.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            phase_id: ID of the completed phase
            phase_type: Type of the phase (e.g., "build", "test")
            success: Whether the phase executed successfully
            tokens_used: Number of tokens consumed during execution
            duration_seconds: Time taken to execute the phase
        """
        self._telemetry_integration.record_phase_to_anomaly_detector(
            phase_id=phase_id,
            phase_type=phase_type,
            success=success,
            tokens_used=tokens_used,
            duration_seconds=duration_seconds,
        )

    def _get_telemetry_adjustments(self, phase_type: Optional[str]) -> Dict:
        """Get telemetry-driven adjustments for phase execution.

        Queries the telemetry analyzer for recommendations and returns
        adjustments to apply to the phase execution.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            phase_type: The type of phase being executed

        Returns:
            Dictionary of adjustments to pass to execute_phase:
            - context_reduction_factor: Factor to reduce context by (e.g., 0.7 for 30% reduction)
            - model_downgrade: Target model to use instead (e.g., "sonnet", "haiku")
            - timeout_increase_factor: Factor to increase timeout by (e.g., 1.5 for 50% increase)
        """
        # Pass the analyzer explicitly to support patching in tests
        analyzer = self._get_telemetry_analyzer()
        return self._telemetry_integration.get_telemetry_adjustments(phase_type, analyzer)

    def _check_cost_recommendations(self) -> CostRecommendation:
        """Check if telemetry recommends pausing for cost reasons (IMP-COST-005).

        Queries the telemetry analyzer for cost recommendations based on
        current token usage against the run's budget cap.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Returns:
            CostRecommendation with pause decision and details
        """
        tokens_used = getattr(self.executor, "_run_tokens_used", 0)
        token_cap = settings.run_token_cap
        # Pass the analyzer explicitly to support patching in tests
        analyzer = self._get_telemetry_analyzer()
        return self._telemetry_integration.check_cost_recommendations(
            tokens_used, token_cap, analyzer
        )

    def _pause_for_cost_limit(self, recommendation: CostRecommendation) -> None:
        """Handle pause when cost limits are approached (IMP-COST-005).

        Logs the cost pause event and could trigger notifications or
        graceful shutdown procedures in the future.

        IMP-MAINT-004: Delegates to LoopTelemetryIntegration for modular implementation.

        Args:
            recommendation: The CostRecommendation that triggered the pause
        """
        project_slug = self.executor._get_project_slug()
        self._telemetry_integration.pause_for_cost_limit(recommendation, project_slug)

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
            # IMP-LOOP-024: Use EnrichedContextInjection for metadata (source, timestamp, freshness)
            injection = injector.get_context_for_phase_with_metadata(
                phase_type=phase_type,
                current_goal=goal,
                project_id=project_id,
                max_tokens=500,
            )

            if injection.total_token_estimate > 0:
                # IMP-LOOP-024: Log enriched context with quality signals
                quality_info = ""
                if injection.has_low_confidence_warning:
                    quality_info = f", LOW_CONFIDENCE avg={injection.avg_confidence:.2f}"
                else:
                    quality_info = f", confidence={injection.avg_confidence:.2f}"

                logger.info(
                    f"[IMP-LOOP-024] Injecting {injection.total_token_estimate} tokens of enriched memory context "
                    f"({len(injection.past_errors)} errors, "
                    f"{len(injection.successful_strategies)} strategies, "
                    f"{len(injection.doctor_hints)} hints, "
                    f"{len(injection.relevant_insights)} insights{quality_info})"
                )

            # IMP-LOOP-024: Use enriched formatting with confidence warnings
            memory_context = injector.format_enriched_for_prompt(injection)

            # IMP-LOOP-025: Retrieve and inject promoted rules into execution context
            # Promoted rules are high-priority patterns that have occurred 3+ times
            if self._feedback_pipeline is not None:
                try:
                    promoted_rules = self._feedback_pipeline.get_promoted_rules(
                        phase_type=phase_type, limit=5
                    )
                    if promoted_rules:
                        rules_lines = ["\n\n## Promoted Rules (High-Priority Patterns)"]
                        rules_lines.append(
                            "The following rules were derived from recurring issues:"
                        )
                        for rule in promoted_rules:
                            description = rule.get("description", "")[:200]
                            action = rule.get("suggested_action", "")[:150]
                            occurrences = rule.get("occurrences", 0)
                            rules_lines.append(f"- **Rule** (seen {occurrences}x): {description}")
                            if action:
                                rules_lines.append(f"  → Action: {action}")
                        rules_context = "\n".join(rules_lines)
                        memory_context += rules_context
                        logger.info(
                            f"[IMP-LOOP-025] Injected {len(promoted_rules)} promoted rules "
                            f"into execution context for phase_type={phase_type}"
                        )
                except Exception as rules_err:
                    logger.warning(
                        f"[IMP-LOOP-025] Failed to retrieve promoted rules (non-fatal): {rules_err}"
                    )

            return memory_context
        except Exception as e:
            logger.warning(
                f"[IMP-ARCH-002] Failed to retrieve memory context: {LogSanitizer.sanitize_exception(e)}"
            )
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

    def _get_feedback_loop_health(self) -> str:
        """Get the current feedback loop health status (IMP-LOOP-001).

        Determines health based on:
        - Circuit breaker state (if enabled)
        - Phase failure ratio
        - Overall execution statistics

        Returns:
            Health status string: "healthy", "degraded", or "attention_required"
        """
        # Check circuit breaker state first (most critical)
        if self._circuit_breaker is not None:
            cb_state = self._circuit_breaker.state
            if cb_state == CircuitBreakerState.OPEN:
                return FeedbackLoopHealth.ATTENTION_REQUIRED.value
            elif cb_state == CircuitBreakerState.HALF_OPEN:
                return FeedbackLoopHealth.DEGRADED.value

        # Check failure ratio
        total_phases = self._total_phases_executed + self._total_phases_failed
        if total_phases > 0:
            failure_ratio = self._total_phases_failed / total_phases
            if failure_ratio >= 0.5:  # 50%+ failures
                return FeedbackLoopHealth.ATTENTION_REQUIRED.value
            elif failure_ratio >= 0.25:  # 25%+ failures
                return FeedbackLoopHealth.DEGRADED.value

        return FeedbackLoopHealth.HEALTHY.value

    def _estimate_tokens(self, context: str) -> int:
        """Estimate token count for a context string.

        Uses a rough heuristic of ~4 characters per token (common for English text).
        This is a fast approximation; actual token counts vary by model and content.

        Args:
            context: The context string to estimate tokens for.

        Returns:
            Estimated token count.
        """
        if not context:
            return 0
        # Rough estimate: ~4 characters per token (typical for English)
        return len(context) // 4

    def _truncate_to_budget(self, context: str, token_budget: int) -> str:
        """Truncate context to fit within a token budget.

        Prioritizes keeping the most recent content (end of string).
        Truncates from the beginning to preserve recent context.

        Args:
            context: The context string to truncate.
            token_budget: Maximum tokens allowed.

        Returns:
            Truncated context string that fits within budget.
        """
        if token_budget <= 0:
            return ""

        current_tokens = self._estimate_tokens(context)
        if current_tokens <= token_budget:
            return context

        # Calculate approximate character limit (4 chars per token)
        char_budget = token_budget * 4

        # Truncate from beginning, keeping most recent content
        truncated = context[-char_budget:]

        # Try to find a clean break point (newline or space)
        clean_break = truncated.find("\n")
        if clean_break == -1:
            clean_break = truncated.find(" ")

        if clean_break > 0 and clean_break < len(truncated) // 2:
            truncated = truncated[clean_break + 1 :]

        return truncated

    def _inject_context_with_ceiling(self, context: str) -> str:
        """Inject context while enforcing the total context ceiling.

        IMP-PERF-002: Prevents unbounded context accumulation across phases.
        Tracks total context tokens injected and truncates when ceiling is reached.

        Args:
            context: The context string to inject.

        Returns:
            The context string (potentially truncated to fit within ceiling).
        """
        if not context:
            return ""

        context_tokens = self._estimate_tokens(context)

        if self._total_context_tokens + context_tokens > self._context_ceiling:
            remaining_budget = self._context_ceiling - self._total_context_tokens

            if remaining_budget <= 0:
                logger.warning(
                    f"[IMP-PERF-002] Context ceiling reached ({self._context_ceiling} tokens). "
                    f"Skipping context injection entirely."
                )
                return ""

            logger.warning(
                f"[IMP-PERF-002] Context ceiling approaching ({self._total_context_tokens}/{self._context_ceiling} tokens). "
                f"Truncating injection from {context_tokens} to {remaining_budget} tokens."
            )
            # Prioritize most recent context
            context = self._truncate_to_budget(context, remaining_budget)
            context_tokens = self._estimate_tokens(context)

        self._total_context_tokens += context_tokens
        logger.debug(
            f"[IMP-PERF-002] Context injected: {context_tokens} tokens "
            f"(total: {self._total_context_tokens}/{self._context_ceiling})"
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

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(
                db_session=db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
            completed_count = 0

            for task in improvement_tasks:
                task_id = task.get("task_id")
                if task_id:
                    result = generator.mark_task_status(
                        task_id, "completed", executed_in_run_id=self.executor.run_id
                    )
                    if result == "updated":
                        completed_count += 1

            if completed_count > 0:
                logger.info(
                    f"[IMP-ARCH-019] Marked {completed_count} improvement tasks as completed"
                )

                # IMP-TELE-001: Record task execution completion for latency tracking
                if self._latency_tracker:
                    self._latency_tracker.record_stage(
                        PipelineStage.TASK_EXECUTED,
                        metadata={"tasks_completed": completed_count},
                    )

        except Exception as e:
            logger.warning(
                f"[IMP-ARCH-019] Failed to mark tasks completed: {LogSanitizer.sanitize_exception(e)}"
            )

    def _mark_improvement_tasks_failed(self, phases_failed: int) -> None:
        """Mark improvement tasks as failed/retry when run has failures (IMP-LOOP-005).

        Called when run finishes with failed phases, indicating the improvement
        tasks were not successfully addressed and need retry or failure tracking.

        Args:
            phases_failed: Number of phases that failed in this run
        """
        improvement_tasks = getattr(self.executor, "_improvement_tasks", [])
        # Ensure it's a proper list (not a Mock or other non-list type)
        if not improvement_tasks or not isinstance(improvement_tasks, list):
            return

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(
                db_session=db_session,
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
                        failure_run_id=self.executor.run_id,
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
            logger.warning(
                f"[IMP-LOOP-005] Failed to update task status: {LogSanitizer.sanitize_exception(e)}"
            )

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
            logger.warning(
                f"[IMP-DB-001] Failed to collect pool health metrics: {LogSanitizer.sanitize_exception(e)}"
            )

    def _increment_memory_write_count(self, count: int = 1) -> None:
        """Increment memory write counter and trigger maintenance if threshold reached.

        IMP-MEM-011: Tracks memory writes to trigger maintenance before collections
        grow unbounded. Maintenance is triggered after every N writes (default: 100).

        Args:
            count: Number of writes to add to the counter (default: 1)
        """
        self._memory_write_count += count

        # Check if maintenance should be triggered
        writes_since_maintenance = self._memory_write_count - self._last_maintenance_write_count
        if writes_since_maintenance >= self._maintenance_write_threshold:
            self._run_write_triggered_maintenance()

    def _run_write_triggered_maintenance(self) -> None:
        """Run maintenance triggered by write count threshold.

        IMP-MEM-011: Runs maintenance and updates the last maintenance write count.
        This complements the time-based maintenance (IMP-LOOP-017) by ensuring
        maintenance runs frequently during high-write-volume periods.
        """
        if not self._auto_maintenance_enabled:
            return

        try:
            logger.info(
                f"[IMP-MEM-011] Triggering maintenance after {self._memory_write_count} "
                f"total writes (threshold: {self._maintenance_write_threshold})"
            )
            maintenance_result = run_maintenance_if_due()

            # Update the last maintenance write count regardless of whether
            # run_maintenance_if_due actually ran (it may skip if recently run)
            self._last_maintenance_write_count = self._memory_write_count

            if maintenance_result is not None:
                logger.info(
                    f"[IMP-MEM-011] Write-triggered maintenance completed: "
                    f"pruned={maintenance_result.get('pruned', 0)}, "
                    f"tombstoned={maintenance_result.get('planning_tombstoned', 0)}"
                )
        except Exception as e:
            # Non-blocking - log and continue
            logger.warning(
                f"[IMP-MEM-011] Write-triggered maintenance failed: {LogSanitizer.sanitize_exception(e)}"
            )
            # Still update count to prevent retry storm
            self._last_maintenance_write_count = self._memory_write_count

    def run(
        self,
        poll_interval: float = 0.5,
        max_iterations: int = 50,
        stop_on_first_failure: bool = False,
    ):
        """Run autonomous execution loop.

        Args:
            poll_interval: Seconds to wait between polling for next phase (default: 0.5s, reduced from 1.0s for better performance)
            max_iterations: Maximum number of phases to execute (default: 50 to prevent runaway execution)
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

        # IMP-AUTO-002: Initialize parallelism checker after intention loop
        # (needs intention anchor for policy checks)
        self._initialize_parallelism_checker()

        # IMP-LOOP-001: Initialize feedback pipeline for self-improvement loop
        self._initialize_feedback_pipeline()

        # IMP-LOOP-027: Initialize wave planner for parallel IMP execution
        self._initialize_wave_planner()

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
                    f"  - Executor DATABASE_URL: {LogSanitizer.sanitize(os.environ.get('DATABASE_URL', 'NOT SET'))}"
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

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(
                db_session=db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
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

    def _fetch_generated_tasks(self) -> List[Dict]:
        """Fetch generated tasks and convert them to executable phase specs (IMP-LOOP-004).

        This method closes the autonomous improvement loop by:
        1. Retrieving pending tasks from the database via task_generator.get_pending_tasks()
        2. Converting GeneratedTask objects into executable phase specifications
        3. Marking tasks as "in_progress" when they start execution

        IMP-TASK-002: Tasks are now sorted by ROI payback period before execution.
        Tasks with shorter payback periods receive higher priority.

        The generated phases use the "generated-task-execution" phase type which
        routes to the specialized handler in phase_dispatch.py.

        Returns:
            List of phase spec dicts ready for execution, or empty list if disabled/no tasks.
        """
        # Check if task execution is enabled (separate from task generation)
        if not settings.task_generation_auto_execute:
            logger.debug("[IMP-LOOP-004] Generated task execution is disabled")
            return []

        try:
            from autopack.roadc.task_generator import AutonomousTaskGenerator

            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(
                db_session=db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )

            # Fetch pending tasks (limit to avoid overwhelming the run)
            max_tasks_per_run = settings.task_generation_max_tasks_per_run
            pending_tasks = generator.get_pending_tasks(status="pending", limit=max_tasks_per_run)

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
                    task.task_id, "in_progress", executed_in_run_id=self.executor.run_id
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

    def _inject_generated_tasks_into_backlog(self, run_data: Dict) -> Dict:
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
        generated_phases = self._fetch_generated_tasks()
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

    # =========================================================================
    # IMP-LOOP-029: Complete Task Injection Wiring
    # =========================================================================

    def _generate_and_inject_tasks(self) -> Optional["InjectionResult"]:
        """Generate tasks and inject them via BacklogMaintenance (IMP-LOOP-029).

        This method completes the wiring between AutonomousTaskGenerator and
        BacklogMaintenance.inject_tasks(), enabling generated tasks to be
        properly injected into the execution queue with verification.

        The wiring flow:
        1. Create AutonomousTaskGenerator with db_session
        2. Call generate_tasks() to get TaskGenerationResult
        3. Convert GeneratedTask objects to TaskCandidate objects
        4. Call BacklogMaintenance.inject_tasks() with candidates
        5. Register task execution for attribution tracking (IMP-LOOP-028)

        Returns:
            InjectionResult with injection details, or None if no tasks generated.
        """
        # Check if task generation is enabled
        if not settings.task_generation_auto_execute:
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
            db_session = getattr(self.executor, "db_session", None)
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            task_generator = AutonomousTaskGenerator(
                db_session=db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )

            # Generate tasks with run context
            max_tasks = settings.task_generation_max_tasks_per_run
            generation_result = task_generator.generate_tasks(
                max_tasks=max_tasks,
                run_id=self.executor.run_id,
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

            # Inject tasks via BacklogMaintenance
            injection_result: InjectionResult = self.executor.backlog_maintenance.inject_tasks(
                tasks=candidates,
                on_injection=self._on_task_injected,  # Callback for attribution
            )

            # Log injection results
            if injection_result.all_succeeded:
                logger.info(
                    f"[IMP-LOOP-029] Successfully injected {injection_result.success_count} tasks"
                )
            else:
                logger.warning(
                    f"[IMP-LOOP-029] Injection partial: "
                    f"{injection_result.success_count} succeeded, "
                    f"{injection_result.failure_count} failed"
                )
                if injection_result.verification_errors:
                    for error in injection_result.verification_errors:
                        logger.warning(f"[IMP-LOOP-029] Verification error: {error}")

            # IMP-LOOP-028: Register task executions for attribution tracking
            if self._task_effectiveness_tracker is not None:
                for task_id in injection_result.injected_ids:
                    # Find the corresponding phase_id in the queue
                    phase_id = self._find_phase_id_for_task(task_id)
                    if phase_id:
                        self._task_effectiveness_tracker.register_task_execution(
                            task_id=task_id,
                            phase_id=phase_id,
                        )
                        logger.debug(
                            f"[IMP-LOOP-029] Registered task {task_id} -> phase {phase_id} "
                            "for attribution"
                        )

            return injection_result

        except Exception as e:
            logger.warning(f"[IMP-LOOP-029] Task injection wiring failed: {e}")
            return None

    def _on_task_injected(self, task_id: str) -> None:
        """Callback invoked when a task is successfully injected (IMP-LOOP-029).

        This callback is passed to BacklogMaintenance.inject_tasks() and
        invoked for each successfully injected task, enabling real-time
        tracking of injections.

        Args:
            task_id: The ID of the successfully injected task.
        """
        logger.debug(f"[IMP-LOOP-029] Task {task_id} injected into queue")

        # IMP-LOOP-025: Mark task as queued for execution in metrics tracker
        if self._meta_metrics_tracker is not None:
            self._meta_metrics_tracker.mark_task_queued(task_id)

    def _find_phase_id_for_task(self, task_id: str) -> Optional[str]:
        """Find the phase_id associated with a task after injection (IMP-LOOP-029).

        The phase_id is needed for attribution tracking (linking task -> phase -> outcome).

        Args:
            task_id: The task ID to look up.

        Returns:
            The phase_id if found, None otherwise.
        """
        if self._current_run_phases is None:
            return None

        for phase in self._current_run_phases:
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

    # =========================================================================
    # ROAD-C Task Queue Consumption (IMP-LOOP-025)
    # =========================================================================

    def _consume_roadc_tasks(self) -> List[Dict]:
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
        from pathlib import Path

        queue_file = Path(".autopack/ROADC_TASK_QUEUE.json")

        if not queue_file.exists():
            logger.debug("[IMP-LOOP-025] No ROAD-C task queue file found")
            return []

        try:
            import json

            queue_data = json.loads(queue_file.read_text())
            tasks = queue_data.get("tasks", [])

            if not tasks:
                logger.debug("[IMP-LOOP-025] ROAD-C task queue is empty")
                return []

            # Check if task execution is enabled
            if not settings.task_generation_auto_execute:
                logger.debug("[IMP-LOOP-025] Generated task execution is disabled")
                return []

            # Limit to max tasks per run
            max_tasks = settings.task_generation_max_tasks_per_run
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

    def _process_roadc_tasks(self, tasks: List[Dict]) -> Dict:
        """Process consumed ROAD-C tasks and inject them into the backlog (IMP-LOOP-025).

        This method processes tasks consumed from the ROAD-C queue and adds them
        to the current run's phase backlog for execution.

        Args:
            tasks: List of phase spec dicts from _consume_roadc_tasks()

        Returns:
            Dict with processing stats: {"injected": N, "skipped": M}
        """
        if not tasks:
            return {"injected": 0, "skipped": 0}

        injected = 0
        skipped = 0

        try:
            # Get existing phase IDs to avoid duplicates
            existing_phase_ids = {
                p.get("phase_id") for p in getattr(self, "_current_run_phases", [])
            }

            for task in tasks:
                phase_id = task.get("phase_id")

                if phase_id in existing_phase_ids:
                    logger.debug(f"[IMP-LOOP-025] Task {phase_id} already in backlog, skipping")
                    skipped += 1
                    continue

                # Insert at front of backlog for high priority, or append for normal priority
                task_priority = task.get("_generated_task", {}).get("priority", "medium")
                if task_priority == "critical":
                    # Insert at front for immediate execution
                    if hasattr(self, "_current_run_phases") and self._current_run_phases:
                        self._current_run_phases.insert(0, task)
                    injected += 1
                    logger.info(
                        f"[IMP-LOOP-025] Injected critical ROAD-C task {phase_id} at front of queue"
                    )
                else:
                    # Append to end of backlog
                    if hasattr(self, "_current_run_phases") and self._current_run_phases:
                        self._current_run_phases.append(task)
                    injected += 1
                    logger.info(f"[IMP-LOOP-025] Appended ROAD-C task {phase_id} to backlog")

            logger.info(
                f"[IMP-LOOP-025] Processed ROAD-C tasks: {injected} injected, {skipped} skipped"
            )
            return {"injected": injected, "skipped": skipped}

        except Exception as e:
            logger.warning(f"[IMP-LOOP-025] Failed to process ROAD-C tasks: {e}")
            return {"injected": injected, "skipped": skipped}

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
                from datetime import datetime, timezone

                from autopack.intention_anchor.models import (
                    IntentionAnchor,
                    IntentionBudgets,
                    IntentionConstraints,
                )

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
        self, poll_interval: float, max_iterations: int, stop_on_first_failure: bool
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

        # IMP-REL-004: Use effective max iterations with fallback to default
        effective_max_iterations = max_iterations if max_iterations else DEFAULT_MAX_ITERATIONS

        while iteration < effective_max_iterations:
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

            # IMP-LOOP-017: Periodic memory maintenance check
            # Runs maintenance if enough time has passed since last maintenance
            if self._auto_maintenance_enabled:
                if current_time - self._last_maintenance_check >= self._maintenance_check_interval:
                    self._last_maintenance_check = current_time
                    try:
                        maintenance_result = run_maintenance_if_due()
                        if maintenance_result is not None:
                            logger.info(
                                f"[IMP-LOOP-017] Memory maintenance completed during loop: "
                                f"pruned={maintenance_result.get('pruned', 0)}, "
                                f"tombstoned={maintenance_result.get('planning_tombstoned', 0)}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"[IMP-LOOP-017] Memory maintenance failed (non-blocking): {e}"
                        )

            iteration += 1

            # IMP-DB-001: Log database pool health at start of each iteration
            self._log_db_pool_health()

            # IMP-SAFETY-005: Check budget exhaustion EARLY, before any token-consuming operations
            # This prevents operations like context loading from consuming tokens when budget is already exhausted
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

            # IMP-COST-005: Check cost recommendations before proceeding
            # This provides a softer pause at 95% budget to prevent reaching hard stop
            cost_recommendation = self._check_cost_recommendations()
            if cost_recommendation.should_pause:
                logger.warning(
                    f"[IMP-COST-005] Cost pause recommended: {cost_recommendation.reason}. "
                    f"Current spend: {cost_recommendation.current_spend:,.0f} tokens"
                )
                self._pause_for_cost_limit(cost_recommendation)
                stop_reason = "cost_limit_reached"
                break

            # IMP-LOOP-006: Check circuit breaker state before proceeding
            if self._circuit_breaker is not None:
                try:
                    self._circuit_breaker.check_state()
                except CircuitBreakerOpenError as e:
                    logger.critical(
                        f"[IMP-LOOP-006] Circuit breaker OPEN - execution blocked. "
                        f"{e.consecutive_failures} consecutive failures. "
                        f"Reset in {e.reset_time:.0f}s."
                    )
                    stop_reason = "circuit_breaker_open"
                    break

            # Fetch run status
            logger.info(f"Iteration {iteration}: Fetching run status...")
            try:
                run_data = self.executor.get_run_status()
            except Exception as e:
                logger.error(f"Failed to fetch run status: {e}")
                logger.info(f"Waiting {poll_interval}s before retry...")
                self._adaptive_sleep(is_idle=True, base_interval=poll_interval)
                continue

            # IMP-LOOP-004: Inject generated tasks into backlog for execution
            # This closes the autonomous improvement loop by executing tasks generated
            # from telemetry insights in previous runs
            try:
                run_data = self._inject_generated_tasks_into_backlog(run_data)
            except Exception as e:
                logger.warning(
                    f"[IMP-LOOP-004] Failed to inject generated tasks (non-blocking): {e}"
                )

            # IMP-LOOP-025: Consume and process tasks from ROAD-C queue file
            # This provides a direct path from task generation to execution,
            # bypassing database polling for faster task consumption
            try:
                roadc_tasks = self._consume_roadc_tasks()
                if roadc_tasks:
                    process_result = self._process_roadc_tasks(roadc_tasks)
                    if process_result["injected"] > 0:
                        # Update run_data with injected tasks
                        run_data["phases"] = self._current_run_phases
                        logger.info(
                            f"[IMP-LOOP-025] ROAD-C queue tasks processed: "
                            f"{process_result['injected']} injected"
                        )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-025] Failed to consume ROAD-C tasks (non-blocking): {e}")

            # IMP-LOOP-029: Generate and inject tasks via BacklogMaintenance
            # This completes the wiring between AutonomousTaskGenerator and
            # BacklogMaintenance.inject_tasks() for proper verification and tracking
            try:
                injection_result = self._generate_and_inject_tasks()
                if injection_result is not None and injection_result.success_count > 0:
                    # Update run_data phases with newly injected tasks
                    if self._current_run_phases:
                        run_data["phases"] = self._current_run_phases
                    logger.info(
                        f"[IMP-LOOP-029] Task injection complete: "
                        f"{injection_result.success_count} injected, "
                        f"verified={injection_result.verified}"
                    )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-029] Task injection wiring failed (non-blocking): {e}")

            # IMP-LOOP-027: Check if current wave is complete and load next wave
            # This enables automatic wave transitions during execution
            try:
                wave_phases_loaded = self._check_and_load_next_wave()
                if wave_phases_loaded > 0:
                    logger.info(
                        f"[IMP-LOOP-027] Wave transition: loaded {wave_phases_loaded} phases "
                        f"from wave {self._current_wave_number}"
                    )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-027] Wave check failed (non-blocking): {e}")

            # IMP-LOOP-003: Store reference to current run's phases for same-run task injection
            # This allows high-priority tasks generated during execution to be injected
            # into the current run's backlog for immediate execution
            self._current_run_phases = run_data.get("phases", [])

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

            # Log budget status before each phase (budget check moved to top of loop per IMP-SAFETY-005)
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)
            token_cap = settings.run_token_cap
            budget_pct = get_budget_remaining_pct(token_cap, tokens_used) * 100
            logger.info(
                f"Phase {phase_id}: Budget remaining {budget_pct:.1f}% ({tokens_used}/{token_cap} tokens)"
            )

            # IMP-AUTO-002: Try parallel execution if enabled and possible
            parallel_result = None
            try:
                parallel_result = self._try_parallel_execution(run_data, next_phase)
            except Exception as parallel_err:
                logger.warning(
                    f"[IMP-AUTO-002] Parallel execution attempt failed (falling back to sequential): "
                    f"{parallel_err}"
                )

            if parallel_result is not None:
                # Parallel execution occurred
                results, parallel_count = parallel_result
                logger.info(f"[IMP-AUTO-002] Parallel execution completed: {parallel_count} phases")

                # Process results from parallel execution
                for phase, success, status in results:
                    phase_id_result = phase.get("phase_id", "unknown")
                    phase_type_result = phase.get("phase_type")

                    # IMP-FBK-001: Update task effectiveness for parallel phase
                    try:
                        # Note: For parallel phases we don't have precise execution time
                        # Use a default estimate based on typical parallel execution
                        tokens_used = getattr(self.executor, "_run_tokens_used", 0)
                        self._update_task_effectiveness(
                            phase_id=phase_id_result,
                            phase_type=phase_type_result,
                            success=success,
                            execution_time_seconds=0.0,  # Unknown for parallel execution
                            tokens_used=tokens_used // max(1, parallel_count),  # Estimate per phase
                        )
                    except Exception as effectiveness_err:
                        logger.warning(
                            f"[IMP-FBK-001] Task effectiveness tracking failed (non-fatal): {effectiveness_err}"
                        )

                    if success:
                        logger.info(f"Phase {phase_id_result} completed successfully (parallel)")
                        phases_executed += 1
                        self.executor._phase_failure_counts[phase_id_result] = 0

                        # IMP-LOOP-027: Track wave phase completion
                        self._mark_wave_phase_complete(phase_id_result)

                        # IMP-TEL-001: Record phase completion stage for parallel execution
                        if self._latency_tracker is not None:
                            self._latency_tracker.record_stage(
                                PipelineStage.PHASE_COMPLETE,
                                metadata={
                                    "phase_id": phase_id_result,
                                    "phase_type": phase_type_result,
                                    "parallel": True,
                                },
                            )

                        if self._circuit_breaker is not None:
                            self._circuit_breaker.record_success()

                        # IMP-INT-001: Aggregate telemetry after parallel phase completion
                        try:
                            self._aggregate_phase_telemetry(phase_id_result)
                        except Exception as agg_err:
                            logger.warning(
                                f"[IMP-INT-001] Telemetry aggregation failed (non-fatal): {agg_err}"
                            )

                        # IMP-TEL-001: Check for SLA breaches after parallel phase
                        self._check_and_emit_sla_alerts(phase_id_result)
                    else:
                        logger.warning(
                            f"Phase {phase_id_result} finished with status: {status} (parallel)"
                        )
                        phases_failed += 1

                        if self._circuit_breaker is not None:
                            self._circuit_breaker.record_failure()
                            if self._circuit_breaker.is_open:
                                logger.critical(
                                    f"[IMP-LOOP-006] Circuit breaker tripped after parallel "
                                    f"phase {phase_id_result} failure."
                                )
                                # IMP-MEM-004: Record circuit breaker event for root cause analysis
                                if self._feedback_pipeline is not None:
                                    self._feedback_pipeline.record_circuit_breaker_event(
                                        failure_count=self._circuit_breaker.consecutive_failures,
                                        last_failure_reason=f"Parallel phase {phase_id_result} failed with status: {status}",
                                        timestamp=datetime.now(timezone.utc),
                                    )
                                stop_reason = "circuit_breaker_tripped"
                                break

                        if stop_on_first_failure:
                            logger.critical(
                                f"[STOP_ON_FAILURE] Parallel phase {phase_id_result} failed. "
                                f"Stopping execution."
                            )
                            stop_reason = "stop_on_first_failure"
                            break

                # Check if we need to break from the main loop
                if stop_reason in ("circuit_breaker_tripped", "stop_on_first_failure"):
                    break

                # IMP-INT-005: Immediate cost check after parallel execution completes
                # Check cost recommendations before waiting, to stop faster if budget is exceeded
                parallel_cost = self._check_cost_recommendations()
                if parallel_cost.should_pause:
                    logger.warning(
                        f"[IMP-INT-005] Cost pause triggered after parallel execution: "
                        f"{parallel_cost.reason}. "
                        f"Current spend: {parallel_cost.current_spend:,.0f} tokens. "
                        f"Budget remaining: {parallel_cost.budget_remaining_pct:.1f}%"
                    )
                    self._pause_for_cost_limit(parallel_cost)
                    stop_reason = "cost_limit_reached"
                    break

                # Skip to next iteration since we handled all phases in parallel
                if iteration < max_iterations:
                    logger.info(f"Waiting {poll_interval}s before next phase...")
                    self._adaptive_sleep(is_idle=False, base_interval=poll_interval)
                continue

            # Sequential execution path (original logic)
            # Telemetry-driven phase adjustments (IMP-TEL-002)
            phase_adjustments = self._get_telemetry_adjustments(phase_type)

            # IMP-ARCH-002: Retrieve memory context for builder injection
            phase_goal = next_phase.get("description", "")
            memory_context = self._get_memory_context(phase_type, phase_goal)

            # IMP-LOOP-001: Retrieve enhanced context from feedback pipeline
            feedback_context = self._get_feedback_pipeline_context(phase_type, phase_goal)

            # IMP-ARCH-019: Inject improvement tasks into phase context
            improvement_context = self._get_improvement_task_context()

            # Combine all context sources
            combined_context = ""
            if memory_context:
                combined_context = memory_context
            if feedback_context:
                combined_context = (
                    combined_context + "\n\n" + feedback_context
                    if combined_context
                    else feedback_context
                )
            if improvement_context:
                combined_context = (
                    combined_context + "\n\n" + improvement_context
                    if combined_context
                    else improvement_context
                )

            # IMP-LOOP-028: Warn when all context sources return empty
            if not combined_context.strip():
                logger.warning(
                    "All context sources returned empty - phase executing without historical guidance",
                    extra={
                        "phase": phase_id,
                        "memory_empty": not memory_context,
                        "feedback_empty": not feedback_context,
                        "improvement_empty": not improvement_context,
                    },
                )

            # IMP-PERF-002: Apply context ceiling enforcement
            if combined_context:
                combined_context = self._inject_context_with_ceiling(combined_context)
                if combined_context:
                    phase_adjustments["memory_context"] = combined_context

            # IMP-LOOP-005: Record execution start time for feedback
            execution_start_time = time.time()

            # Execute phase (with any telemetry-driven adjustments and memory context)
            success, status = self.executor.execute_phase(next_phase, **phase_adjustments)

            # IMP-LOOP-005: Record execution feedback to memory for learning
            try:
                self._record_execution_feedback(
                    phase=next_phase,
                    success=success,
                    status=status,
                    execution_start_time=execution_start_time,
                    memory_context=combined_context if combined_context else None,
                )
            except Exception as feedback_err:
                # Non-fatal - continue execution even if feedback fails
                logger.warning(
                    f"[IMP-LOOP-005] Execution feedback recording failed (non-fatal): {feedback_err}"
                )

            # IMP-LOOP-001: Process outcome through unified feedback pipeline
            try:
                self._process_phase_with_feedback_pipeline(
                    phase=next_phase,
                    success=success,
                    status=status,
                    execution_start_time=execution_start_time,
                )
            except Exception as pipeline_err:
                # Non-fatal - continue execution even if feedback pipeline fails
                logger.warning(
                    f"[IMP-LOOP-001] Feedback pipeline processing failed (non-fatal): {pipeline_err}"
                )

            # IMP-FBK-001: Update task effectiveness tracking for closed-loop learning
            try:
                execution_time = time.time() - execution_start_time
                tokens_used = getattr(self.executor, "_run_tokens_used", 0)
                self._update_task_effectiveness(
                    phase_id=phase_id,
                    phase_type=phase_type,
                    success=success,
                    execution_time_seconds=execution_time,
                    tokens_used=tokens_used,
                )
            except Exception as effectiveness_err:
                # Non-fatal - continue execution even if effectiveness tracking fails
                logger.warning(
                    f"[IMP-FBK-001] Task effectiveness tracking failed (non-fatal): {effectiveness_err}"
                )

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
                phases_executed += 1
                # Reset failure count on success
                self.executor._phase_failure_counts[phase_id] = 0

                # IMP-LOOP-027: Track wave phase completion
                self._mark_wave_phase_complete(phase_id)

                # IMP-TEL-001: Record phase completion stage for latency tracking
                if self._latency_tracker is not None:
                    self._latency_tracker.record_stage(
                        PipelineStage.PHASE_COMPLETE,
                        metadata={
                            "phase_id": phase_id,
                            "phase_type": phase_type,
                            "execution_time_seconds": execution_time,
                        },
                    )

                # IMP-LOOP-006: Record success with circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_success()

                # IMP-INT-001: Aggregate telemetry after phase completion for self-improvement
                try:
                    self._aggregate_phase_telemetry(phase_id)
                except Exception as agg_err:
                    # Non-fatal - continue execution even if telemetry aggregation fails
                    logger.warning(
                        f"[IMP-INT-001] Telemetry aggregation failed (non-fatal): {agg_err}"
                    )

                # IMP-TEL-001: Check for SLA breaches and emit alerts
                self._check_and_emit_sla_alerts(phase_id)

                # IMP-REL-015: Save checkpoint after phase completion
                # This enables crash recovery by persisting progress
                try:
                    self.executor.save_checkpoint()
                except Exception as ckpt_err:
                    logger.warning(f"[IMP-REL-015] Checkpoint save failed (non-fatal): {ckpt_err}")

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

                # IMP-LOOP-006: Record failure with circuit breaker
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_failure()
                    # Check if circuit just tripped
                    if self._circuit_breaker.is_open:
                        logger.critical(
                            f"[IMP-LOOP-006] Circuit breaker tripped after phase {phase_id} failure. "
                            f"Total trips: {self._circuit_breaker.total_trips}. "
                            f"Execution will be blocked until reset."
                        )
                        # IMP-MEM-004: Record circuit breaker event for root cause analysis
                        if self._feedback_pipeline is not None:
                            self._feedback_pipeline.record_circuit_breaker_event(
                                failure_count=self._circuit_breaker.consecutive_failures,
                                last_failure_reason=f"Phase {phase_id} failed with status: {status}",
                                timestamp=datetime.now(timezone.utc),
                            )
                        stop_reason = "circuit_breaker_tripped"
                        break

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

                # IMP-REL-015: Save checkpoint after phase failure
                # This enables recovery even when phases fail
                try:
                    self.executor.save_checkpoint()
                except Exception as ckpt_err:
                    logger.warning(f"[IMP-REL-015] Checkpoint save failed (non-fatal): {ckpt_err}")

            # IMP-INT-005: Immediate cost check after phase completion
            # Check cost recommendations before waiting, to stop faster if budget is exceeded
            post_phase_cost = self._check_cost_recommendations()
            if post_phase_cost.should_pause:
                logger.warning(
                    f"[IMP-INT-005] Cost pause triggered after phase {phase_id}: "
                    f"{post_phase_cost.reason}. "
                    f"Current spend: {post_phase_cost.current_spend:,.0f} tokens. "
                    f"Budget remaining: {post_phase_cost.budget_remaining_pct:.1f}%"
                )
                self._pause_for_cost_limit(post_phase_cost)
                stop_reason = "cost_limit_reached"
                break

            # Wait before next iteration
            if iteration < effective_max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                self._adaptive_sleep(is_idle=False, base_interval=poll_interval)
        else:
            # IMP-REL-004: Max iterations reached - log warning and set stop reason
            logger.warning(
                f"Execution loop reached max iterations ({effective_max_iterations}), "
                "stopping to prevent resource exhaustion"
            )
            stop_reason = "max_iterations"

        logger.info("Autonomous execution loop finished")

        # IMP-LOOP-006: Update instance-level counters
        self._iteration_count = iteration
        self._total_phases_executed = phases_executed
        self._total_phases_failed = phases_failed

        # Build stats with optional circuit breaker info
        stats = {
            "iteration": iteration,
            "phases_executed": phases_executed,
            "phases_failed": phases_failed,
            "stop_reason": stop_reason,
        }

        # IMP-LOOP-006: Include circuit breaker statistics
        if self._circuit_breaker is not None:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats()

        return stats

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
            # IMP-LOOP-001: Persist telemetry insights with graceful error handling
            self._persist_loop_insights()

            # IMP-ARCH-009: Generate improvement tasks from telemetry for self-improvement loop
            # IMP-LOOP-001: Gate task generation on feedback loop health
            health_status = self._get_feedback_loop_health()
            if health_status in (
                FeedbackLoopHealth.HEALTHY.value,
                FeedbackLoopHealth.DEGRADED.value,
            ):
                # IMP-LOOP-002: Check circuit breaker before task generation
                if self._circuit_breaker is not None and not self._circuit_breaker.is_available():
                    logger.warning("[IMP-LOOP-002] Circuit breaker OPEN - skipping task generation")
                else:
                    try:
                        self._generate_improvement_tasks()
                    except Exception as e:
                        logger.warning(f"Failed to generate improvement tasks: {e}")
            else:
                # IMP-REL-001: Auto-pause task generation on critical health issues
                logger.warning(
                    f"[IMP-REL-001] Auto-pausing task generation due to "
                    f"ATTENTION_REQUIRED status (health_status={health_status})"
                )
                self._task_generation_paused = True
                self._emit_alert(
                    "Task generation auto-paused - manual intervention required. "
                    f"Health status: {health_status}"
                )

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
            else:
                # IMP-LOOP-005: Mark tasks as failed/retry when run has failures
                try:
                    self._mark_improvement_tasks_failed(phases_failed)
                except Exception as e:
                    logger.warning(f"Failed to mark improvement tasks as failed: {e}")

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

            # IMP-REL-015: Mark run as completed in checkpoint (clean completion)
            try:
                self.executor.mark_run_completed()
                logger.info("[IMP-REL-015] Run marked as completed in checkpoint")
            except Exception as e:
                logger.warning(f"[IMP-REL-015] Failed to mark run complete: {e}")
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

    def _record_execution_feedback(
        self,
        phase: Dict,
        success: bool,
        status: str,
        execution_start_time: float,
        memory_context: Optional[str] = None,
    ) -> None:
        """Record task execution feedback to memory for learning.

        IMP-LOOP-005: Captures execution results (success/failure) and stores them
        in memory to enable learning from past executions and improve future context.

        Args:
            phase: The phase dictionary with execution details
            success: Whether the phase executed successfully
            status: The final status string from execution
            execution_start_time: Unix timestamp when execution started
            memory_context: Optional memory context that was injected for this phase
        """
        # Check if memory service is available
        memory_service = getattr(self.executor, "memory_service", None)
        if memory_service is None:
            logger.debug("[IMP-LOOP-005] Memory service not available, skipping feedback")
            return

        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_type = phase.get("phase_type")
            project_id = getattr(self.executor, "_get_project_slug", lambda: "default")()
            run_id = getattr(self.executor, "run_id", "unknown")

            # Calculate execution time
            execution_time = time.time() - execution_start_time

            # Get tokens used for this phase (approximate)
            tokens_used = getattr(self.executor, "_run_tokens_used", 0)

            # Build error message for failures
            error_message = None
            if not success:
                error_message = f"Phase failed with status: {status}"
                # Try to get more specific error info if available
                phase_result = getattr(self.executor, "_last_phase_result", None)
                if phase_result and isinstance(phase_result, dict):
                    error_detail = phase_result.get("error") or phase_result.get("message")
                    if error_detail:
                        error_message = f"{error_message}. Detail: {error_detail}"

            # Build context summary
            context_summary = None
            if memory_context:
                # Summarize the context that was used
                context_lines = memory_context.split("\n")[:10]
                context_summary = "\n".join(context_lines)

            # Extract learnings based on outcome
            learnings = []
            if success:
                learnings.append(f"Phase type '{phase_type}' completed successfully")
                if execution_time < 30:
                    learnings.append("Fast execution - phase was efficient")
                elif execution_time > 300:
                    learnings.append("Long execution time - may need optimization")
            else:
                learnings.append(f"Phase type '{phase_type}' failed with status: {status}")
                if "timeout" in status.lower():
                    learnings.append(
                        "Timeout occurred - consider increasing timeout or reducing scope"
                    )
                elif "budget" in status.lower():
                    learnings.append("Budget exhausted - consider reducing token usage")

            # Write feedback to memory
            memory_service.write_task_execution_feedback(
                run_id=run_id,
                phase_id=phase_id,
                project_id=project_id,
                success=success,
                phase_type=phase_type,
                execution_time_seconds=execution_time,
                error_message=error_message,
                tokens_used=tokens_used,
                context_summary=context_summary,
                learnings=learnings,
            )

            # IMP-MEM-011: Track memory write for maintenance scheduling
            self._increment_memory_write_count()

            logger.info(
                f"[IMP-LOOP-005] Recorded execution feedback for phase {phase_id} "
                f"(success={success}, time={execution_time:.1f}s)"
            )

        except Exception as e:
            # Non-fatal error - log and continue
            logger.warning(f"[IMP-LOOP-005] Failed to record execution feedback: {e}")

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

    def _validate_telemetry_feedback(
        self,
        ranked_issues: Dict,
    ) -> tuple[bool, Dict, int]:
        """Validate telemetry feedback data before memory storage.

        IMP-LOOP-002: Ensures data integrity and proper feedback propagation
        between telemetry collection and memory service.

        Args:
            ranked_issues: Dictionary containing telemetry analysis results with
                          'top_cost_sinks', 'top_failure_modes', 'top_retry_causes'.

        Returns:
            Tuple of (is_valid, validated_issues, validation_error_count).
        """
        from autopack.memory.memory_service import TelemetryFeedbackValidator

        if not isinstance(ranked_issues, dict):
            logger.warning(
                f"[IMP-LOOP-002] Invalid telemetry feedback type: {type(ranked_issues).__name__}"
            )
            return False, {}, 1

        validated_issues: Dict = {}
        total_errors = 0

        issue_categories = ["top_cost_sinks", "top_failure_modes", "top_retry_causes"]
        insight_type_map = {
            "top_cost_sinks": "cost_sink",
            "top_failure_modes": "failure_mode",
            "top_retry_causes": "retry_cause",
        }

        for category in issue_categories:
            issues = ranked_issues.get(category, [])
            if not isinstance(issues, list):
                logger.warning(
                    f"[IMP-LOOP-002] Invalid {category} type: {type(issues).__name__}, expected list"
                )
                total_errors += 1
                validated_issues[category] = []
                continue

            validated_list = []
            for issue in issues:
                # Convert issue to insight format for validation
                insight = {
                    "insight_type": insight_type_map.get(category, "unknown"),
                    "description": issue.get("description", str(issue)),
                    "phase_id": issue.get("phase_id"),
                    "run_id": issue.get("run_id"),
                    "suggested_action": issue.get("suggested_action"),
                }

                is_valid, errors = TelemetryFeedbackValidator.validate_insight(insight)
                if is_valid:
                    validated_list.append(issue)
                else:
                    total_errors += 1
                    logger.debug(f"[IMP-LOOP-002] Skipping invalid {category} issue: {errors}")
                    # Sanitize and include anyway for non-critical validation errors
                    sanitized = TelemetryFeedbackValidator.sanitize_insight(insight)
                    # Merge sanitized fields back into original issue
                    issue_copy = dict(issue)
                    issue_copy["description"] = sanitized.get("description", "")
                    validated_list.append(issue_copy)

            validated_issues[category] = validated_list

        is_valid = total_errors == 0
        if total_errors > 0:
            logger.info(
                f"[IMP-LOOP-002] Telemetry feedback validation: "
                f"{total_errors} issues sanitized/corrected"
            )

        return is_valid, validated_issues, total_errors

    def _persist_telemetry_insights(self) -> None:
        """Analyze and persist telemetry insights to memory after run completion.

        Implements IMP-ARCH-001: Wire Telemetry Analyzer to Memory Service.
        IMP-INT-002: Explicit bridge invocation after aggregation.
        IMP-LOOP-002: Added validation to ensure data integrity before persistence.

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

            # IMP-INT-002: Persist aggregated insights to memory via bridge
            # This ensures insights are persisted before validation processing
            self._persist_insights_to_memory(ranked_issues, context="run_finalization")

            # IMP-LOOP-002: Validate telemetry feedback before memory storage
            is_valid, validated_issues, error_count = self._validate_telemetry_feedback(
                ranked_issues
            )
            if not is_valid:
                logger.info(
                    f"[IMP-LOOP-002] Telemetry feedback validated with {error_count} corrections"
                )
            # Use validated issues for logging and further processing
            ranked_issues = validated_issues

            logger.info(
                f"[IMP-ARCH-001] Analyzed telemetry: "
                f"{len(ranked_issues.get('top_cost_sinks', []))} cost sinks, "
                f"{len(ranked_issues.get('top_failure_modes', []))} failure modes, "
                f"{len(ranked_issues.get('top_retry_causes', []))} retry causes"
            )

            # IMP-INT-003: Generate tasks from the validated ranked issues and queue for execution
            # This completes the insight→task→execution cycle by ensuring tasks are generated
            # directly from the insights that were just persisted to memory
            self._generate_tasks_from_ranked_issues(ranked_issues, context="run_finalization")

        except Exception as e:
            logger.warning(f"[IMP-ARCH-001] Failed to analyze telemetry: {e}")
            return

    def _persist_loop_insights(self, insights: dict | None = None) -> None:
        """Persist loop insights with graceful error handling.

        IMP-LOOP-001: Wraps persist_insights call with try/except for graceful degradation.
        Insight persistence is non-critical; failures should not crash the autonomous loop.

        Args:
            insights: Optional insights dictionary for logging context.
        """
        try:
            self._persist_telemetry_insights()
            logger.debug("Loop insights persisted successfully")
        except Exception as e:
            # Log warning with extra context but don't re-raise
            extra = {}
            if insights:
                extra["insights_keys"] = list(insights.keys())
            logger.warning(
                f"Failed to persist loop insights (non-fatal): {e}",
                extra=extra,
            )
            # Continue loop execution - insight persistence is non-critical

        # IMP-LOOP-001: Flush pending insights from feedback pipeline
        if self._feedback_pipeline is not None:
            try:
                flushed = self._feedback_pipeline.flush_pending_insights()
                if flushed > 0:
                    logger.info(
                        f"[IMP-LOOP-001] Flushed {flushed} pending feedback pipeline insights"
                    )

                # Also persist any learning hints
                hints_persisted = self._feedback_pipeline.persist_learning_hints()
                if hints_persisted > 0:
                    logger.info(
                        f"[IMP-LOOP-001] Persisted {hints_persisted} learning hints from feedback pipeline"
                    )

                # Log final stats
                stats = self._feedback_pipeline.get_stats()
                logger.info(
                    f"[IMP-LOOP-001] Feedback pipeline stats: "
                    f"outcomes_processed={stats.get('outcomes_processed', 0)}, "
                    f"insights_persisted={stats.get('insights_persisted', 0)}, "
                    f"context_retrievals={stats.get('context_retrievals', 0)}"
                )
            except Exception as e:
                logger.warning(f"[IMP-LOOP-001] Failed to flush feedback pipeline (non-fatal): {e}")

    def _generate_improvement_tasks(self) -> list:
        """Generate improvement tasks from telemetry (ROAD-C).

        Implements IMP-ARCH-004: Autonomous Task Generator.
        Implements IMP-FEAT-001: Wire TelemetryAnalyzer output to TaskGenerator.

        Converts telemetry insights into improvement tasks for self-improvement feedback loop.
        The ROAD-C pipeline connects:
        1. TelemetryAnalyzer.aggregate_telemetry() -> ranked issues
        2. AutonomousTaskGenerator.generate_tasks(telemetry_insights=...) -> improvement tasks

        Returns:
            List of GeneratedTask objects
        """
        # IMP-REL-001: Check if task generation is paused due to health issues
        if self._task_generation_paused:
            logger.info("[IMP-REL-001] Task generation skipped - paused due to health issues")
            return []

        try:
            from autopack.config import settings as config_settings
            from autopack.roadc import AutonomousTaskGenerator
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
            # IMP-FEAT-001: Get telemetry insights to wire to task generation
            telemetry_insights = None
            analyzer = self._get_telemetry_analyzer()
            if analyzer:
                try:
                    telemetry_insights = analyzer.aggregate_telemetry(window_days=7)
                    total_issues = (
                        len(telemetry_insights.get("top_cost_sinks", []))
                        + len(telemetry_insights.get("top_failure_modes", []))
                        + len(telemetry_insights.get("top_retry_causes", []))
                    )
                    logger.info(
                        f"[IMP-FEAT-001] Retrieved {total_issues} telemetry issues for task generation"
                    )
                except Exception as tel_err:
                    logger.warning(
                        f"[IMP-FEAT-001] Failed to get telemetry insights, "
                        f"falling back to memory retrieval: {tel_err}"
                    )
                    telemetry_insights = None

            # IMP-ARCH-017: Pass db_session to enable telemetry aggregation in task generator
            # The generator can now call aggregate_telemetry() internally if no insights provided
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            db_session = getattr(self.executor, "db_session", None)
            generator = AutonomousTaskGenerator(
                db_session=db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )
            result = generator.generate_tasks(
                max_tasks=task_gen_config.get("max_tasks_per_run", 10),
                min_confidence=task_gen_config.get("min_confidence", 0.7),
                telemetry_insights=telemetry_insights,
            )

            logger.info(
                f"[IMP-ARCH-004] Generated {len(result.tasks_generated)} tasks "
                f"from {result.insights_processed} insights "
                f"({result.generation_time_ms:.0f}ms)"
            )

            # IMP-TELE-001: Record task generation time for latency tracking
            if self._latency_tracker and result.tasks_generated:
                self._latency_tracker.record_stage(
                    PipelineStage.TASK_GENERATED,
                    metadata={
                        "tasks_generated": len(result.tasks_generated),
                        "generation_time_ms": result.generation_time_ms,
                    },
                )

            # IMP-ARCH-014: Persist generated tasks to database
            if result.tasks_generated:
                try:
                    run_id = getattr(self.executor, "run_id", None)
                    persisted_count = generator.persist_tasks(result.tasks_generated, run_id)
                    logger.info(f"[IMP-ARCH-014] Persisted {persisted_count} tasks to database")
                except Exception as persist_err:
                    logger.warning(f"[IMP-ARCH-014] Failed to persist tasks: {persist_err}")

                # IMP-LOOP-021: Register generated tasks for execution verification
                tracker = self._get_task_effectiveness_tracker()
                if tracker:
                    for task in result.tasks_generated:
                        try:
                            tracker.register_task(
                                task_id=task.task_id,
                                priority=getattr(task, "priority", ""),
                                category=getattr(task, "estimated_effort", ""),
                            )
                        except Exception as reg_err:
                            logger.debug(
                                f"[IMP-LOOP-021] Failed to register task {task.task_id}: {reg_err}"
                            )
                    logger.info(
                        f"[IMP-LOOP-021] Registered {len(result.tasks_generated)} tasks "
                        "for execution verification"
                    )

                # IMP-LOOP-023: Check goal alignment to detect drift from stated objectives
                # IMP-LOOP-028: Auto-correct drift by generating corrective tasks
                if self._goal_drift_detector is not None:
                    try:
                        drift_result = self._goal_drift_detector.calculate_drift(
                            result.tasks_generated
                        )
                        if drift_result.is_drifting(self._goal_drift_threshold):
                            self._emit_alert(
                                f"Goal drift detected in task generation. "
                                f"Drift score: {drift_result.drift_score:.2f} "
                                f"(threshold: {self._goal_drift_threshold}). "
                                f"Misaligned tasks: {len(drift_result.misaligned_tasks)}/{drift_result.total_task_count}"
                            )
                            logger.warning(
                                f"[IMP-LOOP-023] Goal drift detected: "
                                f"score={drift_result.drift_score:.3f}, "
                                f"aligned={drift_result.aligned_task_count}/{drift_result.total_task_count}"
                            )

                            # IMP-LOOP-028: Generate corrective tasks for drift
                            corrective_tasks = self._goal_drift_detector.realignment_action(
                                result.tasks_generated
                            )
                            if corrective_tasks:
                                self._queue_correction_tasks(corrective_tasks, generator, run_id)
                                logger.info(
                                    f"[IMP-LOOP-028] Queued {len(corrective_tasks)} "
                                    f"corrective tasks for drift correction"
                                )
                        else:
                            logger.info(
                                f"[IMP-LOOP-023] Tasks aligned with objectives: "
                                f"drift_score={drift_result.drift_score:.3f}, "
                                f"aligned={drift_result.aligned_task_count}/{drift_result.total_task_count}"
                            )
                    except Exception as drift_err:
                        logger.debug(
                            f"[IMP-LOOP-023] Goal drift check failed (non-fatal): {drift_err}"
                        )

            return result.tasks_generated
        except Exception as e:
            logger.warning(f"[IMP-ARCH-004] Failed to generate improvement tasks: {e}")
            return []
