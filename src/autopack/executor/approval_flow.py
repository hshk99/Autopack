"""Approval Flow Module - Human approval logic extracted from autonomous_executor.py

This module handles all human approval flows via Telegram/SupervisorApiClient:
- Regular phase approval requests (deletion-based risk assessment)
- BUILD-113 RISKY decision approval
- BUILD-113 AMBIGUOUS decision clarification

All functions are "data-in/data-out" around SupervisorApiClient with injectable
sleep/clock for deterministic testing.
"""

import logging
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def request_human_approval(
    api_client,
    phase_id: str,
    quality_report,
    run_id: str,
    last_files_changed: Optional[list] = None,
    timeout_seconds: int = 3600,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """
    Request human approval via Telegram for blocked phases.

    Sends approval request to backend API, which triggers Telegram notification.
    Polls for approval decision until timeout.

    Args:
        api_client: SupervisorApiClient instance for API communication
        phase_id: Phase identifier
        quality_report: Quality gate report with risk assessment
        run_id: Current run identifier
        last_files_changed: List of recently changed files (for fallback)
        timeout_seconds: How long to wait for approval (default: 1 hour)
        sleep_fn: Sleep function for polling (default: time.sleep, injectable for tests)

    Returns:
        True if approved, False if rejected or timed out
    """
    logger.info(f"[{phase_id}] Requesting human approval via Telegram...")

    # Extract risk assessment from quality report
    risk_assessment = getattr(quality_report, "risk_assessment", None)
    if not risk_assessment:
        logger.warning(f"[{phase_id}] No risk assessment found in quality report")
        deletion_info = {
            "net_deletion": 0,
            "loc_removed": 0,
            "loc_added": 0,
            "files": [],
            "risk_level": "unknown",
            "risk_score": 0,
        }
    else:
        metadata = risk_assessment.get("metadata", {})
        # BUILD-190: Extract files from risk_assessment metadata or executor state
        changed_files = (
            metadata.get("files_changed", [])
            or metadata.get("files", [])
            or list(last_files_changed or [])
        )
        deletion_info = {
            "net_deletion": metadata.get("loc_removed", 0) - metadata.get("loc_added", 0),
            "loc_removed": metadata.get("loc_removed", 0),
            "loc_added": metadata.get("loc_added", 0),
            "files": changed_files[:10],  # Limit to 10 files for display
            "risk_level": risk_assessment.get("risk_level", "unknown"),
            "risk_score": risk_assessment.get("risk_score", 0),
        }

    # Send approval request to backend API
    try:
        # BUILD-190: Derive context from phase metadata or quality report
        # Context helps operators understand the nature of the approval request
        phase_context = "general"
        if hasattr(quality_report, "phase_category"):
            phase_context = quality_report.phase_category
        elif risk_assessment and risk_assessment.get("metadata", {}).get("task_category"):
            phase_context = risk_assessment["metadata"]["task_category"]

        result = api_client.request_approval(
            {
                "phase_id": phase_id,
                "deletion_info": deletion_info,
                "run_id": run_id,
                "context": phase_context,
            },
            timeout=30,
        )

        if result.get("status") == "rejected":
            logger.error(
                f"[{phase_id}] Approval request rejected: {result.get('reason', 'Unknown')}"
            )
            return False

        # Check if immediately approved (auto-approve mode)
        if result.get("status") == "approved":
            logger.info(f"[{phase_id}] ✅ Approval GRANTED (auto-approved)")
            return True

        # Extract approval_id for polling
        approval_id = result.get("approval_id")
        if not approval_id:
            logger.error(f"[{phase_id}] No approval_id in response - cannot poll for status")
            return False

        logger.info(
            f"[{phase_id}] Approval request sent (approval_id={approval_id}), waiting for user decision..."
        )

    except Exception as e:
        logger.error(f"[{phase_id}] Failed to send approval request: {e}")
        # If Telegram is not configured, auto-reject
        return False

    # Poll for approval status
    elapsed = 0
    poll_interval = 10  # seconds

    while elapsed < timeout_seconds:
        try:
            status_data = api_client.poll_approval_status(approval_id, timeout=10)

            status = status_data.get("status")

            if status == "approved":
                logger.info(f"[{phase_id}] ✅ Approval GRANTED by user")
                return True

            if status == "rejected":
                logger.warning(f"[{phase_id}] ❌ Approval REJECTED by user")
                return False

            # Still pending, wait and check again
            sleep_fn(poll_interval)
            elapsed += poll_interval

            if elapsed % 60 == 0:  # Log every minute
                logger.info(
                    f"[{phase_id}] Still waiting for approval... ({elapsed}s / {timeout_seconds}s)"
                )

        except Exception as e:
            logger.warning(f"[{phase_id}] Error checking approval status: {e}")
            sleep_fn(poll_interval)
            elapsed += poll_interval

    # Timeout reached
    logger.warning(f"[{phase_id}] ⏱️  Approval timeout after {timeout_seconds}s")
    return False


def request_build113_approval(
    api_client,
    phase_id: str,
    decision,
    patch_content: str,
    run_id: str,
    timeout_seconds: int = 3600,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """
    Request human approval for BUILD-113 RISKY decisions via Telegram.

    Sends approval request with decision details, risk assessment, and patch preview.
    Polls for approval decision until timeout.

    Args:
        api_client: SupervisorApiClient instance for API communication
        phase_id: Phase identifier
        decision: BUILD-113 Decision object with risk/confidence details
        patch_content: Full patch content for preview
        run_id: Current run identifier
        timeout_seconds: How long to wait for approval (default: 1 hour)
        sleep_fn: Sleep function for polling (default: time.sleep, injectable for tests)

    Returns:
        True if approved, False if rejected or timed out
    """
    logger.info(f"[BUILD-113] Requesting human approval for RISKY decision on {phase_id}...")

    # Build approval request with BUILD-113 decision details
    try:
        # Extract patch preview (first 500 chars)
        patch_preview = patch_content[:500] + ("..." if len(patch_content) > 500 else "")

        result = api_client.request_approval(
            {
                "phase_id": phase_id,
                "run_id": run_id,
                "context": "build113_risky_decision",
                "decision_info": {
                    "type": decision.type.value,
                    "risk_level": decision.risk_level,
                    "confidence": f"{decision.confidence:.0%}",
                    "rationale": decision.rationale,
                    "files_modified": decision.files_modified[:5],  # First 5 files
                    "files_count": len(decision.files_modified),
                    "deliverables_met": decision.deliverables_met,
                    "net_deletion": decision.net_deletion,
                    "questions": decision.questions_for_human,
                },
                "patch_preview": patch_preview,
            },
            timeout=30,
        )

        if result.get("status") == "rejected":
            logger.error(
                f"[BUILD-113] Approval request rejected: {result.get('reason', 'Unknown')}"
            )
            return False

        # Check if immediately approved (auto-approve mode)
        if result.get("status") == "approved":
            logger.info("[BUILD-113] ✅ RISKY patch APPROVED (auto-approved)")
            return True

        # Extract approval_id for polling
        approval_id = result.get("approval_id")
        if not approval_id:
            logger.error("[BUILD-113] No approval_id in response - cannot poll for status")
            return False

        logger.info(
            f"[BUILD-113] Approval request sent (approval_id={approval_id}), waiting for user decision..."
        )

    except Exception as e:
        logger.error(f"[BUILD-113] Failed to send approval request: {e}")
        # If Telegram is not configured, auto-reject high-risk patches
        logger.warning(
            "[BUILD-113] Defaulting to REJECT for RISKY decision without approval system"
        )
        return False

    # Poll for approval status (reuse same polling logic as regular approval)
    elapsed = 0
    poll_interval = 10  # seconds

    while elapsed < timeout_seconds:
        try:
            status_data = api_client.poll_approval_status(approval_id, timeout=10)

            status = status_data.get("status")

            if status == "approved":
                logger.info("[BUILD-113] ✅ RISKY patch APPROVED by user")
                return True

            if status == "rejected":
                logger.warning("[BUILD-113] ❌ RISKY patch REJECTED by user")
                return False

            # Still pending, wait and check again
            sleep_fn(poll_interval)
            elapsed += poll_interval

            if elapsed % 60 == 0:  # Log every minute
                logger.info(
                    f"[BUILD-113] Still waiting for approval... ({elapsed}s / {timeout_seconds}s)"
                )

        except Exception as e:
            logger.warning(f"[BUILD-113] Error checking approval status: {e}")
            sleep_fn(poll_interval)
            elapsed += poll_interval

    # Timeout reached
    logger.warning(
        f"[BUILD-113] ⏱️  Approval timeout after {timeout_seconds}s - defaulting to REJECT"
    )
    return False


def request_build113_clarification(
    api_client,
    phase_id: str,
    decision,
    run_id: str,
    timeout_seconds: int = 3600,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Optional[str]:
    """
    Request human clarification for BUILD-113 AMBIGUOUS decisions via Telegram.

    Sends clarification request with decision details and questions.
    Polls for human response until timeout.

    Args:
        api_client: SupervisorApiClient instance for API communication
        phase_id: Phase identifier
        decision: BUILD-113 Decision object with questions
        run_id: Current run identifier
        timeout_seconds: How long to wait for clarification (default: 1 hour)
        sleep_fn: Sleep function for polling (default: time.sleep, injectable for tests)

    Returns:
        Human response text if provided, None if timed out
    """
    logger.info(
        f"[BUILD-113] Requesting human clarification for AMBIGUOUS decision on {phase_id}..."
    )

    # Build clarification request with BUILD-113 decision details
    try:
        result = api_client.request_clarification(
            {
                "phase_id": phase_id,
                "run_id": run_id,
                "context": "build113_ambiguous_decision",
                "decision_info": {
                    "type": decision.type.value,
                    "risk_level": decision.risk_level,
                    "confidence": f"{decision.confidence:.0%}",
                    "rationale": decision.rationale,
                    "questions": decision.questions_for_human,
                    "alternatives": decision.alternatives_considered,
                },
            },
            timeout=30,
        )

        if result.get("status") == "rejected":
            logger.error(
                f"[BUILD-113] Clarification request rejected: {result.get('reason', 'Unknown')}"
            )
            return None

        logger.info("[BUILD-113] Clarification request sent, waiting for user response...")

    except Exception as e:
        logger.error(f"[BUILD-113] Failed to send clarification request: {e}")
        # If Telegram is not configured, cannot get clarification
        logger.warning(
            "[BUILD-113] No clarification system available - cannot resolve AMBIGUOUS decision"
        )
        return None

    # Poll for clarification response
    elapsed = 0
    poll_interval = 10  # seconds

    while elapsed < timeout_seconds:
        try:
            status_data = api_client.poll_clarification_status(phase_id, timeout=10)

            status = status_data.get("status")

            if status == "answered":
                clarification_text = status_data.get("response", "")
                logger.info(
                    f"[BUILD-113] ✅ Clarification received: {clarification_text[:100]}..."
                )
                return clarification_text

            if status == "rejected":
                logger.warning("[BUILD-113] ❌ Clarification request rejected by user")
                return None

            # Still pending, wait and check again
            sleep_fn(poll_interval)
            elapsed += poll_interval

            if elapsed % 60 == 0:  # Log every minute
                logger.info(
                    f"[BUILD-113] Still waiting for clarification... ({elapsed}s / {timeout_seconds}s)"
                )

        except Exception as e:
            logger.warning(f"[BUILD-113] Error checking clarification status: {e}")
            sleep_fn(poll_interval)
            elapsed += poll_interval

    # Timeout reached
    logger.warning(f"[BUILD-113] ⏱️  Clarification timeout after {timeout_seconds}s")
    return None
