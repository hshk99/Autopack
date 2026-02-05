"""JSON Schema validation for Autopack artifacts.

Minimal schema validator that checks:
- Required fields
- Field types
- Enum constraints
- Format version matching

Does NOT require jsonschema library (uses Python built-ins).
For production use, consider installing jsonschema for full validation.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


def load_schema(schema_name: str) -> Dict[str, Any]:
    """Load a JSON schema from src/autopack/schemas/.

    Args:
        schema_name: Schema filename (e.g., "intention_anchor_v2.schema.json")

    Returns:
        Parsed schema dict

    Raises:
        FileNotFoundError: If schema file not found
        json.JSONDecodeError: If schema is invalid JSON
    """
    schema_path = Path(__file__).parent.parent / "schemas" / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_type(value: Any, expected_type: str, path: str) -> List[str]:
    """Validate a value against an expected JSON schema type.

    Args:
        value: Value to validate
        expected_type: JSON schema type (string, integer, number, boolean, object, array)
        path: JSON path for error reporting

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    expected_py_type = type_map.get(expected_type)
    if expected_py_type is None:
        errors.append(f"{path}: Unknown type '{expected_type}'")
        return errors

    if not isinstance(value, expected_py_type):
        errors.append(f"{path}: Expected type '{expected_type}', got '{type(value).__name__}'")

    return errors


def validate_enum(value: Any, enum_values: List[Any], path: str) -> List[str]:
    """Validate a value against an enum constraint.

    Args:
        value: Value to validate
        enum_values: List of allowed values
        path: JSON path for error reporting

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    if value not in enum_values:
        errors.append(f"{path}: Value '{value}' not in allowed values {enum_values}")
    return errors


def validate_const(value: Any, const_value: Any, path: str) -> List[str]:
    """Validate a value against a const constraint.

    Args:
        value: Value to validate
        const_value: Expected constant value
        path: JSON path for error reporting

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    if value != const_value:
        errors.append(f"{path}: Expected constant value '{const_value}', got '{value}'")
    return errors


def validate_string_format(value: str, format_type: str, path: str) -> List[str]:
    """Validate string format constraints.

    Args:
        value: String value to validate
        format_type: Format type (date-time, etc.)
        path: JSON path for error reporting

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if format_type == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            errors.append(f"{path}: Invalid ISO 8601 date-time format: '{value}'")

    return errors


def validate_string_pattern(value: str, pattern: str, path: str) -> List[str]:
    """Validate string pattern constraints (basic regex).

    Args:
        value: String value to validate
        pattern: Regex pattern
        path: JSON path for error reporting

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    import re

    try:
        if not re.match(pattern, value):
            errors.append(f"{path}: Value '{value}' does not match pattern '{pattern}'")
    except re.error as e:
        errors.append(f"{path}: Invalid regex pattern '{pattern}': {e}")

    return errors


