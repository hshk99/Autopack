"""
Tests for authentication rate limiting.

Verifies that rate limiting prevents brute force attacks on login endpoints.
"""

import os
import pytest
from time import time, sleep
from unittest.mock import MagicMock, patch

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestRateLimiterUnit:
    """Unit tests for RateLimiter class."""

    def test_rate_limiter_initialization(self):
        """Test RateLimiter initializes with correct defaults."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)
        assert limiter.max_requests == 5
        assert limiter.window_seconds == 60
        assert limiter.requests == {}

    def test_rate_limiter_allows_requests_under_limit(self):
        """Test that requests under the limit are allowed."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)
        client_ip = "192.168.1.1"

        # First 5 requests should be allowed
        for i in range(5):
            assert limiter.check_rate_limit(client_ip) is True

    def test_rate_limiter_blocks_requests_over_limit(self):
        """Test that requests over the limit are blocked."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)
        client_ip = "192.168.1.1"

        # First 5 requests allowed
        for i in range(5):
            limiter.check_rate_limit(client_ip)

        # 6th request should be blocked
        assert limiter.check_rate_limit(client_ip) is False

    def test_rate_limiter_resets_after_window(self):
        """Test that rate limit resets after time window expires."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=2, window_seconds=1)
        client_ip = "192.168.1.1"

        # Use up the limit
        assert limiter.check_rate_limit(client_ip) is True
        assert limiter.check_rate_limit(client_ip) is True
        assert limiter.check_rate_limit(client_ip) is False

        # Wait for window to expire
        sleep(1.1)

        # Should allow requests again
        assert limiter.check_rate_limit(client_ip) is True

    def test_rate_limiter_tracks_multiple_ips(self):
        """Test that rate limiter tracks multiple IPs independently."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=2, window_seconds=60)
        client_ip_1 = "192.168.1.1"
        client_ip_2 = "192.168.1.2"

        # Client 1 uses up limit
        assert limiter.check_rate_limit(client_ip_1) is True
        assert limiter.check_rate_limit(client_ip_1) is True
        assert limiter.check_rate_limit(client_ip_1) is False

        # Client 2 should still have full quota
        assert limiter.check_rate_limit(client_ip_2) is True
        assert limiter.check_rate_limit(client_ip_2) is True
        assert limiter.check_rate_limit(client_ip_2) is False

    def test_rate_limiter_removes_old_requests(self):
        """Test that old requests outside the window are removed."""
        from autopack.auth.rate_limiter import RateLimiter

        limiter = RateLimiter(max_requests=3, window_seconds=1)
        client_ip = "192.168.1.1"

        # Add some requests
        limiter.check_rate_limit(client_ip)
        limiter.check_rate_limit(client_ip)

        # Wait for requests to age out
        sleep(1.1)

        # Old requests should be removed, only current one counts
        assert limiter.check_rate_limit(client_ip) is True
        assert len(limiter.requests[client_ip]) == 1


class TestLoginRateLimitIntegration:
    """Integration tests for rate limiting on login endpoint."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock FastAPI Request object."""
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @pytest.fixture
    def test_db(self):
        """Create a test database session."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from autopack.database import Base

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(bind=engine)
        db = TestingSessionLocal()

        try:
            yield db
        finally:
            db.close()

    @pytest.fixture
    def test_user(self, test_db):
        """Create a test user in the database."""
        from autopack.auth.models import User
        from autopack.auth.router import get_password_hash
        from datetime import datetime, timezone

        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=get_password_hash("testpass123"),
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        test_db.add(user)
        test_db.commit()
        test_db.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_login_applies_rate_limiting(self, mock_request, test_db, test_user):
        """Test that login endpoint enforces rate limiting."""
        from autopack.auth.router import login
        from autopack.auth.rate_limiter import login_rate_limiter
        from fastapi.security import OAuth2PasswordRequestForm
        from fastapi import HTTPException

        # Reset rate limiter
        login_rate_limiter.requests.clear()

        # Create form data
        form_data = OAuth2PasswordRequestForm(
            username="testuser",
            password="testpass123",
            scope="",
            client_id=None,
            client_secret=None,
        )

        # First 5 attempts should succeed
        for i in range(5):
            result = await login(request=mock_request, form_data=form_data, db=test_db)
            assert result.access_token is not None
            assert result.token_type == "bearer"

        # 6th attempt should be rate limited
        with pytest.raises(HTTPException) as exc_info:
            await login(request=mock_request, form_data=form_data, db=test_db)

        assert exc_info.value.status_code == 429
        assert "Too many login attempts" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_login_rate_limit_per_ip(self, test_db, test_user):
        """Test that rate limiting is applied per IP address."""
        from autopack.auth.router import login
        from autopack.auth.rate_limiter import login_rate_limiter
        from fastapi.security import OAuth2PasswordRequestForm

        # Reset rate limiter
        login_rate_limiter.requests.clear()

        # Create two different mock requests with different IPs
        request1 = MagicMock()
        request1.client = MagicMock()
        request1.client.host = "192.168.1.100"

        request2 = MagicMock()
        request2.client = MagicMock()
        request2.client.host = "192.168.1.101"

        form_data = OAuth2PasswordRequestForm(
            username="testuser",
            password="testpass123",
            scope="",
            client_id=None,
            client_secret=None,
        )

        # IP1: Use up the rate limit (5 requests)
        for i in range(5):
            await login(request=request1, form_data=form_data, db=test_db)

        # IP2: Should still be able to login
        result = await login(request=request2, form_data=form_data, db=test_db)
        assert result.access_token is not None

    @pytest.mark.asyncio
    async def test_login_rate_limit_with_failed_attempts(self, mock_request, test_db, test_user):
        """Test that rate limiting applies even to failed login attempts."""
        from autopack.auth.router import login
        from autopack.auth.rate_limiter import login_rate_limiter
        from fastapi.security import OAuth2PasswordRequestForm
        from fastapi import HTTPException

        # Reset rate limiter
        login_rate_limiter.requests.clear()

        # Create form data with wrong password
        form_data = OAuth2PasswordRequestForm(
            username="testuser",
            password="wrongpassword",
            scope="",
            client_id=None,
            client_secret=None,
        )

        # First 5 failed attempts
        for i in range(5):
            with pytest.raises(HTTPException) as exc_info:
                await login(request=mock_request, form_data=form_data, db=test_db)
            # Should get 401 Unauthorized, not 429
            assert exc_info.value.status_code == 401

        # 6th attempt should be rate limited (429, not 401)
        with pytest.raises(HTTPException) as exc_info:
            await login(request=mock_request, form_data=form_data, db=test_db)

        assert exc_info.value.status_code == 429
        assert "Too many login attempts" in exc_info.value.detail


class TestRateLimiterGlobalInstance:
    """Tests for the global login_rate_limiter instance."""

    def test_global_limiter_has_correct_defaults(self):
        """Test that global login_rate_limiter has production-ready defaults."""
        from autopack.auth.rate_limiter import login_rate_limiter

        assert login_rate_limiter.max_requests == 5
        assert login_rate_limiter.window_seconds == 60
