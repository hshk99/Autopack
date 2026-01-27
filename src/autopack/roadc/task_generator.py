"""ROAD-C: Autonomous Task Generator - converts insights to tasks."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..memory.memory_service import (DEFAULT_MEMORY_FRESHNESS_HOURS,
                                     MemoryService)
from ..roadi import RegressionProtector
from ..roadi.regression_protector import RiskAssessment
from ..telemetry.analyzer import RankedIssue, TelemetryAnalyzer
from ..telemetry.causal_analysis import CausalAnalyzer
from .discovery_context_merger import DiscoveryContextMerger

logger = logging.getLogger(__name__)


def _emit_task_generation_event(
    success: bool,
    insights_processed: int = 0,
    patterns_detected: int = 0,
    tasks_generated: int = 0,
    tasks_persisted: int = 0,
    generation_time_ms: float = 0.0,
    run_id: Optional[str] = None,
    telemetry_source: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_tasks: Optional[int] = None,
    error_message: Optional[str] = None,
    error_type: Optional[str] = None,
) -> None:
    """Emit a task generation telemetry event (IMP-LOOP-004).

    Records task generation metrics to the database for monitoring
    and quality analysis of the self-improvement loop.

    Args:
        success: Whether the generation completed successfully
        insights_processed: Number of insights processed
        patterns_detected: Number of patterns detected
        tasks_generated: Number of tasks generated
        tasks_persisted: Number of tasks persisted to database
        generation_time_ms: Duration in milliseconds
        run_id: Optional run ID that triggered generation
        telemetry_source: "direct" or "memory"
        min_confidence: Confidence threshold used
        max_tasks: Max tasks limit used
        error_message: Error details if failed
        error_type: Exception type if failed
    """
    try:
        from ..database import SessionLocal
        from ..models import TaskGenerationEvent

        session = SessionLocal()
        try:
            event = TaskGenerationEvent(
                run_id=run_id,
                success=success,
                insights_processed=insights_processed,
                patterns_detected=patterns_detected,
                tasks_generated=tasks_generated,
                tasks_persisted=tasks_persisted,
                generation_time_ms=generation_time_ms,
                telemetry_source=telemetry_source,
                min_confidence=min_confidence,
                max_tasks=max_tasks,
                error_message=error_message,
                error_type=error_type,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(event)
            session.commit()
            logger.debug(
                f"[IMP-LOOP-004] Emitted task generation event: "
                f"success={success}, tasks={tasks_generated}, patterns={patterns_detected}"
            )
        except Exception as e:
            session.rollback()
            logger.warning(f"[IMP-LOOP-004] Failed to emit task generation event: {e}")
        finally:
            session.close()
    except ImportError:
        # Database not available - skip telemetry
        logger.debug("[IMP-LOOP-004] Database not available, skipping telemetry event")


# Stale task threshold: tasks in_progress for longer than this are considered stale (IMP-REL-003)
STALE_TASK_THRESHOLD_HOURS = 24


@dataclass
class TaskCompletionEvent:
    """Event emitted when a ROAD-C task completes (IMP-LOOP-012).

    Captures task execution outcomes for effectiveness tracking. This enables
    measurement of whether improvement tasks achieve their intended targets.
    """

    task_id: str
    success: bool
    target_metric: Optional[float] = None  # Expected improvement target
    actual_metric: Optional[float] = None  # Actual measured result
    target_achieved: Optional[bool] = None  # Did we hit the target?
    task_type: Optional[str] = None  # cost_sink, failure_mode, retry_cause
    task_priority: Optional[str] = None  # critical, high, medium, low
    execution_duration_ms: Optional[float] = None  # How long the task took
    run_id: Optional[str] = None  # Run that executed the task
    failure_reason: Optional[str] = None  # Reason if failed
    retry_count: int = 0  # Retries needed


def emit_task_completion(event: TaskCompletionEvent) -> None:
    """Emit a task completion telemetry event (IMP-LOOP-012).

    Records task execution outcomes to the database for measuring
    task effectiveness and improvement target achievement.

    Args:
        event: TaskCompletionEvent with execution outcome details
    """
    try:
        from ..database import SessionLocal
        from ..models import TaskCompletionEvent as TaskCompletionEventModel

        session = SessionLocal()
        try:
            # Calculate improvement percentage if we have both target and actual
            improvement_percentage = None
            if event.target_metric is not None and event.actual_metric is not None:
                if event.target_metric != 0:
                    improvement_percentage = (
                        (event.actual_metric - event.target_metric) / abs(event.target_metric)
                    ) * 100

            db_event = TaskCompletionEventModel(
                task_id=event.task_id,
                run_id=event.run_id,
                success=event.success,
                failure_reason=event.failure_reason,
                target_metric=event.target_metric,
                actual_metric=event.actual_metric,
                target_achieved=event.target_achieved,
                improvement_percentage=improvement_percentage,
                task_type=event.task_type,
                task_priority=event.task_priority,
                execution_duration_ms=event.execution_duration_ms,
                retry_count=event.retry_count,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(db_event)
            session.commit()
            logger.debug(
                f"[IMP-LOOP-012] Emitted task completion event: "
                f"task_id={event.task_id}, success={event.success}, "
                f"target_achieved={event.target_achieved}"
            )
        except Exception as e:
            session.rollback()
            logger.warning(f"[IMP-LOOP-012] Failed to emit task completion event: {e}")
        finally:
            session.close()
    except ImportError:
        # Database not available - skip telemetry
        logger.debug("[IMP-LOOP-012] Database not available, skipping task completion event")


@dataclass
class GeneratedTask:
    """A task generated from telemetry insights."""

    task_id: str
    title: str
    description: str
    priority: str  # critical, high, medium, low
    source_insights: List[str]
    suggested_files: List[str]
    estimated_effort: str  # S, M, L, XL
    created_at: datetime
    run_id: Optional[str] = None  # Run that generated this task
    status: str = "pending"  # pending, in_progress, completed, skipped, failed
    # IMP-LOOP-005: Retry tracking fields
    retry_count: int = 0
    max_retries: int = 3
    failure_runs: List[str] = field(default_factory=list)
    # IMP-LOOP-018: Risk assessment fields
    requires_approval: bool = False  # True for medium-risk tasks needing approval gate
    risk_severity: Optional[str] = None  # low, medium, high, critical


@dataclass
class TaskGenerationResult:
    """Result of task generation run."""

    tasks_generated: List[GeneratedTask]
    insights_processed: int
    patterns_detected: int
    generation_time_ms: float


class AutonomousTaskGenerator:
    """ROAD-C: Converts telemetry insights into improvement tasks."""

    def __init__(
        self,
        memory_service: Optional[MemoryService] = None,
        regression_protector: Optional[RegressionProtector] = None,
        causal_analyzer: Optional[CausalAnalyzer] = None,
        db_session: Optional[Session] = None,
    ):
        self._memory = memory_service or MemoryService()
        self._regression = regression_protector or RegressionProtector()
        # IMP-FBK-005: CausalAnalyzer for risk-based task prioritization
        self._causal_analyzer = causal_analyzer or CausalAnalyzer()
        # IMP-ARCH-017: Reconnect TelemetryAnalyzer when db_session is available.
        # This enables automatic aggregation of telemetry data (cost sinks, failure
        # modes, retry patterns) to feed directly into task generation.
        self._db_session = db_session
        self._telemetry_analyzer: Optional[TelemetryAnalyzer] = None
        if db_session is not None:
            self._telemetry_analyzer = TelemetryAnalyzer(db_session, memory_service=self._memory)
            logger.debug("[IMP-ARCH-017] TelemetryAnalyzer initialized for task generation")
        logger.debug("[IMP-FBK-005] CausalAnalyzer initialized for task prioritization")

    def _convert_telemetry_to_insights(
        self, telemetry_data: Dict[str, List[RankedIssue]]
    ) -> List[Dict[str, Any]]:
        """Convert TelemetryAnalyzer output to insight format for pattern detection.

        Implements IMP-FEAT-001: Wires TelemetryAnalyzer.aggregate_telemetry() output
        to the task generation pipeline by converting RankedIssue objects to the
        insight dict format expected by _detect_patterns().

        Args:
            telemetry_data: Output from TelemetryAnalyzer.aggregate_telemetry() containing:
                - top_cost_sinks: List[RankedIssue]
                - top_failure_modes: List[RankedIssue]
                - top_retry_causes: List[RankedIssue]
                - phase_type_stats: Dict (ignored for task generation)

        Returns:
            List of insight dicts compatible with _detect_patterns()
        """
        insights = []

        # Convert cost sinks
        for issue in telemetry_data.get("top_cost_sinks", []):
            insights.append(
                {
                    "id": f"cost_sink_{issue.phase_id}_{issue.rank}",
                    "issue_type": "cost_sink",
                    "severity": "high" if issue.metric_value > 50000 else "medium",
                    "content": (
                        f"Phase {issue.phase_id} ({issue.phase_type}) consuming "
                        f"{issue.metric_value:,.0f} tokens. "
                        f"Avg: {issue.details.get('avg_tokens', 0):,.0f} tokens, "
                        f"Count: {issue.details.get('count', 0)}"
                    ),
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "metric_value": issue.metric_value,
                    "rank": issue.rank,
                    "details": issue.details,
                }
            )

        # Convert failure modes
        for issue in telemetry_data.get("top_failure_modes", []):
            insights.append(
                {
                    "id": f"failure_{issue.phase_id}_{issue.rank}",
                    "issue_type": "failure_mode",
                    "severity": "high" if issue.metric_value > 5 else "medium",
                    "content": (
                        f"Phase {issue.phase_id} ({issue.phase_type}) failed "
                        f"{int(issue.metric_value)} times. "
                        f"Outcome: {issue.details.get('outcome', 'unknown')}, "
                        f"Reason: {issue.details.get('stop_reason', 'unknown')}"
                    ),
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "metric_value": issue.metric_value,
                    "rank": issue.rank,
                    "details": issue.details,
                }
            )

        # Convert retry causes
        for issue in telemetry_data.get("top_retry_causes", []):
            insights.append(
                {
                    "id": f"retry_{issue.phase_id}_{issue.rank}",
                    "issue_type": "retry_cause",
                    "severity": "high" if issue.metric_value > 5 else "medium",
                    "content": (
                        f"Phase {issue.phase_id} ({issue.phase_type}) required "
                        f"{int(issue.metric_value)} retries. "
                        f"Reason: {issue.details.get('stop_reason', 'unknown')}, "
                        f"Success count: {issue.details.get('success_count', 0)}"
                    ),
                    "phase_id": issue.phase_id,
                    "phase_type": issue.phase_type,
                    "metric_value": issue.metric_value,
                    "rank": issue.rank,
                    "details": issue.details,
                }
            )

        logger.debug(
            f"[IMP-FEAT-001] Converted telemetry to {len(insights)} insights: "
            f"{len(telemetry_data.get('top_cost_sinks', []))} cost sinks, "
            f"{len(telemetry_data.get('top_failure_modes', []))} failure modes, "
            f"{len(telemetry_data.get('top_retry_causes', []))} retry causes"
        )

        return insights

    def generate_tasks(
        self,
        max_tasks: int = 10,
        min_confidence: float = 0.7,
        telemetry_insights: Optional[Dict[str, List[RankedIssue]]] = None,
        run_id: Optional[str] = None,
        max_age_hours: Optional[float] = None,
    ) -> TaskGenerationResult:
        """Generate improvement tasks from recent telemetry insights.

        Args:
            max_tasks: Maximum number of tasks to generate
            min_confidence: Minimum confidence threshold for pattern detection
            telemetry_insights: Optional telemetry data from TelemetryAnalyzer.aggregate_telemetry().
                               If provided, uses this directly instead of querying MemoryService.
                               This enables the ROAD-C self-improvement pipeline (IMP-FEAT-001).
            run_id: Optional run ID for telemetry tracking (IMP-LOOP-004)
            max_age_hours: Maximum age in hours for memory insights to be considered fresh.
                          Only applies when retrieving from memory (not direct telemetry).
                          Defaults to DEFAULT_MEMORY_FRESHNESS_HOURS (72 hours).
                          IMP-LOOP-003: Ensures only recent data is used for task generation.

        Returns:
            TaskGenerationResult containing generated tasks and statistics
        """
        start_time = datetime.now()
        telemetry_source = None
        insights: List[dict] = []
        patterns: List[dict] = []
        tasks: List[GeneratedTask] = []

        try:
            # IMP-FEAT-001: Use telemetry insights directly if provided
            if telemetry_insights:
                insights = self._convert_telemetry_to_insights(telemetry_insights)
                telemetry_source = "direct"
                logger.info(
                    f"[IMP-FEAT-001] Using {len(insights)} telemetry insights for task generation"
                )
            # IMP-ARCH-017: Auto-aggregate telemetry when db_session is available
            elif self._telemetry_analyzer is not None:
                logger.info(
                    "[IMP-ARCH-017] Calling TelemetryAnalyzer.aggregate_telemetry() for task generation"
                )
                aggregated = self._telemetry_analyzer.aggregate_telemetry(window_days=7)
                insights = self._convert_telemetry_to_insights(aggregated)
                telemetry_source = "analyzer"
                logger.info(
                    f"[IMP-ARCH-017] Aggregated {len(insights)} insights from telemetry: "
                    f"{len(aggregated.get('top_cost_sinks', []))} cost sinks, "
                    f"{len(aggregated.get('top_failure_modes', []))} failure modes, "
                    f"{len(aggregated.get('top_retry_causes', []))} retry causes"
                )
            else:
                # Fallback: Retrieve recent high-signal insights from memory
                # IMP-ARCH-016: Removed namespace parameter - retrieve_insights now queries
                # across run_summaries, errors_ci, doctor_hints collections
                # IMP-LOOP-003: Apply freshness check to filter stale insights
                effective_max_age = (
                    max_age_hours if max_age_hours is not None else DEFAULT_MEMORY_FRESHNESS_HOURS
                )
                insights = self._memory.retrieve_insights(
                    query="error failure bottleneck improvement opportunity",
                    limit=100,
                    max_age_hours=effective_max_age,
                )
                telemetry_source = "memory"
                logger.debug(
                    f"[IMP-LOOP-003] Retrieved {len(insights)} fresh insights "
                    f"(max_age={effective_max_age}h)"
                )

            # Detect patterns across insights
            patterns = self._detect_patterns(insights)

            # IMP-LOOP-018: Filter patterns with risk assessment for regression gating
            # This blocks high/critical risk patterns and flags medium risk for approval
            original_pattern_count = len(patterns)
            patterns, risk_assessments = self._regression.filter_patterns_with_risk_assessment(
                patterns
            )

            # Log risk gating summary
            if len(patterns) < original_pattern_count:
                blocked_count = original_pattern_count - len(patterns)
                high_risk_blocked = sum(
                    1 for r in risk_assessments.values() if r.blocking_recommended
                )
                logger.info(
                    f"[IMP-LOOP-018] Regression risk gating: blocked {blocked_count} patterns "
                    f"(high/critical risk: {high_risk_blocked}), kept {len(patterns)}"
                )

                # Emit telemetry for risk gating decisions
                self._emit_risk_gating_metrics(risk_assessments)

            # IMP-FBK-005: Apply causal analysis adjustments to pattern priorities
            # This adjusts severity/confidence based on historical causal relationships
            patterns = self._apply_causal_adjustments(patterns)

            # Re-sort patterns after causal adjustments (severity may have changed)
            patterns.sort(key=lambda p: (p["severity"], p["occurrences"]), reverse=True)

            # Generate tasks from patterns
            for pattern in patterns[:max_tasks]:
                if pattern["confidence"] >= min_confidence:
                    # IMP-LOOP-018: Include risk assessment in task generation
                    risk_assessment = pattern.get("_risk_assessment")
                    requires_approval = pattern.get("_requires_approval", False)

                    task = self._pattern_to_task(pattern)

                    # Mark tasks that require approval gate (medium risk)
                    if requires_approval and risk_assessment:
                        task.requires_approval = True
                        task.risk_severity = risk_assessment.severity.value
                        logger.info(
                            f"[IMP-LOOP-018] Task {task.task_id} flagged for approval gate "
                            f"(risk: {risk_assessment.severity.value})"
                        )

                    tasks.append(task)

                    # Add regression protection for each task
                    self._ensure_regression_protection(task)

            generation_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            # IMP-LOOP-004: Emit success metrics
            _emit_task_generation_event(
                success=True,
                insights_processed=len(insights),
                patterns_detected=len(patterns),
                tasks_generated=len(tasks),
                tasks_persisted=0,  # Updated by persist_tasks if called
                generation_time_ms=generation_time_ms,
                run_id=run_id,
                telemetry_source=telemetry_source,
                min_confidence=min_confidence,
                max_tasks=max_tasks,
            )

            return TaskGenerationResult(
                tasks_generated=tasks,
                insights_processed=len(insights),
                patterns_detected=len(patterns),
                generation_time_ms=generation_time_ms,
            )

        except Exception as e:
            generation_time_ms = (datetime.now() - start_time).total_seconds() * 1000

            # IMP-LOOP-004: Emit failure metrics
            _emit_task_generation_event(
                success=False,
                insights_processed=len(insights),
                patterns_detected=len(patterns),
                tasks_generated=len(tasks),
                tasks_persisted=0,
                generation_time_ms=generation_time_ms,
                run_id=run_id,
                telemetry_source=telemetry_source,
                min_confidence=min_confidence,
                max_tasks=max_tasks,
                error_message=str(e),
                error_type=type(e).__name__,
            )
            logger.error(f"[IMP-LOOP-004] Task generation failed: {e}")
            raise

    def _detect_patterns(self, insights: List[dict]) -> List[dict]:
        """Detect actionable patterns from insights.

        IMP-ARCH-017: Integrates TelemetryAnalyzer results into pattern scoring.
        Patterns matching known cost sinks, failure modes, or retry causes receive
        boosted confidence and severity scores.

        IMP-DISC-001: Integrates discovery context from external sources (GitHub,
        Reddit, Web). Patterns with matching discovered solutions receive additional
        confidence and severity boosts.
        """
        patterns = []

        # IMP-DISC-001: Fetch discovery context for pattern matching
        discovery_keywords = self._get_discovery_keywords(insights)

        # Group by error type
        error_groups = {}
        for insight in insights:
            error_type = insight.get("issue_type", "unknown")
            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append(insight)

        # Create patterns from groups
        for error_type, group in error_groups.items():
            if len(group) >= 2:  # At least 2 occurrences
                base_confidence = min(1.0, len(group) / 5)
                base_severity = self._calculate_severity(group)

                # IMP-ARCH-017: Boost scores based on telemetry issue type
                # Cost sinks and failure modes are higher priority
                confidence_boost = 0.0
                severity_boost = 0

                if error_type == "cost_sink":
                    # High-cost phases are critical to optimize
                    confidence_boost = 0.15
                    severity_boost = 2
                    # Extra boost for very high token consumers
                    max_tokens = max((i.get("metric_value", 0) for i in group), default=0)
                    if max_tokens > 100000:
                        severity_boost += 1
                elif error_type == "failure_mode":
                    # Failures directly impact reliability
                    confidence_boost = 0.2
                    severity_boost = 3
                elif error_type == "retry_cause":
                    # Retries indicate flakiness needing attention
                    confidence_boost = 0.1
                    severity_boost = 1

                # IMP-DISC-001: Boost patterns with matching discovered solutions
                discovery_boost = self._calculate_discovery_boost(group, discovery_keywords)
                confidence_boost += discovery_boost["confidence"]
                severity_boost += discovery_boost["severity"]

                patterns.append(
                    {
                        "type": error_type,
                        "occurrences": len(group),
                        "confidence": min(1.0, base_confidence + confidence_boost),
                        "examples": group[:3],
                        "severity": min(10, base_severity + severity_boost),
                        "telemetry_boosted": severity_boost > 0,  # Track if boosted
                        "discovery_boosted": discovery_boost["severity"] > 0,  # IMP-DISC-001
                    }
                )

        # Sort by severity and occurrences
        patterns.sort(key=lambda p: (p["severity"], p["occurrences"]), reverse=True)

        return patterns

    def _get_discovery_keywords(self, insights: List[dict]) -> set:
        """Extract keywords from discovery context for pattern matching (IMP-DISC-001).

        Args:
            insights: List of insight dictionaries

        Returns:
            Set of keywords from discovered solutions
        """
        keywords = set()

        try:
            # Build query from insight content
            query_parts = []
            for insight in insights[:5]:  # Limit to first 5 for query building
                content = insight.get("content", "")
                if content:
                    query_parts.append(content[:100])

            if not query_parts:
                return keywords

            query = " ".join(query_parts)

            # Fetch discovery insights
            merger = DiscoveryContextMerger()
            discovery_insights = merger.merge_sources(query=query, limit=5)

            # Extract keywords from discoveries
            for discovery in discovery_insights:
                words = discovery.content.lower().split()
                keywords.update(w for w in words if len(w) > 3)

            logger.debug(
                f"[IMP-DISC-001] Extracted {len(keywords)} discovery keywords "
                f"from {len(discovery_insights)} insights"
            )

        except Exception as e:
            logger.warning(f"[IMP-DISC-001] Failed to get discovery keywords: {e}")

        return keywords

    def _calculate_discovery_boost(self, group: List[dict], discovery_keywords: set) -> dict:
        """Calculate boost based on discovered solutions matching pattern (IMP-DISC-001).

        Args:
            group: Group of insights forming a pattern
            discovery_keywords: Keywords from discovered solutions

        Returns:
            Dict with 'confidence' and 'severity' boost values
        """
        if not discovery_keywords:
            return {"confidence": 0.0, "severity": 0}

        # Count keyword matches in group
        matches = 0
        for insight in group:
            content = insight.get("content", "").lower()
            for keyword in discovery_keywords:
                if keyword in content:
                    matches += 1
                    break  # One match per insight is enough

        # Calculate boost based on match ratio
        match_ratio = matches / len(group) if group else 0

        if match_ratio >= 0.5:
            # Strong match: discovered solutions highly relevant
            return {"confidence": 0.15, "severity": 2}
        elif match_ratio >= 0.25:
            # Moderate match: some discovered solutions apply
            return {"confidence": 0.1, "severity": 1}
        else:
            # Weak or no match
            return {"confidence": 0.0, "severity": 0}

    def _apply_causal_adjustments(self, patterns: List[dict]) -> List[dict]:
        """Apply causal analysis adjustments to pattern priorities (IMP-FBK-005).

        Queries CausalAnalyzer for historical causal relationships and adjusts
        pattern severity/confidence based on risk assessment. Tasks that have
        historically caused downstream failures get lower priority; safe tasks
        get higher priority.

        Args:
            patterns: List of pattern dicts from _detect_patterns()

        Returns:
            List of patterns with adjusted severity/confidence based on causal risk
        """
        if not patterns:
            return patterns

        adjusted_patterns = []
        adjustments_made = 0

        for pattern in patterns:
            pattern_type = pattern.get("type", "unknown")

            try:
                # Query causal history for this pattern type
                causal_history = self._causal_analyzer.get_pattern_causal_history(
                    pattern_type=pattern_type,
                    lookback_days=30,
                )

                # Apply adjustments based on causal risk
                adjusted = self._causal_analyzer.adjust_priority_for_causal_risk(
                    pattern=pattern,
                    causal_history=causal_history,
                )

                # Track if adjustment was made
                if adjusted.get("severity") != pattern.get("severity"):
                    adjustments_made += 1
                    logger.debug(
                        f"[IMP-FBK-005] Adjusted {pattern_type} severity: "
                        f"{pattern.get('severity')} -> {adjusted.get('severity')} "
                        f"(risk: {causal_history.get('recommendation')})"
                    )

                adjusted_patterns.append(adjusted)

            except Exception as e:
                # If causal analysis fails, keep original pattern
                logger.warning(f"[IMP-FBK-005] Causal adjustment failed for {pattern_type}: {e}")
                adjusted_patterns.append(pattern)

        if adjustments_made > 0:
            logger.info(
                f"[IMP-FBK-005] Applied causal adjustments to {adjustments_made}/{len(patterns)} patterns"
            )

        return adjusted_patterns

    def _emit_risk_gating_metrics(self, risk_assessments: Dict[str, "RiskAssessment"]) -> None:
        """Emit telemetry for risk gating decisions (IMP-LOOP-018).

        Tracks regression rate trends and risk distribution for monitoring
        the effectiveness of the risk gating system.

        Args:
            risk_assessments: Dict mapping pattern type to RiskAssessment
        """
        try:
            from ..database import SessionLocal
            from ..models import RiskGatingEvent

            # Calculate risk distribution
            severity_counts = {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            }
            total_blocked = 0
            avg_historical_rate = 0.0
            historical_rates = []

            for risk in risk_assessments.values():
                severity_counts[risk.severity.value] += 1
                if risk.blocking_recommended:
                    total_blocked += 1
                if risk.historical_regression_rate > 0:
                    historical_rates.append(risk.historical_regression_rate)

            if historical_rates:
                avg_historical_rate = sum(historical_rates) / len(historical_rates)

            session = SessionLocal()
            try:
                event = RiskGatingEvent(
                    total_patterns=len(risk_assessments),
                    blocked_count=total_blocked,
                    low_risk_count=severity_counts["low"],
                    medium_risk_count=severity_counts["medium"],
                    high_risk_count=severity_counts["high"],
                    critical_risk_count=severity_counts["critical"],
                    avg_historical_regression_rate=avg_historical_rate,
                    timestamp=datetime.now(),
                )
                session.add(event)
                session.commit()
                logger.debug(
                    f"[IMP-LOOP-018] Emitted risk gating metrics: "
                    f"total={len(risk_assessments)}, blocked={total_blocked}, "
                    f"avg_historical_rate={avg_historical_rate:.2%}"
                )
            except Exception as e:
                session.rollback()
                logger.warning(f"[IMP-LOOP-018] Failed to emit risk gating metrics: {e}")
            finally:
                session.close()
        except ImportError:
            # Database or model not available - skip telemetry
            logger.debug("[IMP-LOOP-018] RiskGatingEvent model not available, skipping metrics")
        except Exception as e:
            logger.warning(f"[IMP-LOOP-018] Error in risk gating metrics: {e}")

    def _pattern_to_task(self, pattern: dict) -> GeneratedTask:
        """Convert a pattern into an improvement task."""
        import uuid

        # Generate task details from pattern
        title = f"Fix recurring {pattern['type']} issues"
        description = self._generate_description(pattern)

        return GeneratedTask(
            task_id=f"TASK-{uuid.uuid4().hex[:8].upper()}",
            title=title,
            description=description,
            priority=self._severity_to_priority(pattern["severity"]),
            source_insights=[e.get("id", "") for e in pattern["examples"]],
            suggested_files=self._suggest_files(pattern),
            estimated_effort=self._estimate_effort(pattern),
            created_at=datetime.now(),
        )

    def _generate_description(self, pattern: dict) -> str:
        """Generate task description from pattern."""
        examples = pattern["examples"]
        return f"""## Problem
