"""Contract-first tests for Telegram approval triggers (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Telegram approval triggers ONLY for pivot-impacting events
- Never active in CI
- Disabled by default, requires explicit configuration

IMP-TRIGGER-001: Improved with proper fixtures to prevent timing-sensitive
failures and ensure deterministic execution.
"""

from __future__ import annotations



def test_telegram_triggers_on_pivot_intention_change(sample_approval_request):
    """Telegram approval requested when pivot intention is changed.

    Uses fixtures to ensure deterministic execution without timing dependencies.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.trigger_reason = ApprovalTriggerReason.PIVOT_INTENTION_CHANGE
    sample_approval_request.description = "Updating risk_tolerance from 'low' to 'moderate'"
    sample_approval_request.diff_summary = {
        "changed": ["pivot_intentions.safety_risk.risk_tolerance"]
    }

    result = should_trigger_approval(sample_approval_request)

    assert result is True


def test_telegram_triggers_on_pivot_constraint_violation(sample_approval_request):
    """Telegram approval requested when pivot constraint is violated.

    Uses fixtures to ensure deterministic execution.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.request_id = "req-002"
    sample_approval_request.trigger_reason = ApprovalTriggerReason.PIVOT_CONSTRAINT_VIOLATION
    sample_approval_request.affected_pivots = ["scope_boundaries"]
    sample_approval_request.description = (
        "Action touches protected path from pivot: src/autopack/models.py"
    )
    sample_approval_request.diff_summary = {"protected_paths_touched": ["src/autopack/models.py"]}

    result = should_trigger_approval(sample_approval_request)

    assert result is True


def test_telegram_triggers_on_governance_escalation(sample_approval_request):
    """Telegram approval requested when governance escalation required.

    Uses fixtures to ensure deterministic execution.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.request_id = "req-003"
    sample_approval_request.trigger_reason = ApprovalTriggerReason.GOVERNANCE_ESCALATION
    sample_approval_request.affected_pivots = []
    sample_approval_request.description = "Risk tier 'critical' requires human approval"
    sample_approval_request.diff_summary = {"risk_level": "critical"}

    result = should_trigger_approval(sample_approval_request)

    assert result is True


def test_telegram_not_triggered_for_normal_retry(sample_approval_request):
    """Telegram NOT triggered for normal phase retry.

    Uses fixtures to ensure deterministic execution.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.request_id = "req-004"
    sample_approval_request.trigger_reason = ApprovalTriggerReason.NORMAL_RETRY
    sample_approval_request.affected_pivots = []
    sample_approval_request.description = "Retrying phase after transient failure"
    sample_approval_request.diff_summary = {}

    result = should_trigger_approval(sample_approval_request)

    assert result is False


def test_telegram_not_triggered_for_replan(sample_approval_request):
    """Telegram NOT triggered for normal replan within pivot bounds.

    Uses fixtures to ensure deterministic execution.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.request_id = "req-005"
    sample_approval_request.trigger_reason = ApprovalTriggerReason.NORMAL_REPLAN
    sample_approval_request.affected_pivots = []
    sample_approval_request.description = "Replanning phase approach"
    sample_approval_request.diff_summary = {}

    result = should_trigger_approval(sample_approval_request)

    assert result is False


def test_telegram_not_triggered_for_model_escalation_within_bounds(sample_approval_request):
    """Telegram NOT triggered for model escalation within pivot budget.

    Uses fixtures to ensure deterministic execution.
    """
    from autopack.approvals.service import (
        ApprovalTriggerReason,
        should_trigger_approval,
    )

    sample_approval_request.request_id = "req-006"
    sample_approval_request.trigger_reason = ApprovalTriggerReason.MODEL_ESCALATION_WITHIN_BOUNDS
    sample_approval_request.affected_pivots = []
    sample_approval_request.description = "Escalating to stronger model (within budget)"
    sample_approval_request.diff_summary = {"model_from": "haiku", "model_to": "sonnet"}

    result = should_trigger_approval(sample_approval_request)

    assert result is False


def test_telegram_never_active_in_ci(ci_environment, telegram_configured):
    """Telegram service is never active in CI environment.

    Uses fixtures to ensure proper CI environment setup and prevent
    timing-sensitive environment variable issues.
    """
    from autopack.approvals.service import NoopApprovalService, get_approval_service

    service = get_approval_service()

    # Even with TELEGRAM_ENABLED and proper config, should NOT return anything
    # other than NoopApprovalService in CI
    assert isinstance(service, NoopApprovalService)


def test_telegram_disabled_by_default(isolated_env, no_ci_environment):
    """Telegram service is disabled by default.

    Uses fixtures to ensure clean environment without any configuration.
    """
    from autopack.approvals.service import NoopApprovalService, get_approval_service

    service = get_approval_service()

    assert isinstance(service, NoopApprovalService)


def test_telegram_enabled_only_with_explicit_config(
    no_ci_environment, telegram_configured, mock_telegram_api
):
    """Telegram service enabled only with explicit configuration.

    Uses fixtures to provide proper configuration and prevent actual
    network calls during testing.
    """
    from autopack.approvals.service import ChainedApprovalService, get_approval_service

    service = get_approval_service()

    # With proper configuration, should return ChainedApprovalService or TelegramApprovalService
    # (depending on whether other channels are configured)
    assert service is not None
    assert (
        isinstance(service, (ChainedApprovalService))
        or service.__class__.__name__ == "TelegramApprovalService"
    )


def test_telegram_misconfigured_fails_safely(sample_approval_request):
    """Misconfigured Telegram records evidence and halts if approval required.

    Uses fixtures to provide proper test data without timing dependencies.
    """
    from autopack.approvals.telegram import TelegramApprovalService

    # Missing required config
    service = TelegramApprovalService(bot_token=None, chat_id=None)

    sample_approval_request.request_id = "req-007"

    result = service.request_approval(sample_approval_request)

    assert result.success is False
    assert result.error_reason == "telegram_misconfigured"
    assert result.evidence is not None


def test_approval_request_serializable(sample_approval_request):
    """ApprovalRequest can be serialized for evidence storage.

    Uses fixtures to ensure proper test data setup and prevent
    timing-sensitive execution issues.
    """
    import json

    sample_approval_request.request_id = "req-008"
    sample_approval_request.affected_pivots = ["safety_risk", "budget_cost"]
    sample_approval_request.diff_summary = {"key": "value"}

    # Should be JSON serializable
    json_str = json.dumps(sample_approval_request.to_dict())
    parsed = json.loads(json_str)

    assert parsed["request_id"] == "req-008"
    assert parsed["trigger_reason"] == "pivot_intention_change"
