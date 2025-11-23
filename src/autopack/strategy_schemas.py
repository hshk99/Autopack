"""Schemas for rulesets and strategies (Chunk C implementation)

Per §7 of v7 playbook:
- Project rulesets (declarative policy)
- Project implementation strategies (compiled per-run)
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CategoryDefaults(BaseModel):
    """Default settings for a task category"""

    complexity: str = Field(default="medium", description="low, medium, or high")
    ci_profile: str = Field(default="normal", description="normal or strict")
    max_builder_attempts: int = Field(default=3)
    max_auditor_attempts: int = Field(default=2)
    incident_token_cap: int = Field(default=500_000)
    tier_token_cap_multiplier: float = Field(default=3.0)
    tier_ci_run_cap_multiplier: float = Field(default=2.0)
    tier_max_minor_issues_multiplier: float = Field(default=2.0)
    tier_max_major_issues_tolerated: int = Field(default=0)
    auto_apply: bool = Field(default=True, description="Whether to auto-apply changes")
    auditor_profile: Optional[str] = Field(None, description="Auditor profile to use")
    default_severity: str = Field(default="minor", description="Default issue severity")


class SafetyProfileConfig(BaseModel):
    """Safety profile configuration"""

    name: str = Field(..., description="normal or safety_critical")
    description: str = Field(default="")
    minor_issue_aging_runs_threshold: int = Field(default=3)
    minor_issue_aging_tiers_threshold: int = Field(default=2)
    run_scope_preference: str = Field(default="multi_tier", description="multi_tier or single_tier")


class ProjectRuleset(BaseModel):
    """Project ruleset (§7.1 of v7 playbook)"""

    version: str = Field(default="v1")
    project_id: str
    default_safety_profile: str = Field(default="normal")
    default_run_scope: str = Field(default="multi_tier")

    # Safety profiles
    safety_profiles: Dict[str, SafetyProfileConfig] = Field(default_factory=dict)

    # Category defaults (per §6 of v7 playbook)
    category_defaults: Dict[str, CategoryDefaults] = Field(default_factory=dict)

    # High-risk categories (§6)
    high_risk_categories: List[str] = Field(
        default_factory=lambda: [
            "cross_cutting_refactor",
            "index_registry_change",
            "schema_contract_change",
            "bulk_multi_file_operation",
            "security_auth_change",
        ]
    )

    # Global defaults
    run_token_cap: int = Field(default=5_000_000)
    run_max_phases: int = Field(default=25)
    run_max_duration_minutes: int = Field(default=120)


class PhaseStrategySlice(BaseModel):
    """Strategy for a single phase"""

    task_category: Optional[str]
    complexity: str
    builder_mode: Optional[str]
    max_builder_attempts: int
    max_auditor_attempts: int
    incident_token_cap: int
    ci_profile: str
    auto_apply: bool
    auditor_profile: Optional[str]


class TierStrategySlice(BaseModel):
    """Strategy for a single tier"""

    tier_id: str
    token_cap: int
    ci_run_cap: int
    max_minor_issues_tolerated: int
    max_major_issues_tolerated: int


class ProjectImplementationStrategy(BaseModel):
    """Compiled per-run strategy (§7.1 of v7 playbook)"""

    version: str = Field(default="v1")
    run_id: str
    project_id: str
    safety_profile: str
    run_scope: str

    # Run-level settings
    run_token_cap: int
    run_max_phases: int
    run_max_duration_minutes: int
    run_max_minor_issues_total: Optional[int]

    # Per-category defaults
    category_strategies: Dict[str, CategoryDefaults] = Field(default_factory=dict)

    # Per-tier budgets
    tier_strategies: Dict[str, TierStrategySlice] = Field(default_factory=dict)

    # Per-phase strategies (when phases are known)
    phase_strategies: Dict[str, PhaseStrategySlice] = Field(default_factory=dict)

    # Aging configuration
    minor_issue_aging_runs_threshold: int = Field(default=3)
    minor_issue_aging_tiers_threshold: int = Field(default=2)
