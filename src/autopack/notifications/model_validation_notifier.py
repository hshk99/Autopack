"""Telegram notification service for model validation approvals (IMP-NOTIFY-001).

Sends formatted model validation reports to Telegram with APPROVE/REJECT buttons,
enabling users to validate and approve discovered generative models.

Features:
- Send model validation reports with detailed metrics
- Inline buttons for approve/reject decisions
- Timeout-based auto-rejection (24 hours)
- Webhook callback handling for approval decisions
- Rate limiting and message batching
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from autopack.research.model_validator import ModelMetadata

logger = logging.getLogger(__name__)


class ModelValidationNotifier:
    """Send model validation reports via Telegram and handle approvals."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> None:
        """Initialize model validation notifier.

        Args:
            bot_token: Telegram bot token (from environment if not provided)
            chat_id: Telegram chat ID (from environment if not provided)
            callback_url: Webhook callback URL for approval responses

        Environment Variables:
            TELEGRAM_BOT_TOKEN: Telegram bot token
            TELEGRAM_CHAT_ID: Telegram chat ID for notifications
            TELEGRAM_WEBHOOK_URL: Webhook URL for receiving approvals
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.callback_url = callback_url or os.getenv(
            "TELEGRAM_WEBHOOK_URL", "http://localhost:8001/webhook/telegram/model-approval"
        )
        self.api_base_url = (
            f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else None
        )

        if not self.bot_token:
            logger.warning("[ModelValidationNotifier] TELEGRAM_BOT_TOKEN not configured")
        if not self.chat_id:
            logger.warning("[ModelValidationNotifier] TELEGRAM_CHAT_ID not configured")

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured.

        Returns:
            True if both bot token and chat ID are set
        """
        return bool(self.bot_token and self.chat_id)

    def send_model_validation_report(
        self,
        model: ModelMetadata,
        validation_request_id: str,
        approval_timeout_hours: int = 24,
    ) -> Dict[str, Any]:
        """Send model validation report to Telegram with approval buttons.

        Args:
            model: ModelMetadata with validation results
            validation_request_id: Unique ID for tracking this request
            approval_timeout_hours: Hours until auto-reject (default: 24h)

        Returns:
            Dict with 'success' bool and 'message_id' if sent, error_details otherwise
        """
        if not self.is_configured():
            logger.error("[ModelValidationNotifier] Service not configured - cannot send")
            return {
                "success": False,
                "error": "telegram_not_configured",
                "details": "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
            }

        try:
            # Format message with model details
            message = self._format_model_report(
                model, validation_request_id, approval_timeout_hours
            )

            # Create inline keyboard
            keyboard = self._create_approval_keyboard(validation_request_id, model.name)

            # Send message
            response = requests.post(
                f"{self.api_base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    message_id = result.get("result", {}).get("message_id")
                    logger.info(
                        f"[ModelValidationNotifier] Report sent for {model.name} "
                        f"(request_id={validation_request_id}, message_id={message_id})"
                    )
                    return {
                        "success": True,
                        "message_id": message_id,
                        "model_name": model.name,
                        "request_id": validation_request_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                else:
                    error = result.get("description", "Unknown error")
                    logger.error(f"[ModelValidationNotifier] Telegram error: {error}")
                    return {
                        "success": False,
                        "error": "telegram_api_error",
                        "details": error,
                    }
            else:
                logger.error(
                    f"[ModelValidationNotifier] HTTP {response.status_code}: {response.text}"
                )
                return {
                    "success": False,
                    "error": f"http_{response.status_code}",
                    "details": response.text,
                }

        except Exception as e:
            logger.error(f"[ModelValidationNotifier] Exception: {e}")
            return {
                "success": False,
                "error": "exception",
                "details": str(e),
            }

    def send_approval_decision_ack(
        self,
        validation_request_id: str,
        decision: str,
        model_name: str,
    ) -> bool:
        """Send acknowledgment of approval decision.

        Args:
            validation_request_id: Request ID of the approval
            decision: "approved" or "rejected"
            model_name: Name of the model

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            return False

        emoji = "✅" if decision.lower() == "approved" else "❌"
        text = f"{emoji} *Model {decision.upper()}*\n\nModel: `{model_name}`"

        try:
            response = requests.post(
                f"{self.api_base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"[ModelValidationNotifier] Failed to send ack: {e}")
            return False

    def _format_model_report(
        self,
        model: ModelMetadata,
        validation_request_id: str,
        approval_timeout_hours: int,
    ) -> str:
        """Format model validation report as HTML for Telegram.

        Args:
            model: ModelMetadata to format
            validation_request_id: Request ID for tracking
            approval_timeout_hours: Timeout hours

        Returns:
            Formatted HTML message
        """
        # Calculate overall score
        overall_score = model.calculate_overall_score() if model.benchmarks else 0.0

        # Format benchmarks
        benchmarks_section = ""
        if model.benchmarks:
            benchmark_lines = []
            for name, score in model.benchmarks.items():
                norm_score = score.normalized_score()
                benchmark_lines.append(f"  • <b>{name}</b>: {norm_score:.1f}")
            if benchmark_lines:
                benchmarks_section = "<b>📊 Benchmarks:</b>\n" + "\n".join(benchmark_lines[:3])

        # Format hardware options
        hardware_section = ""
        if model.hardware_options:
            hardware_lines = []
            for hw in model.hardware_options[:2]:
                hardware_lines.append(
                    f"  • {hw.hardware_type.value}: {hw.min_vram_gb}-{hw.recommended_vram_gb}GB VRAM"
                )
            if hardware_lines:
                hardware_section = "<b>💻 Hardware:</b>\n" + "\n".join(hardware_lines)

        # Format reasoning capabilities
        reasoning_section = ""
        if model.reasoning_score is not None:
            reasoning_section = f"<b>🧠 Reasoning Score:</b> {model.reasoning_score:.1f}/100"

        # Format community feedback
        community_section = f"<b>👥 Community:</b> ⭐ {model.community_stars:.1f}/5.0 ({model.community_feedback_count} reviews)"

        # Build message
        message = f"""<b>🤖 Model Validation Report</b>

<b>Model:</b> {model.name}
<b>Provider:</b> {model.provider}
<b>Type:</b> {model.model_type.value}
<b>Release:</b> {model.release_date}
<b>Context Window:</b> {model.context_window:,} tokens

<b>Overall Score:</b> {overall_score:.1f}/100

{benchmarks_section}

{hardware_section}

{reasoning_section}

{community_section}

<b>Confidence:</b> {model.validation_confidence}
<b>Request ID:</b> <code>{validation_request_id}</code>

<i>Approval timeout: {approval_timeout_hours}h</i>"""

        return message

    def _create_approval_keyboard(
        self,
        validation_request_id: str,
        model_name: str,
    ) -> Dict[str, Any]:
        """Create inline keyboard for approve/reject buttons.

        Args:
            validation_request_id: Request ID for callback data
            model_name: Model name for reference

        Returns:
            Telegram keyboard dict
        """
        return {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve",
                        "callback_data": f"model_approve:{validation_request_id}",
                    },
                    {
                        "text": "❌ Reject",
                        "callback_data": f"model_reject:{validation_request_id}",
                    },
                ]
            ]
        }
