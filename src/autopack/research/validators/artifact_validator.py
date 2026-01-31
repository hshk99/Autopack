"""Validation for tech stack proposal artifacts (IMP-SCHEMA-001).

Ensures tech stack proposal artifacts meet schema requirements before being
written to disk. Validates against tech_stack_proposal.schema.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """Represents a validation error in the artifact."""

    path: str  # JSON path to the error (e.g., "options[0].estimated_cost")
    message: str  # Error message
    value: Any = None  # The invalid value
    expected: Optional[str] = None  # What was expected


@dataclass
class ValidationResult:
    """Result of artifact validation."""

    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]

    @property
    def summary(self) -> str:
        """Get a human-readable summary of validation result."""
        if self.is_valid:
            if self.warnings:
                return f"Valid with {len(self.warnings)} warning(s)"
            return "Valid"
        error_count = len(self.errors)
        return f"Invalid - {error_count} error(s)"


class ArtifactValidator:
    """Validates tech stack proposal artifacts against JSON schema."""

    def __init__(self, schema_path: Optional[Path | str] = None):
        """Initialize the validator with the schema.

        Args:
            schema_path: Path to tech_stack_proposal.schema.json.
                        If None, uses default location relative to this file.
        """
        if schema_path is None:
            # Default location: src/autopack/schemas/tech_stack_proposal.schema.json
            current_dir = Path(__file__).parent
            schema_path = current_dir.parent.parent / "schemas" / "tech_stack_proposal.schema.json"

        self.schema_path = Path(schema_path)
        self._schema: Optional[Dict[str, Any]] = None
        self._load_schema()

    def _load_schema(self) -> None:
        """Load the JSON schema from file.

        Raises:
            FileNotFoundError: If schema file doesn't exist
            json.JSONDecodeError: If schema file is not valid JSON
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Tech stack proposal schema not found at {self.schema_path}")

        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema = json.load(f)
            logger.debug(f"[ArtifactValidator] Loaded schema from {self.schema_path}")
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Failed to parse schema at {self.schema_path}: {e.msg}", e.doc, e.pos
            )

    def validate(self, artifact: Dict[str, Any]) -> ValidationResult:
        """Validate a tech stack proposal artifact.

        Args:
            artifact: The artifact dict to validate (should be TechStackProposal.model_dump())

        Returns:
            ValidationResult with is_valid, errors, and warnings
        """
        if self._schema is None:
            return ValidationResult(
                is_valid=False,
                errors=[ValidationError(path="", message="Schema not loaded")],
                warnings=[],
            )

        errors: List[ValidationError] = []
        warnings: List[str] = []

        # Validate against JSON schema
        try:
            jsonschema.validate(instance=artifact, schema=self._schema)
        except jsonschema.ValidationError as e:
            # Convert jsonschema validation error to our format
            path = ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
            errors.append(
                ValidationError(
                    path=path,
                    message=e.message,
                    value=e.instance,
                    expected=e.validator,
                )
            )
        except jsonschema.SchemaError as e:
            # Schema itself is invalid
            return ValidationResult(
                is_valid=False,
                errors=[ValidationError(path="schema", message=f"Invalid schema: {e.message}")],
                warnings=[],
            )

        # Additional semantic validation
        semantic_errors, semantic_warnings = self._validate_semantics(artifact)
        errors.extend(semantic_errors)
        warnings.extend(semantic_warnings)

        is_valid = len(errors) == 0
        return ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    def _validate_semantics(
        self, artifact: Dict[str, Any]
    ) -> tuple[List[ValidationError], List[str]]:
        """Perform semantic validation beyond JSON schema.

        Args:
            artifact: The artifact to validate

        Returns:
            Tuple of (errors, warnings)
        """
        errors: List[ValidationError] = []
        warnings: List[str] = []

        # Validate options have required fields
        options = artifact.get("options", [])
        for idx, option in enumerate(options):
            # Check that each option has a name (used in recommendation)
            if not option.get("name"):
                errors.append(
                    ValidationError(
                        path=f"options[{idx}].name",
                        message="Option name cannot be empty",
                        value=None,
                    )
                )

            # Check that estimated_cost has valid values
            cost = option.get("estimated_cost", {})
            if isinstance(cost, dict):
                min_cost = cost.get("monthly_min")
                max_cost = cost.get("monthly_max")

                if isinstance(min_cost, (int, float)) and isinstance(max_cost, (int, float)):
                    if min_cost > max_cost:
                        errors.append(
                            ValidationError(
                                path=f"options[{idx}].estimated_cost",
                                message="monthly_min cannot be greater than monthly_max",
                                value={"monthly_min": min_cost, "monthly_max": max_cost},
                            )
                        )

            # Warn if option has critical ToS risks but is still recommended
            recommendation = artifact.get("recommendation")
            if recommendation == option.get("name"):
                tos_risks = option.get("tos_risks", [])
                for risk in tos_risks:
                    if risk.get("level") == "critical":
                        warnings.append(
                            f"Option '{option.get('name')}' is recommended but has "
                            f"critical ToS risks: {risk.get('description')}"
                        )

        # Validate recommendation exists in options
        recommendation = artifact.get("recommendation")
        if recommendation:
            option_names = [opt.get("name") for opt in options]
            if recommendation not in option_names:
                errors.append(
                    ValidationError(
                        path="recommendation",
                        message=f"Recommendation '{recommendation}' does not match any option name",
                        value=recommendation,
                        expected=f"One of: {option_names}",
                    )
                )

        # Validate confidence score
        confidence = artifact.get("confidence_score")
        if confidence is not None:
            if not (0.0 <= confidence <= 1.0):
                errors.append(
                    ValidationError(
                        path="confidence_score",
                        message="Confidence score must be between 0.0 and 1.0",
                        value=confidence,
                    )
                )

        return errors, warnings

    def validate_artifact_dict(self, artifact_dict: Dict[str, Any]) -> ValidationResult:
        """Validate an artifact passed as a dictionary.

        This is the main method to call for validating artifact data before writing.

        Args:
            artifact_dict: Dictionary representation of the artifact

        Returns:
            ValidationResult with validation status
        """
        return self.validate(artifact_dict)

    def validate_before_write(self, artifact: Dict[str, Any], artifact_path: Path) -> bool:
        """Validate an artifact before writing to disk.

        Logs validation results and returns success/failure.

        Args:
            artifact: The artifact to validate
            artifact_path: Path where artifact will be written (for logging)

        Returns:
            True if valid and should be written, False otherwise
        """
        result = self.validate(artifact)

        if result.is_valid:
            logger.info(f"[ArtifactValidator] Artifact validation passed for {artifact_path.name}")
            if result.warnings:
                for warning in result.warnings:
                    logger.warning(f"[ArtifactValidator] {warning}")
            return True
        else:
            logger.error(
                f"[ArtifactValidator] Artifact validation failed for {artifact_path.name}: "
                f"{len(result.errors)} error(s)"
            )
            for error in result.errors:
                logger.error(f"  - {error.path}: {error.message}")
            return False
