"""Telemetry persistence management for autonomous execution loop.

Extracted from autonomous_loop.py as part of IMP-MAINT-002.
Handles telemetry aggregation, insight persistence to memory, and task generation.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.telemetry.analyzer import TelemetryAnalyzer
    from autopack.telemetry.meta_metrics import MetaMetricsTracker, PipelineLatencyTracker
    from autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge

from autopack.telemetry.meta_metrics import PipelineStage

logger = logging.getLogger(__name__)


class TelemetryPersistenceManager:
    """Manages telemetry persistence and insight generation.

    IMP-MAINT-002: Extracted from AutonomousLoop to improve maintainability.
    Encapsulates logic for:
    1. Telemetry analyzer management
    2. TelemetryToMemoryBridge for persisting insights
    3. Task generation from ranked issues
    4. Telemetry aggregation throttling

    This class bridges telemetry collection with memory storage and task generation,
    completing the insight→task→execution cycle.
    """

    def __init__(
        self,
        db_session: Any = None,
        memory_service: Any = None,
        aggregation_interval: int = 3,
        latency_tracker: Optional["PipelineLatencyTracker"] = None,
        meta_metrics_tracker: Optional["MetaMetricsTracker"] = None,
    ):
        """Initialize the TelemetryPersistenceManager.

        Args:
            db_session: Database session for telemetry queries
            memory_service: Memory service for insight persistence
            aggregation_interval: Phases between telemetry aggregations
            latency_tracker: Pipeline latency tracker for stage timing
            meta_metrics_tracker: Meta-metrics tracker for health monitoring
        """
        self._db_session = db_session
        self._memory_service = memory_service
        self._aggregation_interval = aggregation_interval
        self._phases_since_last_aggregation = 0
        self._latency_tracker = latency_tracker
        self._meta_metrics_tracker = meta_metrics_tracker

        # Lazy-initialized instances
        self._telemetry_analyzer: Optional["TelemetryAnalyzer"] = None
        self._telemetry_to_memory_bridge: Optional["TelemetryToMemoryBridge"] = None

    def set_db_session(self, db_session: Any) -> None:
        """Update the database session.

        Args:
            db_session: New database session to use
        """
        self._db_session = db_session
        # Reset analyzer so it's recreated with new session
        self._telemetry_analyzer = None

    def set_memory_service(self, memory_service: Any) -> None:
        """Update the memory service.

        Args:
            memory_service: New memory service to use
        """
        self._memory_service = memory_service
        # Reset bridge so it's recreated with new service
        self._telemetry_to_memory_bridge = None

    def get_telemetry_analyzer(self) -> Optional["TelemetryAnalyzer"]:
        """Get or create the telemetry analyzer instance.

        Returns:
            TelemetryAnalyzer instance if database session is available, None otherwise.
        """
        if self._telemetry_analyzer is None:
            if self._db_session:
                from autopack.telemetry.analyzer import TelemetryAnalyzer

                # IMP-ARCH-015: Pass memory_service to enable telemetry -> memory bridge
                self._telemetry_analyzer = TelemetryAnalyzer(
                    self._db_session,
                    memory_service=self._memory_service,
                )
        return self._telemetry_analyzer

    def get_telemetry_to_memory_bridge(self) -> Optional["TelemetryToMemoryBridge"]:
        """Get or create the TelemetryToMemoryBridge instance.

        IMP-INT-002: Provides a bridge for persisting telemetry insights to memory
        after aggregation. The bridge is lazily initialized and reused.

        Returns:
            TelemetryToMemoryBridge instance if memory_service is available, None otherwise.
        """
        if self._telemetry_to_memory_bridge is None:
            if self._memory_service and getattr(self._memory_service, "enabled", False):
                from autopack.telemetry.telemetry_to_memory_bridge import TelemetryToMemoryBridge

                self._telemetry_to_memory_bridge = TelemetryToMemoryBridge(
                    memory_service=self._memory_service,
                    enabled=True,
                )
        return self._telemetry_to_memory_bridge

    def flatten_ranked_issues_to_dicts(self, ranked_issues: Dict) -> List[Dict]:
        """Convert ranked issues from aggregate_telemetry() to a flat list of dicts.

        IMP-INT-002: Converts RankedIssue objects to dictionaries suitable for
        TelemetryToMemoryBridge.persist_insights().

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.

        Returns:
            Flat list of dictionaries ready for bridge.persist_insights().
        """
        flat_issues: List[Dict] = []

        for issue in ranked_issues.get("top_cost_sinks", []):
            flat_issues.append(
                {
                    "issue_type": "cost_sink",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "high",
                    "description": f"Phase {issue.phase_id} consuming {issue.metric_value:,.0f} tokens",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Optimize token usage for {issue.phase_type}",
                }
            )

        for issue in ranked_issues.get("top_failure_modes", []):
            flat_issues.append(
                {
                    "issue_type": "failure_mode",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "high",
                    "description": f"Failure: {issue.details.get('outcome', '')} - {issue.details.get('stop_reason', '')}",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Fix {issue.phase_type} failure pattern",
                }
            )

        for issue in ranked_issues.get("top_retry_causes", []):
            flat_issues.append(
                {
                    "issue_type": "retry_cause",
                    "insight_id": f"{issue.rank}",
                    "rank": issue.rank,
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "severity": "medium",
                    "description": f"Retry cause: {issue.details.get('stop_reason', '')}",
                    "metric_value": issue.metric_value,
                    "occurrences": issue.details.get("count", 1),
                    "details": issue.details,
                    "suggested_action": f"Increase timeout or optimize {issue.phase_type}",
                }
            )

        return flat_issues

    def persist_insights_to_memory(
        self,
        ranked_issues: Dict,
        run_id: str = "unknown",
        project_id: str = "default",
        context: str = "phase_telemetry",
    ) -> int:
        """Persist ranked issues to memory via TelemetryToMemoryBridge.

        IMP-INT-002: Invokes TelemetryToMemoryBridge.persist_insights() after
        telemetry aggregation to store insights in memory for future retrieval.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
            run_id: Current run ID for tracking
            project_id: Project identifier
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of insights persisted, or 0 if persistence failed/skipped.
        """
        bridge = self.get_telemetry_to_memory_bridge()
        if not bridge:
            logger.debug(f"[IMP-INT-002] No bridge available for {context} persistence")
            return 0

        try:
            # Flatten ranked issues to dicts for bridge
            flat_issues = self.flatten_ranked_issues_to_dicts(ranked_issues)

            if not flat_issues:
                logger.debug(f"[IMP-INT-002] No issues to persist for {context}")
                return 0

            # Persist to memory
            persisted_count = bridge.persist_insights(
                ranked_issues=flat_issues,
                run_id=run_id,
                project_id=project_id,
            )

            logger.info(
                f"[IMP-INT-002] Persisted {persisted_count} insights to memory "
                f"(context={context}, run_id={run_id})"
            )

            # IMP-TEL-001: Record memory persistence stage for latency tracking
            if self._latency_tracker is not None and persisted_count > 0:
                self._latency_tracker.record_stage(
                    PipelineStage.MEMORY_PERSISTED,
                    metadata={
                        "persisted_count": persisted_count,
                        "context": context,
                        "run_id": run_id,
                    },
                )

            return persisted_count

        except Exception as e:
            # Non-fatal - persistence failure should not block execution
            logger.warning(
                f"[IMP-INT-002] Failed to persist insights to memory "
                f"(context={context}, non-fatal): {e}"
            )
            return 0

    def generate_tasks_from_ranked_issues(
        self,
        ranked_issues: Dict,
        run_id: Optional[str] = None,
        current_run_phases: Optional[List[Dict]] = None,
        context: str = "phase_telemetry",
    ) -> int:
        """Generate improvement tasks from ranked issues and queue them for execution.

        IMP-INT-003: Wires ROADC TaskGenerator into executor loop. After telemetry
        insights are persisted to memory, this method generates improvement tasks
        from those same insights and persists them to the database for execution.

        This completes the insight→task→execution cycle by ensuring tasks are
        generated directly from persisted insights without re-aggregating telemetry.

        Args:
            ranked_issues: Dictionary from TelemetryAnalyzer.aggregate_telemetry()
                containing top_cost_sinks, top_failure_modes, top_retry_causes.
            run_id: Current run ID for tracking
            current_run_phases: Current run phases for same-run task injection
            context: Context string for logging (e.g., "phase_telemetry", "run_finalization")

        Returns:
            Number of tasks generated and persisted, or 0 if generation failed/skipped.
        """
        try:
            from autopack.config import settings as config_settings
            from autopack.roadc import AutonomousTaskGenerator
        except ImportError:
            logger.debug("[IMP-INT-003] ROADC module not available for task generation")
            return 0

        # Check if task generation is enabled
        # Use direct attribute access to match autonomous_loop.py pattern
        if not getattr(config_settings, "task_generation_enabled", False):
            logger.debug("[IMP-INT-003] Task generation not enabled in settings")
            return 0

        # Check if we have any issues to generate tasks from
        total_issues = (
            len(ranked_issues.get("top_cost_sinks", []))
            + len(ranked_issues.get("top_failure_modes", []))
            + len(ranked_issues.get("top_retry_causes", []))
        )

        if total_issues == 0:
            logger.debug(f"[IMP-INT-003] No ranked issues for task generation ({context})")
            return 0

        try:
            # IMP-INT-003: Generate tasks directly from the ranked issues that were just persisted
            # IMP-LOOP-025: Pass metrics tracker for throughput observability
            generator = AutonomousTaskGenerator(
                db_session=self._db_session,
                metrics_tracker=self._meta_metrics_tracker,
            )

            # IMP-LOOP-003: Pass current run phases as backlog for same-run injection
            # of high-priority (critical) tasks
            result = generator.generate_tasks(
                max_tasks=getattr(config_settings, "task_generation_max_tasks_per_run", 10),
                min_confidence=getattr(config_settings, "task_generation_min_confidence", 0.7),
                telemetry_insights=ranked_issues,
                run_id=run_id,
                backlog=current_run_phases,
            )

            tasks_generated = len(result.tasks_generated)
            logger.info(
                f"[IMP-INT-003] Generated {tasks_generated} tasks from {total_issues} "
                f"ranked issues ({context}, {result.generation_time_ms:.0f}ms)"
            )

            # Persist generated tasks to database for execution queue
            if result.tasks_generated:
                try:
                    persisted_count = generator.persist_tasks(result.tasks_generated, run_id)
                    logger.info(
                        f"[IMP-INT-003] Queued {persisted_count} tasks for execution ({context})"
                    )
                    return persisted_count
                except Exception as persist_err:
                    logger.warning(
                        f"[IMP-INT-003] Failed to queue tasks for execution "
                        f"(context={context}, non-fatal): {persist_err}"
                    )
                    return 0

            return 0

        except Exception as e:
            # Non-fatal - task generation failure should not block execution
            logger.warning(
                f"[IMP-INT-003] Failed to generate tasks from ranked issues "
                f"(context={context}, non-fatal): {e}"
            )
            return 0

    def aggregate_phase_telemetry(
        self,
        phase_id: str,
        run_id: str = "unknown",
        project_id: str = "default",
        current_run_phases: Optional[List[Dict]] = None,
        health_callback: Optional[Callable[[Dict], None]] = None,
        force: bool = False,
    ) -> Optional[Dict]:
        """Aggregate telemetry after phase completion for self-improvement feedback.

        IMP-INT-001: Wires TelemetryAnalyzer.aggregate_telemetry() into the autonomous
        execution loop after phase completion. This enables the self-improvement
        architecture by ensuring telemetry insights are aggregated and persisted
        during execution, not just at the end of the run.

        Uses throttling to avoid expensive database queries after every phase.
        By default, aggregates every N phases (controlled by aggregation_interval).

        Args:
            phase_id: ID of the phase that just completed (for logging)
            run_id: Current run ID for tracking
            project_id: Project identifier
            current_run_phases: Current run phases for same-run task injection
            health_callback: Optional callback for updating circuit breaker health
            force: If True, bypass throttling and aggregate immediately

        Returns:
            Dictionary of ranked issues from aggregate_telemetry(), or None if
            aggregation was skipped (throttled) or failed.
        """
        # Increment phase counter
        self._phases_since_last_aggregation += 1

        # Check if we should aggregate (throttling)
        should_aggregate = force or (
            self._phases_since_last_aggregation >= self._aggregation_interval
        )

        if not should_aggregate:
            logger.debug(
                f"[IMP-INT-001] Skipping telemetry aggregation after phase {phase_id} "
                f"({self._phases_since_last_aggregation}/{self._aggregation_interval} phases)"
            )
            return None

        analyzer = self.get_telemetry_analyzer()
        if not analyzer:
            logger.debug("[IMP-INT-001] No telemetry analyzer available for aggregation")
            return None

        try:
            # Aggregate telemetry from database
            ranked_issues = analyzer.aggregate_telemetry(window_days=7)

            # IMP-TEL-001: Record telemetry collection stage for latency tracking
            if self._latency_tracker is not None:
                self._latency_tracker.record_stage(
                    PipelineStage.TELEMETRY_COLLECTED,
                    metadata={"phase_id": phase_id, "forced": force},
                )

            # Reset throttle counter
            self._phases_since_last_aggregation = 0

            # Log aggregation results
            total_issues = (
                len(ranked_issues.get("top_cost_sinks", []))
                + len(ranked_issues.get("top_failure_modes", []))
                + len(ranked_issues.get("top_retry_causes", []))
            )
            logger.info(
                f"[IMP-INT-001] Aggregated telemetry after phase {phase_id}: "
                f"{total_issues} issues found "
                f"(cost_sinks={len(ranked_issues.get('top_cost_sinks', []))}, "
                f"failure_modes={len(ranked_issues.get('top_failure_modes', []))}, "
                f"retry_causes={len(ranked_issues.get('top_retry_causes', []))})"
            )

            # IMP-INT-002: Persist aggregated insights to memory via bridge
            self.persist_insights_to_memory(
                ranked_issues,
                run_id=run_id,
                project_id=project_id,
                context="phase_telemetry",
            )

            # IMP-FBK-002: Update circuit breaker health report from meta-metrics
            if health_callback is not None:
                health_callback(ranked_issues)

            return ranked_issues

        except Exception as e:
            # Non-fatal - telemetry aggregation failure should not block execution
            logger.warning(
                f"[IMP-INT-001] Failed to aggregate telemetry after phase {phase_id} "
                f"(non-fatal): {e}"
            )
            return None

    def reset_aggregation_counter(self) -> None:
        """Reset the aggregation throttle counter."""
        self._phases_since_last_aggregation = 0

    @property
    def phases_since_last_aggregation(self) -> int:
        """Get number of phases since last aggregation."""
        return self._phases_since_last_aggregation
