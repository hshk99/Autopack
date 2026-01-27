"""IMP-REL-001: Multi-channel notification with fallback support.

Provides NotificationChain with Telegram -> Email -> SMS fallback
for approval notifications. Ensures single point of failure is eliminated
by automatically trying backup channels when primary fails.

Configuration (env vars):
- AUTOPACK_NOTIFICATION_EMAIL_ENABLED=true
- AUTOPACK_NOTIFICATION_EMAIL_HOST=smtp.example.com
- AUTOPACK_NOTIFICATION_EMAIL_PORT=587
- AUTOPACK_NOTIFICATION_EMAIL_USER=user@example.com
- AUTOPACK_NOTIFICATION_EMAIL_PASSWORD=password
- AUTOPACK_NOTIFICATION_EMAIL_FROM=autopack@example.com
- AUTOPACK_NOTIFICATION_EMAIL_TO=admin@example.com

- AUTOPACK_NOTIFICATION_SMS_ENABLED=true
- AUTOPACK_NOTIFICATION_SMS_PROVIDER=twilio  # or sns
- AUTOPACK_NOTIFICATION_SMS_ACCOUNT_SID=...  # Twilio
- AUTOPACK_NOTIFICATION_SMS_AUTH_TOKEN=...   # Twilio
- AUTOPACK_NOTIFICATION_SMS_FROM_NUMBER=+1234567890
- AUTOPACK_NOTIFICATION_SMS_TO_NUMBER=+0987654321
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from autopack.utils import create_safe_error_message
from .service import ApprovalRequest, ApprovalResult

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    def send(self, request: ApprovalRequest) -> ApprovalResult:
        """Send notification through this channel.

        Args:
            request: ApprovalRequest to send

        Returns:
            ApprovalResult indicating success/failure
        """
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if channel is properly configured."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Channel name for logging."""
        pass


@dataclass
class NotificationChainResult:
    """Result of notification chain execution."""

    success: bool
    successful_channel: Optional[str] = None
    failed_channels: List[str] = field(default_factory=list)
    error_details: Dict[str, str] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


class NotificationChain:
    """Multi-channel notification with fallback support.

    IMP-REL-001: Tries channels in sequence until one succeeds.
    Default order: Telegram -> Email -> SMS

    Example:
        chain = NotificationChain()
        chain.add_channel(TelegramChannel(...))
        chain.add_channel(EmailChannel(...))
        chain.add_channel(SMSChannel(...))

        result = chain.send(approval_request)
        if result.success:
            print(f"Sent via {result.successful_channel}")
    """

    def __init__(self) -> None:
        """Initialize empty notification chain."""
        self._channels: List[NotificationChannel] = []

    def add_channel(self, channel: NotificationChannel) -> "NotificationChain":
        """Add a notification channel to the chain.

        Channels are tried in the order they are added.

        Args:
            channel: NotificationChannel to add

        Returns:
            self for method chaining
        """
        if channel.is_enabled():
            self._channels.append(channel)
            logger.debug(f"[NotificationChain] Added channel: {channel.name}")
        else:
            logger.debug(f"[NotificationChain] Channel {channel.name} not enabled, skipping")
        return self

    def send(self, request: ApprovalRequest) -> NotificationChainResult:
        """Send notification through chain with fallback.

        Tries each enabled channel in sequence until one succeeds.

        Args:
            request: ApprovalRequest to send

        Returns:
            NotificationChainResult with success status and details
        """
        result = NotificationChainResult(
            success=False,
            evidence={
                "request_id": request.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "channels_attempted": [],
            },
        )

        if not self._channels:
            logger.error("[NotificationChain] No enabled channels configured")
            result.error_details["chain"] = "No enabled notification channels"
            return result

        for channel in self._channels:
            result.evidence["channels_attempted"].append(channel.name)

            try:
                logger.info(f"[NotificationChain] Trying channel: {channel.name}")
                channel_result = channel.send(request)

                if channel_result.success:
                    result.success = True
                    result.successful_channel = channel.name
                    result.evidence["successful_channel"] = channel.name
                    result.evidence["channel_evidence"] = channel_result.evidence
                    logger.info(f"[NotificationChain] Successfully sent via {channel.name}")
                    return result
                else:
                    result.failed_channels.append(channel.name)
                    result.error_details[channel.name] = (
                        channel_result.error_reason or "Unknown error"
                    )
                    logger.warning(
                        f"[NotificationChain] Channel {channel.name} failed: "
                        f"{channel_result.error_reason}"
                    )

            except Exception as e:
                result.failed_channels.append(channel.name)
                safe_error = create_safe_error_message(e)
                result.error_details[channel.name] = safe_error
                logger.error(f"[NotificationChain] Channel {channel.name} exception: {safe_error}")

        # All channels failed
        logger.error(f"[NotificationChain] All channels failed for request {request.request_id}")
        return result

    def get_enabled_channels(self) -> List[str]:
        """Get list of enabled channel names."""
        return [c.name for c in self._channels]


