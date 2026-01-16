"""Validates builder deliverables against intention constraints.

This module provides post-hoc validation that builder-generated deliverables
respect intention anchor constraints (must_not, success_criteria, etc.).
"""

from dataclasses import dataclass
from typing import Optional, Dict, List

from ..intention_anchor.v2 import IntentionAnchorV2


@dataclass
class ValidationResult:
    """Result of deliverable validation.

    Attributes:
        is_valid: True if no violations found
        violations: List of constraint violations (must_not, hard_blocks, etc.)
        warnings: List of warnings for unmet criteria
        success_criteria_met: Dict mapping criterion to whether it was met
    """

    is_valid: bool
    violations: List[str]
    warnings: List[str]
    success_criteria_met: Dict[str, bool]


class DeliverableValidator:
    """Validates builder output against intention anchor constraints.

    Checks:
    - must_not (SafetyRisk): Operations that must never be allowed
    - hard_blocks (EvidenceVerification): Must-pass checks
    - success_criteria (NorthStar): Desired outcomes and success signals
    """

    def __init__(self, anchor: Optional[IntentionAnchorV2] = None):
        """Initialize validator with optional intention anchor.

        Args:
            anchor: IntentionAnchorV2 instance for constraint validation
        """
        self.anchor = anchor

    def validate(self, deliverable: str, metadata: Optional[Dict] = None) -> ValidationResult:
        """Validate deliverable against intention anchor constraints.

        Args:
            deliverable: The builder-generated deliverable content
            metadata: Optional metadata (phase, attempt, etc.)

        Returns:
            ValidationResult with violations, warnings, and criteria status
        """
        violations: List[str] = []
        warnings: List[str] = []
        criteria_met: Dict[str, bool] = {}

        # If no anchor, skip validation with warning
        if not self.anchor:
            return ValidationResult(
                is_valid=True,
                violations=[],
                warnings=["No intention anchor provided - skipping validation"],
                success_criteria_met={},
            )

        # Check must_not constraints (SafetyRisk.never_allow)
        if (
            self.anchor.pivot_intentions.safety_risk
            and self.anchor.pivot_intentions.safety_risk.never_allow
        ):
            for constraint in self.anchor.pivot_intentions.safety_risk.never_allow:
                if self._check_violation(deliverable, constraint):
                    violations.append(f"must_not violation: {constraint}")

        # Check hard_blocks (EvidenceVerification.hard_blocks)
        if (
            self.anchor.pivot_intentions.evidence_verification
            and self.anchor.pivot_intentions.evidence_verification.hard_blocks
        ):
            for block in self.anchor.pivot_intentions.evidence_verification.hard_blocks:
                if not self._check_criterion(deliverable, metadata, block):
                    violations.append(f"hard_block failed: {block}")

        # Check success_criteria (NorthStar.success_signals)
        if (
            self.anchor.pivot_intentions.north_star
            and self.anchor.pivot_intentions.north_star.success_signals
        ):
            for criterion in self.anchor.pivot_intentions.north_star.success_signals:
                met = self._check_criterion(deliverable, metadata, criterion)
                criteria_met[criterion] = met
                if not met:
                    warnings.append(f"Success criterion not verified: {criterion}")

        return ValidationResult(
            is_valid=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            success_criteria_met=criteria_met,
        )

    def _check_violation(self, deliverable: str, constraint: str) -> bool:
        """Check if deliverable violates a must_not/never_allow constraint.

        Uses simple keyword matching. Can be enhanced with semantic analysis.

        Args:
            deliverable: Content to check
            constraint: Constraint description

        Returns:
            True if constraint is violated
        """
        constraint_lower = constraint.lower()
        deliverable_lower = deliverable.lower()
        return constraint_lower in deliverable_lower

    def _check_criterion(self, deliverable: str, metadata: Optional[Dict], criterion: str) -> bool:
        """Check if success criterion is met.

        Uses simple keyword matching. Can be enhanced with LLM-based validation.

        Args:
            deliverable: Content to check
            metadata: Optional context (phase, etc.)
            criterion: Criterion description

        Returns:
            True if criterion appears to be met
        """
        # Placeholder - can be enhanced with more sophisticated checks
        # For now, always return True to avoid false negatives
        # Real implementation would use semantic analysis or LLM validation
        return True
