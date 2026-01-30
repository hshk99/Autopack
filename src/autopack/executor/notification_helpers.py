"""
Notification Helpers Module

Extracted from autonomous_executor.py as part of IMP-GOD-001.

Handles Telegram notifications for:
- Large deletion warnings (100-200 lines)
- Phase failures and stuck phases

Key responsibilities:
- Send informational notifications for large deletions
- Send failure notifications when phases fail
- Format notification messages with appropriate emojis and metadata
"""

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class NotificationHelper:
    """Handles Telegram notifications for executor events.

    IMP-GOD-001: Extracted from AutonomousExecutor to reduce god file complexity.
    """

    def __init__(self, run_id: str):
        """Initialize notification helper.

        Args:
            run_id: Run identifier for context in messages
        """
        self.run_id = run_id

    def send_deletion_notification(self, phase_id: str, quality_report: Any) -> None:
        """
        Send informational Telegram notification for large deletions (100-200 lines).
        This is notification-only - does not block execution.

        Args:
            phase_id: Phase identifier
            quality_report: QualityReport with risk assessment
        """
        try:
            from autopack.notifications.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()

            if not notifier.is_configured():
                return  # Silently skip if not configured

            # Extract deletion info from risk assessment
            risk_assessment = quality_report.risk_assessment
            if not risk_assessment:
                return

            metadata = risk_assessment.get("metadata", {})
            checks = risk_assessment.get("checks", {})
            net_deletion = checks.get("net_deletion", 0)
            loc_removed = metadata.get("loc_removed", 0)
            loc_added = metadata.get("loc_added", 0)
            risk_level = risk_assessment.get("risk_level", "unknown")
            risk_score = risk_assessment.get("risk_score", 0)

            # Determine emoji based on risk level
            risk_emoji = {
                "low": "\u2705",  # Green check
                "medium": "\u26a0\ufe0f",  # Warning
                "high": "\U0001f534",  # Red circle
                "critical": "\U0001f6a8",  # Siren
            }.get(
                risk_level, "\u2753"
            )  # Question mark

            # Format message
            message = (
                f"\U0001f4ca *Autopack Deletion Notification*\\n\\n"
                f"*Run*: `{self.run_id}`\\n"
                f"*Phase*: `{phase_id}`\\n"
                f"*Risk*: {risk_emoji} {risk_level.upper()} (score: {risk_score}/100)\\n\\n"
                f"*Net Deletion*: {net_deletion} lines\\n"
                f"  \u251c\u2500 Removed: {loc_removed}\\n"
                f"  \u2514\u2500 Added: {loc_added}\\n\\n"
                f"\u2139\ufe0f _This is informational only. Execution continues automatically._\\n\\n"
                f"_Time_: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

            # Send notification (no buttons needed, just FYI)
            notifier.send_completion_notice(phase_id=phase_id, status="info", message=message)

            logger.info(f"[{phase_id}] Sent deletion notification to Telegram (informational only)")

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to send deletion notification: {e}")

    def send_phase_failure_notification(self, phase_id: str, reason: str) -> None:
        """
        Send Telegram notification when a phase fails or gets stuck.

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED", "BUILDER_FAILED")
        """
        try:
            from autopack.notifications.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()

            if not notifier.is_configured():
                return  # Silently skip if not configured

            # Determine emoji based on failure type
            emoji = "\u274c"  # Red X
            if "EXHAUSTED" in reason:
                emoji = "\U0001f501"  # Retry arrows
            elif "TIMEOUT" in reason:
                emoji = "\u23f1\ufe0f"  # Stopwatch
            elif "STUCK" in reason:
                emoji = "\u26a0\ufe0f"  # Warning

            # Format message
            message = (
                f"{emoji} *Autopack Phase Failed*\\n\\n"
                f"*Run*: `{self.run_id}`\\n"
                f"*Phase*: `{phase_id}`\\n"
                f"*Reason*: {reason}\\n\\n"
                f"The executor has halted. Please review the logs and take action.\\n\\n"
                f"_Time_: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

            # Send notification (no buttons needed for failures, just FYI)
            notifier.send_completion_notice(phase_id=phase_id, status="failed", message=message)

            logger.info(f"[{phase_id}] Sent failure notification to Telegram")

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to send Telegram notification: {e}")