def validate_object(data: Dict[str, Any], schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Validate an object against a JSON schema (recursive).

    Args:
        data: Data to validate
        schema: JSON schema
        path: Current path in the object (for error reporting)

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"{path}: Missing required field '{field}'")

    # Validate properties
    properties = schema.get("properties", {})
    for field, value in data.items():
        field_path = f"{path}.{field}"
        field_schema = properties.get(field)

        if field_schema is None:
            # Unknown field - skip if additionalProperties not explicitly false
            if schema.get("additionalProperties") is False:
                errors.append(f"{field_path}: Unknown field (not in schema)")
            continue

        # Skip validation for None values on optional fields
        if value is None:
            if field not in required:
                continue
            else:
                errors.append(f"{field_path}: Required field cannot be null")
                continue

        # Validate type
        if "type" in field_schema:
            field_type = field_schema["type"]
            errors.extend(validate_type(value, field_type, field_path))

            # Type-specific validations
            if field_type == "string" and isinstance(value, str):
                # Format validation
                if "format" in field_schema:
                    errors.extend(validate_string_format(value, field_schema["format"], field_path))
                # Pattern validation
                if "pattern" in field_schema:
                    errors.extend(
                        validate_string_pattern(value, field_schema["pattern"], field_path)
                    )
                # minLength
                if "minLength" in field_schema and len(value) < field_schema["minLength"]:
                    errors.append(
                        f"{field_path}: String too short (min {field_schema['minLength']})"
                    )
                # maxLength
                if "maxLength" in field_schema and len(value) > field_schema["maxLength"]:
                    errors.append(
                        f"{field_path}: String too long (max {field_schema['maxLength']})"
                    )

            elif field_type in ("integer", "number") and isinstance(value, (int, float)):
                # Minimum
                if "minimum" in field_schema and value < field_schema["minimum"]:
                    errors.append(f"{field_path}: Value below minimum {field_schema['minimum']}")
                # Maximum
                if "maximum" in field_schema and value > field_schema["maximum"]:
                    errors.append(f"{field_path}: Value above maximum {field_schema['maximum']}")

            elif field_type == "array" and isinstance(value, list):
                # Array item validation
                if "items" in field_schema:
                    item_schema = field_schema["items"]
                    for i, item in enumerate(value):
                        item_path = f"{field_path}[{i}]"
                        if item_schema.get("type") == "object":
                            errors.extend(validate_object(item, item_schema, item_path))
                        elif "type" in item_schema:
                            errors.extend(validate_type(item, item_schema["type"], item_path))

            elif field_type == "object" and isinstance(value, dict):
                # Recursive object validation
                errors.extend(validate_object(value, field_schema, field_path))

        # Enum validation
        if "enum" in field_schema:
            errors.extend(validate_enum(value, field_schema["enum"], field_path))

        # Const validation
        if "const" in field_schema:
            errors.extend(validate_const(value, field_schema["const"], field_path))

    return errors


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any], schema_name: str) -> None:
    """Validate data against a JSON schema.

    Args:
        data: Data to validate
        schema: JSON schema
        schema_name: Schema name (for error messages)

    Raises:
        SchemaValidationError: If validation fails
    """
    if not isinstance(data, dict):
        raise SchemaValidationError(f"Data must be an object, got {type(data).__name__}")

    errors = validate_object(data, schema, "$")

    if errors:
        raise SchemaValidationError(
            f"Schema validation failed for {schema_name}: {len(errors)} error(s)", errors=errors
        )


def validate_intention_anchor_v2(data: Dict[str, Any]) -> None:
    """Validate IntentionAnchorV2 artifact.

    Args:
        data: Intention anchor data to validate

    Raises:
        SchemaValidationError: If validation fails
    """
    schema = load_schema("intention_anchor_v2.schema.json")
    validate_against_schema(data, schema, "IntentionAnchorV2")
    logger.debug("IntentionAnchorV2 validation passed")


def validate_gap_report_v1(data: Dict[str, Any]) -> None:
    """Validate GapReportV1 artifact.

    Args:
        data: Gap report data to validate

    Raises:
        SchemaValidationError: If validation fails
    """
    schema = load_schema("gap_report_v1.schema.json")
    validate_against_schema(data, schema, "GapReportV1")
    logger.debug("GapReportV1 validation passed")


def validate_plan_proposal_v1(data: Dict[str, Any]) -> None:
    """Validate PlanProposalV1 artifact.

    Args:
        data: Plan proposal data to validate

    Raises:
        SchemaValidationError: If validation fails
    """
    schema = load_schema("plan_proposal_v1.schema.json")
    validate_against_schema(data, schema, "PlanProposalV1")
    logger.debug("PlanProposalV1 validation passed")


def validate_autopilot_session_v1(data: Dict[str, Any]) -> None:
    """Validate AutopilotSessionV1 artifact.

    Args:
        data: Autopilot session data to validate

    Raises:
        SchemaValidationError: If validation fails
    """
    schema = load_schema("autopilot_session_v1.schema.json")
    validate_against_schema(data, schema, "AutopilotSessionV1")
    logger.debug("AutopilotSessionV1 validation passed")
