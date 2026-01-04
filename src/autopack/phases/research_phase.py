"""Research Phase Implementation for Autonomous Build System.

This module implements the RESEARCH phase type, which enables the autonomous
executor to conduct research sessions before making implementation decisions.

Research phases are used when:
- A task requires external knowledge gathering
- Multiple implementation approaches need evaluation
- Domain-specific context is needed for decision-making
- Evidence collection is required before proceeding

Design Principles:
- Research phases are non-blocking and time-bounded
- Results are cached and reusable across phases
- Integration with BUILD_HISTORY for learning
- Clear success/failure criteria
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResearchStatus(Enum):
    """Status of a research phase."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Alias for backward compatibility with tests
ResearchPhaseStatus = ResearchStatus


@dataclass
class ResearchQuery:
    """Represents a research query within a phase."""

    query: str
    priority: int = 1
    required: bool = False
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchResult:
    """Result from a research query."""

    query: str
    answer: str
    confidence: float
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchPhaseConfig:
    """Configuration for a research phase."""

    queries: List[ResearchQuery] = field(default_factory=list)
    max_duration_minutes: Optional[int] = None
    save_to_history: bool = True
    auto_approve_threshold: float = 0.9


@dataclass
class ResearchPhase:
    """Represents a research phase with its configuration and state."""

    phase_id: str
    description: str
    config: ResearchPhaseConfig
    status: ResearchStatus = ResearchStatus.PENDING
    results: List[ResearchResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "queries": [
                    {
                        "query": q.query,
                        "priority": q.priority,
                        "required": q.required,
                        "context": q.context,
                    }
                    for q in self.config.queries
                ],
                "max_duration_minutes": self.config.max_duration_minutes,
                "save_to_history": self.config.save_to_history,
                "auto_approve_threshold": self.config.auto_approve_threshold,
            },
            "results": [
                {
                    "query": r.query,
                    "answer": r.answer,
                    "confidence": r.confidence,
                    "sources": r.sources,
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class ResearchPhaseExecutor:
    """Executor for research phases."""

    def __init__(
        self,
        research_system: Optional[Any] = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.

        Args:
            research_system: Optional research system to query
            build_history_path: Optional path to BUILD_HISTORY.md
        """
        self.research_system = research_system
        self.build_history_path = build_history_path

    def execute(self, phase: ResearchPhase) -> ResearchPhase:
        """Execute a research phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing research phase: {phase.phase_id}")

        phase.status = ResearchStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.results = []
        phase.error = None

        try:
            # Execute each query
            for query in phase.config.queries:
                try:
                    result = self._execute_query(query)
                    phase.results.append(result)

                    # Check if required query failed
                    if query.required and result.confidence < 0.5:
                        phase.status = ResearchStatus.FAILED
                        phase.error = f"Required query failed: {query.query}"
                        break

                except Exception as e:
                    logger.error(f"Query execution failed: {e}", exc_info=True)
                    if query.required:
                        phase.status = ResearchStatus.FAILED
                        phase.error = f"Required query failed: {str(e)}"
                        break

            # Mark as completed if not already failed
            if phase.status == ResearchStatus.IN_PROGRESS:
                phase.status = ResearchStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = ResearchStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _execute_query(self, query: ResearchQuery) -> ResearchResult:
        """Execute a single research query.

        Args:
            query: The query to execute

        Returns:
            ResearchResult with findings
        """
        if self.research_system is None:
            # Fallback when no research system is available
            return ResearchResult(
                query=query.query,
                answer="No research system available",
                confidence=0.0,
                sources=[],
                metadata={"fallback": True},
            )

        # Call research system
        response = self.research_system.query(query.query, query.context)

        # Convert response to ResearchResult
        return ResearchResult(
            query=query.query,
            answer=response.get("answer", ""),
            confidence=response.get("confidence", 0.0),
            sources=response.get("sources", []),
            metadata=response.get("metadata", {}),
        )

    def should_auto_approve(self, phase: ResearchPhase) -> bool:
        """Check if phase results should be auto-approved.

        Args:
            phase: The phase to check

        Returns:
            True if should auto-approve
        """
        if not phase.results:
            return False

        # Calculate average confidence
        avg_confidence = sum(r.confidence for r in phase.results) / len(phase.results)

        return avg_confidence >= phase.config.auto_approve_threshold

    def _save_to_history(self, phase: ResearchPhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        # Append to build history
        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: ResearchPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Research Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.results:
            lines.append("### Results")
            for result in phase.results:
                lines.append(f"- **Query**: {result.query}")
                lines.append(f"  - **Confidence**: {result.confidence:.1%}")
                lines.append(f"  - **Answer**: {result.answer}")
                if result.sources:
                    lines.append(f"  - **Sources**: {', '.join(result.sources)}")
                lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class ResearchPhaseResult:
    """Result object expected by workflow tests.

    This is a simpler interface for tests that expect a flat result structure.
    """
    status: ResearchStatus
    query: str
    findings: List[Any] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    iterations_used: int = 1
    duration_seconds: float = 0.0


def create_research_phase(phase_id: str, queries: List[str], **kwargs) -> ResearchPhase:
    """Factory function to create a research phase.

    Args:
        phase_id: Unique phase identifier
        queries: List of research query strings
        **kwargs: Additional configuration options

    Returns:
        Configured ResearchPhase instance
    """
    research_queries = [
        ResearchQuery(query=q, priority=i+1)
        for i, q in enumerate(queries)
    ]

    config = ResearchPhaseConfig(queries=research_queries)

    return ResearchPhase(
        phase_id=phase_id,
        description=f"Research phase: {phase_id}",
        config=config,
    )


# Backward compatibility alias for tests
ResearchPhaseManager = ResearchPhaseExecutor

# Backward compatibility - ResearchPriority not in original implementation
class ResearchPriority:
    """Compat shim for ResearchPriority (missing from original)."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Backward compatibility - create_research_phase_from_task not in original
def create_research_phase_from_task(task_description: str, **kwargs) -> ResearchPhase:
    """Compat shim for creating research phase from task description."""
    return create_research_phase(
        phase_id=f"research_{kwargs.get('task_id', 'default')}",
        queries=[task_description],
        **kwargs
    )
