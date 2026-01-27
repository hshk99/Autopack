"""Tests for alert routing (ROAD-G)."""

import logging

import pytest

from autopack.telemetry.alerts import AlertRouter
from autopack.telemetry.anomaly_detector import AlertSeverity, AnomalyAlert


@pytest.fixture
def router():
    """Create alert router."""
    return AlertRouter()


@pytest.fixture
def sample_alert():
    """Create a sample anomaly alert."""
    return AnomalyAlert(
        alert_id="TEST_001",
        severity=AlertSeverity.WARNING,
        metric="tokens",
        phase_id="phase-test",
        current_value=3000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Test recommendation",
    )


def test_router_initialization(router):
    """Test AlertRouter initialization."""
    assert router.handlers is not None
    assert AlertSeverity.INFO in router.handlers
    assert AlertSeverity.WARNING in router.handlers
    assert AlertSeverity.CRITICAL in router.handlers


def test_route_info_alert(router, sample_alert, caplog):
    """Test routing INFO severity alert."""
    sample_alert.severity = AlertSeverity.INFO

    with caplog.at_level(logging.INFO):
        router.route_alert(sample_alert)

    # Should log at INFO level
    assert any("[ANOMALY:INFO]" in record.message for record in caplog.records)
    assert any("tokens" in record.message for record in caplog.records)


def test_route_warning_alert(router, sample_alert, caplog):
    """Test routing WARNING severity alert."""
    sample_alert.severity = AlertSeverity.WARNING

    with caplog.at_level(logging.WARNING):
        router.route_alert(sample_alert)

    # Should log at WARNING level
    assert any("[ANOMALY:WARNING]" in record.message for record in caplog.records)
    assert any("phase-test" in record.message for record in caplog.records)
    assert any("Test recommendation" in record.message for record in caplog.records)


def test_route_critical_alert(router, sample_alert, caplog):
    """Test routing CRITICAL severity alert."""
    sample_alert.severity = AlertSeverity.CRITICAL

    with caplog.at_level(logging.ERROR):
        router.route_alert(sample_alert)

    # Should log at ERROR level
    assert any("[ANOMALY:CRITICAL]" in record.message for record in caplog.records)
    assert any("phase-test" in record.message for record in caplog.records)


def test_route_multiple_alerts(router, caplog):
    """Test routing multiple alerts."""
    alerts = [
        AnomalyAlert(
            alert_id="INFO_001",
            severity=AlertSeverity.INFO,
            metric="tokens",
            phase_id="phase-1",
            current_value=1500.0,
            threshold=2000.0,
            baseline=1000.0,
            recommendation="Info alert",
        ),
        AnomalyAlert(
            alert_id="WARNING_001",
            severity=AlertSeverity.WARNING,
            metric="duration",
            phase_id="phase-2",
            current_value=30.0,
            threshold=20.0,
            baseline=10.0,
            recommendation="Warning alert",
        ),
        AnomalyAlert(
            alert_id="CRITICAL_001",
            severity=AlertSeverity.CRITICAL,
            metric="failure_rate",
            phase_id="phase-3",
            current_value=0.5,
            threshold=0.2,
            baseline=0.0,
            recommendation="Critical alert",
        ),
    ]

    with caplog.at_level(logging.INFO):
        for alert in alerts:
            router.route_alert(alert)

    # Should have logged all three
    assert any("[ANOMALY:INFO]" in record.message for record in caplog.records)
    assert any("[ANOMALY:WARNING]" in record.message for record in caplog.records)
    assert any("[ANOMALY:CRITICAL]" in record.message for record in caplog.records)


def test_handle_info_includes_metrics(router, sample_alert, caplog):
    """Test that INFO handler includes metric details."""
    sample_alert.severity = AlertSeverity.INFO

    with caplog.at_level(logging.INFO):
        router.route_alert(sample_alert)

    # Should include current value and threshold
    log_message = next(
        record.message for record in caplog.records if "[ANOMALY:INFO]" in record.message
    )
    assert "3000.0" in log_message or "tokens" in log_message
    assert "2000.0" in log_message or "threshold" in log_message


def test_handle_warning_includes_recommendation(router, sample_alert, caplog):
    """Test that WARNING handler includes recommendation."""
    sample_alert.severity = AlertSeverity.WARNING

    with caplog.at_level(logging.WARNING):
        router.route_alert(sample_alert)

    # Should include recommendation
    log_message = next(
        record.message for record in caplog.records if "[ANOMALY:WARNING]" in record.message
    )
    assert "Test recommendation" in log_message


def test_handle_critical_includes_recommendation(router, sample_alert, caplog):
    """Test that CRITICAL handler includes recommendation."""
    sample_alert.severity = AlertSeverity.CRITICAL

    with caplog.at_level(logging.ERROR):
        router.route_alert(sample_alert)

    # Should include recommendation
    log_message = next(
        record.message for record in caplog.records if "[ANOMALY:CRITICAL]" in record.message
    )
    assert "Test recommendation" in log_message
