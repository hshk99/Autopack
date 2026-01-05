"""Telegram notification service for Autopack approval requests.

Uses your existing CodeCompassBot (@CodeSherpaBot) to send approval requests
to your phone when Autopack needs human approval for risky changes.
"""

import os
import logging
import requests
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send approval requests via Telegram bot."""

    def __init__(self):
        """
        Initialize Telegram notifier.

        Required environment variables:
            TELEGRAM_BOT_TOKEN: Your bot token from @BotFather
            TELEGRAM_CHAT_ID: Your Telegram user ID (chat with your bot to get this)
            AUTOPACK_CALLBACK_URL: Callback URL for approvals (default: http://localhost:8001)

        Optional:
            NGROK_URL: Your ngrok URL (e.g., https://harrybot.ngrok.app)
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.callback_url = os.getenv("AUTOPACK_CALLBACK_URL", "http://localhost:8001")
        self.ngrok_url = os.getenv("NGROK_URL", "https://harrybot.ngrok.app")

        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set - notifications disabled")
        if not self.chat_id:
            logger.warning("TELEGRAM_CHAT_ID not set - notifications disabled")

    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.bot_token and self.chat_id)

    def send_approval_request(
        self, phase_id: str, deletion_info: Dict, run_id: str = "", context: str = ""
    ) -> bool:
        """
        Send approval request to Telegram.

        Args:
            phase_id: Phase identifier
            deletion_info: {
                'net_deletion': int,
                'loc_removed': int,
                'loc_added': int,
                'files': list,
                'risk_level': str,
                'risk_score': int
            }
            run_id: Optional run identifier
            context: Optional context (e.g., "troubleshooting", "refactoring")

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            logger.error("Telegram not configured - cannot send notification")
            return False

        # Format message
        message = self._format_approval_message(phase_id, deletion_info, run_id, context)

        # Create inline keyboard with Approve/Reject buttons
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{phase_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{phase_id}"},
                ]
            ]
        }

        try:
            # Send message via Telegram API
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard,
                },
                timeout=10,
            )

            if response.status_code == 200:
                logger.info(f"[Telegram] Approval request sent for {phase_id}")
                return True
            else:
                logger.error(f"[Telegram] API error: {response.status_code} {response.text}")
                return False

        except Exception as e:
            logger.error(f"[Telegram] Failed to send notification: {e}")
            return False

    def send_completion_notice(
        self, phase_id: str, status: str, message: str = ""  # "approved", "rejected", "timeout"
    ) -> bool:
        """Send completion notice after approval decision."""
        if not self.is_configured():
            return False

        emoji = {"approved": "✅", "rejected": "❌", "timeout": "⏱️"}.get(status, "ℹ️")

        text = (
            f"{emoji} *Autopack Update*\n\n" f"Phase: `{phase_id}`\n" f"Status: {status.upper()}\n"
        )

        if message:
            text += f"\n{message}"

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"[Telegram] Failed to send completion notice: {e}")
            return False

    def send_pr_approval_request(
        self,
        approval_id: int,
        run_id: str,
        branch: str,
        summary_md: str,
        risk_score: int = 0,
        files_changed: int = 0,
        loc_added: int = 0,
        loc_removed: int = 0,
    ) -> bool:
        """Send PR creation approval request to Telegram.

        Uses inline keyboard buttons with callback_data based on approval_id,
        not phase_id, to avoid collisions and ensure idempotence.

        Args:
            approval_id: Unique approval request ID
            run_id: Run identifier
            branch: Branch name for PR
            summary_md: PR summary (first 200 chars shown)
            risk_score: Risk score 0-100
            files_changed: Number of files changed
            loc_added: Lines added
            loc_removed: Lines removed

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            logger.error("Telegram not configured - cannot send PR approval")
            return False

        # Format message
        risk_emoji = "🔴" if risk_score >= 70 else "⚠️" if risk_score >= 40 else "✅"

        # Truncate summary for Telegram
        summary_preview = summary_md[:200] + "..." if len(summary_md) > 200 else summary_md

        message = (
            f"🔀 *PR Creation Approval Needed*\n\n"
            f"*Run*: `{run_id}`\n"
            f"*Branch*: `{branch}`\n"
            f"*Risk*: {risk_emoji} {risk_score}/100\n"
            f"*Changes*: {files_changed} files (+{loc_added}/-{loc_removed} lines)\n\n"
            f"*Summary*:\n{summary_preview}\n\n"
            f"_Sent: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        )

        # Create inline keyboard with Approve/Reject buttons
        # IMPORTANT: Use approval_id, not phase_id or run_id
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"pr_approve:{approval_id}"},
                    {"text": "❌ Reject", "callback_data": f"pr_reject:{approval_id}"},
                ]
            ]
        }

        try:
            # Send message via Telegram API
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            response = requests.post(
                url,
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard,
                },
                timeout=10,
            )

            if response.status_code == 200:
                logger.info(f"[Telegram] PR approval request sent for approval_id={approval_id}")
                return True
            else:
                logger.error(f"[Telegram] API error: {response.status_code} {response.text}")
                return False

        except Exception as e:
            logger.error(f"[Telegram] Failed to send PR approval: {e}")
            return False

    def _format_approval_message(
        self, phase_id: str, deletion_info: Dict, run_id: str, context: str
    ) -> str:
        """Format approval request message."""

        net_deletion = deletion_info.get("net_deletion", 0)
        loc_removed = deletion_info.get("loc_removed", 0)
        loc_added = deletion_info.get("loc_added", 0)
        risk_level = deletion_info.get("risk_level", "unknown")
        risk_score = deletion_info.get("risk_score", 0)
        files = deletion_info.get("files", [])

        # Risk emoji
        risk_emoji = {"critical": "🚨", "high": "🔴", "medium": "⚠️", "low": "✅"}.get(
            risk_level.lower(), "❓"
        )

        # Context-specific warning
        context_note = ""
        if context in ["troubleshoot", "debug", "fix"]:
            context_note = "\n⚠️ *Troubleshooting context*: Large deletions unexpected"

        # File list (limit to 3)
        file_list = ""
        if files:
            shown_files = files[:3]
            file_list = "\n*Files*:\n" + "\n".join(f"  • `{f}`" for f in shown_files)
            if len(files) > 3:
                file_list += f"\n  _...and {len(files) - 3} more_"

        message = (
            f"⚠️ *Autopack Approval Needed*\n\n"
            f"*Phase*: `{phase_id}`\n"
            f"*Run*: `{run_id or 'N/A'}`\n"
            f"*Risk*: {risk_emoji} {risk_level.upper()} (score: {risk_score}/100)\n"
            f"*Net Deletion*: {net_deletion} lines\n"
            f"  ├─ Removed: {loc_removed}\n"
            f"  └─ Added: {loc_added}\n"
            f"{file_list}\n"
            f"{context_note}\n"
            f"_Sent: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC_"
        )

        return message


