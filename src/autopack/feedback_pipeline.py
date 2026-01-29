"""
Unified Feedback Pipeline for Autopack Self-Improvement Loop.

IMP-LOOP-001: Creates a unified FeedbackPipeline that automatically orchestrates
the full telemetry -> memory -> learning -> planning loop.

This module integrates:
- Telemetry collection from phase execution
- Persistent storage of insights to memory service
- Learning rule extraction from patterns
- Context enrichment for next phase planning
- IMP-LOOP-017: Task effectiveness analysis for automatic rule generation

The pipeline ensures that lessons learned from each phase execution are:
1. Captured as telemetry insights
2. Persisted to vector memory for future retrieval
3. Used to inform subsequent phase planning
4. IMP-LOOP-017: Analyzed for effectiveness patterns that generate learning rules
"""

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from autopack.telemetry.meta_metrics import (FeedbackLoopHealth,
                                             MetaMetricsTracker,
                                             PipelineLatencyTracker,
                                             PipelineStage)

if TYPE_CHECKING:
    from autopack.task_generation.task_effectiveness_tracker import \
        TaskEffectivenessTracker

logger = logging.getLogger(__name__)


@dataclass
class PhaseOutcome:
    """Represents the outcome of a phase execution for feedback processing.

    Attributes:
        phase_id: Unique identifier for the phase
        phase_type: Type of phase (e.g., 'build', 'test', 'deploy')
        success: Whether the phase executed successfully
        status: Status message from execution
        execution_time_seconds: Duration of phase execution
        tokens_used: Number of tokens consumed
        error_message: Error message if execution failed
        learnings: List of key learnings from execution
        run_id: Identifier for the current run
        project_id: Project identifier for namespacing
    """

    phase_id: str
    phase_type: Optional[str]
    success: bool
    status: str
    execution_time_seconds: Optional[float] = None
    tokens_used: Optional[int] = None
    error_message: Optional[str] = None
    learnings: Optional[List[str]] = None
    run_id: Optional[str] = None
    project_id: Optional[str] = None


@dataclass
class PhaseContext:
    """Context retrieved from memory for phase planning.

    Attributes:
        relevant_insights: List of relevant telemetry insights
        similar_errors: List of similar past errors
        success_patterns: List of patterns from successful executions
        recommendations: List of actionable recommendations
        formatted_context: Pre-formatted string for prompt injection
    """

    relevant_insights: List[Dict[str, Any]]
    similar_errors: List[Dict[str, Any]]
    success_patterns: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    formatted_context: str


