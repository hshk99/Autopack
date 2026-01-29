"""Contract tests for governance router.

These tests verify the governance router behavior contract is preserved
during the extraction from main.py to api/routes/governance.py (PR-API-3e).
"""

import pytest


class TestGovernanceRouterContract:
    """Contract tests for governance router configuration."""

    def test_router_has_governance_prefix(self):
        """Contract: Governance router uses /governance prefix."""
        from autopack.api.routes.governance import router

        assert router.prefix == "/governance"

    def test_router_has_governance_tag(self):
        """Contract: Governance router is tagged as 'governance'."""
        from autopack.api.routes.governance import router

        assert "governance" in router.tags


class TestGetPendingGovernanceRequestsContract:
    """Contract tests for get_pending_governance_requests endpoint."""

    @pytest.mark.asyncio
    async def test_pending_returns_count_and_list(self):
        """Contract: /governance/pending returns count and pending_requests list."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.governance import get_pending_governance_requests

        mock_db = MagicMock()

        with patch("autopack.governance_requests.get_pending_requests") as mock_get_pending:
            mock_get_pending.return_value = []

            result = await get_pending_governance_requests(db=mock_db, _auth="test")

        assert "count" in result
        assert "pending_requests" in result
        assert result["count"] == 0
        assert result["pending_requests"] == []

    @pytest.mark.asyncio
    async def test_pending_returns_serialized_requests(self):
        """Contract: /governance/pending returns serialized request objects."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.governance import get_pending_governance_requests

        mock_db = MagicMock()

        # Create mock request
        mock_request = MagicMock()
        mock_request.to_dict.return_value = {
            "id": "req-123",
            "status": "pending",
            "path": "/some/path",
        }

        with patch("autopack.governance_requests.get_pending_requests") as mock_get_pending:
            mock_get_pending.return_value = [mock_request]

            result = await get_pending_governance_requests(db=mock_db, _auth="test")

        assert result["count"] == 1
        assert len(result["pending_requests"]) == 1
        assert result["pending_requests"][0]["id"] == "req-123"

    @pytest.mark.asyncio
    async def test_pending_returns_500_on_error(self):
        """Contract: /governance/pending returns 500 on internal error."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.governance import get_pending_governance_requests

        mock_db = MagicMock()

        with patch("autopack.governance_requests.get_pending_requests") as mock_get_pending:
            mock_get_pending.side_effect = Exception("Database error")

            with pytest.raises(HTTPException) as exc_info:
                await get_pending_governance_requests(db=mock_db, _auth="test")

        assert exc_info.value.status_code == 500
        assert "Failed to fetch pending requests" in exc_info.value.detail


def _create_mock_user(username: str = "admin"):
    """Create a mock user object for testing."""
    from unittest.mock import MagicMock

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.username = username
    mock_user.email = f"{username}@example.com"
    mock_user.is_active = True
    return mock_user


class TestApproveGovernanceRequestContract:
    """Contract tests for approve_governance_request endpoint."""

    @pytest.mark.asyncio
    async def test_approve_returns_approved_status(self):
        """Contract: /governance/approve/{request_id} returns approved status."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("admin")

        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.return_value = True

            result = await approve_governance_request(
                request_id="req-123", approved=True, db=mock_db, current_user=mock_user
            )

        assert result["status"] == "approved"
        assert result["request_id"] == "req-123"
        assert "approved" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_deny_returns_denied_status(self):
        """Contract: /governance/approve/{request_id} with approved=False returns denied status."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("admin")

        with patch("autopack.governance_requests.deny_request") as mock_deny:
            mock_deny.return_value = True

            result = await approve_governance_request(
                request_id="req-456", approved=False, db=mock_db, current_user=mock_user
            )

        assert result["status"] == "denied"
        assert result["request_id"] == "req-456"
        assert "denied" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_approve_returns_404_for_missing_request(self):
        """Contract: /governance/approve/{request_id} returns 404 for missing request."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("admin")

        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await approve_governance_request(
                    request_id="nonexistent", approved=True, db=mock_db, current_user=mock_user
                )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_approve_returns_500_on_error(self):
        """Contract: /governance/approve/{request_id} returns 500 on internal error."""
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("admin")

        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.side_effect = Exception("Database error")

            with pytest.raises(HTTPException) as exc_info:
                await approve_governance_request(
                    request_id="req-123", approved=True, db=mock_db, current_user=mock_user
                )

        assert exc_info.value.status_code == 500
        assert "Failed to update request" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_approve_uses_authenticated_username(self):
        """Contract: /governance/approve/{request_id} uses authenticated user's username (IMP-SEC-005)."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("authenticated_admin")

        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.return_value = True

            await approve_governance_request(
                request_id="req-123", db=mock_db, current_user=mock_user
            )

        # Verify the authenticated user's username is used, not a user-provided value
        mock_approve.assert_called_once_with(mock_db, "req-123", approved_by="authenticated_admin")
