"""Telegram approval service implementation (BUILD-181 Phase 6).

Provides Telegram-based approval requests for pivot-impacting actions.
Disabled by default, requires explicit configuration.
Never active in CI.

Properties:
- Pivot-only triggers
- Safe failure: records evidence on misconfiguration
- Formats messages with anchor_id + pivot section + diff summary
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .service import ApprovalRequest, ApprovalResult, ApprovalService

logger = logging.getLogger(__name__)


class TelegramApprovalService(ApprovalService):
    """Telegram-based approval service.

    Sends approval requests to configured Telegram chat.
    Fails safely if misconfigured (records evidence, halts if required).
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        """Initialize Telegram service.

        Args:
            bot_token: Telegram bot token
            chat_id: Telegram chat ID to send requests to
        """
        self._bot_token = bot_token
        self._chat_id = chat_id

    def is_enabled(self) -> bool:
        """Check if service is properly configured."""
        return bool(self._bot_token and self._chat_id)

    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval request to Telegram.

        Args:
            request: ApprovalRequest with details

        Returns:
            ApprovalResult with outcome
        """
        # Check configuration
        if not self.is_enabled():
            logger.warning(
                f"[TelegramApproval] Request {request.request_id} cannot be sent: "
                f"service misconfigured"
            )
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="telegram_misconfigured",
                evidence={
                    "service": "telegram",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request.request_id,
                    "error": "Missing bot_token or chat_id",
                    "request_data": request.to_dict(),
                },
            )

        # Format message
        message = self._format_message(request)

        # Send message
        try:
            success = self._send_message(message)

            if success:
                logger.info(f"[TelegramApproval] Request {request.request_id} sent successfully")
                return ApprovalResult(
                    success=True,
                    approved=None,  # Pending human response
                    error_reason=None,
                    evidence={
                        "service": "telegram",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "request_id": request.request_id,
                        "chat_id": self._chat_id,
                        "message_sent": True,
                    },
                )
            else:
                return ApprovalResult(
                    success=False,
                    approved=None,
                    error_reason="telegram_send_failed",
                    evidence={
                        "service": "telegram",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "request_id": request.request_id,
                        "error": "Failed to send message",
                    },
                )

        except Exception as e:
            logger.error(f"[TelegramApproval] Error sending request: {e}")
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="telegram_error",
                evidence={
                    "service": "telegram",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "request_id": request.request_id,
                    "error": str(e),
                },
            )

    def _format_message(self, request: ApprovalRequest) -> str:
        """Format approval request as Telegram message.

        Includes:
        - Request ID
        - Run/Phase context
        - Trigger reason
        - Affected pivots
        - Diff summary
        """
        # Build pivot section
        pivot_section = ""
        if request.affected_pivots:
            pivot_section = f"\n🎯 Affected Pivots: {', '.join(request.affected_pivots)}"

        # Build diff summary
        diff_section = ""
        if request.diff_summary:
            diff_lines = []
            for key, value in request.diff_summary.items():
                if isinstance(value, list):
                    diff_lines.append(f"  • {key}: {', '.join(str(v) for v in value[:3])}")
                else:
                    diff_lines.append(f"  • {key}: {value}")
            if diff_lines:
                diff_section = "\n📋 Changes:\n" + "\n".join(diff_lines[:5])

        # Format reason
        reason_emoji = {
            "pivot_intention_change": "🔄",
            "pivot_constraint_violation": "⚠️",
            "governance_escalation": "🚨",
        }
        emoji = reason_emoji.get(request.trigger_reason.value, "❓")

        message = f"""🔐 Approval Required

{emoji} Reason: {request.trigger_reason.value.replace("_", " ").title()}

📌 Request ID: {request.request_id}
🏃 Run: {request.run_id}
📍 Phase: {request.phase_id}
{pivot_section}

📝 Description:
{request.description}
{diff_section}

⏰ {request.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}

Reply with /approve {request.request_id} or /deny {request.request_id}"""

        return message

    def _send_message(self, message: str) -> bool:
        """Send message to Telegram.

        Args:
            message: Message text to send

        Returns:
            True if sent successfully
        """
        try:
            import json
            import urllib.parse
            import urllib.request

            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            data = urllib.parse.urlencode(
                {
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }
            ).encode()

            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode())
                return result.get("ok", False)

        except Exception as e:
            logger.error(f"[TelegramApproval] HTTP error: {e}")
            return False
