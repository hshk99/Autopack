"""Real-time anomaly detection for telemetry streams.

Detects:
- Token usage spikes (>2x rolling baseline)
- Failure rate threshold breaches (>20% in window)
- Phase duration exceeding p95
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from statistics import mean, quantiles
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AnomalyAlert:
    """An anomaly detection alert."""

    alert_id: str
    severity: AlertSeverity
    metric: str  # tokens, failure_rate, duration
    phase_id: Optional[str]
    current_value: float
    threshold: float
    baseline: float
    recommendation: str
    timestamp: datetime = field(default_factory=lambda: datetime.utcnow())


class TelemetryAnomalyDetector:
    """Detects anomalies in real-time telemetry."""

    def __init__(
        self,
        window_size: int = 20,
        token_spike_multiplier: float = 2.0,
        failure_rate_threshold: float = 0.20,
        duration_percentile: float = 0.95,
    ):
        self.window_size = window_size
        self.token_spike_multiplier = token_spike_multiplier
        self.failure_rate_threshold = failure_rate_threshold
        self.duration_percentile = duration_percentile

        # Rolling windows per phase type
        self.token_history: Dict[str, List[int]] = {}
        self.duration_history: Dict[str, List[float]] = {}
        self.outcome_history: Dict[str, List[bool]] = {}  # True=success

        # Alerts generated
        self.pending_alerts: List[AnomalyAlert] = []

    def record_phase_outcome(
        self,
        phase_id: str,
        phase_type: str,
        success: bool,
        tokens_used: int,
        duration_seconds: float,
    ) -> List[AnomalyAlert]:
        """Record a phase outcome and check for anomalies."""
        alerts = []

        # Update histories
        key = phase_type or phase_id

        if key not in self.token_history:
            self.token_history[key] = []
            self.duration_history[key] = []
            self.outcome_history[key] = []

        self.token_history[key].append(tokens_used)
        self.duration_history[key].append(duration_seconds)
        self.outcome_history[key].append(success)

        # Trim to window size
        for hist in [
            self.token_history[key],
            self.duration_history[key],
            self.outcome_history[key],
        ]:
            while len(hist) > self.window_size:
                hist.pop(0)

        # Check for anomalies (only if we have enough history)
        if len(self.token_history[key]) >= 5:
            token_alert = self._check_token_anomaly(key, tokens_used)
            if token_alert:
                alerts.append(token_alert)

            duration_alert = self._check_duration_anomaly(key, duration_seconds)
            if duration_alert:
                alerts.append(duration_alert)

            failure_alert = self._check_failure_rate(key)
            if failure_alert:
                alerts.append(failure_alert)

        self.pending_alerts.extend(alerts)
        return alerts

    def _check_token_anomaly(self, key: str, current_tokens: int) -> Optional[AnomalyAlert]:
        """Check if current token usage is anomalous."""
        history = self.token_history[key][:-1]  # Exclude current
        if not history:
            return None

        baseline = mean(history)
        threshold = baseline * self.token_spike_multiplier

        if current_tokens > threshold:
            return AnomalyAlert(
                alert_id=f"TOKEN_SPIKE_{key}_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="tokens",
                phase_id=key,
                current_value=current_tokens,
                threshold=threshold,
                baseline=baseline,
                recommendation=f"Token usage {current_tokens:,} exceeds {self.token_spike_multiplier}x baseline ({baseline:,.0f}). Consider: (1) Check for context bloat, (2) Review model selection, (3) Enable caching",
            )
        return None

    def _check_duration_anomaly(self, key: str, current_duration: float) -> Optional[AnomalyAlert]:
        """Check if current duration exceeds p95."""
        history = self.duration_history[key][:-1]
        if len(history) < 5:
            return None

        try:
            p95 = quantiles(history, n=20)[18]  # 95th percentile
        except Exception:
            return None

        if current_duration > p95 * 1.5:  # 50% above p95
            return AnomalyAlert(
                alert_id=f"DURATION_SPIKE_{key}_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="duration",
                phase_id=key,
                current_value=current_duration,
                threshold=p95,
                baseline=mean(history),
                recommendation=f"Duration {current_duration:.1f}s exceeds p95 ({p95:.1f}s). Check for: (1) Network issues, (2) Model overload, (3) Large file processing",
            )
        return None

    def _check_failure_rate(self, key: str) -> Optional[AnomalyAlert]:
        """Check if failure rate exceeds threshold."""
        history = self.outcome_history[key]
        if len(history) < 5:
            return None

        failure_rate = 1 - (sum(history) / len(history))

        if failure_rate > self.failure_rate_threshold:
            return AnomalyAlert(
                alert_id=f"FAILURE_RATE_{key}_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.CRITICAL,
                metric="failure_rate",
                phase_id=key,
                current_value=failure_rate,
                threshold=self.failure_rate_threshold,
                baseline=0.0,
                recommendation=f"Failure rate {failure_rate:.1%} exceeds {self.failure_rate_threshold:.1%} threshold. Triggering: (1) ROAD-J auto-heal check, (2) Model escalation, (3) Doctor diagnosis",
            )
        return None

    def get_pending_alerts(self, clear: bool = True) -> List[AnomalyAlert]:
        """Get pending alerts, optionally clearing them."""
        alerts = self.pending_alerts.copy()
        if clear:
            self.pending_alerts = []
        return alerts
