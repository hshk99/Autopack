"""Tests for ROAD-J self-healing engine."""

import pytest

from autopack.telemetry.anomaly_detector import AlertSeverity, AnomalyAlert
from autopack.telemetry.auto_healer import (
    AutoHealingEngine,
    HealingAction,
    HealingDecision,
)


@pytest.fixture
def auto_healer():
    """Create auto-healing engine with default settings."""
    return AutoHealingEngine(enable_aggressive_healing=False)


@pytest.fixture
def aggressive_healer():
    """Create auto-healing engine with aggressive mode enabled."""
    return AutoHealingEngine(enable_aggressive_healing=True)


@pytest.fixture
def token_spike_alert():
    """Sample token spike WARNING alert."""
    return AnomalyAlert(
        alert_id="TOKEN_001",
        severity=AlertSeverity.WARNING,
        metric="tokens",
        phase_id="code_generation",
        current_value=3000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Token usage spike detected",
    )


@pytest.fixture
def failure_rate_critical_alert():
    """Sample failure rate CRITICAL alert."""
    return AnomalyAlert(
        alert_id="FAILURE_001",
        severity=AlertSeverity.CRITICAL,
        metric="failure_rate",
        phase_id="test_generation",
        current_value=0.30,  # 30% failure rate
        threshold=0.20,  # 20% threshold
        baseline=0.05,  # 5% baseline
        recommendation="High failure rate detected, triggering ROAD-J auto-heal",
    )


@pytest.fixture
def duration_warning_alert():
    """Sample duration WARNING alert."""
    return AnomalyAlert(
        alert_id="DURATION_001",
        severity=AlertSeverity.WARNING,
        metric="duration",
        phase_id="refactoring",
        current_value=30.0,
        threshold=20.0,
        baseline=10.0,
        recommendation="Phase duration elevated",
    )


def test_healer_initialization():
    """Test AutoHealingEngine initialization."""
    healer = AutoHealingEngine(enable_aggressive_healing=True, healing_executor=lambda d: True)

    assert healer.enable_aggressive_healing is True
    assert healer.healing_executor is not None
    assert healer.max_healing_attempts == 3
    assert len(healer.healing_history) == 0


def test_heal_token_spike_warning(auto_healer, token_spike_alert):
    """Test healing decision for token spike WARNING."""
    decision = auto_healer.heal(token_spike_alert)

    assert decision is not None
    assert decision.action == HealingAction.OPTIMIZE_PROMPT
    assert decision.confidence > 0.5
    assert "optimizing" in decision.reason.lower()
    assert decision.parameters["phase_id"] == "code_generation"


def test_heal_token_spike_critical(auto_healer):
    """Test healing decision for token spike CRITICAL."""
    critical_alert = AnomalyAlert(
        alert_id="TOKEN_CRITICAL",
        severity=AlertSeverity.CRITICAL,
        metric="tokens",
        phase_id="code_generation",
        current_value=5000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Critical token spike",
    )

    decision = auto_healer.heal(critical_alert)

    assert decision is not None
    assert decision.action == HealingAction.PRUNE_CONTEXT
    assert "prune" in decision.reason.lower() or "context" in decision.reason.lower()
    assert decision.parameters["target_tokens"] == 1500  # 1.5x baseline


def test_heal_failure_rate_conservative(auto_healer, failure_rate_critical_alert):
    """Test failure rate healing with conservative mode (no aggressive healing)."""
    decision = auto_healer.heal(failure_rate_critical_alert)

    assert decision is not None
    # Without aggressive healing, should escalate to human
    assert decision.action == HealingAction.ESCALATE_HUMAN
    assert decision.confidence == 1.0


def test_heal_failure_rate_aggressive(aggressive_healer, failure_rate_critical_alert):
    """Test failure rate healing with aggressive mode enabled."""
    decision = aggressive_healer.heal(failure_rate_critical_alert)

    assert decision is not None
    # With aggressive healing, should replan
    assert decision.action == HealingAction.REPLAN_PHASE
    assert decision.confidence >= 0.7
    assert decision.parameters["phase_id"] == "test_generation"


