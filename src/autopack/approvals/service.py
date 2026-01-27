"""Approval service interface and implementation (BUILD-181 Phase 6).

Provides pivot-only approval triggers. Telegram integration is:
- Disabled by default
- Never active in CI
- Requires explicit configuration

Approval is requested ONLY for:
- Pivot intention change
- Pivot constraint violation
- Governance escalation (critical risk tier)

Normal retries, replans, and model escalations within bounds do NOT trigger approval.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ApprovalTriggerReason(str, Enum):
    """Reasons for triggering approval request."""

    # Pivot-impacting (require approval)
    PIVOT_INTENTION_CHANGE = "pivot_intention_change"
    PIVOT_CONSTRAINT_VIOLATION = "pivot_constraint_violation"
    GOVERNANCE_ESCALATION = "governance_escalation"

    # Non-pivot-impacting (do NOT require approval)
    NORMAL_RETRY = "normal_retry"
    NORMAL_REPLAN = "normal_replan"
    MODEL_ESCALATION_WITHIN_BOUNDS = "model_escalation_within_bounds"


# Trigger reasons that require approval
PIVOT_IMPACTING_TRIGGERS = {
    ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
    ApprovalTriggerReason.PIVOT_CONSTRAINT_VIOLATION,
    ApprovalTriggerReason.GOVERNANCE_ESCALATION,
}


class ApprovalRequest(BaseModel):
    """Request for approval of a pivot-impacting action."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., description="Unique request identifier")
    run_id: str = Field(..., description="Run this request belongs to")
    phase_id: str = Field(..., description="Phase triggering the request")
    trigger_reason: ApprovalTriggerReason = Field(..., description="Why approval is needed")
    affected_pivots: List[str] = Field(default_factory=list, description="Pivot types affected")
    description: str = Field(..., description="Human-readable description")
    diff_summary: Dict[str, Any] = Field(default_factory=dict, description="Change summary")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "trigger_reason": self.trigger_reason.value,
            "affected_pivots": self.affected_pivots,
            "description": self.description,
            "diff_summary": self.diff_summary,
            "created_at": self.created_at.isoformat(),
        }


class ApprovalResult(BaseModel):
    """Result of an approval request."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether request was successfully sent")
    approved: Optional[bool] = Field(
        default=None, description="Approval decision (None if pending)"
    )
    error_reason: Optional[str] = Field(default=None, description="Error reason if failed")
    evidence: Optional[Dict[str, Any]] = Field(default=None, description="Evidence record")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "success": self.success,
            "approved": self.approved,
            "error_reason": self.error_reason,
            "evidence": self.evidence,
        }


def should_trigger_approval(request: ApprovalRequest) -> bool:
    """Determine if an approval request should trigger approval flow.

    Only pivot-impacting triggers require approval.

    Args:
        request: ApprovalRequest to evaluate

    Returns:
        True if approval should be requested
    """
    return request.trigger_reason in PIVOT_IMPACTING_TRIGGERS


class ApprovalService(ABC):
    """Abstract base class for approval services."""

    @abstractmethod
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Request approval for a pivot-impacting action.

        Args:
            request: ApprovalRequest with details

        Returns:
            ApprovalResult with outcome
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if service is enabled and configured."""
        pass


