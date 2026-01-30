"""Intention Anchor v2: Universal pivot intentions model.

Phase 1 of Pivot Intentions → Gap Taxonomy → Autonomy Loop plan.

Key differences from v1:
- Universal pivot intention types (works for any project)
- Explicit safety/risk, evidence/verification, governance/review sections
- Optional parallelism/isolation policy
- Designed for deterministic-first approach
- Schema-validated artifacts (validates against docs/schemas/intention_anchor_v2.schema.json)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..schema_validation import validate_intention_anchor_v2

logger = logging.getLogger(__name__)


class NorthStarIntention(BaseModel):
    """Desired outcomes, success signals, non-goals."""

    model_config = ConfigDict(extra="forbid")

    desired_outcomes: List[str] = Field(default_factory=list)
    success_signals: List[str] = Field(default_factory=list)
    non_goals: List[str] = Field(default_factory=list)


class SafetyRiskIntention(BaseModel):
    """What must never happen; what requires approval."""

    model_config = ConfigDict(extra="forbid")

    never_allow: List[str] = Field(default_factory=list)
    requires_approval: List[str] = Field(default_factory=list)
    risk_tolerance: Literal["minimal", "low", "moderate", "high"] = "low"


class EvidenceVerificationIntention(BaseModel):
    """Hard blocks, required checks, proof artifacts."""

    model_config = ConfigDict(extra="forbid")

    hard_blocks: List[str] = Field(default_factory=list)
    required_proofs: List[str] = Field(default_factory=list)
    verification_gates: List[str] = Field(default_factory=list)


class ScopeBoundariesIntention(BaseModel):
    """Allowed write roots, protected paths, network allowlist."""

    model_config = ConfigDict(extra="forbid")

    allowed_write_roots: List[str] = Field(default_factory=list)
    protected_paths: List[str] = Field(default_factory=list)
    network_allowlist: List[str] = Field(default_factory=list)


class BudgetCostIntention(BaseModel):
    """Token/time caps, cost escalation policy."""

    model_config = ConfigDict(extra="forbid")

    token_cap_global: Optional[int] = Field(default=None, ge=0)
    token_cap_per_call: Optional[int] = Field(default=None, ge=0)
    time_cap_seconds: Optional[int] = Field(default=None, ge=0)
    cost_escalation_policy: Literal["block", "warn", "request_approval"] = "request_approval"


class MemoryContinuityIntention(BaseModel):
    """What persists to SOT, derived indexes, retention rules."""

    model_config = ConfigDict(extra="forbid")

    persist_to_sot: List[str] = Field(default_factory=list)
    derived_indexes: List[str] = Field(default_factory=list)
    retention_rules: Dict[str, str] = Field(default_factory=dict)


class AutoApprovalRule(BaseModel):
    """Narrow auto-approval rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str
    conditions: List[str]


class GovernanceReviewIntention(BaseModel):
    """Default-deny, auto-approval rules, approval channels."""

    model_config = ConfigDict(extra="forbid")

    default_policy: Literal["deny", "allow"] = "deny"
    auto_approve_rules: List[AutoApprovalRule] = Field(default_factory=list)
    approval_channels: List[str] = Field(default_factory=list)


