"""Contract tests for approvals router.

These tests verify the approvals router behavior contract is preserved
during the extraction from main.py to api/routes/approvals.py (PR-API-3f).
"""

import pytest


class TestApprovalsRouterContract:
    """Contract tests for approvals router configuration."""

    def test_router_has_approvals_tag(self):
        """Contract: Approvals router is tagged as 'approvals'."""
        from autopack.api.routes.approvals import router

        assert "approvals" in router.tags


class TestRequestApprovalContract:
    """Contract tests for request_approval endpoint."""

    @pytest.mark.asyncio
    async def test_request_approval_returns_pending_status(self):
        """Contract: /approval/request returns pending status when not auto-approved."""
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from autopack.api.routes.approvals import request_approval

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(
            return_value={
                "phase_id": "test-phase",
                "run_id": "test-run",
                "context": "test",
                "decision_info": {},
            }
        )

        with patch.dict(os.environ, {"AUTO_APPROVE_BUILD113": "false"}, clear=False):
            with patch(
                "autopack.notifications.telegram_notifier.TelegramNotifier"
            ) as mock_notifier_cls:
                mock_notifier = MagicMock()
                mock_notifier.is_configured.return_value = False
                mock_notifier_cls.return_value = mock_notifier

                result = await request_approval(request=mock_request, db=mock_db)

        assert result["status"] == "pending"
        assert "approval_id" in result

    @pytest.mark.asyncio
    async def test_request_approval_returns_500_on_error(self):
        """Contract: /approval/request returns 500 on internal error."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.approvals import request_approval

        mock_db = MagicMock()
        mock_db.add.side_effect = Exception("Database error")

        mock_request = AsyncMock()
        mock_request.json = AsyncMock(
            return_value={
                "phase_id": "test-phase",
                "run_id": "test-run",
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            await request_approval(request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 500
        assert "failed" in exc_info.value.detail.lower()


class TestGetApprovalStatusContract:
    """Contract tests for get_approval_status endpoint."""

    @pytest.mark.asyncio
    async def test_approval_status_returns_404_for_missing(self):
        """Contract: /approval/status/{id} returns 404 for missing approval."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.approvals import get_approval_status

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_approval_status(approval_id=999, db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approval_status_returns_approval_fields(self):
        """Contract: /approval/status/{id} returns expected fields."""
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        from autopack.api.routes.approvals import get_approval_status

        mock_approval = MagicMock()
        mock_approval.id = 123
        mock_approval.run_id = "test-run"
        mock_approval.phase_id = "test-phase"
        mock_approval.status = "pending"
        mock_approval.requested_at = datetime.now(timezone.utc)
        mock_approval.responded_at = None
        mock_approval.timeout_at = datetime.now(timezone.utc)
        mock_approval.approval_reason = None
        mock_approval.rejected_reason = None
        mock_approval.response_method = None

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_approval
        mock_db.query.return_value = mock_query

        result = await get_approval_status(approval_id=123, db=mock_db, _auth="test")

        assert result["approval_id"] == 123
        assert result["run_id"] == "test-run"
        assert result["phase_id"] == "test-phase"
        assert result["status"] == "pending"
        assert "requested_at" in result
        assert "timeout_at" in result


class TestGetPendingApprovalsContract:
    """Contract tests for get_pending_approvals endpoint."""

    @pytest.mark.asyncio
    async def test_pending_approvals_returns_count_and_list(self):
        """Contract: /approval/pending returns count and requests list."""
        from unittest.mock import MagicMock

        from autopack.api.routes.approvals import get_pending_approvals

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        result = await get_pending_approvals(db=mock_db, _auth="test")

        assert "count" in result
        assert "requests" in result
        assert result["count"] == 0
        assert result["requests"] == []

    @pytest.mark.asyncio
    async def test_pending_approvals_returns_500_on_error(self):
        """Contract: /approval/pending returns 500 on internal error."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.approvals import get_pending_approvals

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        with pytest.raises(HTTPException) as exc_info:
            await get_pending_approvals(db=mock_db, _auth="test")

        assert exc_info.value.status_code == 500


class TestTelegramWebhookContract:
    """Contract tests for telegram_webhook endpoint."""

    @pytest.mark.asyncio
    async def test_webhook_returns_ok_without_callback_query(self):
        """Contract: /telegram/webhook returns ok when no callback_query."""
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from autopack.api.routes.approvals import telegram_webhook

        mock_db = MagicMock()
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={})

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            result = await telegram_webhook(request=mock_request, db=mock_db)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_webhook_returns_ok_without_callback_data(self):
        """Contract: /telegram/webhook returns ok when no callback data."""
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from autopack.api.routes.approvals import telegram_webhook

        mock_db = MagicMock()
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(
            return_value={
                "callback_query": {
                    "id": "123",
                    # No "data" field
                }
            }
        )

        with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
            result = await telegram_webhook(request=mock_request, db=mock_db)

        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_webhook_rejects_without_secret_in_production(self):
        """Contract: /telegram/webhook rejects requests without proper verification."""
        import os
        from unittest.mock import AsyncMock, MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.approvals import telegram_webhook

        mock_db = MagicMock()
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={})

        # Not in testing mode, and verification will fail
        with patch.dict(os.environ, {"TESTING": "0"}, clear=False):
            with patch(
                "autopack.api.routes.approvals.verify_telegram_webhook_crypto"
            ) as mock_verify:
                mock_verify.return_value = False

                with pytest.raises(HTTPException) as exc_info:
                    await telegram_webhook(request=mock_request, db=mock_db)

        assert exc_info.value.status_code == 403
