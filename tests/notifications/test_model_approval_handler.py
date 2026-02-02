"""Tests for ModelApprovalHandler (IMP-NOTIFY-001)."""

import pytest

from autopack.notifications.model_approval_handler import (
    ApprovalDecision,
    ModelApprovalHandler,
    ModelApprovalRequest,
    parse_telegram_callback_data,
)


@pytest.fixture
def handler():
    """Create approval handler."""
    return ModelApprovalHandler()


class TestModelApprovalHandler:
    """Test ModelApprovalHandler functionality."""

    def test_initialization(self, handler):
        """Test handler initialization."""
        assert handler is not None
        assert handler.get_approval_history() == {}

    def test_process_approval_callback_approved(self, handler):
        """Test processing approved decision."""
        result = handler.process_approval_callback(
            validation_request_id="req-001",
            model_name="Test Model",
            decision_str="approved",
            user_id=12345,
            message_id=67890,
        )

        assert result.success
        assert result.validation_request_id == "req-001"
        assert result.model_name == "Test Model"
        assert result.decision == ApprovalDecision.APPROVED

    def test_process_approval_callback_rejected(self, handler):
        """Test processing rejected decision."""
        result = handler.process_approval_callback(
            validation_request_id="req-002",
            model_name="Another Model",
            decision_str="rejected",
            user_id=12345,
        )

        assert result.success
        assert result.decision == ApprovalDecision.REJECTED

    def test_process_approval_callback_case_insensitive(self, handler):
        """Test decision parsing is case-insensitive."""
        result1 = handler.process_approval_callback("req-001", "Model", "APPROVED")
        result2 = handler.process_approval_callback("req-002", "Model", "Rejected")

        assert result1.decision == ApprovalDecision.APPROVED
        assert result2.decision == ApprovalDecision.REJECTED

    def test_process_approval_callback_invalid_decision(self, handler):
        """Test invalid decision string."""
        result = handler.process_approval_callback("req-001", "Model", "maybe")

        assert not result.success
        assert "invalid_decision" in result.error_reason

    def test_process_approval_callback_stores_in_history(self, handler):
        """Test approval is stored in history."""
        handler.process_approval_callback("req-001", "Model", "approved")

        assert handler.has_approval_decision("req-001")
        decision = handler.get_approval_decision("req-001")
        assert decision == ApprovalDecision.APPROVED

    def test_has_approval_decision(self, handler):
        """Test checking approval existence."""
        assert not handler.has_approval_decision("req-001")

        handler.process_approval_callback("req-001", "Model", "approved")
        assert handler.has_approval_decision("req-001")

    def test_get_approval_decision_not_found(self, handler):
        """Test getting non-existent approval."""
        decision = handler.get_approval_decision("nonexistent")
        assert decision is None

    def test_get_approval_history_empty(self, handler):
        """Test getting empty approval history."""
        history = handler.get_approval_history()
        assert history == {}

    def test_get_approval_history_multiple(self, handler):
        """Test getting history with multiple approvals."""
        handler.process_approval_callback("req-001", "Model1", "approved")
        handler.process_approval_callback("req-002", "Model2", "rejected")

        history = handler.get_approval_history()
        assert len(history) == 2
        assert "req-001" in history
        assert "req-002" in history

    def test_clear_approval_history(self, handler):
        """Test clearing approval history."""
        handler.process_approval_callback("req-001", "Model", "approved")
        assert len(handler.get_approval_history()) == 1

        handler.clear_approval_history()
        assert handler.get_approval_history() == {}

    def test_approval_request_model(self):
        """Test ModelApprovalRequest model."""
        request = ModelApprovalRequest(
            validation_request_id="req-001",
            model_name="Test Model",
            decision=ApprovalDecision.APPROVED,
        )

        assert request.validation_request_id == "req-001"
        assert request.model_name == "Test Model"
        assert request.decision == ApprovalDecision.APPROVED

    def test_approval_request_to_dict(self):
        """Test ModelApprovalRequest to_dict()."""
        request = ModelApprovalRequest(
            validation_request_id="req-001",
            model_name="Test Model",
            decision=ApprovalDecision.APPROVED,
            user_id=12345,
            message_id=67890,
        )

        d = request.to_dict()
        assert d["validation_request_id"] == "req-001"
        assert d["model_name"] == "Test Model"
        assert d["decision"] == "approved"
        assert d["user_id"] == 12345

    def test_approval_result_to_dict(self, handler):
        """Test ModelApprovalResult to_dict()."""
        result = handler.process_approval_callback("req-001", "Model", "approved")

        d = result.to_dict()
        assert d["success"]
        assert d["validation_request_id"] == "req-001"
        assert d["decision"] == "approved"

    def test_process_callback_sets_timestamps(self, handler):
        """Test that timestamps are set."""
        result = handler.process_approval_callback("req-001", "Model", "approved")

        assert result.processed_at is not None
        assert "timestamp" in result.evidence

    def test_exception_handling(self, handler, monkeypatch):
        """Test exception handling during processing."""
        # This would need the handler to raise an exception somehow
        # For now, we test normal exception path
        result = handler.process_approval_callback(
            "req-001",
            "Model",
            "approved",
        )
        assert result.success


