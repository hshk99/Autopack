"""Pydantic schemas for dashboard API endpoints"""

from datetime import datetime
from typing import Dict, Literal, Optional

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

    # Token efficiency (BUILD-145) - optional for backwards compatibility
    token_efficiency: Optional[Dict] = None


class TokenEfficiencyStats(BaseModel):
    """Token efficiency statistics for a run (BUILD-145)"""

    run_id: str
    total_phases: int
    total_artifact_substitutions: int
    total_tokens_saved_artifacts: int
    total_budget_used: int
    total_budget_cap: int
    total_files_kept: int
    total_files_omitted: int
    semantic_mode_count: int
    lexical_mode_count: int
    avg_artifact_substitutions_per_phase: float = 0.0
    avg_tokens_saved_per_phase: float = 0.0
    budget_utilization: float = 0.0


class Phase6Stats(BaseModel):
    """Phase 6 True Autonomy feature effectiveness statistics (BUILD-146)"""

    run_id: str
    total_phases: int
    failure_hardening_triggered_count: int
    failure_patterns_detected: Dict[str, int] = {}  # {pattern_id: count}
    doctor_calls_skipped_count: int
    # BUILD-146 P3: Counterfactual estimate (NOT actual tokens saved from A/B)
    total_doctor_tokens_avoided_estimate: int
    estimate_coverage_stats: Dict[str, Dict] = {}  # {source: {count: N, total_n: N}}
    intention_context_injected_count: int
    total_intention_context_chars: int
    avg_intention_context_chars_per_phase: float = 0.0
    plan_normalization_used: bool = False


class DatabasePoolStats(BaseModel):
    """Database connection pool health metrics (IMP-DB-001)."""

    timestamp: datetime
    pool_size: int
    checked_out: int
    checked_in: int
    overflow: int
    max_overflow: int
    utilization_pct: float
    queue_size: int
    potential_leaks: list[dict]
    longest_checkout_sec: float
    avg_checkout_ms: float
    avg_checkin_ms: float
    total_checkouts: int
    total_timeouts: int


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


class DoctorStatsResponse(BaseModel):
    """Doctor usage statistics for a run"""

    run_id: str
    doctor_calls_total: int
    doctor_cheap_calls: int
    doctor_strong_calls: int
    doctor_escalations: int
    doctor_actions: Dict[str, int]  # action_type -> count
    cheap_vs_strong_ratio: float  # 0.0-1.0 (cheap calls / total calls)
    escalation_frequency: float  # 0.0-1.0 (escalations / total calls)
