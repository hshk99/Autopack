"""Approval service modules (BUILD-181 Phase 6, IMP-REL-001, IMP-LOOP-014).

Provides pivot-only approval triggers and multi-channel notification.
Supports Telegram -> Email -> SMS fallback chain for reliability.
Disabled by default, requires explicit configuration.
Never active in CI.

IMP-LOOP-014: Adds human approval feedback capture and analysis for
improving task generation through pattern recognition.
"""

from .feedback_analyzer import (ApprovalFeedback, ApprovalFeedbackAnalyzer,
                                HumanAction, PriorityWeightUpdate,
                                RejectionPattern)
from .notification_chain import (EmailChannel, NotificationChain,
                                 NotificationChainResult, NotificationChannel,
                                 SMSChannel, TelegramChannel,
                                 create_notification_chain)
from .service import (ApprovalRequest, ApprovalResult, ApprovalService,
                      ApprovalTriggerReason, ChainedApprovalService,
                      NoopApprovalService, get_approval_service,
                      should_trigger_approval)

__all__ = [
    # Core approval types
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalService",
    "ApprovalTriggerReason",
    "ChainedApprovalService",
    "NoopApprovalService",
    "get_approval_service",
    "should_trigger_approval",
    # IMP-REL-001: Notification chain
    "NotificationChain",
    "NotificationChainResult",
    "NotificationChannel",
    "TelegramChannel",
    "EmailChannel",
    "SMSChannel",
    "create_notification_chain",
    # IMP-LOOP-014: Feedback capture and analysis
    "ApprovalFeedback",
    "ApprovalFeedbackAnalyzer",
    "HumanAction",
    "PriorityWeightUpdate",
    "RejectionPattern",
]