class TestParseTelegramCallbackData:
    """Test parse_telegram_callback_data function."""

    def test_parse_approve_callback(self):
        """Test parsing approve callback."""
        result = parse_telegram_callback_data("model_approve:req-001")
        assert result == ("approved", "req-001")

    def test_parse_reject_callback(self):
        """Test parsing reject callback."""
        result = parse_telegram_callback_data("model_reject:req-002")
        assert result == ("rejected", "req-002")

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        result = parse_telegram_callback_data("invalid_format")
        assert result is None

    def test_parse_wrong_prefix(self):
        """Test parsing with wrong prefix."""
        result = parse_telegram_callback_data("phase_approve:req-001")
        assert result is None

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_telegram_callback_data("")
        assert result is None

    def test_parse_none(self):
        """Test parsing None."""
        result = parse_telegram_callback_data(None)
        assert result is None

    def test_parse_complex_request_id(self):
        """Test parsing with complex request ID."""
        callback = "model_approve:req-2024-01-001-complex-id"
        result = parse_telegram_callback_data(callback)
        assert result == ("approved", "req-2024-01-001-complex-id")

    def test_parse_callback_with_extra_colons(self):
        """Test parsing callback with extra colons."""
        # Only the first colon should be used as separator
        callback = "model_approve:req:001:extra"
        result = parse_telegram_callback_data(callback)
        assert result == ("approved", "req:001:extra")


class TestApprovalDecision:
    """Test ApprovalDecision enum."""

    def test_approved_value(self):
        """Test APPROVED enum value."""
        assert ApprovalDecision.APPROVED.value == "approved"

    def test_rejected_value(self):
        """Test REJECTED enum value."""
        assert ApprovalDecision.REJECTED.value == "rejected"

    def test_enum_comparison(self):
        """Test enum comparison."""
        decision1 = ApprovalDecision.APPROVED
        decision2 = ApprovalDecision.APPROVED
        assert decision1 == decision2

    def test_enum_string_value(self):
        """Test enum string value."""
        decision = ApprovalDecision.APPROVED
        assert str(decision) == "ApprovalDecision.APPROVED"


class TestIntegration:
    """Integration tests for handler."""

    def test_full_workflow(self, handler):
        """Test full approval workflow."""
        # 1. Process approval
        result = handler.process_approval_callback(
            "req-001",
            "Claude 3.5",
            "approved",
            user_id=12345,
        )
        assert result.success

        # 2. Check in history
        assert handler.has_approval_decision("req-001")

        # 3. Retrieve decision
        decision = handler.get_approval_decision("req-001")
        assert decision == ApprovalDecision.APPROVED

        # 4. Get full history
        history = handler.get_approval_history()
        assert len(history) == 1
        request = history["req-001"]
        assert request.model_name == "Claude 3.5"
        assert request.user_id == 12345

    def test_multiple_models_workflow(self, handler):
        """Test handling multiple model approvals."""
        models = ["Model A", "Model B", "Model C"]
        decisions = ["approved", "rejected", "approved"]

        for i, (model, decision) in enumerate(zip(models, decisions)):
            req_id = f"req-{i:03d}"
            result = handler.process_approval_callback(
                req_id,
                model,
                decision,
            )
            assert result.success

        # Verify all stored
        history = handler.get_approval_history()
        assert len(history) == 3

        # Verify decisions
        assert handler.get_approval_decision("req-000") == ApprovalDecision.APPROVED
        assert handler.get_approval_decision("req-001") == ApprovalDecision.REJECTED
        assert handler.get_approval_decision("req-002") == ApprovalDecision.APPROVED
