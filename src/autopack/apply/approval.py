"""Approval workflow logic extracted from governed_apply.py.

This module contains approval-related functions that were previously embedded
in governed_apply.py. It reduces complexity by separating approval workflow
concerns.
"""

import logging

logger = logging.getLogger(__name__)


def require_approval(patch: str, risk_level: str) -> bool:
    """
    Determine if patch requires manual approval.

    Args:
        patch: Patch content to evaluate
        risk_level: Risk level classification (low, medium, high, critical)

    Returns:
        True if approval is required, False otherwise
    """
    # High and critical risk patches always require approval
    if risk_level in ("high", "critical"):
        return True

    # Check patch size as a risk indicator
    lines = len(patch.split("\n"))
    if lines > 500:
        logger.debug(f"Large patch ({lines} lines) may require approval")
        return True

    # Check for protected paths in patch
    protected_indicators = [
        "src/autopack/",
        ".git/",
        ".autonomous_runs/",
        "config/",
    ]

    for indicator in protected_indicators:
        if indicator in patch:
            logger.debug(f"Patch touches protected area: {indicator}")
            return True

    return False


def get_approval_status(patch_id: str) -> str:
    """
    Check approval status for patch.

    Args:
        patch_id: Unique identifier for the patch

    Returns:
        Approval status (pending, approved, rejected)
    """
    # This is a placeholder for future approval tracking system
    # In a real implementation, this would query an approval database/API
    logger.debug(f"Checking approval status for patch {patch_id}")
    return "pending"


def request_approval(patch: str, reviewer: str) -> str:
    """
    Request approval for high-risk patch.

    Args:
        patch: Patch content to request approval for
        reviewer: Email or ID of reviewer to request approval from

    Returns:
        Request ID for the approval request
    """
    # This is a placeholder for future approval request system
    # In a real implementation, this would create an approval request in a system
    logger.info(f"Approval request submitted to {reviewer} for patch")
    return f"approval_req_{hash(patch) % 1000000}"


def is_patch_risk_high(patch: str) -> bool:
    """
    Assess if patch represents high risk.

    Args:
        patch: Patch content to assess

    Returns:
        True if patch is high risk, False otherwise
    """
    # Check for multiple files modified
    file_count = patch.count("diff --git")
    if file_count > 10:
        logger.debug(f"Patch modifies many files ({file_count})")
        return True

    # Check for deletion patterns
    if patch.count("\n-") > patch.count("\n+") * 2:
        logger.debug("Patch has high deletion ratio")
        return True

    # Check for critical keywords
    critical_keywords = [
        "__init__.py",
        "config.py",
        "main.py",
        "database.py",
        "security",
    ]

    for keyword in critical_keywords:
        if keyword in patch:
            logger.debug(f"Patch touches critical component: {keyword}")
            return True

    return False


def assess_patch_risk(patch: str) -> str:
    """
    Assess overall risk level of a patch.

    Args:
        patch: Patch content to assess

    Returns:
        Risk level classification (low, medium, high, critical)
    """
    if is_patch_risk_high(patch):
        return "high"

    file_count = patch.count("diff --git")
    if file_count > 5:
        return "medium"

    if len(patch) > 1000:
        return "medium"

    return "low"
