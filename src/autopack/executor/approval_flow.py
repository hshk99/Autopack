"""Approval flow module for human-in-the-loop decisions.

Extracted from autonomous_executor.py for PR-EXE-2.
Provides approval and clarification request workflows for:
- Quality gate blocked phases (human approval required)
- BUILD-113 RISKY decisions (high-risk patch approval)
- BUILD-113 AMBIGUOUS decisions (human clarification needed)

Uses SupervisorApiClient for all API communication.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from autopack.supervisor.api_client import SupervisorApiClient

logger = logging.getLogger(__name__)


class ApprovalResult(Enum):
    """Result of an approval request."""
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class DeletionInfo:
    """Deletion information for approval requests."""
    net_deletion: int
    loc_removed: int
    loc_added: int
    files: List[str]
    risk_level: str
    risk_score: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API payload."""
        return {
            "net_deletion": self.net_deletion,
            "loc_removed": self.loc_removed,
            "loc_added": self.loc_added,
            "files": self.files,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
        }


@dataclass
class Build113DecisionInfo:
    """BUILD-113 decision information for approval/clarification requests."""
    decision_type: str
    risk_level: str
    confidence: float
    rationale: str
    files_modified: List[str]
    deliverables_met: bool
    net_deletion: int
    questions_for_human: List[str]
    alternatives_considered: Optional[List[str]] = None

    def to_approval_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for approval request payload."""
        return {
            "type": self.decision_type,
            "risk_level": self.risk_level,
            "confidence": f"{self.confidence:.0%}",
            "rationale": self.rationale,
            "files_modified": self.files_modified[:5],  # First 5 files
            "files_count": len(self.files_modified),
            "deliverables_met": self.deliverables_met,
            "net_deletion": self.net_deletion,
            "questions": self.questions_for_human,
        }

    def to_clarification_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for clarification request payload."""
        return {
            "type": self.decision_type,
            "risk_level": self.risk_level,
            "confidence": f"{self.confidence:.0%}",
            "rationale": self.rationale,
            "questions": self.questions_for_human,
            "alternatives": self.alternatives_considered or [],
        }


def extract_deletion_info(
    quality_report: Any,
    fallback_files: Optional[List[str]] = None,
) -> DeletionInfo:
    """
    Extract deletion information from a quality report.

    Args:
        quality_report: Quality gate report with risk assessment
        fallback_files: Files to use if not found in report

    Returns:
        DeletionInfo with extracted or default values
    """
    risk_assessment = getattr(quality_report, "risk_assessment", None)

    if not risk_assessment:
        logger.warning("No risk assessment found in quality report")
        return DeletionInfo(
            net_deletion=0,
            loc_removed=0,
            loc_added=0,
            files=[],
            risk_level="unknown",
            risk_score=0,
        )

    metadata = risk_assessment.get("metadata", {})
    # BUILD-190: Extract files from risk_assessment metadata or fallback
    changed_files = (
        metadata.get("files_changed", [])
        or metadata.get("files", [])
        or list(fallback_files or [])
    )

    return DeletionInfo(
        net_deletion=metadata.get("loc_removed", 0) - metadata.get("loc_added", 0),
        loc_removed=metadata.get("loc_removed", 0),
        loc_added=metadata.get("loc_added", 0),
        files=changed_files[:10],  # Limit to 10 files for display
        risk_level=risk_assessment.get("risk_level", "unknown"),
        risk_score=risk_assessment.get("risk_score", 0),
    )


def derive_context_from_report(quality_report: Any) -> str:
    """
    Derive approval context from quality report.

    Args:
        quality_report: Quality gate report

    Returns:
        Context string for the approval request
    """
    if hasattr(quality_report, "phase_category"):
        return quality_report.phase_category

    risk_assessment = getattr(quality_report, "risk_assessment", None)
    if risk_assessment:
        metadata = risk_assessment.get("metadata", {})
        if metadata.get("task_category"):
            return metadata["task_category"]

    return "general"


