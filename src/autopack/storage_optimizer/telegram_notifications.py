"""
Telegram notifications for Storage Optimizer.

Extends existing TelegramNotifier for storage-specific workflows:
- Scan completion notifications
- Inline approval buttons
- Execution status updates

Usage:
    from autopack.storage_optimizer.telegram_notifications import StorageTelegramNotifier
    from autopack.storage_optimizer.db import get_candidate_stats_by_category

    notifier = StorageTelegramNotifier()
    stats = get_candidate_stats_by_category(db, scan_id)
    notifier.send_scan_completion(scan, stats)
"""

import logging
import requests
from typing import Dict
from autopack.notifications.telegram_notifier import TelegramNotifier
from autopack.models import StorageScan

logger = logging.getLogger(__name__)


class StorageTelegramNotifier(TelegramNotifier):
    """Telegram notifications for storage scans."""

    def send_scan_completion(
        self,
        scan: StorageScan,
        category_stats: Dict[str, Dict]
    ) -> bool:
        """
        Send scan completion notification with approval buttons.

        Args:
            scan: StorageScan database record
            category_stats: Stats by category from get_candidate_stats_by_category()
                Example: {
                    'dev_caches': {'count': 15, 'total_size_bytes': 20000000000},
                    'diagnostics_logs': {'count': 50, 'total_size_bytes': 5000000000}
                }

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            logger.error("[Telegram] Not configured - cannot send scan notification")
            return False

        # Format message
        message = self._format_scan_summary(scan, category_stats)

        # Create inline keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve All",
                        "callback_data": f"storage_approve_all:{scan.id}"
                    },
                    {
                        "text": "👀 View Details",
                        "callback_data": f"storage_details:{scan.id}"
                    }
                ],
                [
                    {
                        "text": "⏭️ Skip This Scan",
                        "callback_data": f"storage_skip:{scan.id}"
                    }
                ]
            ]
        }

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }, timeout=10)

            if response.status_code == 200:
                logger.info(f"[Telegram] Scan notification sent for scan {scan.id}")
                return True
            else:
                logger.error(f"[Telegram] API error: {response.status_code} {response.text}")
                return False

        except Exception as e:
            logger.error(f"[Telegram] Failed to send scan notification: {e}")
            return False

    def send_execution_complete(
        self,
        scan_id: int,
        total_freed_bytes: int,
        successful: int,
        failed: int,
        skipped: int
    ) -> bool:
        """
        Send execution completion notification.

        Args:
            scan_id: Scan ID that was executed
            total_freed_bytes: Total bytes freed
            successful: Number of successfully deleted items
            failed: Number of failed deletions
            skipped: Number of skipped items

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            return False

        freed_gb = total_freed_bytes / (1024**3)

        # Choose emoji based on success rate
        if failed == 0:
            emoji = "✅"
        elif failed < successful:
            emoji = "⚠️"
        else:
            emoji = "❌"

        message = (
            f"{emoji} *Storage Cleanup Complete*\n\n"
            f"Scan ID: `{scan_id}`\n"
            f"Freed: {freed_gb:.2f} GB\n"
            f"Successful: {successful} items\n"
            f"Failed: {failed} items\n"
            f"Skipped: {skipped} items\n\n"
            f"_Deleted items are in Recycle Bin (can be restored)_"
        )

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)

            if response.status_code == 200:
                logger.info(f"[Telegram] Execution notification sent for scan {scan_id}")
                return True
            else:
                logger.error(f"[Telegram] API error: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"[Telegram] Failed to send execution notification: {e}")
            return False

    def send_approval_confirmation(
        self,
        scan_id: int,
        approved_count: int,
        approved_size_gb: float
    ) -> bool:
        """Send confirmation after user approves candidates."""
        if not self.is_configured():
            return False

        message = (
            f"✅ *Approval Confirmed*\n\n"
            f"Scan ID: `{scan_id}`\n"
            f"Approved: {approved_count} items\n"
            f"Size: {approved_size_gb:.2f} GB\n\n"
            f"Cleanup will execute on next scheduled run.\n"
            f"_Manual execution:_ `python scripts/storage/scan_and_report.py --execute --scan-id {scan_id}`"
        )

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)

            return response.status_code == 200

        except Exception as e:
            logger.error(f"[Telegram] Failed to send approval confirmation: {e}")
            return False

    def _format_scan_summary(
        self,
        scan: StorageScan,
        category_stats: Dict[str, Dict]
    ) -> str:
        """
        Format scan summary message.

        Args:
            scan: StorageScan database record
            category_stats: Category statistics

        Returns:
            Formatted Markdown message
        """
        potential_savings_gb = scan.potential_savings_bytes / (1024**3)

        # Category breakdown (limit to top 5)
        category_lines = []
        sorted_categories = sorted(
            category_stats.items(),
            key=lambda x: x[1]['total_size_bytes'],
            reverse=True
        )

        for category, stats in sorted_categories[:5]:
            count = stats['count']
            size_gb = stats['total_size_bytes'] / (1024**3)
            category_lines.append(f"  • {category}: {count} items ({size_gb:.1f} GB)")

        if len(sorted_categories) > 5:
            remaining = len(sorted_categories) - 5
            category_lines.append(f"  _...and {remaining} more categories_")

        category_summary = "\n".join(category_lines) if category_lines else "  _No cleanup candidates_"

        # Format timestamp
        timestamp_str = scan.timestamp.strftime('%Y-%m-%d %H:%M')

        message = (
            f"📊 *Storage Scan Complete*\n\n"
            f"Target: `{scan.scan_target}`\n"
            f"Scanned: {scan.total_items_scanned:,} items\n"
            f"Total Size: {scan.total_size_bytes / (1024**3):.1f} GB\n\n"
            f"💾 *Cleanup Opportunities*\n"
            f"Potential Savings: {potential_savings_gb:.2f} GB\n"
            f"Candidates: {scan.cleanup_candidates_count} items\n\n"
            f"*By Category*:\n{category_summary}\n\n"
            f"_Scan ID: {scan.id} • {timestamp_str}_"
        )

        return message


def answer_telegram_callback(bot_token: str, callback_id: str, text: str, show_alert: bool = False) -> bool:
    """
    Answer Telegram callback query (removes loading state from button).

    Args:
        bot_token: Telegram bot token
        callback_id: Callback query ID from webhook
        text: Response text to show user
        show_alert: Show as popup alert vs. toast notification

    Returns:
        True if callback answered successfully
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        response = requests.post(url, json={
            "callback_query_id": callback_id,
            "text": text,
            "show_alert": show_alert
        }, timeout=5)

        return response.status_code == 200

    except Exception as e:
        logger.error(f"[Telegram] Failed to answer callback: {e}")
        return False
