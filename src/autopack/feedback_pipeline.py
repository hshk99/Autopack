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

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from autopack.task_generation.task_effectiveness_tracker import (
        TaskEffectivenessTracker,
    )

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
        self._hint_occurrences: Dict[str, int] = {}
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

            # 3. Record learning hint if failure
            if not outcome.success and self.learning_pipeline:
                try:
                    hint_type = self._determine_hint_type(outcome)
                    self.learning_pipeline.record_hint(
                        phase={"phase_id": outcome.phase_id, "phase_type": outcome.phase_type},
                        hint_type=hint_type,
                        details=outcome.error_message or outcome.status,
                    )
                    result["hints_recorded"] += 1
                    self._stats["learning_hints_recorded"] += 1

                    # IMP-LOOP-015: Track hint occurrences and promote to rules
                    hint_key = self._get_hint_promotion_key(hint_type, outcome)
                    self._hint_occurrences[hint_key] = self._hint_occurrences.get(hint_key, 0) + 1

                    if self._hint_occurrences[hint_key] >= self._hint_promotion_threshold:
                        self._promote_hint_to_rule(hint_type, hint_key, outcome)
                except Exception as e:
                    logger.warning(f"[IMP-LOOP-001] Failed to record learning hint: {e}")

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
        """
        try:
            # IMP-AUTO-003: Thread-safe access to pending insights count
            with self._insights_lock:
                pending_count = len(self._pending_insights)
            if pending_count > 0:
                logger.info(f"[IMP-LOOP-004] Auto-flushing {pending_count} pending insights")
                flushed = self.flush_pending_insights()
                logger.info(f"[IMP-LOOP-004] Auto-flush complete: {flushed} insights persisted")
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

    def get_stats(self) -> Dict[str, int]:
        """Get pipeline statistics.

        Returns:
            Dictionary with pipeline statistics
        """
        return dict(self._stats)

    def reset_stats(self) -> None:
        """Reset pipeline statistics and hint tracking."""
        self._stats = {
            "outcomes_processed": 0,
            "insights_persisted": 0,
            "context_retrievals": 0,
            "learning_hints_recorded": 0,
            "hints_promoted_to_rules": 0,
        }
        # IMP-LOOP-015: Also reset hint occurrence tracking
        self._hint_occurrences = {}

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