def request_human_approval(
    client: SupervisorApiClient,
    run_id: str,
    phase_id: str,
    quality_report: Any,
    fallback_files: Optional[List[str]] = None,
    timeout_seconds: int = 3600,
    poll_interval: int = 10,
) -> bool:
    """
    Request human approval via Telegram for blocked phases.

    Sends approval request to backend API, which triggers Telegram notification.
    Polls for approval decision until timeout.

    Args:
        client: SupervisorApiClient instance
        run_id: Run identifier
        phase_id: Phase identifier
        quality_report: Quality gate report with risk assessment
        fallback_files: Files to use if not found in report
        timeout_seconds: How long to wait for approval (default: 1 hour)
        poll_interval: Seconds between status checks

    Returns:
        True if approved, False if rejected or timed out
    """
    logger.info(f"[{phase_id}] Requesting human approval via Telegram...")

    # Extract deletion info from quality report
    deletion_info = extract_deletion_info(quality_report, fallback_files)
    context = derive_context_from_report(quality_report)

    # Build payload
    payload = {
        "phase_id": phase_id,
        "deletion_info": deletion_info.to_dict(),
        "run_id": run_id,
        "context": context,
    }

    # Send approval request
    result = client.request_approval(
        run_id=run_id,
        phase_id=phase_id,
        context=context,
        payload=payload,
        timeout=30,
    )

    if not result.success:
        logger.error(f"[{phase_id}] Failed to send approval request: {result.error}")
        return False

    # Check for immediate response
    status = result.data.get("status") if result.data else None
    if status == "rejected":
        logger.error(
            f"[{phase_id}] Approval request rejected: {result.data.get('reason', 'Unknown')}"
        )
        return False

    if status == "approved":
        logger.info(f"[{phase_id}] Approval GRANTED (auto-approved)")
        return True

    # Extract approval_id for polling
    approval_id = result.data.get("approval_id") if result.data else None
    if not approval_id:
        logger.error(f"[{phase_id}] No approval_id in response - cannot poll for status")
        return False

    logger.info(
        f"[{phase_id}] Approval request sent (approval_id={approval_id}), waiting for user decision..."
    )

    # Poll for approval status
    approval_status = client.poll_approval_status(
        approval_id=approval_id,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )

    if approval_status.status == "approved":
        logger.info(f"[{phase_id}] Approval GRANTED by user")
        return True

    if approval_status.status == "rejected":
        logger.warning(f"[{phase_id}] Approval REJECTED by user")
        return False

    if approval_status.status == "timeout":
        logger.warning(f"[{phase_id}] Approval timeout after {timeout_seconds}s")
        return False

    # Error or unknown status
    logger.error(f"[{phase_id}] Approval status check failed: {approval_status.error}")
    return False


def request_build113_approval(
    client: SupervisorApiClient,
    run_id: str,
    phase_id: str,
    decision_info: Build113DecisionInfo,
    patch_content: str,
    timeout_seconds: int = 3600,
    poll_interval: int = 10,
) -> bool:
    """
    Request human approval for BUILD-113 RISKY decisions via Telegram.

    Sends approval request with decision details, risk assessment, and patch preview.
    Polls for approval decision until timeout.

    Args:
        client: SupervisorApiClient instance
        run_id: Run identifier
        phase_id: Phase identifier
        decision_info: BUILD-113 decision details
        patch_content: Full patch content for preview
        timeout_seconds: How long to wait for approval (default: 1 hour)
        poll_interval: Seconds between status checks

    Returns:
        True if approved, False if rejected or timed out
    """
    logger.info(f"[BUILD-113] Requesting human approval for RISKY decision on {phase_id}...")

    # Extract patch preview (first 500 chars)
    patch_preview = patch_content[:500] + ("..." if len(patch_content) > 500 else "")

    # Build payload
    payload = {
        "phase_id": phase_id,
        "run_id": run_id,
        "context": "build113_risky_decision",
        "decision_info": decision_info.to_approval_dict(),
        "patch_preview": patch_preview,
    }

    # Send approval request
    result = client.request_approval(
        run_id=run_id,
        phase_id=phase_id,
        context="build113_risky_decision",
        payload=payload,
        timeout=30,
    )

    if not result.success:
        logger.error(f"[BUILD-113] Failed to send approval request: {result.error}")
        logger.warning(
            "[BUILD-113] Defaulting to REJECT for RISKY decision without approval system"
        )
        return False

    # Check for immediate response
    status = result.data.get("status") if result.data else None
    if status == "rejected":
        logger.error(
            f"[BUILD-113] Approval request rejected: {result.data.get('reason', 'Unknown')}"
        )
        return False

    if status == "approved":
        logger.info("[BUILD-113] RISKY patch APPROVED (auto-approved)")
        return True

    # Extract approval_id for polling
    approval_id = result.data.get("approval_id") if result.data else None
    if not approval_id:
        logger.error("[BUILD-113] No approval_id in response - cannot poll for status")
        return False

    logger.info(
        f"[BUILD-113] Approval request sent (approval_id={approval_id}), waiting for user decision..."
    )

    # Poll for approval status
    approval_status = client.poll_approval_status(
        approval_id=approval_id,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )

    if approval_status.status == "approved":
        logger.info("[BUILD-113] RISKY patch APPROVED by user")
        return True

    if approval_status.status == "rejected":
        logger.warning("[BUILD-113] RISKY patch REJECTED by user")
        return False

    if approval_status.status == "timeout":
        logger.warning(
            f"[BUILD-113] Approval timeout after {timeout_seconds}s - defaulting to REJECT"
        )
        return False

    # Error or unknown status
    logger.error(f"[BUILD-113] Approval status check failed: {approval_status.error}")
    return False


