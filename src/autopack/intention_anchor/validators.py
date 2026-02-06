"""Runtime validators for IntentionAnchor fields.

Provides validation utilities for safe field access at consumption time,
ensuring that code doesn't assume fields exist without null checks.

IMP-SCHEMA-012: Added schema validation at consumption time.
- Validates anchors against JSON schema, not just field existence
- Validates nested structures (pivot_intentions)
- Returns detailed validation results with errors and paths
"""

import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, List, Optional

from ..schema_validation import SchemaValidationError, validate_intention_anchor_v2

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Detailed validation result for anchor consumption.

    Provides structured information about validation success/failure,
    including specific error messages and JSON paths where issues occurred.
    """

    valid: bool
    errors: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    schema_validated: bool = False

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

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        """Merge another validation result into this one.

        Args:
            other: Another ValidationResult to merge

        Returns:
            Self for chaining
        """
        self.valid = self.valid and other.valid
        self.errors.extend(other.errors)
        self.paths.extend(other.paths)
        # Propagate schema_validated flag
        self.schema_validated = self.schema_validated or other.schema_validated
        return self


def safe_anchor_access(field: str, default: Any = None):
    """Decorator to safely access anchor fields with default.

    Args:
        field: Field name to access on anchor
        default: Default value if field is missing or None

    Returns:
        Decorator function
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            anchor = getattr(self, "anchor", None) or kwargs.get("anchor")
            if anchor is None:
                return default

            value = getattr(anchor, field, None)
            if value is None:
                return default

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


def validate_anchor_field(anchor: Any, field: str, required: bool = False) -> Optional[Any]:
    """Validate and return anchor field, raising if required but missing.

    Args:
        anchor: The anchor object to validate
        field: Field name to access
        required: If True, raises ValueError if field is missing

    Returns:
        Field value or None

    Raises:
        ValueError: If field is required but missing or None
    """
    if anchor is None:
        if required:
            raise ValueError(f"Anchor is None, cannot access {field}")
        return None

    value = getattr(anchor, field, None)
    if value is None and required:
        raise ValueError(f"Required anchor field '{field}' is None")

    return value


