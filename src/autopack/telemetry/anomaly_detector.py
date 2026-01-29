"""Real-time anomaly detection for telemetry streams.

Detects:
- Token usage spikes (>2x rolling baseline)
- Failure rate threshold breaches (>20% in window)
- Phase duration exceeding p95
- Model staleness (embeddings/learning models not updated)
- Policy effectiveness degradation (declining success rates)
- Cross-phase correlation anomalies
- Memory retrieval quality degradation
- Hint effectiveness regression
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from statistics import mean, quantiles, stdev
from typing import Dict, List, Optional, Tuple

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
        # New thresholds for additional anomaly signals
        staleness_threshold_hours: float = 24.0,
        policy_degradation_threshold: float = 0.15,
        correlation_change_threshold: float = 0.3,
        retrieval_quality_min_threshold: float = 0.5,
        hint_effectiveness_min_threshold: float = 0.3,
    ):
        self.window_size = window_size
        self.token_spike_multiplier = token_spike_multiplier
        self.failure_rate_threshold = failure_rate_threshold
        self.duration_percentile = duration_percentile

        # New thresholds for additional signals
        self.staleness_threshold_hours = staleness_threshold_hours
        self.policy_degradation_threshold = policy_degradation_threshold
        self.correlation_change_threshold = correlation_change_threshold
        self.retrieval_quality_min_threshold = retrieval_quality_min_threshold
        self.hint_effectiveness_min_threshold = hint_effectiveness_min_threshold

        # Rolling windows per phase type
        self.token_history: Dict[str, List[int]] = {}
        self.duration_history: Dict[str, List[float]] = {}
        self.outcome_history: Dict[str, List[bool]] = {}  # True=success

        # Alerts generated
        self.pending_alerts: List[AnomalyAlert] = []

        # New tracking structures for additional signals
        self.model_update_times: Dict[str, datetime] = {}
        self.policy_effectiveness_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self.phase_correlation_baseline: Dict[Tuple[str, str], float] = {}
        self.phase_outcomes_for_correlation: Dict[str, List[Tuple[datetime, bool]]] = {}
        self.retrieval_quality_history: List[Tuple[datetime, float, int]] = []
        self.hint_effectiveness_history: List[Tuple[datetime, bool, bool]] = []

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
        except Exception as e:
            logger.debug(f"[IMP-TELE-003] Failed to calculate p95 for {key}: {e}")
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

    # ==========================================================================
    # Model Staleness Detection
    # ==========================================================================

    def record_model_update(self, model_name: str) -> None:
        """Record that a model (embeddings, learning model) was updated."""
        self.model_update_times[model_name] = datetime.utcnow()

    def detect_model_staleness(self) -> Optional[AnomalyAlert]:
        """Detect if any models haven't been updated within threshold.

        Returns an alert if a model is stale (not updated within staleness_threshold_hours).
        """
        if not self.model_update_times:
            return None

        now = datetime.utcnow()
        threshold_delta = timedelta(hours=self.staleness_threshold_hours)
        stale_models = []

        for model_name, last_update in self.model_update_times.items():
            age = now - last_update
            if age > threshold_delta:
                stale_models.append((model_name, age.total_seconds() / 3600))

        if stale_models:
            # Sort by staleness (most stale first)
            stale_models.sort(key=lambda x: x[1], reverse=True)
            most_stale, hours_stale = stale_models[0]

            alert = AnomalyAlert(
                alert_id=f"MODEL_STALENESS_{most_stale}_{now.timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="model_staleness",
                phase_id=None,
                current_value=hours_stale,
                threshold=self.staleness_threshold_hours,
                baseline=0.0,
                recommendation=(
                    f"Model '{most_stale}' is {hours_stale:.1f}h stale "
                    f"(threshold: {self.staleness_threshold_hours}h). "
                    f"Total stale models: {len(stale_models)}. "
                    "Consider: (1) Trigger model refresh, (2) Check learning pipeline, "
                    "(3) Verify data ingestion"
                ),
            )
            self.pending_alerts.append(alert)
            return alert
        return None

    # ==========================================================================
    # Policy Effectiveness Degradation Detection
    # ==========================================================================

    def record_policy_outcome(
        self, policy_name: str, success: bool, timestamp: Optional[datetime] = None
    ) -> None:
        """Record a policy execution outcome for effectiveness tracking."""
        ts = timestamp or datetime.utcnow()
        if policy_name not in self.policy_effectiveness_history:
            self.policy_effectiveness_history[policy_name] = []

        # Calculate rolling effectiveness rate
        history = self.policy_effectiveness_history[policy_name]
        history.append((ts, 1.0 if success else 0.0))

        # Keep only last window_size entries
        while len(history) > self.window_size:
            history.pop(0)

    def detect_policy_effectiveness_degradation(self) -> Optional[AnomalyAlert]:
        """Detect if policy effectiveness is degrading over time.

        Compares recent effectiveness against historical baseline to detect decline.
        """
        alerts = []

        for policy_name, history in self.policy_effectiveness_history.items():
            if len(history) < 10:  # Need minimum history
                continue

            # Split into first half (baseline) and second half (recent)
            mid = len(history) // 2
            baseline_values = [v for _, v in history[:mid]]
            recent_values = [v for _, v in history[mid:]]

            baseline_rate = mean(baseline_values) if baseline_values else 0.0
            recent_rate = mean(recent_values) if recent_values else 0.0

            # Check for significant degradation
            degradation = baseline_rate - recent_rate
            if degradation > self.policy_degradation_threshold:
                alert = AnomalyAlert(
                    alert_id=f"POLICY_DEGRADATION_{policy_name}_{datetime.utcnow().timestamp()}",
                    severity=AlertSeverity.WARNING,
                    metric="policy_effectiveness",
                    phase_id=policy_name,
                    current_value=recent_rate,
                    threshold=baseline_rate - self.policy_degradation_threshold,
                    baseline=baseline_rate,
                    recommendation=(
                        f"Policy '{policy_name}' effectiveness dropped from "
                        f"{baseline_rate:.1%} to {recent_rate:.1%} "
                        f"(delta: {degradation:.1%}). "
                        "Consider: (1) Review policy rules, (2) Check for data drift, "
                        "(3) Retrain policy model"
                    ),
                )
                alerts.append(alert)

        if alerts:
            # Return most severe (largest degradation)
            alerts.sort(key=lambda a: a.baseline - a.current_value, reverse=True)
            self.pending_alerts.extend(alerts)
            return alerts[0]
        return None

    # ==========================================================================
    # Cross-Phase Correlation Detection
    # ==========================================================================

    def record_phase_outcome_for_correlation(
        self, phase_type: str, success: bool, timestamp: Optional[datetime] = None
    ) -> None:
        """Record phase outcome for cross-phase correlation analysis."""
        ts = timestamp or datetime.utcnow()
        if phase_type not in self.phase_outcomes_for_correlation:
            self.phase_outcomes_for_correlation[phase_type] = []

        self.phase_outcomes_for_correlation[phase_type].append((ts, success))

        # Keep limited history
        while len(self.phase_outcomes_for_correlation[phase_type]) > self.window_size * 2:
            self.phase_outcomes_for_correlation[phase_type].pop(0)

    def _calculate_correlation(self, outcomes_a: List[bool], outcomes_b: List[bool]) -> float:
        """Calculate Pearson correlation between two outcome sequences."""
        if len(outcomes_a) != len(outcomes_b) or len(outcomes_a) < 3:
            return 0.0

        # Convert to float
        a = [1.0 if x else 0.0 for x in outcomes_a]
        b = [1.0 if x else 0.0 for x in outcomes_b]

        try:
            mean_a, mean_b = mean(a), mean(b)
            std_a, std_b = stdev(a), stdev(b)

            if std_a == 0 or std_b == 0:
                return 0.0

            covariance = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(len(a)))
            covariance /= len(a)

            return covariance / (std_a * std_b)
        except Exception as e:
            logger.debug(f"[IMP-TELE-003] Failed to calculate correlation: {e}")
            return 0.0

    def detect_cross_phase_correlation(self) -> Optional[AnomalyAlert]:
        """Detect anomalous changes in cross-phase correlations.

        Monitors if phase A success correlating with phase B success changes significantly.
        """
        phase_types = list(self.phase_outcomes_for_correlation.keys())
        if len(phase_types) < 2:
            return None

        alerts = []

        for i, phase_a in enumerate(phase_types):
            for phase_b in phase_types[i + 1 :]:
                outcomes_a = self.phase_outcomes_for_correlation[phase_a]
                outcomes_b = self.phase_outcomes_for_correlation[phase_b]

                # Align by timestamp (within 1 minute tolerance)
                aligned_a, aligned_b = [], []
                for ts_a, success_a in outcomes_a:
                    for ts_b, success_b in outcomes_b:
                        if abs((ts_a - ts_b).total_seconds()) < 60:
                            aligned_a.append(success_a)
                            aligned_b.append(success_b)
                            break

                if len(aligned_a) < 5:
                    continue

                # Calculate current correlation
                current_corr = self._calculate_correlation(aligned_a, aligned_b)

                # Get or set baseline
                pair_key = (phase_a, phase_b)
                if pair_key not in self.phase_correlation_baseline:
                    self.phase_correlation_baseline[pair_key] = current_corr
                    continue

                baseline_corr = self.phase_correlation_baseline[pair_key]
                corr_change = abs(current_corr - baseline_corr)

                if corr_change > self.correlation_change_threshold:
                    alert = AnomalyAlert(
                        alert_id=f"CORRELATION_SHIFT_{phase_a}_{phase_b}_{datetime.utcnow().timestamp()}",
                        severity=AlertSeverity.WARNING,
                        metric="cross_phase_correlation",
                        phase_id=f"{phase_a}<->{phase_b}",
                        current_value=current_corr,
                        threshold=(
                            baseline_corr - self.correlation_change_threshold
                            if current_corr < baseline_corr
                            else baseline_corr + self.correlation_change_threshold
                        ),
                        baseline=baseline_corr,
                        recommendation=(
                            f"Correlation between '{phase_a}' and '{phase_b}' shifted from "
                            f"{baseline_corr:.2f} to {current_corr:.2f}. "
                            "This may indicate: (1) Dependency changes, (2) Shared resource issues, "
                            "(3) Pipeline configuration drift"
                        ),
                    )
                    alerts.append(alert)

                # Update baseline with exponential moving average
                self.phase_correlation_baseline[pair_key] = 0.9 * baseline_corr + 0.1 * current_corr

        if alerts:
            self.pending_alerts.extend(alerts)
            return alerts[0]
        return None

    # ==========================================================================
    # Memory Retrieval Quality Detection
    # ==========================================================================

    def record_retrieval_quality(
        self,
        relevance_score: float,
        hit_count: int,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record memory retrieval quality metrics."""
        ts = timestamp or datetime.utcnow()
        self.retrieval_quality_history.append((ts, relevance_score, hit_count))

        # Keep limited history
        while len(self.retrieval_quality_history) > self.window_size * 2:
            self.retrieval_quality_history.pop(0)

    def detect_memory_retrieval_quality(self) -> Optional[AnomalyAlert]:
        """Detect degradation in memory retrieval quality.

        Monitors relevance scores and hit rates to detect poor retrieval.
        """
        if len(self.retrieval_quality_history) < 5:
            return None

        # Calculate recent average relevance
        recent = self.retrieval_quality_history[-self.window_size :]
        avg_relevance = mean([r for _, r, _ in recent])
        avg_hits = mean([h for _, _, h in recent])

        # Check for low quality
        if avg_relevance < self.retrieval_quality_min_threshold:
            # Calculate trend (is it getting worse?)
            if len(recent) >= 6:
                first_half = mean([r for _, r, _ in recent[: len(recent) // 2]])
                second_half = mean([r for _, r, _ in recent[len(recent) // 2 :]])
                trend = "declining" if second_half < first_half else "stable"
            else:
                trend = "unknown"

            alert = AnomalyAlert(
                alert_id=f"RETRIEVAL_QUALITY_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="memory_retrieval_quality",
                phase_id=None,
                current_value=avg_relevance,
                threshold=self.retrieval_quality_min_threshold,
                baseline=0.0,
                recommendation=(
                    f"Memory retrieval quality is low: avg relevance {avg_relevance:.2f} "
                    f"(min threshold: {self.retrieval_quality_min_threshold}), "
                    f"avg hits: {avg_hits:.1f}, trend: {trend}. "
                    "Consider: (1) Reindex embeddings, (2) Adjust similarity threshold, "
                    "(3) Review memory pruning settings"
                ),
            )
            self.pending_alerts.append(alert)
            return alert

        # Also check for very low hit count (potential index issue)
        if avg_hits < 1.0:
            alert = AnomalyAlert(
                alert_id=f"RETRIEVAL_MISS_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="memory_retrieval_quality",
                phase_id=None,
                current_value=avg_hits,
                threshold=1.0,
                baseline=0.0,
                recommendation=(
                    f"Memory retrieval returning very few results: avg {avg_hits:.2f} hits. "
                    "This may indicate: (1) Empty memory store, (2) Query mismatch, "
                    "(3) Index corruption"
                ),
            )
            self.pending_alerts.append(alert)
            return alert

        return None

    # ==========================================================================
    # Hint Effectiveness Regression Detection
    # ==========================================================================

    def record_hint_outcome(
        self,
        hint_was_applied: bool,
        phase_succeeded: bool,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Record whether applying a hint led to success.

        Args:
            hint_was_applied: Whether a hint was available and applied
            phase_succeeded: Whether the phase execution succeeded
            timestamp: Optional timestamp (defaults to now)
        """
        ts = timestamp or datetime.utcnow()
        self.hint_effectiveness_history.append((ts, hint_was_applied, phase_succeeded))

        # Keep limited history
        while len(self.hint_effectiveness_history) > self.window_size * 3:
            self.hint_effectiveness_history.pop(0)

    def detect_hint_effectiveness_regression(self) -> Optional[AnomalyAlert]:
        """Detect if hints are becoming less effective over time.

        Compares success rate when hints are applied vs not applied,
        and checks for declining hint effectiveness.
        """
        if len(self.hint_effectiveness_history) < 10:
            return None

        # Separate into hint-applied and no-hint cases
        with_hint = [
            (ts, success) for ts, applied, success in self.hint_effectiveness_history if applied
        ]
        without_hint = [
            (ts, success) for ts, applied, success in self.hint_effectiveness_history if not applied
        ]

        if len(with_hint) < 5:
            return None

        # Calculate success rates
        hint_success_rate = sum(1 for _, s in with_hint if s) / len(with_hint)
        no_hint_success_rate = (
            sum(1 for _, s in without_hint if s) / len(without_hint)
            if without_hint
            else 0.5  # Default baseline
        )

        # Check if hints are helping at all
        hint_benefit = hint_success_rate - no_hint_success_rate

        if hint_success_rate < self.hint_effectiveness_min_threshold:
            alert = AnomalyAlert(
                alert_id=f"HINT_INEFFECTIVE_{datetime.utcnow().timestamp()}",
                severity=AlertSeverity.WARNING,
                metric="hint_effectiveness",
                phase_id=None,
                current_value=hint_success_rate,
                threshold=self.hint_effectiveness_min_threshold,
                baseline=no_hint_success_rate,
                recommendation=(
                    f"Hint effectiveness is low: {hint_success_rate:.1%} success with hints "
                    f"(min threshold: {self.hint_effectiveness_min_threshold:.1%}). "
                    f"Without hints: {no_hint_success_rate:.1%}. "
                    f"Hint benefit: {hint_benefit:+.1%}. "
                    "Consider: (1) Review hint quality, (2) Prune stale hints, "
                    "(3) Retrain hint extraction"
                ),
            )
            self.pending_alerts.append(alert)
            return alert

        # Check for regression (was better before)
        if len(with_hint) >= 10:
            mid = len(with_hint) // 2
            early_rate = sum(1 for _, s in with_hint[:mid] if s) / mid
            recent_rate = sum(1 for _, s in with_hint[mid:] if s) / (len(with_hint) - mid)

            regression = early_rate - recent_rate
            if regression > self.policy_degradation_threshold:
                alert = AnomalyAlert(
                    alert_id=f"HINT_REGRESSION_{datetime.utcnow().timestamp()}",
                    severity=AlertSeverity.WARNING,
                    metric="hint_effectiveness",
                    phase_id=None,
                    current_value=recent_rate,
                    threshold=early_rate - self.policy_degradation_threshold,
                    baseline=early_rate,
                    recommendation=(
                        f"Hint effectiveness regressing: was {early_rate:.1%}, now {recent_rate:.1%} "
                        f"(dropped {regression:.1%}). "
                        "Consider: (1) Hints may be stale, (2) Context drift detected, "
                        "(3) Re-evaluate hint sources"
                    ),
                )
                self.pending_alerts.append(alert)
                return alert

        return None

    # ==========================================================================
    # Batch Detection (Run All Detectors)
    # ==========================================================================

    def run_all_detections(self) -> List[AnomalyAlert]:
        """Run all anomaly detection checks and return any alerts."""
        alerts = []

        # Run all detection methods
        detectors = [
            self.detect_model_staleness,
            self.detect_policy_effectiveness_degradation,
            self.detect_cross_phase_correlation,
            self.detect_memory_retrieval_quality,
            self.detect_hint_effectiveness_regression,
        ]

        for detector in detectors:
            try:
                alert = detector()
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.warning(f"Anomaly detector {detector.__name__} failed: {e}")

        return alerts
