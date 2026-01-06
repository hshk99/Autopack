"""Approval service modules (BUILD-181 Phase 6).

Provides pivot-only approval triggers and Telegram integration.
Disabled by default, requires explicit configuration.
Never active in CI.
"""

from .service import (
    ApprovalRequest,
    ApprovalResult,
    ApprovalService,
    ApprovalTriggerReason,
    NoopApprovalService,
    get_approval_service,
    should_trigger_approval,
)

__all__ = [
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalService",
    "ApprovalTriggerReason",
    "NoopApprovalService",
    "get_approval_service",
    "should_trigger_approval",
]