def test_heal_duration_moderate_warning(auto_healer):
    """Test duration WARNING with moderate overage (no escalation needed)."""
    # Duration is 25s, threshold is 20s (1.25x), not >1.3x threshold (26s)
    moderate_alert = AnomalyAlert(
        alert_id="DURATION_MOD",
        severity=AlertSeverity.WARNING,
        metric="duration",
        phase_id="refactoring",
        current_value=25.0,
        threshold=20.0,
        baseline=10.0,
        recommendation="Phase duration slightly elevated",
    )

    decision = auto_healer.heal(moderate_alert)

    assert decision is not None
    # Moderate overage (1.25x < 1.3x threshold): should be alert only
    assert decision.action == HealingAction.ALERT_ONLY
    assert decision.confidence > 0.5


def test_heal_duration_significant_warning(auto_healer):
    """Test duration WARNING with significant overage (>30% over threshold)."""
    significant_alert = AnomalyAlert(
        alert_id="DURATION_SIG",
        severity=AlertSeverity.WARNING,
        metric="duration",
        phase_id="refactoring",
        current_value=30.0,
        threshold=20.0,
        baseline=10.0,
        recommendation="Duration significantly elevated",
    )

    decision = auto_healer.heal(significant_alert)

    assert decision is not None
    # 30s is 1.5x threshold (20s), which is >1.3x, should escalate
    assert decision.action == HealingAction.ESCALATE_MODEL
    assert decision.parameters["phase_id"] == "refactoring"


def test_heal_duration_critical(auto_healer):
    """Test duration CRITICAL alert."""
    critical_alert = AnomalyAlert(
        alert_id="DURATION_CRITICAL",
        severity=AlertSeverity.CRITICAL,
        metric="duration",
        phase_id="testing",
        current_value=60.0,
        threshold=30.0,
        baseline=15.0,
        recommendation="Critical duration exceeded",
    )

    decision = auto_healer.heal(critical_alert)

    assert decision is not None
    assert decision.action == HealingAction.ESCALATE_MODEL
    assert "escalat" in decision.reason.lower()
    assert decision.parameters.get("extend_timeout_by") == 1.5


def test_heal_info_alert(auto_healer):
    """Test that INFO alerts result in alert-only action."""
    info_alert = AnomalyAlert(
        alert_id="INFO_001",
        severity=AlertSeverity.INFO,
        metric="tokens",
        phase_id="some_phase",
        current_value=1500.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Minor increase observed",
    )

    decision = auto_healer.heal(info_alert)

    assert decision is not None
    assert decision.action == HealingAction.ALERT_ONLY
    assert decision.confidence == 1.0


def test_max_healing_attempts_exceeded(auto_healer, token_spike_alert):
    """Test that healing attempts are limited per phase."""
    # Perform max_healing_attempts (3) healing attempts
    for i in range(3):
        decision = auto_healer.heal(token_spike_alert)
        assert decision.action != HealingAction.ESCALATE_HUMAN

    # 4th attempt should escalate to human
    decision = auto_healer.heal(token_spike_alert)
    assert decision.action == HealingAction.ESCALATE_HUMAN
    assert "max healing attempts" in decision.reason.lower()


def test_healing_history_tracking(auto_healer, token_spike_alert):
    """Test that healing attempts are tracked correctly."""
    phase_id = token_spike_alert.phase_id

    # Initially no history
    assert auto_healer.healing_history.get(phase_id, 0) == 0

    # First heal
    auto_healer.heal(token_spike_alert)
    assert auto_healer.healing_history[phase_id] == 1

    # Second heal
    auto_healer.heal(token_spike_alert)
    assert auto_healer.healing_history[phase_id] == 2


def test_reset_healing_history_specific_phase(auto_healer, token_spike_alert):
    """Test resetting healing history for specific phase."""
    phase_id = token_spike_alert.phase_id

    # Perform healing
    auto_healer.heal(token_spike_alert)
    assert auto_healer.healing_history[phase_id] == 1

    # Reset specific phase
    auto_healer.reset_healing_history(phase_id)
    assert auto_healer.healing_history.get(phase_id, 0) == 0


def test_reset_healing_history_all_phases(auto_healer, token_spike_alert):
    """Test resetting all healing history."""
    # Heal multiple phases
    alert1 = token_spike_alert
    alert2 = AnomalyAlert(
        alert_id="ALERT2",
        severity=AlertSeverity.WARNING,
        metric="duration",
        phase_id="another_phase",
        current_value=30.0,
        threshold=20.0,
        baseline=10.0,
        recommendation="Test",
    )

    auto_healer.heal(alert1)
    auto_healer.heal(alert2)

    assert len(auto_healer.healing_history) == 2

    # Reset all
    auto_healer.reset_healing_history()
    assert len(auto_healer.healing_history) == 0


