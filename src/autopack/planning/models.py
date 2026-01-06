"""Plan proposal models (Pydantic-based, validates against plan_proposal_v1.schema.json)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schema_validation import validate_plan_proposal_v1, SchemaValidationError


class EstimatedCost(BaseModel):
    """Estimated cost for an action."""

    model_config = ConfigDict(extra="forbid")

    tokens: Optional[int] = Field(default=None, ge=0)
    time_seconds: Optional[int] = Field(default=None, ge=0)
    api_calls: Optional[int] = Field(default=None, ge=0)


class Action(BaseModel):
    """A proposed action to remediate gaps."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_type: Literal[
        "tidy_apply",
        "test_fix",
        "doc_update",
        "baseline_refresh",
        "config_update",
        "dependency_install",
        "file_move",
        "file_delete",
        "git_operation",
        "custom",
    ]
    title: Optional[str] = None
    description: Optional[str] = None
    target_gap_ids: List[str]
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_factors: List[str] = Field(default_factory=list)
    approval_status: Literal["auto_approved", "requires_approval", "blocked"]
    approval_reason: Optional[str] = None
    target_paths: List[str] = Field(default_factory=list)
    command: Optional[str] = None
    estimated_cost: Optional[EstimatedCost] = None
    dependencies: List[str] = Field(default_factory=list)
    rollback_strategy: Optional[str] = None


class PlanSummary(BaseModel):
    """Summary statistics for plan proposal."""

    model_config = ConfigDict(extra="forbid")

    total_actions: int = 0
    auto_approved_actions: int = 0
    requires_approval_actions: int = 0
    blocked_actions: int = 0
    total_estimated_tokens: Optional[int] = Field(default=None, ge=0)
    total_estimated_time_seconds: Optional[int] = Field(default=None, ge=0)


class ProtectedPathCheck(BaseModel):
    """Protected path check result."""

    model_config = ConfigDict(extra="forbid")

    path: str
    is_protected: bool
    action_id: str


class BudgetCompliance(BaseModel):
    """Budget compliance check result."""

    model_config = ConfigDict(extra="forbid")

    within_global_cap: bool
    within_per_call_cap: bool
    estimated_usage_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GovernanceChecks(BaseModel):
    """Governance checks applied to plan."""

    model_config = ConfigDict(extra="forbid")

    default_deny_applied: bool
    never_auto_approve_violations: List[str] = Field(default_factory=list)
    protected_path_checks: List[ProtectedPathCheck] = Field(default_factory=list)
    budget_compliance: Optional[BudgetCompliance] = None


class PlanMetadata(BaseModel):
    """Optional metadata for plan proposal."""

    model_config = ConfigDict(extra="forbid")

    proposer_version: Optional[str] = None
    generation_duration_ms: Optional[int] = None


class PlanProposalV1(BaseModel):
    """Plan Proposal v1: Gap-to-action mapping with governance.

    This model captures proposed actions to remediate gaps,
    with risk scoring, approval status, and governance checks.

    All artifacts validate against docs/schemas/plan_proposal_v1.schema.json.
    """

    model_config = ConfigDict(extra="forbid")

    format_version: Literal["v1"] = "v1"
    project_id: str
    run_id: str
    generated_at: datetime
    anchor_id: str
    gap_report_id: Optional[str] = None
    actions: List[Action] = Field(default_factory=list)
    summary: Optional[PlanSummary] = None
    governance_checks: Optional[GovernanceChecks] = None
    metadata: Optional[PlanMetadata] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with ISO datetime formatting.

        Returns:
            Dictionary ready for JSON serialization
        """
        data = self.model_dump(mode="json", exclude_none=True)
        # Ensure datetimes are ISO strings
        if isinstance(data.get("generated_at"), datetime):
            data["generated_at"] = data["generated_at"].isoformat()
        return data

    def validate_against_schema(self) -> None:
        """Validate this proposal against the JSON schema.

        Raises:
            SchemaValidationError: If validation fails
        """
        data = self.to_json_dict()
        validate_plan_proposal_v1(data)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> PlanProposalV1:
        """Create PlanProposalV1 from JSON dict.

        Args:
            data: JSON dictionary

        Returns:
            PlanProposalV1 instance

        Raises:
            SchemaValidationError: If data doesn't match schema
        """
        # Validate first
        validate_plan_proposal_v1(data)
        return cls.model_validate(data)

    def save_to_file(self, path: Path) -> None:
        """Save plan proposal to JSON file.

        Args:
            path: Path to save to
        """
        self.validate_against_schema()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_json_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: Path) -> PlanProposalV1:
        """Load plan proposal from JSON file.

        Args:
            path: Path to load from

        Returns:
            PlanProposalV1 instance
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_json_dict(data)
