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
from dataclasses import dataclass, field
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


@dataclass
class BootstrapValidationResult:
    """Result of bootstrap output validation.

    Provides detailed information about validation status including:
    - Whether the anchor passed all validation gates
    - Specific errors encountered during validation
    - JSON paths where errors occurred
    - Whether schema validation was performed
    """

    valid: bool
    errors: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    schema_validated: bool = False
    anchor: Optional[IntentionAnchorV2] = None

    def add_error(self, message: str, path: Optional[str] = None) -> None:
        """Add an error to the validation result.

        Args:
            message: Error message
            path: Optional JSON path where error occurred
        """
        self.errors.append(message)
        if path:
            self.paths.append(path)
        self.valid = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of the validation result
        """
        return {
            "valid": self.valid,
            "errors": self.errors,
            "paths": self.paths,
            "schema_validated": self.schema_validated,
        }


@dataclass
class BootstrapOutputValidator:
    """Validates bootstrap output (IntentionAnchorV2) before acceptance.

    IMP-BOOTSTRAP-002: This validator provides a validation gate that ensures
    the anchor structure is valid before it can be accepted by the bootstrap
    pipeline. This prevents invalid anchors from being written to disk or
    used downstream.

    Validation checks performed:
    1. Null checks - anchor and required fields must not be None
    2. Schema validation - validates against intention_anchor_v2.schema.json
    3. Structural validation - validates nested structures (pivot_intentions)
    4. Minimum viable anchor - validates critical fields for bootstrap completion

    Usage:
        validator = BootstrapOutputValidator()
        result = validator.validate(anchor)
        if not result.valid:
            for error in result.errors:
                print(f"Validation error: {error}")
    """

    strict_mode: bool = True  # If True, all schema errors are fatal

    def validate(self, anchor: Optional[IntentionAnchorV2]) -> BootstrapValidationResult:
        """Validate an anchor before acceptance.

        This is the main validation gate for bootstrap output. It performs
        comprehensive validation including schema, structural, and business
        rule checks.

        Args:
            anchor: The IntentionAnchorV2 to validate

        Returns:
            BootstrapValidationResult with validation status and any errors
        """
        result = BootstrapValidationResult(valid=True, anchor=anchor)

        # Gate 1: Null check
        if anchor is None:
            result.add_error("Bootstrap output anchor is None", "$")
            return result

        # Gate 2: Required field checks
        self._validate_required_fields(anchor, result)
        if not result.valid and self.strict_mode:
            return result

        # Gate 3: Schema validation
        self._validate_schema(anchor, result)
        if not result.valid and self.strict_mode:
            return result

        # Gate 4: Structural validation (pivot_intentions)
        self._validate_structure(anchor, result)
        if not result.valid and self.strict_mode:
            return result

        # Gate 5: Minimum viable anchor check (for bootstrap completion)
        self._validate_minimum_viable(anchor, result)

        return result

    def validate_or_raise(self, anchor: Optional[IntentionAnchorV2]) -> IntentionAnchorV2:
        """Validate anchor and raise if invalid.

        Convenience method that validates and raises a descriptive error
        if validation fails.

        Args:
            anchor: The IntentionAnchorV2 to validate

        Returns:
            The validated anchor (same as input)

        Raises:
            ValueError: If validation fails, with detailed error message
        """
        result = self.validate(anchor)
        if not result.valid:
            error_summary = "; ".join(result.errors[:5])
            if len(result.errors) > 5:
                error_summary += f" (+{len(result.errors) - 5} more errors)"
            raise ValueError(f"Bootstrap output validation failed: {error_summary}")
        return anchor  # type: ignore

    def _validate_required_fields(
        self, anchor: IntentionAnchorV2, result: BootstrapValidationResult
    ) -> None:
        """Validate required fields are present.

        Args:
            anchor: The anchor to validate
            result: Result object to add errors to
        """
        # Check format_version
        if anchor.format_version != "v2":
            result.add_error(
                f"Invalid format_version: expected 'v2', got '{anchor.format_version}'",
                "$.format_version",
            )

        # Check project_id
        if not anchor.project_id or not anchor.project_id.strip():
            result.add_error("project_id is required and cannot be empty", "$.project_id")

        # Check created_at
        if anchor.created_at is None:
            result.add_error("created_at is required", "$.created_at")

        # Check raw_input_digest
        if not anchor.raw_input_digest or not anchor.raw_input_digest.strip():
            result.add_error(
                "raw_input_digest is required and cannot be empty",
                "$.raw_input_digest",
            )

        # Check pivot_intentions exists
        if anchor.pivot_intentions is None:
            result.add_error("pivot_intentions is required", "$.pivot_intentions")

    def _validate_schema(
        self, anchor: IntentionAnchorV2, result: BootstrapValidationResult
    ) -> None:
        """Validate anchor against JSON schema.

        Args:
            anchor: The anchor to validate
            result: Result object to add errors to
        """
        from ..schema_validation import SchemaValidationError, validate_intention_anchor_v2

        try:
            anchor_dict = anchor.to_json_dict()
            validate_intention_anchor_v2(anchor_dict)
            result.schema_validated = True
            logger.debug("[BootstrapOutputValidator] Schema validation passed")
        except SchemaValidationError as e:
            result.add_error(f"Schema validation failed: {e}", "$")
            for error in e.errors:
                result.add_error(error, "$")
            logger.warning(f"[BootstrapOutputValidator] Schema validation failed: {e}")
        except Exception as e:
            result.add_error(f"Unexpected error during schema validation: {e}", "$")
            logger.error(f"[BootstrapOutputValidator] Unexpected schema validation error: {e}")

    def _validate_structure(
        self, anchor: IntentionAnchorV2, result: BootstrapValidationResult
    ) -> None:
        """Validate nested structures within the anchor.

        Args:
            anchor: The anchor to validate
            result: Result object to add errors to
        """
        if anchor.pivot_intentions is None:
            return  # Already caught in required fields

        # Validate safety_risk if present
        if anchor.pivot_intentions.safety_risk is not None:
            self._validate_safety_risk(anchor.pivot_intentions.safety_risk, result)

        # Validate evidence_verification if present
        if anchor.pivot_intentions.evidence_verification is not None:
            self._validate_evidence_verification(
                anchor.pivot_intentions.evidence_verification, result
            )

        # Validate governance_review if present
        if anchor.pivot_intentions.governance_review is not None:
            self._validate_governance_review(anchor.pivot_intentions.governance_review, result)

        # Validate budget_cost if present
        if anchor.pivot_intentions.budget_cost is not None:
            self._validate_budget_cost(anchor.pivot_intentions.budget_cost, result)

    def _validate_safety_risk(
        self, safety_risk: SafetyRiskIntention, result: BootstrapValidationResult
    ) -> None:
        """Validate safety_risk structure.

        Args:
            safety_risk: The safety_risk intention to validate
            result: Result object to add errors to
        """
        valid_tolerances = ["minimal", "low", "moderate", "high"]
        if safety_risk.risk_tolerance not in valid_tolerances:
            result.add_error(
                f"safety_risk.risk_tolerance must be one of {valid_tolerances}, "
                f"got '{safety_risk.risk_tolerance}'",
                "$.pivot_intentions.safety_risk.risk_tolerance",
            )

    def _validate_evidence_verification(
        self, evidence: EvidenceVerificationIntention, result: BootstrapValidationResult
    ) -> None:
        """Validate evidence_verification structure.

        Args:
            evidence: The evidence_verification intention to validate
            result: Result object to add errors to
        """
        # Validate that hard_blocks, required_proofs, verification_gates are lists
        if not isinstance(evidence.hard_blocks, list):
            result.add_error(
                f"evidence_verification.hard_blocks must be a list, "
                f"got {type(evidence.hard_blocks).__name__}",
                "$.pivot_intentions.evidence_verification.hard_blocks",
            )
        if not isinstance(evidence.required_proofs, list):
            result.add_error(
                f"evidence_verification.required_proofs must be a list, "
                f"got {type(evidence.required_proofs).__name__}",
                "$.pivot_intentions.evidence_verification.required_proofs",
            )

    def _validate_governance_review(
        self, governance: GovernanceReviewIntention, result: BootstrapValidationResult
    ) -> None:
        """Validate governance_review structure.

        Args:
            governance: The governance_review intention to validate
            result: Result object to add errors to
        """
        valid_policies = ["deny", "allow"]
        if governance.default_policy not in valid_policies:
            result.add_error(
                f"governance_review.default_policy must be one of {valid_policies}, "
                f"got '{governance.default_policy}'",
                "$.pivot_intentions.governance_review.default_policy",
            )

        # Validate auto_approve_rules structure
        for i, rule in enumerate(governance.auto_approve_rules):
            if not rule.rule_id:
                result.add_error(
                    f"auto_approve_rules[{i}].rule_id is required",
                    f"$.pivot_intentions.governance_review.auto_approve_rules[{i}].rule_id",
                )
            if not rule.description:
                result.add_error(
                    f"auto_approve_rules[{i}].description is required",
                    f"$.pivot_intentions.governance_review.auto_approve_rules[{i}].description",
                )

    def _validate_budget_cost(
        self, budget: BudgetCostIntention, result: BootstrapValidationResult
    ) -> None:
        """Validate budget_cost structure.

        Args:
            budget: The budget_cost intention to validate
            result: Result object to add errors to
        """
        valid_policies = ["block", "warn", "request_approval"]
        if budget.cost_escalation_policy not in valid_policies:
            result.add_error(
                f"budget_cost.cost_escalation_policy must be one of {valid_policies}, "
                f"got '{budget.cost_escalation_policy}'",
                "$.pivot_intentions.budget_cost.cost_escalation_policy",
            )

        # Validate numeric fields are non-negative if set
        if budget.token_cap_global is not None and budget.token_cap_global < 0:
            result.add_error(
                f"budget_cost.token_cap_global must be non-negative, "
                f"got {budget.token_cap_global}",
                "$.pivot_intentions.budget_cost.token_cap_global",
            )
        if budget.token_cap_per_call is not None and budget.token_cap_per_call < 0:
            result.add_error(
                f"budget_cost.token_cap_per_call must be non-negative, "
                f"got {budget.token_cap_per_call}",
                "$.pivot_intentions.budget_cost.token_cap_per_call",
            )
        if budget.time_cap_seconds is not None and budget.time_cap_seconds < 0:
            result.add_error(
                f"budget_cost.time_cap_seconds must be non-negative, "
                f"got {budget.time_cap_seconds}",
                "$.pivot_intentions.budget_cost.time_cap_seconds",
            )

    def _validate_minimum_viable(
        self, anchor: IntentionAnchorV2, result: BootstrapValidationResult
    ) -> None:
        """Validate minimum viable anchor for bootstrap completion.

        A minimum viable anchor for bootstrap completion must have:
        - At least one pivot intention defined

        Args:
            anchor: The anchor to validate
            result: Result object to add errors to
        """
        if anchor.pivot_intentions is None:
            return  # Already caught in required fields

        # Check at least one pivot is defined
        pivots = anchor.pivot_intentions
        has_any_pivot = any(
            [
                pivots.north_star is not None,
                pivots.safety_risk is not None,
                pivots.evidence_verification is not None,
                pivots.scope_boundaries is not None,
                pivots.budget_cost is not None,
                pivots.memory_continuity is not None,
                pivots.governance_review is not None,
                pivots.parallelism_isolation is not None,
                pivots.deployment is not None,
            ]
        )

        if not has_any_pivot:
            result.add_error(
                "Bootstrap anchor must have at least one pivot intention defined",
                "$.pivot_intentions",
            )
