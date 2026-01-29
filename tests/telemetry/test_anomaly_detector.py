"""Tests for telemetry anomaly detector (ROAD-G)."""

from datetime import datetime

import pytest

from autopack.telemetry.anomaly_detector import (
    AlertSeverity,
    AnomalyAlert,
    TelemetryAnomalyDetector,
)


@pytest.fixture
def detector():
    """Create anomaly detector with default settings."""
    return TelemetryAnomalyDetector(
        window_size=20,
        token_spike_multiplier=2.0,
        failure_rate_threshold=0.20,
        duration_percentile=0.95,
    )


def test_detector_initialization():
    """Test TelemetryAnomalyDetector initialization."""
    detector = TelemetryAnomalyDetector(
        window_size=10, token_spike_multiplier=3.0, failure_rate_threshold=0.15
    )

    assert detector.window_size == 10
    assert detector.token_spike_multiplier == 3.0
    assert detector.failure_rate_threshold == 0.15
    assert len(detector.token_history) == 0
    assert len(detector.pending_alerts) == 0


def test_record_phase_outcome_initializes_history(detector):
    """Test that recording first outcome initializes history."""
    alerts = detector.record_phase_outcome(
        phase_id="phase-001",
        phase_type="code_generation",
        success=True,
        tokens_used=1000,
        duration_seconds=10.0,
    )

    # No alerts on first record (need at least 5 samples)
    assert len(alerts) == 0

    # History initialized
    assert "code_generation" in detector.token_history
    assert len(detector.token_history["code_generation"]) == 1
    assert detector.token_history["code_generation"][0] == 1000


def test_token_spike_detection(detector):
    """Test token usage spike detection."""
    # Build baseline: 5 samples around 1000 tokens
    for i in range(5):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # No alerts yet (all within baseline)
    assert len(detector.pending_alerts) == 0

    # Record a spike: 3000 tokens (3x baseline, exceeds 2x threshold)
    alerts = detector.record_phase_outcome(
        phase_id="phase-spike",
        phase_type="code_generation",
        success=True,
        tokens_used=3000,
        duration_seconds=10.0,
    )

    # Should trigger token spike alert
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.severity == AlertSeverity.WARNING
    assert alert.metric == "tokens"
    assert alert.phase_id == "code_generation"
    assert alert.current_value == 3000
    assert alert.baseline == 1000
    assert alert.threshold == 2000  # 2x baseline
    assert "Token usage" in alert.recommendation


def test_no_token_spike_when_within_threshold(detector):
    """Test that no alert is triggered when tokens are within threshold."""
    # Build baseline: 5 samples around 1000 tokens
    for i in range(5):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # Record slightly higher but within 2x threshold: 1800 tokens
    alerts = detector.record_phase_outcome(
        phase_id="phase-ok",
        phase_type="code_generation",
        success=True,
        tokens_used=1800,
        duration_seconds=10.0,
    )

    # No token spike alerts (1800 < 2000 threshold)
    token_alerts = [a for a in alerts if a.metric == "tokens"]
    assert len(token_alerts) == 0


def test_duration_anomaly_detection(detector):
    """Test phase duration anomaly detection."""
    # Build baseline: 10 samples with durations 10-15s
    for i in range(10):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="test_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0 + i * 0.5,  # 10.0, 10.5, 11.0, ..., 14.5
        )

    # Record a duration spike: 30s (>1.5x p95)
    alerts = detector.record_phase_outcome(
        phase_id="phase-slow",
        phase_type="test_generation",
        success=True,
        tokens_used=1000,
        duration_seconds=30.0,
    )

    # Should trigger duration anomaly alert
    duration_alerts = [a for a in alerts if a.metric == "duration"]
    assert len(duration_alerts) == 1
    alert = duration_alerts[0]
    assert alert.severity == AlertSeverity.WARNING
    assert alert.phase_id == "test_generation"
    assert alert.current_value == 30.0
    assert "Duration" in alert.recommendation


def test_failure_rate_detection(detector):
    """Test failure rate threshold detection."""
    # Record 10 outcomes with 3 failures (30% failure rate)
    outcomes = [True, True, True, False, True, False, True, True, False, True]

    for i, success in enumerate(outcomes):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=success,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # Should trigger failure rate alert (30% > 20% threshold)
    failure_alerts = [
        a
        for a in detector.pending_alerts
        if a.metric == "failure_rate" and a.phase_id == "code_generation"
    ]
    assert len(failure_alerts) >= 1
    alert = failure_alerts[0]
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.current_value > 0.20  # Above threshold
    assert "ROAD-J" in alert.recommendation


def test_no_failure_alert_when_below_threshold(detector):
    """Test that no alert is triggered when failure rate is acceptable."""
    # Record 10 outcomes with 1 failure (10% failure rate)
    outcomes = [True, True, True, True, False, True, True, True, True, True]

    for i, success in enumerate(outcomes):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=success,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # No failure rate alerts (10% < 20% threshold)
    failure_alerts = [a for a in detector.pending_alerts if a.metric == "failure_rate"]
    assert len(failure_alerts) == 0


