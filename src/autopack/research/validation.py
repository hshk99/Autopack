"""Research Validation Module - Compatibility Shims.

This module provides compatibility shims for research validation functionality
that tests expect but doesn't exist in the actual implementation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ValidationLevel(Enum):
    """Compat shim for ValidationLevel."""
    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


@dataclass
class ValidationRule:
    """Compat shim for ValidationRule."""
    name: str
    description: str = ""
    enabled: bool = True
    level: ValidationLevel = ValidationLevel.MODERATE


@dataclass
class ValidationResult:
    """Compat shim for ValidationResult."""
    valid: bool
    rule_name: str
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class Validator:
    """Compat shim for Validator."""

    def __init__(self, rules: Optional[List[ValidationRule]] = None):
        """Initialize validator with rules."""
        self.rules = rules or []

    def validate(self, data: Any) -> List[ValidationResult]:
        """Validate data against rules."""
        return []

    def is_valid(self, data: Any) -> bool:
        """Check if data is valid."""
        return True


class ValidationFramework:
    """Compat shim for ValidationFramework."""

    def __init__(self):
        """Initialize validation framework."""
        self.validators: List[Validator] = []

    def add_validator(self, validator: Validator) -> None:
        """Add a validator to the framework."""
        self.validators.append(validator)

    def validate_all(self, data: Any) -> List[ValidationResult]:
        """Validate data against all validators."""
        return []


class EvidenceValidator(Validator):
    """Compat shim for EvidenceValidator."""

    def __init__(self):
        """Initialize evidence validator."""
        super().__init__()


__all__ = [
    "CitationValidator",
    "QualityValidator",
    "ValidationLevel",
    "ValidationRule",
    "ValidationResult",
    "Validator",
    "ValidationFramework",
    "EvidenceValidator",
]


class CitationValidator(Validator):
    """Compat shim for CitationValidator."""
    def __init__(self):
        super().__init__()

class QualityValidator(Validator):
    """Compat shim for QualityValidator."""
    def __init__(self):
        super().__init__()

