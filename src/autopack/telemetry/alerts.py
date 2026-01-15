"""Alert routing and notification for anomaly detection."""

import logging
from .anomaly_detector import AnomalyAlert, AlertSeverity

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes alerts to appropriate handlers."""

    def __init__(self):
        self.handlers = {
            AlertSeverity.INFO: self._handle_info,
            AlertSeverity.WARNING: self._handle_warning,
            AlertSeverity.CRITICAL: self._handle_critical,
        }

    def route_alert(self, alert: AnomalyAlert) -> None:
        """Route alert to appropriate handler."""
        handler = self.handlers.get(alert.severity, self._handle_info)
        handler(alert)

    def _handle_info(self, alert: AnomalyAlert) -> None:
        """Log info-level alerts."""
        logger.info(
            f"[ANOMALY:INFO] {alert.metric}: {alert.current_value} (threshold: {alert.threshold})"
        )

    def _handle_warning(self, alert: AnomalyAlert) -> None:
        """Log warning and queue for review."""
        logger.warning(
            f"[ANOMALY:WARNING] {alert.metric} on {alert.phase_id}: {alert.recommendation}"
        )
        # TODO: Integrate with ROAD-J auto-heal

    def _handle_critical(self, alert: AnomalyAlert) -> None:
        """Log critical and trigger immediate action."""
        logger.error(
            f"[ANOMALY:CRITICAL] {alert.metric} on {alert.phase_id}: {alert.recommendation}"
        )
        # TODO: Trigger model escalation or pause execution
