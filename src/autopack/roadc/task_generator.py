"""ROAD-C: Autonomous Task Generator - converts insights to tasks."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ..memory.memory_service import MemoryService
from ..roadi import RegressionProtector

logger = logging.getLogger(__name__)


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
    status: str = "pending"  # pending, in_progress, completed, skipped


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
        self._regression = regression_protector or RegressionProtector()

    def generate_tasks(
        self, max_tasks: int = 10, min_confidence: float = 0.7
    ) -> TaskGenerationResult:
        """Generate improvement tasks from recent telemetry insights."""
        start_time = datetime.now()

        # Retrieve recent high-signal insights
        # IMP-ARCH-016: Removed namespace parameter - retrieve_insights now queries
        # across run_summaries, errors_ci, doctor_hints collections
        insights = self._memory.retrieve_insights(
            query="error failure bottleneck improvement opportunity",
            limit=100,
        )

        # Detect patterns across insights
        patterns = self._detect_patterns(insights)

        # Generate tasks from patterns
        tasks = []
        for pattern in patterns[:max_tasks]:
            if pattern["confidence"] >= min_confidence:
                task = self._pattern_to_task(pattern)
                tasks.append(task)

                # Add regression protection for each task
                self._ensure_regression_protection(task)

        return TaskGenerationResult(
            tasks_generated=tasks,
            insights_processed=len(insights),
            patterns_detected=len(patterns),
            generation_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )

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
Detected {pattern['occurrences']} occurrences of {pattern['type']} issues.

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
            status: New status (pending, in_progress, completed, skipped)
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
