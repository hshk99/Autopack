"""ROAD-C: Autonomous Task Generator - converts insights to tasks."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from ..memory.memory_service import MemoryService
from ..roadi import RegressionProtector
from ..telemetry.analyzer import RankedIssue

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
        from ..models import TaskGenerationEvent
        from ..database import SessionLocal

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
    ):
        self._memory = memory_service or MemoryService()
        # NOTE: TelemetryAnalyzer removed (IMP-ARCH-017) - it was never used and
        # requires db_session which isn't available at AutonomousTaskGenerator init time.
        # Task generation relies on MemoryService.retrieve_insights() instead.
        # IMP-FEAT-001: Telemetry can now be passed directly via generate_tasks().
        self._regression = regression_protector or RegressionProtector()

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
    ) -> TaskGenerationResult:
        """Generate improvement tasks from recent telemetry insights.

        Args:
            max_tasks: Maximum number of tasks to generate
            min_confidence: Minimum confidence threshold for pattern detection
            telemetry_insights: Optional telemetry data from TelemetryAnalyzer.aggregate_telemetry().
                               If provided, uses this directly instead of querying MemoryService.
                               This enables the ROAD-C self-improvement pipeline (IMP-FEAT-001).
            run_id: Optional run ID for telemetry tracking (IMP-LOOP-004)

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
            else:
                # Fallback: Retrieve recent high-signal insights from memory
                # IMP-ARCH-016: Removed namespace parameter - retrieve_insights now queries
                # across run_summaries, errors_ci, doctor_hints collections
                insights = self._memory.retrieve_insights(
                    query="error failure bottleneck improvement opportunity",
                    limit=100,
                )
                telemetry_source = "memory"

            # Detect patterns across insights
            patterns = self._detect_patterns(insights)

            # Generate tasks from patterns
            for pattern in patterns[:max_tasks]:
                if pattern["confidence"] >= min_confidence:
                    task = self._pattern_to_task(pattern)
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
        """Detect actionable patterns from insights."""
        patterns = []

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
                patterns.append(
                    {
                        "type": error_type,
                        "occurrences": len(group),
                        "confidence": min(1.0, len(group) / 5),
                        "examples": group[:3],
                        "severity": self._calculate_severity(group),
                    }
                )

        # Sort by severity and occurrences
        patterns.sort(key=lambda p: (p["severity"], p["occurrences"]), reverse=True)

        return patterns

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
        from ..models import GeneratedTaskModel
        from ..database import SessionLocal

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
        from ..models import GeneratedTaskModel
        from ..database import SessionLocal
        from sqlalchemy import case

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
        status: str,
        executed_in_run_id: Optional[str] = None,
    ) -> bool:
        """Update task status in database (IMP-ARCH-012).

        Args:
            task_id: ID of task to update
            status: New status (pending, in_progress, completed, skipped, failed)
            executed_in_run_id: Run ID that executed/is executing this task

        Returns:
            True if task was updated, False if not found
        """
        from ..models import GeneratedTaskModel
        from ..database import SessionLocal

        session = SessionLocal()

        try:
            db_task = session.query(GeneratedTaskModel).filter_by(task_id=task_id).first()

            if not db_task:
                logger.warning(f"[ROAD-C] Task {task_id} not found for status update")
                return False

            db_task.status = status
            db_task.updated_at = datetime.now()  # Track status change time (IMP-REL-003)
            if status == "completed":
                db_task.completed_at = datetime.now()
            if executed_in_run_id:
                db_task.executed_in_run_id = executed_in_run_id

            session.commit()
            logger.debug(f"[ROAD-C] Updated task {task_id} status to {status}")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"[ROAD-C] Failed to update task status: {e}")
            return False
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
        from ..models import GeneratedTaskModel
        from ..database import SessionLocal

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