Detected {pattern["occurrences"]} occurrences of {pattern["type"]} issues.

## Examples
{chr(10).join(f"- {e.get('content', '')[:100]}" for e in examples[:3])}

## Suggested Fix
Analyze the pattern and implement a fix to prevent recurrence.
"""

    def _calculate_severity(self, group: List[dict]) -> int:
        """Calculate severity score (0-10) for a pattern group."""
        # Count high-severity insights
        high_count = sum(1 for i in group if i.get("severity") == "high")
        return min(10, len(group) + high_count * 2)

    def _severity_to_priority(self, severity: int) -> str:
        """Convert severity score to priority."""
        if severity >= 8:
            return "critical"
        elif severity >= 6:
            return "high"
        elif severity >= 4:
            return "medium"
        return "low"

    def _suggest_files(self, pattern: dict) -> List[str]:
        """Suggest files to modify based on pattern."""
        # Extract file paths from examples
        files = set()
        for example in pattern["examples"]:
            if "file_path" in example:
                files.add(example["file_path"])
        return list(files)[:5]

    def _estimate_effort(self, pattern: dict) -> str:
        """Estimate effort for fixing pattern."""
        occurrences = pattern["occurrences"]
        if occurrences > 10:
            return "XL"
        elif occurrences > 5:
            return "L"
        elif occurrences > 2:
            return "M"
        return "S"

    def _ensure_regression_protection(self, task: GeneratedTask) -> None:
        """Ensure regression protection exists for task's issue pattern.

        Args:
            task: The generated task to add protection for.
        """
        # Check if already protected
        result = self._regression.check_protection(task.title)

        if not result.is_protected:
            # Add protection
            test = self._regression.add_protection(
                task_id=task.task_id,
                issue_pattern=task.title,
            )
            logger.info(f"Added regression protection: {test.test_id} for {task.title}")

    # =========================================================================
    # Task Persistence (IMP-ARCH-011)
    # =========================================================================

    def persist_tasks(self, tasks: List[GeneratedTask], run_id: Optional[str] = None) -> int:
        """Persist generated tasks to database (IMP-ARCH-011).

        Args:
            tasks: List of GeneratedTask dataclass instances
            run_id: Optional run ID to associate with tasks

        Returns:
            Number of tasks persisted
        """
        from ..database import SessionLocal
        from ..models import GeneratedTaskModel

        session = SessionLocal()
        tasks_to_persist = []

        try:
            for task in tasks:
                # Check if task already exists (by task_id)
                existing = session.query(GeneratedTaskModel).filter_by(task_id=task.task_id).first()

                if existing:
                    logger.debug(f"[ROAD-C] Task {task.task_id} already exists, skipping")
                    continue

                db_task = GeneratedTaskModel(
                    task_id=task.task_id,
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    source_insights=task.source_insights,
                    suggested_files=task.suggested_files,
                    estimated_effort=task.estimated_effort,
                    run_id=run_id or task.run_id,
                    status="pending",
                )
                session.add(db_task)
                tasks_to_persist.append(db_task)

            session.commit()
            # Only count after successful commit
            persisted_count = len(tasks_to_persist)
            logger.info(f"[ROAD-C] Persisted {persisted_count} new tasks to database")
            return persisted_count

        except Exception as e:
            session.rollback()
            logger.error(f"[ROAD-C] Failed to persist tasks: {e}")
            raise
        finally:
            session.close()

    # =========================================================================
    # Task Retrieval (IMP-ARCH-012)
    # =========================================================================

    def get_pending_tasks(
        self,
        status: str = "pending",
        limit: int = 10,
    ) -> List[GeneratedTask]:
        """Retrieve pending tasks from database (IMP-ARCH-012).

        Args:
            status: Task status to filter by (default: pending)
            limit: Maximum number of tasks to return

        Returns:
            List of GeneratedTask dataclass instances
        """
        from sqlalchemy import case

        from ..database import SessionLocal
        from ..models import GeneratedTaskModel

        session = SessionLocal()

        try:
            db_tasks = (
                session.query(GeneratedTaskModel)
                .filter_by(status=status)
                .order_by(
                    # Priority order: critical > high > medium > low
                    case(
                        (GeneratedTaskModel.priority == "critical", 1),
                        (GeneratedTaskModel.priority == "high", 2),
                        (GeneratedTaskModel.priority == "medium", 3),
                        (GeneratedTaskModel.priority == "low", 4),
                        else_=5,
                    ),
                    GeneratedTaskModel.created_at.asc(),
                )
                .limit(limit)
                .all()
            )

            tasks = []
            for db_task in db_tasks:
                task = GeneratedTask(
                    task_id=db_task.task_id,
                    title=db_task.title,
                    description=db_task.description or "",
                    priority=db_task.priority,
                    source_insights=db_task.source_insights or [],
                    suggested_files=db_task.suggested_files or [],
                    estimated_effort=db_task.estimated_effort or "M",
                    created_at=db_task.created_at,
                    run_id=db_task.run_id,
                    status=db_task.status,
                )
                tasks.append(task)

            logger.info(f"[ROAD-C] Retrieved {len(tasks)} {status} tasks from database")
            return tasks

        finally:
            session.close()

    def mark_task_status(
        self,
        task_id: str,
        status: Optional[str] = None,
        executed_in_run_id: Optional[str] = None,
        increment_retry: bool = False,
        failure_run_id: Optional[str] = None,
    ) -> str:
        """Update task status in database (IMP-ARCH-012, IMP-LOOP-005).

        Args:
            task_id: ID of task to update
            status: New status (pending, in_progress, completed, skipped, failed).
                    If None and increment_retry=True, status is determined by retry logic.
            executed_in_run_id: Run ID that executed/is executing this task
            increment_retry: If True, increment retry_count and determine status based on retries
            failure_run_id: Run ID to add to failure_runs list (IMP-LOOP-005)

        Returns:
            Result string: "updated", "retry", "failed", or "not_found"
        """
        from ..database import SessionLocal
        from ..models import GeneratedTaskModel

        session = SessionLocal()

        try:
            db_task = session.query(GeneratedTaskModel).filter_by(task_id=task_id).first()

            if not db_task:
                logger.warning(f"[ROAD-C] Task {task_id} not found for status update")
                return "not_found"

            result = "updated"

            # IMP-LOOP-005: Handle retry logic when increment_retry is True
            if increment_retry:
                db_task.retry_count = (db_task.retry_count or 0) + 1

                # Track the failed run
                if failure_run_id:
                    failure_runs = db_task.failure_runs or []
                    if failure_run_id not in failure_runs:
                        failure_runs.append(failure_run_id)
                    db_task.failure_runs = failure_runs

                # Determine status based on retry count
                max_retries = db_task.max_retries or 3
                if db_task.retry_count >= max_retries:
                    db_task.status = "failed"
                    db_task.failure_reason = (
                        f"Exceeded max retries ({max_retries}). "
                        f"Failed in runs: {', '.join(db_task.failure_runs or [])}"
                    )
                    result = "failed"
                    logger.info(
                        f"[IMP-LOOP-005] Task {task_id} marked as failed "
                        f"(retry {db_task.retry_count}/{max_retries})"
                    )
                else:
                    db_task.status = "pending"  # Return to pending for retry
                    result = "retry"
                    logger.info(
                        f"[IMP-LOOP-005] Task {task_id} returned to pending for retry "
                        f"({db_task.retry_count}/{max_retries})"
                    )
            elif status is not None:
                db_task.status = status
                if status == "completed":
                    db_task.completed_at = datetime.now()

            db_task.updated_at = datetime.now()  # Track status change time (IMP-REL-003)
            if executed_in_run_id:
                db_task.executed_in_run_id = executed_in_run_id

            session.commit()
            logger.debug(f"[ROAD-C] Updated task {task_id} status to {db_task.status}")
            return result

        except Exception as e:
            session.rollback()
            logger.error(f"[ROAD-C] Failed to update task status: {e}")
            return "not_found"
        finally:
            session.close()

    # =========================================================================
    # Stale Task Cleanup (IMP-REL-003)
    # =========================================================================

    def cleanup_stale_tasks(
        self,
        threshold_hours: int = STALE_TASK_THRESHOLD_HOURS,
    ) -> int:
        """Clean up tasks stuck in in_progress state for too long (IMP-REL-003).

        Tasks that remain in_progress beyond the threshold are considered stale
        (likely due to a run failure) and are marked as failed.

        Args:
            threshold_hours: Hours after which in_progress tasks are considered stale.
                            Defaults to STALE_TASK_THRESHOLD_HOURS (24).

        Returns:
            Number of stale tasks cleaned up.
        """
        from ..database import SessionLocal
        from ..models import GeneratedTaskModel

        session = SessionLocal()
        threshold = datetime.now() - timedelta(hours=threshold_hours)

        try:
            # Query tasks stuck in in_progress state
            # Use updated_at if available, fall back to created_at for older tasks
            stale_tasks = (
                session.query(GeneratedTaskModel)
                .filter(
                    GeneratedTaskModel.status == "in_progress",
                )
                .all()
            )

            # Filter stale tasks based on updated_at or created_at
            tasks_to_cleanup = []
            for task in stale_tasks:
                # Use updated_at if set, otherwise use created_at
                check_time = task.updated_at or task.created_at
                if check_time < threshold:
                    tasks_to_cleanup.append(task)

            # Mark stale tasks as failed
            for task in tasks_to_cleanup:
                logger.warning(
                    f"[ROAD-C] Marking stale task {task.task_id} as failed "
                    f"(in_progress for over {threshold_hours} hours)"
                )
                task.status = "failed"
                task.updated_at = datetime.now()
                task.failure_reason = f"Stale: in_progress for over {threshold_hours} hours"

            session.commit()

            if tasks_to_cleanup:
                logger.info(f"[ROAD-C] Cleaned up {len(tasks_to_cleanup)} stale tasks")

            return len(tasks_to_cleanup)

        except Exception as e:
            session.rollback()
            logger.error(f"[ROAD-C] Failed to cleanup stale tasks: {e}")
            raise
        finally:
            session.close()
