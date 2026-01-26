"""Alert routing and notification for anomaly detection."""

import logging
import os
from typing import Optional
from .anomaly_detector import AnomalyAlert, AlertSeverity
from .auto_healer import AutoHealingEngine

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes alerts to appropriate handlers.

    IMP-TEL-004: Extended with persistence for WARNING and CRITICAL alerts.
    Alerts are stored in the database for analysis and historical tracking.
    """

    def __init__(self, auto_healer: Optional[AutoHealingEngine] = None):
        """
        Args:
            auto_healer: ROAD-J AutoHealingEngine instance for automatic recovery.
                        If None, alerts are logged only (no auto-healing).
        """
        self.auto_healer = auto_healer
        self.handlers = {
            AlertSeverity.INFO: self._handle_info,
            AlertSeverity.WARNING: self._handle_warning,
            AlertSeverity.CRITICAL: self._handle_critical,
        }

    def route_alert(self, alert: AnomalyAlert, run_id: Optional[str] = None) -> None:
        """Route alert to appropriate handler.

        IMP-TEL-004: Extended to persist WARNING and CRITICAL alerts to database.

        Args:
            alert: The anomaly alert to route.
            run_id: Optional run ID for persistence context.
        """
        handler = self.handlers.get(alert.severity, self._handle_info)
        handler(alert)

        # IMP-TEL-004: Persist WARNING and CRITICAL alerts for analysis
        if alert.severity in (AlertSeverity.WARNING, AlertSeverity.CRITICAL):
            self.persist_alert(alert, run_id=run_id)

    def persist_alert(self, alert: AnomalyAlert, run_id: Optional[str] = None) -> bool:
        """IMP-TEL-004: Persist alert to database for historical tracking.

        Persists anomaly alerts to enable:
        - Historical trend analysis of anomaly patterns
        - Effectiveness measurement of auto-healing actions
        - Alert frequency monitoring per phase type/metric
        - Post-incident review and debugging

        Args:
            alert: The anomaly alert to persist.
            run_id: Optional run ID for context.

        Returns:
            True if persistence succeeded, False otherwise.
        """
        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() != "true":
            logger.debug(
                f"[IMP-TEL-004] Alert persistence skipped (TELEMETRY_DB_ENABLED=false): {alert.alert_id}"
            )
            return False

        try:
            from autopack.models import AnomalyAlertEvent
            from autopack.database import SessionLocal

            db = SessionLocal()
            try:
                event = AnomalyAlertEvent(
                    alert_id=alert.alert_id,
                    run_id=run_id,
                    phase_id=alert.phase_id,
                    timestamp=alert.timestamp,
                    severity=alert.severity.value,
                    metric=alert.metric,
                    current_value=alert.current_value,
                    threshold=alert.threshold,
                    baseline=alert.baseline,
                    recommendation=alert.recommendation,
                )
                db.add(event)
                db.commit()
                logger.debug(
                    f"[IMP-TEL-004] Persisted alert: {alert.alert_id} "
                    f"({alert.severity.value} - {alert.metric})"
                )
                return True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[IMP-TEL-004] Failed to persist alert {alert.alert_id}: {e}")
            return False

    def _handle_info(self, alert: AnomalyAlert) -> None:
        """Log info-level alerts."""
        logger.info(
            f"[ANOMALY:INFO] {alert.metric}: {alert.current_value} (threshold: {alert.threshold})"
        )

    def _handle_warning(self, alert: AnomalyAlert) -> None:
        """Log warning and trigger auto-healing if enabled."""
        logger.warning(
            f"[ANOMALY:WARNING] {alert.metric} on {alert.phase_id}: {alert.recommendation}"
        )

        # ROAD-J integration: Attempt automatic healing
        if self.auto_healer:
            self.auto_healer.heal(alert)

    def _handle_critical(self, alert: AnomalyAlert) -> None:
        """Log critical and trigger immediate healing action."""
        logger.error(
            f"[ANOMALY:CRITICAL] {alert.metric} on {alert.phase_id}: {alert.recommendation}"
        )

        # ROAD-J integration: Attempt critical healing (replan, escalate, or rollback)
        if self.auto_healer:
            self.auto_healer.heal(alert)
