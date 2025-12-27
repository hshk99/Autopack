"""Pydantic schemas for API requests and responses"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class RunCreate(BaseModel):
    """Request to create a new run"""

    run_id: str = Field(..., description="Unique identifier for the run")
    safety_profile: str = Field(default="normal", description="normal or safety_critical")
    run_scope: str = Field(default="multi_tier", description="multi_tier or single_tier")
    token_cap: Optional[int] = Field(default=5_000_000, description="Maximum tokens for this run")
    max_phases: Optional[int] = Field(default=25, description="Maximum phases for this run")
    max_duration_minutes: Optional[int] = Field(default=120, description="Maximum duration in minutes")


class TierCreate(BaseModel):
    """Tier to be created within a run"""

    tier_id: str = Field(..., description="Tier identifier (e.g. T1, T2)")
    tier_index: int = Field(..., description="Order index for this tier")
    name: str = Field(..., description="Human-readable tier name")
    description: Optional[str] = Field(None, description="Tier description")


class PhaseCreate(BaseModel):
    """Phase to be created within a tier"""

    phase_id: str = Field(..., description="Phase identifier (e.g. F2.3)")
    phase_index: int = Field(..., description="Order index for this phase")
    tier_id: str = Field(..., description="Parent tier identifier")
    name: str = Field(..., description="Human-readable phase name")
    description: Optional[str] = Field(None, description="Phase description")
    task_category: Optional[str] = Field(None, description="Task category (e.g. schema_change)")
    complexity: Optional[str] = Field(None, description="Complexity: low, medium, or high")
    builder_mode: Optional[str] = Field(None, description="Builder mode (e.g. tweak_light)")
    scope: Optional[Dict[str, Any]] = Field(None, description="Scope configuration: paths and read_only_context")


class RunStartRequest(BaseModel):
    """Request to start a run with tiers and phases"""

    run: RunCreate
    tiers: List[TierCreate] = Field(default_factory=list)
    phases: List[PhaseCreate] = Field(default_factory=list)


class PhaseStatusUpdate(BaseModel):
    """Request to update phase status"""

    state: str = Field(..., description="New phase state")
    builder_attempts: Optional[int] = Field(None)
    tokens_used: Optional[int] = Field(None)
    minor_issues_count: Optional[int] = Field(None)
    major_issues_count: Optional[int] = Field(None)
    quality_level: Optional[str] = Field(None, description="Quality level: ok, needs_review, blocked")
    quality_blocked: Optional[bool] = Field(None, description="Whether phase is blocked by quality gate")


class PhaseResponse(BaseModel):
    """Phase information response"""

    id: int
    phase_id: str
    run_id: str
    tier_id: int
    name: str
    description: Optional[str]
    state: str
    task_category: Optional[str]
    complexity: Optional[str]
    builder_mode: Optional[str]
    phase_index: int
    scope: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class TierResponse(BaseModel):
    """Tier information response"""

    id: int
    tier_id: str
    name: str
    state: str
    tier_index: int
    cleanliness: str
    minor_issues_count: int
    major_issues_count: int
    phases: List[PhaseResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RunResponse(BaseModel):
    """Run information response"""

    id: str
    state: str
    safety_profile: str
    run_scope: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    tokens_used: int
    ci_runs_used: int
    minor_issues_count: int
    major_issues_count: int
    promotion_eligible_to_main: str
    debt_status: Optional[str]
    failure_reason: Optional[str]
    tiers: List[TierResponse] = Field(default_factory=list)
    # Some runs (e.g. patch-scoped or legacy) may not have Tier rows populated.
    # Include a top-level phases list so executors can still select queued work.
    phases: List[PhaseResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