class AnchorValidator:
    """Validates IntentionAnchor at consumption time.

    Checks that required fields are present and non-None,
    validates against JSON schema, and performs nested structure validation.

    IMP-SCHEMA-012: Enhanced to validate against schema at consumption time,
    not just field existence. Validates pivot_intentions structure and
    returns detailed validation results.
    """

    REQUIRED_FIELDS = ["pivot_intentions"]
    OPTIONAL_FIELDS = ["project_id", "created_at", "updated_at", "raw_input_digest", "metadata"]

    # Pivot intention types that require trigger_conditions when present
    PIVOTS_REQUIRING_CONDITIONS = ["safety_risk", "evidence_verification", "governance_review"]

    @classmethod
    def validate(cls, anchor: Any) -> tuple[bool, list[str]]:
        """Validate anchor, return (is_valid, error_messages).

        This is the legacy validation method for backwards compatibility.
        For detailed validation including schema, use validate_for_consumption().

        Args:
            anchor: The anchor object to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        result = cls.validate_for_consumption(anchor)
        return result.valid, result.errors

    @classmethod
    def validate_for_consumption(cls, anchor: Any) -> ValidationResult:
        """Validate anchor for consumption with schema validation.

        Performs comprehensive validation including:
        1. Null checks for anchor and required fields
        2. JSON schema validation against intention_anchor_v2.schema.json
        3. Nested structure validation for pivot_intentions

        Args:
            anchor: The anchor object to validate

        Returns:
            ValidationResult with detailed error information
        """
        result = ValidationResult(valid=True)

        # Check anchor is not None
        if anchor is None:
            result.add_error("Anchor is None", "$")
            return result

        # Check required fields exist
        for field_name in cls.REQUIRED_FIELDS:
            if getattr(anchor, field_name, None) is None:
                result.add_error(f"Required field '{field_name}' is None", f"$.{field_name}")

        # Early return if basic validation fails
        if not result.valid:
            return result

        # Perform schema validation
        schema_result = cls._validate_against_schema(anchor)
        result.merge(schema_result)

        # Validate nested structures
        nested_result = cls._validate_nested_structures(anchor)
        result.merge(nested_result)

        return result

    @classmethod
    def _validate_against_schema(cls, anchor: Any) -> ValidationResult:
        """Validate anchor against JSON schema.

        Args:
            anchor: The anchor object to validate

        Returns:
            ValidationResult with schema validation errors
        """
        result = ValidationResult(valid=True)

        try:
            # Convert to JSON dict for schema validation
            if hasattr(anchor, "to_json_dict"):
                anchor_dict = anchor.to_json_dict()
            elif hasattr(anchor, "model_dump"):
                anchor_dict = anchor.model_dump(mode="json", exclude_none=True)
            else:
                result.add_error("Anchor does not have to_json_dict or model_dump method", "$")
                return result

            # Validate against schema
            validate_intention_anchor_v2(anchor_dict)
            result.schema_validated = True
            logger.debug("Anchor schema validation passed")

        except SchemaValidationError as e:
            result.add_error(f"Schema validation failed: {e}", "$")
            for error in e.errors:
                result.add_error(error, "$")
            logger.warning(f"Anchor schema validation failed: {e}")

        except Exception as e:
            result.add_error(f"Unexpected error during schema validation: {e}", "$")
            logger.error(f"Unexpected schema validation error: {e}")

        return result

    @classmethod
    def _validate_nested_structures(cls, anchor: Any) -> ValidationResult:
        """Validate nested structures within the anchor.

        Validates pivot_intentions and their internal structure.

        Args:
            anchor: The anchor object to validate

        Returns:
            ValidationResult with nested structure validation errors
        """
        result = ValidationResult(valid=True)

        pivot_intentions = getattr(anchor, "pivot_intentions", None)
        if pivot_intentions is None:
            # Already caught by required field check
            return result

        # Validate each pivot intention that is present
        pivot_types = [
            "north_star",
            "safety_risk",
            "evidence_verification",
            "scope_boundaries",
            "budget_cost",
            "memory_continuity",
            "governance_review",
            "parallelism_isolation",
            "deployment",
        ]

        for pivot_type in pivot_types:
            pivot = getattr(pivot_intentions, pivot_type, None)
            if pivot is not None:
                pivot_result = cls._validate_pivot_intention(pivot, pivot_type)
                result.merge(pivot_result)

        return result

    @classmethod
    def _validate_pivot_intention(cls, pivot: Any, pivot_type: str) -> ValidationResult:
        """Validate a specific pivot intention.

        Args:
            pivot: The pivot intention object
            pivot_type: Name of the pivot type (e.g., 'north_star')

        Returns:
            ValidationResult for this pivot
        """
        result = ValidationResult(valid=True)
        path = f"$.pivot_intentions.{pivot_type}"

        # Validate safety_risk structure
        if pivot_type == "safety_risk":
            never_allow = getattr(pivot, "never_allow", None)
            if never_allow is not None and not isinstance(never_allow, list):
                result.add_error(
                    f"safety_risk.never_allow must be a list, got {type(never_allow).__name__}",
                    f"{path}.never_allow",
                )

            requires_approval = getattr(pivot, "requires_approval", None)
            if requires_approval is not None and not isinstance(requires_approval, list):
                result.add_error(
                    f"safety_risk.requires_approval must be a list, got {type(requires_approval).__name__}",
                    f"{path}.requires_approval",
                )

            risk_tolerance = getattr(pivot, "risk_tolerance", None)
            if risk_tolerance is not None:
                valid_tolerances = ["minimal", "low", "moderate", "high"]
                if risk_tolerance not in valid_tolerances:
                    result.add_error(
                        f"safety_risk.risk_tolerance must be one of {valid_tolerances}, got '{risk_tolerance}'",
                        f"{path}.risk_tolerance",
                    )

        # Validate evidence_verification structure
        elif pivot_type == "evidence_verification":
            hard_blocks = getattr(pivot, "hard_blocks", None)
            if hard_blocks is not None and not isinstance(hard_blocks, list):
                result.add_error(
                    f"evidence_verification.hard_blocks must be a list, got {type(hard_blocks).__name__}",
                    f"{path}.hard_blocks",
                )

            required_proofs = getattr(pivot, "required_proofs", None)
            if required_proofs is not None and not isinstance(required_proofs, list):
                result.add_error(
                    f"evidence_verification.required_proofs must be a list, got {type(required_proofs).__name__}",
                    f"{path}.required_proofs",
                )

        # Validate governance_review structure
        elif pivot_type == "governance_review":
            default_policy = getattr(pivot, "default_policy", None)
            if default_policy is not None:
                valid_policies = ["deny", "allow"]
                if default_policy not in valid_policies:
                    result.add_error(
                        f"governance_review.default_policy must be one of {valid_policies}, got '{default_policy}'",
                        f"{path}.default_policy",
                    )

            auto_approve_rules = getattr(pivot, "auto_approve_rules", None)
            if auto_approve_rules is not None:
                if not isinstance(auto_approve_rules, list):
                    result.add_error(
                        f"governance_review.auto_approve_rules must be a list, got {type(auto_approve_rules).__name__}",
                        f"{path}.auto_approve_rules",
                    )
                else:
                    # Validate each auto-approve rule
                    for i, rule in enumerate(auto_approve_rules):
                        rule_result = cls._validate_auto_approve_rule(
                            rule, f"{path}.auto_approve_rules[{i}]"
                        )
                        result.merge(rule_result)

        # Validate budget_cost structure
        elif pivot_type == "budget_cost":
            cost_escalation_policy = getattr(pivot, "cost_escalation_policy", None)
            if cost_escalation_policy is not None:
                valid_policies = ["block", "warn", "request_approval"]
                if cost_escalation_policy not in valid_policies:
                    result.add_error(
                        f"budget_cost.cost_escalation_policy must be one of {valid_policies}, got '{cost_escalation_policy}'",
                        f"{path}.cost_escalation_policy",
                    )

            # Validate numeric fields are non-negative
            for num_field in ["token_cap_global", "token_cap_per_call", "time_cap_seconds"]:
                value = getattr(pivot, num_field, None)
                if value is not None and isinstance(value, (int, float)) and value < 0:
                    result.add_error(
                        f"budget_cost.{num_field} must be non-negative, got {value}",
                        f"{path}.{num_field}",
                    )

        # Validate parallelism_isolation structure
        elif pivot_type == "parallelism_isolation":
            isolation_model = getattr(pivot, "isolation_model", None)
            if isolation_model is not None:
                valid_models = ["four_layer", "none"]
                if isolation_model not in valid_models:
                    result.add_error(
                        f"parallelism_isolation.isolation_model must be one of {valid_models}, got '{isolation_model}'",
                        f"{path}.isolation_model",
                    )

            max_concurrent = getattr(pivot, "max_concurrent_runs", None)
            if (
                max_concurrent is not None
                and isinstance(max_concurrent, int)
                and max_concurrent < 1
            ):
                result.add_error(
                    f"parallelism_isolation.max_concurrent_runs must be >= 1, got {max_concurrent}",
                    f"{path}.max_concurrent_runs",
                )

        return result

    @classmethod
    def _validate_auto_approve_rule(cls, rule: Any, path: str) -> ValidationResult:
        """Validate an auto-approve rule structure.

        Args:
            rule: The auto-approve rule object
            path: JSON path for error reporting

        Returns:
            ValidationResult for this rule
        """
        result = ValidationResult(valid=True)

        # Check required fields
        rule_id = (
            getattr(rule, "rule_id", None)
            if hasattr(rule, "rule_id")
            else rule.get("rule_id") if isinstance(rule, dict) else None
        )
        if not rule_id:
            result.add_error("auto_approve_rule missing required field 'rule_id'", path)

        description = (
            getattr(rule, "description", None)
            if hasattr(rule, "description")
            else rule.get("description") if isinstance(rule, dict) else None
        )
        if not description:
            result.add_error("auto_approve_rule missing required field 'description'", path)

        conditions = (
            getattr(rule, "conditions", None)
            if hasattr(rule, "conditions")
            else rule.get("conditions") if isinstance(rule, dict) else None
        )
        if conditions is None:
            result.add_error("auto_approve_rule missing required field 'conditions'", path)
        elif not isinstance(conditions, list):
            result.add_error(
                f"auto_approve_rule.conditions must be a list, got {type(conditions).__name__}",
                f"{path}.conditions",
            )

        return result

    @classmethod
    def validate_pivot_intentions(
        cls, anchor: Any, pivot_type: str, required: bool = False
    ) -> Optional[Any]:
        """Validate specific pivot intention type.

        Args:
            anchor: The anchor object
            pivot_type: Name of pivot intention type (e.g., 'north_star', 'safety_risk')
            required: If True, raises ValueError if pivot is missing

        Returns:
            Pivot intention object or None

        Raises:
            ValueError: If pivot is required but missing
        """
        if anchor is None:
            if required:
                raise ValueError(f"Anchor is None, cannot access pivot {pivot_type}")
            return None

        pivot_intentions = getattr(anchor, "pivot_intentions", None)
        if pivot_intentions is None:
            if required:
                raise ValueError(f"pivot_intentions is None, cannot access {pivot_type}")
            return None

        pivot = getattr(pivot_intentions, pivot_type, None)
        if pivot is None and required:
            raise ValueError(f"Required pivot intention '{pivot_type}' is None")

        return pivot