def setup_telegram_webhook(bot_token: str, ngrok_url: str) -> bool:
    """
    Set up Telegram webhook to receive button callbacks.

    This allows Telegram to POST to your Autopack server when you tap
    Approve/Reject buttons.

    Args:
        bot_token: Your Telegram bot token
        ngrok_url: Your ngrok public URL (e.g., https://harrybot.ngrok.app)

    Returns:
        True if webhook set successfully

    Example:
        >>> setup_telegram_webhook(
        ...     bot_token="YOUR_BOT_TOKEN",
        ...     ngrok_url="https://harrybot.ngrok.app"
        ... )
    """
    webhook_url = f"{ngrok_url}/telegram/webhook"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        response = requests.post(
            url, json={"url": webhook_url, "allowed_updates": ["callback_query", "message"]}
        )

        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                logger.info(f"[Telegram] Webhook set to {webhook_url}")
                return True
            else:
                logger.error(f"[Telegram] Webhook failed: {result}")
                return False
        else:
            logger.error(f"[Telegram] API error: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"[Telegram] Failed to set webhook: {e}")
        return False


def answer_telegram_callback(
    bot_token: str,
    callback_id: str,
    text: str,
    show_alert: bool = False,
) -> bool:
    """
    Answer Telegram callback query (removes loading state from inline button).

    Args:
        bot_token: Telegram bot token
        callback_id: callback_query.id from webhook payload
        text: Message to show user (toast or alert)
        show_alert: If True, show as popup alert instead of toast

    Returns:
        True if callback answered successfully
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        response = requests.post(
            url,
            json={
                "callback_query_id": callback_id,
                "text": text,
                "show_alert": show_alert,
            },
            timeout=5,
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"[Telegram] Failed to answer callback: {e}")
        return False


def get_my_chat_id(bot_token: str) -> Optional[str]:
    """
    Helper to get your Telegram chat ID.

    Instructions:
    1. Send a message to your bot (@CodeSherpaBot)
    2. Run this function
    3. It will return your chat ID

    Args:
        bot_token: Your bot token

    Returns:
        Your chat ID or None if not found
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url)

        if response.status_code == 200:
            result = response.json()
            if result.get("ok") and result.get("result"):
                # Get the most recent message
                updates = result["result"]
                if updates:
                    chat_id = updates[-1]["message"]["chat"]["id"]
                    username = updates[-1]["message"]["from"].get("username", "N/A")
                    logger.info(f"[Telegram] Found chat ID: {chat_id} (user: @{username})")
                    return str(chat_id)

        logger.warning("[Telegram] No recent messages found. Send a message to your bot first.")
        return None

    except Exception as e:
        logger.error(f"[Telegram] Failed to get chat ID: {e}")
        return None