def request_build113_clarification(
    client: SupervisorApiClient,
    run_id: str,
    phase_id: str,
    decision_info: Build113DecisionInfo,
    timeout_seconds: int = 3600,
    poll_interval: int = 10,
) -> Optional[str]:
    """
    Request human clarification for BUILD-113 AMBIGUOUS decisions via Telegram.

    Sends clarification request with decision details and questions.
    Polls for human response until timeout.

    Args:
        client: SupervisorApiClient instance
        run_id: Run identifier
        phase_id: Phase identifier
        decision_info: BUILD-113 decision details with questions
        timeout_seconds: How long to wait for clarification (default: 1 hour)
        poll_interval: Seconds between status checks

    Returns:
        Human response text if provided, None if timed out or rejected
    """
    logger.info(
        f"[BUILD-113] Requesting human clarification for AMBIGUOUS decision on {phase_id}..."
    )

    # Build payload
    payload = {
        "phase_id": phase_id,
        "run_id": run_id,
        "context": "build113_ambiguous_decision",
        "decision_info": decision_info.to_clarification_dict(),
    }

    # Send clarification request
    result = client.request_clarification(
        run_id=run_id,
        phase_id=phase_id,
        context="build113_ambiguous_decision",
        payload=payload,
        timeout=30,
    )

    if not result.success:
        logger.error(f"[BUILD-113] Failed to send clarification request: {result.error}")
        logger.warning(
            "[BUILD-113] No clarification system available - cannot resolve AMBIGUOUS decision"
        )
        return None

    # Check for immediate rejection
    status = result.data.get("status") if result.data else None
    if status == "rejected":
        logger.error(
            f"[BUILD-113] Clarification request rejected: {result.data.get('reason', 'Unknown')}"
        )
        return None

    logger.info("[BUILD-113] Clarification request sent, waiting for user response...")

    # Poll for clarification response
    clarification_status = client.poll_clarification_status(
        phase_id=phase_id,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )

    if clarification_status.status == "answered":
        response = clarification_status.response or ""
        logger.info(f"[BUILD-113] Clarification received: {response[:100]}...")
        return response

    if clarification_status.status == "rejected":
        logger.warning("[BUILD-113] Clarification request rejected by user")
        return None

    if clarification_status.status == "timeout":
        logger.warning(f"[BUILD-113] Clarification timeout after {timeout_seconds}s")
        return None

    # Error or unknown status
    logger.error(f"[BUILD-113] Clarification status check failed: {clarification_status.error}")
    return None


def create_build113_decision_info(decision: Any) -> Build113DecisionInfo:
    """
    Create Build113DecisionInfo from a BUILD-113 Decision object.

    Args:
        decision: BUILD-113 Decision object with type, risk_level, confidence, etc.

    Returns:
        Build113DecisionInfo dataclass instance
    """
    return Build113DecisionInfo(
        decision_type=decision.type.value if hasattr(decision.type, "value") else str(decision.type),
        risk_level=decision.risk_level,
        confidence=decision.confidence,
        rationale=decision.rationale,
        files_modified=decision.files_modified,
        deliverables_met=decision.deliverables_met,
        net_deletion=decision.net_deletion,
        questions_for_human=decision.questions_for_human,
        alternatives_considered=getattr(decision, "alternatives_considered", None),
    )
