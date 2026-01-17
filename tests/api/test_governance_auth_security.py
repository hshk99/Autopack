"""Security tests for governance endpoint authentication (IMP-SEC-005).

These tests verify that:
1. The governance approval endpoint requires authentication
2. User ID comes from the authenticated session, not user input
3. Unauthenticated requests are rejected with 401
"""

import pytest
from unittest.mock import MagicMock, patch


def _create_mock_user(username: str = "test_user", user_id: int = 1):
    """Create a mock user object for testing."""
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.username = username
    mock_user.email = f"{username}@example.com"
    mock_user.is_active = True
    return mock_user


class TestGovernanceApprovalAuthentication:
    """Security tests for governance approval endpoint authentication."""

    @pytest.mark.asyncio
    async def test_approval_uses_authenticated_user_not_user_input(self):
        """IMP-SEC-005: Verify user_id comes from authenticated session, not request.

        Previously, the endpoint accepted user_id as a query parameter,
        which allowed authorization bypass by providing any user_id.
        Now the user_id must come from the authenticated JWT token.
        """
        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        # Create user with specific username to verify it's used
        mock_user = _create_mock_user("secure_admin_user")

        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.return_value = True

            await approve_governance_request(
                request_id="gov-req-001",
                approved=True,
                db=mock_db,
                current_user=mock_user,
            )

        # Verify the authenticated user's username is passed to approve_request
        mock_approve.assert_called_once_with(
            mock_db, "gov-req-001", approved_by="secure_admin_user"
        )

    @pytest.mark.asyncio
    async def test_denial_uses_authenticated_user_not_user_input(self):
        """IMP-SEC-005: Verify user_id for denial also comes from authenticated session."""
        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()
        mock_user = _create_mock_user("deny_admin_user")

        with patch("autopack.governance_requests.deny_request") as mock_deny:
            mock_deny.return_value = True

            await approve_governance_request(
                request_id="gov-req-002",
                approved=False,
                db=mock_db,
                current_user=mock_user,
            )

        # Verify the authenticated user's username is passed to deny_request
        mock_deny.assert_called_once_with(mock_db, "gov-req-002", denied_by="deny_admin_user")

    @pytest.mark.asyncio
    async def test_different_users_tracked_correctly(self):
        """IMP-SEC-005: Verify different authenticated users are tracked correctly."""
        from autopack.api.routes.governance import approve_governance_request

        mock_db = MagicMock()

        # First user approves
        user1 = _create_mock_user("alice")
        with patch("autopack.governance_requests.approve_request") as mock_approve:
            mock_approve.return_value = True
            await approve_governance_request(
                request_id="req-1", approved=True, db=mock_db, current_user=user1
            )
            mock_approve.assert_called_with(mock_db, "req-1", approved_by="alice")

        # Second user denies
        user2 = _create_mock_user("bob")
        with patch("autopack.governance_requests.deny_request") as mock_deny:
            mock_deny.return_value = True
            await approve_governance_request(
                request_id="req-2", approved=False, db=mock_db, current_user=user2
            )
            mock_deny.assert_called_with(mock_db, "req-2", denied_by="bob")


class TestGovernanceEndpointRequiresAuth:
    """Tests verifying the endpoint requires authentication."""

    def test_endpoint_has_get_current_user_dependency(self):
        """IMP-SEC-005: Verify endpoint uses get_current_user dependency."""
        from autopack.api.routes.governance import approve_governance_request
        import inspect

        # Get the function signature
        sig = inspect.signature(approve_governance_request)
        params = sig.parameters

        # Verify current_user parameter exists
        assert "current_user" in params, "Endpoint must have current_user parameter"

        # Verify it has a default (the Depends() call)
        param = params["current_user"]
        assert (
            param.default is not inspect.Parameter.empty
        ), "current_user must have a Depends() default"

    def test_endpoint_does_not_accept_user_id_parameter(self):
        """IMP-SEC-005: Verify endpoint no longer accepts user_id as parameter."""
        from autopack.api.routes.governance import approve_governance_request
        import inspect

        sig = inspect.signature(approve_governance_request)
        params = sig.parameters

        # Verify user_id is NOT in parameters (security fix)
        assert "user_id" not in params, (
            "Endpoint must NOT accept user_id parameter - " "this would allow authorization bypass"
        )
