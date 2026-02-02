"""Research Completeness Validator (IMP-RESEARCH-002).

This module provides validation gates to ensure research artifacts are complete
before anchor generation. Validates that required fields are present in:
- Market research results (market_size, growth_rate, etc.)
- Competitive analysis results (competitors, competitor_count, etc.)
- Technical feasibility results (feasibility_score, key_challenges, etc.)
- Synthesis output (scores, recommendation, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Blocks anchor generation
    WARNING = "warning"  # Allows anchor generation with caveats
    INFO = "info"  # Informational only


@dataclass
class ValidationIssue:
    """Represents a validation issue found during completeness check."""

    field_path: str  # e.g., "market_research.market_size"
    message: str
    severity: ValidationSeverity
    expected_type: Optional[str] = None
    actual_value: Any = None


@dataclass
class CompletenessValidationResult:
    """Result of research completeness validation."""

    is_complete: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    phase_coverage: dict[str, float] = field(default_factory=dict)
    overall_completeness_score: float = 0.0

    @property
    def has_errors(self) -> bool:
        """Check if there are any blocking errors."""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    @property
    def error_count(self) -> int:
        """Count of error-level issues."""
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of warning-level issues."""
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "is_complete": self.is_complete,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "overall_completeness_score": self.overall_completeness_score,
            "phase_coverage": self.phase_coverage,
            "issues": [
                {
                    "field_path": issue.field_path,
                    "message": issue.message,
                    "severity": issue.severity.value,
                    "expected_type": issue.expected_type,
                }
                for issue in self.issues
            ],
        }


# Required fields for each research phase
MARKET_RESEARCH_REQUIRED_FIELDS = {
    "market_size": {"type": (int, float), "description": "Estimated market size in USD"},
    "growth_rate": {"type": (int, float), "description": "Annual growth rate as decimal"},
}

MARKET_RESEARCH_RECOMMENDED_FIELDS = {
    "target_segments": {"type": list, "description": "Target market segments"},
    "tam_sam_som": {"type": dict, "description": "TAM/SAM/SOM breakdown"},
}

COMPETITIVE_ANALYSIS_REQUIRED_FIELDS = {
    "competitors": {"type": list, "description": "List of competitor profiles"},
}

COMPETITIVE_ANALYSIS_RECOMMENDED_FIELDS = {
    "differentiation_factors": {"type": list, "description": "Key differentiation factors"},
    "competitive_intensity": {"type": str, "description": "Competitive intensity assessment"},
}

TECHNICAL_FEASIBILITY_REQUIRED_FIELDS = {
    "feasibility_score": {"type": (int, float), "description": "Feasibility score (0-1)"},
}

TECHNICAL_FEASIBILITY_RECOMMENDED_FIELDS = {
    "key_challenges": {"type": list, "description": "Major technical challenges"},
    "required_technologies": {"type": list, "description": "Required technologies"},
    "estimated_effort": {"type": str, "description": "Estimated effort level"},
}

SYNTHESIS_REQUIRED_FIELDS = {
    "overall_recommendation": {"type": str, "description": "Overall recommendation"},
    "scores": {"type": dict, "description": "Aggregated scores from all phases"},
}

SYNTHESIS_RECOMMENDED_FIELDS = {
    "project_title": {"type": str, "description": "Project title"},
    "project_type": {"type": str, "description": "Project type"},
    "confidence_level": {"type": str, "description": "Confidence level"},
    "risk_assessment": {"type": str, "description": "Risk assessment"},
    "key_dependencies": {"type": list, "description": "Key dependencies"},
}

# Required fields within synthesis.scores
SYNTHESIS_SCORES_REQUIRED_FIELDS = {
    "market_attractiveness": {
        "type": (int, float),
        "description": "Market attractiveness score",
    },
    "competitive_intensity": {
        "type": (int, float),
        "description": "Competitive intensity score",
    },
    "technical_feasibility": {
        "type": (int, float),
        "description": "Technical feasibility score",
    },
    "total": {"type": (int, float), "description": "Total score"},
}


