"""Model approval callback handler for Telegram webhooks (IMP-NOTIFY-001).

Processes approval/rejection decisions from Telegram callbacks and updates
model validation status accordingly.

Flow:
1. User clicks Approve/Reject button in Telegram
2. Callback received at webhook endpoint
3. Handler processes decision
4. Model registry updated
5. Confirmation sent to user
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class ApprovalDecision(str, Enum):
    """Model approval decision."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ModelApprovalRequest(BaseModel):
    """Request model from Telegram callback."""

    model_config = ConfigDict(extra="forbid")

    validation_request_id: str = Field(..., description="Unique validation request ID")
    model_name: str = Field(..., description="Name of the model")
    decision: ApprovalDecision = Field(..., description="User's decision")
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[int] = Field(None, description="Telegram user ID from callback")
    message_id: Optional[int] = Field(None, description="Telegram message ID")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "validation_request_id": self.validation_request_id,
            "model_name": self.model_name,
            "decision": self.decision.value,
            "decided_at": self.decided_at.isoformat(),
            "user_id": self.user_id,
            "message_id": self.message_id,
        }


class ModelApprovalResult(BaseModel):
    """Result of processing an approval decision."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether processing succeeded")
    validation_request_id: str = Field(..., description="Request ID")
    model_name: str = Field(..., description="Model name")
    decision: ApprovalDecision = Field(..., description="Decision")
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_reason: Optional[str] = Field(None, description="Error if failed")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Evidence record")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "validation_request_id": self.validation_request_id,
            "model_name": self.model_name,
            "decision": self.decision.value,
            "processed_at": self.processed_at.isoformat(),
            "error_reason": self.error_reason,
            "evidence": self.evidence,
        }


class ModelApprovalHandler:
    """Handle model approval decisions from Telegram callbacks."""

    def __init__(self, approval_storage_path: Optional[str] = None) -> None:
        """Initialize the approval handler.

        Args:
            approval_storage_path: Path to store approval decisions (optional)
        """
        self.approval_storage_path = approval_storage_path or os.getenv(
            "MODEL_APPROVAL_STORAGE_PATH", ".autopack/model_approvals"
        )
        self._approval_history: Dict[str, ModelApprovalRequest] = {}

    def process_approval_callback(
        self,
        validation_request_id: str,
        model_name: str,
        decision_str: str,
        user_id: Optional[int] = None,
        message_id: Optional[int] = None,
    ) -> ModelApprovalResult:
        """Process an approval decision from Telegram callback.

        Args:
            validation_request_id: Validation request ID
            model_name: Name of the model
            decision_str: "approved" or "rejected"
            user_id: Optional Telegram user ID
            message_id: Optional Telegram message ID

        Returns:
            ModelApprovalResult with outcome
        """
        try:
            # Validate decision
            if decision_str.lower() not in ["approved", "rejected"]:
                return ModelApprovalResult(
                    success=False,
                    validation_request_id=validation_request_id,
                    model_name=model_name,
                    decision=ApprovalDecision.REJECTED,
                    error_reason=f"invalid_decision: {decision_str}",
                    evidence={
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "user_id": user_id,
                        "message_id": message_id,
                    },
                )

            decision = (
                ApprovalDecision.APPROVED
                if decision_str.lower() == "approved"
                else ApprovalDecision.REJECTED
            )

            # Create approval request
            approval_request = ModelApprovalRequest(
                validation_request_id=validation_request_id,
                model_name=model_name,
                decision=decision,
                user_id=user_id,
                message_id=message_id,
            )

            # Store approval
            self._approval_history[validation_request_id] = approval_request

            # Log decision
            logger.info(
                f"[ModelApprovalHandler] {model_name} {decision.value} "
                f"(request_id={validation_request_id}, user_id={user_id})"
            )

            return ModelApprovalResult(
                success=True,
                validation_request_id=validation_request_id,
                model_name=model_name,
                decision=decision,
                evidence={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "user_id": user_id,
                    "message_id": message_id,
                    "stored": True,
                },
            )

        except Exception as e:
            logger.error(f"[ModelApprovalHandler] Error processing approval: {e}")
            return ModelApprovalResult(
                success=False,
                validation_request_id=validation_request_id,
                model_name=model_name,
                decision=ApprovalDecision.REJECTED,
                error_reason="exception",
                evidence={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                },
            )

    def get_approval_decision(self, validation_request_id: str) -> Optional[ApprovalDecision]:
        """Get approval decision for a request.

        Args:
            validation_request_id: Request ID to look up

        Returns:
            ApprovalDecision if found, None otherwise
        """
        request = self._approval_history.get(validation_request_id)
        return request.decision if request else None

    def has_approval_decision(self, validation_request_id: str) -> bool:
        """Check if an approval decision exists.

        Args:
            validation_request_id: Request ID to check

        Returns:
            True if decision exists
        """
        return validation_request_id in self._approval_history

    def get_approval_history(self) -> Dict[str, ModelApprovalRequest]:
        """Get all approval decisions.

        Returns:
            Dict mapping request IDs to approval requests
        """
        return dict(self._approval_history)

    def clear_approval_history(self) -> None:
        """Clear approval history (for testing)."""
        self._approval_history.clear()


def parse_telegram_callback_data(callback_data: str) -> Optional[tuple[str, str]]:
    """Parse Telegram callback data for model approval.

    Expected format: "model_{approve|reject}:{validation_request_id}"

    Args:
        callback_data: Raw callback data from Telegram

    Returns:
        Tuple of (decision, validation_request_id) or None if invalid
    """
    if not callback_data:
        return None

    try:
        if callback_data.startswith("model_approve:"):
            decision = "approved"
            request_id = callback_data[len("model_approve:") :]
            return (decision, request_id)
        elif callback_data.startswith("model_reject:"):
            decision = "rejected"
            request_id = callback_data[len("model_reject:") :]
            return (decision, request_id)
    except Exception as e:
        logger.warning(f"[ModelApprovalHandler] Failed to parse callback: {e}")

    return None