class NoopApprovalService(ApprovalService):
    """No-op approval service (default when Telegram disabled)."""

    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Log request but take no action.

        Args:
            request: ApprovalRequest

        Returns:
            ApprovalResult indicating no action taken
        """
        logger.info(
            f"[ApprovalService:Noop] Request {request.request_id} logged but not sent "
            f"(approval service disabled)"
        )

        return ApprovalResult(
            success=True,
            approved=None,  # Unknown - no actual approval flow
            error_reason=None,
            evidence={
                "service": "noop",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": request.request_id,
                "note": "Approval service disabled, request logged only",
            },
        )

    def is_enabled(self) -> bool:
        """Noop service is always available but not really enabled."""
        return False


class ChainedApprovalService(ApprovalService):
    """IMP-REL-001: Approval service with multi-channel fallback.

    Uses NotificationChain to try Telegram -> Email -> SMS in sequence
    until one succeeds. Provides resilience against single point of failure.
    """

    def __init__(self):
        """Initialize with notification chain."""
        from .notification_chain import create_notification_chain

        self._chain = create_notification_chain()

    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval request through notification chain.

        Args:
            request: ApprovalRequest with details

        Returns:
            ApprovalResult with outcome
        """
        if not self.is_enabled():
            logger.warning(
                f"[ChainedApprovalService] Request {request.request_id} cannot be sent: "
                f"no notification channels configured"
            )
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="no_channels_configured",
                evidence={
                    "service": "chained",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request.request_id,
                    "error": "No notification channels are enabled",
                },
            )

        chain_result = self._chain.send(request)

        if chain_result.success:
            logger.info(
                f"[ChainedApprovalService] Request {request.request_id} sent via "
                f"{chain_result.successful_channel}"
            )
            return ApprovalResult(
                success=True,
                approved=None,  # Pending human response
                error_reason=None,
                evidence={
                    "service": "chained",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request.request_id,
                    "successful_channel": chain_result.successful_channel,
                    "failed_channels": chain_result.failed_channels,
                    "chain_evidence": chain_result.evidence,
                },
            )
        else:
            logger.error(
                f"[ChainedApprovalService] All channels failed for {request.request_id}: "
                f"{chain_result.error_details}"
            )
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="all_channels_failed",
                evidence={
                    "service": "chained",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request.request_id,
                    "failed_channels": chain_result.failed_channels,
                    "error_details": chain_result.error_details,
                },
            )

    def is_enabled(self) -> bool:
        """Check if any notification channel is enabled."""
        return len(self._chain.get_enabled_channels()) > 0

    def get_enabled_channels(self) -> List[str]:
        """Get list of enabled notification channel names."""
        return self._chain.get_enabled_channels()


def _is_ci_environment() -> bool:
    """Check if running in CI environment."""
    ci_indicators = [
        "CI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "JENKINS_URL",
        "CIRCLECI",
        "TRAVIS",
        "BUILDKITE",
    ]
    return any(os.environ.get(var) for var in ci_indicators)


def get_approval_service(use_chain: bool = True) -> ApprovalService:
    """Get the configured approval service.

    IMP-REL-001: Now supports multi-channel fallback via ChainedApprovalService.

    Logic:
    1. Never active in CI
    2. If use_chain=True (default), use ChainedApprovalService with fallback
    3. Falls back to single-channel TelegramApprovalService if use_chain=False
    4. Returns NoopApprovalService if no channels configured

    Args:
        use_chain: Use ChainedApprovalService with fallback (default: True)

    Returns:
        ApprovalService instance
    """
    # Never active in CI
    if _is_ci_environment():
        logger.debug("[ApprovalService] CI environment detected, using NoopApprovalService")
        return NoopApprovalService()

    # IMP-REL-001: Use notification chain by default for fallback support
    if use_chain:
        chained_service = ChainedApprovalService()
        if chained_service.is_enabled():
            enabled_channels = chained_service.get_enabled_channels()
            logger.info(
                f"[ApprovalService] Using ChainedApprovalService with channels: {enabled_channels}"
            )
            return chained_service
        else:
            logger.debug(
                "[ApprovalService] No notification channels enabled, falling back to legacy check"
            )

    # Legacy: Check if Telegram is explicitly enabled (backward compatibility)
    telegram_enabled = os.environ.get("AUTOPACK_TELEGRAM_ENABLED", "").lower() == "true"
    if not telegram_enabled:
        logger.debug("[ApprovalService] Telegram not enabled, using NoopApprovalService")
        return NoopApprovalService()

    # Check for required config
    bot_token = os.environ.get("AUTOPACK_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("AUTOPACK_TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning(
            "[ApprovalService] Telegram enabled but missing BOT_TOKEN or CHAT_ID, "
            "using NoopApprovalService"
        )
        return NoopApprovalService()

    # Import here to avoid circular dependency and optional dependency
    from .telegram import TelegramApprovalService

    logger.info("[ApprovalService] Using TelegramApprovalService (legacy single-channel)")
    return TelegramApprovalService(bot_token=bot_token, chat_id=chat_id)