class FeedbackPipeline:
    """Unified pipeline for the telemetry-memory-learning-planning loop.

    IMP-LOOP-001: Orchestrates the full feedback loop:
    1. Captures telemetry from phase execution (process_phase_outcome)
    2. Persists insights to memory service
    3. Extracts learning rules from patterns
    4. Feeds context into next phase planning (get_context_for_phase)

    This class integrates with:
    - MemoryService: For persistent storage and retrieval of insights
    - TelemetryAnalyzer: For analyzing phase outcomes and detecting patterns
    - LearningPipeline: For recording and promoting learning hints

    Example usage:
        ```python
        feedback_pipeline = FeedbackPipeline(
            memory_service=memory_service,
            telemetry_analyzer=telemetry_analyzer,
            run_id="run_001",
            project_id="my_project"
        )

        # After phase execution
        outcome = PhaseOutcome(
            phase_id="phase_1",
            phase_type="build",
            success=True,
            status="completed",
            execution_time_seconds=45.2
        )
        feedback_pipeline.process_phase_outcome(outcome)

        # Before next phase
        context = feedback_pipeline.get_context_for_phase(
            phase_type="test",
            phase_goal="Run unit tests for feature X"
        )
        ```
    """

    def __init__(
        self,
        memory_service: Optional[Any] = None,
        telemetry_analyzer: Optional[Any] = None,
        learning_pipeline: Optional[Any] = None,
        effectiveness_tracker: Optional["TaskEffectivenessTracker"] = None,
        latency_tracker: Optional[PipelineLatencyTracker] = None,
        meta_metrics_tracker: Optional[MetaMetricsTracker] = None,
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        enabled: bool = True,
    ):
        """Initialize the FeedbackPipeline.

        Args:
            memory_service: MemoryService instance for persistent storage
            telemetry_analyzer: TelemetryAnalyzer for pattern detection
            learning_pipeline: LearningPipeline for recording hints
            effectiveness_tracker: IMP-LOOP-017: TaskEffectivenessTracker for
                analyzing patterns and generating learning rules
            latency_tracker: IMP-TELE-001: PipelineLatencyTracker for measuring
                loop cycle time across pipeline stages
            meta_metrics_tracker: IMP-REL-001: MetaMetricsTracker for health
                monitoring and auto-resume of task generation
            run_id: Current run identifier
            project_id: Project identifier for namespacing
            enabled: Whether the pipeline is active (default: True)
        """
        self.memory_service = memory_service
        self.telemetry_analyzer = telemetry_analyzer
        self.learning_pipeline = learning_pipeline
        self._effectiveness_tracker = effectiveness_tracker
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.project_id = project_id or "default"
        self.enabled = enabled

        # IMP-TELE-001: Pipeline latency tracking for loop cycle time measurement
        self._latency_tracker = latency_tracker

        # IMP-REL-001: Meta-metrics tracking for health monitoring and auto-resume
        self._meta_metrics_tracker = meta_metrics_tracker or MetaMetricsTracker()
        self._task_generation_paused = False
        self._health_resume_callbacks: List[Any] = []

        # Track processed outcomes for deduplication
        self._processed_outcomes: set = set()

        # Track accumulated insights for batch processing
        self._pending_insights: List[Dict[str, Any]] = []

        # IMP-AUTO-003: Thread-safe access to pending insights list
        self._insights_lock = threading.Lock()

        # Stats tracking
        self._stats = {
            "outcomes_processed": 0,
            "insights_persisted": 0,
            "context_retrievals": 0,
            "learning_hints_recorded": 0,
            "hints_promoted_to_rules": 0,
            "effectiveness_rules_created": 0,  # IMP-LOOP-017
        }

        # IMP-LOOP-015: Track hint occurrences for automatic promotion to rules
        # When a hint pattern occurs 3+ times, it becomes a rule in memory
        # IMP-LOOP-020: Persist hint occurrences across runs for cross-run learning
        self._hint_occurrences: Dict[str, int] = self._load_hint_occurrences()
        self._hint_promotion_threshold = 3

        # IMP-LOOP-004: Auto-flush configuration for pending insights
        # Flush every 5 minutes (300 seconds) or at 100 insight threshold
        self._auto_flush_interval = 300  # 5 minutes in seconds
        self._insight_threshold = 100
        self._flush_timer: Optional[threading.Timer] = None
        self._auto_flush_enabled = enabled  # Only auto-flush if pipeline is enabled

        # Start auto-flush timer if enabled
        if self._auto_flush_enabled:
            self._start_auto_flush_timer()

        logger.info(
            f"[IMP-LOOP-001] FeedbackPipeline initialized "
            f"(run_id={self.run_id}, project_id={self.project_id}, enabled={self.enabled}, "
            f"auto_flush={'enabled' if self._auto_flush_enabled else 'disabled'})"
        )

    def process_phase_outcome(self, outcome: PhaseOutcome) -> Dict[str, Any]:
        """Process a phase execution outcome through the feedback loop.

        This method:
        1. Validates and normalizes the outcome data
        2. Creates telemetry insights based on success/failure
        3. Persists insights to memory service
        4. Records learning hints for future runs
        5. Updates internal statistics

        Args:
            outcome: PhaseOutcome containing execution results

        Returns:
            Dictionary with processing results:
            - success: Whether processing succeeded
            - insights_created: Number of insights created
            - hints_recorded: Number of learning hints recorded
            - error: Error message if processing failed
        """
        if not self.enabled:
            logger.debug("[IMP-LOOP-001] FeedbackPipeline disabled, skipping outcome processing")
            return {"success": True, "insights_created": 0, "hints_recorded": 0}

        result = {
            "success": False,
            "insights_created": 0,
            "hints_recorded": 0,
            "error": None,
        }

        try:
            # IMP-TELE-001: Record phase completion time for latency tracking
            if self._latency_tracker:
                self._latency_tracker.record_stage(
                    PipelineStage.PHASE_COMPLETE,
                    metadata={"phase_id": outcome.phase_id, "success": outcome.success},
                )

            # Deduplication check
            outcome_key = f"{outcome.phase_id}:{outcome.run_id or self.run_id}"
            if outcome_key in self._processed_outcomes:
                logger.debug(f"[IMP-LOOP-001] Outcome already processed: {outcome_key}")
                result["success"] = True
                return result

            # 1. Create telemetry insight from outcome
            insight = self._create_insight_from_outcome(outcome)
            # IMP-AUTO-003: Thread-safe queuing of pending insights
            with self._insights_lock:
                self._pending_insights.append(insight)
            result["insights_created"] += 1

            # IMP-TELE-001: Record telemetry collection time
            if self._latency_tracker:
                self._latency_tracker.record_stage(
                    PipelineStage.TELEMETRY_COLLECTED,
                    metadata={"insight_count": result["insights_created"]},
                )

            # IMP-LOOP-004: Check if insight threshold reached for immediate flush
            self._check_threshold_flush()

            # 2. Persist to memory service
            if self.memory_service and getattr(self.memory_service, "enabled", False):
                try:
                    self.memory_service.write_task_execution_feedback(
                        run_id=outcome.run_id or self.run_id,
                        phase_id=outcome.phase_id,
                        project_id=outcome.project_id or self.project_id,
                        success=outcome.success,
                        phase_type=outcome.phase_type,
                        execution_time_seconds=outcome.execution_time_seconds,
                        error_message=outcome.error_message,
                        tokens_used=outcome.tokens_used,
                        context_summary=outcome.status,
                        learnings=outcome.learnings,
                    )
                    self._stats["insights_persisted"] += 1
                    logger.debug(
                        f"[IMP-LOOP-001] Persisted execution feedback for {outcome.phase_id}"
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to persist execution feedback: {e}")

                # Also write as telemetry insight for cross-run retrieval
                try:
                    self.memory_service.write_telemetry_insight(
                        insight=insight,
                        project_id=outcome.project_id or self.project_id,
                        validate=True,
                        strict=False,
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to persist telemetry insight: {e}")

                # IMP-TELE-001: Record memory persistence time
                if self._latency_tracker:
                    self._latency_tracker.record_stage(
                        PipelineStage.MEMORY_PERSISTED,
                        metadata={"insights_persisted": self._stats["insights_persisted"]},
                    )

            # 3. Record learning hint if failure, or success pattern if success
            if self.learning_pipeline:
                if not outcome.success:
                    # Record failure hint
                    try:
                        hint_type = self._determine_hint_type(outcome)
                        self.learning_pipeline.record_hint(
                            phase={
                                "phase_id": outcome.phase_id,
                                "phase_type": outcome.phase_type,
                            },
                            hint_type=hint_type,
                            details=outcome.error_message or outcome.status,
                        )
                        result["hints_recorded"] += 1
                        self._stats["learning_hints_recorded"] += 1

                        # IMP-LOOP-015: Track hint occurrences and promote to rules
                        # IMP-LOOP-020: Persist after each increment for cross-run learning
                        hint_key = self._get_hint_promotion_key(hint_type, outcome)
                        self._hint_occurrences[hint_key] = (
                            self._hint_occurrences.get(hint_key, 0) + 1
                        )
                        self._save_hint_occurrences()

                        if self._hint_occurrences[hint_key] >= self._hint_promotion_threshold:
                            self._promote_hint_to_rule(hint_type, hint_key, outcome)
                    except Exception as e:
                        logger.warning(f"[IMP-LOOP-001] Failed to record learning hint: {e}")
                else:
                    # IMP-LOOP-027: Record success pattern for positive reinforcement
                    try:
                        self.learning_pipeline.record_success_pattern(
                            phase={
                                "phase_id": outcome.phase_id,
                                "phase_type": outcome.phase_type,
                                "task_category": getattr(outcome, "task_category", None),
                            },
                            action_taken=outcome.status or "Phase completed successfully",
                            context_summary=self._build_success_context_summary(outcome),
                        )
                        self._stats["success_patterns_recorded"] = (
                            self._stats.get("success_patterns_recorded", 0) + 1
                        )
                        logger.debug(
                            f"[IMP-LOOP-027] Recorded success pattern for {outcome.phase_id}"
                        )
                    except Exception as e:
                        logger.warning(f"[IMP-LOOP-027] Failed to record success pattern: {e}")

            # Mark as processed
            self._processed_outcomes.add(outcome_key)
            self._stats["outcomes_processed"] += 1
            result["success"] = True

            logger.info(
                f"[IMP-LOOP-001] Processed outcome for {outcome.phase_id} "
                f"(success={outcome.success}, insights={result['insights_created']})"
            )

            # IMP-LOOP-017: Check effectiveness patterns and create rules
            self._check_effectiveness_rules()

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[IMP-LOOP-001] Failed to process phase outcome: {e}")

        return result

    def _check_effectiveness_rules(self) -> int:
        """Check if effectiveness patterns warrant new learning rules.

        IMP-LOOP-017: Analyzes task effectiveness patterns and creates
        learning rules when success/failure patterns cross thresholds.

        Returns:
            Number of rules created
        """
        if not self._effectiveness_tracker:
            return 0

        try:
            rules = self._effectiveness_tracker.analyze_effectiveness_patterns()
            if not rules:
                return 0

            rules_created = 0
            for rule in rules:
                # Persist rule to memory as a telemetry insight
                if self.memory_service and getattr(self.memory_service, "enabled", False):
                    try:
                        insight = {
                            "insight_type": "effectiveness_rule",
                            "description": f"{rule.rule_type}: {rule.pattern} - {rule.reason}",
                            "content": rule.reason,
                            "metadata": {
                                "rule_type": rule.rule_type,
                                "pattern": rule.pattern,
                                "confidence": rule.confidence,
                                "sample_size": rule.sample_size,
                                "success_rate": rule.success_rate,
                            },
                            "severity": "medium",
                            "confidence": rule.confidence,
                            "run_id": self.run_id,
                            "suggested_action": self._generate_rule_action_from_effectiveness(
                                rule.rule_type, rule.pattern
                            ),
                            "is_rule": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        self.memory_service.write_telemetry_insight(
                            insight=insight,
                            project_id=self.project_id,
                            validate=True,
                            strict=False,
                        )
                        rules_created += 1
                        self._stats["effectiveness_rules_created"] += 1

                        logger.info(
                            f"[IMP-LOOP-017] Created {rule.rule_type} rule for '{rule.pattern}' "
                            f"(confidence={rule.confidence:.2f}, sample_size={rule.sample_size})"
                        )

                    except Exception as e:
                        logger.warning(f"[IMP-LOOP-017] Failed to persist effectiveness rule: {e}")

            return rules_created

        except Exception as e:
            logger.warning(f"[IMP-LOOP-017] Failed to check effectiveness rules: {e}")
            return 0

    def _generate_rule_action_from_effectiveness(self, rule_type: str, pattern: str) -> str:
        """Generate actionable guidance from effectiveness-based rule.

        Args:
            rule_type: "avoid_pattern" or "prefer_pattern"
            pattern: Task category/type

        Returns:
            Suggested action string for the rule
        """
        if rule_type == "avoid_pattern":
            return (
                f"Avoid or deprioritize tasks in the '{pattern}' category. "
                f"Historical data shows low success rate. Consider breaking down "
                f"tasks into smaller units or investigating root causes."
            )
        elif rule_type == "prefer_pattern":
            return (
                f"Prioritize tasks in the '{pattern}' category. "
                f"Historical data shows high success rate. This pattern is "
                f"effective and should be used when applicable."
            )
        else:
            return f"Review effectiveness patterns for '{pattern}' category."

    def get_context_for_phase(
        self,
        phase_type: str,
        phase_goal: str,
        max_insights: int = 5,
        max_age_hours: float = 72.0,
        include_errors: bool = True,
        include_success_patterns: bool = True,
    ) -> PhaseContext:
        """Retrieve context from memory for phase planning.

        This method queries the memory service to retrieve:
        1. Relevant telemetry insights from similar past phases
        2. Similar error patterns to avoid
        3. Success patterns to replicate
        4. Recommendations from telemetry analysis

        Args:
            phase_type: Type of phase being planned
            phase_goal: Description of what the phase aims to achieve
            max_insights: Maximum number of insights to retrieve (default: 5)
            max_age_hours: Maximum age in hours for insights (default: 72)
            include_errors: Whether to include error patterns (default: True)
            include_success_patterns: Whether to include success patterns (default: True)

        Returns:
            PhaseContext containing retrieved context and formatted string
        """
        self._stats["context_retrievals"] += 1

        if not self.enabled or not self.memory_service:
            logger.debug("[IMP-LOOP-001] FeedbackPipeline disabled or no memory service")
            return PhaseContext(
                relevant_insights=[],
                similar_errors=[],
                success_patterns=[],
                recommendations=[],
                formatted_context="",
            )

        try:
            # Build search query combining phase type and goal
            search_query = f"{phase_type} phase: {phase_goal}"

            # 1. Retrieve relevant telemetry insights
            insights = []
            if getattr(self.memory_service, "enabled", False):
                try:
                    insights = self.memory_service.retrieve_insights(
                        query=search_query,
                        limit=max_insights,
                        project_id=self.project_id,
                        max_age_hours=max_age_hours,
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to retrieve insights: {e}")

            # 2. Retrieve similar errors
            similar_errors = []
            if include_errors and getattr(self.memory_service, "enabled", False):
                try:
                    similar_errors = self.memory_service.search_errors(
                        query=search_query,
                        project_id=self.project_id,
                        limit=3,
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to retrieve errors: {e}")

            # 3. Retrieve success patterns
            success_patterns = []
            if include_success_patterns and getattr(self.memory_service, "enabled", False):
                try:
                    success_patterns = self.memory_service.search_execution_feedback(
                        query=search_query,
                        project_id=self.project_id,
                        success_only=True,
                        phase_type=phase_type,
                        limit=3,
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to retrieve success patterns: {e}")

            # 4. Get recommendations from telemetry analyzer
            recommendations = []
            if self.telemetry_analyzer:
                try:
                    recommendations = self.telemetry_analyzer.get_recommendations_for_phase(
                        phase_type=phase_type,
                        lookback_hours=24,
                    )
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to get recommendations: {e}")

            # Format context for prompt injection
            formatted_context = self._format_context(
                insights=insights,
                errors=similar_errors,
                success_patterns=success_patterns,
                recommendations=recommendations,
                phase_type=phase_type,
            )

            logger.info(
                f"[IMP-LOOP-001] Retrieved context for {phase_type} "
                f"(insights={len(insights)}, errors={len(similar_errors)}, "
                f"patterns={len(success_patterns)}, recommendations={len(recommendations)})"
            )

            return PhaseContext(
                relevant_insights=insights,
                similar_errors=similar_errors,
                success_patterns=success_patterns,
                recommendations=recommendations,
                formatted_context=formatted_context,
            )

        except Exception as e:
            logger.error(f"[IMP-LOOP-001] Failed to get context for phase: {e}")
            return PhaseContext(
                relevant_insights=[],
                similar_errors=[],
                success_patterns=[],
                recommendations=[],
                formatted_context="",
            )

    def flush_pending_insights(self) -> int:
        """Flush accumulated insights to memory service.

        Call this at the end of a run to ensure all insights are persisted.
        IMP-AUTO-003: Thread-safe flush with copy-and-clear pattern.

        Returns:
            Number of insights flushed
        """
        # IMP-AUTO-003: Thread-safe access - copy and clear under lock
        with self._insights_lock:
            if not self._pending_insights:
                return 0
            insights_to_flush = list(self._pending_insights)
            self._pending_insights.clear()

        flushed = 0
        if self.memory_service and getattr(self.memory_service, "enabled", False):
            for insight in insights_to_flush:
                try:
                    self.memory_service.write_telemetry_insight(
                        insight=insight,
                        project_id=self.project_id,
                        validate=True,
                        strict=False,
                    )
                    flushed += 1
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to flush insight: {e}")

        logger.info(f"[IMP-LOOP-001] Flushed {flushed} pending insights")
        return flushed

    def _start_auto_flush_timer(self) -> None:
        """Start the auto-flush timer for periodic insight persistence.

        IMP-LOOP-004: Schedules automatic flush of pending insights every
        5 minutes to ensure telemetry data is persisted without manual
        intervention.
        """
        if self._flush_timer is not None:
            self._flush_timer.cancel()

        self._flush_timer = threading.Timer(self._auto_flush_interval, self._auto_flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()
        logger.debug(
            f"[IMP-LOOP-004] Auto-flush timer started " f"(interval={self._auto_flush_interval}s)"
        )

    def _auto_flush(self) -> None:
        """Perform automatic flush of pending insights.

        IMP-LOOP-004: Called by the timer to flush insights. Also checks
        if insight threshold is reached. Reschedules itself after completion.
        IMP-AUTO-003: Thread-safe access to pending insights count.
        IMP-LOOP-022: Also checks for SLA breaches during auto-flush.
        """
        try:
            # IMP-AUTO-003: Thread-safe access to pending insights count
            with self._insights_lock:
                pending_count = len(self._pending_insights)
            if pending_count > 0:
                logger.info(f"[IMP-LOOP-004] Auto-flushing {pending_count} pending insights")
                flushed = self.flush_pending_insights()
                logger.info(f"[IMP-LOOP-004] Auto-flush complete: {flushed} insights persisted")

            # IMP-LOOP-022: Check for SLA breaches during auto-flush
            self._check_and_alert_sla_breaches()
        except Exception as e:
            logger.warning(f"[IMP-LOOP-004] Auto-flush failed: {e}")
        finally:
            # Reschedule the timer for the next flush cycle
            if self._auto_flush_enabled:
                self._start_auto_flush_timer()

    def _check_threshold_flush(self) -> None:
        """Check if insight threshold is reached and trigger flush if needed.

        IMP-LOOP-004: Called after adding insights to check if the threshold
        of 100 insights is reached, triggering an immediate flush.
        IMP-AUTO-003: Thread-safe access to pending insights count.
        """
        # IMP-AUTO-003: Thread-safe access to pending insights count
        with self._insights_lock:
            should_flush = len(self._pending_insights) >= self._insight_threshold
        if should_flush:
            logger.info(
                f"[IMP-LOOP-004] Insight threshold ({self._insight_threshold}) reached, "
                "triggering flush"
            )
            self.flush_pending_insights()

    def stop_auto_flush(self) -> None:
        """Stop the auto-flush timer.

        IMP-LOOP-004: Call this when shutting down the pipeline to cleanly
        stop the background timer and flush any remaining insights.
        IMP-AUTO-003: Thread-safe access to pending insights.
        """
        self._auto_flush_enabled = False
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
            logger.info("[IMP-LOOP-004] Auto-flush timer stopped")

        # Flush any remaining insights on shutdown
        # IMP-AUTO-003: Thread-safe access to pending insights count
        with self._insights_lock:
            has_pending = bool(self._pending_insights)
            pending_count = len(self._pending_insights)
        if has_pending:
            logger.info(
                f"[IMP-LOOP-004] Flushing {pending_count} " "remaining insights on shutdown"
            )
            self.flush_pending_insights()

    def _check_and_alert_sla_breaches(self) -> List[Dict[str, Any]]:
        """Check for SLA breaches and generate alerts.

        IMP-LOOP-022: Monitors the feedback pipeline for SLA breaches and
        generates alerts when thresholds are exceeded. Alerts are logged
        and optionally persisted as telemetry insights for cross-run analysis.

        Returns:
            List of SLA breach alerts that were detected
        """
        if not self._latency_tracker:
            return []

        try:
            breaches = self._latency_tracker.check_sla_breaches()
            if not breaches:
                return []

            alerts_sent = []
            for breach in breaches:
                # Log the alert with appropriate severity
                if breach.level == "critical":
                    logger.error(f"[IMP-LOOP-022] CRITICAL SLA BREACH: {breach.message}")
                else:
                    logger.warning(f"[IMP-LOOP-022] SLA BREACH WARNING: {breach.message}")

                alert_dict = breach.to_dict()
                alerts_sent.append(alert_dict)

                # Persist breach as telemetry insight for tracking
                if self.memory_service and getattr(self.memory_service, "enabled", False):
                    try:
                        insight = {
                            "insight_type": "sla_breach",
                            "description": breach.message,
                            "content": (
                                f"Pipeline SLA breached: {breach.actual_ms:.0f}ms "
                                f"exceeded {breach.threshold_ms:.0f}ms threshold "
                                f"by {breach.breach_amount_ms:.0f}ms"
                            ),
                            "metadata": {
                                "level": breach.level,
                                "stage_from": breach.stage_from,
                                "stage_to": breach.stage_to,
                                "threshold_ms": breach.threshold_ms,
                                "actual_ms": breach.actual_ms,
                                "breach_amount_ms": breach.breach_amount_ms,
                            },
                            "severity": "critical" if breach.level == "critical" else "high",
                            "confidence": 1.0,
                            "run_id": self.run_id,
                            "suggested_action": self._generate_sla_breach_action(breach),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }

                        self.memory_service.write_telemetry_insight(
                            insight=insight,
                            project_id=self.project_id,
                            validate=True,
                            strict=False,
                        )
                        self._stats["insights_persisted"] += 1
                        logger.debug(
                            f"[IMP-LOOP-022] Persisted SLA breach insight: {breach.message}"
                        )
                    except Exception as e:
                        logger.warning(f"[IMP-LOOP-022] Failed to persist SLA breach insight: {e}")

            if alerts_sent:
                logger.info(
                    f"[IMP-LOOP-022] Detected {len(alerts_sent)} SLA breach(es), "
                    f"alerts generated"
                )

            return alerts_sent

        except Exception as e:
            logger.warning(f"[IMP-LOOP-022] Failed to check SLA breaches: {e}")
            return []

    def _generate_sla_breach_action(self, breach: Any) -> str:
        """Generate suggested action for an SLA breach.

        IMP-LOOP-022: Creates actionable guidance based on the type and
        severity of the SLA breach.

        Args:
            breach: SLABreachAlert object containing breach details

        Returns:
            Suggested action string
        """
        if breach.stage_from and breach.stage_to:
            # Stage-specific breach
            stage_actions = {
                ("phase_complete", "telemetry_collected"): (
                    "Optimize telemetry collection. Check for slow event handlers "
                    "or excessive logging that may be delaying telemetry processing."
                ),
                ("telemetry_collected", "memory_persisted"): (
                    "Investigate memory service latency. Check vector database "
                    "connection, batch sizes, and embedding generation performance."
                ),
                ("memory_persisted", "task_generated"): (
                    "Review task generation logic. Consider caching retrieval results "
                    "or simplifying task prioritization algorithms."
                ),
                ("task_generated", "task_executed"): (
                    "Reduce task execution time. Consider breaking large tasks into "
                    "smaller units or optimizing the task executor."
                ),
            }
            key = (breach.stage_from, breach.stage_to)
            if key in stage_actions:
                return stage_actions[key]

        # End-to-end or unknown breach
        if breach.level == "critical":
            return (
                "URGENT: Pipeline SLA critically breached. Investigate bottlenecks "
                "across all pipeline stages. Consider temporarily reducing task "
                "generation rate or increasing processing resources."
            )
        else:
            return (
                "Pipeline SLA approaching critical threshold. Monitor pipeline "
                "latency trends and consider optimizing the slowest stages."
            )

    def check_sla_status(self) -> Dict[str, Any]:
        """Get current SLA status for the feedback pipeline.

        IMP-LOOP-022: Provides a snapshot of current SLA compliance status,
        including any active breaches and overall health metrics.

        Returns:
            Dictionary with SLA status information:
            - is_healthy: Whether pipeline is within SLA
            - sla_status: Human-readable status string
            - breaches: List of current SLA breaches
            - latency_metrics: Current latency measurements
        """
        if not self._latency_tracker:
            return {
                "is_healthy": True,
                "sla_status": "unknown",
                "breaches": [],
                "latency_metrics": None,
                "message": "No latency tracker configured",
            }

        try:
            breaches = self._latency_tracker.check_sla_breaches()
            return {
                "is_healthy": self._latency_tracker.is_within_sla(),
                "sla_status": self._latency_tracker.get_sla_status(),
                "breaches": [b.to_dict() for b in breaches],
                "latency_metrics": self._latency_tracker.to_dict(),
            }
        except Exception as e:
            logger.warning(f"[IMP-LOOP-022] Failed to get SLA status: {e}")
            return {
                "is_healthy": True,
                "sla_status": "error",
                "breaches": [],
                "latency_metrics": None,
                "error": str(e),
            }

    def persist_learning_hints(self) -> int:
        """Persist accumulated learning hints to memory.

        Call this at the end of a run to ensure learning hints are
        available for future runs.

        Returns:
            Number of hints persisted
        """
        if not self.learning_pipeline:
            return 0

        try:
            return self.learning_pipeline.persist_to_memory(
                memory_service=self.memory_service,
                project_id=self.project_id,
            )
        except Exception as e:
            logger.error(f"[IMP-LOOP-001] Failed to persist learning hints: {e}")
            return 0

    def get_learning_hints_for_context(
        self,
        phase: Dict[str, Any],
        decay_threshold: float = 0.3,
        include_scores: bool = False,
    ) -> List[Any]:
        """Retrieve learning hints with decay filtering for phase context.

        IMP-MEM-004: Retrieves learning hints that have been filtered and
        sorted by decay score. Old hints below the decay threshold are
        excluded to prioritize fresh guidance.

        Args:
            phase: Phase specification dict with phase_id and optional task_category
            decay_threshold: Minimum decay score to include hint (default 0.3)
            include_scores: If True, return (hint_text, decay_score) tuples;
                           if False, return just hint_text strings

        Returns:
            List of hint texts or (hint_text, decay_score) tuples, sorted by
            decay score (highest first)
        """
        if not self.learning_pipeline:
            return []

        try:
            if include_scores:
                return self.learning_pipeline.get_hints_with_decay_scores(
                    phase=phase,
                    decay_threshold=decay_threshold,
                )
            else:
                return self.learning_pipeline.get_hints_for_phase(
                    phase=phase,
                    decay_threshold=decay_threshold,
                )
        except Exception as e:
            logger.warning(f"[IMP-MEM-004] Failed to get learning hints: {e}")
            return []

    def format_hints_with_decay_weights(
        self,
        hints_with_scores: List[tuple],
        max_hints: int = 5,
    ) -> str:
        """Format learning hints with decay-weighted prominence.

        IMP-MEM-004: Formats hints for prompt injection, with visual indicators
        showing hint freshness/reliability based on decay scores.

        Args:
            hints_with_scores: List of (hint_text, decay_score) tuples
            max_hints: Maximum number of hints to include

        Returns:
            Formatted string with hints and freshness indicators
        """
        if not hints_with_scores:
            return ""

        lines = ["### Learning Hints (sorted by relevance)"]
        for hint_text, score in hints_with_scores[:max_hints]:
            # Use visual indicators for freshness
            if score >= 0.8:
                freshness = "[FRESH]"
            elif score >= 0.5:
                freshness = "[RECENT]"
            else:
                freshness = "[AGING]"
            lines.append(f"- {freshness} {hint_text}")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, int]:
        """Get pipeline statistics.

        Returns:
            Dictionary with pipeline statistics
        """
        return dict(self._stats)

    @property
    def latency_tracker(self) -> Optional[PipelineLatencyTracker]:
        """Get the pipeline latency tracker.

        IMP-TELE-001: Returns the latency tracker for external access,
        allowing the autonomous loop to record additional stages.

        Returns:
            PipelineLatencyTracker instance or None if not configured
        """
        return self._latency_tracker

    def set_latency_tracker(self, tracker: PipelineLatencyTracker) -> None:
        """Set the pipeline latency tracker.

        IMP-TELE-001: Allows the autonomous loop to inject a latency tracker
        after pipeline initialization.

        Args:
            tracker: PipelineLatencyTracker instance to use
        """
        self._latency_tracker = tracker
        logger.debug("[IMP-TELE-001] Latency tracker set on FeedbackPipeline")

    def get_latency_metrics(self) -> Optional[Dict[str, Any]]:
        """Get current latency metrics from the tracker.

        IMP-TELE-001: Returns comprehensive latency metrics including
        stage timestamps, latencies, and SLA status.

        Returns:
            Dictionary with latency metrics or None if tracker not configured
        """
        if self._latency_tracker is None:
            return None
        return self._latency_tracker.to_dict()

    def reset_stats(self) -> None:
        """Reset pipeline statistics and hint tracking.

        Note: This does NOT persist the reset hint occurrences to avoid
        accidental data loss. Use clear_hint_occurrences() to also clear
        persisted data.
        """
        self._stats = {
            "outcomes_processed": 0,
            "insights_persisted": 0,
            "context_retrievals": 0,
            "learning_hints_recorded": 0,
            "hints_promoted_to_rules": 0,
        }
        # IMP-LOOP-015: Also reset hint occurrence tracking (in-memory only)
        self._hint_occurrences = {}

    def clear_hint_occurrences(self, persist: bool = True) -> None:
        """Clear hint occurrence tracking data.

        IMP-LOOP-020: Clears both in-memory and optionally persisted hint
        occurrence data. Use with caution as this resets cross-run learning.

        Args:
            persist: If True, also clears the persisted data file
        """
        self._hint_occurrences = {}
        if persist:
            self._save_hint_occurrences()
            logger.info("[IMP-LOOP-020] Cleared and persisted empty hint occurrences")

    # =========================================================================
    # IMP-REL-001: Health Monitoring and Auto-Resume Support
    # =========================================================================

    def check_health_and_update_pause_state(
        self, telemetry_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check feedback loop health and update task generation pause state.

        IMP-REL-001: Monitors the feedback loop health and automatically
        manages task generation pause/resume state. When health degrades
        to ATTENTION_REQUIRED, task generation is paused. When health
        recovers to HEALTHY, task generation is automatically resumed.

        Args:
            telemetry_data: Optional telemetry data for health analysis.
                If not provided, uses empty dict (baseline scores).

        Returns:
            True if task generation should be paused, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Analyze current health state
            health_report = self._meta_metrics_tracker.analyze_feedback_loop_health(
                telemetry_data or {}
            )

            # Check if we should pause (this also triggers transition callbacks)
            should_pause = self._meta_metrics_tracker.should_pause_task_generation(health_report)

            # Update our local pause state
            self._task_generation_paused = should_pause

            if should_pause:
                logger.warning(
                    f"[IMP-REL-001] Task generation paused: health={health_report.overall_status.value}, "
                    f"score={health_report.overall_score:.2f}"
                )
            elif (
                self._meta_metrics_tracker.get_previous_health_status()
                == FeedbackLoopHealth.ATTENTION_REQUIRED
            ):
                # Just recovered - log the resume
                logger.info(
                    f"[IMP-REL-001] Task generation can resume: health={health_report.overall_status.value}, "
                    f"score={health_report.overall_score:.2f}"
                )

            return should_pause

        except Exception as e:
            logger.warning(f"[IMP-REL-001] Failed to check health status: {e}")
            return False

    def register_health_resume_callback(self, callback: Any) -> None:
        """Register a callback to be invoked when health recovers.

        IMP-REL-001: Callbacks are invoked with (old_status, new_status) when
        health transitions from ATTENTION_REQUIRED to HEALTHY, enabling
        external components to resume their operations.

        Args:
            callback: Function that takes (old_status, new_status) as arguments
        """
        self._health_resume_callbacks.append(callback)
        # Also register with the MetaMetricsTracker
        self._meta_metrics_tracker.register_health_transition_callback(callback)
        logger.debug(
            f"[IMP-REL-001] Registered health resume callback "
            f"(total: {len(self._health_resume_callbacks)})"
        )

    def unregister_health_resume_callback(self, callback: Any) -> bool:
        """Unregister a previously registered health resume callback.

        Args:
            callback: The callback function to unregister

        Returns:
            True if callback was found and removed, False otherwise
        """
        try:
            self._health_resume_callbacks.remove(callback)
            self._meta_metrics_tracker.unregister_health_transition_callback(callback)
            return True
        except ValueError:
            return False

    def is_task_generation_paused(self) -> bool:
        """Check if task generation is currently paused due to health issues.

        IMP-REL-001: Returns True if task generation has been paused due
        to feedback loop health being in ATTENTION_REQUIRED state.

        Returns:
            True if task generation is paused, False otherwise
        """
        return self._task_generation_paused

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status summary.

        IMP-REL-001: Returns a summary of the current feedback loop health
        status including whether task generation is paused.

        Returns:
            Dictionary with health status information
        """
        previous_status = self._meta_metrics_tracker.get_previous_health_status()
        return {
            "task_generation_paused": self._task_generation_paused,
            "previous_health_status": previous_status.value if previous_status else None,
            "meta_metrics_paused": self._meta_metrics_tracker.is_task_generation_paused(),
            "registered_callbacks": len(self._health_resume_callbacks),
        }

    @property
    def meta_metrics_tracker(self) -> MetaMetricsTracker:
        """Get the meta-metrics tracker.

        IMP-REL-001: Returns the MetaMetricsTracker for external access,
        allowing integration with autopilot health gating.

        Returns:
            MetaMetricsTracker instance
        """
        return self._meta_metrics_tracker

    def set_meta_metrics_tracker(self, tracker: MetaMetricsTracker) -> None:
        """Set the meta-metrics tracker.

        IMP-REL-001: Allows injection of a MetaMetricsTracker after
        pipeline initialization.

        Args:
            tracker: MetaMetricsTracker instance to use
        """
        # Re-register any existing callbacks with the new tracker
        for callback in self._health_resume_callbacks:
            tracker.register_health_transition_callback(callback)

        self._meta_metrics_tracker = tracker
        logger.debug("[IMP-REL-001] Meta-metrics tracker set on FeedbackPipeline")

    def _create_insight_from_outcome(self, outcome: PhaseOutcome) -> Dict[str, Any]:
        """Create a telemetry insight from a phase outcome.

        Args:
            outcome: PhaseOutcome to convert

        Returns:
            Dictionary in telemetry insight format
        """
        # Determine insight type based on outcome
        if outcome.success:
            insight_type = "unknown"  # Successful outcomes don't trigger specific insight types
            description = f"Phase {outcome.phase_id} completed successfully"
        else:
            insight_type = self._determine_insight_type(outcome)
            description = (
                f"Phase {outcome.phase_id} failed: {outcome.error_message or outcome.status}"
            )

        # Build suggested action
        suggested_action = None
        if not outcome.success:
            suggested_action = self._generate_suggested_action(outcome)

        return {
            "insight_type": insight_type,
            "description": description,
            "phase_id": outcome.phase_id,
            "run_id": outcome.run_id or self.run_id,
            "suggested_action": suggested_action,
            "severity": "high" if not outcome.success else "low",
            "phase_type": outcome.phase_type,
            "success": outcome.success,
            "execution_time_seconds": outcome.execution_time_seconds,
            "tokens_used": outcome.tokens_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _determine_insight_type(self, outcome: PhaseOutcome) -> str:
        """Determine the insight type from an outcome.

        Args:
            outcome: PhaseOutcome to analyze

        Returns:
            Insight type string
        """
        error_msg = (outcome.error_message or outcome.status or "").lower()

        # Check for cost-related issues
        if outcome.tokens_used and outcome.tokens_used > 100000:
            return "cost_sink"

        # Check for failure patterns
        if any(pattern in error_msg for pattern in ["timeout", "retry", "rate limit", "overload"]):
            return "retry_cause"

        # Default to failure mode for unsuccessful outcomes
        if not outcome.success:
            return "failure_mode"

        return "unknown"

    def _determine_hint_type(self, outcome: PhaseOutcome) -> str:
        """Determine the learning hint type from an outcome.

        Args:
            outcome: PhaseOutcome to analyze

        Returns:
            Hint type string for LearningPipeline
        """
        error_msg = (outcome.error_message or outcome.status or "").lower()

        if "audit" in error_msg or "reject" in error_msg:
            return "auditor_reject"
        if "ci" in error_msg or "test" in error_msg or "fail" in error_msg:
            return "ci_fail"
        if "patch" in error_msg or "apply" in error_msg:
            return "patch_apply_error"
        if "infrastructure" in error_msg or "network" in error_msg or "api" in error_msg:
            return "infra_error"
        if "guardrail" in error_msg or "limit" in error_msg:
            return "builder_guardrail"

        return "ci_fail"  # Default to CI fail for unknown failures

    def _build_success_context_summary(self, outcome: PhaseOutcome) -> str:
        """Build a context summary from a successful outcome.

        IMP-LOOP-027: Creates a summary of the context that led to success,
        for use in positive reinforcement learning.

        Args:
            outcome: PhaseOutcome to summarize

        Returns:
            Context summary string
        """
        parts = []

        # Add phase type info
        if outcome.phase_type:
            parts.append(f"Phase type: {outcome.phase_type}")

        # Add execution time if available
        if outcome.execution_time_seconds:
            parts.append(f"Execution time: {outcome.execution_time_seconds:.1f}s")

        # Add tokens used if available
        if outcome.tokens_used:
            parts.append(f"Tokens used: {outcome.tokens_used}")

        # Add learnings if available
        if outcome.learnings:
            learnings_str = "; ".join(outcome.learnings[:3])  # Limit to 3 learnings
            parts.append(f"Key learnings: {learnings_str}")

        # Add status if it provides useful context
        if outcome.status and outcome.status not in ["success", "completed", "done"]:
            parts.append(f"Status: {outcome.status}")

        return " | ".join(parts) if parts else "Phase completed successfully"

    def _generate_suggested_action(self, outcome: PhaseOutcome) -> str:
        """Generate a suggested action from an outcome.

        Args:
            outcome: PhaseOutcome to generate action for

        Returns:
            Suggested action string
        """
        error_msg = (outcome.error_message or outcome.status or "").lower()

        if "timeout" in error_msg:
            return f"Increase timeout for {outcome.phase_type} phases or optimize execution"
        if "token" in error_msg or "budget" in error_msg:
            return f"Reduce context size for {outcome.phase_type} phases"
        if "test" in error_msg or "ci" in error_msg:
            return f"Review test failures in {outcome.phase_type} and fix failing tests"
        if "patch" in error_msg:
            return f"Improve patch generation for {outcome.phase_type}"

        return f"Investigate and fix failure in {outcome.phase_type}: {outcome.phase_id}"

    def _format_context(
        self,
        insights: List[Dict[str, Any]],
        errors: List[Dict[str, Any]],
        success_patterns: List[Dict[str, Any]],
        recommendations: List[Dict[str, Any]],
        phase_type: str,
    ) -> str:
        """Format retrieved context for prompt injection.

        Args:
            insights: List of telemetry insights
            errors: List of similar errors
            success_patterns: List of success patterns
            recommendations: List of recommendations
            phase_type: Type of phase being planned

        Returns:
            Formatted context string for prompt injection
        """
        sections = []

        # Header
        sections.append(f"## Context from Previous Executions ({phase_type})\n")

        # Recommendations section (highest priority)
        if recommendations:
            rec_lines = ["### Recommendations"]
            for rec in recommendations[:3]:
                severity = rec.get("severity", "INFO")
                action = rec.get("action", "review")
                reason = rec.get("reason", "No reason provided")
                rec_lines.append(f"- [{severity}] {action}: {reason}")
            sections.append("\n".join(rec_lines))

        # Insights section
        if insights:
            insight_lines = ["### Relevant Insights"]
            for insight in insights[:5]:
                content = insight.get("content", insight.get("metadata", {}).get("summary", ""))
                if content:
                    insight_lines.append(f"- {content[:200]}")
            sections.append("\n".join(insight_lines))

        # Error patterns section
        if errors:
            error_lines = ["### Similar Past Errors (to avoid)"]
            for err in errors[:3]:
                payload = err.get("payload", {})
                error_type = payload.get("error_type", "unknown")
                error_text = payload.get("error_text", "")[:150]
                error_lines.append(f"- {error_type}: {error_text}")
            sections.append("\n".join(error_lines))

        # Success patterns section
        if success_patterns:
            success_lines = ["### Successful Patterns (to replicate)"]
            for pattern in success_patterns[:3]:
                payload = pattern.get("payload", {})
                context = payload.get("context_summary", "")
                learnings = payload.get("learnings", [])
                if context:
                    success_lines.append(f"- Context: {context[:150]}")
                if learnings:
                    for learning in learnings[:2]:
                        success_lines.append(f"  - Learning: {learning[:100]}")
            sections.append("\n".join(success_lines))

        return "\n\n".join(sections) if sections else ""

    def _get_hint_occurrences_file(self) -> Path:
        """Get path to hint occurrences persistence file.

        IMP-LOOP-020: Returns the path where hint occurrences are persisted
        for cross-run learning. The file is stored in the project's docs directory.

        Returns:
            Path to the hint occurrences JSON file
        """
        from .config import settings

        if self.project_id == "autopack" or self.project_id == "default":
            return Path("docs") / "HINT_OCCURRENCES.json"
        else:
            return (
                Path(settings.autonomous_runs_dir)
                / self.project_id
                / "docs"
                / "HINT_OCCURRENCES.json"
            )

    def _load_hint_occurrences(self) -> Dict[str, int]:
        """Load hint occurrences from persistence layer.

        IMP-LOOP-020: Loads previously persisted hint occurrence counts
        to enable cross-run promotion tracking. If the file doesn't exist
        or is corrupted, returns an empty dict.

        Returns:
            Dictionary mapping hint keys to occurrence counts
        """
        occurrences_file = self._get_hint_occurrences_file()

        if not occurrences_file.exists():
            logger.debug(
                f"[IMP-LOOP-020] No hint occurrences file found at {occurrences_file}, "
                "starting fresh"
            )
            return {}

        try:
            with open(occurrences_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            occurrences = data.get("occurrences", {})
            logger.info(
                f"[IMP-LOOP-020] Loaded {len(occurrences)} hint occurrence entries "
                f"from {occurrences_file}"
            )
            return occurrences

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(
                f"[IMP-LOOP-020] Failed to load hint occurrences from {occurrences_file}: {e}. "
                "Starting fresh."
            )
            return {}

    def _save_hint_occurrences(self) -> bool:
        """Save hint occurrences to persistence layer.

        IMP-LOOP-020: Persists current hint occurrence counts to enable
        cross-run promotion tracking. Creates parent directories if needed.

        Returns:
            True if save succeeded, False otherwise
        """
        occurrences_file = self._get_hint_occurrences_file()

        try:
            occurrences_file.parent.mkdir(parents=True, exist_ok=True)

            with open(occurrences_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "occurrences": self._hint_occurrences,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "run_id": self.run_id,
                        "project_id": self.project_id,
                    },
                    f,
                    indent=2,
                )

            logger.debug(
                f"[IMP-LOOP-020] Saved {len(self._hint_occurrences)} hint occurrence entries "
                f"to {occurrences_file}"
            )
            return True

        except (OSError, TypeError) as e:
            logger.warning(f"[IMP-LOOP-020] Failed to save hint occurrences: {e}")
            return False

    def _get_hint_promotion_key(self, hint_type: str, outcome: PhaseOutcome) -> str:
        """Generate a key for tracking hint occurrences.

        IMP-LOOP-015: Creates a unique key for grouping similar hints.
        Hints with the same type and phase_type are grouped together.

        Args:
            hint_type: The type of learning hint
            outcome: The phase outcome containing context

        Returns:
            A key string for tracking occurrences
        """
        phase_type = outcome.phase_type or "unknown"
        return f"{hint_type}:{phase_type}"

    def _promote_hint_to_rule(self, hint_type: str, hint_key: str, outcome: PhaseOutcome) -> bool:
        """Promote a frequently occurring hint to a persistent rule.

        IMP-LOOP-015: When a hint pattern occurs 3+ times, it becomes a rule
        that is persisted to memory for cross-run learning. Rules are
        higher-priority than hints and are always included in context.

        Args:
            hint_type: The type of learning hint
            hint_key: The promotion key identifying this pattern
            outcome: The phase outcome that triggered promotion

        Returns:
            True if promotion succeeded, False otherwise
        """
        if not self.memory_service or not getattr(self.memory_service, "enabled", False):
            logger.debug("[IMP-LOOP-015] Cannot promote hint - memory service unavailable")
            return False

        try:
            occurrences = self._hint_occurrences.get(hint_key, 0)
            phase_type = outcome.phase_type or "unknown"

            # Create rule from accumulated hint pattern
            rule_description = (
                f"RULE (promoted from {occurrences} occurrences): "
                f"Phases of type '{phase_type}' frequently encounter '{hint_type}' issues. "
                f"Take preventive measures based on past failures."
            )

            suggested_action = self._generate_rule_action(hint_type, phase_type)

            rule_insight = {
                "insight_type": "promoted_rule",
                "description": rule_description,
                "phase_type": phase_type,
                "hint_type": hint_type,
                "occurrences": occurrences,
                "run_id": self.run_id,
                "suggested_action": suggested_action,
                "severity": "high",  # Rules are high priority
                "is_rule": True,  # Flag to identify promoted rules
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.memory_service.write_telemetry_insight(
                insight=rule_insight,
                project_id=self.project_id,
                validate=True,
                strict=False,
            )

            self._stats["hints_promoted_to_rules"] += 1

            logger.info(
                f"[IMP-LOOP-015] Promoted hint to rule: {hint_key} (occurrences={occurrences})"
            )
            return True

        except Exception as e:
            logger.warning(f"[IMP-LOOP-015] Failed to promote hint to rule: {e}")
            return False

    def _generate_rule_action(self, hint_type: str, phase_type: str) -> str:
        """Generate actionable guidance for a promoted rule.

        Args:
            hint_type: The type of hint being promoted
            phase_type: The type of phase affected

        Returns:
            Suggested action string for the rule
        """
        actions = {
            "auditor_reject": (
                f"For {phase_type} phases: Ensure complete implementations, "
                "add proper error handling, and verify code quality before submission."
            ),
            "ci_fail": (
                f"For {phase_type} phases: Run local tests before submitting, "
                "check for common test failures, and ensure all dependencies are included."
            ),
            "patch_apply_error": (
                f"For {phase_type} phases: Use proper diff format, "
                "verify file paths exist, and check for conflicting changes."
            ),
            "infra_error": (
                f"For {phase_type} phases: Add retry logic, "
                "check API connectivity, and handle network failures gracefully."
            ),
            "builder_guardrail": (
                f"For {phase_type} phases: Reduce output size, "
                "break large changes into smaller chunks, and respect token limits."
            ),
        }

        return actions.get(
            hint_type,
            f"For {phase_type} phases: Review past failures of type '{hint_type}' "
            "and implement preventive measures.",
        )

    def get_promoted_rules(
        self,
        phase_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve promoted rules for injection into execution context.

        IMP-LOOP-025: Fetches rules that were promoted from recurring hint patterns
        (via IMP-LOOP-015) to provide high-priority guidance during phase execution.
        Promoted rules have is_rule=True and represent patterns that have occurred
        3+ times across runs.

        Args:
            phase_type: Optional filter to get rules for a specific phase type
            limit: Maximum number of rules to return (default: 5)

        Returns:
            List of rule dictionaries with description, suggested_action, and metadata
        """
        if not self.memory_service or not getattr(self.memory_service, "enabled", False):
            logger.debug(
                "[IMP-LOOP-025] Cannot retrieve promoted rules - memory service unavailable"
            )
            return []

        try:
            # Search for promoted rules across telemetry insight collections
            # Use "promoted_rule" as the query to find rules in semantic search
            query = f"promoted_rule {phase_type or 'all'}"

            # Search telemetry insights and filter for is_rule=True
            all_results = self.memory_service.search_telemetry_insights(
                query=query,
                limit=limit * 3,  # Fetch extra to account for filtering
                project_id=self.project_id,
                max_age_hours=168,  # 7 days - rules should persist longer
            )

            # Filter for actual promoted rules
            rules = []
            for result in all_results:
                metadata = result.get("metadata", {})
                # Check for promoted rule markers
                if not (
                    metadata.get("is_rule") is True
                    or metadata.get("insight_type") == "promoted_rule"
                ):
                    continue

                # Optional: filter by phase_type if specified
                if phase_type and metadata.get("phase_type") != phase_type:
                    continue

                rule = {
                    "description": metadata.get("description", result.get("content", "")),
                    "suggested_action": metadata.get("suggested_action", ""),
                    "phase_type": metadata.get("phase_type", "unknown"),
                    "hint_type": metadata.get("hint_type", "unknown"),
                    "occurrences": metadata.get("occurrences", 0),
                    "confidence": result.get("confidence", 0.8),
                    "timestamp": result.get("timestamp"),
                }
                rules.append(rule)

                if len(rules) >= limit:
                    break

            if rules:
                logger.info(
                    f"[IMP-LOOP-025] Retrieved {len(rules)} promoted rules "
                    f"for phase_type={phase_type or 'all'}"
                )
            else:
                logger.debug(
                    f"[IMP-LOOP-025] No promoted rules found for phase_type={phase_type or 'all'}"
                )

            return rules

        except Exception as e:
            logger.warning(f"[IMP-LOOP-025] Failed to retrieve promoted rules: {e}")
            return []

    def record_circuit_breaker_event(
        self,
        failure_count: int,
        last_failure_reason: str,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Record a circuit breaker open event for root cause analysis.

        IMP-MEM-004: Persists circuit breaker trip events as telemetry insights
        to enable cross-run root cause analysis. When the circuit breaker opens
        due to consecutive failures, this method captures the failure context
        and stores it in memory for later investigation.

        Args:
            failure_count: Number of consecutive failures that triggered the trip
            last_failure_reason: Description of the most recent failure
            timestamp: When the circuit breaker tripped (defaults to now)

        Returns:
            Dictionary with recording results:
            - success: Whether recording succeeded
            - insight_id: ID of the persisted insight (if successful)
            - error: Error message if recording failed
        """
        if not self.enabled:
            logger.debug("[IMP-MEM-004] FeedbackPipeline disabled, skipping circuit breaker event")
            return {"success": True, "insight_id": None}

        result = {"success": False, "insight_id": None, "error": None}

        try:
            event_timestamp = timestamp or datetime.now(timezone.utc)

            # Create insight for the circuit breaker event
            insight = {
                "insight_type": "circuit_breaker_open",
                "description": f"Circuit breaker opened after {failure_count} consecutive failures",
                "content": f"Circuit breaker tripped: {failure_count} failures. Last error: {last_failure_reason}",
                "metadata": {
                    "failure_count": failure_count,
                    "last_failure_reason": last_failure_reason,
                    "timestamp": event_timestamp.isoformat(),
                    "event_type": "circuit_breaker_trip",
                },
                "severity": "critical",
                "confidence": 1.0,
                "run_id": self.run_id,
                "suggested_action": (
                    "Investigate root cause of consecutive failures. "
                    "Check logs for error patterns, verify external service availability, "
                    "and review recent code changes that may have introduced instability."
                ),
                "timestamp": event_timestamp.isoformat(),
            }

            # Persist to memory service
            if self.memory_service and getattr(self.memory_service, "enabled", False):
                try:
                    self.memory_service.write_telemetry_insight(
                        insight=insight,
                        project_id=self.project_id,
                        validate=True,
                        strict=False,
                    )
                    self._stats["insights_persisted"] += 1
                    result["success"] = True
                    logger.info(
                        f"[IMP-MEM-004] Recorded circuit breaker event: "
                        f"{failure_count} failures, reason: {last_failure_reason[:100]}"
                    )
                except Exception as e:
                    logger.warning(f"[IMP-MEM-004] Failed to persist circuit breaker insight: {e}")
                    result["error"] = str(e)
            else:
                # Queue for later flush if memory service unavailable
                # IMP-AUTO-003: Thread-safe queuing of pending insights
                with self._insights_lock:
                    self._pending_insights.append(insight)
                result["success"] = True
                logger.info(
                    f"[IMP-MEM-004] Queued circuit breaker event for later persistence: "
                    f"{failure_count} failures"
                )

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"[IMP-MEM-004] Failed to record circuit breaker event: {e}")

        return result
