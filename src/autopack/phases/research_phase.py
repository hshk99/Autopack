"""Research Phase Implementation for Autonomous Build System.

This module implements the RESEARCH phase type, which enables the autonomous
executor to conduct research sessions before making implementation decisions.

Research phases are used when:
- A task requires external knowledge gathering
- Multiple implementation approaches need evaluation
- Domain-specific context is needed for decision-making
- Evidence collection is required before proceeding

Design Principles:
- Research phases are non-blocking and can be skipped if needed
- Results are stored in BUILD_HISTORY for future reference
- Integration with autonomous executor is seamless
- Human review is optional but recommended for critical decisions
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
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
    SKIPPED = "skipped"


# BUILD-146: Compatibility alias for tests
ResearchPhaseStatus = ResearchStatus


@dataclass
class ResearchPhaseResult:
    """Result from a research phase (BUILD-146: compatibility for tests)."""

    status: ResearchStatus
    query: str
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    iterations_used: int = 0
    duration_seconds: float = 0.0


@dataclass
class ResearchQuery:
    """Represents a research query."""
    
    query: str
    context: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1=low, 5=high
    required: bool = False  # If True, phase cannot proceed without answer


@dataclass
class ResearchResult:
    """Result from a research query."""
    
    query: str
    answer: str
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchPhaseConfig:
    """Configuration for a research phase."""
    
    queries: List[ResearchQuery] = field(default_factory=list)
    max_duration_minutes: int = 30
    require_human_review: bool = False
    auto_approve_threshold: float = 0.8  # Auto-approve if confidence >= this
    output_format: str = "markdown"  # 'markdown', 'json', 'yaml'
    save_to_history: bool = True


@dataclass
class ResearchPhase:
    """Represents a research phase in the build process."""
    
    phase_id: str
    description: str
    config: ResearchPhaseConfig
    status: ResearchStatus = ResearchStatus.PENDING
    results: List[ResearchResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "queries": [asdict(q) for q in self.config.queries],
                "max_duration_minutes": self.config.max_duration_minutes,
                "require_human_review": self.config.require_human_review,
                "auto_approve_threshold": self.config.auto_approve_threshold,
                "output_format": self.config.output_format,
                "save_to_history": self.config.save_to_history,
            },
            "results": [
                {
                    "query": r.query,
                    "answer": r.answer,
                    "sources": r.sources,
                    "confidence": r.confidence,
                    "timestamp": r.timestamp.isoformat(),
                    "metadata": r.metadata,
                }
                for r in self.results
            ],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class ResearchPhaseExecutor:
    """Executes research phases."""
    
    def __init__(
        self,
        research_system: Any = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.
        
        Args:
            research_system: Research system instance (optional)
            build_history_path: Path to BUILD_HISTORY.md
        """
        self.research_system = research_system
        self.build_history_path = build_history_path or Path("BUILD_HISTORY.md")
    
    def execute(self, phase: ResearchPhase) -> ResearchPhase:
        """Execute a research phase.
        
        Args:
            phase: Research phase to execute
            
        Returns:
            Updated research phase with results
        """
        logger.info(f"Executing research phase: {phase.phase_id}")
        
        phase.status = ResearchStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        
        try:
            # Execute each query
            for query in phase.config.queries:
                result = self._execute_query(query)
                phase.results.append(result)
                
                # Check if required query failed
                if query.required and result.confidence < 0.5:
                    raise ValueError(
                        f"Required query failed: {query.query} "
                        f"(confidence: {result.confidence})"
                    )
            
            phase.status = ResearchStatus.COMPLETED
            phase.completed_at = datetime.now()
            
            # Save to BUILD_HISTORY if configured
            if phase.config.save_to_history:
                self._save_to_history(phase)
        
        except Exception as e:
            logger.error(f"Research phase failed: {e}")
            phase.status = ResearchStatus.FAILED
            phase.error = str(e)
            phase.completed_at = datetime.now()
        
        return phase
    
    def _execute_query(self, query: ResearchQuery) -> ResearchResult:
        """Execute a single research query.
        
        Args:
            query: Query to execute
            
        Returns:
            Research result
        """
        if not self.research_system:
            # Fallback: return placeholder result
            logger.warning("No research system available, using placeholder")
            return ResearchResult(
                query=query.query,
                answer="Research system not available",
                confidence=0.0,
            )
        
        try:
            # Call research system
            result = self.research_system.query(
                query.query,
                context=query.context,
            )
            
            return ResearchResult(
                query=query.query,
                answer=result.get("answer", ""),
                sources=result.get("sources", []),
                confidence=result.get("confidence", 0.0),
                metadata=result.get("metadata", {}),
            )
        
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return ResearchResult(
                query=query.query,
                answer=f"Query failed: {e}",
                confidence=0.0,
            )
    
    def _save_to_history(self, phase: ResearchPhase) -> None:
        """Save research phase to BUILD_HISTORY.
        
        Args:
            phase: Research phase to save
        """
        try:
            # Format phase entry
            entry = self._format_history_entry(phase)
            
            # Append to BUILD_HISTORY.md
            if self.build_history_path.exists():
                content = self.build_history_path.read_text()
            else:
                content = "# Build History\n\n"
            
            content += "\n" + entry + "\n"
            self.build_history_path.write_text(content)
            
            logger.info(f"Saved research phase to {self.build_history_path}")
        
        except Exception as e:
            logger.error(f"Failed to save to BUILD_HISTORY: {e}")
    
    def _format_history_entry(self, phase: ResearchPhase) -> str:
        """Format research phase as BUILD_HISTORY entry.
        
        Args:
            phase: Research phase to format
            
        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Research Phase: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at.isoformat() if phase.started_at else 'N/A'}",
            f"**Completed**: {phase.completed_at.isoformat() if phase.completed_at else 'N/A'}",
            "",
        ]
        
        if phase.results:
            lines.append("### Research Results:")
            for i, result in enumerate(phase.results, 1):
                lines.extend([
                    f"\n#### Query {i}: {result.query}",
                    f"**Confidence**: {result.confidence:.2f}",
                    f"**Answer**: {result.answer}",
                ])
                if result.sources:
                    lines.append("**Sources**:")
                    for source in result.sources:
                        lines.append(f"- {source}")
        
        if phase.error:
            lines.extend([
                "",
                f"### Error: {phase.error}",
            ])
        
        return "\n".join(lines)
    
    def should_auto_approve(self, phase: ResearchPhase) -> bool:
        """Check if phase results should be auto-approved.
        
        Args:
            phase: Research phase to check
            
        Returns:
            True if auto-approval is recommended
        """
        if phase.status != ResearchStatus.COMPLETED:
            return False
        
        if not phase.results:
            return False
        
        # Check if all results meet confidence threshold
        avg_confidence = sum(r.confidence for r in phase.results) / len(phase.results)
        return avg_confidence >= phase.config.auto_approve_threshold
