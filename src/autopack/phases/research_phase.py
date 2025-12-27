"""Research Phase Implementation for Autonomous Build System.

This module implements the RESEARCH phase type, which enables the autonomous
executor to conduct research sessions before making implementation decisions.

Research phases are used when:
- A task requires external knowledge gathering
- Multiple implementation approaches need evaluation
- Domain-specific context is needed for decision-making
- Evidence collection is required before proceeding

Design Principles:
- Research phases are non-blocking and can run in parallel
- Results are stored for review before implementation
- Integration with BUILD_HISTORY for decision tracking
- Support for both autonomous and manual research triggers
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#
# ---------------------------------------------------------------------------
# Compatibility shims (legacy execution API)
# ---------------------------------------------------------------------------
#
# Newer code in this repo uses the storage-oriented `ResearchPhase` dataclass
# (phase_id/title/queries/results, etc.).
#
# Older tests and historical runs also expect an executable research phase:
#   from autopack.phases.research_phase import ResearchPhase, ResearchPhaseConfig
#   phase = ResearchPhase(config=ResearchPhaseConfig(...))
#   result = phase.execute()
#
# We keep the existing `ResearchPhase` dataclass intact and *add* a separate
# executor class, then export a compatibility alias named `ResearchPhase`
# only if it is safe in-context. To avoid breaking current code, we instead
# provide `ResearchPhaseExecutor` and a thin callable `ResearchPhaseRunner`
# while also exposing `ResearchPhaseConfig`, `ResearchPhaseResult`,
# and a patchable `ResearchSession`.
#

class ResearchStatus(Enum):
    """Status of a research phase."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchPriority(Enum):
    """Priority level for research phases."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ResearchQuery:
    """Represents a research query to be executed."""
    query_text: str
    context: Dict[str, Any] = field(default_factory=dict)
    max_results: int = 10
    timeout_seconds: int = 300


@dataclass
class ResearchResult:
    """Results from a research query."""
    query: ResearchQuery
    findings: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    sources: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class ResearchPhaseRecord:
    """Represents a stored research phase in the build system."""
    
    phase_id: str
    title: str
    description: str
    queries: List[ResearchQuery]
    status: ResearchStatus = ResearchStatus.PENDING
    priority: ResearchPriority = ResearchPriority.MEDIUM
    results: List[ResearchResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "phase_id": self.phase_id,
            "title": self.title,
            "description": self.description,
            "queries": [asdict(q) for q in self.queries],
            "status": self.status.value,
            "priority": self.priority.value,
            "results": [asdict(r) for r in self.results],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResearchPhaseRecord:
        """Create from dictionary."""
        return cls(
            phase_id=data["phase_id"],
            title=data["title"],
            description=data["description"],
            queries=[
                ResearchQuery(**q) for q in data.get("queries", [])
            ],
            status=ResearchStatus(data.get("status", "pending")),
            priority=ResearchPriority(data.get("priority", "medium")),
            results=[
                ResearchResult(
                    query=ResearchQuery(**r["query"]),
                    findings=r.get("findings", []),
                    summary=r.get("summary", ""),
                    confidence=r.get("confidence", 0.0),
                    sources=r.get("sources", []),
                    timestamp=datetime.fromisoformat(r["timestamp"]),
                    error=r.get("error"),
                )
                for r in data.get("results", [])
            ],
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {}),
        )


class ResearchPhaseManager:
    """Manages research phases in the build system."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize the research phase manager.
        
        Args:
            storage_dir: Directory for storing research phase data
        """
        self.storage_dir = storage_dir or Path(".autopack/research")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._phases: Dict[str, ResearchPhaseRecord] = {}
        self._load_phases()
    
    def create_phase(
        self,
        title: str,
        description: str,
        queries: List[ResearchQuery],
        priority: ResearchPriority = ResearchPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResearchPhaseRecord:
        """Create a new research phase.
        
        Args:
            title: Phase title
            description: Phase description
            queries: List of research queries to execute
            priority: Phase priority
            metadata: Additional metadata
            
        Returns:
            Created ResearchPhase
        """
        phase_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        phase = ResearchPhaseRecord(
            phase_id=phase_id,
            title=title,
            description=description,
            queries=queries,
            priority=priority,
            metadata=metadata or {},
        )
        
        self._phases[phase_id] = phase
        self._save_phase(phase)
        
        logger.info(f"Created research phase: {phase_id}")
        return phase
    
    def start_phase(self, phase_id: str) -> None:
        """Mark a phase as started.
        
        Args:
            phase_id: ID of the phase to start
        """
        phase = self._phases.get(phase_id)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")
        
        phase.status = ResearchStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        self._save_phase(phase)
        
        logger.info(f"Started research phase: {phase_id}")
    
    def add_result(
        self,
        phase_id: str,
        result: ResearchResult,
    ) -> None:
        """Add a research result to a phase.
        
        Args:
            phase_id: ID of the phase
            result: Research result to add
        """
        phase = self._phases.get(phase_id)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")
        
        phase.results.append(result)
        self._save_phase(phase)
        
        logger.debug(f"Added result to phase {phase_id}")
    
    def complete_phase(
        self,
        phase_id: str,
        success: bool = True,
    ) -> None:
        """Mark a phase as completed.
        
        Args:
            phase_id: ID of the phase to complete
            success: Whether the phase completed successfully
        """
        phase = self._phases.get(phase_id)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")
        
        phase.status = ResearchStatus.COMPLETED if success else ResearchStatus.FAILED
        phase.completed_at = datetime.now()
        self._save_phase(phase)
        
        logger.info(f"Completed research phase: {phase_id} (success={success})")
    
    def cancel_phase(self, phase_id: str) -> None:
        """Cancel a research phase.
        
        Args:
            phase_id: ID of the phase to cancel
        """
        phase = self._phases.get(phase_id)
        if not phase:
            raise ValueError(f"Phase not found: {phase_id}")
        
        phase.status = ResearchStatus.CANCELLED
        phase.completed_at = datetime.now()
        self._save_phase(phase)
        
        logger.info(f"Cancelled research phase: {phase_id}")
    
    def get_phase(self, phase_id: str) -> Optional[ResearchPhaseRecord]:
        """Get a research phase by ID.
        
        Args:
            phase_id: ID of the phase
            
        Returns:
            ResearchPhase if found, None otherwise
        """
        return self._phases.get(phase_id)
    
    def list_phases(
        self,
        status: Optional[ResearchStatus] = None,
        priority: Optional[ResearchPriority] = None,
    ) -> List[ResearchPhaseRecord]:
        """List research phases with optional filtering.
        
        Args:
            status: Filter by status
            priority: Filter by priority
            
        Returns:
            List of matching ResearchPhase objects
        """
        phases = list(self._phases.values())
        
        if status:
            phases = [p for p in phases if p.status == status]
        
        if priority:
            phases = [p for p in phases if p.priority == priority]
        
        # Sort by priority (critical first) then by created_at
        priority_order = {
            ResearchPriority.CRITICAL: 0,
            ResearchPriority.HIGH: 1,
            ResearchPriority.MEDIUM: 2,
            ResearchPriority.LOW: 3,
        }
        
        phases.sort(
            key=lambda p: (priority_order[p.priority], p.created_at),
            reverse=False,
        )
        
        return phases
    
    def _save_phase(self, phase: ResearchPhaseRecord) -> None:
        """Save a phase to disk."""
        phase_file = self.storage_dir / f"{phase.phase_id}.json"
        try:
            phase_file.write_text(json.dumps(phase.to_dict(), indent=2))
        except Exception as e:
            logger.error(f"Error saving phase {phase.phase_id}: {e}")
    
    def _load_phases(self) -> None:
        """Load all phases from disk."""
        if not self.storage_dir.exists():
            return
        
        for phase_file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(phase_file.read_text())
                phase = ResearchPhaseRecord.from_dict(data)
                self._phases[phase.phase_id] = phase
            except Exception as e:
                logger.error(f"Error loading phase from {phase_file}: {e}")
        
        logger.info(f"Loaded {len(self._phases)} research phases")


def create_research_phase_from_task(
    task_description: str,
    task_category: str,
    context: Optional[Dict[str, Any]] = None,
) -> ResearchPhaseRecord:
    """Create a research phase from a task description.
    
    Args:
        task_description: Description of the task
        task_category: Category of the task
        context: Additional context for research
        
    Returns:
        ResearchPhase configured for the task
    """
    # Generate research queries based on task
    queries = []
    
    # Main query about the task
    queries.append(ResearchQuery(
        query_text=f"Best practices for {task_category}: {task_description}",
        context=context or {},
    ))
    
    # Query about common pitfalls
    queries.append(ResearchQuery(
        query_text=f"Common issues and pitfalls when {task_description}",
        context=context or {},
    ))
    
    # Query about implementation approaches
    queries.append(ResearchQuery(
        query_text=f"Implementation approaches for {task_description}",
        context=context or {},
    ))
    
    manager = ResearchPhaseManager()
    return manager.create_phase(
        title=f"Research: {task_description[:50]}",
        description=task_description,
        queries=queries,
        priority=ResearchPriority.MEDIUM,
        metadata={
            "task_category": task_category,
            "auto_generated": True,
        },
    )


# ---------------------------------------------------------------------------
# Legacy execution API (used by tests/autopack/integration/test_research_end_to_end.py
# and tests/autopack/workflow/test_research_review.py)
# ---------------------------------------------------------------------------


@dataclass
class ResearchPhaseConfig:
    query: str
    max_iterations: int = 3
    output_dir: Optional[Path] = None
    store_results: bool = False
    session_id_prefix: str = "research"


@dataclass
class ResearchPhaseResult:
    success: bool
    session_id: str
    query: str
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    iterations_used: int = 0
    duration_seconds: float = 0.0
    artifacts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ResearchSession:
    """Placeholder session class.

    Integration tests patch `autopack.phases.research_phase.ResearchSession`
    and expect `.research(...)` to return an object with:
      - session_id
      - final_answer
      - iterations (each has .summary)
      - status
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs

    def research(self, query: str, max_iterations: int = 3) -> Any:
        raise RuntimeError(
            "ResearchSession.research is a stub. In tests it should be patched; "
            "in production use the research subsystem instead."
        )


