"""Runtime validators for IntentionAnchor fields.

Provides validation utilities for safe field access at consumption time,
ensuring that code doesn't assume fields exist without null checks.
"""

from typing import Optional, Any
from functools import wraps
import logging

logger = logging.getLogger(__name__)


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
    allowing safe access patterns in consuming code.
    """

    REQUIRED_FIELDS = ["pivot_intentions"]
    OPTIONAL_FIELDS = ["project_id", "created_at", "updated_at", "raw_input_digest", "metadata"]

    @classmethod
    def validate(cls, anchor: Any) -> tuple[bool, list[str]]:
        """Validate anchor, return (is_valid, error_messages).

        Args:
            anchor: The anchor object to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        if anchor is None:
            return False, ["Anchor is None"]

        for field in cls.REQUIRED_FIELDS:
            if getattr(anchor, field, None) is None:
                errors.append(f"Required field '{field}' is None")

        return len(errors) == 0, errors

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
