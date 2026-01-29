"""Telemetry-to-Task Daemon for automatic task generation.

IMP-LOOP-030: Monitors telemetry insights and automatically creates
tasks from high-ROI patterns without manual intervention.

This daemon provides a closed-loop self-improvement mechanism by:
1. Periodically scanning telemetry data for actionable insights
2. Identifying high-ROI patterns (cost sinks, failure modes, retry causes)
3. Automatically generating improvement tasks via AutonomousTaskGenerator
4. Persisting tasks to both database and executor queue for execution

The daemon runs in a background thread and can be started/stopped gracefully.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default daemon configuration
DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
DEFAULT_MIN_CONFIDENCE = 0.7
DEFAULT_MAX_TASKS_PER_CYCLE = 5
DEFAULT_TELEMETRY_WINDOW_DAYS = 7


@dataclass
class DaemonCycleResult:
    """Result of a single daemon cycle (IMP-LOOP-030).

    Captures metrics about what the daemon accomplished in each cycle
    for observability and debugging.
    """

    cycle_number: int
    timestamp: datetime
    insights_found: int
    tasks_generated: int
    tasks_persisted: int
    tasks_queued: int
    cycle_duration_ms: float
    error: Optional[str] = None
    skipped_reason: Optional[str] = None


@dataclass
class DaemonStats:
    """Aggregate statistics for the daemon (IMP-LOOP-030).

    Tracks overall daemon performance across multiple cycles.
    """

    total_cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    total_insights_processed: int = 0
    total_tasks_generated: int = 0
    total_tasks_persisted: int = 0
    total_tasks_queued: int = 0
    avg_cycle_duration_ms: float = 0.0
    last_successful_cycle: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    cycle_history: List[DaemonCycleResult] = field(default_factory=list)


class TelemetryTaskDaemon:
    """Daemon that monitors insights and generates tasks automatically (IMP-LOOP-030).

    This daemon implements the telemetry-to-task automation loop, periodically
    scanning for high-ROI telemetry patterns and generating improvement tasks.

    Example usage:
        >>> from autopack.roadc.task_daemon import TelemetryTaskDaemon
        >>> daemon = TelemetryTaskDaemon(db_session=session)
        >>> daemon.start()
        >>> # ... daemon runs in background ...
        >>> daemon.stop()

    Attributes:
        interval_seconds: Time between daemon cycles (default: 300 seconds)
        min_confidence: Minimum confidence threshold for insights (default: 0.7)
        max_tasks_per_cycle: Maximum tasks to generate per cycle (default: 5)
    """

    # Maximum cycle history to keep in memory
    MAX_CYCLE_HISTORY = 100

    def __init__(
        self,
        db_session: Optional[Session] = None,
        memory_service: Optional["MemoryService"] = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        max_tasks_per_cycle: int = DEFAULT_MAX_TASKS_PER_CYCLE,
        telemetry_window_days: int = DEFAULT_TELEMETRY_WINDOW_DAYS,
        project_id: str = "default",
        auto_persist: bool = True,
        auto_queue: bool = True,
    ):
        """Initialize the TelemetryTaskDaemon.

        Args:
            db_session: SQLAlchemy database session for telemetry queries.
                       If None, daemon will attempt to create one on start.
            memory_service: Optional MemoryService for insight retrieval.
            interval_seconds: Time between daemon cycles in seconds.
            min_confidence: Minimum confidence threshold for insight filtering.
            max_tasks_per_cycle: Maximum number of tasks to generate per cycle.
            telemetry_window_days: Number of days of telemetry to analyze.
            project_id: Project ID for namespace isolation (IMP-MEM-015).
            auto_persist: Whether to automatically persist tasks to database.
            auto_queue: Whether to automatically emit tasks to executor queue.
        """
        self._db_session = db_session
        self._memory_service = memory_service
        self._interval = interval_seconds
        self._min_confidence = min_confidence
        self._max_tasks_per_cycle = max_tasks_per_cycle
        self._telemetry_window_days = telemetry_window_days
        self._project_id = project_id
        self._auto_persist = auto_persist
        self._auto_queue = auto_queue

        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Statistics
        self._stats = DaemonStats()
        self._cycle_count = 0

        # Components (lazily initialized)
        self._analyzer: Optional["TelemetryAnalyzer"] = None
        self._task_generator: Optional["AutonomousTaskGenerator"] = None

        logger.info(
            f"[IMP-LOOP-030] TelemetryTaskDaemon initialized: "
            f"interval={interval_seconds}s, min_confidence={min_confidence}, "
            f"max_tasks={max_tasks_per_cycle}"
        )

    @property
    def is_running(self) -> bool:
        """Check if the daemon is currently running."""
        return self._running

    @property
    def stats(self) -> DaemonStats:
        """Get current daemon statistics."""
        with self._lock:
            return self._stats

    def start(self) -> bool:
        """Start the daemon loop.

        Returns:
            True if daemon started successfully, False if already running.
        """
        with self._lock:
            if self._running:
                logger.warning("[IMP-LOOP-030] Daemon already running")
                return False

            # Initialize components
            if not self._initialize_components():
                logger.error("[IMP-LOOP-030] Failed to initialize daemon components")
                return False

            self._running = True
            self._stop_event.clear()

            # Start background thread
            self._thread = threading.Thread(
                target=self._run_loop,
                name="TelemetryTaskDaemon",
                daemon=True,
            )
            self._thread.start()

            logger.info(f"[IMP-LOOP-030] Daemon started, polling every {self._interval} seconds")
            return True

    def stop(self, timeout: float = 10.0) -> bool:
        """Stop the daemon gracefully.

        Args:
            timeout: Maximum time to wait for daemon to stop (seconds).

        Returns:
            True if daemon stopped cleanly, False if timeout occurred.
        """
        with self._lock:
            if not self._running:
                logger.debug("[IMP-LOOP-030] Daemon not running")
                return True

            logger.info("[IMP-LOOP-030] Stopping daemon...")
            self._running = False
            self._stop_event.set()

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    f"[IMP-LOOP-030] Daemon thread did not stop within {timeout}s timeout"
                )
                return False

        logger.info(
            f"[IMP-LOOP-030] Daemon stopped. Stats: {self._stats.total_cycles} cycles, "
            f"{self._stats.total_tasks_generated} tasks generated"
        )
        return True

    def run_once(self) -> DaemonCycleResult:
        """Run a single daemon cycle (useful for testing and manual triggers).

        This method runs one iteration of the daemon loop synchronously,
        without starting the background thread.

        Returns:
            DaemonCycleResult with cycle metrics.
        """
        if not self._initialize_components():
            return DaemonCycleResult(
                cycle_number=0,
                timestamp=datetime.now(timezone.utc),
                insights_found=0,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=0.0,
                error="Failed to initialize components",
            )

        return self._execute_cycle()

    def _initialize_components(self) -> bool:
        """Initialize TelemetryAnalyzer and AutonomousTaskGenerator.

        Returns:
            True if components initialized successfully.
        """
        try:
            # Import here to avoid circular imports
            from autopack.memory.memory_service import MemoryService
            from autopack.roadc.task_generator import AutonomousTaskGenerator
            from autopack.telemetry.analyzer import TelemetryAnalyzer

            # Initialize memory service if not provided
            if self._memory_service is None:
                self._memory_service = MemoryService()
                logger.debug("[IMP-LOOP-030] Created default MemoryService")

            # Initialize TelemetryAnalyzer
            if self._db_session is not None:
                self._analyzer = TelemetryAnalyzer(
                    db_session=self._db_session,
                    memory_service=self._memory_service,
                )
                logger.debug("[IMP-LOOP-030] TelemetryAnalyzer initialized with db_session")
            else:
                # Analyzer requires db_session - will use memory fallback
                logger.debug(
                    "[IMP-LOOP-030] No db_session provided, will use memory-based insights"
                )

            # Initialize AutonomousTaskGenerator
            self._task_generator = AutonomousTaskGenerator(
                memory_service=self._memory_service,
                db_session=self._db_session,
                project_id=self._project_id,
            )
            logger.debug("[IMP-LOOP-030] AutonomousTaskGenerator initialized")

            return True

        except ImportError as e:
            logger.error(f"[IMP-LOOP-030] Failed to import required components: {e}")
            return False
        except Exception as e:
            logger.error(f"[IMP-LOOP-030] Failed to initialize components: {e}")
            return False

    def _run_loop(self) -> None:
        """Main daemon loop that checks for high-ROI insights.

        This method runs in a background thread and periodically:
        1. Aggregates telemetry insights
        2. Generates improvement tasks
        3. Persists tasks to database and/or queue
        """
        logger.info("[IMP-LOOP-030] Daemon loop started")

        while self._running and not self._stop_event.is_set():
            try:
                # Execute a cycle
                result = self._execute_cycle()

                # Update statistics
                self._update_stats(result)

                # Log cycle result
                if result.error:
                    logger.warning(
                        f"[IMP-LOOP-030] Cycle {result.cycle_number} failed: {result.error}"
                    )
                elif result.skipped_reason:
                    logger.debug(
                        f"[IMP-LOOP-030] Cycle {result.cycle_number} skipped: {result.skipped_reason}"
                    )
                else:
                    logger.info(
                        f"[IMP-LOOP-030] Cycle {result.cycle_number} completed: "
                        f"{result.insights_found} insights -> {result.tasks_generated} tasks "
                        f"({result.tasks_persisted} persisted, {result.tasks_queued} queued) "
                        f"in {result.cycle_duration_ms:.0f}ms"
                    )

            except Exception as e:
                logger.error(f"[IMP-LOOP-030] Unexpected error in daemon loop: {e}")
                self._stats.last_error = str(e)
                self._stats.last_error_time = datetime.now(timezone.utc)

            # Wait for next cycle or stop signal
            if self._stop_event.wait(timeout=self._interval):
                break  # Stop signal received

        logger.info("[IMP-LOOP-030] Daemon loop exited")

    def _execute_cycle(self) -> DaemonCycleResult:
        """Execute a single daemon cycle.

        Returns:
            DaemonCycleResult with cycle metrics.
        """
        start_time = time.time()
        self._cycle_count += 1
        cycle_number = self._cycle_count

        try:
            # Step 1: Get telemetry insights
            telemetry_insights = None
            if self._analyzer is not None:
                telemetry_insights = self._analyzer.aggregate_telemetry(
                    window_days=self._telemetry_window_days
                )
                logger.debug(
                    f"[IMP-LOOP-030] Aggregated telemetry: "
                    f"{len(telemetry_insights.get('top_cost_sinks', []))} cost sinks, "
                    f"{len(telemetry_insights.get('top_failure_modes', []))} failures, "
                    f"{len(telemetry_insights.get('top_retry_causes', []))} retries"
                )

            # Step 2: Generate tasks from insights
            if self._task_generator is None:
                return DaemonCycleResult(
                    cycle_number=cycle_number,
                    timestamp=datetime.now(timezone.utc),
                    insights_found=0,
                    tasks_generated=0,
                    tasks_persisted=0,
                    tasks_queued=0,
                    cycle_duration_ms=(time.time() - start_time) * 1000,
                    error="TaskGenerator not initialized",
                )

            result = self._task_generator.generate_tasks(
                max_tasks=self._max_tasks_per_cycle,
                min_confidence=self._min_confidence,
                telemetry_insights=telemetry_insights,
                run_id=f"daemon-{cycle_number}-{int(time.time())}",
            )

            insights_count = result.insights_processed
            tasks_generated = len(result.tasks_generated)

            if tasks_generated == 0:
                return DaemonCycleResult(
                    cycle_number=cycle_number,
                    timestamp=datetime.now(timezone.utc),
                    insights_found=insights_count,
                    tasks_generated=0,
                    tasks_persisted=0,
                    tasks_queued=0,
                    cycle_duration_ms=(time.time() - start_time) * 1000,
                    skipped_reason="No high-ROI patterns detected",
                )

            # Step 3: Emit tasks for execution
            tasks_persisted = 0
            tasks_queued = 0

            if self._auto_persist or self._auto_queue:
                emit_result = self._task_generator.emit_tasks_for_execution(
                    tasks=result.tasks_generated,
                    persist_to_db=self._auto_persist,
                    emit_to_queue=self._auto_queue,
                    run_id=f"daemon-{cycle_number}",
                )
                tasks_persisted = emit_result.get("persisted", 0)
                tasks_queued = emit_result.get("queued", 0)

            cycle_duration_ms = (time.time() - start_time) * 1000

            return DaemonCycleResult(
                cycle_number=cycle_number,
                timestamp=datetime.now(timezone.utc),
                insights_found=insights_count,
                tasks_generated=tasks_generated,
                tasks_persisted=tasks_persisted,
                tasks_queued=tasks_queued,
                cycle_duration_ms=cycle_duration_ms,
            )

        except Exception as e:
            cycle_duration_ms = (time.time() - start_time) * 1000
            logger.error(f"[IMP-LOOP-030] Cycle {cycle_number} error: {e}")
            return DaemonCycleResult(
                cycle_number=cycle_number,
                timestamp=datetime.now(timezone.utc),
                insights_found=0,
                tasks_generated=0,
                tasks_persisted=0,
                tasks_queued=0,
                cycle_duration_ms=cycle_duration_ms,
                error=str(e),
            )

    def _update_stats(self, result: DaemonCycleResult) -> None:
        """Update aggregate statistics from cycle result.

        Args:
            result: The cycle result to incorporate into stats.
        """
        with self._lock:
            self._stats.total_cycles += 1

            if result.error:
                self._stats.failed_cycles += 1
                self._stats.last_error = result.error
                self._stats.last_error_time = result.timestamp
            else:
                self._stats.successful_cycles += 1
                self._stats.last_successful_cycle = result.timestamp

            self._stats.total_insights_processed += result.insights_found
            self._stats.total_tasks_generated += result.tasks_generated
            self._stats.total_tasks_persisted += result.tasks_persisted
            self._stats.total_tasks_queued += result.tasks_queued

            # Update rolling average duration
            if self._stats.total_cycles > 0:
                prev_total = self._stats.avg_cycle_duration_ms * (self._stats.total_cycles - 1)
                self._stats.avg_cycle_duration_ms = (
                    prev_total + result.cycle_duration_ms
                ) / self._stats.total_cycles

            # Keep cycle history (bounded)
            self._stats.cycle_history.append(result)
            if len(self._stats.cycle_history) > self.MAX_CYCLE_HISTORY:
                self._stats.cycle_history = self._stats.cycle_history[-self.MAX_CYCLE_HISTORY :]

    def get_recent_cycles(self, count: int = 10) -> List[DaemonCycleResult]:
        """Get recent cycle results.

        Args:
            count: Number of recent cycles to return.

        Returns:
            List of recent DaemonCycleResult objects (most recent last).
        """
        with self._lock:
            return self._stats.cycle_history[-count:]

    def update_configuration(
        self,
        interval_seconds: Optional[int] = None,
        min_confidence: Optional[float] = None,
        max_tasks_per_cycle: Optional[int] = None,
    ) -> None:
        """Update daemon configuration (takes effect next cycle).

        Args:
            interval_seconds: New interval between cycles.
            min_confidence: New minimum confidence threshold.
            max_tasks_per_cycle: New maximum tasks per cycle.
        """
        if interval_seconds is not None:
            self._interval = interval_seconds
            logger.info(f"[IMP-LOOP-030] Updated interval to {interval_seconds}s")

        if min_confidence is not None:
            self._min_confidence = min_confidence
            logger.info(f"[IMP-LOOP-030] Updated min_confidence to {min_confidence}")

        if max_tasks_per_cycle is not None:
            self._max_tasks_per_cycle = max_tasks_per_cycle
            logger.info(f"[IMP-LOOP-030] Updated max_tasks_per_cycle to {max_tasks_per_cycle}")


def create_task_daemon(
    db_session: Optional[Session] = None,
    **kwargs,
) -> TelemetryTaskDaemon:
    """Factory function to create a TelemetryTaskDaemon instance.

    This is the recommended way to create a daemon instance, as it handles
    initialization with appropriate defaults.

    Args:
        db_session: SQLAlchemy database session.
        **kwargs: Additional arguments passed to TelemetryTaskDaemon.

    Returns:
        Configured TelemetryTaskDaemon instance.
    """
    return TelemetryTaskDaemon(db_session=db_session, **kwargs)
