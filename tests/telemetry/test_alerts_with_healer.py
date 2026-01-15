"""Tests for AlertRouter integration with ROAD-J AutoHealingEngine."""

import pytest
import logging

from autopack.telemetry.anomaly_detector import AnomalyAlert, AlertSeverity
from autopack.telemetry.alerts import AlertRouter
from autopack.telemetry.auto_healer import AutoHealingEngine, HealingAction


@pytest.fixture
def sample_alert():
    """Sample alert for testing."""
    return AnomalyAlert(
        alert_id="TEST_001",
        severity=AlertSeverity.WARNING,
        metric="tokens",
        phase_id="test_phase",
        current_value=3000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Test recommendation",
    )


@pytest.fixture
def router_without_healer():
    """Alert router without auto-healing."""
    return AlertRouter()


@pytest.fixture
def router_with_healer():
    """Alert router with auto-healing enabled."""
    auto_healer = AutoHealingEngine(enable_aggressive_healing=False)
    return AlertRouter(auto_healer=auto_healer)


def test_router_without_healer_logs_only(router_without_healer, sample_alert, caplog):
    """Test that router without healer just logs alerts."""
    with caplog.at_level(logging.WARNING):
        router_without_healer.route_alert(sample_alert)

    # Should log but not invoke any healing
    assert any("[ANOMALY:WARNING]" in record.message for record in caplog.records)


def test_router_with_healer_invokes_healing(router_with_healer, sample_alert):
    """Test that router with healer invokes auto-healing."""
    # Track healing invocations
    healing_decisions = []

    def mock_executor(decision):
        healing_decisions.append(decision)
        return True

    router_with_healer.auto_healer.healing_executor = mock_executor

    router_with_healer.route_alert(sample_alert)

    # Should have invoked healing
    assert len(healing_decisions) == 1
    assert healing_decisions[0].action == HealingAction.OPTIMIZE_PROMPT


def test_router_healer_on_critical_alert(router_with_healer):
    """Test that critical alerts trigger healing."""
    critical_alert = AnomalyAlert(
        alert_id="CRITICAL_001",
        severity=AlertSeverity.CRITICAL,
        metric="failure_rate",
        phase_id="test_phase",
        current_value=0.30,
        threshold=0.20,
        baseline=0.05,
        recommendation="Critical failure rate",
    )

    healing_decisions = []

    def mock_executor(decision):
        healing_decisions.append(decision)
        return True

    router_with_healer.auto_healer.healing_executor = mock_executor

    router_with_healer.route_alert(critical_alert)

    # Should have invoked healing for critical alert
    assert len(healing_decisions) == 1
    # Should escalate to human (default mode is not aggressive)
    assert healing_decisions[0].action == HealingAction.ESCALATE_HUMAN


def test_router_healer_on_info_alert(router_with_healer):
    """Test that INFO alerts do not trigger healing actions."""
    info_alert = AnomalyAlert(
        alert_id="INFO_001",
        severity=AlertSeverity.INFO,
        metric="tokens",
        phase_id="test_phase",
        current_value=1500.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Minor increase",
    )

    healing_decisions = []

    def mock_executor(decision):
        healing_decisions.append(decision)
        return True

    router_with_healer.auto_healer.healing_executor = mock_executor

    router_with_healer.route_alert(info_alert)

    # INFO alerts result in ALERT_ONLY, which doesn't invoke executor
    assert len(healing_decisions) == 0


def test_router_handles_missing_auto_healer_gracefully(router_without_healer, sample_alert):
    """Test that router handles missing auto_healer gracefully."""
    # Should not raise error when auto_healer is None
    router_without_healer.route_alert(sample_alert)


def test_router_preserves_logging_with_healer(router_with_healer, sample_alert, caplog):
    """Test that logging still occurs when healer is present."""
    with caplog.at_level(logging.WARNING):
        router_with_healer.route_alert(sample_alert)

    # Should still log the alert
    assert any("[ANOMALY:WARNING]" in record.message for record in caplog.records)


def test_router_aggressive_healer_replan_on_critical(sample_alert):
    """Test aggressive healing mode with critical failure rate."""
    aggressive_healer = AutoHealingEngine(enable_aggressive_healing=True)
    router = AlertRouter(auto_healer=aggressive_healer)

    critical_alert = AnomalyAlert(
        alert_id="CRIT",
        severity=AlertSeverity.CRITICAL,
        metric="failure_rate",
        phase_id="test",
        current_value=0.35,
        threshold=0.20,
        baseline=0.05,
        recommendation="Critical",
    )

    healing_decisions = []

    def mock_executor(decision):
        healing_decisions.append(decision)
        return True

    aggressive_healer.healing_executor = mock_executor

    router.route_alert(critical_alert)

    # Aggressive mode should replan, not escalate to human
    assert len(healing_decisions) == 1
    assert healing_decisions[0].action == HealingAction.REPLAN_PHASE
