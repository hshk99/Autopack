"""Safety profile derivation from IntentionAnchorV2 (BUILD-181 Phase 2).

Deterministically derives safety profile from pivot intentions.
Missing or conservative intentions default to strict (fail-safe).

Mapping:
- risk_tolerance in {"minimal", "low"} → safety_profile="strict"
- risk_tolerance in {"moderate", "high"} → safety_profile="normal"
- Missing safety_risk pivot → default strict (fail-safe)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from autopack.intention_anchor.v2 import IntentionAnchorV2

logger = logging.getLogger(__name__)

# Type alias for safety profile
SafetyProfile = Literal["normal", "strict"]

# Risk tolerance to safety profile mapping
RISK_TO_SAFETY: dict[str, SafetyProfile] = {
    "minimal": "strict",
    "low": "strict",
    "moderate": "normal",
    "high": "normal",
}

# Default when no safety_risk pivot is defined
DEFAULT_SAFETY_PROFILE: SafetyProfile = "strict"


def derive_safety_profile(anchor: "IntentionAnchorV2") -> SafetyProfile:
    """Derive safety profile from IntentionAnchorV2.

    Deterministic mapping from pivot_intentions.safety_risk.risk_tolerance.
    When safety_risk pivot is missing, defaults to "strict" (fail-safe).

    Args:
        anchor: IntentionAnchorV2 instance

    Returns:
        Safety profile: "strict" or "normal"
    """
    # Check if safety_risk pivot exists
    if anchor.pivot_intentions.safety_risk is None:
        logger.debug(
            f"[SafetyProfile] No safety_risk pivot for project={anchor.project_id}, "
            f"defaulting to '{DEFAULT_SAFETY_PROFILE}'"
        )
        return DEFAULT_SAFETY_PROFILE

    # Get risk tolerance
    risk_tolerance = anchor.pivot_intentions.safety_risk.risk_tolerance

    # Map to safety profile
    safety_profile = RISK_TO_SAFETY.get(risk_tolerance, DEFAULT_SAFETY_PROFILE)

    logger.debug(
        f"[SafetyProfile] project={anchor.project_id}, "
        f"risk_tolerance={risk_tolerance} → safety_profile={safety_profile}"
    )

    return safety_profile


def is_strict_profile(anchor: "IntentionAnchorV2") -> bool:
    """Check if anchor requires strict safety profile.

    Convenience function for guards and checks.

    Args:
        anchor: IntentionAnchorV2 instance

    Returns:
        True if safety profile is "strict"
    """
    return derive_safety_profile(anchor) == "strict"


def requires_elevated_review(anchor: "IntentionAnchorV2") -> bool:
    """Check if anchor's safety posture requires elevated review.

    True when:
    - Safety profile is strict
    - OR never_allow list is non-empty
    - OR requires_approval list is non-empty

    Args:
        anchor: IntentionAnchorV2 instance

    Returns:
        True if elevated review is required
    """
    if is_strict_profile(anchor):
        return True

    safety_risk = anchor.pivot_intentions.safety_risk
    if safety_risk is None:
        return True  # No safety pivot = elevated review

    if safety_risk.never_allow:
        return True

    if safety_risk.requires_approval:
        return True

    return False