class TelegramChannel(NotificationChannel):
    """Telegram notification channel.

    Uses existing Telegram bot configuration.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> None:
        """Initialize Telegram channel.

        Args:
            bot_token: Telegram bot token (or from TELEGRAM_BOT_TOKEN env)
            chat_id: Telegram chat ID (or from TELEGRAM_CHAT_ID env)
        """
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def name(self) -> str:
        return "telegram"

    def is_enabled(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval notification via Telegram."""
        if not self.is_enabled():
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="telegram_not_configured",
                evidence={"channel": "telegram", "error": "Missing bot_token or chat_id"},
            )

        try:
            import json
            import urllib.parse
            import urllib.request

            message = self._format_message(request)

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
                if result.get("ok", False):
                    return ApprovalResult(
                        success=True,
                        approved=None,
                        error_reason=None,
                        evidence={
                            "channel": "telegram",
                            "chat_id": self._chat_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                else:
                    return ApprovalResult(
                        success=False,
                        approved=None,
                        error_reason="telegram_api_error",
                        evidence={"channel": "telegram", "error": result},
                    )

        except Exception as e:
            safe_error = create_safe_error_message(e)
            logger.error(f"[TelegramChannel] Error: {safe_error}")
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="telegram_exception",
                evidence={"channel": "telegram", "error": safe_error},
            )

    def _format_message(self, request: ApprovalRequest) -> str:
        """Format approval request as Telegram message."""
        pivot_section = ""
        if request.affected_pivots:
            pivot_section = f"\n<b>Affected Pivots:</b> {', '.join(request.affected_pivots)}"

        return f"""<b>Approval Required</b>

<b>Request ID:</b> {request.request_id}
<b>Run:</b> {request.run_id}
<b>Phase:</b> {request.phase_id}
<b>Reason:</b> {request.trigger_reason.value.replace("_", " ").title()}
{pivot_section}

<b>Description:</b>
{request.description}

<i>{request.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</i>

Reply with /approve {request.request_id} or /deny {request.request_id}"""


class EmailChannel(NotificationChannel):
    """Email notification channel.

    Sends approval notifications via SMTP.
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None,
        to_email: Optional[str] = None,
        use_tls: bool = True,
    ) -> None:
        """Initialize Email channel.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port (default: 587 for TLS)
            smtp_user: SMTP username
            smtp_password: SMTP password
            from_email: Sender email address
            to_email: Recipient email address
            use_tls: Use TLS encryption (default: True)
        """
        self._smtp_host = smtp_host or os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_HOST")
        self._smtp_port = smtp_port or int(
            os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_PORT", "587")
        )
        self._smtp_user = smtp_user or os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_USER")
        self._smtp_password = smtp_password or os.environ.get(
            "AUTOPACK_NOTIFICATION_EMAIL_PASSWORD"
        )
        self._from_email = from_email or os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_FROM")
        self._to_email = to_email or os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_TO")
        self._use_tls = use_tls
        self._enabled = os.environ.get("AUTOPACK_NOTIFICATION_EMAIL_ENABLED", "").lower() == "true"

    @property
    def name(self) -> str:
        return "email"

    def is_enabled(self) -> bool:
        return bool(
            self._enabled
            and self._smtp_host
            and self._smtp_user
            and self._smtp_password
            and self._from_email
            and self._to_email
        )

    def send(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval notification via email."""
        if not self.is_enabled():
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="email_not_configured",
                evidence={"channel": "email", "error": "Email not fully configured"},
            )

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Autopack] Approval Required: {request.request_id}"
            msg["From"] = self._from_email
            msg["To"] = self._to_email

            # Plain text version
            text_content = self._format_text_message(request)
            # HTML version
            html_content = self._format_html_message(request)

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            # Send email
            context = ssl.create_default_context()

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                if self._use_tls:
                    server.starttls(context=context)
                server.login(self._smtp_user, self._smtp_password)
                server.sendmail(self._from_email, [self._to_email], msg.as_string())

            logger.info(f"[EmailChannel] Sent approval request to {self._to_email}")

            return ApprovalResult(
                success=True,
                approved=None,
                error_reason=None,
                evidence={
                    "channel": "email",
                    "to": self._to_email,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        except Exception as e:
            safe_error = create_safe_error_message(e)
            logger.error(f"[EmailChannel] Error: {safe_error}")
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="email_send_failed",
                evidence={"channel": "email", "error": safe_error},
            )

    def _format_text_message(self, request: ApprovalRequest) -> str:
        """Format as plain text."""
        pivot_section = ""
        if request.affected_pivots:
            pivot_section = f"\nAffected Pivots: {', '.join(request.affected_pivots)}"

        return f"""AUTOPACK APPROVAL REQUIRED

Request ID: {request.request_id}
Run: {request.run_id}
Phase: {request.phase_id}
Reason: {request.trigger_reason.value.replace("_", " ").title()}
{pivot_section}

Description:
{request.description}

Timestamp: {request.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}

To approve, reply to this email with: APPROVE {request.request_id}
To reject, reply with: REJECT {request.request_id}
"""

    def _format_html_message(self, request: ApprovalRequest) -> str:
        """Format as HTML."""
        pivot_section = ""
        if request.affected_pivots:
            pivot_section = (
                f"<p><strong>Affected Pivots:</strong> " f"{', '.join(request.affected_pivots)}</p>"
            )

        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f44336; color: white; padding: 15px; border-radius: 5px; }}
        .content {{ padding: 20px; border: 1px solid #ddd; margin-top: 10px; }}
        .field {{ margin: 10px 0; }}
        .label {{ font-weight: bold; color: #333; }}
        .footer {{ margin-top: 20px; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>Autopack Approval Required</h2>
    </div>
    <div class="content">
        <div class="field">
            <span class="label">Request ID:</span> {request.request_id}
        </div>
        <div class="field">
            <span class="label">Run:</span> {request.run_id}
        </div>
        <div class="field">
            <span class="label">Phase:</span> {request.phase_id}
        </div>
        <div class="field">
            <span class="label">Reason:</span>
            {request.trigger_reason.value.replace("_", " ").title()}
        </div>
        {pivot_section}
        <div class="field">
            <span class="label">Description:</span>
            <p>{request.description}</p>
        </div>
    </div>
    <div class="footer">
        <p>Timestamp: {request.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</p>
        <p>To approve, reply: <code>APPROVE {request.request_id}</code></p>
        <p>To reject, reply: <code>REJECT {request.request_id}</code></p>
    </div>
</body>
</html>
"""


class SMSChannel(NotificationChannel):
    """SMS notification channel.

    Supports Twilio and AWS SNS providers.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        to_number: Optional[str] = None,
    ) -> None:
        """Initialize SMS channel.

        Args:
            provider: SMS provider ('twilio' or 'sns')
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
            from_number: Sender phone number
            to_number: Recipient phone number
        """
        self._provider = provider or os.environ.get("AUTOPACK_NOTIFICATION_SMS_PROVIDER", "twilio")
        self._account_sid = account_sid or os.environ.get("AUTOPACK_NOTIFICATION_SMS_ACCOUNT_SID")
        self._auth_token = auth_token or os.environ.get("AUTOPACK_NOTIFICATION_SMS_AUTH_TOKEN")
        self._from_number = from_number or os.environ.get("AUTOPACK_NOTIFICATION_SMS_FROM_NUMBER")
        self._to_number = to_number or os.environ.get("AUTOPACK_NOTIFICATION_SMS_TO_NUMBER")
        self._enabled = os.environ.get("AUTOPACK_NOTIFICATION_SMS_ENABLED", "").lower() == "true"

    @property
    def name(self) -> str:
        return "sms"

    def is_enabled(self) -> bool:
        if not self._enabled:
            return False

        if self._provider == "twilio":
            return bool(
                self._account_sid and self._auth_token and self._from_number and self._to_number
            )
        elif self._provider == "sns":
            # AWS SNS uses IAM credentials, so just check to_number
            return bool(self._to_number)
        return False

    def send(self, request: ApprovalRequest) -> ApprovalResult:
        """Send approval notification via SMS."""
        if not self.is_enabled():
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="sms_not_configured",
                evidence={"channel": "sms", "error": "SMS not fully configured"},
            )

        message = self._format_message(request)

        if self._provider == "twilio":
            return self._send_twilio(message)
        elif self._provider == "sns":
            return self._send_sns(message)
        else:
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="sms_unknown_provider",
                evidence={"channel": "sms", "error": f"Unknown provider: {self._provider}"},
            )

    def _send_twilio(self, message: str) -> ApprovalResult:
        """Send via Twilio."""
        try:
            import base64
            import json
            import urllib.parse
            import urllib.request

            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"

            data = urllib.parse.urlencode(
                {
                    "From": self._from_number,
                    "To": self._to_number,
                    "Body": message,
                }
            ).encode()

            # Basic auth for Twilio
            credentials = base64.b64encode(
                f"{self._account_sid}:{self._auth_token}".encode()
            ).decode()

            req = urllib.request.Request(
                url,
                data=data,
                headers={"Authorization": f"Basic {credentials}"},
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode())
                if result.get("sid"):
                    logger.info(
                        f"[SMSChannel:Twilio] Sent to {self._to_number}, SID: {result['sid']}"
                    )
                    return ApprovalResult(
                        success=True,
                        approved=None,
                        error_reason=None,
                        evidence={
                            "channel": "sms",
                            "provider": "twilio",
                            "message_sid": result["sid"],
                            "to": self._to_number,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                else:
                    return ApprovalResult(
                        success=False,
                        approved=None,
                        error_reason="twilio_no_sid",
                        evidence={"channel": "sms", "error": result},
                    )

        except Exception as e:
            safe_error = create_safe_error_message(e)
            logger.error(f"[SMSChannel:Twilio] Error: {safe_error}")
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="twilio_exception",
                evidence={"channel": "sms", "provider": "twilio", "error": safe_error},
            )

    def _send_sns(self, message: str) -> ApprovalResult:
        """Send via AWS SNS."""
        try:
            import boto3

            client = boto3.client("sns")
            response = client.publish(
                PhoneNumber=self._to_number,
                Message=message,
            )

            message_id = response.get("MessageId")
            if message_id:
                logger.info(f"[SMSChannel:SNS] Sent to {self._to_number}, ID: {message_id}")
                return ApprovalResult(
                    success=True,
                    approved=None,
                    error_reason=None,
                    evidence={
                        "channel": "sms",
                        "provider": "sns",
                        "message_id": message_id,
                        "to": self._to_number,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            else:
                return ApprovalResult(
                    success=False,
                    approved=None,
                    error_reason="sns_no_message_id",
                    evidence={"channel": "sms", "error": response},
                )

        except ImportError:
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="sns_boto3_missing",
                evidence={"channel": "sms", "error": "boto3 not installed"},
            )
        except Exception as e:
            safe_error = create_safe_error_message(e)
            logger.error(f"[SMSChannel:SNS] Error: {safe_error}")
            return ApprovalResult(
                success=False,
                approved=None,
                error_reason="sns_exception",
                evidence={"channel": "sms", "provider": "sns", "error": safe_error},
            )

    def _format_message(self, request: ApprovalRequest) -> str:
        """Format as SMS (160 char limit friendly)."""
        # Keep it short for SMS
        return (
            f"[Autopack] Approval needed for {request.phase_id}. "
            f"Reason: {request.trigger_reason.value.replace('_', ' ')}. "
            f"ID: {request.request_id[:8]}"
        )


def create_notification_chain() -> NotificationChain:
    """Create notification chain with all configured channels.

    Order: Telegram -> Email -> SMS

    Returns:
        Configured NotificationChain
    """
    chain = NotificationChain()

    # Add Telegram (primary)
    chain.add_channel(TelegramChannel())

    # Add Email (secondary fallback)
    chain.add_channel(EmailChannel())

    # Add SMS (tertiary fallback)
    chain.add_channel(SMSChannel())

    enabled = chain.get_enabled_channels()
    if enabled:
        logger.info(f"[NotificationChain] Enabled channels: {enabled}")
    else:
        logger.warning("[NotificationChain] No notification channels enabled")

    return chain
