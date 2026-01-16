"""ROAD-C: Autonomous Task Generator - converts insights to tasks."""

from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime
from ..memory.memory_service import MemoryService
from ..telemetry.analyzer import TelemetryAnalyzer


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
        analyzer: Optional[TelemetryAnalyzer] = None,
    ):
        self._memory = memory_service or MemoryService()
        self._analyzer = analyzer or TelemetryAnalyzer()

    def generate_tasks(
        self, max_tasks: int = 10, min_confidence: float = 0.7
    ) -> TaskGenerationResult:
        """Generate improvement tasks from recent telemetry insights."""
        start_time = datetime.now()

        # Retrieve recent high-signal insights
        insights = self._memory.retrieve_insights(
            query="error failure bottleneck improvement opportunity",
            namespace="telemetry_insights",
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