def test_get_healing_stats(auto_healer, token_spike_alert, failure_rate_critical_alert):
    """Test retrieval of healing statistics."""
    # Perform some healing
    auto_healer.heal(token_spike_alert)
    auto_healer.heal(failure_rate_critical_alert)

    # Exhaust attempts for one phase
    for _ in range(2):
        auto_healer.heal(token_spike_alert)

    stats = auto_healer.get_healing_stats()

    assert stats["total_phases_healed"] == 2
    assert stats["phases_at_max_attempts"] == 1  # token_spike_alert phase
    assert "code_generation" in stats["healing_history"]
    assert stats["healing_history"]["code_generation"] == 3


def test_healing_executor_callback(token_spike_alert):
    """Test that healing executor callback is called."""
    callback_called = []

    def mock_executor(decision: HealingDecision) -> bool:
        callback_called.append(decision)
        return True

    healer = AutoHealingEngine(healing_executor=mock_executor)
    healer.heal(token_spike_alert)

    assert len(callback_called) == 1
    assert callback_called[0].action == HealingAction.OPTIMIZE_PROMPT


def test_healing_executor_not_called_for_alert_only(auto_healer):
    """Test that executor is not invoked for ALERT_ONLY actions."""
    callback_called = []

    def mock_executor(decision: HealingDecision) -> bool:
        callback_called.append(decision)
        return True

    auto_healer.healing_executor = mock_executor

    info_alert = AnomalyAlert(
        alert_id="INFO",
        severity=AlertSeverity.INFO,
        metric="tokens",
        phase_id="test",
        current_value=1000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Info only",
    )

    auto_healer.heal(info_alert)

    # ALERT_ONLY should not trigger executor
    assert len(callback_called) == 0


def test_healing_decision_dataclass():
    """Test HealingDecision dataclass creation."""
    alert = AnomalyAlert(
        alert_id="TEST",
        severity=AlertSeverity.WARNING,
        metric="tokens",
        phase_id="test_phase",
        current_value=3000.0,
        threshold=2000.0,
        baseline=1000.0,
        recommendation="Test alert",
    )

    decision = HealingDecision(
        alert=alert,
        action=HealingAction.OPTIMIZE_PROMPT,
        reason="Test reason",
        parameters={"key": "value"},
        confidence=0.75,
    )

    assert decision.alert == alert
    assert decision.action == HealingAction.OPTIMIZE_PROMPT
    assert decision.reason == "Test reason"
    assert decision.parameters["key"] == "value"
    assert decision.confidence == 0.75


def test_healing_action_enum():
    """Test HealingAction enum values."""
    assert HealingAction.PRUNE_CONTEXT.value == "prune_context"
    assert HealingAction.ESCALATE_MODEL.value == "escalate_model"
    assert HealingAction.REPLAN_PHASE.value == "replan_phase"
    assert HealingAction.ALERT_ONLY.value == "alert_only"
    assert HealingAction.ESCALATE_HUMAN.value == "escalate_human"


def test_unknown_critical_metric_defaults_to_alert_only(auto_healer):
    """Test that unknown critical metrics default to ALERT_ONLY."""
    unknown_alert = AnomalyAlert(
        alert_id="UNKNOWN",
        severity=AlertSeverity.CRITICAL,
        metric="unknown_metric",
        phase_id="test",
        current_value=100.0,
        threshold=50.0,
        baseline=25.0,
        recommendation="Unknown metric anomaly",
    )

    decision = auto_healer.heal(unknown_alert)

    assert decision is not None
    assert decision.action == HealingAction.ALERT_ONLY
    assert "unknown" in decision.reason.lower()


def test_healing_preserves_alert_context(auto_healer, token_spike_alert):
    """Test that healing decision preserves original alert context."""
    decision = auto_healer.heal(token_spike_alert)

    assert decision is not None
    assert decision.alert == token_spike_alert
    assert decision.alert.alert_id == "TOKEN_001"
    assert decision.alert.phase_id == "code_generation"