class ParallelismIsolationIntention(BaseModel):
    """Parallelism isolation model requirements (optional unless enabled)."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = False
    isolation_model: Literal["four_layer", "none"] = "none"
    max_concurrent_runs: int = Field(default=1, ge=1)


class DeploymentIntention(BaseModel):
    """Deployment phase configuration and requirements."""

    model_config = ConfigDict(extra="forbid")

    hosting_requirements: List[str] = Field(default_factory=list)
    env_vars: Dict[str, str] = Field(default_factory=dict)
    secrets_config: Dict[str, Any] = Field(default_factory=dict)


class PivotIntentions(BaseModel):
    """All pivot intention types (universal)."""

    model_config = ConfigDict(extra="forbid")

    north_star: Optional[NorthStarIntention] = None
    safety_risk: Optional[SafetyRiskIntention] = None
    evidence_verification: Optional[EvidenceVerificationIntention] = None
    scope_boundaries: Optional[ScopeBoundariesIntention] = None
    budget_cost: Optional[BudgetCostIntention] = None
    memory_continuity: Optional[MemoryContinuityIntention] = None
    governance_review: Optional[GovernanceReviewIntention] = None
    parallelism_isolation: Optional[ParallelismIsolationIntention] = None
    deployment: Optional[DeploymentIntention] = None


class IntentionMetadata(BaseModel):
    """Optional metadata for tracking and auditing."""

    model_config = ConfigDict(extra="forbid")

    author: Optional[str] = None
    source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class IntentionAnchorV2(BaseModel):
    """Intention Anchor v2: Universal pivot intentions model.

    This model captures the high-level intention types that determine safe
    autonomous progress, without chasing implementation details.

    All artifacts validate against docs/schemas/intention_anchor_v2.schema.json.
    """

    model_config = ConfigDict(extra="forbid")

    format_version: Literal["v2"] = "v2"
    project_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    raw_input_digest: str
    pivot_intentions: PivotIntentions = Field(default_factory=PivotIntentions)
    metadata: Optional[IntentionMetadata] = None
    custom_pivots: Dict[str, Any] = Field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict with ISO datetime formatting.

        Returns:
            Dictionary ready for JSON serialization
        """
        data = self.model_dump(mode="json", exclude_none=True)
        # Ensure datetimes are ISO strings
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        if data.get("updated_at") and isinstance(data["updated_at"], datetime):
            data["updated_at"] = data["updated_at"].isoformat()
        return data

    def validate_against_schema(self) -> None:
        """Validate this anchor against the JSON schema.

        Raises:
            SchemaValidationError: If validation fails
        """
        data = self.to_json_dict()
        validate_intention_anchor_v2(data)

    def validate_for_phase(self, phase_type: str) -> tuple[bool, List[str]]:
        """Validate anchor is appropriate for given phase type.

        Args:
            phase_type: The phase type to validate against (e.g., 'build', 'test', 'tidy')

        Returns:
            Tuple of (is_valid, error_messages) where error_messages is empty if valid
        """
        from .phase_type_registry import PhaseTypeRegistry

        registry = PhaseTypeRegistry()
        registry.load_from_config("config/phase_type_pivots.yaml")
        return registry.validate_anchor_for_phase(self, phase_type)

    def validate_for_consumption(self) -> tuple[bool, list[str]]:
        """Validate anchor is ready for consumption at runtime.

        This performs runtime validation to ensure critical fields are present
        when the anchor is being used, not just at creation time.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        from .validators import AnchorValidator

        return AnchorValidator.validate(self)

    def get_safe(self, field: str, default: Any = None) -> Any:
        """Safely get field value with default.

        Useful for optional fields that may be None. Returns the default
        if the field doesn't exist or is None.

        Args:
            field: Field name to access
            default: Default value if field is missing or None

        Returns:
            Field value or default
        """
        return getattr(self, field, default) or default

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> IntentionAnchorV2:
        """Create IntentionAnchorV2 from JSON dict.

        Args:
            data: JSON dictionary

        Returns:
            IntentionAnchorV2 instance

        Raises:
            SchemaValidationError: If data doesn't match schema
        """
        # Validate first
        validate_intention_anchor_v2(data)
        return cls.model_validate(data)

    def save_to_file(self, path: Path) -> None:
        """Save anchor to JSON file.

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
    def load_from_file(cls, path: Path) -> IntentionAnchorV2:
        """Load anchor from JSON file.

        Args:
            path: Path to load from

        Returns:
            IntentionAnchorV2 instance
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_json_dict(data)


def create_from_inputs(
    project_id: str,
    raw_input: str,
    north_star: Optional[Dict[str, Any]] = None,
    safety_risk: Optional[Dict[str, Any]] = None,
    evidence_verification: Optional[Dict[str, Any]] = None,
    scope_boundaries: Optional[Dict[str, Any]] = None,
    budget_cost: Optional[Dict[str, Any]] = None,
    memory_continuity: Optional[Dict[str, Any]] = None,
    governance_review: Optional[Dict[str, Any]] = None,
    parallelism_isolation: Optional[Dict[str, Any]] = None,
    deployment: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> IntentionAnchorV2:
    """Create IntentionAnchorV2 from inputs (deterministic-first).

    This function merges explicit user inputs (preferred) with optional
    deterministic inference. No LLM calls required.

    Args:
        project_id: Project identifier
        raw_input: Raw unstructured input (for digest calculation)
        north_star: NorthStar intention dict
        safety_risk: SafetyRisk intention dict
        evidence_verification: EvidenceVerification intention dict
        scope_boundaries: ScopeBoundaries intention dict
        budget_cost: BudgetCost intention dict
        memory_continuity: MemoryContinuity intention dict
        governance_review: GovernanceReview intention dict
        parallelism_isolation: ParallelismIsolation intention dict
        deployment: Deployment intention dict
        metadata: Metadata dict

    Returns:
        IntentionAnchorV2 instance
    """
    # Compute raw input digest (stable, deterministic)
    raw_input_digest = hashlib.sha256(raw_input.encode("utf-8", errors="ignore")).hexdigest()[:16]

    # Create timestamp
    now = datetime.now(timezone.utc)

    # Build pivot intentions
    pivot_intentions_dict = {}
    if north_star:
        pivot_intentions_dict["north_star"] = NorthStarIntention(**north_star)
    if safety_risk:
        pivot_intentions_dict["safety_risk"] = SafetyRiskIntention(**safety_risk)
    if evidence_verification:
        pivot_intentions_dict["evidence_verification"] = EvidenceVerificationIntention(
            **evidence_verification
        )
    if scope_boundaries:
        pivot_intentions_dict["scope_boundaries"] = ScopeBoundariesIntention(**scope_boundaries)
    if budget_cost:
        pivot_intentions_dict["budget_cost"] = BudgetCostIntention(**budget_cost)
    if memory_continuity:
        pivot_intentions_dict["memory_continuity"] = MemoryContinuityIntention(**memory_continuity)
    if governance_review:
        pivot_intentions_dict["governance_review"] = GovernanceReviewIntention(**governance_review)
    if parallelism_isolation:
        pivot_intentions_dict["parallelism_isolation"] = ParallelismIsolationIntention(
            **parallelism_isolation
        )
    if deployment:
        pivot_intentions_dict["deployment"] = DeploymentIntention(**deployment)

    pivot_intentions = PivotIntentions(**pivot_intentions_dict)

    # Build metadata
    metadata_obj = IntentionMetadata(**metadata) if metadata else None

    anchor = IntentionAnchorV2(
        project_id=project_id,
        created_at=now,
        raw_input_digest=raw_input_digest,
        pivot_intentions=pivot_intentions,
        metadata=metadata_obj,
    )

    logger.info(
        f"[IntentionAnchorV2] Created anchor for project={project_id}, digest={raw_input_digest}"
    )

    return anchor


def validate_pivot_completeness(anchor: IntentionAnchorV2) -> List[str]:
    """Validate pivot completeness and return missing pivot types as questions.

    This function checks which pivot types are missing and returns a bounded
    list of clarifying questions (max 8).

    Args:
        anchor: IntentionAnchorV2 to check

    Returns:
        List of clarifying questions for missing pivots (empty if complete)
    """
    questions = []

    if not anchor.pivot_intentions.north_star:
        questions.append("What are the desired outcomes and success signals for this project?")

    if not anchor.pivot_intentions.safety_risk:
        questions.append("What operations must never be allowed, and what requires approval?")

    if not anchor.pivot_intentions.evidence_verification:
        questions.append(
            "What checks must pass (hard blocks) and what proof artifacts are required?"
        )

    if not anchor.pivot_intentions.scope_boundaries:
        questions.append("Which paths are allowed for writes, and which are protected?")

    if not anchor.pivot_intentions.budget_cost:
        questions.append("What are the token/time budget caps and cost escalation policy?")

    if not anchor.pivot_intentions.memory_continuity:
        questions.append("What should persist to SOT ledgers and what are the retention rules?")

    if not anchor.pivot_intentions.governance_review:
        questions.append(
            "What is the approval policy (default-deny vs allow) and what auto-approval rules apply?"
        )

    if not anchor.pivot_intentions.parallelism_isolation:
        questions.append("Is parallelism allowed, and if so, what isolation model is required?")

    if not anchor.pivot_intentions.deployment:
        questions.append(
            "What are the deployment requirements, environment variables, and secrets configuration?"
        )

    # Return at most 8 questions
    return questions[:8]
