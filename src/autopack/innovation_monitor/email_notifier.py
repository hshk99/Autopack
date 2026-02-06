"""
Email notifier for AI innovations.

Template-based email notifications via Gmail SMTP - 0 tokens.
Reuses pattern from idea-genesis-orchestrator/report_sender.py.
"""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from .models import ImprovementAssessment, ScoredInnovation, WeeklySummaryStats

logger = logging.getLogger(__name__)


class EmailNotifier:
    """
    Email notification via Gmail SMTP - 0 tokens.

    Uses same pattern as idea-genesis-orchestrator/report_sender.py.

    Environment variables:
    - SMTP_HOST: smtp.gmail.com (default)
    - SMTP_PORT: 587 (default)
    - SMTP_USER: your-email@gmail.com
    - SMTP_PASSWORD: Gmail App Password (not regular password)
    - EMAIL_TO: recipient email
    """

    EMAIL_SUBJECT_TEMPLATE = "🚀 AI Innovation Alert: {title}"

    EMAIL_HTML_TEMPLATE = """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 600px; margin: 0 auto; }}
            .header {{ background: #4A90D9; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
            .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-radius: 0 0 5px 5px; }}
            .score {{ font-size: 32px; font-weight: bold; color: #2E7D32; }}
            .score-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }}
            .score-item {{ background: white; padding: 10px; border-radius: 5px; text-align: center; }}
            .score-value {{ font-size: 20px; font-weight: bold; color: #333; }}
            .components {{ background: #E3F2FD; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            .rationale {{ font-style: italic; color: #555; border-left: 3px solid #4A90D9; padding-left: 10px; margin: 15px 0; }}
            .footer {{ font-size: 12px; color: #888; margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; }}
            a {{ color: #4A90D9; }}
            .effort-low {{ color: #2E7D32; }}
            .effort-medium {{ color: #F57C00; }}
            .effort-high {{ color: #D32F2F; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin: 0;">🚀 AI Innovation Alert for Autopack</h2>
        </div>
        <div class="content">
            <h3 style="margin-top: 0;">{title}</h3>
            <p><strong>Source:</strong> {source} | <a href="{url}">View Original →</a></p>

            <p class="score">Improvement Potential: {overall:.0%}</p>

            <div class="score-grid">
                <div class="score-item">
                    <div class="score-value">{capability}%</div>
                    <div>Capability</div>
                </div>
                <div class="score-item">
                    <div class="score-value">{token_efficiency}%</div>
                    <div>Token Efficiency</div>
                </div>
                <div class="score-item">
                    <div class="score-value">{speed}%</div>
                    <div>Speed</div>
                </div>
                <div class="score-item">
                    <div class="score-value effort-{effort_class}">{effort}</div>
                    <div>Effort</div>
                </div>
            </div>

            <div class="components">
                <strong>Applicable Components:</strong> {components}
            </div>

            <div class="rationale">
                <strong>Why this matters:</strong><br>
                {rationale}
            </div>

            <div class="footer">
                Report #{report_id} | Generated {timestamp}
            </div>
        </div>
    </body>
    </html>
    """

    EMAIL_PLAIN_TEMPLATE = """
AI Innovation Alert for Autopack
================================

{title}

Source: {source}
URL: {url}

Improvement Potential: {overall:.0%}
- Capability: {capability}%
- Token Efficiency: {token_efficiency}%
- Speed: {speed}%
- Implementation Effort: {effort}

Applicable Components: {components}

Why this matters:
{rationale}

---
Report #{report_id} | {timestamp}
"""

    WEEKLY_SUMMARY_HTML = """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 600px; margin: 0 auto; }}
            .header {{ background: #4A90D9; color: white; padding: 15px; border-radius: 5px; }}
            .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 20px 0; }}
            .stat {{ background: #f0f0f0; padding: 15px; text-align: center; border-radius: 5px; }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
            .top-item {{ background: #fff; border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            .no-items {{ color: #666; font-style: italic; padding: 20px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2 style="margin: 0;">📊 Weekly AI Innovation Summary</h2>
            <p style="margin: 5px 0 0 0;">{start_date} - {end_date}</p>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total_scanned}</div>
                <div>Scanned</div>
            </div>
            <div class="stat">
                <div class="stat-value">{passed_filter}</div>
                <div>Passed Filter</div>
            </div>
            <div class="stat">
                <div class="stat-value">{assessed}</div>
                <div>LLM Assessed</div>
            </div>
            <div class="stat">
                <div class="stat-value">{above_threshold}</div>
                <div>Above 10%</div>
            </div>
        </div>

        <h3>Top Innovations This Week</h3>
        {top_items_section}

        <p style="color: #888; font-size: 12px; margin-top: 20px;">
            Next scan: {next_scan}
        </p>
    </body>
    </html>
    """

    def __init__(self):
        """Load config from environment variables."""
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.email_to = os.getenv("EMAIL_TO")

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.email_to)

    def send_innovation_alert(
        self,
        assessment: ImprovementAssessment,
    ) -> bool:
        """
        Send innovation alert via email.

        Returns True if sent successfully.
        """
        if not self.is_configured():
            logger.warning("[EmailNotifier] Email not configured - skipping")
            return False

        try:
            # Build message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self.EMAIL_SUBJECT_TEMPLATE.format(
                title=assessment.innovation_title[:50]
            )
            msg["From"] = self.smtp_user
            msg["To"] = self.email_to

            # Determine effort class for styling
            effort_class = assessment.implementation_effort.lower()
            if effort_class not in ("low", "medium", "high"):
                effort_class = "medium"

            # Template variables
            template_vars = {
                "title": assessment.innovation_title,
                "source": assessment.source.value,
                "url": assessment.innovation_url,
                "overall": assessment.overall_improvement,
                "capability": assessment.capability_improvement,
                "token_efficiency": assessment.token_efficiency_improvement,
                "speed": assessment.speed_improvement,
                "effort": assessment.implementation_effort.capitalize(),
                "effort_class": effort_class,
                "components": ", ".join(assessment.applicable_components) or "General",
                "rationale": assessment.rationale or "No details provided.",
                "report_id": assessment.innovation_id[:8],
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            }

            # Plain text version
            text_part = MIMEText(self.EMAIL_PLAIN_TEMPLATE.format(**template_vars), "plain")
            msg.attach(text_part)

            # HTML version
            html_part = MIMEText(self.EMAIL_HTML_TEMPLATE.format(**template_vars), "html")
            msg.attach(html_part)

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"[EmailNotifier] Alert sent: {assessment.innovation_title[:50]}")
            return True

        except Exception as e:
            logger.error(f"[EmailNotifier] Failed to send alert: {e}")
            return False

    def send_weekly_summary(
        self,
        stats: WeeklySummaryStats,
    ) -> bool:
        """Send weekly summary email."""
        if not self.is_configured():
            logger.warning("[EmailNotifier] Email not configured - skipping summary")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"📊 AI Innovation Weekly Summary - {stats.end_date}"
            msg["From"] = self.smtp_user
            msg["To"] = self.email_to

            # Build top items section
            if stats.top_innovations:
                top_items_html = ""
                for item in stats.top_innovations[:5]:
                    top_items_html += f"""
                    <div class="top-item">
                        <strong>{item.innovation_title}</strong><br>
                        <span style="color: #2E7D32; font-weight: bold;">
                            {item.overall_improvement:.0%}
                        </span> improvement potential |
                        Components: {', '.join(item.applicable_components) or 'General'}<br>
                        <a href="{item.innovation_url}" style="font-size: 12px;">
                            View →
                        </a>
                    </div>
                    """
            else:
                top_items_html = (
                    '<div class="no-items">No innovations above threshold this week.</div>'
                )

            html_content = self.WEEKLY_SUMMARY_HTML.format(
                start_date=stats.start_date,
                end_date=stats.end_date,
                total_scanned=stats.total_scanned,
                passed_filter=stats.passed_filter,
                assessed=stats.assessed,
                above_threshold=stats.above_threshold,
                top_items_section=top_items_html,
                next_scan=stats.next_scan,
            )

            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info("[EmailNotifier] Weekly summary sent")
            return True

        except Exception as e:
            logger.error(f"[EmailNotifier] Failed to send summary: {e}")
            return False


def check_email_config() -> Dict[str, bool]:
    """Check email configuration status."""
    notifier = EmailNotifier()
    return {
        "configured": notifier.is_configured(),
        "smtp_host": bool(notifier.smtp_host),
        "smtp_user": bool(notifier.smtp_user),
        "smtp_password": bool(notifier.smtp_password),
        "email_to": bool(notifier.email_to),
    }