def test_rolling_window_trims_old_data(detector):
    """Test that rolling window only keeps recent samples."""
    detector = TelemetryAnomalyDetector(window_size=5)

    # Record 10 samples
    for i in range(10):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000 + i * 100,
            duration_seconds=10.0,
        )

    # Should only keep last 5 samples
    assert len(detector.token_history["code_generation"]) == 5
    assert len(detector.duration_history["code_generation"]) == 5
    assert len(detector.outcome_history["code_generation"]) == 5

    # Oldest samples should be trimmed
    assert detector.token_history["code_generation"][0] == 1500  # 6th sample


def test_separate_history_per_phase_type(detector):
    """Test that histories are tracked separately per phase type."""
    # Record outcomes for different phase types
    detector.record_phase_outcome(
        phase_id="phase-001",
        phase_type="code_generation",
        success=True,
        tokens_used=1000,
        duration_seconds=10.0,
    )

    detector.record_phase_outcome(
        phase_id="phase-002",
        phase_type="test_generation",
        success=True,
        tokens_used=2000,
        duration_seconds=20.0,
    )

    # Should have separate histories
    assert "code_generation" in detector.token_history
    assert "test_generation" in detector.token_history
    assert detector.token_history["code_generation"][0] == 1000
    assert detector.token_history["test_generation"][0] == 2000


def test_no_alerts_with_insufficient_history(detector):
    """Test that no alerts are generated with < 5 samples."""
    # Record only 3 samples
    for i in range(3):
        alerts = detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

        # No alerts (insufficient history)
        assert len(alerts) == 0


def test_get_pending_alerts_clears_by_default(detector):
    """Test that get_pending_alerts clears alerts by default."""
    # Generate some alerts
    for i in range(5):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # Trigger a spike
    detector.record_phase_outcome(
        phase_id="phase-spike",
        phase_type="code_generation",
        success=True,
        tokens_used=3000,
        duration_seconds=10.0,
    )

    # Get alerts (should clear)
    alerts = detector.get_pending_alerts(clear=True)
    assert len(alerts) > 0

    # Should be cleared now
    assert len(detector.pending_alerts) == 0


def test_get_pending_alerts_without_clearing(detector):
    """Test that get_pending_alerts can preserve alerts."""
    # Generate some alerts
    for i in range(5):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # Trigger a spike
    detector.record_phase_outcome(
        phase_id="phase-spike",
        phase_type="code_generation",
        success=True,
        tokens_used=3000,
        duration_seconds=10.0,
    )

    # Get alerts without clearing
    alerts = detector.get_pending_alerts(clear=False)
    assert len(alerts) > 0

    # Should still be in pending
    assert len(detector.pending_alerts) > 0


def test_anomaly_alert_dataclass():
    """Test AnomalyAlert dataclass creation."""
    alert = AnomalyAlert(
        alert_id="TEST_001",
        severity=AlertSeverity.WARNING,
        metric="tokens",
        phase_id="phase-test",
        current_value=3000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Test recommendation",
    )

    assert alert.alert_id == "TEST_001"
    assert alert.severity == AlertSeverity.WARNING
    assert alert.metric == "tokens"
    assert alert.phase_id == "phase-test"
    assert alert.current_value == 3000.0
    assert alert.threshold == 2000.0
    assert alert.baseline == 1000.0
    assert alert.recommendation == "Test recommendation"
    assert isinstance(alert.timestamp, datetime)


def test_alert_severity_enum():
    """Test AlertSeverity enum values."""
    assert AlertSeverity.INFO.value == "info"
    assert AlertSeverity.WARNING.value == "warning"
    assert AlertSeverity.CRITICAL.value == "critical"


def test_multiple_anomalies_same_outcome(detector):
    """Test that multiple anomalies can be detected in single outcome."""
    # Build baseline with normal values
    for i in range(10):
        detector.record_phase_outcome(
            phase_id=f"phase-{i:03d}",
            phase_type="code_generation",
            success=True,
            tokens_used=1000,
            duration_seconds=10.0,
        )

    # Record outcome with both token spike AND duration anomaly
    alerts = detector.record_phase_outcome(
        phase_id="phase-multi-anomaly",
        phase_type="code_generation",
        success=True,
        tokens_used=3000,  # 3x baseline (triggers token spike)
        duration_seconds=30.0,  # Much higher than baseline (triggers duration)
    )

    # Should detect both anomalies
    assert len(alerts) >= 2
    metrics = {a.metric for a in alerts}
    assert "tokens" in metrics
    assert "duration" in metrics


def test_phase_type_fallback_to_phase_id(detector):
    """Test that phase_id is used when phase_type is None."""
    # Record with no phase_type
    detector.record_phase_outcome(
        phase_id="unique-phase-001",
        phase_type=None,
        success=True,
        tokens_used=1000,
        duration_seconds=10.0,
    )

    # Should use phase_id as key
    assert "unique-phase-001" in detector.token_history
    assert len(detector.token_history["unique-phase-001"]) == 1
