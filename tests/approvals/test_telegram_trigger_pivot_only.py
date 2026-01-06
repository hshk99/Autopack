"""Contract-first tests for Telegram approval triggers (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Telegram approval triggers ONLY for pivot-impacting events
- Never active in CI
- Disabled by default, requires explicit configuration
"""

from __future__ import annotations

from unittest.mock import patch



def test_telegram_triggers_on_pivot_intention_change():
    """Telegram approval requested when pivot intention is changed."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-001",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
        affected_pivots=["safety_risk"],
        description="Updating risk_tolerance from 'low' to 'moderate'",
        diff_summary={"changed": ["pivot_intentions.safety_risk.risk_tolerance"]},
    )

    result = should_trigger_approval(request)

    assert result is True


def test_telegram_triggers_on_pivot_constraint_violation():
    """Telegram approval requested when pivot constraint is violated."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-002",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.PIVOT_CONSTRAINT_VIOLATION,
        affected_pivots=["scope_boundaries"],
        description="Action touches protected path from pivot: src/autopack/models.py",
        diff_summary={"protected_paths_touched": ["src/autopack/models.py"]},
    )

    result = should_trigger_approval(request)

    assert result is True


def test_telegram_triggers_on_governance_escalation():
    """Telegram approval requested when governance escalation required."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-003",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.GOVERNANCE_ESCALATION,
        affected_pivots=[],
        description="Risk tier 'critical' requires human approval",
        diff_summary={"risk_level": "critical"},
    )

    result = should_trigger_approval(request)

    assert result is True


def test_telegram_not_triggered_for_normal_retry():
    """Telegram NOT triggered for normal phase retry."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-004",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.NORMAL_RETRY,
        affected_pivots=[],
        description="Retrying phase after transient failure",
        diff_summary={},
    )

    result = should_trigger_approval(request)

    assert result is False


def test_telegram_not_triggered_for_replan():
    """Telegram NOT triggered for normal replan within pivot bounds."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-005",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.NORMAL_REPLAN,
        affected_pivots=[],
        description="Replanning phase approach",
        diff_summary={},
    )

    result = should_trigger_approval(request)

    assert result is False


def test_telegram_not_triggered_for_model_escalation_within_bounds():
    """Telegram NOT triggered for model escalation within pivot budget."""
    from autopack.approvals.service import (
        ApprovalRequest,
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    request = ApprovalRequest(
        request_id="req-006",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.MODEL_ESCALATION_WITHIN_BOUNDS,
        affected_pivots=[],
        description="Escalating to stronger model (within budget)",
        diff_summary={"model_from": "haiku", "model_to": "sonnet"},
    )

    result = should_trigger_approval(request)

    assert result is False


def test_telegram_never_active_in_ci():
    """Telegram service is never active in CI environment."""
    from autopack.approvals.service import get_approval_service
    from autopack.approvals.telegram import TelegramApprovalService

    # Simulate CI environment
    with patch.dict("os.environ", {"CI": "true", "AUTOPACK_TELEGRAM_ENABLED": "true"}):
        service = get_approval_service()

        # Even with TELEGRAM_ENABLED, should NOT return TelegramApprovalService in CI
        assert not isinstance(service, TelegramApprovalService)


def test_telegram_disabled_by_default():
    """Telegram service is disabled by default."""
    from autopack.approvals.service import get_approval_service, NoopApprovalService

    # No environment variables set
    with patch.dict("os.environ", {}, clear=True):
        service = get_approval_service()

        assert isinstance(service, NoopApprovalService)


def test_telegram_enabled_only_with_explicit_config():
    """Telegram service enabled only with explicit configuration."""
    from autopack.approvals.service import get_approval_service
    from autopack.approvals.telegram import TelegramApprovalService

    # Explicit config required
    with patch.dict(
        "os.environ",
        {
            "AUTOPACK_TELEGRAM_ENABLED": "true",
            "AUTOPACK_TELEGRAM_BOT_TOKEN": "test-token",
            "AUTOPACK_TELEGRAM_CHAT_ID": "test-chat",
        },
        clear=True,
    ):
        service = get_approval_service()

        assert isinstance(service, TelegramApprovalService)


def test_telegram_misconfigured_fails_safely():
    """Misconfigured Telegram records evidence and halts if approval required."""
    from autopack.approvals.telegram import TelegramApprovalService
    from autopack.approvals.service import ApprovalRequest, ApprovalTriggerReason

    # Missing required config
    service = TelegramApprovalService(bot_token=None, chat_id=None)

    request = ApprovalRequest(
        request_id="req-007",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
        affected_pivots=["safety_risk"],
        description="Change requiring approval",
        diff_summary={},
    )

    result = service.request_approval(request)

    assert result.success is False
    assert result.error_reason == "telegram_misconfigured"
    assert result.evidence is not None


def test_approval_request_serializable():
    """ApprovalRequest can be serialized for evidence storage."""
    import json

    from autopack.approvals.service import ApprovalRequest, ApprovalTriggerReason

    request = ApprovalRequest(
        request_id="req-008",
        run_id="test-run",
        phase_id="phase-1",
        trigger_reason=ApprovalTriggerReason.PIVOT_INTENTION_CHANGE,
        affected_pivots=["safety_risk", "budget_cost"],
        description="Test request",
        diff_summary={"key": "value"},
    )

    # Should be JSON serializable
    json_str = json.dumps(request.to_dict())
    parsed = json.loads(json_str)

    assert parsed["request_id"] == "req-008"
    assert parsed["trigger_reason"] == "pivot_intention_change"
