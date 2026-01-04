"""
Intention Anchor schema (canonical, versioned intent representation).

Intention behind it: a single artifact that prevents goal drift by being
referenced at every decision point (plan → build → audit → SOT → retrieve).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IntentionConstraints(BaseModel):
    """Hard requirements and preferences for the run."""

    model_config = ConfigDict(extra="forbid")

    must: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)


class IntentionScope(BaseModel):
    """Allowed and disallowed paths for the run."""

    model_config = ConfigDict(extra="forbid")

    allowed_paths: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


class IntentionBudgets(BaseModel):
    """Token/character budgets for context and SOT retrieval."""

    model_config = ConfigDict(extra="forbid")

    max_context_chars: int = 100_000
    max_sot_chars: int = 4_000


class IntentionRiskProfile(BaseModel):
    """Safety settings and protected paths for the run."""

    model_config = ConfigDict(extra="forbid")

    safety_profile: Literal["normal", "strict"] = "normal"
    protected_paths: list[str] = Field(default_factory=list)


class IntentionAnchor(BaseModel):
    """
    Canonical, versioned intent representation for a run.

    Intention behind it: a single artifact that prevents goal drift by being
    referenced at every decision point (plan → build → audit → SOT → retrieve).

    Schema strictness: all models use `extra="forbid"` to catch unintended fields.
    """

    model_config = ConfigDict(extra="forbid")

    anchor_id: str
    run_id: str
    project_id: str
    created_at: datetime
    updated_at: datetime
    version: int = 1

    north_star: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: IntentionConstraints = Field(default_factory=IntentionConstraints)
    scope: IntentionScope = Field(default_factory=IntentionScope)
    budgets: IntentionBudgets = Field(default_factory=IntentionBudgets)
    risk_profile: IntentionRiskProfile = Field(
        default_factory=IntentionRiskProfile
    )
