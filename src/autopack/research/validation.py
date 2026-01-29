"""Research Validation Module - Validators for research evidence and citations.

This module provides validation logic for Evidence, Citations, and ResearchReports
to ensure data quality and consistency.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from urllib.parse import urlparse

from autopack.research.models import Citation, Evidence, EvidenceQuality, ResearchReport


class ValidationLevel(Enum):
    """Validation strictness levels."""

    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


@dataclass
class ValidationRule:
    """Validation rule definition."""

    name: str
    description: str = ""
    enabled: bool = True
    level: ValidationLevel = ValidationLevel.MODERATE


@dataclass
class ValidationResult:
    """Result of validation check.

    Attributes:
        is_valid: Whether validation passed
        errors: List of error messages (validation failures)
        warnings: List of warning messages (potential issues)
        quality_score: Optional quality score (0.0-1.0)
    """

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quality_score: float = 0.0


class Validator:
    """Base validator class."""

    def __init__(self, rules: Optional[List[ValidationRule]] = None):
        """Initialize validator with rules."""
        self.rules = rules or []

    def validate(self, data: Any, **kwargs) -> ValidationResult:
        """Validate data against rules.

        Args:
            data: Data to validate
            **kwargs: Additional validation parameters

        Returns:
            ValidationResult with validation status
        """
        return ValidationResult(is_valid=True)

    def is_valid(self, data: Any) -> bool:
        """Check if data is valid."""
        return self.validate(data).is_valid


class EvidenceValidator(Validator):
    """Validator for Evidence objects."""

    def validate(
        self,
        evidence: Evidence,
        min_quality: Optional[EvidenceQuality] = None,
        min_content_length: int = 0,
        **kwargs,
    ) -> ValidationResult:
        """Validate evidence quality and completeness.

        Args:
            evidence: Evidence to validate
            min_quality: Minimum required quality level
            min_content_length: Minimum content length in characters

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []

        # Check citations (should never fail due to __post_init__ but double-check)
        if not evidence.citations:
            errors.append("Evidence must have at least one citation")

        # Check quality threshold
        if min_quality:
            quality_order = {
                EvidenceQuality.LOW: 0,
                EvidenceQuality.MEDIUM: 1,
                EvidenceQuality.HIGH: 2,
                EvidenceQuality.UNKNOWN: -1,
            }
            if quality_order.get(evidence.quality, -1) < quality_order.get(min_quality, 0):
                errors.append(
                    f"Evidence quality {evidence.quality.value} below minimum {min_quality.value}"
                )

        # Check content length
        if len(evidence.content) < min_content_length:
            errors.append(
                f"Evidence content length {len(evidence.content)} below minimum {min_content_length}"
            )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


class CitationValidator(Validator):
    """Validator for Citation objects."""

    def validate(
        self,
        citation: Citation,
        check_accessibility: bool = False,
        max_age_days: Optional[int] = None,
        **kwargs,
    ) -> ValidationResult:
        """Validate citation completeness and freshness.

        Args:
            citation: Citation to validate
            check_accessibility: Whether to check if URL is accessible (not implemented)
            max_age_days: Maximum age in days for citation freshness

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []

        # URL validation already done in Citation.__post_init__

        # Check freshness
        if max_age_days and citation.accessed_at:
            age = datetime.now() - citation.accessed_at
            if age.days > max_age_days:
                warnings.append(f"Citation is {age.days} days old (max: {max_age_days})")

        # Note: check_accessibility not implemented (would require network calls)

        return ValidationResult(is_valid=len(errors) == 0, errors=errors, warnings=warnings)


class QualityValidator(Validator):
    """Validator for ResearchReport quality."""

    def validate(
        self,
        report: ResearchReport,
        min_evidence_count: int = 1,
        min_unique_domains: int = 1,
        require_diverse_sources: bool = False,
        **kwargs,
    ) -> ValidationResult:
        """Validate research report quality.

        Args:
            report: ResearchReport to validate
            min_evidence_count: Minimum number of evidence items
            min_unique_domains: Minimum number of unique source domains
            require_diverse_sources: Whether to warn about lack of source diversity

        Returns:
            ValidationResult with quality score
        """
        errors = []
        warnings = []

        # Check evidence count
        if len(report.evidence) < min_evidence_count:
            errors.append(f"Insufficient evidence: {len(report.evidence)} < {min_evidence_count}")

        # Extract domains from all citations
        domains = set()
        for evidence in report.evidence:
            for citation in evidence.citations:
                try:
                    parsed = urlparse(citation.source_url)
                    if parsed.netloc:
                        domains.add(parsed.netloc)
                except Exception:
                    pass

        # Check source diversity
        if require_diverse_sources and len(domains) < min_unique_domains:
            warnings.append(f"Limited source diversity: only {len(domains)} unique domains")

        # Calculate quality score
        quality_score = 0.0
        if report.evidence:
            # Base score on evidence count (up to 0.5)
            quality_score += min(len(report.evidence) / 10.0, 0.5)
            # Add quality bonus (up to 0.3)
            quality_levels = {
                EvidenceQuality.HIGH: 0.3,
                EvidenceQuality.MEDIUM: 0.2,
                EvidenceQuality.LOW: 0.1,
                EvidenceQuality.UNKNOWN: 0.0,
            }
            avg_quality = sum(quality_levels.get(e.quality, 0.0) for e in report.evidence) / len(
                report.evidence
            )
            quality_score += avg_quality
            # Add diversity bonus (up to 0.2)
            if domains:
                quality_score += min(len(domains) / 10.0, 0.2)

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            quality_score=min(quality_score, 1.0),
        )


class ValidationFramework:
    """Framework for managing multiple validators."""

    def __init__(self):
        """Initialize validation framework."""
        self.validators: List[Validator] = []

    def add_validator(self, validator: Validator) -> None:
        """Add a validator to the framework."""
        self.validators.append(validator)

    def validate_all(self, data: Any) -> List[ValidationResult]:
        """Validate data against all validators."""
        return [validator.validate(data) for validator in self.validators]


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
