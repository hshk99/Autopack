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
    approved: Optional[bool] = Field(default=None, description="Approval decision (None if pending)")
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


def get_approval_service() -> ApprovalService:
    """Get the configured approval service.

    Logic:
    1. Never return TelegramApprovalService in CI
    2. Require explicit AUTOPACK_TELEGRAM_ENABLED=true
    3. Require AUTOPACK_TELEGRAM_BOT_TOKEN and AUTOPACK_TELEGRAM_CHAT_ID

    Returns:
        ApprovalService instance
    """
    # Never active in CI
    if _is_ci_environment():
        logger.debug("[ApprovalService] CI environment detected, using NoopApprovalService")
        return NoopApprovalService()

    # Check if Telegram is explicitly enabled
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

    logger.info("[ApprovalService] Using TelegramApprovalService")
    return TelegramApprovalService(bot_token=bot_token, chat_id=chat_id)
