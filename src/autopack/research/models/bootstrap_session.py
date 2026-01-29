"""Bootstrap Session Model for research-to-anchor pipeline.

This module provides the BootstrapSession model which manages the workflow state
for bootstrap sessions that coordinate multiple research phases in parallel.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class BootstrapPhase(str, Enum):
    """Phases of the bootstrap research process."""

    INITIALIZED = "initialized"
    MARKET_RESEARCH = "market_research"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    TECHNICAL_FEASIBILITY = "technical_feasibility"
    SYNTHESIS = "synthesis"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchPhaseResult(BaseModel):
    """Result from a single research phase."""

    phase: BootstrapPhase = Field(..., description="Phase that produced this result")
    status: str = Field(
        default="pending", description="Status: pending, running, completed, failed"
    )
    started_at: Optional[datetime] = Field(default=None, description="When the phase started")
    completed_at: Optional[datetime] = Field(default=None, description="When the phase completed")
    data: dict[str, Any] = Field(default_factory=dict, description="Research data collected")
    errors: list[str] = Field(default_factory=list, description="Errors encountered")
    duration_seconds: Optional[float] = Field(default=None, description="How long the phase took")


class BootstrapSession(BaseModel):
    """Bootstrap session managing the research workflow state.

    Coordinates market research, competitive analysis, and technical feasibility
    research phases, supporting parallel execution and caching.
    """

    session_id: str = Field(..., description="Unique session identifier")
    idea_hash: str = Field(..., description="Hash of the parsed idea for caching")
    parsed_idea_title: str = Field(default="", description="Title from parsed idea")
    parsed_idea_type: str = Field(default="other", description="Detected project type")

    current_phase: BootstrapPhase = Field(
        default=BootstrapPhase.INITIALIZED, description="Current phase of the session"
    )

    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update time")
    expires_at: Optional[datetime] = Field(default=None, description="When cache expires (24h TTL)")

    market_research: ResearchPhaseResult = Field(
        default_factory=lambda: ResearchPhaseResult(phase=BootstrapPhase.MARKET_RESEARCH),
        description="Market research results",
    )
    competitive_analysis: ResearchPhaseResult = Field(
        default_factory=lambda: ResearchPhaseResult(phase=BootstrapPhase.COMPETITIVE_ANALYSIS),
        description="Competitive analysis results",
    )
    technical_feasibility: ResearchPhaseResult = Field(
        default_factory=lambda: ResearchPhaseResult(phase=BootstrapPhase.TECHNICAL_FEASIBILITY),
        description="Technical feasibility results",
    )

    synthesis: dict[str, Any] = Field(
        default_factory=dict, description="Synthesized findings from all phases"
    )

    parallel_execution_used: bool = Field(
        default=False, description="Whether parallel execution was used"
    )
    total_duration_seconds: Optional[float] = Field(
        default=None, description="Total session duration"
    )

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True

    def is_complete(self) -> bool:
        """Check if all research phases are complete."""
        return (
            self.market_research.status == "completed"
            and self.competitive_analysis.status == "completed"
            and self.technical_feasibility.status == "completed"
        )

    def is_cached_valid(self) -> bool:
        """Check if cached results are still valid (within 24h TTL)."""
        if self.expires_at is None:
            return False
        return datetime.now() < self.expires_at

    def get_completed_phases(self) -> list[BootstrapPhase]:
        """Get list of completed phases."""
        completed = []
        if self.market_research.status == "completed":
            completed.append(BootstrapPhase.MARKET_RESEARCH)
        if self.competitive_analysis.status == "completed":
            completed.append(BootstrapPhase.COMPETITIVE_ANALYSIS)
        if self.technical_feasibility.status == "completed":
            completed.append(BootstrapPhase.TECHNICAL_FEASIBILITY)
        return completed

    def get_failed_phases(self) -> list[tuple[BootstrapPhase, list[str]]]:
        """Get list of failed phases with their errors."""
        failed = []
        if self.market_research.status == "failed":
            failed.append((BootstrapPhase.MARKET_RESEARCH, self.market_research.errors))
        if self.competitive_analysis.status == "failed":
            failed.append((BootstrapPhase.COMPETITIVE_ANALYSIS, self.competitive_analysis.errors))
        if self.technical_feasibility.status == "failed":
            failed.append((BootstrapPhase.TECHNICAL_FEASIBILITY, self.technical_feasibility.errors))
        return failed

    def mark_phase_started(self, phase: BootstrapPhase) -> None:
        """Mark a phase as started."""
        result = self._get_phase_result(phase)
        if result:
            result.status = "running"
            result.started_at = datetime.now()
        self.updated_at = datetime.now()

    def mark_phase_completed(self, phase: BootstrapPhase, data: dict[str, Any]) -> None:
        """Mark a phase as completed with its data."""
        result = self._get_phase_result(phase)
        if result:
            result.status = "completed"
            result.completed_at = datetime.now()
            result.data = data
            if result.started_at:
                result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.updated_at = datetime.now()
        self._check_all_complete()

    def mark_phase_failed(self, phase: BootstrapPhase, errors: list[str]) -> None:
        """Mark a phase as failed with errors."""
        result = self._get_phase_result(phase)
        if result:
            result.status = "failed"
            result.completed_at = datetime.now()
            result.errors = errors
            if result.started_at:
                result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        self.updated_at = datetime.now()

    def _get_phase_result(self, phase: BootstrapPhase) -> Optional[ResearchPhaseResult]:
        """Get the result object for a phase."""
        if phase == BootstrapPhase.MARKET_RESEARCH:
            return self.market_research
        elif phase == BootstrapPhase.COMPETITIVE_ANALYSIS:
            return self.competitive_analysis
        elif phase == BootstrapPhase.TECHNICAL_FEASIBILITY:
            return self.technical_feasibility
        return None

    def _check_all_complete(self) -> None:
        """Check if all phases are complete and update session status."""
        if self.is_complete():
            self.current_phase = BootstrapPhase.SYNTHESIS
            if self.created_at:
                self.total_duration_seconds = (datetime.now() - self.created_at).total_seconds()


def generate_idea_hash(title: str, description: str, project_type: str) -> str:
    """Generate a hash for a parsed idea for caching purposes.

    Args:
        title: Project title
        description: Project description
        project_type: Detected project type

    Returns:
        MD5 hash string for the idea
    """
    content = f"{title.lower().strip()}:{description.lower().strip()[:200]}:{project_type}"
    return hashlib.md5(content.encode()).hexdigest()
