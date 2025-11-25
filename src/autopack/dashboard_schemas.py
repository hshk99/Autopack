"""Pydantic schemas for dashboard API endpoints"""

from typing import Literal, Optional

from pydantic import BaseModel


class DashboardRunStatus(BaseModel):
    """Run status for dashboard display"""

    run_id: str
    state: str
    current_tier_name: Optional[str]
    current_phase_name: Optional[str]
    current_tier_index: Optional[int]
    current_phase_index: Optional[int]
    total_tiers: int
    total_phases: int
    completed_tiers: int
    completed_phases: int
    percent_complete: float
    tiers_percent_complete: float

    # Budget info
    tokens_used: int
    token_cap: int
    token_utilization: float

    # Issue counts
    minor_issues_count: int
    major_issues_count: int

    # Quality gate (Phase 2)
    quality_level: Optional[str] = None  # "ok" | "needs_review" | "blocked"
    quality_blocked: bool = False
    quality_warnings: list[str] = []


class ProviderUsage(BaseModel):
    """Token usage for a provider"""

    provider: str
    period: str  # "day" | "week" | "month"
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cap_tokens: int
    percent_of_cap: float


class ModelUsage(BaseModel):
    """Token usage for a specific model"""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class UsageResponse(BaseModel):
    """Dashboard usage response"""

    providers: list[ProviderUsage]
    models: list[ModelUsage]


class ModelMapping(BaseModel):
    """Current model mapping"""

    role: str  # builder / auditor
    category: str
    complexity: str
    model: str
    scope: str  # "global" or "run"


class ModelOverrideRequest(BaseModel):
    """Request to override model mapping"""

    role: str
    category: str
    complexity: str
    model: str
    scope: Literal["global", "run"]
    run_id: Optional[str] = None


class HumanNoteRequest(BaseModel):
    """Request to add human note"""

    note: str
    run_id: Optional[str] = None