class ResearchCompletenessValidator:
    """Validates research artifacts for completeness before anchor generation.

    This validator ensures that all required fields are present in research
    artifacts before they are used for anchor generation. This prevents
    incomplete or invalid research from being transformed into anchors.

    Usage:
        validator = ResearchCompletenessValidator()
        result = validator.validate_session(bootstrap_session)
        if not result.is_complete:
            # Handle validation errors
            for issue in result.issues:
                print(f"{issue.severity.value}: {issue.field_path} - {issue.message}")
    """

    def __init__(
        self,
        strict_mode: bool = False,
        min_completeness_threshold: float = 0.7,
    ):
        """Initialize the completeness validator.

        Args:
            strict_mode: If True, treats warnings as errors
            min_completeness_threshold: Minimum completeness score (0-1) required
        """
        self.strict_mode = strict_mode
        self.min_completeness_threshold = min_completeness_threshold

    def validate_session(self, session: Any) -> CompletenessValidationResult:
        """Validate a BootstrapSession for completeness.

        Args:
            session: BootstrapSession instance to validate

        Returns:
            CompletenessValidationResult with validation status and issues
        """
        issues: list[ValidationIssue] = []
        phase_coverage: dict[str, float] = {}

        # Validate each research phase
        market_issues, market_coverage = self._validate_market_research(session)
        issues.extend(market_issues)
        phase_coverage["market_research"] = market_coverage

        competitive_issues, competitive_coverage = self._validate_competitive_analysis(session)
        issues.extend(competitive_issues)
        phase_coverage["competitive_analysis"] = competitive_coverage

        feasibility_issues, feasibility_coverage = self._validate_technical_feasibility(session)
        issues.extend(feasibility_issues)
        phase_coverage["technical_feasibility"] = feasibility_coverage

        # Validate synthesis if present
        if hasattr(session, "synthesis") and session.synthesis:
            synthesis_issues, synthesis_coverage = self._validate_synthesis(session.synthesis)
            issues.extend(synthesis_issues)
            phase_coverage["synthesis"] = synthesis_coverage
        else:
            phase_coverage["synthesis"] = 0.0

        # Calculate overall completeness score
        overall_completeness = (
            sum(phase_coverage.values()) / len(phase_coverage) if phase_coverage else 0.0
        )

        # Determine if complete
        has_blocking_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)
        has_blocking_warnings = self.strict_mode and any(
            issue.severity == ValidationSeverity.WARNING for issue in issues
        )
        meets_threshold = overall_completeness >= self.min_completeness_threshold

        is_complete = not has_blocking_errors and not has_blocking_warnings and meets_threshold

        result = CompletenessValidationResult(
            is_complete=is_complete,
            issues=issues,
            phase_coverage=phase_coverage,
            overall_completeness_score=overall_completeness,
        )

        if is_complete:
            logger.info(
                f"[CompletenessValidator] Session validation passed: "
                f"completeness={overall_completeness:.2%}"
            )
        else:
            logger.warning(
                f"[CompletenessValidator] Session validation failed: "
                f"completeness={overall_completeness:.2%}, "
                f"errors={result.error_count}, warnings={result.warning_count}"
            )

        return result

    def validate_synthesis(self, synthesis: dict[str, Any]) -> CompletenessValidationResult:
        """Validate synthesis output for completeness.

        This is a convenience method for validating just the synthesis
        without a full session.

        Args:
            synthesis: Synthesis dictionary to validate

        Returns:
            CompletenessValidationResult with validation status
        """
        issues, coverage = self._validate_synthesis(synthesis)

        is_complete = (
            not any(issue.severity == ValidationSeverity.ERROR for issue in issues)
            and coverage >= self.min_completeness_threshold
        )

        return CompletenessValidationResult(
            is_complete=is_complete,
            issues=issues,
            phase_coverage={"synthesis": coverage},
            overall_completeness_score=coverage,
        )

    def validate_before_anchor_generation(
        self,
        session: Any,
    ) -> tuple[bool, CompletenessValidationResult]:
        """Validate session before anchor generation.

        This is the main validation gate that should be called before
        mapping research to anchors.

        Args:
            session: BootstrapSession to validate

        Returns:
            Tuple of (can_proceed, validation_result)
        """
        result = self.validate_session(session)

        if not result.is_complete:
            logger.error(
                f"[CompletenessValidator] Anchor generation blocked: "
                f"research artifacts incomplete. "
                f"Errors: {result.error_count}, Warnings: {result.warning_count}"
            )

        return result.is_complete, result

    def _validate_market_research(
        self,
        session: Any,
    ) -> tuple[list[ValidationIssue], float]:
        """Validate market research phase data.

        Args:
            session: BootstrapSession with market_research attribute

        Returns:
            Tuple of (issues, coverage_score)
        """
        issues: list[ValidationIssue] = []
        total_fields = len(MARKET_RESEARCH_REQUIRED_FIELDS) + len(
            MARKET_RESEARCH_RECOMMENDED_FIELDS
        )
        present_fields = 0

        # Check if market research exists
        if not hasattr(session, "market_research") or session.market_research is None:
            issues.append(
                ValidationIssue(
                    field_path="market_research",
                    message="Market research phase is missing",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        # Check phase status
        if session.market_research.status != "completed":
            issues.append(
                ValidationIssue(
                    field_path="market_research.status",
                    message=f"Market research not completed: {session.market_research.status}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        data = session.market_research.data or {}

        # Validate required fields
        for field_name, field_config in MARKET_RESEARCH_REQUIRED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"market_research.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=True,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        # Validate recommended fields (warnings only)
        for field_name, field_config in MARKET_RESEARCH_RECOMMENDED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"market_research.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=False,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        coverage = present_fields / total_fields if total_fields > 0 else 0.0
        return issues, coverage

    def _validate_competitive_analysis(
        self,
        session: Any,
    ) -> tuple[list[ValidationIssue], float]:
        """Validate competitive analysis phase data.

        Args:
            session: BootstrapSession with competitive_analysis attribute

        Returns:
            Tuple of (issues, coverage_score)
        """
        issues: list[ValidationIssue] = []
        total_fields = len(COMPETITIVE_ANALYSIS_REQUIRED_FIELDS) + len(
            COMPETITIVE_ANALYSIS_RECOMMENDED_FIELDS
        )
        present_fields = 0

        # Check if competitive analysis exists
        if not hasattr(session, "competitive_analysis") or session.competitive_analysis is None:
            issues.append(
                ValidationIssue(
                    field_path="competitive_analysis",
                    message="Competitive analysis phase is missing",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        # Check phase status
        if session.competitive_analysis.status != "completed":
            issues.append(
                ValidationIssue(
                    field_path="competitive_analysis.status",
                    message=f"Competitive analysis not completed: {session.competitive_analysis.status}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        data = session.competitive_analysis.data or {}

        # Validate required fields
        for field_name, field_config in COMPETITIVE_ANALYSIS_REQUIRED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"competitive_analysis.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=True,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        # Additional validation: competitors list should not be empty
        if "competitors" in data and isinstance(data["competitors"], list):
            if len(data["competitors"]) == 0:
                issues.append(
                    ValidationIssue(
                        field_path="competitive_analysis.competitors",
                        message="Competitors list is empty - at least one competitor expected",
                        severity=ValidationSeverity.WARNING,
                    )
                )

        # Validate recommended fields (warnings only)
        for field_name, field_config in COMPETITIVE_ANALYSIS_RECOMMENDED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"competitive_analysis.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=False,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        coverage = present_fields / total_fields if total_fields > 0 else 0.0
        return issues, coverage

    def _validate_technical_feasibility(
        self,
        session: Any,
    ) -> tuple[list[ValidationIssue], float]:
        """Validate technical feasibility phase data.

        Args:
            session: BootstrapSession with technical_feasibility attribute

        Returns:
            Tuple of (issues, coverage_score)
        """
        issues: list[ValidationIssue] = []
        total_fields = len(TECHNICAL_FEASIBILITY_REQUIRED_FIELDS) + len(
            TECHNICAL_FEASIBILITY_RECOMMENDED_FIELDS
        )
        present_fields = 0

        # Check if technical feasibility exists
        if not hasattr(session, "technical_feasibility") or session.technical_feasibility is None:
            issues.append(
                ValidationIssue(
                    field_path="technical_feasibility",
                    message="Technical feasibility phase is missing",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        # Check phase status
        if session.technical_feasibility.status != "completed":
            issues.append(
                ValidationIssue(
                    field_path="technical_feasibility.status",
                    message=f"Technical feasibility not completed: {session.technical_feasibility.status}",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        data = session.technical_feasibility.data or {}

        # Validate required fields
        for field_name, field_config in TECHNICAL_FEASIBILITY_REQUIRED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"technical_feasibility.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=True,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        # Additional validation: feasibility_score range
        if "feasibility_score" in data:
            score = data["feasibility_score"]
            if isinstance(score, (int, float)):
                if not (0 <= score <= 1):
                    issues.append(
                        ValidationIssue(
                            field_path="technical_feasibility.feasibility_score",
                            message=f"Feasibility score {score} out of range (expected 0-1)",
                            severity=ValidationSeverity.WARNING,
                            actual_value=score,
                        )
                    )

        # Validate recommended fields (warnings only)
        for field_name, field_config in TECHNICAL_FEASIBILITY_RECOMMENDED_FIELDS.items():
            issue = self._validate_field(
                data,
                f"technical_feasibility.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=False,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        coverage = present_fields / total_fields if total_fields > 0 else 0.0
        return issues, coverage

    def _validate_synthesis(
        self,
        synthesis: dict[str, Any],
    ) -> tuple[list[ValidationIssue], float]:
        """Validate synthesis output data.

        Args:
            synthesis: Synthesis dictionary

        Returns:
            Tuple of (issues, coverage_score)
        """
        issues: list[ValidationIssue] = []
        total_fields = (
            len(SYNTHESIS_REQUIRED_FIELDS)
            + len(SYNTHESIS_RECOMMENDED_FIELDS)
            + len(SYNTHESIS_SCORES_REQUIRED_FIELDS)
        )
        present_fields = 0

        if not synthesis:
            issues.append(
                ValidationIssue(
                    field_path="synthesis",
                    message="Synthesis is empty or missing",
                    severity=ValidationSeverity.ERROR,
                )
            )
            return issues, 0.0

        # Validate required fields
        for field_name, field_config in SYNTHESIS_REQUIRED_FIELDS.items():
            issue = self._validate_field(
                synthesis,
                f"synthesis.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=True,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        # Validate recommended fields
        for field_name, field_config in SYNTHESIS_RECOMMENDED_FIELDS.items():
            issue = self._validate_field(
                synthesis,
                f"synthesis.{field_name}",
                field_name,
                field_config["type"],
                field_config["description"],
                required=False,
            )
            if issue:
                issues.append(issue)
            else:
                present_fields += 1

        # Validate scores sub-object
        scores = synthesis.get("scores", {})
        if not isinstance(scores, dict):
            issues.append(
                ValidationIssue(
                    field_path="synthesis.scores",
                    message="Scores must be a dictionary",
                    severity=ValidationSeverity.ERROR,
                    expected_type="dict",
                    actual_value=type(scores).__name__,
                )
            )
        else:
            for field_name, field_config in SYNTHESIS_SCORES_REQUIRED_FIELDS.items():
                issue = self._validate_field(
                    scores,
                    f"synthesis.scores.{field_name}",
                    field_name,
                    field_config["type"],
                    field_config["description"],
                    required=True,
                )
                if issue:
                    issues.append(issue)
                else:
                    present_fields += 1

        coverage = present_fields / total_fields if total_fields > 0 else 0.0
        return issues, coverage

    def _validate_field(
        self,
        data: dict[str, Any],
        field_path: str,
        field_name: str,
        expected_type: type | tuple,
        description: str,
        required: bool,
    ) -> Optional[ValidationIssue]:
        """Validate a single field for presence and type.

        Args:
            data: Dictionary containing the field
            field_path: Full path for error reporting
            field_name: Name of the field in the data dict
            expected_type: Expected type(s) for the field
            description: Human-readable description
            required: Whether field is required

        Returns:
            ValidationIssue if invalid, None if valid
        """
        if field_name not in data:
            return ValidationIssue(
                field_path=field_path,
                message=f"Missing {description}",
                severity=ValidationSeverity.ERROR if required else ValidationSeverity.WARNING,
                expected_type=str(expected_type),
            )

        value = data[field_name]

        # Check type
        if not isinstance(value, expected_type):
            return ValidationIssue(
                field_path=field_path,
                message=f"Invalid type for {description}: "
                f"expected {expected_type}, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR if required else ValidationSeverity.WARNING,
                expected_type=str(expected_type),
                actual_value=type(value).__name__,
            )

        return None

    def get_required_fields_summary(self) -> dict[str, list[str]]:
        """Get a summary of all required fields for documentation.

        Returns:
            Dictionary mapping phase names to lists of required field names
        """
        return {
            "market_research": list(MARKET_RESEARCH_REQUIRED_FIELDS.keys()),
            "competitive_analysis": list(COMPETITIVE_ANALYSIS_REQUIRED_FIELDS.keys()),
            "technical_feasibility": list(TECHNICAL_FEASIBILITY_REQUIRED_FIELDS.keys()),
            "synthesis": list(SYNTHESIS_REQUIRED_FIELDS.keys())
            + [f"scores.{k}" for k in SYNTHESIS_SCORES_REQUIRED_FIELDS.keys()],
        }
