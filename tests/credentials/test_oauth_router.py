"""Tests for OAuth router endpoint authorization."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

from autopack.auth.oauth_router import refresh_credential, reset_failure_count


class TestOAuthRouterAuthorization:
    """Tests for OAuth router admin-only endpoints."""

    def test_refresh_requires_superuser(self):
        """Test that refresh endpoint requires superuser privileges."""
        # Create a non-superuser mock
        non_admin_user = MagicMock()
        non_admin_user.is_superuser = False

        # Should raise 403
        with pytest.raises(HTTPException) as exc_info:
            # We need to run this synchronously for testing
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                refresh_credential(
                    provider="test",
                    background_tasks=MagicMock(),
                    max_retries=3,
                    current_user=non_admin_user,
                )
            )

        assert exc_info.value.status_code == 403
        assert "Admin privileges required" in exc_info.value.detail

    def test_reset_requires_superuser(self):
        """Test that reset endpoint requires superuser privileges."""
        # Create a non-superuser mock
        non_admin_user = MagicMock()
        non_admin_user.is_superuser = False

        # Should raise 403
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                reset_failure_count(
                    provider="test",
                    current_user=non_admin_user,
                )
            )

        assert exc_info.value.status_code == 403
        assert "Admin privileges required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_refresh_allows_superuser(self):
        """Test that refresh endpoint allows superuser."""
        admin_user = MagicMock()
        admin_user.is_superuser = True

        with patch("autopack.auth.oauth_router.get_credential_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_cred = MagicMock()
            mock_cred.refresh_token = "test_token"
            mock_manager.get_credential.return_value = mock_cred
            mock_get_manager.return_value = mock_manager

            mock_bg_tasks = MagicMock()

            result = await refresh_credential(
                provider="test",
                background_tasks=mock_bg_tasks,
                max_retries=3,
                current_user=admin_user,
            )

            assert result["status"] == "queued"
            assert result["provider"] == "test"

    @pytest.mark.asyncio
    async def test_reset_allows_superuser(self):
        """Test that reset endpoint allows superuser."""
        admin_user = MagicMock()
        admin_user.is_superuser = True

        with patch("autopack.auth.oauth_router.get_credential_manager") as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.reset_failure_count.return_value = True
            mock_get_manager.return_value = mock_manager

            result = await reset_failure_count(
                provider="test",
                current_user=admin_user,
            )

            assert result["status"] == "success"
            assert result["provider"] == "test"