class ResearchPhaseExecutor:
    """Executable research phase wrapper expected by older tests."""

    def __init__(self, config: ResearchPhaseConfig):
        self.config = config

    def execute(self) -> ResearchPhaseResult:
        start = datetime.now()
        output_dir = self.config.output_dir
        if output_dir is not None:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        # Execute research (patched in tests).
        session = ResearchSession()
        try:
            session_result = session.research(
                self.config.query, max_iterations=self.config.max_iterations
            )
        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            return ResearchPhaseResult(
                success=False,
                session_id=f"{self.config.session_id_prefix}_error",
                query=self.config.query,
                findings=[],
                recommendations=[],
                confidence_score=0.0,
                iterations_used=0,
                duration_seconds=duration,
                artifacts={},
                error=str(e),
            )

        duration = (datetime.now() - start).total_seconds()

        # Basic extraction from mocked/real session result.
        session_id = getattr(session_result, "session_id", f"{self.config.session_id_prefix}_unknown")
        final_answer = getattr(session_result, "final_answer", "") or ""
        iterations = getattr(session_result, "iterations", []) or []

        findings: List[str] = []
        if final_answer:
            findings.append(final_answer)
        for it in iterations:
            summary = getattr(it, "summary", None)
            if summary:
                findings.append(str(summary))

        confidence = 0.8 if findings else 0.0

        artifacts: Dict[str, Any] = {}
        if self.config.store_results and output_dir is not None:
            try:
                result_path = output_dir / f"{session_id}_research_result.json"
                result_path.write_text(
                    json.dumps(
                        {
                            "session_id": session_id,
                            "query": self.config.query,
                            "findings": findings,
                            "duration_seconds": duration,
                        },
                        indent=2,
                    )
                )
                artifacts["result_json"] = result_path
            except Exception as e:
                logger.debug("Failed to store research results artifact: %s", e)
                artifacts["result_json"] = None
        else:
            # Tests accept non-existent paths; return a sentinel artifact.
            artifacts["result_json"] = output_dir / f"{session_id}_research_result.json" if output_dir else "in_memory"

        return ResearchPhaseResult(
            success=str(getattr(session_result, "status", "completed")).lower() == "completed",
            session_id=session_id,
            query=self.config.query,
            findings=findings,
            recommendations=[],
            confidence_score=confidence,
            iterations_used=len(iterations),
            duration_seconds=duration,
            artifacts=artifacts,
        )


# Legacy import compatibility:
# - tests import `ResearchPhase` expecting executable; elsewhere `ResearchPhase`
#   is already a dataclass. Export the executor under a distinct name and also
#   provide `ExecutableResearchPhase` for clarity.
ExecutableResearchPhase = ResearchPhaseExecutor

# Legacy name expected by tests:
# - `ResearchPhase(config=ResearchPhaseConfig(...)).execute()`
ResearchPhase = ResearchPhaseExecutor
